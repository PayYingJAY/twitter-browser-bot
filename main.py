"""Canonical browser workflow shared by website and API generation."""
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
from browser import create_browser
from ai_client import APIClient, ReplyRejected, generate_post_reply
from doubao_web import create_doubao_client
from post_context import READ_POST, has_context

def create_ai(config):
    return APIClient(config) if config.get('ai_mode') == 'api' else create_doubao_client(config)

def run(config, execute=False):
    if config.get('continuous', False):
        from continuous import ContinuousRunner
        return ContinuousRunner(config, execute).run()
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
                    post = driver.execute_script(f'return ({READ_POST})(arguments[0]);', tweet)
                    permalink = post['url']
                    if not permalink or permalink in seen:
                        continue
                    seen.add(permalink)
                    if not has_context(post):
                        continue
                    own = config.get('my_username', '').strip().lstrip('@').casefold()
                    if own and permalink.split('/')[3].casefold() == own:
                        continue
                    # Finish generation before any social action; failures stop the run.
                    try:
                        reply = generate_post_reply(ai, post)
                    except ReplyRejected as error:
                        print(f'跳过推文 {permalink}：{error}')
                        continue
                    print(f'\n推文：{post["text"] or permalink}\n回复：{reply}')
                    count += 1
                    found = True
                    if not execute:
                        print('预览：未点赞、未发布。')
                        continue
                    if config.get('like_tweets', True):
                        likes = tweet.find_elements(By.CSS_SELECTOR, '[data-testid="like"]')
                        if likes:
                            likes[0].click()
                            wait.until(lambda _: tweet.find_elements(By.CSS_SELECTOR, '[data-testid="unlike"]'))
                            print('已点赞。')
                        elif tweet.find_elements(By.CSS_SELECTOR, '[data-testid="unlike"]'):
                            print('此前已点赞。')
                        else:
                            raise RuntimeError('无法确认点赞状态，已停止；未发送本条评论')
                    tweet.find_element(By.CSS_SELECTOR, '[data-testid="reply"]').click()
                    # X renders the dialog shell before its editor and send button.
                    box = wait.until(EC.visibility_of_element_located((
                        By.CSS_SELECTOR, '[role="dialog"] [data-testid="tweetTextarea_0"]')))
                    box.send_keys(reply)
                    send = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,
                        '[role="dialog"] [data-testid="tweetButton"], '
                        '[role="dialog"] [data-testid="tweetButtonInline"]')))
                    send.click()
                    # Never repeat a send on timeout: delivery may have succeeded.
                    wait.until(EC.invisibility_of_element_located((
                        By.CSS_SELECTOR, '[role="dialog"] [data-testid="tweetTextarea_0"]')))
                    print('已发布回复：' + permalink)
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
