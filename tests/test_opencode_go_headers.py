# -*- coding: utf-8 -*-
"""opencode Zen / Go 网关：自动补 x-opencode-session 头，并还原裸 model id。

背景：opencode 的 Go 网关要求客户端在请求头里带稳定的会话 ID
（https://opencode.ai/docs/go/#where-can-i-use-it），缺失时直接返回
400 MissingSessionID——与 API Key 是否有效无关。桌宠此前只发浏览器头 +
Authorization，所以在 AI 设置里填 opencode Go 的地址必然连不上。

这里锁住三条不变量：
1. 只有 opencode.ai 域名才补这个头，其它 provider 的请求头一个字节都不变；
2. 会话 ID 在同一进程内稳定（服务端用它做路由与 prompt 缓存）；
3. OpenCode 配置写法 `opencode-go/<id>` 在 HTTP 侧还原成裸 `<id>`。
"""
from __future__ import annotations

import json
import urllib.request

from pet.chat import providers as providers_mod
from pet.chat.models import ProviderConfig
from pet.chat.providers import OpenAICompatibleProvider, _normalize_model_id, _opencode_headers

# 注意：不能 `from pet.chat.providers import test_connection`——pytest 会把导入进来的
# test_connection 也当成测试函数收集，然后因为缺 config 参数报 fixture 错误。

OPENCODE_BASE = 'https://opencode.ai/zen/go/v1'
DEEPSEEK_BASE = 'https://api.deepseek.com'


def _config(**overrides) -> ProviderConfig:
    kwargs = dict(
        provider_id='opencode-go',
        name='opencode-go',
        base_url=OPENCODE_BASE,
        chat_path='/v1/chat/completions',
        model='opencode-go/deepseek-v4.1-flash',
        api_key='sk-test-key',
        timeout=5.0,
    )
    kwargs.update(overrides)
    return ProviderConfig(**kwargs)


class _FakeResponse:
    """够用的 urlopen 返回值替身：test_connection 需要上下文管理器 + read()。"""

    status = 200

    def __init__(self, body: bytes = b'{"choices":[]}'):
        self._body = body

    def read(self, n: int = -1) -> bytes:
        return self._body

    def close(self) -> None:
        pass

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc) -> bool:
        return False


def _capture_request(monkeypatch, body: bytes = b'{"choices":[]}') -> dict:
    captured: dict = {}

    def fake_urlopen(request, timeout=None, context=None):
        captured['request'] = request
        return _FakeResponse(body)

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
    return captured


def _headers_of(request) -> dict:
    # urllib 会把头名规范成 Xxx-yyy 的形式，统一小写后再断言
    return {str(k).lower(): v for k, v in request.headers.items()}


def test_opencode_headers_only_for_opencode_host():
    """只有 opencode.ai 域名补会话头；其它服务商不受影响。"""
    assert _opencode_headers(OPENCODE_BASE).get('x-opencode-session')
    assert _opencode_headers('https://opencode.ai/inference/go/openai/v1').get('x-opencode-session')
    assert _opencode_headers(DEEPSEEK_BASE) == {}
    assert _opencode_headers('') == {}


def test_opencode_session_id_is_stable():
    """同一进程内会话 ID 不变（稳定 ID 才能让服务端复用路由/缓存）。"""
    first = _opencode_headers(OPENCODE_BASE)['x-opencode-session']
    second = _opencode_headers(OPENCODE_BASE)['x-opencode-session']
    assert first == second
    assert len(first) >= 8


def test_test_connection_sends_session_header(monkeypatch):
    """「测试连接」也必须带上会话头，否则用户点测试只会看到 400。"""
    captured = _capture_request(monkeypatch)
    ok, message = providers_mod.test_connection(_config())
    assert ok and '200' in message
    headers = _headers_of(captured['request'])
    assert headers['x-opencode-session'] == _opencode_headers(OPENCODE_BASE)['x-opencode-session']
    assert headers['authorization'] == 'Bearer sk-test-key'


def test_model_prefix_stripped_for_opencode(monkeypatch):
    """`opencode-go/deepseek-v4.1-flash` 发出去时必须还原成 `deepseek-v4.1-flash`。"""
    captured = _capture_request(monkeypatch)
    providers_mod.test_connection(_config())
    body = json.loads(captured['request'].data.decode('utf-8'))
    assert body['model'] == 'deepseek-v4.1-flash'


def test_stream_request_sends_session_and_naked_model(monkeypatch):
    """正式对话走 _open()：头与 model 同样要处理。"""
    captured = _capture_request(monkeypatch)
    provider = OpenAICompatibleProvider()
    provider._open(
        {'model': 'opencode-go/kimi-k3', 'messages': [{'role': 'user', 'content': 'hi'}], 'stream': True},
        _config(),
        'text/event-stream',
    )
    headers = _headers_of(captured['request'])
    assert headers['x-opencode-session']
    body = json.loads(captured['request'].data.decode('utf-8'))
    assert body['model'] == 'kimi-k3'


