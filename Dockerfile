# syntax=docker/dockerfile:1
# Multi-stage (optional future) single-stage simple production image for FastAPI app

# 3.10 是为了拿到 torch 1.13.x 的 CPU wheel（3.11 已不提供）
ARG PYTHON_VERSION=3.10
FROM python:${PYTHON_VERSION}-slim AS runtime

# Prevent prompts / speed up installs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps for building some wheels (e.g. pyaudio needs portaudio)
# git 用来 pip install melotts @ git+https://...
RUN apt-get update \
     && apt-get install -y --no-install-recommends \
         build-essential \
         git \
         portaudio19-dev \
         curl \
         ca-certificates \
         tzdata \
     && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only requirements first for better layer caching
COPY requirements.txt ./
# 先装常规依赖（torch/unidic 等）。MeloTTS 因为 setup.py 用了废弃的 pip.req，
# 不能在 PEP 517 隔离构建里装，所以这里不放进 requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# 单独装 MeloTTS：clone 源码后 patch setup.py（用 packaging 替代已废弃的 pip.req），
# 然后 --no-build-isolation 安装
COPY scripts/patch_melotts_setup.py /tmp/patch_melotts_setup.py
RUN git clone --depth 1 --branch v0.1.2 https://github.com/myshell-ai/MeloTTS.git /tmp/melotts \
 && cd /tmp/melotts \
 && python /tmp/patch_melotts_setup.py \
 && pip install --no-build-isolation /tmp/melotts \
 && python -c "import melo; print('melo import ok')" \
 && rm -rf /tmp/melotts /tmp/patch_melotts_setup.py

# 预下载 MeloTTS 启动所需的 nltk 数据（cmudict 等）
# 不预下载的话 /api/tts 首次请求会卡 30s+ 还要过外网，不稳定
# 装到 /usr/local/share/nltk_data（nltk 搜索路径之一），所有用户可读
RUN mkdir -p /usr/local/share/nltk_data \
 && python -m nltk.downloader -d /usr/local/share/nltk_data cmudict averaged_perceptron_tagger \
 && python -c "import nltk, os; nltk.data.path.insert(0, '/usr/local/share/nltk_data'); nltk.data.find('corpora/cmudict'); print('nltk cmudict ok')"

# 预下载 MeloTTS JP checkpoint + config（v0.1.2 默认从 myshell S3 拉，但公桶 403）
# 改从 Hugging Face 镜像拉（myshell-ai/MeloTTS-Japanese），落到 /app/models/melotts/JP/
# app/services/tts.py 启动时会探测到这里并把 download_utils 里的 URL 改成 file://
# 后续 /api/tts 首次请求就能直接读本地，不再访问外网
ARG MELOTTS_HF_REPO_JP=myshell-ai/MeloTTS-Japanese
ENV MELOTTS_HF_REPO_JP=${MELOTTS_HF_REPO_JP}
COPY scripts/fetch_melotts_models.py /tmp/fetch_melotts_models.py
RUN python /tmp/fetch_melotts_models.py && rm /tmp/fetch_melotts_models.py

# 下载 UniDic 字典（日语分词 + 读音预测，MeloTTS 必需）
# 默认装到 /app/.unidic 避免污染系统目录
RUN python -m unidic download \
 && python -c "import unidic; print('unidic ok at', unidic.DICDIR)"

# Copy application source
COPY . .

# Create non-root user
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 3434

# Environment (override OPENAI_API_KEY at runtime: -e OPENAI_API_KEY=sk-xxx)
ENV OPENAI_API_KEY="" \
    OPENAI_MODEL="" \
    PYTHONPATH="/app"

# Default command (no reload in container; mount source + override CMD for dev if needed)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3434"]

# For development (example):
# docker build -t yomu-dev --build-arg PYTHON_VERSION=3.11 .
# docker run -it --rm -p 8000:8000 -e OPENAI_API_KEY=your_key -v %cd%:/app yomu-dev \
#   uvicorn app:app --host 0.0.0.0 --port 3434 --reload
