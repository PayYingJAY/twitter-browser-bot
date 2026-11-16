# Twitter Browser Bot

基于 Python / Selenium 的推特（X）浏览与互动脚本，支持豆包网页生成回复，也保留 OpenAI API 版本。

## 快速开始

需要 Python 3.10+、Chrome 和匹配的 ChromeDriver。历史代码使用旧版依赖与网页选择器，尚未针对当前页面做真实账号验证。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item config.example.json config.json
$env:TWITTER_MY_USERNAME = "your_own_display_name"
python start.py
```

在打开的 X 和豆包窗口手动登录。脚本会保存登录 Cookies，并执行真实点赞和评论。修改本地 `config.json` 的 `max_tweets` 控制数量（示例为 10）。

## 配置与隐私

- `config.example.json` 是可公开的参数示例，`config.json` 为被 Git 忽略的本地配置。
- API Key 仅从 `OPENAI_API_KEY` 环境变量读取；JSON 中的密钥、用户名与密码字段不会被加载。
- `TWITTER_MY_USERNAME` 用于主程序跳过自己的推文；未设置时无法准确识别本人。
- 可选旧版入口 `python run_bot.py` 使用 `star_simple.py`，账号和密码分别从 `TWITTER_USERNAME`、`TWITTER_PASSWORD` 环境变量读取。`ai_type` 设为 `openai` 时使用 OpenAI 模块。
- `.env.example` 仅用于说明变量名；程序不自动读取 `.env`，请通过终端或密钥管理工具注入。
- Cookies、环境变量文件、日志、浏览器数据、数据库和截图均不提交。日志可能包含推文、评论或异常详情，分享前务必另行脱敏。
- 发布采用全新 Git 历史，不包含原项目历史、账号配置、Cookies、日志和驱动二进制。

## 文件

`main.py` / `start.py`：豆包网页版主入口。`doubao_ai.py` / `doubao_login.py`：豆包辅助模块。`ai_reply.py`：OpenAI 回复模块。`star_simple.py` / `run_bot.py`：可选旧版工作流。`settings.py`：统一配置与环境变量读取。

本项目保留历史实现；自动化依赖网页结构，页面更新后可能需要维护。运行前检查配置及生成内容，并遵守平台规则。

## License

MIT
