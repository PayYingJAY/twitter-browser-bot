#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推特自动化机器人主程序
支持从配置文件读取设置，提供更灵活的自动化功能
"""

import json
import sys
import argparse
from pathlib import Path
from settings import load_config as load_private_config
from star_simple import TwitterBot

def load_config(config_file="config.json"):
    """加载配置文件"""
    try:
        config = load_private_config(config_file)
        print(f"✅ 配置文件 {config_file} 加载成功")
        return config
    except FileNotFoundError:
        print(f"❌ 配置文件 {config_file} 不存在")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ 配置文件格式错误: {e}")
        return None

def validate_config(config):
    """验证配置文件"""
    required_fields = ["username", "password"]
    for field in required_fields:
        if field not in config or config[field] in ["your_username", "your_password"]:
            print(f"❌ 请在配置文件中设置正确的 {field}")
            return False
    
    # 验证数值参数
    numeric_fields = ["max_tweets", "max_replies", "browse_duration", "ai_reply_max_length"]
    for field in numeric_fields:
        if field in config and (not isinstance(config[field], int) or config[field] < 0):
            print(f"❌ {field} 必须是正整数")
            return False
    
    # 检查AI配置
    if config.get("use_ai_reply", False):
        ai_type = config.get("ai_type", "doubao")
        if ai_type == "doubao":
            print("✅ 豆包AI回复功能已启用")
            print("💡 提示：首次使用需要运行 python doubao_login.py 登录豆包")
        elif ai_type == "openai":
            api_key = config.get("openai_api_key")
            if not api_key or api_key == "your_openai_api_key":
                print("⚠️ 已启用OpenAI回复但未设置API密钥，将使用模拟AI回复")
            else:
                print("✅ OpenAI AI回复功能已启用")
        else:
            print("⚠️ 未知的AI类型，将使用模拟AI回复")
    else:
        print("ℹ️ 使用预设回复模板")
    
    print("✅ 配置文件验证通过")
    return True

def run_automation(config, mode="full"):
    """运行自动化任务"""
    bot = None
    try:
        print("🤖 启动推特自动化机器人...")
        
        # 创建机器人实例
        bot = TwitterBot(headless=config.get("headless", False), config=config)
        
        # 尝试加载cookies
        if not bot.load_cookies():
            print("🔐 开始登录推特...")
            if not bot.login_twitter(config["username"], config["password"]):
                print("❌ 登录失败，请检查用户名和密码")
                return False
        
        # 保存cookies
        bot.save_cookies()
        print("✅ 登录成功")
        
        # 获取AI设置
        use_ai = config.get("use_ai_reply", True)
        ai_type = config.get("ai_type", "doubao")
        
        if use_ai:
            if ai_type == "doubao":
                print("🤖 使用豆包AI生成回复")
            elif ai_type == "openai":
                print("🤖 使用OpenAI生成回复")
            else:
                print("🤖 使用模拟AI生成回复")
        else:
            print("📝 使用预设模板回复")
        
        # 根据模式执行不同的操作
        if mode == "full" or mode == "interact":
            print("👍 开始浏览推特并互动（点赞+评论）...")
            comments = config.get("comments", ["很有趣！", "支持一下", "不错的内容"])
            tags = config.get("tag", ["", "", "", "", "", ""])
            bot.browse_and_interact(
                max_tweets=config.get("max_tweets", 10), 
                comments_list=comments,
                use_ai=use_ai,
                tags=tags
            )
        
        if mode == "full" or mode == "reply":
            print("🔄 开始回复评论...")
            replies = config.get("reply_templates", ["谢谢评论！", "感谢支持！"])
            tags = config.get("tag", ["", "", "", "", "", ""])
            bot.reply_to_comments(
                reply_templates=replies, 
                max_replies=config.get("max_replies", 3),
                use_ai=use_ai,
                tags=tags
            )
        
        if mode == "full" or mode == "browse":
            print("📱 开始自动浏览...")
            bot.auto_browse(duration_minutes=config.get("browse_duration", 30))
        
        print("🎉 所有操作完成！")
        return True
        
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断操作")
        return False
    except Exception as e:
        print(f"❌ 程序出错: {e}")
        return False
    finally:
        if bot:
            bot.close()

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="推特自动化机器人")
    parser.add_argument(
        "--config", "-c", 
        default="config.json", 
        help="配置文件路径 (默认: config.json)"
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["full", "interact", "reply", "browse"],
        default="full",
        help="运行模式 (默认: full)"
    )
    parser.add_argument(
        "--headless", 
        action="store_true",
        help="使用无头模式运行"
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="禁用AI回复，使用预设模板"
    )
    
    args = parser.parse_args()
    
    # 检查配置文件是否存在
    if not Path(args.config).exists():
        print(f"❌ 配置文件 {args.config} 不存在")
        print("请先创建配置文件或使用 --config 参数指定正确的配置文件路径")
        return
    
    # 加载配置
    config = load_config(args.config)
    if not config:
        return
    
    # 验证配置
    if not validate_config(config):
        return
    
    # 覆盖设置
    if args.headless:
        config["headless"] = True
    
    if args.no_ai:
        config["use_ai_reply"] = False
        print("ℹ️ 已禁用AI回复，将使用预设模板")
    
    # 显示运行信息
    print(f"📋 运行模式: {args.mode}")
    print(f"🔧 无头模式: {config.get('headless', False)}")
    print(f"🤖 AI回复: {config.get('use_ai_reply', True)}")
    
    # 显示AI类型信息
    if config.get("use_ai_reply", True):
        ai_type = config.get("ai_type", "doubao")
        print(f"🤖 AI类型: {ai_type}")
        if ai_type == "doubao":
            print("💡 豆包AI：首次使用请运行 python doubao_login.py 登录")
        elif ai_type == "openai":
            print("💡 OpenAI AI：需要设置有效的API密钥")
    
    # 运行自动化任务
    success = run_automation(config, args.mode)
    
    if success:
        print("✅ 程序执行成功")
        sys.exit(0)
    else:
        print("❌ 程序执行失败")
        sys.exit(1)

if __name__ == "__main__":
    main() 