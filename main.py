#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推特自动化机器人 - 简化版
功能：打开x.com和豆包，等待登录，自动点赞和AI回复
"""

import json
import time
import random
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import os
from settings import load_config

class TwitterBot:
    def __init__(self, config):
        """初始化推特机器人"""
        self.config = config
        self.twitter_driver = None
        self.doubao_driver = None
        self.twitter_wait = None
        self.doubao_wait = None
        self.setup_logging()
        self.setup_drivers()
        
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
        
    def setup_drivers(self):
        """设置浏览器驱动"""
        def create_chrome_options():
            chrome_options = Options()
            if self.config.get("headless", False):
                chrome_options.add_argument("--headless")
            
            # 基本设置
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--disable-blink-features")
            chrome_options.add_argument("--disable-infobars")
            chrome_options.add_argument("--start-maximized")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--lang=zh-CN")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-popup-blocking")
            
            # 随机窗口大小
            window_width = random.randint(1050, 1920)
            window_height = random.randint(800, 1080)
            chrome_options.add_argument(f"--window-size={window_width},{window_height}")
            
            # 随机用户代理
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0"
            ]
            chrome_options.add_argument(f"--user-agent={random.choice(user_agents)}")
            
            # 实验性选项
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
            
            return chrome_options
            
        def inject_stealth_js(driver):
            """注入反检测 JavaScript"""
            driver.execute_script("""
                // 覆盖 webdriver 属性
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // 覆盖 chrome 属性
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };
                
                // 添加语言和插件
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh', 'en-US', 'en']
                });
                
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        {
                            0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format"},
                            description: "Portable Document Format",
                            filename: "internal-pdf-viewer",
                            length: 1,
                            name: "Chrome PDF Plugin"
                        },
                        {
                            0: {type: "application/pdf", suffixes: "pdf", description: "Portable Document Format"},
                            description: "Portable Document Format",
                            filename: "internal-pdf-viewer",
                            length: 1,
                            name: "Chrome PDF Viewer"
                        }
                    ]
                });
                
                // 添加 WebGL
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) {
                        return 'Intel Inc.'
                    }
                    if (parameter === 37446) {
                        return 'Intel(R) Iris(TM) Graphics 6100'
                    }
                    return getParameter.apply(this, [parameter]);
                };
            """)
            
        try:
            # 创建推特浏览器
            twitter_options = create_chrome_options()
            self.twitter_driver = webdriver.Chrome(options=twitter_options)
            inject_stealth_js(self.twitter_driver)
            self.twitter_wait = WebDriverWait(self.twitter_driver, 10)
            
            # 创建豆包浏览器
            doubao_options = create_chrome_options()
            self.doubao_driver = webdriver.Chrome(options=doubao_options)
            inject_stealth_js(self.doubao_driver)
            self.doubao_wait = WebDriverWait(self.doubao_driver, 10)
            
            self.logger.info("浏览器驱动初始化成功")
        except Exception as e:
            self.logger.error(f"浏览器驱动初始化失败: {e}")
            raise
            
    def save_twitter_cookies(self):
        """保存推特cookies"""
        try:
            cookies = self.twitter_driver.get_cookies()
            with open("twitter_cookies.json", 'w', encoding='utf-8') as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            self.logger.info("推特cookies已保存")
            return True
        except Exception as e:
            self.logger.error(f"保存推特cookies失败: {e}")
            return False
            
    def format_browser_cookies(self, cookies_data):
        """格式化从浏览器导出的cookies"""
        formatted_cookies = []
        required_fields = ['name', 'value', 'domain', 'path']
        
        for cookie in cookies_data:
            # 确保基本字段存在
            if not all(field in cookie for field in required_fields):
                continue
                
            # 标准化cookie格式
            formatted_cookie = {
                'name': cookie['name'],
                'value': cookie['value'],
                'domain': cookie['domain'].replace('twitter.com', 'x.com'),  # 兼容新域名
                'path': cookie['path']
            }
            
            # 添加可选字段
            if 'expiry' in cookie:
                formatted_cookie['expiry'] = int(cookie['expiry'])
            if 'httpOnly' in cookie:
                formatted_cookie['httpOnly'] = cookie['httpOnly']
            if 'secure' in cookie:
                formatted_cookie['secure'] = cookie['secure']
            
            formatted_cookies.append(formatted_cookie)
            
        return formatted_cookies
        
    def validate_cookies(self, cookies):
        """验证cookies的有效性"""
        essential_cookies = ['auth_token', 'ct0', 'twid']  # Twitter必要的cookies
        found_cookies = set()
        
        for cookie in cookies:
            if cookie['name'] in essential_cookies:
                found_cookies.add(cookie['name'])
                
        missing_cookies = set(essential_cookies) - found_cookies
        if missing_cookies:
            self.logger.warning(f"缺少重要的cookies: {missing_cookies}")
            return False
            
        return True
        
    def load_twitter_cookies(self, external_cookies_file=None):
        """加载推特cookies，支持从外部浏览器导入"""
        try:
            cookies = None
            
            # 尝试加载外部cookies
            if external_cookies_file and os.path.exists(external_cookies_file):
                self.logger.info(f"尝试加载外部cookies: {external_cookies_file}")
                try:
                    with open(external_cookies_file, 'r', encoding='utf-8') as f:
                        cookies = json.load(f)
                    cookies = self.format_browser_cookies(cookies)
                except Exception as e:
                    self.logger.error(f"加载外部cookies失败: {e}")
                    
            # 如果没有外部cookies，使用默认文件
            if not cookies and os.path.exists("twitter_cookies.json"):
                self.logger.info("加载默认cookies文件")
                with open("twitter_cookies.json", 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                    
            if not cookies:
                self.logger.info("没有可用的cookies")
                return False
                
            # 验证cookies的有效性
            if not self.validate_cookies(cookies):
                self.logger.warning("cookies验证失败")
                return False
                
            # 检查cookies是否过期
            current_time = time.time()
            valid_cookies = []
            for cookie in cookies:
                if 'expiry' in cookie:
                    if cookie['expiry'] > current_time:
                        valid_cookies.append(cookie)
                    else:
                        self.logger.warning(f"Cookie {cookie.get('name')} 已过期")
                else:
                    valid_cookies.append(cookie)
            
            if not valid_cookies:
                self.logger.warning("所有cookies已过期")
                return False
            
            # 先访问推特网站
            self.twitter_driver.get("https://x.com")
            self.random_delay(3, 5)
            
            # 清除所有现有cookies
            self.twitter_driver.delete_all_cookies()
            self.random_delay(1, 2)
            
            # 添加cookies
            success_count = 0
            for cookie in valid_cookies:
                try:
                    # 移除可能导致问题的字段
                    if 'sameSite' in cookie:
                        del cookie['sameSite']
                    if 'expiry' in cookie:
                        cookie['expiry'] = int(cookie['expiry'])
                    
                    self.twitter_driver.add_cookie(cookie)
                    success_count += 1
                    self.random_delay(0.1, 0.3)
                except Exception as e:
                    self.logger.warning(f"添加cookie {cookie.get('name')} 失败: {e}")
                    continue
            
            if success_count > 0:
                self.logger.info(f"成功加载 {success_count} 个cookies")
                # 保存成功的cookies到默认文件
                if external_cookies_file:
                    self.save_twitter_cookies()
                # 刷新页面使cookies生效
                self.random_delay(1, 2)
                self.twitter_driver.refresh()
                self.random_delay(2, 3)
                return True
            else:
                self.logger.warning("没有成功加载任何cookies")
                return False
            
        except Exception as e:
            self.logger.error(f"加载推特cookies失败: {e}")
            return False
            
    def check_twitter_login(self):
        """检查推特登录状态"""
        try:
            # 访问主页
            self.twitter_driver.get("https://x.com/home")
            self.random_delay(3, 5)
            
            # 模拟人类浏览行为
            self.human_like_mouse_move(self.twitter_driver)
            self.random_delay(1, 2)
            
            # 随机滚动页面
            self.human_like_scroll(self.twitter_driver, direction="down", speed="normal")
            self.random_delay(2, 3)
            
            # 检查是否已登录（查找推文元素）
            try:
                tweet_elements = self.twitter_driver.find_elements(By.CSS_SELECTOR, '[data-testid="tweet"]')
                if tweet_elements:
                    # 模拟阅读一下推文
                    self.simulate_human_reading(self.twitter_driver, random.choice(tweet_elements))
                    self.logger.info("推特已登录")
                    return True
            except:
                pass
            
            # 检查是否有登录按钮
            try:
                login_elements = self.twitter_driver.find_elements(By.CSS_SELECTOR, 'a[href*="login"]')
                if login_elements:
                    self.logger.info("推特未登录")
                    return False
            except:
                pass
            
            # 随机执行一些其他操作
            if random.random() < 0.3:  # 30%的概率
                self.human_like_scroll(self.twitter_driver, direction="up", speed="slow")
            
            self.logger.info("无法确定推特登录状态")
            return False
            
        except Exception as e:
            self.logger.error(f"检查推特登录状态失败: {e}")
            return False
            
    def random_delay(self, min_seconds=1, max_seconds=3):
        """随机延迟，使用正态分布模拟更真实的人类行为"""
        # 使用正态分布生成延迟时间，均值为中间值，标准差为范围的1/4
        mean = (min_seconds + max_seconds) / 2
        std_dev = (max_seconds - min_seconds) / 4
        delay = random.gauss(mean, std_dev)
        # 确保延迟时间在指定范围内
        delay = max(min_seconds, min(max_seconds, delay))
        time.sleep(delay)
        
    def human_like_mouse_move(self, driver, element=None):
        """模拟人类鼠标移动"""
        try:
            action = ActionChains(driver)
            
            # 如果没有指定元素，随机移动
            if element is None:
                # 随机移动2-4次
                for _ in range(random.randint(2, 4)):
                    x = random.randint(100, 700)
                    y = random.randint(100, 500)
                    # 使用二次贝塞尔曲线模拟平滑移动
                    action.move_by_offset(x/2, y/2).pause(0.1)
                    action.move_by_offset(x/2, y/2).pause(0.1)
                    action.perform()
                    self.random_delay(0.1, 0.3)
            else:
                # 移动到元素前先随机移动一下
                action.move_by_offset(
                    random.randint(-100, 100),
                    random.randint(-100, 100)
                ).pause(0.1).perform()
                self.random_delay(0.1, 0.3)
                
                # 然后移动到元素
                action.move_to_element(element)
                action.pause(random.uniform(0.1, 0.3))
                action.perform()
                
            return True
        except Exception as e:
            self.logger.warning(f"鼠标移动失败: {e}")
            return False
            
    def human_like_scroll(self, driver, direction="down", speed="normal"):
        """模拟人类滚动行为"""
        try:
            if direction == "down":
                scroll_range = random.randint(300, 700)  # 随机滚动距离
                # 分多次滚动，模拟平滑效果
                steps = random.randint(4, 8)
                for i in range(steps):
                    step = scroll_range // steps
                    driver.execute_script(f"window.scrollBy(0, {step});")
                    if speed == "normal":
                        self.random_delay(0.1, 0.3)
                    else:  # slow
                        self.random_delay(0.3, 0.5)
            else:  # up
                scroll_range = random.randint(-700, -300)
                steps = random.randint(4, 8)
                for i in range(steps):
                    step = scroll_range // steps
                    driver.execute_script(f"window.scrollBy(0, {step});")
                    if speed == "normal":
                        self.random_delay(0.1, 0.3)
                    else:  # slow
                        self.random_delay(0.3, 0.5)
            
            return True
        except Exception as e:
            self.logger.warning(f"页面滚动失败: {e}")
            return False
            
    def simulate_human_reading(self, driver, element=None):
        """模拟人类阅读行为"""
        try:
            # 如果提供了具体元素，先滚动到元素位置
            if element:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                self.random_delay(0.5, 1)
            
            # 随机上下滚动，模拟阅读
            scroll_times = random.randint(2, 4)
            for _ in range(scroll_times):
                # 随机选择滚动方向和速度
                direction = random.choice(["up", "down"])
                speed = random.choice(["normal", "slow"])
                self.human_like_scroll(driver, direction, speed)
                self.random_delay(1, 2)
            
            return True
        except Exception as e:
            self.logger.warning(f"模拟阅读失败: {e}")
            return False
            
    def human_like_type(self, element, text):
        """模拟人类输入行为"""
        try:
            # 先点击输入框
            element.click()
            self.random_delay(0.2, 0.5)
            
            # 清除现有内容
            element.clear()
            self.random_delay(0.1, 0.3)
            
            # 模拟人类输入速度和错误
            for char in text:
                # 随机输入错误并修正（5%的概率）
                if random.random() < 0.05:
                    # 输入一个错误字符
                    wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
                    element.send_keys(wrong_char)
                    self.random_delay(0.1, 0.3)
                    # 删除错误字符
                    element.send_keys(Keys.BACKSPACE)
                    self.random_delay(0.1, 0.3)
                
                # 输入正确字符
                element.send_keys(char)
                # 使用正态分布的延迟时间
                delay = random.gauss(0.1, 0.02)
                delay = max(0.05, min(0.2, delay))  # 限制在50ms到200ms之间
                time.sleep(delay)
            
            # 输入完成后的短暂停顿
            self.random_delay(0.3, 0.7)
            return True
        except Exception as e:
            self.logger.warning(f"模拟输入失败: {e}")
            return False
        
    def open_websites(self, external_cookies_file=None):
        """打开x.com和豆包"""
        try:
            # 尝试加载推特cookies
            if self.load_twitter_cookies(external_cookies_file):
                # 检查推特登录状态
                if self.check_twitter_login():
                    self.logger.info("推特已登录，无需重新登录")
                else:
                    self.logger.info("推特cookies已过期，需要重新登录")
            else:
                self.logger.info("未找到有效的推特cookies，需要登录")
            
            # 打开豆包
            self.logger.info("正在打开豆包...")
            self.doubao_driver.get("https://www.doubao.com/")
            self.random_delay(2, 3)
            
            self.logger.info("网站打开完成")
            return True
            
        except Exception as e:
            self.logger.error(f"打开网站失败: {e}")
            return False
            
    def wait_for_login(self):
        """等待用户登录"""
        print("\n" + "="*50)
        print("🤖 请完成以下步骤：")
        
        # 检查推特登录状态
        twitter_logged_in = self.check_twitter_login()
        if not twitter_logged_in:
            print("1. 在x.com浏览器中登录您的推特账号")
        else:
            print("1. ✅ 推特已登录")
        
        print("2. 在豆包浏览器中登录您的豆包账号")
        print("3. 程序将等待1分钟让您完成登录")
        print("="*50)
        
        # 等待1分钟
        print("⏰ 等待1分钟让您完成登录...")
        time.sleep(60)
        
        # 保存推特cookies
        if not twitter_logged_in:
            if self.check_twitter_login():
                self.save_twitter_cookies()
                print("✅ 推特登录成功，cookies已保存")
        
        print("✅ 等待完成，开始自动化操作")
        return True
        
    def safe_click(self, driver, element, description=""):
        """安全点击元素"""
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            self.random_delay(0.5, 1)
            driver.execute_script("arguments[0].click();", element)
            self.logger.info(f"✅ {description} 成功")
            return True
        except Exception as e:
            self.logger.warning(f"❌ {description} 失败: {e}")
            return False
            
    def extract_tweet_content(self, tweet_element):
        """提取推文内容"""
        try:
            text_elements = tweet_element.find_elements(By.CSS_SELECTOR, '[data-testid="tweetText"]')
            if text_elements:
                content = text_elements[0].text
                self.logger.info(f"提取到推文内容: {content[:50]}...")
                return content
            
            text_elements = tweet_element.find_elements(By.CSS_SELECTOR, 'div[lang]')
            if text_elements:
                content = text_elements[0].text
                self.logger.info(f"提取到推文内容: {content[:50]}...")
                return content
            
            return ""
        except Exception as e:
            self.logger.error(f"提取推文内容失败: {e}")
            return ""
            
    def get_ai_reply(self, tweet_content):
        """从豆包获取AI回复"""
        try:
            # 清理推文内容，移除回车符避免意外发送
            cleaned_content = tweet_content.replace('\n', ' ').replace('\r', ' ').strip()
            # 移除多余的空格
            cleaned_content = ' '.join(cleaned_content.split())
            
            # 构建提示词
            prompt = f"""需要回复的推文内容：{cleaned_content}"""
            
            # 查找豆包输入框
            textarea = self.doubao_wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "textarea"))
            )
            
            # 清空输入框
            textarea.clear()
            self.random_delay(1, 2)
            
            # 输入提示词
            for char in prompt:
                textarea.send_keys(char)
                time.sleep(0.05)
            
            self.random_delay(1, 2)
            
            # 发送消息
            textarea.send_keys(Keys.RETURN)
            
            # 等待回复生成
            self.logger.info("等待豆包生成回复...")
            self.random_delay(5, 8)
            
            # 提取回复
            reply = self.extract_doubao_reply()
            
            if reply:
                self.logger.info(f"豆包回复: {reply}")
                return reply
            else:
                self.logger.info("豆包回复失败，使用备用回复")
                return self.get_fallback_reply()
                
        except Exception as e:
            self.logger.error(f"获取AI回复失败: {e}")
            return self.get_fallback_reply()
            
    def extract_doubao_reply(self):
        """提取豆包回复"""
        try:
            self.random_delay(2, 4)
            tags = [
                        ""
            ]
            
            # 使用用户提供的精确选择器
            selectors = [
                # 用户提供的精确元素
                "div.auto-hide-last-sibling-br.paragraph-JOTKXA.paragraph-element.br-paragraph-space",
            ]
            
            for selector in selectors:
                try:
                    paragraph_elements = self.doubao_driver.find_elements(By.CSS_SELECTOR, "div[class*='br-paragraph-space']")
                    self.logger.info(f"paragraph_elements: {paragraph_elements}")
                    if paragraph_elements:
                        latest_reply = paragraph_elements[-1]
                        reply_text = latest_reply.text.strip()
                        if reply_text and len(reply_text) > 5:
                            self.logger.info(f"使用选择器 '{selector}' 成功提取回复")
                            return reply_text + random.choice(tags)
                except Exception as e:
                    self.logger.warning(f"选择器 '{selector}' 提取失败: {e}")
                    continue

            # 如果上面的选择器都不行，尝试查找包含文本的元素
            try:
                # 查找所有可能包含回复的元素
                all_elements = self.doubao_driver.find_elements(By.XPATH, "//*[contains(text(), '')]")
                for element in reversed(all_elements):
                    text = element.text.strip()
                    if text and len(text) > 10 and len(text) < 200:
                        return text + random.choice(tags)
                        
            except:
                pass
            
            return ""
            
        except Exception as e:
            self.logger.error(f"提取豆包回复失败: {e}")
            return ""
            
    def get_fallback_reply(self):
        """获取备用回复"""
        fallback_replies = [
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
            ""
        ]
        return random.choice(fallback_replies) + random.choice(tags)
        
    def process_tweet(self, tweet_element):
        """处理单条推文：点赞 + AI评论"""
        try:
            # 检查推文是否为回复，如果是回复则跳过
            try:
                # 先提取推文内容
                tweet_content = self.extract_tweet_content(tweet_element)
                
                # 简单判断：字数少于50的推文默认为回复，跳过处理
                if len(tweet_content) < 50:
                    self.logger.info(f"推文字数不足50字（当前{len(tweet_content)}字），默认为回复，跳过处理")
                    return False
                    
            except Exception as e:
                self.logger.warning(f"检查推文字数失败: {e}")
                return False
            
            # 检查用户名，如果是自己的推文就跳过
            try:
                username_elements = tweet_element.find_elements(By.CSS_SELECTOR, '[data-testid="User-Name"] a')
                if username_elements:
                    username = username_elements[0].text.strip()
                    if username.startswith('@'):
                        username = username[1:]  # 移除@符号
                    
                    # 获取配置中的用户名
                    config_username = self.config.get("my_username", "")
                    
                    # 比较用户名（中文用户名不需要lower()）
                    if username == config_username or username.lower() == config_username.lower():
                        self.logger.info("检测到自己的推文，跳过处理")
                        return False
            except Exception as e:
                self.logger.warning(f"检查用户名失败: {e}")
            
            # 推文内容已经在前面提取过了，这里直接使用
            
            # 查找点赞按钮
            like_button = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="like"]')
            
            # 检查是否已经点赞
            if "liked" not in like_button.get_attribute("class"):
                # 点赞
                if self.safe_click(self.twitter_driver, like_button, "点赞"):
                    self.random_delay(1, 2)
                    
                                # 获取AI回复
                    if tweet_content:
                        ai_reply = self.get_ai_reply(tweet_content)
                        # 去掉最后一个符号（通常是句号、感叹号等）
                        if ai_reply and ai_reply[-1] in '。！？.!?':
                            ai_reply = ai_reply[:-1]
                        self.logger.info(f"AI生成回复: {ai_reply}")
                    else:
                        ai_reply = self.get_fallback_reply()
                        # 同样去掉备用回复的最后一个符号
                        if ai_reply and ai_reply[-1] in '。！？.!?':
                            ai_reply = ai_reply[:-1]

                    # 查找回复按钮
                    reply_button = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="reply"]')
                    
                    # 评论
                    if self.safe_click(self.twitter_driver, reply_button, "点击回复"):
                        self.random_delay(1, 2)
                        
                        # 查找评论输入框
                        comment_input = self.twitter_wait.until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="tweetTextarea_0"]'))
                        )
                        
                        comment_input.clear()
                        
                        # 输入评论
                        for char in ai_reply:
                            comment_input.send_keys(char)
                            time.sleep(0.05)
                        self.random_delay(1, 2)
                        
                        # 点击发送按钮
                        send_button = self.twitter_driver.find_element(
                            By.CSS_SELECTOR, 
                            '[data-testid="tweetButton"]'
                        )
                        if self.safe_click(self.twitter_driver, send_button, "发送评论"):
                            self.logger.info(f"✅ 推文处理完成: 点赞 + 评论 '{ai_reply}'")
                            self.random_delay(2, 4)
                            return True
                        else:
                            # 如果发送失败，尝试关闭评论框
                            try:
                                cancel_button = self.twitter_driver.find_element(
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
        
    def browse_and_interact(self, max_tweets=10):
        """浏览推特并互动"""
        try:
            self.logger.info(f"开始浏览推特并互动，目标数量: {max_tweets}")
            
            processed_count = 0
            processed_tweet_ids = set()  # 记录已处理的推文ID，避免重复处理
            scroll_count = 0
            no_new_tweets_count = 0  # 连续没有新推文的次数
            
            while processed_count < max_tweets:
                # 查找所有推文
                tweet_elements = self.twitter_driver.find_elements(
                    By.CSS_SELECTOR, 
                    '[data-testid="tweet"]'
                )
                
                if not tweet_elements:
                    self.logger.info("当前页面没有找到推文，刷新页面...")
                    self.twitter_driver.refresh()
                    self.random_delay(3, 5)  # 等待页面加载
                    no_new_tweets_count = 0
                    scroll_count = 0
                    continue
                
                # 处理当前页面的推文
                new_tweets_found = False
                for tweet_element in tweet_elements:
                    if processed_count >= max_tweets:
                        break
                    
                    try:
                        # 尝试获取推文的唯一标识（使用推文内容的前50个字符作为标识）
                        tweet_content = self.extract_tweet_content(tweet_element)
                        if tweet_content:
                            tweet_id = hash(tweet_content[:50])  # 使用内容哈希作为标识
                        else:
                            # 如果无法提取内容，使用元素位置作为标识
                            tweet_id = id(tweet_element)
                        
                        # 检查是否已处理过
                        if tweet_id in processed_tweet_ids:
                            continue
                        
                        # 处理单条推文
                        if self.process_tweet(tweet_element):
                            processed_count += 1
                            processed_tweet_ids.add(tweet_id)
                            new_tweets_found = True
                            self.logger.info(f"已处理 {processed_count}/{max_tweets} 条推文")
                            
                        # 处理完一条推文后，滚动到下一位置
                        self.twitter_driver.execute_script("window.scrollBy(0, 300);")
                        self.random_delay(1, 20)
                        
                    except Exception as e:
                        self.logger.warning(f"处理推文时出错: {e}")
                        continue
                
                # 如果找到了新推文，重置计数器
                if new_tweets_found:
                    no_new_tweets_count = 0
                else:
                    no_new_tweets_count += 1
                
                # 如果连续多次没有找到新推文，尝试滚动或刷新
                if no_new_tweets_count >= 3:
                    # 先尝试滚动加载更多推文
                    if scroll_count < 30:
                        self.logger.info("未找到新推文，滚动页面加载更多...")
                        self.twitter_driver.execute_script("window.scrollBy(0, 1000);")
                        self.random_delay(2, 3)
                        scroll_count += 1
                        no_new_tweets_count = 0
                    else:
                        # 如果滚动次数达到上限，刷新页面获取新推文
                        self.logger.info("已浏览完当前页面所有推文，刷新页面获取新推文...")
                        self.twitter_driver.refresh()
                        self.random_delay(3, 5)  # 等待页面加载
                        scroll_count = 0
                        no_new_tweets_count = 0
                        # 清空已处理推文记录，因为刷新后会有新推文
                        processed_tweet_ids.clear()
                else:
                    # 正常滚动加载更多推文
                    if scroll_count < 30:
                        self.twitter_driver.execute_script("window.scrollBy(0, 1000);")
                        self.random_delay(2, 3)
                        scroll_count += 1
                    else:
                        # 滚动次数达到上限，刷新页面
                        self.logger.info("滚动次数达到上限，刷新页面获取新推文...")
                        self.twitter_driver.refresh()
                        self.random_delay(3, 5)  # 等待页面加载
                        scroll_count = 0
                        # 清空已处理推文记录，因为刷新后会有新推文
                        processed_tweet_ids.clear()
                
            self.logger.info(f"浏览互动完成，共处理 {processed_count} 条推文")
            
        except Exception as e:
            self.logger.error(f"浏览互动过程中出错: {e}")
            
    def close(self):
        """关闭浏览器"""
        if self.twitter_driver:
            self.twitter_driver.quit()
            self.logger.info("推特浏览器已关闭")
            
        if self.doubao_driver:
            self.doubao_driver.quit()
            self.logger.info("豆包浏览器已关闭")

def main():
    """主函数"""
    print("🤖 推特自动化机器人 - 简化版")
    print("=" * 50)
    
    # 加载配置
    try:
        config = load_config()
        print("✅ 配置文件加载成功")
    except Exception as e:
        print(f"❌ 配置文件加载失败: {e}")
        return
    
    bot = None
    try:
        # 创建机器人实例
        bot = TwitterBot(config)
        
        # 尝试使用外部cookies
        external_cookies = config.get("external_cookies_file")
        if external_cookies:
            print(f"尝试使用外部cookies文件: {external_cookies}")
            
        # 打开网站
        if not bot.open_websites(external_cookies):
            print("❌ 打开网站失败")
            return
        
        # 等待用户登录
        bot.wait_for_login()
        
        # 开始自动化操作
        print("🚀 开始自动化操作...")
        bot.browse_and_interact(max_tweets=config.get("max_tweets", 10))
        
        print("🎉 所有操作完成！")
        
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断操作")
    except Exception as e:
        print(f"❌ 程序出错: {e}")
    finally:
        if bot:
            bot.close()

if __name__ == "__main__":
    main() 