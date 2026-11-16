#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
豆包AI回复模块
使用豆包网页版生成针对推文内容的智能回复
"""

import time
import random
import logging
import json
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException

class DoubaoAIReplyGenerator:
    """豆包AI回复生成器"""
    
    def __init__(self, headless=False, cookies_file="doubao_cookies.json"):
        """
        初始化豆包AI回复生成器
        :param headless: 是否使用无头模式
        :param cookies_file: cookies文件路径
        """
        self.driver = None
        self.wait = None
        self.headless = headless
        self.cookies_file = cookies_file
        self.setup_logging()
        self.setup_driver()
        
    def setup_logging(self):
        """设置日志"""
        self.logger = logging.getLogger(__name__)
        
    def setup_driver(self):
        """设置浏览器驱动"""
        from selenium.webdriver.chrome.options import Options
        
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
            
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.wait = WebDriverWait(self.driver, 10)
            self.logger.info("豆包AI浏览器驱动初始化成功")
        except Exception as e:
            self.logger.error(f"豆包AI浏览器驱动初始化失败: {e}")
            raise
            
    def random_delay(self, min_seconds=1, max_seconds=3):
        """随机延迟"""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
        
    def save_cookies(self):
        """保存cookies"""
        try:
            cookies = self.driver.get_cookies()
            with open(self.cookies_file, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            self.logger.info(f"豆包cookies已保存到 {self.cookies_file}")
            return True
        except Exception as e:
            self.logger.error(f"保存豆包cookies失败: {e}")
            return False
            
    def load_cookies(self):
        """加载cookies"""
        try:
            if not os.path.exists(self.cookies_file):
                self.logger.info("豆包cookies文件不存在")
                return False
                
            with open(self.cookies_file, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
            
            # 检查当前是否已经在豆包网站
            current_url = self.driver.current_url
            if "doubao.com" not in current_url:
                # 只有在不在豆包网站时才重新访问
                self.driver.get("https://www.doubao.com/")
                self.random_delay(2, 3)
            
            # 添加cookies
            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except Exception as e:
                    self.logger.warning(f"添加cookie失败: {e}")
                    continue
            
            self.logger.info("豆包cookies加载成功")
            return True
            
        except Exception as e:
            self.logger.error(f"加载豆包cookies失败: {e}")
            return False
            
    def check_login_status(self):
        """检查登录状态"""
        try:
            # 不刷新页面，避免打断登录过程
            self.random_delay(2, 3)
            
            # 检查是否存在登录相关的元素
            login_elements = self.driver.find_elements(By.CSS_SELECTOR, "button, a")
            for element in login_elements:
                text = element.text.lower()
                if "登录" in text or "login" in text or "sign in" in text:
                    self.logger.info("检测到登录按钮，需要登录")
                    return False
            
            # 检查是否存在输入框（说明可以正常使用）
            try:
                textarea = self.driver.find_element(By.CSS_SELECTOR, "textarea")
                if textarea.is_displayed():
                    self.logger.info("检测到输入框，已登录状态")
                    return True
            except:
                pass
            
            self.logger.info("无法确定登录状态，尝试继续使用")
            return True
            
        except Exception as e:
            self.logger.error(f"检查登录状态失败: {e}")
            return False
        
    def open_doubao(self):
        """打开豆包网页版"""
        try:
            self.logger.info("正在打开豆包网页版...")
            self.driver.get("https://www.doubao.com/")
            self.random_delay(3, 5)
            
            # 尝试加载cookies
            if self.load_cookies():
                # 不刷新页面，避免打断登录过程
                self.random_delay(2, 3)
                
                # 检查登录状态
                if self.check_login_status():
                    self.logger.info("豆包网页版加载成功（已登录）")
                    return True
            
            # 如果没有cookies或登录失败，等待页面加载
            try:
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "textarea")))
                self.logger.info("豆包网页版加载成功")
                return True
            except:
                self.logger.warning("未检测到输入框，可能需要登录")
                return True  # 仍然返回True，让用户手动登录
            
        except Exception as e:
            self.logger.error(f"打开豆包网页版失败: {e}")
            return False
            
    def wait_for_login(self, timeout_minutes=1):
        """等待用户手动登录"""
        self.logger.info(f"请在 {timeout_minutes} 分钟内完成豆包登录...")
        self.logger.info("登录完成后，程序将自动保存cookies")
        
        # 完整等待指定时间
        timeout_seconds = timeout_minutes * 60
        self.logger.info(f"等待 {timeout_minutes} 分钟让您完成登录...")
        time.sleep(timeout_seconds)
        
        # 等待完成后，尝试保存cookies
        try:
            self.logger.info("等待完成，正在保存cookies...")
            if self.save_cookies():
                self.logger.info("cookies保存成功")
                return True
            else:
                self.logger.warning("cookies保存失败")
                return False
        except Exception as e:
            self.logger.error(f"保存cookies时出错: {e}")
            return False
            
    def generate_reply(self, tweet_content: str, comment_content: str = "", 
                      language: str = "中文", max_length: int = 100) -> str:
        """
        使用豆包生成回复
        :param tweet_content: 推文内容
        :param comment_content: 评论内容（如果有）
        :param language: 回复语言
        :param max_length: 最大回复长度
        :return: 生成的回复内容
        """
        try:
            # 检查登录状态
            if not self.check_login_status():
                self.logger.warning("豆包未登录，使用备用回复")
                return self._get_fallback_reply(language)
            
            # 构建提示词
            prompt = self._build_prompt(tweet_content, comment_content, language, max_length)
            
            # 查找输入框
            textarea = self.wait.until(
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
            
            # 发送消息（按Enter键）
            textarea.send_keys(Keys.RETURN)
            
            # 等待回复生成
            self.logger.info("等待豆包生成回复...")
            self.random_delay(5, 8)
            
            # 查找回复内容
            reply = self._extract_reply()
            
            if reply:
                # 清理回复内容
                reply = self._clean_reply(reply, max_length)
                self.logger.info(f"豆包生成回复: {reply}")
                return reply
            else:
                self.logger.warning("未能获取豆包回复，使用备用回复")
                return self._get_fallback_reply(language)
                
        except Exception as e:
            self.logger.error(f"豆包生成回复失败: {e}")
            return self._get_fallback_reply(language)
            
    def _build_prompt(self, tweet_content: str, comment_content: str, 
                     language: str, max_length: int) -> str:
        """构建提示词"""
        if language == "中文":
            prompt = f"""请针对以下推文内容生成一个友善、有意义的回复。

