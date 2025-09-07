import json
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class AIClientError(Exception):
    pass


class AIClient:
    @staticmethod
    def detect_format(api_url: str) -> str:
        low = (api_url or "").lower()
        # common indicators for Google's Gemini / Generative Language API
        if (
            "generativelanguage.googleapis.com" in low
            or ":generatecontent" in low
            or ":generate" in low
            or ":generatemessage" in low
            or "/v1/models/" in low and ":generate" in low
            or "/generativelanguage" in low
        ):
            return "GEMINI"
        return "OPENAI"

    @staticmethod
    def factory(provider: Dict[str, Any]):
        fmt = AIClient.detect_format(provider.get("api_url"))
        if fmt == "GEMINI":
            return GeminiClient(provider)
        return OpenAICompatClient(provider)


class BaseClient:
    def __init__(self, provider: Dict[str, Any]):
        self.provider = provider
        self.api_url = provider.get("api_url")
        self.api_key = provider.get("api_key") or provider.get("api_key_enc")
        self.model = provider.get("model")
        self.extra = provider.get("extra") or {}

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def chat(self, messages: List[Dict[str, str]], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raise NotImplementedError()


class OpenAICompatClient(BaseClient):
    async def chat(self, messages: List[Dict[str, str]], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        body = {
            "model": self.model,
            "messages": messages,
        }
        # merge extras
        merged = {}
        if isinstance(self.extra, dict):
            merged.update(self.extra)
        if extra:
            merged.update(extra)
        merged and body.update(merged)

        base = (self.api_url or '').rstrip('/')
        # Normalize common shapes:
        # - if provider gave a root like https://.../compatible-mode/v1 we should POST to .../v1/chat/completions
        # - if provider already includes /v1/chat/completions use it as-is
        if base.endswith('/v1/chat/completions'):
            full = base
        elif base.endswith('/v1'):
            full = base + '/chat/completions'
        else:
            # default fallback: append full path
            full = base + '/v1/chat/completions'

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                r = await client.post(full, headers=self._headers(), json=body)
                # If provider returns 404 for constructed path, attempt a fallback to the raw base url
                if r.status_code == 404:
                    logger.warning('OpenAICompatClient got 404 for %s, retrying raw api_url %s', full, base)
                    try:
                        fb = await client.post(base, headers=self._headers(), json=body)
                        if fb.status_code >= 200 and fb.status_code < 300:
                            data = fb.json()
                        else:
                            # include both response bodies for debugging
                            txt1 = None
                            txt2 = None
                            try:
                                txt1 = r.text
                            except Exception:
                                txt1 = '<no body>'
                            try:
                                txt2 = fb.text
                            except Exception:
                                txt2 = '<no body>'
                            logger.error('OpenAICompatClient primary(%s) and fallback(%s) failed: %s / %s', full, base, txt1, txt2)
                            fb.raise_for_status()
                    except Exception:
                        # bubble up original r content if fallback also fails
                        try:
                            logger.error('OpenAICompatClient fallback post to %s failed: %s', base, fb.text if 'fb' in locals() else '<no body>')
                        except Exception:
                            pass
                        r.raise_for_status()
                else:
                    try:
                        r.raise_for_status()
                    except Exception:
                        # Log response text to aid debugging (some providers return useful JSON errors)
                        txt = None
                        try:
                            txt = r.text
                        except Exception:
                            txt = '<could not read response body>'
                        logger.error('OpenAICompatClient async chat non-2xx response: %s %s', r.status_code, txt)
                        r.raise_for_status()
                    data = r.json()
                text = None
                if isinstance(data, dict):
                    choices = data.get("choices") or []
                    if choices:
                        delta = choices[0].get("message") or choices[0].get("delta")
                        if delta:
                            if isinstance(delta, dict):
                                text = delta.get("content") or delta.get("content", None)
                        text = text or choices[0].get("text") or choices[0].get("message", {}).get("content")
                return {"text": text or json.dumps(data, ensure_ascii=False), "raw": data}
            except Exception as e:
                logger.exception("OpenAICompatClient async chat failed")
                msg = str(e)
                try:
                    # If this was an httpx HTTPStatusError, include response body for debugging
                    if isinstance(e, httpx.HTTPStatusError) and getattr(e, 'response', None) is not None:
                        resp = e.response
                        req_url = getattr(resp, 'url', None) or full
                        body_text = None
                        try:
                            body_text = resp.text
                        except Exception:
                            body_text = '<could not read response body>'
                        msg = f'HTTP {resp.status_code} at {req_url}: {body_text}'
                except Exception:
                    pass
                raise AIClientError(msg)


class GeminiClient(BaseClient):
    async def chat(self, messages: List[Dict[str, str]], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        base = (self.api_url or '').rstrip('/')
        # Normalize model: if user supplied a short id like 'text-bison', make it 'models/text-bison'
        model_segment = self.model or ''
        try:
            if model_segment and 'models/' not in model_segment:
                model_segment = 'models/' + model_segment
        except Exception:
            pass

        # If base already contains a generateMessage-like path or model path, use it as-is.
        # Don't let the URL scheme (https:) trigger the ':' check — instead check for known path markers.
        # If the provider is Google's generativelanguage host, prefer the generateContent endpoint and payload
        is_google_gl = 'generativelanguage.googleapis.com' in base
        if is_google_gl and model_segment:
            # avoid double 'models/' when building path
            seg = model_segment
            if seg.startswith('models/'): seg = seg[len('models/'):]
            # Use generateContent for Google GL (some SDKs/docs use generateContent)
            full = f"{base}/v1/models/{seg}:generateContent"
        elif model_segment and (':generate' not in base and '/v1/models/' not in base):
            full = f"{base}/v1/{model_segment}:generateMessage"
        else:
            full = base

        # Prepare body depending on provider flavor
        if is_google_gl:
            # Google Generative Language (generateContent) expects:
            # {"contents": [{"role": "user", "parts": [{"text": "..."}, ...]}]}
            try:
                parts = []
                for m in messages:
                    # include all message texts as separate parts
                    parts.append({"text": m.get("content")})
                body = {
                    "contents": [
                        {
                            "role": "user",
                            "parts": parts
                        }
                    ]
                }
            except Exception:
                parts = []
                for m in messages:
                    parts.append({"text": str(m.get("content"))})
                body = {"contents": [{"role": "user", "parts": parts}]}
        else:
            # Google Generative Language expects messages like: {"author": "user", "content": {"text": "..."}}
            try:
                body = {
                    "messages": [{"author": m.get("role", "user"), "content": {"text": m.get("content")}} for m in messages]
                }
            except Exception:
                body = {"messages": [{"author": (m.get("role", "user")), "content": {"text": str(m.get("content"))}} for m in messages]}
        merged = {}
        if isinstance(self.extra, dict):
            merged.update(self.extra)
        if extra:
            merged.update(extra)
        merged and body.update(merged)

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # For Google Generative Language API, many users use API keys instead of OAuth tokens.
                # If the api_url indicates generativelanguage.googleapis.com and the provided api_key
                # looks like an API key (heuristic: does not start with 'ya29.'), send it as query param `key=`.
                params = None
                try:
                    low_base = (base or '').lower()
                    if 'generativelanguage.googleapis.com' in low_base and self.api_key:
                        # heuristic for API key vs OAuth token
                        if not str(self.api_key).startswith('ya29.'):
                            params = {'key': self.api_key}
                except Exception:
                    params = None

                # Build headers: if using Google Generative Language with API key, DO NOT send Authorization header
                headers_local = self._headers()
                if is_google_gl and params:
                    # API key in query param should be used instead of Authorization header
                    headers_local.pop('Authorization', None)

                # Log the final target and request body for debugging
                try:
                    final_url_debug = full + (('?'+ '&'.join([f"{k}={v}" for k,v in params.items()])) if params else '')
                except Exception:
                    final_url_debug = full
                logger.debug('GeminiClient POST %s body=%s headers=%s', final_url_debug, json.dumps(body, ensure_ascii=False), {k: ('<redacted>' if k.lower()=='authorization' else v) for k,v in headers_local.items()})

                r = await client.post(full, headers=headers_local, json=body, params=params)
                if r.status_code == 404:
                    # Try OpenAI-compatible chat completions path as a fallback (some providers support compat layer)
                    try:
                        logger.warning('GeminiClient primary generateMessage returned 404, trying /v1/chat/completions fallback')
                        openai_compat_url = base.rstrip('/') + '/v1/chat/completions'
                        # construct OpenAI-style body
                        oa_body = {"model": self.model, "messages": messages}
                        oa_merged = {}
                        if isinstance(self.extra, dict):
                            oa_merged.update(self.extra)
                        if extra:
                            oa_merged.update(extra)
                        oa_merged and oa_body.update(oa_merged)
                        # For fallback, reuse header policy (remove Authorization if using API key)
                        fb = await client.post(openai_compat_url, headers=headers_local, json=oa_body, params=params)
                        if fb.status_code >= 200 and fb.status_code < 300:
                            data = fb.json()
                            # parse as OpenAI response
                            text = None
                            if isinstance(data, dict):
                                choices = data.get('choices') or []
                                if choices:
                                    delta = choices[0].get('message') or choices[0].get('delta')
                                    if delta and isinstance(delta, dict):
                                        text = delta.get('content') or delta.get('content', None)
                                    text = text or choices[0].get('text') or choices[0].get('message', {}).get('content')
                            return {"text": text or json.dumps(data, ensure_ascii=False), "raw": data}
                        else:
                            logger.error('GeminiClient fallback also failed: %s %s', fb.status_code, fb.text if hasattr(fb, 'text') else str(fb))
                            fb.raise_for_status()
                    except Exception:
                        # re-raise original 404 if fallback fails
                        try:
                            logger.error('GeminiClient fallback post failed: %s', r.text if hasattr(r, 'text') else str(r))
                        except Exception:
                            pass
                        r.raise_for_status()
                else:
                    r.raise_for_status()
                    data = r.json()
                text = None
                if isinstance(data, dict):
                    if "candidates" in data:
                        c = data.get("candidates")
                        if c and isinstance(c, list):
                            first = c[0].get("content") or {}
                            # Common Gemini/GL shape: content.parts -> [{text: ...}, ...]
                            parts = first.get("parts") or []
                            if parts and isinstance(parts, list):
                                try:
                                    text = ''.join([p.get('text', '') for p in parts if isinstance(p, dict)])
                                except Exception:
                                    text = None
                            # fallback: some vendors put text directly
                            if not text:
                                text = first.get("text") or first.get('text', None)
                    if not text:
                        text = json.dumps(data, ensure_ascii=False)
                return {"text": text or "", "raw": data}
            except Exception as e:
                logger.exception("GeminiClient async chat failed")
                msg = str(e)
                try:
                    if isinstance(e, httpx.HTTPStatusError) and getattr(e, 'response', None) is not None:
                        resp = e.response
                        req_url = getattr(resp, 'url', None) or full
                        try:
                            body_text = resp.text
                        except Exception:
                            body_text = '<could not read response body>'
                        msg = f'HTTP {resp.status_code} at {req_url}: {body_text}'
                except Exception:
                    pass
                raise AIClientError(msg)
