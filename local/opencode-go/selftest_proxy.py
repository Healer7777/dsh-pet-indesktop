#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""opencode_proxy.py 自检：不消耗任何 API 额度。

1) 起一个 mock 上游（模拟 opencode 的 400 MissingSessionID 行为）；
2) 起被测代理，指向 mock；
3) 验证：header 注入、model 前缀剥离、SSE 流式透传、普通 JSON 响应；
4) 最后对真实 opencode 网关发一个假 key 请求，确认 400 -> 401（说明 session 关已过）。
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
MOCK_PORT = 8799
PROXY_PORT = 8798
seen = {"headers": None, "body": None}


class MockUpstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        if not self.headers.get("x-opencode-session"):
            self._err(400, "MissingSessionID", "Request is missing x-opencode-session")
            return
        body = json.dumps({"data": [{"id": "deepseek-v4.1-flash"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        seen["headers"] = dict(self.headers)
        seen["body"] = json.loads(raw.decode("utf-8"))
        if not self.headers.get("x-opencode-session"):
            self._err(400, "MissingSessionID", "Request is missing x-opencode-session")
            return
        if seen["body"].get("model") != "deepseek-v4.1-flash":
            self._err(400, "InvalidModel", f"unexpected model {seen['body'].get('model')!r}")
            return
        if seen["body"].get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for word in ["你", "好", "呀"]:
                ev = "data: " + json.dumps({"choices": [{"delta": {"content": word}}]}, ensure_ascii=False) + "\n\n"
                data = ev.encode()
                self.wfile.write(b"%x\r\n" % len(data) + data + b"\r\n")
                self.wfile.flush()
                time.sleep(0.05)
            done = b"data: [DONE]\n\n"
            self.wfile.write(b"%x\r\n" % len(done) + done + b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        else:
            body = json.dumps({"choices": [{"message": {"role": "assistant", "content": "pong"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def _err(self, code, typ, msg):
        body = json.dumps({"type": "error", "error": {"type": typ, "message": msg}}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def wait_port(port, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.1)
    return False


def post(url, payload, stream):
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "text/event-stream" if stream else "application/json")
    req.add_header("Authorization", "Bearer sk-selftest")
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode("utf-8", "replace")


def main() -> int:
    failures = []

    def check(name, cond, detail=""):
        print(("PASS  " if cond else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
        if not cond:
            failures.append(name)

    mock = ThreadingHTTPServer(("127.0.0.1", MOCK_PORT), MockUpstream)
    mock.daemon_threads = True
    threading.Thread(target=mock.serve_forever, daemon=True).start()

    # 沙箱禁止子进程管道，这里直接把代理模块跑在本进程的线程里
    sys.path.insert(0, str(HERE))
    import opencode_proxy as px

    px._upstream_base = f"http://127.0.0.1:{MOCK_PORT}/v1"
    px._user_agent = px.DEFAULT_UA
    httpd = px.ProxyServer(("127.0.0.1", PROXY_PORT), px.Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        if not wait_port(PROXY_PORT):
            print("代理没起来")
            return 1

        # 1) 流式 + 前缀剥离 + header 注入
        status, text = post(
            f"http://127.0.0.1:{PROXY_PORT}/v1/chat/completions",
            {"model": "opencode-go/deepseek-v4.1-flash", "stream": True,
             "messages": [{"role": "user", "content": "hi"}]},
            stream=True,
        )
        check("流式请求 200", status == 200, str(status))
        check("SSE 三个增量按序到达", text.count("data:") >= 4 and "你好呀" == "".join(
            json.loads(l[5:])["choices"][0]["delta"].get("content", "")
            for l in text.splitlines() if l.startswith("data: {")
        ), text[:80].replace("\n", "\\n"))
        check("注入 x-opencode-session", bool(seen["headers"] and seen["headers"].get("x-opencode-session")),
              (seen["headers"] or {}).get("x-opencode-session", ""))
        check("model 前缀已剥离", (seen["body"] or {}).get("model") == "deepseek-v4.1-flash",
              str((seen["body"] or {}).get("model")))
        check("Authorization 原样透传", (seen["headers"] or {}).get("Authorization") == "Bearer sk-selftest")
        check("用自有 UA 覆盖浏览器 UA", "dsh-pet" in ((seen["headers"] or {}).get("User-Agent") or ""),
              (seen["headers"] or {}).get("User-Agent", ""))

        # 2) 非流式（桌宠「测试连接」走这条）
        status, text = post(
            f"http://127.0.0.1:{PROXY_PORT}/v1/chat/completions",
            {"model": "deepseek-v4.1-flash", "stream": False, "max_tokens": 1,
             "messages": [{"role": "user", "content": "ping"}]},
            stream=False,
        )
        check("非流式 200 且回 pong", status == 200 and "pong" in text, text[:80])

        # 3) /models 透传
        req = urllib.request.Request(f"http://127.0.0.1:{PROXY_PORT}/v1/models")
        with urllib.request.urlopen(req, timeout=10) as r:
            check("/v1/models 透传", r.status == 200 and b"deepseek-v4.1-flash" in r.read())

        # 4) 真实网关：经代理发假 key -> 401（不是 400 MissingSessionID）
        px._upstream_base = "https://opencode.ai/zen/go/v1"
        try:
            post(f"http://127.0.0.1:{PROXY_PORT}/v1/chat/completions",
                 {"model": "opencode-go/deepseek-v4.1-flash", "messages": [{"role": "user", "content": "hi"}],
                  "max_tokens": 4}, stream=False)
            check("真实网关（假 key）返回 401", False, "竟然成功了？")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            check("真实网关（假 key）返回 401 而非 400（session 关已过）", e.code == 401,
                  f"{e.code} {body[:80]}")
    finally:
        httpd.shutdown()
        mock.shutdown()

    print("\n" + ("全部通过" if not failures else f"失败 {len(failures)} 项: {failures}"))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
