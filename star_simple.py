from settings import load_config
import time
import random
import json
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# 尝试导入AI模块
try:
    from ai_reply import create_ai_reply_generator
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from doubao_ai import create_doubao_ai_reply_generator
    DOUBAO_AVAILABLE = True
except ImportError:
    DOUBAO_AVAILABLE = False

class TwitterBot:
    def __init__(self, headless=False, config=None):
        """
        初始化推特机器人
        :param headless: 是否使用无头模式
        :param config: 配置信息
        """
        self.driver = None
        self.wait = None
        self.headless = headless
        self.config = config or {}
        self.setup_logging()
        self.setup_driver()
        
        # 初始化AI回复生成器
        self.ai_generator = self._create_ai_generator()
        
    def setup_logging(self):
        """设置日志"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('twitter_bot.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def setup_driver(self):
        """设置Chrome浏览器驱动"""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument("--headless")
            
        # 添加其他选项以模拟真实用户
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-blink-features")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--lang=zh-CN")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-popup-blocking")
        
        # 添加随机指纹
        chrome_options.add_argument(f"--window-size={random.randint(1050, 1920)},{random.randint(800, 1080)}")
        
        # 随机选择一个用户代理
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0"
        ]
        chrome_options.add_argument(f"--user-agent={random.choice(user_agents)}")
        
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        # 添加随机代理（如果有代理池的话）
        # if self.config.get("proxy"):
        #     chrome_options.add_argument(f'--proxy-server={self.config["proxy"]}')
        
        try:
            # 直接使用Chrome，让系统自动查找ChromeDriver
            self.driver = webdriver.Chrome(options=chrome_options)
            
            # 注入反检测 JavaScript
            self.driver.execute_script("""
                // 覆盖 webdriver 属性
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // 覆盖 chrome 属性
                window.chrome = {
                    runtime: {}
                };
                
                // 添加语言和插件
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh', 'en-US', 'en']
                });
                
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
            """)
            
            self.wait = WebDriverWait(self.driver, 10)
            self.logger.info("浏览器驱动初始化成功")
        except Exception as e:
            self.logger.error(f"浏览器驱动初始化失败: {e}")
            self.logger.error("请确保ChromeDriver已安装并添加到系统PATH中")
            self.logger.error("下载地址: https://chromedriver.chromium.org/")
            raise
    
    def _create_ai_generator(self):
        """创建AI回复生成器"""
        ai_type = self.config.get("ai_type", "doubao")  # 默认使用豆包
        
        if ai_type == "openai" and OPENAI_AVAILABLE:
            try:
                return create_ai_reply_generator(self.config)
            except Exception as e:
                self.logger.warning(f"OpenAI初始化失败: {e}")
        
        if ai_type == "doubao" and DOUBAO_AVAILABLE:
            try:
                return create_doubao_ai_reply_generator(self.config)
            except Exception as e:
                self.logger.warning(f"豆包AI初始化失败: {e}")
        
        # 如果都失败了，返回None，使用预设模板
        self.logger.warning("AI回复功能不可用，将使用预设模板")
        return None
            
    def random_delay(self, min_seconds=1, max_seconds=3):
        """随机延迟，模拟人类行为"""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
        
    def login_twitter(self, username, password, max_retries=3):
        """
        登录推特
        :param username: 用户名或邮箱
        :param password: 密码
        :param max_retries: 最大重试次数
        """
        retry_count = 0
        while retry_count < max_retries:
            try:
                self.logger.info(f"开始登录推特... (尝试 {retry_count + 1}/{max_retries})")
                
                # 清除所有cookies
                self.driver.delete_all_cookies()
                
                # 访问登录页面
                self.driver.get("https://twitter.com/i/flow/login")
                self.random_delay(3, 5)
                
                # 随机移动鼠标
                action = ActionChains(self.driver)
                action.move_by_offset(random.randint(-100, 100), random.randint(-100, 100)).perform()
                
                # 等待并输入用户名
                username_input = self.wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[autocomplete="username"]'))
                )
                
                # 模拟人类输入
                username_input.clear()
                for char in username:
                    username_input.send_keys(char)
                    time.sleep(random.uniform(0.1, 0.3))  # 随机输入延迟
                
                self.random_delay(2, 3)
                
                # 随机移动鼠标到下一步按钮
                next_button = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//span[text()='下一步']"))
                )
                action.move_to_element(next_button).perform()
                self.random_delay(0.5, 1)
                
                # 点击下一步
                next_button.click()
                self.random_delay(2, 4)
                
                # 等待并输入密码
                password_input = self.wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="password"]'))
                )
                
                # 模拟人类输入密码
                password_input.clear()
                for char in password:
                    password_input.send_keys(char)
                    time.sleep(random.uniform(0.1, 0.3))  # 随机输入延迟
                
                self.random_delay(1, 2)
                
                # 随机移动鼠标到登录按钮
                login_button = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//span[text()='登录']"))
                )
                action.move_to_element(login_button).perform()
                self.random_delay(0.5, 1)
                
                # 点击登录
                login_button.click()
                
                # 检查是否需要处理验证码或其他安全检查
                try:
                    # 等待可能出现的验证码
                    security_element = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="challenge_response"]'))
                    )
                    self.logger.warning("检测到安全验证，需要手动处理")
                    # 等待用户手动处理验证码
                    input("请在浏览器中完成验证，完成后按回车继续...")
                except:
                    pass
                
                # 等待登录完成
                try:
                    self.wait.until(EC.url_contains("twitter.com/home"))
                    self.logger.info("登录成功")
                    return True
                except TimeoutException:
                    # 检查是否有错误消息
                    try:
                        error_message = self.driver.find_element(By.CSS_SELECTOR, '[data-testid="error-message"]').text
                        self.logger.error(f"登录失败，错误信息: {error_message}")
                        if "Could not log you in" in error_message:
                            self.random_delay(30, 60)  # 遇到限制时等待较长时间
                    except:
                        pass
                
            except Exception as e:
                self.logger.error(f"登录过程出错: {e}")
            
            retry_count += 1
            if retry_count < max_retries:
                wait_time = random.randint(30, 60)  # 在重试之间等待30-60秒
                self.logger.info(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
        
        self.logger.error("登录失败，已达到最大重试次数")
        return False
            
    def safe_click(self, element, description=""):
        """安全点击元素，处理被遮挡的情况"""
        try:
            # 滚动到元素位置
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            self.random_delay(0.5, 1)
            
            # 等待元素可点击
            self.wait.until(EC.element_to_be_clickable(element))
            
            # 尝试JavaScript点击
            self.driver.execute_script("arguments[0].click();", element)
            self.logger.info(f"✅ {description} 成功")
            return True
            
        except Exception as e:
            self.logger.warning(f"❌ {description} 失败: {e}")
            return False
    
    def extract_tweet_content(self, tweet_element):
        """提取推文内容"""
        try:
            # 查找推文文本内容
            text_elements = tweet_element.find_elements(
                By.CSS_SELECTOR, 
                '[data-testid="tweetText"]'
            )
            
            if text_elements:
                content = text_elements[0].text
                self.logger.info(f"提取到推文内容: {content[:50]}...")
                return content
            
            # 如果没有找到文本内容，尝试其他选择器
            text_elements = tweet_element.find_elements(
                By.CSS_SELECTOR, 
                'div[lang]'
            )
            
            if text_elements:
                content = text_elements[0].text
                self.logger.info(f"提取到推文内容: {content[:50]}...")
                return content
            
            self.logger.warning("未找到推文内容")
            return ""
            
        except Exception as e:
            self.logger.error(f"提取推文内容失败: {e}")
            return ""
    
    def generate_ai_reply(self, tweet_content, language="中文", max_length=100):
        """生成AI回复"""
        if self.ai_generator:
            try:
                reply = self.ai_generator.generate_reply(
                    tweet_content, 
                    language=language,
                    max_length=max_length
                )
                self.logger.info(f"AI生成回复: {reply}")
                return reply
            except Exception as e:
                self.logger.error(f"AI生成回复失败: {e}")
        
        # 如果AI不可用，使用预设模板
        return self._get_fallback_reply(language)
    
    def _get_fallback_reply(self, language):
        """获取备用回复"""
        if language == "中文":
            replies = [
                "很有趣的内容！👍",
                "支持一下，继续加油！",
                "不错的内容，学习了",
                "很有见地，感谢分享",
                "这个观点很有意思",
                "完全同意你的看法",
                "谢谢分享，很有帮助",
                "内容很棒，期待更多",
                "很有启发性",
                "支持原创内容"
            ]
        else:
            replies = [
                "Interesting content! 👍",
                "Keep up the good work!",
                "Great content, learned a lot",
                "Insightful, thanks for sharing",
                "This is an interesting perspective"
            ]
        
        return random.choice(replies)
            
    def process_tweet(self, tweet_element, comments_list=None, use_ai=True):
        """处理单条推文：点赞 + 评论"""
        try:
            # 提取推文内容
            tweet_content = self.extract_tweet_content(tweet_element)
            
            # 查找点赞按钮
            like_button = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="like"]')
            
            # 检查是否已经点赞
            if "liked" not in like_button.get_attribute("class"):
                # 点赞
                if self.safe_click(like_button, "点赞"):
                    self.random_delay(1, 2)
                    
                    # 查找回复按钮
                    reply_button = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="reply"]')
                    
                    # 生成评论内容
                    if use_ai and tweet_content:
                        # 使用AI生成回复
                        comment = self.generate_ai_reply(tweet_content, "中文", 100)
                    else:
                        # 使用预设评论
                        if comments_list:
                            comment = random.choice(comments_list)
                        else:
                            comment = "很有趣的内容！👍"
                    
                    # 评论
                    if self.safe_click(reply_button, "点击回复"):
                        self.random_delay(1, 2)
                        
                        # 查找评论输入框
                        comment_input = self.wait.until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="tweetTextarea_0"]'))
                        )
                        
                        comment_input.clear()
                        
                        # 逐字符输入评论
                        for char in comment:
                            comment_input.send_keys(char)
                            time.sleep(0.05)
                        self.random_delay(1, 2)
                        
                        # 点击发送按钮
                        send_button = self.driver.find_element(
                            By.CSS_SELECTOR, 
                            '[data-testid="tweetButton"]'
                        )
                        if self.safe_click(send_button, "发送评论"):
                            self.logger.info(f"✅ 推文处理完成: 点赞 + 评论 '{comment}'")
                            self.random_delay(2, 4)
                            return True
                        else:
                            # 如果发送失败，尝试关闭评论框
                            try:
                                cancel_button = self.driver.find_element(
                                    By.CSS_SELECTOR, 
                                    '[data-testid="closeButton"]'
                                )
                                cancel_button.click()
                            except:
                                pass
            else:
                self.logger.info("该推文已经点赞过，跳过")
                
        except Exception as e:
            self.logger.warning(f"处理推文失败: {e}")
            
        return False
            
    def browse_and_interact(self, max_tweets=10, comments_list=None, use_ai=True):
        """
        浏览推特并互动：对每条推文先点赞再评论
        :param max_tweets: 最大处理推文数量
        :param comments_list: 评论列表（备用）
        :param use_ai: 是否使用AI生成回复
        """
        if comments_list is None:
            comments = [
                " 很有趣的内容！👍",
                " 支持一下，继续加油！",
                " 不错的内容，学习了",
                " 很有见地，感谢分享",
                " 这个观点很有意思",
                " 完全同意你的看法",
                " 谢谢分享，很有帮助",
                " 内容很棒，期待更多",
                " 很有启发性",
                " 支持原创内容"
            ]
            tags = [
                "",
                "",
                "",
                "",
                "",
                ""
            ]
            
            comments_list = [comment + " " + tag for comment in comments for tag in tags]
            
        try:
            self.logger.info(f"开始浏览推特并互动，目标数量: {max_tweets}")
            self.logger.info(f"使用AI生成回复: {use_ai}")
            self.driver.get("https://twitter.com/home")
            self.random_delay(2, 4)
            
            processed_count = 0
            scroll_count = 0
            
            while processed_count < max_tweets and scroll_count < 30:
                # 查找所有推文
                tweet_elements = self.driver.find_elements(
                    By.CSS_SELECTOR, 
                    '[data-testid="tweet"]'
                )
                
                for tweet_element in tweet_elements:
                    if processed_count >= max_tweets:
                        break
                        
                    try:
                        # 处理单条推文
                        if self.process_tweet(tweet_element, comments_list, use_ai):
                            processed_count += 1
                            self.logger.info(f"已处理 {processed_count}/{max_tweets} 条推文")
                            
                        # 处理完一条推文后，滚动到下一位置
                        self.driver.execute_script("window.scrollBy(0, 300);")
                        self.random_delay(1, 2)
                        
                    except Exception as e:
                        self.logger.warning(f"处理推文时出错: {e}")
                        continue
                
                # 滚动页面加载更多推文
                self.driver.execute_script("window.scrollBy(0, 1000);")
                self.random_delay(2, 3)
                scroll_count += 1
                
            self.logger.info(f"浏览互动完成，共处理 {processed_count} 条推文")
            
        except Exception as e:
            self.logger.error(f"浏览互动过程中出错: {e}")
            
    def check_notifications(self):
        """检查通知页面"""
        try:
            self.logger.info("检查通知页面...")
            self.driver.get("https://twitter.com/notifications")
            self.random_delay(2, 4)
            
            # 查找评论通知
            comment_notifications = self.driver.find_elements(
                By.CSS_SELECTOR, 
                '[data-testid="notification"]'
            )
            
            self.logger.info(f"找到 {len(comment_notifications)} 条通知")
            return len(comment_notifications)
            
        except Exception as e:
            self.logger.error(f"检查通知失败: {e}")
            return 0
            
    def reply_to_comments(self, reply_templates=None, max_replies=5, use_ai=True):
        """
        回复评论
        :param reply_templates: 回复模板列表（备用）
        :param max_replies: 最大回复数量
        :param use_ai: 是否使用AI生成回复
        """
        try:
            self.logger.info(f"开始回复评论，目标数量: {max_replies}")
            self.logger.info(f"使用AI生成回复: {use_ai}")
            self.driver.get("https://twitter.com/notifications")
            self.random_delay(2, 4)
            
            replies_count = 0
            
            # 查找评论通知
            notifications = self.driver.find_elements(
                By.CSS_SELECTOR, 
                '[data-testid="notification"]'
            )
            
            for notification in notifications:
                if replies_count >= max_replies:
                    break
                    
                try:
                    # 检查是否是评论通知
                    notification_text = notification.text.lower()
                    if "回复" in notification_text or "comment" in notification_text:
                        # 点击通知查看详情
                        notification.click()
                        self.random_delay(2, 3)
                        
                        # 提取推文内容
                        tweet_content = self.extract_tweet_content(self.driver)
                        
                        # 生成回复内容
                        if use_ai and tweet_content:
                            # 使用AI生成回复
                            reply = self.generate_ai_reply(tweet_content, "中文", 100)
                        else:
                            # 使用预设回复
                            if reply_templates:
                                reply = random.choice(reply_templates)
                            else:
                                reply = "谢谢你的评论！🙏"
                        
                        # 查找回复按钮
                        reply_button = self.driver.find_element(
                            By.CSS_SELECTOR, 
                            '[data-testid="reply"]'
                        )
                        reply_button.click()
                        self.random_delay(1, 2)
                        
                        # 查找回复输入框
                        reply_input = self.wait.until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="tweetTextarea_0"]'))
                        )
                        
                        reply_input.clear()
                        
                        # 逐字符输入回复
                        for char in reply:
                            reply_input.send_keys(char)
                            time.sleep(0.05)
                        self.random_delay(1, 2)
                        
                        # 点击发送按钮
                        send_button = self.driver.find_element(
                            By.CSS_SELECTOR, 
                            '[data-testid="tweetButton"]'
                        )
                        send_button.click()
                        
                        replies_count += 1
                        self.logger.info(f"已回复 {replies_count} 条评论: {reply}")
                        self.random_delay(2, 4)
                        
                        # 返回通知页面
                        self.driver.get("https://twitter.com/notifications")
                        self.random_delay(2, 3)
                        
                except Exception as e:
                    self.logger.warning(f"回复失败: {e}")
                    continue
                    
            self.logger.info(f"回复完成，共回复 {replies_count} 条评论")
            
        except Exception as e:
            self.logger.error(f"回复过程中出错: {e}")
            
    def auto_browse(self, duration_minutes=30):
        """
        自动浏览推特
        :param duration_minutes: 浏览时长（分钟）
        """
        try:
            self.logger.info(f"开始自动浏览，时长: {duration_minutes} 分钟")
            start_time = time.time()
            end_time = start_time + (duration_minutes * 60)
            
            while time.time() < end_time:
                # 随机选择操作
                action = random.choice(['scroll', 'interact', 'check_notifications'])
                
                if action == 'scroll':
                    self.driver.execute_script("window.scrollBy(0, 500);")
                    self.logger.info("滚动页面")
                    
                elif action == 'interact':
                    self.browse_and_interact(max_tweets=2, use_ai=True)  # 每次只处理2条推文
                    
                elif action == 'check_notifications':
                    self.check_notifications()
                    
                self.random_delay(30, 60)  # 随机等待30-60秒
                
            self.logger.info("自动浏览完成")
            
        except Exception as e:
            self.logger.error(f"自动浏览过程中出错: {e}")
            
    def save_cookies(self, filename="twitter_cookies.json"):
        """保存cookies"""
        try:
            cookies = self.driver.get_cookies()
            with open(filename, 'w') as f:
                json.dump(cookies, f)
            self.logger.info(f"Cookies已保存到 {filename}")
        except Exception as e:
            self.logger.error(f"保存cookies失败: {e}")
            
    def load_cookies(self, filename="twitter_cookies.json"):
        """加载cookies"""
        try:
            with open(filename, 'r') as f:
                cookies = json.load(f)
            
            self.driver.get("https://twitter.com")
            for cookie in cookies:
                self.driver.add_cookie(cookie)
            self.logger.info("Cookies加载成功")
            return True
        except Exception as e:
            self.logger.error(f"加载cookies失败: {e}")
            return False
            
    def close(self):
        """关闭浏览器"""
        if self.driver:
            self.driver.quit()
            self.logger.info("浏览器已关闭")
        
        # 关闭AI生成器
        if self.ai_generator and hasattr(self.ai_generator, 'close'):
            try:
                self.ai_generator.close()
            except:
                pass

def main():
    """主函数示例"""
    # 配置信息
    config = {
        "username": "your_username",  # 替换为您的用户名
        "password": "your_password",  # 替换为您的密码
        "headless": False,  # 是否使用无头模式
        "max_tweets": 10,   # 最大处理推文数量
        "max_replies": 3,   # 最大回复数量
        "browse_duration": 30,  # 浏览时长（分钟）
        "ai_type": "doubao",  # AI类型：doubao 或 openai
        "use_ai_reply": True  # 是否使用AI回复
    }
    
    config.update(load_config())

    # 评论和回复模板（备用）
    comments = [
        "很有趣的内容！👍",
        "支持一下，继续加油！",
        "不错的内容，学习了",
        "很有见地，感谢分享",
        "这个观点很有意思",
        "完全同意你的看法",
        "谢谢分享，很有帮助",
        "内容很棒，期待更多",
        "很有启发性",
        "支持原创内容"
    ]
    
    reply_templates = [
        "谢谢你的评论！🙏",
        "感谢支持！",
        "很高兴收到你的回复",
        "谢谢关注！",
        "你的评论很有价值"
    ]
    
    bot = None
    try:
        # 创建机器人实例
        bot = TwitterBot(headless=config["headless"], config=config)
        
        # 尝试加载cookies（如果存在）
        if not bot.load_cookies():
            # 如果cookies不存在，进行登录
            if not bot.login_twitter(config["username"], config["password"]):
                print("登录失败，请检查用户名和密码")
                return
        
        # 保存cookies
        bot.save_cookies()
        
        # 执行自动化操作
        print("开始执行自动化操作...")
        
        # 浏览推特并互动（点赞+AI评论）
        bot.browse_and_interact(max_tweets=config["max_tweets"], use_ai=config["use_ai_reply"])
        
        # 检查并AI回复评论
        bot.reply_to_comments(reply_templates, max_replies=config["max_replies"], use_ai=config["use_ai_reply"])
        
        # 自动浏览
        bot.auto_browse(duration_minutes=config["browse_duration"])
        
        print("所有操作完成！")
        
    except KeyboardInterrupt:
        print("\n用户中断操作")
    except Exception as e:
        print(f"程序出错: {e}")
    finally:
        if bot:
            bot.close()

if __name__ == "__main__":
    main() 