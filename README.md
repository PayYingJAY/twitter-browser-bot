# Twitter Browser Bot

Python + Selenium 浏览 X（推特），读取推文并生成回复。两种 AI 模式共用同一套流程：**豆包网页版**或**多协议 API**。默认只预览，加入 `--execute` 才会点赞和发布评论。

## 5 分钟开始

需要 Python 3.10+、已安装的 Chrome 和能访问 X / 模型提供方的网络。

```bash
git clone https://github.com/PayYingJAY/twitter-browser-bot.git
cd twitter-browser-bot
python -m venv .venv
```

Windows PowerShell：`.venv\Scripts\Activate.ps1`；macOS / Linux：`source .venv/bin/activate`。如果 PowerShell 阻止激活，可直接用 `.venv\Scripts\python.exe` 代替下面的 `python`。

```bash
python -m pip install -r requirements.txt
python start.py --init
```

向导生成本地 `config.json` 和 `.env`，已有配置不会覆盖。

### 方式一：豆包网页版（不需要 API Key）

向导选择 `1`，然后：

```bash
python start.py --test-ai
```

在打开的豆包窗口登录并进入空白对话，回终端按 Enter。成功后终端显示测试回复。登录保存在本地独立 Chrome profile，下次可复用。当前网页使用 contenteditable 编辑器，适配器同时支持 textarea；回答只从新的 assistant 消息提取，等待生成结束和文字稳定，不会把历史回答或页面任意文字当回复。页面结构变化时可修改 `doubao.selectors`。

### 方式二：API

向导选择 `2`，选择提供方并填写**该账号可用的模型 ID**。编辑 `.env`：

```dotenv
LLM_API_KEY=填入你自己的密钥
# 可选：覆盖提供方地址、模型
LLM_BASE_URL=
LLM_MODEL=
TWITTER_MY_USERNAME=你的X用户名不含@（可选）
```

然后：

```bash
python start.py --check
python start.py --test-ai
```

测试只向所选模型发送一条示例推文，不打开 X。API 模式不需要豆包登录。

## 浏览预览和实际发布

```bash
python start.py             # 打开 X、生成并显示回复，不点赞、不发送
python start.py --execute   # 实际点赞并发送评论
```

X 首次需要手动登录，在首页准备好后回终端按 Enter。`max_tweets` 默认 3；`like_tweets: false` 可关闭点赞。`TWITTER_MY_USERNAME` 填写账号 handle，可跳过自己的推文。`interaction_delay_seconds` 控制发布间隔。

## 协议与提供方

以下是接口适配范围，不代表每个厂商、模型都已实际调用验证。模型名由用户填写，不自动换模型。

| `api.provider` | 默认协议 | 说明 |
|---|---|---|
| `openai` | `openai_chat` | `/chat/completions` |
| `openai_responses` | `openai_responses` | `/responses` |
| `anthropic` | `anthropic` | `/messages`，独立 system 与版本头 |
| `gemini` | `gemini` | `/models/{model}:generateContent` |
| `deepseek` | `openai_chat` | DeepSeek 兼容接口 |
| `qwen` | `openai_chat` | 阿里云百炼兼容接口；地域可覆盖 |
| `ark` / `ark_coding` | `openai_chat` | 火山方舟通用 / Coding Plan 接口 |
| `ollama` | `openai_chat` | 本机 `http://localhost:11434/v1`，可不填 Key |
| `custom` | 自定义 | GLM、Moonshot、MiniMax、OpenRouter、vLLM、LM Studio 或中转站等，按服务实际支持的协议配置 |

`api.protocol` 留空使用预设，或填上述四种协议之一。`api.base_url` 填包含版本的基础地址（如 `https://example.com/v1`），**不要加** `/chat/completions` 等具体接口。`LLM_BASE_URL` / `LLM_MODEL` 环境变量优先于 JSON。凭据优先取 `LLM_API_KEY`，也支持预设提供方的标准变量，或 `api.api_key_env` 指定变量名。API Key 本身始终不放在 JSON。

不同网关可能支持不同参数。默认 Chat 使用 `max_completion_tokens`；若网关仅接受 `max_tokens`，可在 `api.extra_body` 填 `{"max_tokens": 1024}`，会自动去掉前者。可用 `extra_body` 设置厂商专属 thinking 等选项，但不能覆盖模型、提示词或流式设置。当前实现为非流式纯文本生成，不包含工具调用、多模态、Bedrock/Vertex 云签名认证。

方舟 Coding Plan 示例（模型 ID 以账号权限为准）：

```json
{
  "ai_mode": "api",
  "api": {
    "provider": "ark_coding",
    "model": "doubao-seed-2-1-pro-260915",
    "max_output_tokens": 2048,
    "trust_env": false,
    "extra_body": {"thinking": {"type": "disabled"}}
  }
}
```

把相应字段合并到向导生成的配置中。Coding Plan 的模型、额度及允许用途以提供方订阅条款为准。

## 隐私与故障处理

- `.env` 自动加载；已存在的终端环境变量优先。`config.json`、Cookies、日志、浏览器 profile 和虚拟环境均被 Git 忽略。
- `browser_data/twitter` 和 `browser_data/doubao` 含登录状态，**不要分享**。ChromeDriver 由 Selenium Manager 自动管理；离线时在配置顶层设置 `chromedriver_path`。
- 仅支持 HTTPS API（localhost 可 HTTP），不跟随重定向，不输出 HTTP 错误正文、请求头和 Key。
- 网络超时、额度不足、输出为空/截断/被过滤时停止，不自动重发请求、不自动切换模型，也不发送备用模板评论。
- HTTP 401/403：检查 Key 和账号权限；404：检查基础地址、协议和模型；429：检查额度或速率。错误提示只保留状态码。
- 代理：默认沿用环境代理；`api.trust_env: false` 可对 API 直连，不修改系统代理。
- 豆包测试超时：先确认登录、空白对话和页面可正常生成，再检查配置中的输入框、assistant、停止按钮选择器。不要把 assistant 选择器改成通用段落或页面文字。
- X 页面变动可能需要调整 `main.py` 的选择器。发送后确认超时会停止，避免重复评论。
- 旧版 `run_bot.py` 现在转到同一 CLI，已移除旧模板兜底与账号密码自动登录代码。

## 验证

```bash
python -m unittest discover -s tests -v
```

四种 API 协议覆盖请求、响应解析、错误脱敏和空输出处理；豆包覆盖旧消息排除。真实 API 验证：2026-11-16，火山方舟 Coding Plan / Seed 2.1 Pro 返回有效中文回复。其他厂商仅做协议级模拟测试。豆包网页实际生成验证状态见发布说明，登录不可用时不宣称已通过。未进行真实 X 点赞或评论测试。

接口参考：[OpenAI Responses](https://developers.openai.com/api/reference/resources/responses/methods/create)、[Anthropic Messages](https://platform.claude.com/docs/en/api/messages)、[Gemini generateContent](https://ai.google.dev/api/generate-content)。

MIT License。运行前阅读生成内容，并遵守平台及模型服务规则。
