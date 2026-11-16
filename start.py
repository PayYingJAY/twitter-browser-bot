#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推特自动化机器人启动脚本
"""

import os
import sys

def main():
    """主函数"""
    print("🤖 推特自动化机器人")
    print("=" * 50)
    print("功能：打开x.com和豆包，等待登录，自动点赞和AI回复")
    print("=" * 50)
    
    # 检查配置文件
    if not os.path.exists("config.json"):
        print("❌ 配置文件 config.json 不存在")
        print("请确保配置文件存在")
        return
    
    # 检查主程序
    if not os.path.exists("main.py"):
        print("❌ 主程序 main.py 不存在")
        print("请确保主程序存在")
        return
    
    # 运行主程序
    print("🚀 启动主程序...")
    try:
        import main
        main.main()
    except Exception as e:
        print(f"❌ 程序运行失败: {e}")

if __name__ == "__main__":
    main() 