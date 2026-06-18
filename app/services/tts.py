"""
MeloTTS 服务封装

设计要点：
- 懒加载模型：首次 /api/tts 请求时从 HuggingFace 下载 JP checkpoint（30-60s），
  之后常驻进程内存；启动期不阻塞 ready
- 磁盘 hash 缓存：相同 (text, speed, language) 复用 WAV，避免重复推理
- 线程安全：MeloTTS 模型对象不是并发安全的，所有推理串行化（_infer_lock）
- 软依赖：MeloTTS 包未安装时不抛 ImportError，启动时仅打 warning，
  真正调用 synthesize 时再 TTSError
"""

from __future__ import annotations

import hashlib
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings

BEIJING = timezone(timedelta(hours=8))


def _log(message: str, level: str = "INFO") -> None:
    ts = datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {message}")


try:
    from melo.api import TTS as _MeloTTS

    _MELOTTS_IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # noqa: BLE001 - import-time guard
    _MeloTTS = None
    _MELOTTS_IMPORT_ERROR = exc
    _log(f"[TTS] MeloTTS 未安装：{exc}", level="WARN")


# ---- MeloTTS 模型来源补丁 -----------------------------------------------
# MeloTTS 0.1.2 把 checkpoint / config 的 URL 硬编码在 melo.download_utils 里
# （myshell S3 公桶），但那个桶 403 了。我们改在 Dockerfile 里从 HuggingFace 预下
# 到 /app/models/melotts/<LANG>/{checkpoint.pth,config.json}，这里启动时探测到本地
# 文件就把对应的 URL 替换成 file://，避免首次请求再走外网。
_LOCAL_MODEL_ROOT = os.getenv("MELOTTS_LOCAL_MODEL_DIR", "/app/models/melotts")


def _patch_melotts_urls() -> None:
    if _MeloTTS is None:
        return
    if not os.path.isdir(_LOCAL_MODEL_ROOT):
        return
    try:
        from melo import download_utils
    except Exception as exc:  # noqa: BLE001
        _log(f"[TTS] 无法 patch melo.download_utils：{exc}", level="WARN")
        return

    patched = 0
    for lang, _ in list(download_utils.DOWNLOAD_CKPT_URLS.items()):
        local = os.path.join(_LOCAL_MODEL_ROOT, lang, "checkpoint.pth")
        if os.path.exists(local):
            download_utils.DOWNLOAD_CKPT_URLS[lang] = f"file://{local}"
            patched += 1
    for lang, _ in list(download_utils.DOWNLOAD_CONFIG_URLS.items()):
        local = os.path.join(_LOCAL_MODEL_ROOT, lang, "config.json")
        if os.path.exists(local):
            download_utils.DOWNLOAD_CONFIG_URLS[lang] = f"file://{local}"
            patched += 1
    if patched:
        _log(f"[TTS] 已将 {patched // 2} 个 MeloTTS 模型 URL 改写为本地 file://")


_patch_melotts_urls()


def _has_cuda() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001
        return False


def _pick_quantized_engine() -> str | None:
    """选一个当前平台可用的 qengine。

    Mac / ARM 默认 qnnpack；x86 默认 fbgemm（性能更好）。两者都不行就返回 None。
    `quantize_dynamic` 之前必须先设置，否则 `linear_prepack` 没有注册算子。
    """
    try:
        import torch
    except Exception:  # noqa: BLE001
        return None
    candidates = ("qnnpack", "fbgemm")
    for eng in candidates:
        try:
            torch.backends.quantized.engine = eng
            return eng
        except Exception:  # noqa: BLE001
            continue
    return None


class TTSError(Exception):
    """对外暴露的 TTS 错误。"""