def test_other_provider_untouched(monkeypatch):
    """非 opencode 的 provider：不补头、不改 model（回归护栏）。"""
    captured = _capture_request(monkeypatch)
    providers_mod.test_connection(_config(base_url=DEEPSEEK_BASE, model='deepseek-chat'))
    headers = _headers_of(captured['request'])
    assert 'x-opencode-session' not in headers
    body = json.loads(captured['request'].data.decode('utf-8'))
    assert body['model'] == 'deepseek-chat'


def test_normalize_model_id_is_host_scoped():
    """前缀只在 opencode 域名下剥离，别的服务商就算叫这个名字也不动。"""
    assert _normalize_model_id(OPENCODE_BASE, 'opencode-go/deepseek-v4.1-flash') == 'deepseek-v4.1-flash'
    assert _normalize_model_id(DEEPSEEK_BASE, 'opencode-go/deepseek-v4.1-flash') == 'opencode-go/deepseek-v4.1-flash'
    assert _normalize_model_id(OPENCODE_BASE, 'deepseek-v4.1-flash') == 'deepseek-v4.1-flash'


# ---------------------------------------------------------------------------
# 直连路径（不走 chat/providers）：识图、截图翻译都自己拼请求，必须自己补头。
# 2026-10-27 回归：这两条路径漏了头 → Go 网关 400 MissingSessionID，聊天却正常。
# ---------------------------------------------------------------------------

_VISION_BODY = b'{"choices":[{"message":{"content":"ok"}}]}'


def test_vision_request_sends_session_header_and_naked_model(monkeypatch):
    """「看看屏幕 / 识图」的请求也要带会话头，model 也要还原成裸 id。"""
    from pet import vision as vision_mod

    captured = _capture_request(monkeypatch, _VISION_BODY)
    reply = vision_mod.ask_about_screen(b'\xff\xd8\xff\xd9', 'app', 'sys', _config())
    assert reply == 'ok'
    headers = _headers_of(captured['request'])
    assert headers['x-opencode-session']
    body = json.loads(captured['request'].data.decode('utf-8'))
    assert body['model'] == 'deepseek-v4.1-flash'
    # Go 网关接受 ds 的关思考参数；不关的话 reasoning 会吃掉 4096 预算 → 空回复
    assert body['thinking'] == {'type': 'disabled'}


def test_vision_other_provider_untouched(monkeypatch):
    """非 opencode 的视觉端点：不补头，DeepSeek 视觉模型映射保持原样。"""
    from pet import vision as vision_mod

    captured = _capture_request(monkeypatch, _VISION_BODY)
    vision_mod.ask_about_screen(
        b'\xff\xd8\xff\xd9', 'app', 'sys',
        _config(base_url=DEEPSEEK_BASE, model='deepseek-chat'),
    )
    headers = _headers_of(captured['request'])
    assert 'x-opencode-session' not in headers
    body = json.loads(captured['request'].data.decode('utf-8'))
    assert body['model'] == 'deepseek-v4-flash-vision-exp'


def test_vision_model_mapping_is_host_scoped():
    """`-vision-exp` 只属于 DeepSeek 官方 API；兼容端点必须直接用聊天模型。

    2026-10-27 实测：opencode Go 上 deepseek-v4-flash-vision-exp 已废弃（400），
    而 deepseek-v4.1-flash 本身吃图（返回"蓝色"）。
    """
    from pet import vision as vision_mod

    assert vision_mod.resolve_vision_model(
        _config(base_url=DEEPSEEK_BASE, model='deepseek-v4.1-flash')
    ) == 'deepseek-v4-flash-vision-exp'
    assert vision_mod.resolve_vision_model(
        _config(model='deepseek-v4.1-flash')
    ) == 'deepseek-v4.1-flash'
    assert vision_mod.resolve_vision_model(_config(model='kimi-k3')) == 'kimi-k3'
    # 设置里显式指定视觉模型时永远优先
    assert vision_mod.resolve_vision_model(_config(
        model='deepseek-v4.1-flash', vision_same_as_chat=False, vision_model='glm-5.3-flash',
    )) == 'glm-5.3-flash'


def test_translate_sends_session_header_and_naked_model(monkeypatch):
    """截图翻译走聊天模型直连：同样补头 + 还原 model id。"""
    from pet.screen_capture import translate as translate_mod
    from pet.screen_capture import vision_bridge

    captured = _capture_request(
        monkeypatch,
        json.dumps({'choices': [{'message': {'content': '你好'}}]}, ensure_ascii=False).encode('utf-8'),
    )
    monkeypatch.setattr(vision_bridge, 'resolve_chat_context', lambda _cfg: (_config(), 'sys'))
    assert translate_mod.translate_text('hello', object()) == '你好'
    headers = _headers_of(captured['request'])
    assert headers['x-opencode-session']
    body = json.loads(captured['request'].data.decode('utf-8'))
    assert body['model'] == 'deepseek-v4.1-flash'
