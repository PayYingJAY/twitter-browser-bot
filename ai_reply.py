#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI智能回复模块
使用OpenAI API生成针对推文内容的智能回复
"""

import os
import openai
import json
import logging
import time
import random
from typing import Optional, List

class AIReplyGenerator:
    def __init__(self, api_key: str, model: str = "gpt-3.5-turbo"):
        """
        初始化AI回复生成器
        :param api_key: OpenAI API密钥
        :param model: 使用的模型名称
        """
        self.api_key = api_key
        self.model = model
        self.client = openai.OpenAI(api_key=api_key)
        self.setup_logging()
        
    def setup_logging(self):
        """设置日志"""
        self.logger = logging.getLogger(__name__)
        
    def generate_reply(self, tweet_content: str, comment_content: str = "", 
                      language: str = "中文", max_length: int = 100) -> Optional[str]:
        """
        生成针对推文内容的智能回复
        :param tweet_content: 推文内容
        :param comment_content: 评论内容（如果有）
        :param language: 回复语言
        :param max_length: 最大回复长度
        :return: 生成的回复内容
        """
        try:
            # 构建提示词
            prompt = self._build_prompt(tweet_content, comment_content, language, max_length)
            
            # 调用OpenAI API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个友善的推特用户，善于与其他人互动。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_length,
                temperature=0.7,
                top_p=0.9
            )
            
            reply = response.choices[0].message.content.strip()
            
            # 清理回复内容
            reply = self._clean_reply(reply, max_length)
            
            self.logger.info(f"AI生成回复: {reply}")
            return reply
            
        except Exception as e:
            self.logger.error(f"AI生成回复失败: {e}")
            return self._get_fallback_reply(language)
    
    def _build_prompt(self, tweet_content: str, comment_content: str, 
                     language: str, max_length: int) -> str:
        """构建提示词"""
        if language == "中文":
            prompt = f"""
请针对以下推文内容生成一个友善、有意义的回复。

推文内容：{tweet_content}

{f"评论内容：{comment_content}" if comment_content else ""}

要求：
1. 回复要自然、友善，体现对内容的关注和理解
2. 长度控制在{max_length}字以内
3. 避免过于正式或机械化的表达
4. 可以表达赞同、感谢、鼓励或提出建设性意见
5. 使用中文回复

请直接给出回复内容，不要包含任何解释或额外文字。
"""
        else:
            prompt = f"""
Please generate a friendly and meaningful reply to the following tweet.

Tweet content: {tweet_content}

{f"Comment content: {comment_content}" if comment_content else ""}

Requirements:
1. The reply should be natural and friendly, showing understanding of the content
2. Keep it under {max_length} characters
3. Avoid overly formal or mechanical expressions
4. Can express agreement, gratitude, encouragement, or constructive feedback
5. Reply in {language}

