"""
Codex Responses API → DeepSeek Chat Completions API 协议翻译代理。

架构：
  Codex CLI  →  POST /v1/responses (Responses API)  →  代理  →  POST /v1/chat/completions  →  DeepSeek
  Codex CLI  ←  SSE / JSON (Responses API)           ←  代理  ←  JSON (Chat Completions)    ←  DeepSeek
"""

import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingMixIn, TCPServer
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError

__all__ = ["ProxyHandler", "ThreadingProxy", "run_proxy", "DEFAULT_MODEL"]

DEFAULT_MODEL = "deepseek-v4-pro"
DEEPSEEK_BASE = "https://api.deepseek.com"
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8080


# ============================================================
#  协议翻译
# ============================================================

def responses_to_chat(req_body: dict) -> dict:
    """Responses API 请求 → Chat Completions 请求"""
    messages = []

    # instructions → system message
    if req_body.get("instructions"):
        messages.append({"role": "system", "content": req_body["instructions"]})

    # input → messages
    inp = req_body.get("input", "")
    if isinstance(inp, str):
        messages.append({"role": "user", "content": inp})
    elif isinstance(inp, list):
        for msg in inp:
            role = msg.get("role", "user")
            if role == "developer":
                role = "system"  # DeepSeek 不识别 developer role
            content = msg.get("content", "")
            if isinstance(content, list):
                content = "\n".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "input_text"
                )
            messages.append({"role": role, "content": content})

    # tools (Responses 格式 → Chat Completions 格式)
    tools = []
    for t in req_body.get("tools", []):
        if t.get("type") == "function":
            tools.append({
                "type": "function",
                "function": {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {}),
                },
            })

    chat_req = {
        "model": req_body.get("model", DEFAULT_MODEL),
        "messages": messages,
        "stream": False,  # 统一用非流式请求 DeepSeek
        "max_tokens": req_body.get("max_output_tokens", 8192),
    }
    if tools:
        chat_req["tools"] = tools
    if "temperature" in req_body:
        chat_req["temperature"] = req_body["temperature"]
    if "top_p" in req_body:
        chat_req["top_p"] = req_body["top_p"]

    return chat_req


def chat_to_responses(chat_resp: dict, req_body: dict) -> dict:
    """Chat Completions 响应 → Responses API 响应"""
    choice = chat_resp.get("choices", [{}])[0]
    message = choice.get("message", {})
    content = message.get("content", "") or ""
    tool_calls = message.get("tool_calls", [])
    finish = choice.get("finish_reason", "stop")

    resp_id = "resp_" + uuid.uuid4().hex[:24]
    msg_id = "msg_" + uuid.uuid4().hex[:24]

    has_tools = len(tool_calls) > 0

    # 构建 output content items
    output_content = []
    if content:
        output_content.append({"type": "output_text", "text": content})
    for tc in tool_calls:
        fn = tc.get("function", {})
        cid = tc.get("id", "call_" + uuid.uuid4().hex[:16])
        output_content.append({
            "type": "function_call",
            "id": cid,
            "call_id": cid,
            "name": fn.get("name", ""),
            "arguments": fn.get("arguments", "{}"),
            "status": "completed",
        })

    usage = chat_resp.get("usage", {})
    return {
        "id": resp_id,
        "object": "response",
        "created": int(time.time()),
        "model": chat_resp.get("model", req_body.get("model", DEFAULT_MODEL)),
        "status": "in_progress" if has_tools else "completed",
        "output": [{
            "type": "message",
            "id": msg_id,
            "role": "assistant",
            "status": "completed",
            "content": output_content,
        }],
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
        # 内部字段（SSE 流式用）
        "_resp_id": resp_id,
        "_msg_id": msg_id,
        "_text": content,
        "_tool_calls": [
            {
                "call_id": tc.get("id", "call_" + uuid.uuid4().hex[:16]),
                "name": tc.get("function", {}).get("name", ""),
                "arguments": tc.get("function", {}).get("arguments", "{}"),
            }
            for tc in tool_calls
        ],
    }


# ============================================================
#  SSE 流式事件构建
# ============================================================