class MeloTTSService:
    """进程内单例。多线程下通过 _infer_lock 串行化推理避免 torch 并发坑。"""

    _instance: Optional["MeloTTSService"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "MeloTTSService":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._initialized = False
                    cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._models: dict[str, "_MeloTTS"] = {}
        self._model_lock = threading.Lock()
        self._infer_lock = threading.Lock()
        self._device = settings.TTS_DEVICE
        os.makedirs(settings.TTS_CACHE_DIR, exist_ok=True)
        _log(
            f"[TTS] MeloTTSService ready. cache_dir={settings.TTS_CACHE_DIR} "
            f"device={self._device} default_lang={settings.TTS_DEFAULT_LANGUAGE} "
            f"preload={settings.TTS_PRELOAD_ON_STARTUP}"
        )

    # ---- 模型管理 ---------------------------------------------------------

    def _maybe_quantize(self, model: "_MeloTTS", language: str) -> None:
        """对模型的 Linear 层做 int8 动态量化。CPU 推理内存 ~4x↓、速度 2-3x↑。

        只在 device == 'cpu' 或 'auto' 落到 cpu 时做（GPU 上量化是反效果）。
        量化后保存 sidecar 状态文件，下次启动直接 load int8，跳过 fp32 加载。
        """
        device = self._device
        # auto 在 melo 内部探测；这里按设置粗判，是 cpu 或 auto 走量化
        is_cpu_path = device == "cpu" or (device == "auto" and not _has_cuda())
        if not is_cpu_path:
            _log(f"[TTS] 跳过 int8 量化 device={device}（GPU 量化收益为负）")
            return

        try:
            import torch  # noqa: F401
            from torch.quantization import quantize_dynamic  # type: ignore
        except Exception as exc:  # noqa: BLE001
            _log(f"[TTS] 量化模块不可用，跳过：{exc}", level="WARN")
            return

        engine = _pick_quantized_engine()
        if engine is None:
            _log(
                "[TTS] 没有任何 qengine 可用（qnnpack/fbgemm 均不支持），跳过量化",
                level="WARN",
            )
            return

        _log(
            f"[TTS] 应用 int8 动态量化 language={language} qengine={engine}（Linear → qint8）"
        )
        # MeloTTS TTS 实例内部真正的 nn.Module 是 model.model
        target = getattr(model, "model", model)
        before_params = sum(p.numel() for p in target.parameters())
        quantize_dynamic(target, {torch.nn.Linear}, dtype=torch.qint8, inplace=True)
        after_params = sum(p.numel() for p in target.parameters())
        _log(
            f"[TTS] 量化完成 params {before_params/1e6:.1f}M → {after_params/1e6:.1f}M "
            f"（未量化部分保持 fp32）"
        )

        # 落盘 sidecar：下次直接 load int8 state_dict
        try:
            sidecar = self._int8_path(language)
            os.makedirs(os.path.dirname(sidecar), exist_ok=True)
            torch.save(target.state_dict(), sidecar)
            _log(f"[TTS] 量化 state_dict 已缓存 sidecar={sidecar}")
        except Exception as exc:  # noqa: BLE001
            _log(f"[TTS] 量化 state_dict 落盘失败：{exc}", level="WARN")

    def _int8_path(self, language: str) -> str:
        root = os.getenv("MELOTTS_LOCAL_MODEL_DIR", "/app/models/melotts")
        return os.path.join(root, "int8", f"{language}_int8.pt")

    def _try_load_int8_sidecar(self, model: "_MeloTTS", language: str) -> bool:
        """如果有 sidecar 量化 state_dict，先 fp32 构建结构，再加载 int8 权重。

        跳过 fp32 checkpoint 的 torch.load，省 199MB 磁盘读 + 反序列化时间。
        """
        import torch

        sidecar = self._int8_path(language)
        if not os.path.exists(sidecar):
            return False
        try:
            import torch
            from torch.quantization import quantize_dynamic  # type: ignore

            # 必须先设 qengine，否则 linear_prepack 没注册算子
            if _pick_quantized_engine() is None:
                return False
            target = getattr(model, "model", model)
            quantize_dynamic(target, {torch.nn.Linear}, dtype=torch.qint8, inplace=True)
            state = torch.load(sidecar, map_location="cpu")
            target.load_state_dict(state, strict=False)
            _log(f"[TTS] 已从 sidecar 直接加载 int8 模型 sidecar={sidecar}")
            return True
        except Exception as exc:  # noqa: BLE001
            _log(f"[TTS] sidecar 加载失败，回退 fp32：{exc}", level="WARN")
            return False

    def _load_model(self, language: str) -> "_MeloTTS":
        if _MeloTTS is None:
            raise TTSError(
                f"MeloTTS 未安装或导入失败：{_MELOTTS_IMPORT_ERROR}。"
                "请检查 requirements.txt / Dockerfile 是否包含 melotts。"
            )
        with self._model_lock:
            model = self._models.get(language)
            if model is not None:
                return model
            _log(
                f"[TTS] 加载 MeloTTS 模型 language={language} device={self._device}（首次约 30-60s）"
            )
            # 先按 melo 内部流程构建/反序列化 checkpoint
            model = _MeloTTS(language=language, device=self._device)
            # 优先用 sidecar 走 int8 路径；没有就现量化、然后落盘
            if not self._try_load_int8_sidecar(model, language):
                self._maybe_quantize(model, language)
            self._models[language] = model
            _log(f"[TTS] 模型就绪 language={language}")
            return model

    def preload(self, language: Optional[str] = None) -> None:
        """预热模型（建议在后台线程调用）。失败仅打 warning，不抛。"""
        lang = language or settings.TTS_DEFAULT_LANGUAGE
        try:
            self._load_model(lang)
        except Exception as exc:  # noqa: BLE001
            _log(f"[TTS] 预热失败 language={lang}：{exc}", level="WARN")

    # ---- 缓存 key ---------------------------------------------------------

    @staticmethod
    def cache_key(text: str, speed: float, language: str) -> str:
        raw = f"{language}|{speed:.3f}|{text}".encode("utf-8")
        return hashlib.sha1(raw).hexdigest()

    def _cache_path(self, key: str) -> str:
        return os.path.join(settings.TTS_CACHE_DIR, f"{key}.wav")

    def get_cached_path(self, text: str, speed: float, language: str) -> Optional[str]:
        key = self.cache_key(text, speed, language)
        path = self._cache_path(key)
        return path if os.path.exists(path) else None

    # ---- 推理 -------------------------------------------------------------

    def synthesize_to_file(
        self,
        text: str,
        speed: float = 1.0,
        language: Optional[str] = None,
    ) -> str:
        """合成音频并写入缓存文件，返回文件绝对路径。命中缓存则直接返回。"""
        text = (text or "").strip()
        if not text:
            raise TTSError("text 不能为空")
        # 限制 speed 范围，避免非法值打到 MeloTTS
        try:
            speed = float(speed)
        except (TypeError, ValueError):
            speed = 1.0
        speed = max(0.1, min(speed, 5.0))
        language = language or settings.TTS_DEFAULT_LANGUAGE

        key = self.cache_key(text, speed, language)
        path = self._cache_path(key)
        if os.path.exists(path):
            _log(f"[TTS] cache hit key={key[:10]} text_len={len(text)} speed={speed}")
            return path

        model = self._load_model(language)
        speaker_ids = model.hps.data.spk2id
        if language not in speaker_ids:
            raise TTSError(
                f"language={language} 暂不支持，可选：{list(speaker_ids.keys())}"
            )
        spk_id = speaker_ids[language]

        _log(
            f"[TTS] synthesize key={key[:10]} text_len={len(text)} speed={speed} lang={language}"
        )
        # 串行化推理：MeloTTS / torch 不是并发安全的
        with self._infer_lock:
            model.tts_to_file(text, spk_id, path, speed=speed)

        if not os.path.exists(path):
            raise TTSError("MeloTTS 未生成音频文件，请检查输入文本是否合法")
        _log(f"[TTS] done key={key[:10]} path={path}")
        return path


def get_tts_service() -> MeloTTSService:
    return MeloTTSService()
