"""Quick-start CLI. API checks never open X or perform social actions."""
import argparse
import json
from pathlib import Path
from settings import ROOT, PRESETS, load_config, api_settings
from ai_client import APIClient, AIError

def init_config():
    path = ROOT / 'config.json'
    if path.exists():
        raise ValueError('config.json 已存在；请直接编辑，避免覆盖本地配置')
    config = json.loads((ROOT / 'config.example.json').read_text(encoding='utf-8-sig'))
    mode = input('选择模式 [1 豆包网页版 / 2 API，默认 1]：').strip()
    config['ai_mode'] = 'api' if mode == '2' else 'doubao_web'
    if mode == '2':
        print('可用提供方：' + ', '.join(PRESETS))
        provider = input('提供方 [openai]：').strip() or 'openai'
        if provider not in PRESETS:
            raise ValueError('未知提供方')
        config['api']['provider'] = provider
        if provider == 'custom':
            config['api']['protocol'] = input('协议 [openai_chat/openai_responses/anthropic/gemini]：').strip()
            config['api']['base_url'] = input('API 基础地址（包含 /v1 等版本，不含具体接口）：').strip()
        config['api']['model'] = input('模型 ID（以提供方控制台为准）：').strip()
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    env = ROOT / '.env'
    if not env.exists():
        env.write_text((ROOT / '.env.example').read_text(encoding='utf-8-sig'), encoding='utf-8')
    print('已生成 config.json 和 .env。API 模式请在 .env 填写 LLM_API_KEY；密钥不会写入 JSON。')

def main():
    parser = argparse.ArgumentParser(description='X 浏览互动：豆包网页 / 多协议 API；默认只预览')
    parser.add_argument('--config', help='本地 JSON 配置路径')
    parser.add_argument('--init', action='store_true', help='交互式生成本地配置')
    parser.add_argument('--check', action='store_true', help='检查配置，不发模型请求')
    parser.add_argument('--test-ai', action='store_true', help='生成一条测试回复，不打开 X')
    parser.add_argument('--text', default='今天终于完成了第一个 Python 项目，学到了很多！')
    parser.add_argument('--execute', action='store_true', help='实际点赞并发布评论；默认只预览')
    parser.add_argument('--continuous', action='store_true', help='持续浏览，使用本地去重记录和随机间隔')
    parser.add_argument('--check-browser', action='store_true', help='只读检查现有 Chrome 和回复历史，不生成或发布评论')
    args = parser.parse_args()
    ai = None
    try:
        if args.init:
            init_config()
            return 0
        config = load_config(args.config)
        if args.continuous:
            config['continuous'] = True
        if args.check_browser:
            config['continuous'] = True
            config['_browser_check_only'] = True
        if config.get('ai_mode') == 'api' and not args.check_browser:
            api_settings(config)
        if args.check:
            print('配置检查通过。')
        elif args.test_ai:
            if config.get('ai_mode') == 'api':
                ai = APIClient(config)
            else:
                from doubao_web import create_doubao_client
                ai = create_doubao_client(config)
                ai.ready()
            print('AI 连接测试成功：' + ai.generate_reply(args.text))
        else:
            from main import run
            print('运行模式：' + ('浏览器只读检查' if args.check_browser else
                  '实际点赞评论' if args.execute else '只预览'))
            run(config, execute=args.execute and not args.check_browser)
        return 0
    except FileNotFoundError:
        print('缺少本地配置；请先运行 python start.py --init')
        return 1
    except (ValueError, AIError, RuntimeError) as e:
        print(str(e))
        return 1
    except KeyboardInterrupt:
        print('已停止。')
        return 130
    except Exception:
        print('运行失败；请检查 Chrome、登录状态和网页选择器。未输出可能含敏感数据的异常详情。')
        return 1
    finally:
        if ai:
            ai.close()

if __name__ == '__main__':
    raise SystemExit(main())
