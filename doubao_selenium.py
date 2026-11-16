"""Doubao website adapter. Only fresh assistant messages are accepted."""
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from browser import create_browser
from ai_client import AIError, SYSTEM, prompt_for, clean_reply

DEFAULT_SELECTORS = {
    'input': 'textarea, [contenteditable="true"]',
    'assistant': '[data-testid="receive_message"] [data-testid="message_text_content"]',
    'stop': '[data-testid="chat_input_local_break_button"]',
}

class DoubaoWebClient:
    def __init__(self, config):
        self.config = config
        self.driver = create_browser(config, 'doubao')
        self.selectors = dict(DEFAULT_SELECTORS, **config.get('doubao', {}).get('selectors', {}))
        # Upgrade the old broad selector in existing local configurations.
        if self.selectors['assistant'] == '[data-testid="receive_message"]':
            self.selectors['assistant'] = DEFAULT_SELECTORS['assistant']
        self.driver.get('https://www.doubao.com/')

    def ready(self):
        input('请在豆包窗口完成登录并打开空白对话，然后回到终端按 Enter：')
        self._input()

    def _input(self):
        def visible(driver):
            return next((x for x in driver.find_elements(By.CSS_SELECTOR, self.selectors['input'])
                         if x.is_displayed() and x.is_enabled()), False)
        return WebDriverWait(self.driver, 30).until(visible)

    def _messages(self):
        return [(x.id, x.text.strip()) for x in self.driver.find_elements(
            By.CSS_SELECTOR, self.selectors['assistant']) if x.is_displayed()]

    def _generating(self):
        # Current Doubao exposes streaming on the answer body itself.
        bodies = self.driver.find_elements(By.CSS_SELECTOR, self.selectors['assistant'])
        streaming = any(x.is_displayed() and x.get_attribute('data-streaming') == 'true'
                        for x in bodies)
        stopping = any(x.is_displayed() for x in self.driver.find_elements(
            By.CSS_SELECTOR, self.selectors['stop']))
        return streaming or stopping

    def generate_reply(self, text):
        before = dict(self._messages())
        field = self._input()
        field.click()
        field.send_keys(Keys.CONTROL, 'a')
        field.send_keys(Keys.BACKSPACE)
        limit = int(self.config.get('reply_max_length', 100))
        # Shift+Enter inserts line breaks without submitting partial prompts.
        lines = (SYSTEM + '\n' + prompt_for(text, limit)).splitlines()
        for index, line in enumerate(lines):
            if index:
                field.send_keys(Keys.SHIFT, Keys.ENTER)
            field.send_keys(line)
        field.send_keys(Keys.ENTER)
        deadline = time.monotonic() + float(self.config.get('doubao', {}).get('timeout_seconds', 120))
        last, changed_at = None, time.monotonic()
        while time.monotonic() < deadline:
            messages = self._messages()
            fresh = [(identity, body) for identity, body in messages if identity not in before and body]
            if fresh:
                candidate = fresh[-1][1]
                if candidate != last:
                    last, changed_at = candidate, time.monotonic()
                generating = self._generating()
                if not generating and time.monotonic() - changed_at >= 4:
                    return clean_reply(candidate, limit)
            time.sleep(0.5)
        raise AIError('豆包未返回新的完整回答；检查登录或 config.json 的 doubao.selectors')

    def close(self):
        self.driver.quit()
