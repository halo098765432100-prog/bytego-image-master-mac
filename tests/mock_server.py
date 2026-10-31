"""本地 mock OpenAI 服务：用于离线验证生成、重试、报错与 Agent 工具调用。

用法： python tests/mock_server.py 8765
"""
import base64
import io
import json
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image, ImageDraw

STATE = {"image_attempts": {}, "chat_calls": [], "edits_calls": []}


def make_png(text: str = "Hiliand", size=(512, 512)) -> bytes:
    img = Image.new("RGB", size, (28, 34, 44))
    draw = ImageDraw.Draw(img)
    for y in range(size[1]):
        shade = int(28 + (y / size[1]) * 46)
        draw.line([(0, y), (size[0], y)], fill=(shade, shade + 8, shade + 24))
    draw.ellipse([size[0] * 0.25, size[1] * 0.2, size[0] * 0.75, size[1] * 0.7],
                 fill=(76, 141, 255))
    draw.text((size[0] * 0.32, size[1] * 0.82), text, fill=(231, 236, 243))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.endswith("/models"):
            self._send(200, {"data": [{"id": "gpt-image-2"}, {"id": "gpt-image-1"},
                                       {"id": "gpt-4o"}, {"id": "gpt-5"}]})
        else:
            self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            body = {}

        if self.path.endswith("/images/generations"):
            self._handle_image(body)
        elif self.path.endswith("/images/edits"):
            self._handle_edits(raw)
        elif self.path.endswith("/chat/completions"):
            self._handle_chat(body)
        else:
            self._send(404, {"error": {"message": "not found"}})

    def _handle_edits(self, raw: bytes):
        """multipart 上传参考图（images/edits）。"""
        text = raw.decode("utf-8", "ignore")
        prompt = ""
        match = re.search(r'name="prompt"\r\n\r\n(.*?)\r\n--', text, re.S)
        if match:
            prompt = match.group(1)
        files = re.findall(r'filename="([^"]+)"', text)
        size = "1024x1024"
        match = re.search(r'name="size"\r\n\r\n(.*?)\r\n--', text, re.S)
        if match:
            size = match.group(1)
        STATE["edits_calls"].append({"prompt": prompt, "files": files, "size": size})
        count = 1
        match = re.search(r'name="n"\r\n\r\n(.*?)\r\n--', text, re.S)
        if match:
            try:
                count = int(match.group(1))
            except ValueError:
                count = 1
        self._handle_image({"prompt": prompt, "n": count, "size": size})

    def _handle_image(self, body: dict):
        prompt = str(body.get("prompt", ""))
        count = int(body.get("n", 1) or 1)
        key = prompt[:40]
        attempt = STATE["image_attempts"].get(key, 0) + 1
        STATE["image_attempts"][key] = attempt

        if prompt.startswith("slow"):
            time.sleep(8)
        if prompt.startswith("always_fail"):
            self._send(500, {"error": {"message": "mock upstream exploded",
                                       "type": "server_error", "code": "mock_500"}})
            return
        if prompt.startswith("retry") and attempt < 3:
            self._send(502, {"error": {"message": f"mock bad gateway (attempt {attempt})"}})
            return
        if prompt.startswith("authfail"):
            self._send(401, {"error": {"message": "mock invalid api key"}})
            return

        data = []
        for i in range(count):
            data.append({"b64_json": base64.b64encode(make_png(f"#{attempt}-{i + 1}")).decode()})
        self._send(200, {"created": int(time.time()), "data": data,
                         "usage": {"total_tokens": 42}})

    def _handle_chat(self, body: dict):
        STATE["chat_calls"].append(body)
        stream = bool(body.get("stream"))
        messages = body.get("messages", [])
        last_user = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user = str(msg.get("content", ""))
                break

        if last_user.startswith("tool:cmd"):
            chunk = {"choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "call_1", "type": "function",
                 "function": {"name": "run_command", "arguments": json.dumps(
                     {"command": "echo hiliand-agent-ok"})}}]}}]}
            final = {"choices": [{"delta": {"content": "命令已执行"}}]}
        elif last_user.startswith("tool:gen"):
            chunk = {"choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "call_2", "type": "function",
                 "function": {"name": "generate_image", "arguments": json.dumps(
                     {"prompt": "mock 生成", "size": "1024x1024", "quality": "auto", "count": 1})}}]}}]}
            final = {"choices": [{"delta": {"content": "图片已生成"}}]}
        elif messages and messages[-1].get("role") == "tool":
            chunk = {"choices": [{"delta": {"content": "已经拿到工具结果，"}}]}
            final = {"choices": [{"delta": {"content": "任务完成。"}}]}
        else:
            chunk = {"choices": [{"delta": {"content": "mock 回复：你"}}]}
            final = {"choices": [{"delta": {"content": "好，有什么需要我做的？"}}]}

        if not stream:
            if chunk["choices"][0]["delta"].get("tool_calls"):
                msg = {"role": "assistant", "content": None,
                       "tool_calls": chunk["choices"][0]["delta"]["tool_calls"]}
            else:
                msg = {"role": "assistant", "content": chunk["choices"][0]["delta"]["content"]}
            self._send(200, {"choices": [{"message": msg, "finish_reason": "stop"}]})
            return

        body_out = b""
        for piece in (chunk, final):
            body_out += f"data: {json.dumps(piece)}\n\n".encode("utf-8")
        body_out += b"data: [DONE]\n\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body_out)))
        self.end_headers()
        self.wfile.write(body_out)


def serve(port: int = 8765):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"mock server on http://127.0.0.1:{port}/v1", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
