#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""opencode Go 本地中转代理（配合桌宠 dsh-pet 使用）

背景：opencode Go 网关要求客户端带 `x-opencode-session` 请求头，否则直接
返回 400 MissingSessionID；而桌宠目前只发浏览器头 + Authorization，没有
自定义请求头的能力。本代理在本机环回口接住桌宠的请求，补上该头后再转发。

桌宠「AI 与对话 → 模型与连接」里这样填：
    API 地址 : http://127.0.0.1:8787/v1
    模型     : deepseek-v4.1-flash
               （填 opencode-go/deepseek-v4.1-flash 也可以，代理会自动剥前缀）

用法：
    python opencode_proxy.py                 # 默认监听 127.0.0.1:8787
    python opencode_proxy.py --port 8787 --verbose
    python opencode_proxy.py --status        # 只打印自检信息

说明：
  * 只绑定 127.0.0.1，局域网内其他机器访问不到；
  * 不落盘任何 API Key，Authorization 原样转发；
  * session id 首次生成后存到同目录 .opencode_session，重启保持不变，
    有利于服务端做 prompt 缓存与路由；
  * 流式（SSE）响应逐块透传，不做缓冲，桌宠的逐字输出不受影响。
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import socket
import sys
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_PORT = 8787
DEFAULT_UPSTREAM = "https://opencode.ai/zen/go/v1"
DEFAULT_UA = "dsh-pet/4.4.0 (local-opencode-proxy)"
SESSION_FILE = Path(__file__).resolve().parent / ".opencode_session"
LOG_FILE = Path(__file__).resolve().parent / "opencode_proxy.log"

_upstream_base = DEFAULT_UPSTREAM
_user_agent = DEFAULT_UA
_verbose = False
_log_lock = threading.Lock()


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    # pythonw.exe（无控制台）下 sys.stdout 是 None，直接 print 会抛异常
    if sys.stdout is not None:
        try:
            print(line, flush=True)
        except Exception:
            pass
    try:
        with _log_lock, LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def load_session_id() -> str:
    """稳定的会话 ID：首启生成，之后复用（跨重启保持，利于路由/缓存）。"""
    try:
        sid = SESSION_FILE.read_text(encoding="utf-8").strip()
        if len(sid) >= 8:
            return sid
    except OSError:
        pass
    sid = uuid.uuid4().hex
    try:
        SESSION_FILE.write_text(sid, encoding="utf-8")
    except OSError:
        pass
    return sid


SESSION_ID = load_session_id()


def normalize_model(payload: bytes) -> bytes:
    """把 OpenCode 配置写法 `opencode-go/<id>` 还原成 HTTP 侧裸 model id。"""
    try:
        data = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return payload
    if not isinstance(data, dict):
        return payload
    model = data.get("model")
    if isinstance(model, str) and "/" in model:
        prefix, _, rest = model.partition("/")
        if prefix.strip().lower() == "opencode-go" and rest:
            data["model"] = rest
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return payload


