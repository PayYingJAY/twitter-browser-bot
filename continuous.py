"""Continuous X browsing with durable deduplication and observable pacing."""
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from activity import ActivityStore, RunnerLock, own_replies, post_id
from ai_client import ReplyRejected, generate_post_reply
from post_context import POST_SUMMARY, READ_POST, has_context
from settings import daily_work_hours


POST_RENDER_TIMEOUT_MS = 30000
SEND_CONFIRMATION_TIMEOUT_MS = 30000
BEIJING = timezone(timedelta(hours=8))


class StopRequested(Exception):
    pass


class ContinuousRunner:
    def __init__(self, config, execute):
        self.config = config
        self.execute = execute
        self.work_hours = daily_work_hours(config) if execute and not config.get('_browser_check_only') else None
        self.root = Path(config.get('_root', Path(__file__).parent))
        self.account = config.get('my_username', '').strip().lstrip('@').casefold()
        if not re.fullmatch(r'[a-z0-9_]{1,15}', self.account):
            raise ValueError('持续运行需要在 .env 配置 TWITTER_MY_USERNAME，避免操作自己的推文或错误账号')
        if config.get('twitter_browser', {}).get('mode') != 'existing_chrome':
            raise ValueError('持续运行目前需要 twitter_browser.mode=existing_chrome')
        self.stop_file = self.root / 'browser_data' / 'STOP'
        self.history_cache = self.root / 'browser_data' / 'history-sync.json'
        self.status_path = self.root / 'logs' / 'status.json'
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        self.log = logging.getLogger('twitter_bot.continuous')
        self.log.setLevel(logging.INFO)
        self.log.propagate = False
        self.handlers = [logging.StreamHandler(), RotatingFileHandler(
            self.status_path.parent / 'continuous.log', maxBytes=2_000_000, backupCount=3, encoding='utf-8')]
        for handler in self.handlers:
            handler.setFormatter(logging.Formatter('%(asctime)s %(message)s', datefmt='%H:%M:%S'))
            self.log.addHandler(handler)
        self.store = None
        self.driver = None
        self.ai = None
        self.lock = None
        self.pages = []
        self.observed_history = 0
        self.completed = 0
        self.skipped = 0
        self.wait_until = 0.0
        self.current_url = None
        self.phase = 'starting'
        self.active_page = None
        self.follow_back = None
        self._following = False

    def status(self, state, **extra):
        document = dict(pid=os.getpid(), account=self.account, state=state,
                        completed=self.completed, skipped=self.skipped,
                        current_url=self.current_url, phase=self.phase,
                        updated_at=datetime.now().astimezone().isoformat(timespec='seconds'),
                        follow_back=self.follow_back.summary() if self.follow_back else {'enabled':False}, **extra)
        temporary = self.status_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.status_path)

    def check_stop(self):
        if self.stop_file.exists():
            raise StopRequested

    def in_work_hours(self, now=None):
        if self.work_hours is None:
            return True
        start, end = self.work_hours
        now = datetime.now(BEIJING) if now is None else now.astimezone(BEIJING)
        return start <= now.time() < end

    def wait_for_work_hours(self, page):
        self.check_stop()
        now = datetime.now(BEIJING)
        if self.in_work_hours(now):
            return False
        start, _ = self.work_hours
        next_start = datetime.combine(now.date(), start, tzinfo=BEIJING)
        if next_start <= now:
            next_start += timedelta(days=1)
        self.current_url = None
        self.status('off_hours', resumes_at=next_start.isoformat(timespec='seconds'))
        self.log.info('已进入时段外待机，预计北京时间 %s 恢复', next_start.strftime('%m-%d %H:%M'))
        while not self.in_work_hours():
            self.check_stop()
            if page.is_closed():
                raise RuntimeError('程序标签页已关闭，已停止互动')
            page.wait_for_timeout(1000)
        self.check_stop()
        self.log.info('已到运行时段，恢复运行')
        return True

    def pause(self, seconds, page, state='waiting'):
        self.status(state, wait_seconds=round(seconds, 1))
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.check_stop()
            if state != 'syncing_history' and not self.in_work_hours():
                return
            if page.is_closed():
                raise RuntimeError('程序标签页已关闭，已停止互动')
            if state in ('waiting','idle') and self.try_follow_back(page):
                self.status(state,wait_seconds=round(max(0,deadline-time.monotonic()),1))
            page.wait_for_timeout(min(1000, max(1, (deadline-time.monotonic())*1000)))

    def random_pause(self, key, default, page, state='waiting'):
        lower, upper = self.config.get(key, default)
        self.pause(random.uniform(lower, upper), page, state)

    def schedule_next_interaction(self):
        lower, upper = self.config.get('interaction_delay_seconds_range', [60, 150])
        self.wait_until = time.monotonic() + random.uniform(lower, upper)

    def check_page(self, page, account=False, action_alerts=True):
        self.check_stop()
        path = urlsplit(page.url).path
        if any(value in path for value in ('/i/flow/', '/account/access', '/account/locked', '/login')):
            raise RuntimeError('X 需要登录或验证，已暂停；请手动处理后重新启动')
        if page.locator('iframe[src*="arkoselabs"], iframe[src*="captcha"]').count():
            raise RuntimeError('X 出现验证，已暂停；请手动处理')
        alerts = ' '.join(page.locator('[role="alert"]').all_text_contents())
        if action_alerts and re.search(r'rate limit|temporarily restricted|automated|unusual activity|try again later|'
                     r'操作频繁|达到.{0,12}上限|暂时.{0,8}限制|验证.{0,6}身份|无法.{0,6}发送', alerts, re.I):
            raise RuntimeError('X 出现限制或异常提示，已暂停；未自动重试')
        if account:
            profile = page.locator('[data-testid="AppTabBar_Profile_Link"]').first
            profile.wait_for(state='visible', timeout=30000)
            handle = urlsplit(profile.get_attribute('href') or '').path.strip('/').casefold()
            if handle != self.account:
                raise RuntimeError('当前 X 登录账号与 TWITTER_MY_USERNAME 不一致，已停止')

    def observe_response(self, response):
        if not any(name in response.url for name in ('UserTweetsAndReplies', 'UserByScreenName', 'TweetDetail')):
            return
        if response.status == 429:
            self.network_limit = True
            return
        if response.status != 200:
            return
        try:
            data = response.json()
        except (PlaywrightError, ValueError):
            return
        if 'UserTweetsAndReplies' in response.url:
            self.observed_history += 1
        for parent, identity, text in own_replies(data, self.account):
            self.store.remember(parent, identity, text, status='imported')

    def guard(self, page, account=False, action_alerts=True):
        if self.network_limit:
            raise RuntimeError('X 返回限流状态，已暂停；未自动重试')
        self.check_page(page, account=account,action_alerts=action_alerts)

    def new_work_page(self, context):
        page = context.new_page()
        self.pages.append(page)
        page.on('response', self.observe_response)
        return page

    def try_follow_back(self, feed):
        if not self.follow_back or self._following or not self.in_work_hours():
            return False
        self._following=True
        previous_phase,previous_page=self.phase,self.active_page
        try:
            changed=self.follow_back.tick(feed.context)
            self.phase,self.active_page=previous_phase,previous_page
        finally:
            self._following=False
        if changed:
            self.status('running')
            return True
        return False

    def sync_history(self, page, resolver):
        self.phase = 'history_profile'
        self.active_page = page
        before = self.store.count()
        page.goto(f'https://x.com/{self.account}/with_replies', wait_until='domcontentloaded', timeout=60000)
        page.locator('[data-testid="AppTabBar_Profile_Link"]').first.wait_for(state='visible', timeout=30000)
        self.guard(page, account=True)
        page.locator('[data-testid="tweet"]').first.wait_for(state='visible', timeout=30000)
        self.pause(3, page, 'syncing_history')
        previous = -1
        idle = 0
        own_posts = {}
        for _ in range(self.config.get('history_sync_scrolls', 15)):
            self.guard(page)
            for item in page.locator('[data-testid="tweet"]').evaluate_all(POST_SUMMARY):
                author = urlsplit(item['url']).path.split('/')[1:2]
                identity = post_id(item['url'])
                if author and author[0].casefold() == self.account and identity:
                    own_posts[identity] = item
            count = len(own_posts)
            idle = idle + 1 if count == previous else 0
            if idle >= 3:
                break
            previous = count
            page.evaluate('window.scrollBy(0, 1000)')
            self.pause(2, page, 'syncing_history')
        if not own_posts and not self.observed_history:
            raise RuntimeError('未能读取 X 最近回复记录，已暂停；请确认个人资料页正常加载')
        # Cached/new X endpoints may not expose the expected response event. Resolve
        # unknown own posts from their actual conversation ancestors instead.
        unknown = [item for identity, item in own_posts.items() if not self.store.knows_reply(identity)]
        for item in unknown[:50]:
            self.phase = 'history_conversation'
            if resolver is None or resolver.is_closed():
                resolver = self.new_work_page(page.context)
            self.active_page = resolver
            self.guard(page)
            identity = post_id(item['url'])
            resolver.goto(item['url'], wait_until='domcontentloaded', timeout=60000)
            focus = resolver.locator('[data-testid="tweet"]').filter(
                has=resolver.locator(f'a[href$="/status/{identity}"]')).first
            focus.wait_for(state='visible', timeout=30000)
            self.guard(resolver, account=True)
            self.pause(1, resolver, 'syncing_history')
            chain = resolver.locator('[data-testid="tweet"]').evaluate_all(POST_SUMMARY)
            index = next((index for index, post in enumerate(chain) if post_id(post['url']) == identity), None)
            if index is not None and index > 0:
                parent = post_id(chain[index-1]['url'])
                if parent:
                    self.store.remember(parent, identity, item['text'], status='imported')
        self.log.info('历史同步：新增 %d 条，累计 %d 条；更早且网页未返回的记录不在本次同步范围内',
                      self.store.count()-before, self.store.count())
        self.history_cache.parent.mkdir(parents=True, exist_ok=True)
        self.history_cache.write_text(json.dumps({'account':self.account,'synced_at':time.time()}),encoding='utf-8')
        return resolver

    def history_is_fresh(self):
        try:
            cached = json.loads(self.history_cache.read_text(encoding='utf-8'))
            return (isinstance(cached,dict) and cached.get('account') == self.account and
                    0 <= time.time()-float(cached['synced_at']) < 600)
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def candidate_is_new(self, item):
        identity = post_id(item.get('url'))
        author = urlsplit(item.get('url') or '').path.split('/')[1:2]
        return bool(identity and has_context(item) and author and
                    author[0].casefold() != self.account and not self.store.contains(identity))

    def visible_own_reply(self, page, identity):
        for item in page.locator('[data-testid="tweet"]').evaluate_all(POST_SUMMARY):
            parts = urlsplit(item['url']).path.split('/')
            if len(parts) > 3 and parts[1].casefold() == self.account and post_id(item['url']) != identity:
                self.store.remember(identity, post_id(item['url']), item['text'], status='imported')
                return True
        return False

    def process(self, item, page):
        if not self.in_work_hours():
            return False
        self.phase = 'candidate'
        self.active_page = page
        url = item['url']
        identity = post_id(url)
        self.current_url = url
        try:
            response = page.goto(url, wait_until='domcontentloaded', timeout=60000)
            if response is not None and response.status == 429:
                raise RuntimeError('X 返回限流状态，已暂停；未自动重试')
            if response is not None and response.status in (404, 410):
                self.guard(page)
                self.skipped += 1
                self.log.info('跳过不可用推文（HTTP %s）：%s', response.status, url)
                return False
            target = page.locator('[data-testid="tweet"]').filter(
                has=page.locator(f'a[href$="/status/{identity}"]:has(time)')).first
            target.wait_for(state='visible', timeout=POST_RENDER_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            self.guard(page)
            self.skipped += 1
            self.log.info('跳过加载超时的推文：%s', url)
            return False
        self.guard(page, account=True)
        self.random_pause('reading_delay_seconds', [4, 10], page, 'reading')
        if not self.in_work_hours():
            return False
        if self.store.contains(identity) or self.visible_own_reply(page, identity):
            self.skipped += 1
            self.log.info('跳过已评论：%s', item['url'])
            return False
        reply_control = target.locator('[data-testid="reply"]').first
        if not reply_control.count() or not reply_control.is_enabled():
            self.log.info('跳过无法评论的推文：%s', item['url'])
            return False
        post = target.evaluate(READ_POST)
        if post_id(post['url']) != identity:
            self.skipped += 1
            self.log.info('跳过：无法确认页面主推文与目标一致 %s', item['url'])
            return False
        self.ai.recent_replies = self.store.recent_texts()
        try:
            reply = generate_post_reply(self.ai, post)
        except ReplyRejected as error:
            self.skipped += 1
            self.log.info('跳过不合适的回复：%s | %s', item['url'], error)
            return False
        if reply.casefold() in {value.casefold() for value in self.ai.recent_replies}:
            self.log.info('跳过重复措辞：%s', item['url'])
            return False
        self.log.info('%s %s | %s', '准备发布' if self.execute else '预览', item['url'], reply)
        if not self.execute:
            return True
        self.guard(page, account=True)
        if self.config.get('like_tweets', True):
            like = target.locator('[data-testid="like"]')
            if like.count():
                if not self.in_work_hours():
                    return False
                like.first.click(timeout=10000)
            target.locator('[data-testid="unlike"]').first.wait_for(state='visible', timeout=10000)
        if not self.in_work_hours():
            return False
        reply_control.click(timeout=10000)
        box = page.locator('[role="dialog"] [data-testid="tweetTextarea_0"]').last
        box.wait_for(state='visible', timeout=20000)
        box.fill(reply)
        self.guard(page, account=True)
        send = page.locator('[role="dialog"] [data-testid="tweetButton"], '
                            '[role="dialog"] [data-testid="tweetButtonInline"]').last
        if not self.in_work_hours():
            return False
        if not self.store.reserve_send(identity, reply):
            raise RuntimeError('该推文已有发送记录，已停止本次提交')
        self.status('sending')
        # Durable reservation happens before the only click. Ambiguous delivery is never retried.
        try:
            with page.expect_response(lambda response: '/CreateTweet' in response.url and
                                      response.request.method == 'POST', timeout=SEND_CONFIRMATION_TIMEOUT_MS) as sent:
                send.click(timeout=15000)
            response = sent.value
        except PlaywrightTimeoutError:
            self.store.mark_send_pending(identity)
            self.skipped += 1
            self.log.warning('评论发布确认超时，已标记待核实：%s', url)
            self.guard(page)
            self.schedule_next_interaction()
            self.status('running')
            return False
        if response.status != 200:
            raise RuntimeError(f'X 发送返回 HTTP {response.status}；已暂停，发送记录保留，不自动重发')
        records = own_replies(response.json(), self.account)
        created = next((record for record in records if record[0] == identity), None)
        if not created:
            raise RuntimeError('未能确认 X 发布结果，已暂停；该推文保留为待核实，不自动重发')
        self.store.remember(*created)
        box.wait_for(state='hidden', timeout=20000)
        self.log.info('已点赞并评论：%s | https://x.com/%s/status/%s', item['url'], self.account, created[1])
        return True

    def run(self):
        self.network_limit = False
        try:
            self.lock = RunnerLock(self.root / 'browser_data' / 'continuous.lock')
            self.check_stop()
            self.store = ActivityStore(self.root / 'browser_data' / 'activity.db', self.account)
            self.status('connecting')
            self.phase = 'connecting'
            from browser import create_browser
            from main import create_ai
            if not self.config.get('_browser_check_only'):
                self.ai = create_ai(self.config)
                if hasattr(self.ai, 'ready'):
                    self.ai.ready()
            self.driver = create_browser(self.config, 'twitter')
            feed = self.driver.page
            self.pages.append(feed)
            feed.on('response', self.observe_response)
            self.wait_for_work_hours(feed)
            detail = None
            if not self.config.get('_browser_check_only') and self.history_is_fresh():
                self.log.info('复用 10 分钟内的历史同步结果：%d 条；候选页仍逐条检查',self.store.count())
            else:
                detail = self.sync_history(feed, detail)
            if self.config.get('_browser_check_only'):
                self.status('ready', history_records=self.store.count())
                self.log.info('浏览器与历史只读检查通过，累计 %d 条记录；未生成或发布评论', self.store.count())
                return
            self.phase = 'feed'
            self.active_page = feed
            feed.goto('https://x.com/home', wait_until='domcontentloaded', timeout=60000)
            feed.locator('[data-testid="tweet"]').first.wait_for(state='visible', timeout=30000)
            self.guard(feed, account=True)
            if self.execute and self.config.get('follow_back',{}).get('enabled',False):
                from follow_back import FollowBackWorker
                self.follow_back=FollowBackWorker(self)
                self.log.info('自动回关已开启：仅认证关注者列表；冷却与回关记录跨重启保留')
            self.log.info('持续%s已启动；跳过 @%s 和已评论推文；创建 browser_data/STOP 可停止',
                          '正式运行' if self.execute else '预览', self.account)
            seen = set()
            idle = 0
            last_sync = time.monotonic()
            while True:
                if self.wait_for_work_hours(feed):
                    self.phase = 'feed'
                    self.active_page = feed
                    self.status('running')
                    feed.goto('https://x.com/home', wait_until='domcontentloaded', timeout=60000)
                    seen.clear()
                    idle = 0
                self.guard(feed, account=True)
                self.try_follow_back(feed)
                candidates = feed.locator('[data-testid="tweet"]').evaluate_all(POST_SUMMARY)
                found = False
                for item in candidates:
                    self.check_stop()
                    if not self.in_work_hours():
                        break
                    identity = post_id(item['url'])
                    if identity in seen:
                        continue
                    seen.add(identity)
                    if not self.candidate_is_new(item):
                        self.skipped += 1
                        continue
                    found = True
                    remaining = self.wait_until-time.monotonic()
                    if remaining > 0:
                        self.pause(remaining, feed)
                    self.try_follow_back(feed)
                    if not self.in_work_hours():
                        break
                    if detail is None or detail.is_closed():
                        detail = self.new_work_page(feed.context)
                    if self.process(item, detail):
                        self.completed += 1
                        self.schedule_next_interaction()
                        self.status('running')
                if not self.in_work_hours():
                    continue
                idle = 0 if found else idle+1
                feed.evaluate('(dy) => window.scrollBy(0,dy)', random.randint(400, 850))
                self.random_pause('scroll_delay_seconds', [3, 7], feed, 'browsing')
                if idle >= 5:
                    self.log.info('暂时没有新推文，休息后刷新首页')
                    self.random_pause('idle_delay_seconds', [90, 180], feed, 'idle')
                    if not self.in_work_hours():
                        continue
                    if time.monotonic()-last_sync > 1800:
                        history = self.new_work_page(feed.context)
                        detail = self.sync_history(history, detail)
                        history.close()
                        last_sync = time.monotonic()
                    feed.goto('https://x.com/home', wait_until='domcontentloaded', timeout=60000)
                    seen.clear()
                    idle = 0
        except (StopRequested, KeyboardInterrupt):
            self.status('stopped', reason='用户停止')
            self.log.info('已停止；本次完成 %d 条', self.completed)
        except Exception as error:
            if isinstance(error, RuntimeError):
                reason = str(error)
            elif isinstance(error, PlaywrightError):
                detail = str(error).splitlines()[0]
                reason = f'浏览器操作失败（{self.phase}）：{detail}；已暂停，不自动重发'
            else:
                reason = '页面或连接异常，已暂停；发送状态不确定的推文不会自动重发'
            if self.active_page:
                try:
                    self.active_page.screenshot(path=str(self.root/'logs'/'last-error.png'),timeout=5000)
                except PlaywrightError:
                    pass
            if self.lock:
                self.status('paused', reason=reason)
            self.log.error('%s；本次完成 %d 条', reason, self.completed)
            raise RuntimeError(reason) from None
        finally:
            for page in self.pages:
                page.remove_listener('response', self.observe_response)
                try:
                    if not page.is_closed():
                        page.close()
                except PlaywrightError:
                    pass
            if self.driver:
                self.driver.quit()
            if self.ai:
                self.ai.close()
            if self.store:
                self.store.close()
            if self.lock:
                self.lock.close()
            for handler in self.handlers:
                self.log.removeHandler(handler)
                handler.close()