def build_sse_events(resp: dict, req_body: dict) -> list:
    """构建 SSE 事件列表"""
    resp_id = resp.pop("_resp_id", "")
    msg_id = resp.pop("_msg_id", "")
    text = resp.pop("_text", "")
    tool_calls = resp.pop("_tool_calls", [])
    model = req_body.get("model", DEFAULT_MODEL)
    created = resp.get("created", int(time.time()))
    has_tools = len(tool_calls) > 0

    events = []

    # 基础响应对象
    base = {"id": resp_id, "object": "response", "created": created, "model": model}
    in_progress = dict(base, status="in_progress", output=[])

    events.append(("response.created", {"type": "response.created", "response": in_progress}))
    events.append(("response.in_progress", {"type": "response.in_progress", "response": in_progress}))
    events.append(("response.output_item.added", {
        "type": "response.output_item.added",
        "item": {"id": msg_id, "type": "message", "role": "assistant", "content": []},
    }))

    # function call events
    for tc in tool_calls:
        events.append(("response.function_call_arguments.delta", {
            "type": "response.function_call_arguments.delta",
            "delta": tc["arguments"],
            "item_id": msg_id,
            "output_index": 0,
            "call_id": tc["call_id"],
        }))
        events.append(("response.function_call_arguments.done", {
            "type": "response.function_call_arguments.done",
            "item_id": msg_id,
            "output_index": 0,
            "call_id": tc["call_id"],
            "name": tc["name"],
            "arguments": tc["arguments"],
        }))

    # text delta events
    if text:
        events.append(("response.output_text.delta", {
            "type": "response.output_text.delta",
            "delta": text,
            "item_id": msg_id,
            "output_index": 0,
            "content_index": 0,
        }))
        events.append(("response.output_text.done", {
            "type": "response.output_text.done",
            "item_id": msg_id,
            "output_index": 0,
            "content_index": 0,
            "text": text,
        }))

    # completed
    events.append(("response.completed", {
        "type": "response.completed",
        "response": resp,
    }))
    events.append(("", "[DONE]"))

    return events


# ============================================================
#  HTTP 服务器
# ============================================================

class ThreadingProxy(ThreadingMixIn, TCPServer):
    """多线程 HTTP 服务器"""
    allow_reuse_address = True
    daemon_threads = True


class ProxyHandler(BaseHTTPRequestHandler):
    """代理请求处理器"""

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._json(200, {"status": "Codex + DeepSeek proxy running", "version": __import__("codex_deepseek").__version__})
        elif path == "/v1/models":
            self._json(200, {
                "object": "list",
                "data": [
                    {"id": "deepseek-v4-pro", "object": "model"},
                    {"id": "deepseek-v4-flash", "object": "model"},
                    {"id": "deepseek-chat", "object": "model"},
                    {"id": "deepseek-reasoner", "object": "model"},
                ],
            })
        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/v1/responses":
            self._handle()
        else:
            self.send_error(404)

    def _handle(self):
        """处理转发的核心逻辑"""
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            self._json(401, {"error": {"message": "DEEPSEEK_API_KEY not set"}})
            return

        # 读取请求
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        stream = body.get("stream", False)

        try:
            # 翻译请求
            chat_req = responses_to_chat(body)

            # 请求 DeepSeek
            ds_req = Request(
                f"{DEEPSEEK_BASE}/v1/chat/completions",
                data=json.dumps(chat_req).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            with urlopen(ds_req, timeout=180) as ds_resp:
                chat_resp = json.loads(ds_resp.read())

            # 翻译响应
            resp = chat_to_responses(chat_resp, body)

            # 返回
            if stream:
                self._send_stream(resp, body)
            else:
                # 移除内部字段
                for k in ["_resp_id", "_msg_id", "_text", "_tool_calls"]:
                    resp.pop(k, None)
                self._json(200, resp)

        except URLError as e:
            self._json(502, {"error": {"message": f"DeepSeek request failed: {str(e)}"}})
        except json.JSONDecodeError as e:
            self._json(502, {"error": {"message": f"DeepSeek returned invalid JSON: {str(e)}"}})
        except Exception as e:
            self._json(500, {"error": {"message": str(e)}})

    def _send_stream(self, resp: dict, req_body: dict):
        """发送流式 SSE 响应"""
        self.protocol_version = "HTTP/1.1"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        events = build_sse_events(resp, req_body)
        for event, data in events:
            if event:
                self.wfile.write(f"event: {event}\ndata: {json.dumps(data)}\n\n".encode())
            else:
                self.wfile.write(f"data: {data}\n\n".encode())
        self.wfile.flush()

    def _json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, fmt, *args):
        pass  # 安静运行


# ============================================================
#  启动函数
# ============================================================

def run_proxy(host=PROXY_HOST, port=PROXY_PORT):
    """启动代理服务器（阻塞）"""
    server = ThreadingProxy((host, port), ProxyHandler)
    print(f"Codex + DeepSeek proxy listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...", flush=True)
        server.server_close()