Please provide the reply directly without any explanation or additional text.
"""
        
        return prompt
    
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

class MockAIReplyGenerator:
    """模拟AI回复生成器（用于测试或API不可用时）"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def generate_reply(self, tweet_content: str, comment_content: str = "", 
                      language: str = "中文", max_length: int = 100) -> str:
        """生成模拟回复"""
        # 基于推文内容的关键词生成回复
        keywords = self._extract_keywords(tweet_content)
        
        if language == "中文":
            replies = {
                "学习": ["学到了新知识！", "很有教育意义", "感谢分享经验"],
                "技术": ["技术分享很棒！", "这个技术很有用", "学到了新技能"],
                "生活": ["生活感悟很深刻", "分享得很棒！", "很有共鸣"],
                "工作": ["工作建议很实用", "职场经验很有价值", "感谢分享心得"],
                "娱乐": ["很有趣的内容！", "分享得很棒！", "很有娱乐性"],
                "新闻": ["新闻分析很到位", "观点很有见地", "感谢分享信息"],
                "美食": ["美食分享很棒！", "看起来很好吃", "感谢推荐"],
                "旅行": ["旅行经历很精彩", "风景很美", "感谢分享美景"],
                "健康": ["健康建议很实用", "养生知识很有用", "感谢分享"],
                "情感": ["情感分享很真实", "很有共鸣", "感谢分享感受"]
            }
        else:
            replies = {
                "learn": ["Learned something new!", "Very educational", "Thanks for sharing"],
                "tech": ["Great tech sharing!", "This technology is useful", "Learned new skills"],
                "life": ["Life insights are profound", "Great sharing!", "Very relatable"],
                "work": ["Work advice is practical", "Career experience is valuable", "Thanks for sharing"],
                "entertainment": ["Very interesting content!", "Great sharing!", "Very entertaining"],
                "news": ["News analysis is spot on", "Great perspective", "Thanks for sharing"],
                "food": ["Great food sharing!", "Looks delicious", "Thanks for the recommendation"],
                "travel": ["Amazing travel experience", "Beautiful scenery", "Thanks for sharing"],
                "health": ["Health advice is practical", "Wellness knowledge is useful", "Thanks for sharing"],
                "emotion": ["Emotional sharing is genuine", "Very relatable", "Thanks for sharing"]
            }
        
        # 根据关键词选择回复
        for keyword, reply_list in replies.items():
            if keyword in keywords:
                return random.choice(reply_list)
        
        # 如果没有匹配的关键词，返回通用回复
        if language == "中文":
            generic_replies = [
                "很有趣的内容！👍",
                "支持一下，继续加油！",
                "不错的内容，学习了",
                "很有见地，感谢分享",
                "这个观点很有意思"
            ]
        else:
            generic_replies = [
                "Interesting content! 👍",
                "Keep up the good work!",
                "Great content, learned a lot",
                "Insightful, thanks for sharing",
                "This is an interesting perspective"
            ]
        
        return random.choice(generic_replies)
    
    def _extract_keywords(self, content: str) -> str:
        """提取关键词"""
        content_lower = content.lower()
        
        # 定义关键词映射
        keyword_mapping = {
            "学习": ["学习", "知识", "教育", "培训", "课程", "教程"],
            "技术": ["技术", "编程", "代码", "开发", "软件", "app", "网站"],
            "生活": ["生活", "日常", "家庭", "朋友", "心情", "感受"],
            "工作": ["工作", "职场", "职业", "公司", "老板", "同事"],
            "娱乐": ["娱乐", "游戏", "电影", "音乐", "综艺", "明星"],
            "新闻": ["新闻", "时事", "政治", "社会", "事件", "报道"],
            "美食": ["美食", "食物", "餐厅", "烹饪", "菜谱", "小吃"],
            "旅行": ["旅行", "旅游", "景点", "风景", "酒店", "机票"],
            "健康": ["健康", "养生", "运动", "健身", "医疗", "疾病"],
            "情感": ["情感", "爱情", "友情", "亲情", "感情", "恋爱"]
        }
        
        # 检查内容中的关键词
        for category, keywords in keyword_mapping.items():
            for keyword in keywords:
                if keyword in content_lower:
                    return category
        
        return "通用"

def create_ai_reply_generator(config: dict) -> AIReplyGenerator:
    """创建AI回复生成器"""
    api_key = os.environ.get("OPENAI_API_KEY")
    
    if api_key and api_key != "your_openai_api_key":
        return AIReplyGenerator(api_key, config.get("openai_model", "gpt-3.5-turbo"))
    else:
        # 如果没有API密钥，使用模拟生成器
        logging.warning("未设置OpenAI API密钥，将使用模拟AI回复")
        return MockAIReplyGenerator()

# 测试函数
def test_ai_reply():
    """测试AI回复功能"""
    # 模拟配置
    config = {
        "openai_api_key": "your_openai_api_key",  # 未设置真实API密钥
        "openai_model": "gpt-3.5-turbo"
    }
    
    # 创建生成器
    generator = create_ai_reply_generator(config)
    
    # 测试推文内容
    test_tweets = [
        "今天学习了Python编程，感觉很有趣！",
        "分享一个技术小技巧：如何提高代码效率",
        "周末去了一家新开的餐厅，菜品很棒！",
        "工作压力很大，但是要坚持下去",
        "推荐一部很棒的电影，剧情很精彩"
    ]
    
    print("🧪 测试AI回复功能")
    print("=" * 50)
    
    for tweet in test_tweets:
        reply = generator.generate_reply(tweet, language="中文")
        print(f"推文: {tweet}")
        print(f"回复: {reply}")
        print("-" * 30)

if __name__ == "__main__":
    test_ai_reply() 