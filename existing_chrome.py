"""Connect to Chrome's user-approved CDP session without importing login data."""
import os
import sys
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, Error as PlaywrightError
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.by import By


def chrome_endpoint(options):
    endpoint = options.get('debugger_url')
    if not endpoint:
        directory = options.get('user_data_dir')
        if not directory:
            if sys.platform == 'win32':
                directory = Path(os.environ['LOCALAPPDATA']) / 'Google/Chrome/User Data'
            elif sys.platform == 'darwin':
                directory = Path.home() / 'Library/Application Support/Google/Chrome'
            else:
                directory = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'google-chrome'
        try:
            port, path = (Path(directory) / 'DevToolsActivePort').read_text().splitlines()[:2]
            if not 1 <= int(port) <= 65535 or not path.startswith('/devtools/browser/'):
                raise ValueError
            endpoint = f'ws://127.0.0.1:{int(port)}{path}'
        except (OSError, ValueError):
            raise RuntimeError('未找到现有 Chrome 的连接入口；请在已登录的 Chrome 打开 chrome://inspect/#remote-debugging，开启远程调试后重试') from None
    parsed = urlsplit(endpoint)
    if (parsed.scheme not in ('http', 'ws') or parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
            or parsed.username or parsed.password or parsed.fragment):
        raise ValueError('twitter_browser.debugger_url must be a local HTTP or WebSocket address')
    return endpoint


def webdriver_errors(method):
    @wraps(method)
    def wrapped(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except PlaywrightError:
            raise WebDriverException('Chrome 页面操作失败；请检查连接和页面状态') from None
    return wrapped


def find_elements(scope, by, selector):
    if by != By.CSS_SELECTOR:
        raise ValueError('Existing Chrome supports CSS selectors only')
    return [ChromeElement(handle) for handle in scope.query_selector_all(selector)]


class ChromeElement:
    """The element operations used by the shared X workflow."""
    def __init__(self, handle):
        self.handle = handle

    @property
    @webdriver_errors
    def text(self):
        return self.handle.inner_text()

    @webdriver_errors
    def get_attribute(self, name):
        if name == 'href':
            return self.handle.evaluate('node => node.href')
        return self.handle.get_attribute(name)

    @webdriver_errors
    def find_elements(self, by, selector):
        return find_elements(self.handle, by, selector)

    def find_element(self, by, selector):
        elements = self.find_elements(by, selector)
        if not elements:
            raise NoSuchElementException('未找到页面元素')
        return elements[0]

    @webdriver_errors
    def is_displayed(self):
        return self.handle.is_visible()

    @webdriver_errors
    def is_enabled(self):
        return self.handle.is_enabled()

    @webdriver_errors
    def click(self):
        self.handle.click(timeout=10000)

    @webdriver_errors
    def send_keys(self, text):
        self.handle.fill(text, timeout=10000)


class ExistingChrome:
    def __init__(self, config):
        endpoint = chrome_endpoint(config.get('twitter_browser', {}))
        self.runtime = None
        self.page = None
        try:
            print('正在连接已打开的 Chrome；如出现连接提示，请点击“允许”。', flush=True)
            self.runtime = sync_playwright().start()
            timeout = max(10, min(float(config.get('twitter_browser', {}).get('connect_timeout_seconds', 180)), 600))
            self.browser = self.runtime.chromium.connect_over_cdp(endpoint, timeout=timeout * 1000)
            if len(self.browser.contexts) != 1:
                raise RuntimeError('Chrome 未提供唯一的浏览器会话；请确认选择了已登录 X 的个人资料')
            # A dedicated tab shares the approved profile's login, leaving existing tabs intact.
            self.page = self.browser.contexts[0].new_page()
            self.page.set_default_timeout(10000)
        except PlaywrightError:
            self.quit()
            raise RuntimeError('连接现有 Chrome 失败；请确认远程调试已开启，并在 Chrome 的连接提示中点击“允许”') from None
        except Exception:
            self.quit()
            raise

    @webdriver_errors
    def get(self, url):
        self.page.goto(url, wait_until='domcontentloaded', timeout=60000)

    @webdriver_errors
    def find_elements(self, by, selector):
        return find_elements(self.page, by, selector)

    def find_element(self, by, selector):
        elements = self.find_elements(by, selector)
        if not elements:
            raise NoSuchElementException('未找到页面元素')
        return elements[0]

    @webdriver_errors
    def execute_script(self, script, *elements):
        if elements:
            return self.page.evaluate(f'args => (function() {{ {script} }}).apply(null, args)',
                                      [element.handle for element in elements])
        return self.page.evaluate(script)

    def quit(self):
        try:
            if self.page and not self.page.is_closed():
                self.page.close()
        except PlaywrightError:
            pass
        finally:
            self.page = None
            if self.runtime:
                # Stop the transport, never send Browser.close to the user's Chrome.
                self.runtime.stop()
                self.runtime = None
