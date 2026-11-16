#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
豆包登录助手
帮助用户快速登录豆包并保存cookies
"""

import time
import os
from doubao_ai import create_doubao_ai_reply_generator

def doubao_login():
    """豆包登录助手"""
    print("🤖 豆包登录助手")
    print("=" * 50)
    print("此工具将帮助您登录豆包并保存cookies")
    print("登录成功后，程序将自动保存cookies，下次使用无需重新登录")
    print("=" * 50)
    
    # 检查是否已有cookies
    cookies_file = "doubao_cookies.json"
    if os.path.exists(cookies_file):
        print(f"ℹ️  发现现有cookies文件: {cookies_file}")
        choice = input("是否要清除现有cookies并重新登录？(y/n): ").strip().lower()
        if choice == 'y':
            try:
                os.remove(cookies_file)
                print("✅ 已清除现有cookies")
            except Exception as e:
                print(f"❌ 清除cookies失败: {e}")
                return False
        else:
            print("ℹ️  保留现有cookies")
    
    generator = None
    try:
        # 创建生成器
        print("🔄 正在初始化豆包AI...")
        generator = create_doubao_ai_reply_generator()
        
        # 打开豆包
        print("🔄 正在打开豆包网页版...")
        generator.driver.get("https://www.doubao.com/")
        print("✅ 豆包网页版已打开")
        
        # 直接等待用户登录，不进行任何检测
        print("\n⚠️  需要登录豆包")
        print("📝 浏览器已打开，请在1分钟内完成登录：")
        print("1. 在打开的浏览器中点击登录按钮")
        print("2. 输入您的账号密码")
        print("3. 完成登录")
        print("\n💡 提示：程序将完整等待1分钟，然后自动保存cookies")
        
        # 等待用户登录
        print(f"\n⏰ 程序将等待1分钟让您完成登录...")
        if generator.wait_for_login(timeout_minutes=1):
            print("✅ 等待完成，cookies已保存")
            print("🎉 现在可以在主程序中使用豆包AI功能了")
            return True
        else:
            print("❌ cookies保存失败")
            print("💡 您可以重新运行此程序进行登录")
            return False
            
    except Exception as e:
        print(f"❌ 登录过程出错: {e}")
        return False
    finally:
        if generator:
            generator.close()

def test_login():
    """测试登录状态"""
    print("🧪 测试豆包登录状态")
    print("=" * 50)
    
    generator = None
    try:
        # 创建生成器
        generator = create_doubao_ai_reply_generator()
        
        # 打开豆包
        if not generator.open_doubao():
            print("❌ 无法打开豆包网页版")
            return False
        
        # 检查登录状态
        if generator.check_login_status():
            print("✅ 豆包已登录，cookies有效")
            
            # 测试生成回复
            print("🔄 测试AI回复功能...")
            test_reply = generator.generate_reply("测试推文", language="中文")
            print(f"✅ AI回复测试成功: {test_reply}")
            return True
        else:
            print("❌ 豆包未登录或cookies已过期")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False
    finally:
        if generator:
            generator.close()

def main():
    """主函数"""
    print("🤖 豆包登录助手")
    print("=" * 50)
    
    print("请选择操作:")
    print("1. 登录豆包并保存cookies")
    print("2. 测试登录状态")
    print("3. 退出")
    
    choice = input("请输入选择 (1-3): ").strip()
    
    if choice == "1":
        success = doubao_login()
        if success:
            print("\n🎉 豆包登录成功！")
            print("现在可以在主程序中使用豆包AI功能了")
        else:
            print("\n❌ 豆包登录失败")
            print("请检查网络连接或重新尝试")
    elif choice == "2":
        success = test_login()
        if success:
            print("\n✅ 豆包登录状态正常")
        else:
            print("\n❌ 豆包登录状态异常")
            print("建议重新登录")
    elif choice == "3":
        print("👋 再见！")
        return
    else:
        print("❌ 无效选择")
        return
    
    input("\n按回车键退出...")

if __name__ == "__main__":
    main() 