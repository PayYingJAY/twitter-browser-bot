"""Follow-back controls scoped to the owner's verified followers list."""
import re
import random
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError

DEFAULT_COOLDOWNS = (300,600,1800,3600,43200)


FOLLOW_CARDS = '''nodes => nodes.map(n=>{
    const b=n.querySelector('[data-testid$="-follow"]');
    if(!b || !b.matches('button,[role="button"]'))return null;
    const label=b.getAttribute('aria-label') || b.innerText;
    if(!/^(回关|follow back)(\\s*@\\w+)?$/i.test(label.trim()) &&
       !/^(回关|follow back)$/i.test(b.innerText.trim())) return null;
    const id=(b.dataset.testid||'').match(/^(\\d+)-follow$/)?.[1];
    const handle=label.match(/@([a-z0-9_]{1,15})/i)?.[1] ||
        [...n.querySelectorAll('a[href]')].map(a=>new URL(a.href).pathname)
        .find(p=>/^\\/[a-z0-9_]{1,15}$/i.test(p))?.slice(1);
    return id && handle ? {id,handle} : null;
}).filter(Boolean)'''


def limit_kind(message, status=200):
    message = message.casefold()
    if re.search(r'ratio|5[,.]?000|比例|关注.{0,8}上限.{0,8}粉丝',message):
        return 'ratio'
    if re.search(r'account.{0,15}(locked|suspend|restrict)|账号.{0,8}(锁定|受限|冻结)|验证.{0,6}身份',message):
        return 'account'
    if re.search(r'daily|per day|24.{0,4}hour|每日|每天|当天|今日|一天|24.{0,2}小时',message):
        return 'daily'
    if status in (403,429) or re.search(r'follow.{0,35}(limit|too quickly|more people)|unable to follow|'
            r'too many|rate limit|try again later|关注.{0,12}(频繁|限制|过多|上限)|'
            r'无法.{0,8}关注|不能.{0,8}关注|稍后再试|操作.{0,5}频繁',message):
        return 'temporary'
    return None


def retry_delay(kind, headers, failures, now, schedule=None):
    steps = schedule or DEFAULT_COOLDOWNS
    base = 86400 if kind == 'daily' else steps[min(max(0,failures),len(steps)-1)]
    retry = headers.get('retry-after')
    if retry:
        try:
            seconds = float(retry)
        except ValueError:
            try:
                seconds = parsedate_to_datetime(retry).timestamp()-now
            except (TypeError,ValueError,OverflowError):
                seconds = 0
        base = max(base,seconds)
    try:
        base = max(base,float(headers.get('x-rate-limit-reset','0'))-now)
    except ValueError:
        pass
    return max(1,base)


