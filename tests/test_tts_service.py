"""
TTS 服务单元测试

不依赖 MeloTTS 真模型：通过 monkeypatch 替换 `melo.api.TTS` 让服务只走 mock 路径，
重点验证：
- 缓存 key 一致性
- 命中/未命中行为
- 单例 + 懒加载
- TTS 端到端（POST /api/tts）
"""

from __future__ import annotations

import os
import tempfile
import types

import pytest


@pytest.fixture()
def tts_cache_dir(monkeypatch, tmp_path):
    """每个测试用独立缓存目录。"""
    monkeypatch.setenv("TTS_CACHE_DIR", str(tmp_path))
    # 配置被读一次，必须在 import 前注入。已 import 过的 settings 实例不会刷新，
    # 所以我们直接 monkeypatch 实例字段。
    from app.core import config as cfg
    monkeypatch.setattr(cfg.settings, "TTS_CACHE_DIR", str(tmp_path))
    return tmp_path


def _install_mock_melotts(monkeypatch, calls):
    """向 app.services.tts 注入一个假的 melotts。"""
    import app.services.tts as tts_module

    class FakeTTSModel:
        def __init__(self, language, device):
            self.language = language
            self.device = device
            # service 期望 instance.model 是真正的 nn.Module
            # 这里给个 FakeInner 站位即可（量化已 patch 成 no-op）
            self.model = types.SimpleNamespace(named_parameters=lambda: [], state_dict=lambda: {})
            self.hps = types.SimpleNamespace(
                data=types.SimpleNamespace(spk2id={language: 0})
            )

        def tts_to_file(self, text, spk_id, path, speed):
            calls.append({"text": text, "spk_id": spk_id, "path": path, "speed": speed})
            # 写一点内容到目标文件，模拟生成的 WAV
            with open(path, "wb") as f:
                f.write(b"RIFF" + b"\x00" * 36)

    fake_module = types.SimpleNamespace(api=types.SimpleNamespace(TTS=FakeTTSModel))
    monkeypatch.setattr(tts_module, "_MeloTTS", FakeTTSModel)
    monkeypatch.setattr(tts_module, "_MELOTTS_IMPORT_ERROR", None)

    # 量化在测试里是 no-op：环境无 torch，且 mock 没有真模块结构
    # 注意：_maybe_quantize / _try_load_int8_sidecar 是类方法，要 patch 到类上
    monkeypatch.setattr(tts_module, "_has_cuda", lambda: False)
    monkeypatch.setattr(
        tts_module.MeloTTSService,
        "_maybe_quantize",
        lambda self, model, language: None,
    )
    monkeypatch.setattr(
        tts_module.MeloTTSService,
        "_try_load_int8_sidecar",
        lambda self, model, language: False,
    )
    return FakeTTSModel


def test_cache_key_changes_with_text_speed_language():
    from app.services.tts import MeloTTSService
    base = MeloTTSService.cache_key("hello", 1.0, "JP")
    same = MeloTTSService.cache_key("hello", 1.0, "JP")
    assert base == same
    assert MeloTTSService.cache_key("hello", 1.5, "JP") != base
    assert MeloTTSService.cache_key("hello", 1.0, "EN") != base
    assert MeloTTSService.cache_key("world", 1.0, "JP") != base


def test_synthesize_writes_file_and_caches(monkeypatch, tts_cache_dir):
    import app.services.tts as tts_module
    calls = []
    _install_mock_melotts(monkeypatch, calls)

    # 清掉单例（不同测试之间不能复用旧实例）
    tts_module.MeloTTSService._instance = None
    service = tts_module.MeloTTSService()

    path1 = service.synthesize_to_file("こんにちは", 1.0, "JP")
    assert os.path.exists(path1)
    assert len(calls) == 1

    # 第二次相同输入应直接命中缓存，不再调模型
    path2 = service.synthesize_to_file("こんにちは", 1.0, "JP")
    assert path1 == path2
    assert len(calls) == 1


def test_synthesize_speed_clamped(monkeypatch, tts_cache_dir):
    import app.services.tts as tts_module
    calls = []
    _install_mock_melotts(monkeypatch, calls)

    tts_module.MeloTTSService._instance = None
    service = tts_module.MeloTTSService()

    service.synthesize_to_file("a", 0.0, "JP")   # 太慢 → clamp 到 0.1
    service.synthesize_to_file("b", 999.0, "JP")  # 太快 → clamp 到 5.0
    assert calls[0]["speed"] == 0.1
    assert calls[1]["speed"] == 5.0


def test_synthesize_empty_text_raises(monkeypatch, tts_cache_dir):
    import app.services.tts as tts_module
    _install_mock_melotts(monkeypatch, [])

    tts_module.MeloTTSService._instance = None
    service = tts_module.MeloTTSService()
    with pytest.raises(tts_module.TTSError):
        service.synthesize_to_file("   ", 1.0, "JP")


def test_singleton_returns_same_instance(monkeypatch, tts_cache_dir):
    import app.services.tts as tts_module
    tts_module.MeloTTSService._instance = None
    a = tts_module.get_tts_service()
    b = tts_module.get_tts_service()
    assert a is b


def test_api_tts_returns_wav_bytes(monkeypatch, tts_cache_dir, db_session):
    """POST /api/tts 端到端：返回 audio/wav，body 是真实 WAV 字节。"""
    import app.services.tts as tts_module
    calls = []
    _install_mock_melotts(monkeypatch, calls)
    tts_module.MeloTTSService._instance = None

    from app.db import get_db
    from app import main as app_main
    from fastapi.testclient import TestClient

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app_main.app.dependency_overrides[get_db] = override_get_db
    with TestClient(app_main.app) as client:
        resp = client.post("/api/tts", json={"text": "こんにちは", "speed": 1.0, "language": "JP"})
    app_main.app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("audio/wav")
    assert resp.content[:4] == b"RIFF"  # 假 WAV 头
    assert len(calls) == 1


def test_api_tts_empty_text_422(monkeypatch, tts_cache_dir, db_session):
    """空 text 被 Pydantic 拦截 → 422 Validation Error。"""
    import app.services.tts as tts_module
    _install_mock_melotts(monkeypatch, [])
    tts_module.MeloTTSService._instance = None

    from app.db import get_db
    from app import main as app_main
    from fastapi.testclient import TestClient

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app_main.app.dependency_overrides[get_db] = override_get_db
    with TestClient(app_main.app) as client:
        resp = client.post("/api/tts", json={"text": ""})
    app_main.app.dependency_overrides.clear()

    # Pydantic min_length=1 直接拦在 router 之前
    assert resp.status_code == 422
