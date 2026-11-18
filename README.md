# Twitter Browser Bot

Python + Selenium 浏览 X（推特），Playwright 驱动豆包免费网页版，读取推文并生成回复。两种 AI 模式共用同一套流程：**豆包网页版**或**多协议 API**。默认只预览，加入 `--execute` 才会点赞和发布评论。

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

在打开的豆包窗口登录并进入空白对话，回终端按 Enter。成功后终端显示测试回复。豆包默认使用 Playwright 和已安装的 Chrome，登录保存在本地独立 Chrome profile，下次可复用。豆包部分不需要 ChromeDriver；输入用一次 fill 完成，元素由 locator 自动等待。当前网页使用 contenteditable 编辑器，适配器同时支持 textarea；回答只从新的 assistant 消息提取，读取 `data-streaming` 生成状态并等待文字稳定，只取 `message_text_content` 正文，不包含时间、按钮和推荐追问，不会把历史回答或页面任意文字当回复。页面结构变化时可修改 `doubao.selectors`。

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

### 豆包浏览器设置与迁移

默认配置：

```json
{"doubao": {"backend": "playwright", "browser_channel": "chrome", "timeout_seconds": 120}}
```

旧配置没有 `backend` 时自动使用 Playwright，继续使用项目 `browser_data/doubao` 登录目录。先关闭占用该目录的旧程序，不能同时用两个引擎操作同一 profile。不会导入个人 Chrome 主 profile 或导出 Cookies。登录过期时只需在程序窗口重新登录。

可选 `browser_channel: "msedge"` 使用已安装 Edge；使用 Playwright Chromium 时先运行 `python -m playwright install chromium`，再设置 `browser_channel: "chromium"`。若新版在你的机器上遇到兼容问题，设置 `doubao.backend: "selenium"` 可使用旧引擎。

