"""Canonical browser workflow shared by website and API generation."""
import re
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
from browser import create_browser
from ai_client import APIClient, AIError
from doubao_web import create_doubao_client

def create_ai(config):
    return APIClient(config) if config.get('ai_mode') == 'api' else create_doubao_client(config)

def run(config, execute=False):
    ai = None
    driver = None
    try:
        ai = create_ai(config)
        if hasattr(ai, 'ready'):
            ai.ready()
        driver = create_browser(config, 'twitter')
        driver.get('https://x.com/home')
        input('请在 X 窗口确认已登录并进入首页，回到终端按 Enter：')
        wait = WebDriverWait(driver, 20)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="tweet"]')))
        seen = set()
        count = 0
        idle = 0
        limit = int(config.get('max_tweets', 10))
        while count < limit and idle < 10:
            found = False
            for tweet in driver.find_elements(By.CSS_SELECTOR, '[data-testid="tweet"]'):
                if count >= limit:
                    break
                try:
                    links = tweet.find_elements(By.CSS_SELECTOR, 'a[href*="/status/"]')
                    permalink = next((a.get_attribute('href') for a in links
                                      if re.search(r'/status/\d+$', a.get_attribute('href') or '')), None)
                    if not permalink or permalink in seen:
                        continue
                    seen.add(permalink)
                    parts = tweet.find_elements(By.CSS_SELECTOR, '[data-testid="tweetText"]')
                    text = parts[0].text.strip() if parts else ''
                    if not text:
                        continue
                    own = config.get('my_username', '').strip().lstrip('@').casefold()
                    if own and permalink.split('/')[3].casefold() == own:
                        continue
                    # Finish generation before any social action; failures stop the run.
                    reply = ai.generate_reply(text)
                    print(f'\n推文：{text}\n回复：{reply}')
                    count += 1
                    found = True
                    if not execute:
                        print('预览：未点赞、未发布。')
                        continue
                    if config.get('like_tweets', True):
                        likes = tweet.find_elements(By.CSS_SELECTOR, '[data-testid="like"]')
                        if likes:
                            likes[0].click()
                    tweet.find_element(By.CSS_SELECTOR, '[data-testid="reply"]').click()
                    dialog = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, '[role="dialog"]')))
                    box = dialog.find_element(By.CSS_SELECTOR, '[data-testid="tweetTextarea_0"]')
                    box.send_keys(reply)
                    send = dialog.find_element(By.CSS_SELECTOR, '[data-testid="tweetButton"], [data-testid="tweetButtonInline"]')
                    send.click()
                    # Never repeat a send on timeout: delivery may have succeeded.
                    wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, '[role="dialog"]')))
                    print('已发布回复。')
                    time.sleep(float(config.get('interaction_delay_seconds', 15)))
                except WebDriverException:
                    if execute:
                        raise RuntimeError('浏览器操作中断；为避免重复发送已停止，请检查 X 页面') from None
                    continue
            idle = 0 if found else idle + 1
            driver.execute_script('window.scrollBy(0, 800)')
            time.sleep(2)
        print(f'结束，共处理 {count} 条推文。')
    finally:
        if driver:
            driver.quit()
        if ai:
            ai.close()