class FollowBackWorker:
    def __init__(self, runner):
        self.runner = runner
        self.store = runner.store
        self.account = runner.account
        self.url = f'https://x.com/{self.account}/verified_followers'
        self.page = None
        self.next_check = 0
        self.empty_scans = 0
        self.completed = 0
        self.last_response = None
        self.pending_checked = False
        self.last_attempt_at = 0

    def interval(self):
        options=self.runner.config.get('follow_back',{})
        legacy=options.get('check_interval_seconds',300)
        return options.get('interval_seconds',[legacy,legacy])

    def summary(self):
        state = self.store.follow_state()
        return dict(enabled=True,completed=self.completed,next_follow_at=self.next_check,
                    interval_seconds=self.interval(),**state)

    def observe(self, response):
        parsed=urlsplit(response.url)
        if (response.request.method == 'POST' and parsed.hostname in ('x.com','api.x.com','api.twitter.com')
                and re.search(r'friend|follow',parsed.path,re.I)):
            self.last_response = response

    def confirm_visible(self, identity, handle):
        followed=self.page.locator(f'[data-testid="primaryColumn"] [data-testid="{identity}-unfollow"]')
        if not followed.count() or not followed.first.is_visible():
            return False
        requested=bool(re.search(r'等待|requested|pending',followed.first.inner_text(),re.I))
        self.store.mark_follow(identity,'requested' if requested else 'confirmed')
        self.store.set_follow_state(0)
        self.completed += 1
        self.empty_scans=0
        self.next_check=(self.last_attempt_at or time.time())+random.uniform(*self.interval())
        self.last_attempt_at=0
        self.runner.log.info('%s：@%s（认证关注者列表）',
                             '已发送回关申请' if requested else '已回关',handle)
        return True

    def recheck(self, identity, handle):
        # A full navigation removes optimistic UI state; this never clicks a follow control.
        self.load()
        for _ in range(6):
            self.runner.check_stop()
            self.runner.guard(self.page,account=True,action_alerts=False)
            if self.confirm_visible(identity,handle):
                return True
            if self.page.locator(f'[data-testid="primaryColumn"] [data-testid="{identity}-follow"]').count():
                return False
            self.page.evaluate('(dy)=>window.scrollBy(0,dy)',700)
            self.page.wait_for_timeout(1000)
        return False

    def cooldown(self, kind, headers=None, pending_id=None):
        old = self.store.follow_state()
        failures = old['failures'] + 1
        blocked = kind in ('ratio','account')
        steps=self.runner.config.get('follow_back',{}).get('cooldown_seconds',DEFAULT_COOLDOWNS)
        seconds = 0 if blocked else retry_delay(kind,headers or {},old['failures'],time.time(),steps)
        resume_at = 0 if blocked else time.time()+seconds
        reason = {'ratio':'关注比例限制，需要人工检查','account':'账号受限，需要人工处理',
                  'daily':'每日回关额度限制','temporary':'回关操作频率限制','unknown':'回关结果待核实'}[kind]
        self.store.set_follow_state(resume_at,reason,failures,blocked)
        if pending_id and kind != 'unknown':
            self.store.mark_follow(pending_id,'limited')
        until = '等待人工处理' if blocked else datetime.fromtimestamp(resume_at).astimezone().isoformat(timespec='seconds')
        self.runner.log.info('回关暂停：%s；下次检查 %s',reason,until)
        self.runner.status('running')

    def feedback(self):
        alerts = ' '.join(self.page.locator('[role="alert"], [data-testid="toast"]').all_text_contents())
        status = 200
        headers = {}
        response = self.last_response
        if response:
            status = response.status
            try:
                headers = response.all_headers()
                data = response.json()
                errors = (data.get('errors') or []) if isinstance(data,dict) else []
                if not isinstance(errors,list):
                    errors=[]
                alerts += ' ' + ' '.join(str(error.get('message','')) for error in errors if isinstance(error,dict))
                # X's following cap may use a numeric error without a useful HTTP status.
                if any(error.get('code') == 161 for error in errors if isinstance(error,dict)):
                    alerts += ' unable to follow more people'
            except (PlaywrightError,ValueError):
                pass
        kind=limit_kind(alerts,status)
        if response and status == 200:
            try:
                data=response.json()
                if isinstance(data,dict) and data.get('errors') and kind is None:
                    kind='account'
            except (PlaywrightError,ValueError):
                pass
        return kind,headers

    def acknowledged(self, identity):
        response=self.last_response
        if response is None or not 200 <= response.status < 300:
            return False
        try:
            data=response.json()
        except (PlaywrightError,ValueError):
            return False
        if not isinstance(data,dict) or data.get('errors'):
            return False
        returned_id=data.get('id_str') or data.get('rest_id')
        if returned_id is not None and str(returned_id) != identity:
            return False
        if data.get('following') is False and not data.get('follow_request_sent'):
            return False
        return True

    def tick(self, context):
        state = self.store.follow_state()
        now = time.time()
        if not self.pending_checked and not state['blocked'] and state['reason']=='回关结果待核实':
            self.pending_checked=True
            pending=self.store.pending_follows()
            if pending:
                if self.page is None or self.page.is_closed():
                    self.page=self.runner.new_work_page(context)
                    self.page.on('response',self.observe)
                for identity,handle in pending:
                    self.recheck(identity,handle)
                state=self.store.follow_state()
        if state['blocked'] or now < state['resume_at'] or now < self.next_check:
            return False
        self.runner.check_stop()
        if state['resume_at']:
            self.store.set_follow_state(0,failures=state['failures'])
        if self.page is None or self.page.is_closed():
            self.page = self.runner.new_work_page(context)
            self.page.on('response',self.observe)
            self.load()
        elif state['resume_at'] or self.empty_scans >= 4:
            self.load()
        path = urlsplit(self.page.url)
        if path.hostname != 'x.com' or path.path.rstrip('/').casefold() != f'/{self.account}/verified_followers':
            raise RuntimeError('回关页面已离开指定认证关注者列表，已停止')
        self.runner.guard(self.page,account=True,action_alerts=False)
        kind,headers = self.feedback()
        if kind:
            self.cooldown(kind,headers)
            return False
        cards = self.page.locator('[data-testid="primaryColumn"] [data-testid="UserCell"]')
        candidates = cards.evaluate_all(FOLLOW_CARDS)
        selected = next((item for item in candidates if item['handle'].casefold() != self.account and
                         self.store.follow_status(item['id']) not in ('confirmed','requested','pending')),None)
        if selected is None:
            self.empty_scans += 1
            self.page.evaluate('(dy)=>window.scrollBy(0,dy)',700)
            self.next_check = now + (300 if self.empty_scans >= 4 else 10)
            return False
        identity,handle = selected['id'],selected['handle']
        button = self.page.locator(f'[data-testid="primaryColumn"] [data-testid="{identity}-follow"]')
        # Recheck the live control rather than acting on a stale snapshot or a recommendation.
        label = (button.get_attribute('aria-label') or button.inner_text()).strip()
        text = button.inner_text().strip()
        if not (re.fullmatch(r'(回关|follow back)(\s*@[a-z0-9_]+)?',label,re.I) or
                re.fullmatch(r'回关|follow back',text,re.I)):
            return False
        self.runner.check_stop()
        if not self.runner.in_work_hours():
            return False
        if not self.store.reserve_follow(identity,handle):
            return False
        self.runner.phase = 'follow_back'
        self.runner.active_page = self.page
        self.runner.status('following')
        self.last_response = None
        try:
            self.last_attempt_at=time.time()
            button.click(timeout=10000)
            deadline = time.monotonic()+15
            followed = self.page.locator(f'[data-testid="primaryColumn"] [data-testid="{identity}-unfollow"]')
            while time.monotonic() < deadline:
                self.runner.check_stop()
                kind,headers = self.feedback()
                if kind:
                    self.cooldown(kind,headers,identity)
                    return True  # A click consumed this action slot, even when limited.
                if followed.count() and followed.first.is_visible() and self.acknowledged(identity) and self.confirm_visible(identity,handle):
                    return True
                self.page.wait_for_timeout(500)
            if self.recheck(identity,handle):
                return True
            self.cooldown('unknown',pending_id=identity)
            self.runner.log.info('回关结果未确认：@%s，保留待核实记录，不重复点击该账号',handle)
            return True
        except PlaywrightError:
            self.cooldown('unknown',pending_id=identity)
            self.runner.log.info('回关页面操作中断：@%s，保留待核实记录',handle)
            return True

    def load(self):
        self.last_response = None
        self.page.goto(self.url,wait_until='domcontentloaded',timeout=60000)
        self.page.locator('[data-testid="primaryColumn"]').wait_for(state='visible',timeout=30000)
        self.runner.guard(self.page,account=True,action_alerts=False)
        # Let the first user cells render; an empty list is also a valid result.
        self.page.wait_for_timeout(1500)
        self.empty_scans = 0
        self.next_check = 0