这里的“免费”指豆包网页对账号开放的免费功能和额度，不代表无限调用。官方豆包助手 API 是独立付费服务；将网页登录 Cookie 包装成 API 的第三方代理并非官方免费接口，本项目不依赖它。详见[官方 API 说明](https://docs.volcengine.com/docs/ark/doubao-assistant?lang=zh)。引擎选择参考 [Playwright 自动等待](https://playwright.dev/python/docs/actionability)和[持久化浏览器](https://playwright.dev/python/docs/api/class-browsertype)。

## 浏览预览和实际发布

```bash
python start.py             # 打开 X、生成并显示回复，不点赞、不发送
python start.py --execute   # 实际点赞并发送评论
```

X 首次需要手动登录，在首页准备好后回终端按 Enter。`max_tweets` 默认 3；`like_tweets: false` 可关闭点赞。`TWITTER_MY_USERNAME` 填写账号 handle，可跳过自己的推文。`interaction_delay_seconds` 控制发布间隔。

回复会分别读取当前推文和页面中已显示的引用推文。支持视觉输入的方舟或 OpenAI 模型可连同两者的图片一起理解，每条最多读取 4 张 X 图片 CDN 的公开静态图。视频只提供正文和浏览器已加载的字幕；作者只写“看这个”或理解内容依赖画面或音频时会跳过。图片、引用或字幕无法读取时，是否回复取决于剩余内容能否支撑具体评论。已经在运行的进程需重新启动才会加载这些变更。

### 持续运行与去重

API 和现有 Chrome 会话配置好后，运行：

```powershell
.\.venv\Scripts\python.exe start.py --continuous --execute
```

也可在本地 JSON 设置 `"continuous": true`。持续模式忽略 `max_tweets`，需要 `TWITTER_MY_USERNAME`，并核对浏览器实际登录账号。默认阅读等待 4–10 秒，每次完成互动后等待 60–150 秒；滚动等待 3–7 秒，无新内容时休息 90–180 秒后刷新。各范围可在 `config.example.json` 对应字段调整。这些随机等待用于控制节奏，不保证自动化不会被平台识别。

去重使用 `browser_data/activity.db`，按账号和推文 ID 保存，重启后保留。启动时滚动个人“回复”页，同步网页返回的真实回复父 ID；没有预期网络响应时，通过本人回复的实际会话核对父推文，再在候选推文页检查可见的本人回复。默认最多滚动 15 次、核对最多 50 条未知会话；更早且网页未返回的历史记录无法保证全量识别。成功同步的结果可复用 10 分钟。发送前先持久保存待核实记录，仅点击一次发布按钮；收到 X 确认后标记成功。超时或结果不明的推文不会自动重发。已有点赞不会再次点击取消。

日志在 `logs/continuous.log`，状态在 `logs/status.json`。按 Ctrl+C，或新建 `browser_data/STOP` 文件停止；再次启动前移除 STOP 文件。程序只关闭自己的标签页，保留日常 Chrome。登录失效、验证、限流、账号不匹配或发送异常时暂停操作，不自动解除验证或重试发布。不得同时启动多个持续实例。

评论采用简短、平实的接话风格，减少数字复述、强行追问和运营术语；不替账号主人编个人经历或习惯。生成后检查额外 @用户名、套话、无依据的平台机制解释、重复措辞和超长句子。图片或亲历信息不足时跳过评论，不发送“看不到图”等输入限制说明，也不截断半句话后发布。连续模式遇到这类不合适的生成会跳过该条，不自动重试模型请求。语言风格仍需结合实际样例判断，规则无法保证识别所有问题。

### 自动回关认证关注者

持续正式模式可设置 `"follow_back": {"enabled": true, "interval_seconds": [30,60], "cooldown_seconds": [300,600,1800,3600,43200]}`。仅在当前账号的 `/{用户名}/verified_followers` 页面主列表点击明确标为“回关 / Follow back”的按钮。推荐栏、普通“关注”、本人、已关注和待核实账号均跳过；不会点击取消关注。回关按点击时间独立计时，目标间隔随机 30–60 秒，评论等待期间继续检查；处理页面加载、发布确认或验证时会顺延。点赞评论保留自身的间隔。旧版 `check_interval_seconds` 仍兼容固定回关间隔。

连续遇到临时频率限制时，依次冷却 5 分钟、10 分钟、30 分钟、1 小时、12 小时，后续维持最后一档；确认成功回关后重置档位。每日额度限制至少等待 24 小时；若服务端给出更长等待时间则遵守该时间。冷却到期后重新加载列表再尝试。比例限制或账号受限暂停回关，等待人工处理。回关结果无法确认时保存待核实记录，不重复点击同一账号，可通过刷新列表核实。回关记录、冷却时间及连续失败次数保存在本地数据库，重启不会清空；回关冷却时评论流程可继续运行。登录失效或身份验证仍会暂停整个程序。限制类型与恢复条件参见 [X 官方说明](https://help.x.com/en/using-x/x-follow-limit)。

只读排查浏览器与历史同步可运行 `python start.py --check-browser`，不调用模型、不点赞或发布。失败时状态文件记录阶段，页面截图保留在本地 `logs/last-error.png`（若能截图），请勿公开分享其中的账号内容。

### 复用平时 Chrome 中的 X 登录

Chrome 144+ 支持连接正在使用的浏览器，无需重启或重新登录：

1. 在已登录 X 的 Chrome 打开 `chrome://inspect/#remote-debugging`，开启远程调试。
2. 在本地 `config.json` 添加 `"twitter_browser": {"mode": "existing_chrome"}`。
3. 运行 `python start.py`，在 Chrome 弹出的连接提示中点击“允许”。确认新标签页进入 X 首页后，回终端按 Enter。

程序通过 Playwright 连接获准的会话，在该会话中新建 X 标签页；不读取或复制 Cookies。退出时仅关闭程序自己的标签页，保留 Chrome 和原有标签页。无法连接时直接停止。恢复独立浏览器可将 `mode` 改回 `isolated`。此设置仅作用于 X。

默认自动读取当前系统 Chrome 的连接入口；非默认安装可用 `twitter_browser.user_data_dir` 指定已开启远程调试的数据目录，或用 `twitter_browser.debugger_url` 指定本机 CDP 地址。使用结束可在同一 Chrome 页面关闭远程调试。该连接可以控制获准会话的页面，请仅允许信任的本地程序。详见 [Chrome 官方说明](https://developer.chrome.com/docs/devtools/agents/get-started/configuration/)。

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

不同网关可能支持不同参数。默认 Chat 使用 `max_completion_tokens`；若网关仅接受 `max_tokens`，可在 `api.extra_body` 填 `{"max_tokens": 1024}`，会自动去掉前者。可用 `extra_body` 设置厂商专属 thinking 等选项，但不能覆盖模型、提示词或流式设置。模型以非流式方式生成文字。方舟和 OpenAI 的 Chat、Responses 适配器支持向具备视觉能力的模型传图片，其余适配器收到正文、引用文字和可用字幕。

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
- `browser_data/twitter` 和 `browser_data/doubao` 含登录状态，**不要分享**。X 以及可选旧豆包引擎的 ChromeDriver 由 Selenium Manager 自动管理；离线时在配置顶层设置 `chromedriver_path`。默认豆包 Playwright 引擎不使用该驱动。
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

另外可运行真实 Chrome 本地页面集成测试（不登录豆包、不访问 X）：Windows PowerShell 先运行 `$env:RUN_BROWSER_TESTS="1"`，macOS/Linux 使用 `RUN_BROWSER_TESTS=1 python -m unittest discover -s tests -v`。验证多行输入、连续两轮生成、排除历史和推荐文字、流式完成和超时不重发。

四种 API 协议覆盖请求、响应解析、错误脱敏和空输出处理；豆包覆盖旧消息排除。真实 API 验证：2026-11-16，火山方舟 Coding Plan / Seed 2.1 Pro 返回有效中文回复。其他厂商仅做协议级模拟测试。豆包网页版：2026-11-16 已登录真实页面连续两轮生成成功，验证新版编辑器、回答正文选择器和 `data-streaming="false"` 完成状态。验证采用已登录浏览器操作及适配器回归测试，未把现有浏览器 Cookies 导入 Selenium 独立 profile；首次使用仍需在程序打开的窗口登录。未进行真实 X 点赞或评论测试。

接口参考：[OpenAI Responses](https://developers.openai.com/api/reference/resources/responses/methods/create)、[Anthropic Messages](https://platform.claude.com/docs/en/api/messages)、[Gemini generateContent](https://ai.google.dev/api/generate-content)。

MIT License。运行前阅读生成内容，并遵守平台及模型服务规则。

新版 Playwright 验证：22 项测试通过（含真实 Chrome 本地页面集成测试）。真实豆包网页在独立 profile 中的验证状态见 CHANGELOG。
