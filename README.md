<div align="center">

# Codex + DeepSeek

**让 OpenAI Codex CLI 使用 DeepSeek 模型** · 协议翻译代理

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](pyproject.toml)

</div>

---

## 这是什么？

[Codex CLI](https://github.com/openai/codex) 是 OpenAI 的 AI 编程助手，但它只能用 OpenAI 的模型。  
DeepSeek V4 是更强、更便宜的国产模型——但 Codex 不认识它。

这个项目在中间做一个**实时翻译代理**，让 Codex 跟 DeepSeek 无障碍对话。

```
┌─────────────┐     Responses API      ┌──────────────────┐     Chat Completions     ┌──────────┐
│  Codex CLI  │ ──── POST /v1/responses ───▶  代理 (8080)   ────▶ POST /v1/chat/ ────▶  DeepSeek │
│  (OpenAI)   │ ◀─── SSE / JSON 流 ──────   本地代理      ◀─────── JSON ──────────  (DeepSeek)│
└─────────────┘                        └──────────────────┘                        └──────────┘
```

---

## 快速开始

### 1. 安装 Codex CLI

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
```

### 2. 安装本项目

```bash
# 方式 A：pip 安装
pip install git+https://github.com/你的用户名/codex-deepseek.git

# 方式 B：本地安装
git clone https://github.com/你的用户名/codex-deepseek.git
cd codex-deepseek
pip install -e .

# 方式 C：单文件版（无需安装）
# 下载 codex_deepseek/proxy.py，直接 python3 proxy.py
```

### 3. 设置 API Key

```bash
# 方式 A：环境变量（临时）
export DEEPSEEK_API_KEY=***# 方式 B：用本工具保存（永久）
codex-deepseek set-key

# 方式 C：直接传参
codex-deepseek set-key *** 4. 启动

**终端 1 —— 启动代理：**

```bash
codex-deepseek proxy
```

**终端 2 —— 打开 Codex：**

```bash
codex
```

---

## 命令参考

| 命令 | 作用 |
|------|------|
| `codex-deepseek` | 配置 + 启动代理（交互式，首次运行推荐） |
| `codex-deepseek proxy` | 仅启动代理（终端 1） |
| `codex-deepseek setup` | 仅生成 Codex 配置文件 |
| `codex-deepseek set-key` | 设置/更换 API Key |
| `codex-deepseek set-key sk-xxx` | 直接传入 Key 设置 |
| `codex-deepseek --port 9090` | 指定代理端口 |
| `codex-deepseek --model deepseek-v4-flash` | 指定模型 |
| `codex-deepseek --version` | 查看版本 |

---

## 更换 API Key

```bash
# 交互输入
codex-deepseek set-key

# 直接传入（适合脚本）
codex-deepseek set-key ***# 或手动修改 ~/.bashrc 里的 DEEPSEEK_API_KEY=... 行
```

更换后重启代理即可生效。

---

## 支持的模型

| 模型名 | 说明 |
|--------|------|
| `deepseek-v4-pro` | DeepSeek V4 完整版（默认） |
| `deepseek-v4-flash` | DeepSeek V4 快速版 |
| `deepseek-chat` | DeepSeek 最新通用模型 |
| `deepseek-reasoner` | DeepSeek 推理模型 |

切换模型：

```bash
codex-deepseek --model deepseek-v4-flash proxy
# 或在 ~/.codex/config.toml 中修改 model = "deepseek-v4-flash"
```

---

## 配置文件

生成的配置在 `~/.codex/config.toml`：

```toml
model = "deepseek-v4-pro"
model_provider = "deepseek_proxy"

[model_providers.deepseek_proxy]
name = "DeepSeek (via proxy)"
base_url = "http://127.0.0.1:8080/v1"
wire_api = "responses"
supports_websockets = false
env_key = "DEEPSEEK_API_KEY"
```

如果需要自定义（如改端口），修改 `base_url` 中的端口即可。

---

## 功能状态

| 功能 | 状态 |
|------|------|
| 文本对话 | ✅ 流式 SSE + 非流式 JSON |
| 工具调用（写文件、跑命令等） | ✅ |
| 长上下文（128K） | ✅ |
| 多模型切换 | ✅ |
| 非流式模式 | ✅ |
| WebSocket | ❌（仅 HTTP） |

---

## 项目结构

```
codex-deepseek/
├── codex_deepseek/
│   ├── __init__.py       包元信息
│   ├── proxy.py          代理服务器 + Responses ↔ Chat 翻译（核心）
│   ├── config.py         Codex 配置文件生成器
│   └── cli.py            命令行入口（含 API Key 管理）
├── scripts/
│   └── install.sh        一键安装脚本（Linux / macOS）
├── examples/
│   ├── config.toml       配置示例
│   └── .env.example     环境变量示例
├── pyproject.toml        Python 包配置
├── README.md             本文档
└── LICENSE               MIT 许可证
```

---

## 工作原理

### 请求翻译（Codex → DeepSeek）

| Responses API 字段 | 翻译后 | 说明 |
|---|---|---|
| `instructions` | `messages[{role:"system"}]` | 系统提示词 |
| `input` | `messages[{role:"user"}]` | 用户输入 |
| `role:"developer"` | `role:"system"` | DeepSeek 不识别 developer |
| `tools[{name,parameters}]` | `tools[{function:{name,parameters}}]` | 工具定义格式转换 |
| `max_output_tokens` | `max_tokens` | 最大 Token 数 |
| `stream: true` | 强制 `stream: false` | 统一非流式请求 DeepSeek |

### 响应翻译（DeepSeek → Codex）

| Chat Completions 字段 | 翻译后（SSE 事件） | 说明 |
|---|---|---|
| `content: "你好"` | `event: output_text.delta` | 文本内容流式发送 |
| `tool_calls: [...]` | `event: function_call_arguments.delta` | 工具调用 |
| `usage.prompt_tokens` | `usage.input_tokens` | Token 用量映射 |
| `finish_reason: "stop"` | `status: "completed"` | 完成状态 |

---

## 许可证

MIT
