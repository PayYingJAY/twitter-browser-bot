"""Modern Doubao website client with persistent login and locator auto-waits."""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from ai_client import AIError, SYSTEM, prompt_for, clean_reply

DEFAULT_SELECTORS = {
    'input': 'textarea, [contenteditable="true"]',
    'assistant': '[data-testid="receive_message"] [data-testid="message_text_content"]',
    'stop': '[data-testid="chat_input_local_break_button"]',
}

class DoubaoWebClient:
    def __init__(self, config):
        self.config = config
        self.options = config.get('doubao', {})
        self.selectors = dict(DEFAULT_SELECTORS, **self.options.get('selectors', {}))
        if self.selectors['assistant'] == '[data-testid="receive_message"]':
            self.selectors['assistant'] = DEFAULT_SELECTORS['assistant']
        self.runtime = None
        self.context = None
        root = Path(config.get('_root', Path(__file__).parent))
        profile = root / 'browser_data' / 'doubao'
        profile.mkdir(parents=True, exist_ok=True)
        try:
            self.runtime = sync_playwright().start()
            channel = self.options.get('browser_channel', 'chrome')
            if channel not in ('chrome', 'msedge', 'chromium'):
                raise ValueError('doubao.browser_channel must be chrome, msedge or chromium')
            self.context = self.runtime.chromium.launch_persistent_context(
                user_data_dir=str(profile.resolve()),
                channel=None if channel == 'chromium' else channel,
                headless=config.get('headless', False), viewport={'width':1280, 'height':900})
            self.context.set_default_timeout(30000)
            self.page = self.context.new_page()
            self.page.goto('https://www.doubao.com/', wait_until='domcontentloaded', timeout=60000)
        except PlaywrightError:
            self.close()
            raise AIError('无法启动豆包浏览器：请安装 Chrome，关闭占用本项目豆包 profile 的窗口；或安装 Chromium 并设置 browser_channel=chromium') from None
        except Exception:
            self.close()
            raise

    def _input(self):
        field = self.page.locator(f':is({self.selectors["input"]}):visible').last
        field.wait_for(state='visible')
        return field

    def ready(self):
        input('请在豆包窗口完成登录并打开空白对话，然后回到终端按 Enter（下次可复用登录）：')
        self._input()

    def _messages(self):
        return self.page.locator(self.selectors['assistant']).evaluate_all('''nodes => nodes
            .filter(x => x.getClientRects().length > 0)
            .map(x => ({text: x.innerText.trim(), streaming: x.getAttribute('data-streaming')}))''')

    def generate_reply(self, text):
        try:
            baseline = self._messages()
            if any(item['streaming'] == 'true' for item in baseline):
                raise AIError('豆包仍在生成上一条回答，请等待完成后重试')
            before = len(baseline)
            field = self._input()
            limit = int(self.config.get('reply_max_length', 100))
            # fill handles both textarea and contenteditable, including multiline text.
            field.fill(SYSTEM + '\n' + prompt_for(text, limit))
            field.press('Enter')
            deadline = time.monotonic() + float(self.options.get('timeout_seconds', 120))
            last, changed_at = None, time.monotonic()
            while time.monotonic() < deadline:
                if self.page.is_closed():
                    raise AIError('豆包窗口已关闭；生成未完成')
                messages = self._messages()
                if len(messages) > before and messages[-1]['text']:
                    answer = messages[-1]
                    candidate = answer['text']
                    if candidate != last:
                        last, changed_at = candidate, time.monotonic()
                    stopped = self.page.locator(f':is({self.selectors["stop"]}):visible').count() == 0
                    stable_seconds = 1 if answer['streaming'] == 'false' else 4
                    if answer['streaming'] != 'true' and stopped and time.monotonic() - changed_at >= stable_seconds:
                        return clean_reply(candidate, limit)
                self.page.wait_for_timeout(250)
            raise AIError('豆包回答超时：请检查登录、免费额度和网页选择器；未自动重发')
        except PlaywrightError:
            raise AIError('豆包页面操作失败：请检查窗口、登录状态或选择器；未自动重发') from None

    def close(self):
        try:
            if self.context:
                self.context.close()
        finally:
            self.context = None
            if self.runtime:
                self.runtime.stop()
                self.runtime = None


def create_doubao_client(config):
    backend = config.get('doubao', {}).get('backend', 'playwright')
    if backend == 'selenium':
        from doubao_selenium import DoubaoWebClient as LegacyClient
        return LegacyClient(config)
    if backend != 'playwright':
        raise ValueError('doubao.backend must be playwright or selenium')
    return DoubaoWebClient(config)