class ProxyServer(ThreadingHTTPServer):
    """Windows 上必须关掉 SO_REUSEADDR：否则同一端口能被绑定两次，
    "已在运行"的判断和开机自启的去重都会失效（连接会随机落到旧实例上）。"""

    allow_reuse_address = False
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "dsh-pet-opencode-proxy/1.0"

    # ---- 基础 ----
    def log_message(self, fmt: str, *args) -> None:  # 静音默认 stderr 噪声
        if _verbose:
            log("HTTP " + (fmt % args))

    def _read_body(self) -> bytes:
        length = self.headers.get("Content-Length")
        if length:
            try:
                return self.rfile.read(int(length))
            except (ValueError, OSError):
                return b""
        return b""

    def _send_json(self, status: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    # ---- 转发 ----
    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        if not path.endswith("/chat/completions"):
            self._send_json(404, {"error": {"message": f"proxy: 不支持的路径 {self.path}"}})
            return

        body = normalize_model(self._read_body())
        up_path = urlparse(_upstream_base).path.rstrip("/") + "/chat/completions"
        self._forward("POST", up_path, body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        if path.endswith("/healthz"):  # 自报家门：开机自启时用来判断"是不是我已经在跑了"
            self._send_json(200, {"ok": True, "proxy": "opencode-proxy", "upstream": _upstream_base})
            return
        if path.endswith("/models"):
            up_path = urlparse(_upstream_base).path.rstrip("/") + "/models"
            self._forward("GET", up_path, b"")
            return
        self._send_json(404, {"error": {"message": f"proxy: 不支持的路径 {self.path}"}})

    def _forward(self, method: str, up_path: str, body: bytes) -> None:
        parsed = urlparse(_upstream_base)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        headers = {
            "x-opencode-session": SESSION_ID,
            "User-Agent": _user_agent,
            "Accept": self.headers.get("Accept") or "application/json",
            "Content-Type": self.headers.get("Content-Type") or "application/json",
        }
        auth = self.headers.get("Authorization")
        if auth:
            headers["Authorization"] = auth

        started = time.time()
        try:
            if parsed.scheme == "https":
                conn = http.client.HTTPSConnection(host, port, timeout=600)
            else:
                conn = http.client.HTTPConnection(host, port, timeout=600)
            conn.request(method, up_path, body=body if method != "GET" else None, headers=headers)
            resp = conn.getresponse()
        except Exception as exc:  # noqa: BLE001 - 任何上游异常都要回给桌宠
            log(f"UPSTREAM-ERROR {type(exc).__name__}: {exc}")
            self._send_json(502, {"error": {"message": f"本地代理连不上 opencode：{exc}"}})
            return

        status = resp.status
        ctype = resp.getheader("Content-Type") or "application/json"
        try:
            if method == "GET":
                data = resp.read()
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)
                self.close_connection = True
                total = len(data)
            else:
                # 流式透传：不缓冲、立即 flush，SSE 增量照常抵达桌宠
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Connection", "close")
                self.end_headers()
                total = 0
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(b"%x\r\n" % len(chunk) + chunk + b"\r\n")
                    self.wfile.flush()
                    total += len(chunk)
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
                self.close_connection = True
            log(f"{method} {up_path} -> {status} ({total}B, {time.time() - started:.2f}s)")
        except (BrokenPipeError, ConnectionResetError):
            log(f"{method} {up_path} -> 客户端提前断开（桌宠取消/关闭）")
        finally:
            try:
                conn.close()
            except Exception:
                pass


def find_free_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def is_our_proxy(port: int, timeout: float = 1.5) -> bool:
    """端口上那个服务是不是本代理（避免开机自启重复拉起时抢占/换端口）。"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=timeout) as resp:
            data = json.loads(resp.read(2048).decode("utf-8", "replace"))
        return isinstance(data, dict) and data.get("proxy") == "opencode-proxy"
    except Exception:
        return False


def main() -> int:
    global _upstream_base, _user_agent, _verbose

    ap = argparse.ArgumentParser(description="opencode Go 本地中转代理")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"监听端口（默认 {DEFAULT_PORT}）")
    ap.add_argument("--upstream", default=DEFAULT_UPSTREAM, help="上游基址（自检时可指向 mock）")
    ap.add_argument("--user-agent", default=DEFAULT_UA, help="转发给 opencode 的 User-Agent")
    ap.add_argument("--verbose", action="store_true", help="打印每个请求的 HTTP 细节")
    ap.add_argument("--auto-port", action="store_true", help="端口被占用时自动换一个空闲端口（默认不换）")
    ap.add_argument("--status", action="store_true", help="只打印配置信息后退出")
    args = ap.parse_args()

    _upstream_base, _user_agent, _verbose = args.upstream.rstrip("/"), args.user_agent, args.verbose

    if args.status:
        print(f"upstream   : {_upstream_base}")
        print(f"session id : {SESSION_ID}")
        print(f"user-agent : {_user_agent}")
        print(f"session 文件: {SESSION_FILE}")
        return 0

    port = args.port
    try:
        httpd = ProxyServer(("127.0.0.1", port), Handler)
    except OSError:
        if is_our_proxy(port):
            log(f"代理已在 {port} 端口运行，无需重复启动。")
            return 0
        if not args.auto_port:
            log(f"端口 {port} 被其它程序占用。请释放该端口，或用 --port 指定别的端口"
                f"（记得同步改桌宠里的 API 地址）。")
            return 1
        port = find_free_port(port)
        log(f"端口 {args.port} 被占用，改用 {port}")
        httpd = ProxyServer(("127.0.0.1", port), Handler)

    httpd.daemon_threads = True
    log(f"opencode 代理已启动: http://127.0.0.1:{port}/v1  ->  {_upstream_base}")
    log(f"桌宠里把 API 地址填: http://127.0.0.1:{port}/v1 ，模型填 deepseek-v4.1-flash")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log("代理已停止")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
