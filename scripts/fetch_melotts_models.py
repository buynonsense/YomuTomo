"""Pre-download MeloTTS JP checkpoint + config from HuggingFace.

MeloTTS 0.1.2 hard-codes MyShell S3 URLs in melo.download_utils, but that
public bucket returns 403. We mirror the JP model + config from
myshell-ai/MeloTTS-Japanese on HuggingFace into /app/models/melotts/JP/.
app/services/tts.py patches the URL dicts at import time to point at these
local files so /api/tts never has to hit the S3 bucket.
"""
import os
import time

from huggingface_hub import hf_hub_download


def _download_with_retry(repo: str, fname: str, local_dir: str, *, attempts: int = 4) -> str:
    last_err: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            return hf_hub_download(repo_id=repo, filename=fname, local_dir=local_dir)
        except Exception as exc:  # noqa: BLE001 - any network error worth retrying
            last_err = exc
            wait = min(2 ** i, 30)
            print(f"hf download {fname} attempt {i}/{attempts} failed: {exc}; retry in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"failed to download {fname} from {repo} after {attempts} attempts: {last_err}")


def main() -> None:
    repo = os.environ.get("MELOTTS_HF_REPO_JP", "myshell-ai/MeloTTS-Japanese")
    out_dir = os.environ.get("MELOTTS_LOCAL_MODEL_DIR", "/app/models/melotts/JP")
    os.makedirs(out_dir, exist_ok=True)
    for fname in ("checkpoint.pth", "config.json"):
        path = _download_with_retry(repo, fname, out_dir)
        print(f"pulled {fname} -> {path}")


if __name__ == "__main__":
    main()
