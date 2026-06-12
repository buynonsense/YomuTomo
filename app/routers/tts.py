"""
TTS 路由

POST /api/tts
  body: {"text": "...", "speed": 1.0, "language": "JP"}
  resp: audio/wav 字节流

- 命中磁盘缓存：直接 FileResponse，秒开
- 未命中：调 MeloTTSService 推理，落盘后再 FileResponse
- 推理是阻塞操作，丢到 ThreadPoolExecutor 跑，不阻塞事件循环
- 错误：返回 JSON {success:false, message:...}，HTTP 4xx/5xx
"""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.tts import TTSError, get_tts_service


router = APIRouter(prefix="/api", tags=["TTS"])


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="要合成的文本")
    speed: float = Field(default=None, ge=0.1, le=5.0, description="语速倍率，默认从 settings 读")
    language: Optional[str] = Field(default=None, description="语言代码，默认 JP")


@router.post("/tts", summary="服务端 TTS 合成（MeloTTS）")
async def synthesize_tts(request: Request, payload: TTSRequest = Body(...)):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")
    speed = payload.speed if payload.speed is not None else settings.TTS_DEFAULT_SPEED
    language = (payload.language or settings.TTS_DEFAULT_LANGUAGE).upper()

    service = get_tts_service()
    loop = asyncio.get_running_loop()

    try:
        # 推理是 CPU/GPU bound，丢到默认 executor
        path = await loop.run_in_executor(
            None, service.synthesize_to_file, text, speed, language
        )
    except TTSError as exc:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": str(exc), "error": "tts_failed"},
        )
    except Exception as exc:  # noqa: BLE001
        # 未知错误 → 500，但保留响应体可读
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"TTS 推理失败：{exc}",
                "error": "tts_internal",
            },
        )

    # FileResponse 走 Starlette，会自动加 Content-Length / Accept-Ranges / ETag
    return FileResponse(
        path=path,
        media_type="audio/wav",
        filename=f"tts-{language}.wav",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-TTS-Cache": "hit" if service.get_cached_path(text, speed, language) == path else "miss",
        },
    )