推文内容：{tweet_content}

{f"评论内容：{comment_content}" if comment_content else ""}

要求：
1. 回复要自然、友善，体现对内容的关注和理解
2. 长度控制在{max_length}字以内
3. 避免过于正式或机械化的表达
4. 可以表达赞同、感谢、鼓励或提出建设性意见
5. 使用中文回复

请直接给出回复内容，不要包含任何解释或额外文字。"""
        else:
            prompt = f"""Please generate a friendly and meaningful reply to the following tweet.

Tweet content: {tweet_content}

{f"Comment content: {comment_content}" if comment_content else ""}

Requirements:
1. The reply should be natural and friendly, showing understanding of the content
2. Keep it under {max_length} characters
3. Avoid overly formal or mechanical expressions
4. Can express agreement, gratitude, encouragement, or constructive feedback
5. Reply in {language}

Please provide the reply directly without any explanation or additional text."""
        
        return prompt
        
    def _extract_reply(self) -> str:
        """提取豆包的回复内容"""
        try:
            # 等待回复出现
            self.random_delay(2, 4)
            
            # 查找回复元素（可能需要尝试不同的选择器）
            selectors = [
                ".markdown-body",
                ".prose",
                "[data-testid='message-text']",
                ".message-content",
                ".ai-response",
                ".chat-message:last-child .content",
                ".message",
                ".response",
                ".ai-message"
            ]
            
            for selector in selectors:
                try:
                    reply_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if reply_elements:
                        # 获取最后一个回复元素
                        latest_reply = reply_elements[-1]
                        reply_text = latest_reply.text.strip()
                        if reply_text and len(reply_text) > 5:
                            return reply_text
                except:
                    continue
            
            # 如果上面的选择器都不行，尝试查找包含文本的元素
            try:
                # 查找所有可能包含回复的元素
                all_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), '')]")
                for element in reversed(all_elements):
                    text = element.text.strip()
                    if text and len(text) > 10 and len(text) < 200:
                        # 检查是否看起来像回复
                        if any(keyword in text for keyword in ["谢谢", "感谢", "很棒", "不错", "支持", "加油", "学习", "分享", "有趣", "同意"]):
                            return text
            except:
                pass
                
            return ""
            
        except Exception as e:
            self.logger.error(f"提取回复失败: {e}")
            return ""
            
    def _clean_reply(self, reply: str, max_length: int) -> str:
        """清理回复内容"""
        # 移除多余的引号
        reply = reply.strip('"\'')
        
        # 移除换行符
        reply = reply.replace('\n', ' ').replace('\r', ' ')
        
        # 移除多余的空格
        reply = ' '.join(reply.split())
        
        # 限制长度
        if len(reply) > max_length:
            reply = reply[:max_length-3] + "..."
        
        return reply
        
    def _get_fallback_reply(self, language: str) -> str:
        """获取备用回复"""
        if language == "中文":
            fallback_replies = [
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
            fallback_replies = [
                "Interesting content! 👍",
                "Keep up the good work!",
                "Great content, learned a lot",
                "Insightful, thanks for sharing",
                "This is an interesting perspective",
                "I completely agree with you",
                "Thanks for sharing, very helpful",
                "Great content, looking forward to more",
                "Very inspiring",
                "Support original content"
            ]
        
        return random.choice(fallback_replies)
        
    def close(self):
        """关闭浏览器"""
        if self.driver:
            self.driver.quit()
            self.logger.info("豆包AI浏览器已关闭")

def create_doubao_ai_reply_generator(config: dict = None):
    """创建豆包AI回复生成器"""
    headless = config.get("headless", False) if config else False
    cookies_file = config.get("doubao_cookies_file", "doubao_cookies.json") if config else "doubao_cookies.json"
    return DoubaoAIReplyGenerator(headless=headless, cookies_file=cookies_file)

# 测试函数
def test_doubao_ai():
    """测试豆包AI回复功能"""
    print("🤖 测试豆包AI回复功能")
    print("=" * 50)
    
    generator = None
    try:
        # 创建生成器
        generator = create_doubao_ai_reply_generator()
        print("✅ 豆包AI生成器创建成功")
        
        # 打开豆包
        print("🔄 正在打开豆包网页版...")
        if not generator.open_doubao():
            print("❌ 无法打开豆包网页版")
            return False
        
        # 检查是否需要登录
        if not generator.check_login_status():
            print("⚠️  需要登录豆包，请在浏览器中完成登录...")
            if not generator.wait_for_login(timeout_minutes=3):
                print("❌ 登录超时")
                return False
        
        print("✅ 豆包网页版准备就绪")
        
        # 测试推文内容
        test_tweets = [
            "今天学习了Python编程，感觉很有趣！",
            "分享一个技术小技巧：如何提高代码效率",
            "周末去了一家新开的餐厅，菜品很棒！"
        ]
        
        print("📝 开始测试豆包AI回复...")
        print("-" * 50)
        
        for i, tweet in enumerate(test_tweets, 1):
            try:
                reply = generator.generate_reply(tweet, language="中文")
                print(f"{i}. 推文: {tweet}")
                print(f"   回复: {reply}")
                print("-" * 50)
                
                # 等待一段时间再进行下一次测试
                time.sleep(3)
                
            except Exception as e:
                print(f"{i}. 推文: {tweet}")
                print(f"   错误: {e}")
                print("-" * 50)
        
        print("✅ 豆包AI回复测试完成！")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False
    finally:
        if generator:
            generator.close()

if __name__ == "__main__":
    test_doubao_ai() 