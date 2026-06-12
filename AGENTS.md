# YomuTomo — Agent 指南

## 技术栈

- **框架**: FastAPI + Jinja2 模板 (服务端渲染, 非 SPA)
- **数据库**: PostgreSQL, SQLAlchemy ORM, Alembic 迁移
- **前端**: 原生 JS, 零前端框架
- **AI**: OpenAI 兼容接口 + Gemini, 自定义异步客户端 (`app/services/ai_client_async.py`)

## 架构要点

| 路径 | 说明 |
|------|------|
| `app/main.py` | 应用入口 (uvicorn 目标) |
| `app.py` | 兼容入口, 仅转发到 `app.main` |
| `app/core/config.py` | `Settings` 类, 从环境变量读取 |
| `app/db.py` | Engine / SessionLocal / Base |
| `app/model/models.py` | User / Article / CrawlTask / Notification |
| `app/services/services.py` | 注音/翻译/生词/标题/评分 + 密码哈希 |
| `app/services/notifications.py` | 统一通知中心: 创建/查询/已读/未读统计 |
| `app/services/ai_client_async.py` | AIClient 工厂 (OpenAI 兼容 / Gemini) |
| `app/routers/` | 路由: pages, auth, articles, evaluation, notifications |
| `templates/` | Jinja2 模板 (8 个主要 html + partials) |
| `static/js/modules/` | 前端 JS 模块 (speech-recognition, pdf-export, text-highlight, ai-config, notifications) |
| `static/css/components/` | CSS 组件 (buttons, forms, layout, modal-animations, common) |
| `spider/rsshub_spider.py` | RSSHub 订阅源抓取、预览与文章生成编排 |

## 关键命令

```bash
make install       # pip install -r requirements.txt
make dev           # uvicorn app.main:app --reload (127.0.0.1:8000)
make test          # pytest
make lint          # flake8 app/ && black --check app/ && isort --check-only app/
make format        # black app/ && isort app/
make up            # docker-compose up -d (开发)
make deploy        # docker-compose -f docker-compose.prod.yml up -d (生产)

alembic upgrade head                    # 应用迁移
alembic revision --autogenerate -m "msg"  # 生成迁移
alembic upgrade heads                   # 当存在多个 migration head 时应用全部分支头
alembic stamp heads                     # 旧数据库已具备表结构但缺少 alembic_version 时，用于标记当前版本
```

## 启动方式

```bash
# 直接启动 (开发)
python -m uvicorn app.main:app --reload

# Docker (开发)
make up

# Docker (生产)
make deploy  # 或 docker-compose -f docker-compose.prod.yml up -d
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `postgresql://postgres:1234@localhost:5432/yomu_pg` | 数据库连接 |
| `OPENAI_API_KEY` | — | AI 接口密钥 |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | AI 接口地址 |
| `OPENAI_MODEL` | — | AI 模型名 |
| `SECRET_KEY` | `dev-secret-key-change-me` | 会话密钥 |
| `FURIGANA_MODE` | `hybrid` | 注音模式: `kakasi` / `hybrid` / `ai` |
| `DB_CONNECT_RETRIES` | `10` | 启动时 DB 连接重试次数 |
| `DB_CONNECT_DELAY` | `3` | 重试间隔(秒) |
| `TTS_DEVICE` | `auto` | MeloTTS 推理设备: `auto` / `cpu` / `cuda` / `mps` |
| `TTS_DEFAULT_LANGUAGE` | `JP` | 服务端 TTS 默认语言 |
| `TTS_DEFAULT_SPEED` | `1.0` | 服务端 TTS 默认语速 |
| `TTS_CACHE_DIR` | `/app/static/audio_cache` | 合成 WAV 磁盘缓存根目录 |
| `TTS_PRELOAD_ON_STARTUP` | `false` | 启动时是否预热模型（首次 /api/tts 推理 30-60s） |

## AI 配置优先级

请求头 > 表单字段 > 用户 DB 配置 > 环境变量

- `X-API-Key` / `X-Base-URL` / `X-Model` 请求头可临时覆盖
- 用户 AI 配置存于 `users` 表的 `openai_api_key` / `openai_base_url` / `openai_model` 字段
- 保存配置会自动调用 `AIClient.chat()` 验证有效性

## 通知中心

- 通知中心是全站统一能力，按用户落库并支持跨设备同步
- 导航栏右侧的铃铛按钮是通知入口，未读数由数据库统计
- 通知面板打开后会自动把当前用户未读通知标记为已读
- 统一通知服务在 `app/services/notifications.py`
- 通知路由在 `app/routers/notifications.py`
- 常见通知来源：
  - 新闻生成成功 / 失败
  - 首页文章生成成功 / 失败
  - AI 配置保存成功 / 验证失败
  - 全局系统报错
- 通知点击后优先跳转到对应页面；文章类通知会附带页面高亮/定位参数

## 注音模式

- **kakasi**: 仅 pykakasi, 最快但可能不准
- **hybrid**: (默认) kakasi 初注 → AI 校对, 推荐
- **ai**: 完全 AI 生成, 最准确但最慢/最贵

## TTS（服务端文字转语音）

使用 [MeloTTS](https://github.com/myshell-ai/MeloTTS) 作为后端，浏览器不再依赖 Web Speech API（不同浏览器日语音质差异大、Chrome 限流等）。

- 服务封装在 `app/services/tts.py`：`MeloTTSService` 单例 + 懒加载 + 磁盘 hash 缓存
- 路由在 `app/routers/tts.py`：`POST /api/tts`，body `{text, speed?, language?}`，返回 `audio/wav`
- 缓存 key = `sha1(language|speed|text)`，WAV 文件落在 `TTS_CACHE_DIR`
- 命中缓存秒开；首次合成要 30-60s（MeloTTS 模型加载 + UniDic + checkpoint）
- 默认不预热（避免阻塞启动）；要加速首请求可开 `TTS_PRELOAD_ON_STARTUP=true`
- 前端 `static/js/pages/reading.js`：`fetch('/api/tts')` + `HTMLAudioElement` 播放
  - 词高亮：没有 word boundary 事件，按 `audio.currentTime / duration × totalChars` 比例映射到 `wordRanges`
  - 旧 `speechSynthesis` 路径、`speechSupported` 探测分支已删除
- 构建相关：`requirements.txt` 用 `melotts @ git+https://github.com/myshell-ai/MeloTTS.git@v0.1.2`，
  并显式 pin `torch / numpy / scipy / unidic`；`Dockerfile` 加 `git` + `python -m unidic download`

### int8 动态量化（省内存 + 二次启动加速）

CPU 路径上自动对 `nn.Linear` 做 int8 动态量化（`torch.quantization.quantize_dynamic`），并把量化后 state_dict 落到 `$MELOTTS_LOCAL_MODEL_DIR/int8/<lang>_int8.pt` 做 sidecar：

- 首次：fp32 checkpoint 反序列化 → 量化 → 推理 → 落盘。耗时与无量化基本相同
- 二次：`TTS(lang)` 快速构建空骨架 → `quantize_dynamic` 替换 Linear → `load_state_dict` 灌入 int8。**跳过 fp32 checkpoint load，省 25-30s**
- 内存：MeloTTS 主体是 Conv1d，Linear 量化只覆盖少部分参数，内存下降 ~20%（1.67GB→1.30GB）
- qengine：Mac/ARM 自动选 `qnnpack`；x86 选 `fbgemm`。两个都没有就 WARN 跳过（PyTorch 1.13 在 Mac 上 `fbgemm` 不支持，所以 `qnnpack` 兜底）
- 量化前后会自动设置 `torch.backends.quantized.engine`，否则 `linear_prepack` 算子未注册
- 关闭量化：删 `int8/` 目录下的 sidecar 即可（下次启动会重新生成 fp32 模型，不走量化）

### MeloTTS 模型镜像

MeloTTS 0.1.2 把 base speaker 的 `checkpoint.pth` / `config.json` URL 硬编码在 `melo.download_utils` 里（MyShell S3 公桶）。该公桶 2025 年开始频繁 403，Docker 镜像里我们改走 HuggingFace 镜像：

- 构建期：`scripts/fetch_melotts_models.py` 走 `huggingface_hub.hf_hub_download` 拉 `myshell-ai/MeloTTS-Japanese` 的 `checkpoint.pth` + `config.json` 到 `/app/models/melotts/JP/`
- 启动期：`app/services/tts.py` 探测到本地文件后 `monkey-patch` `melo.download_utils.DOWNLOAD_CKPT_URLS` / `DOWNLOAD_CONFIG_URLS`，把对应语言换成 `file://` 路径
- `MELOTTS_HF_REPO_JP` / `MELOTTS_LOCAL_MODEL_DIR` 两个环境变量可覆盖镜像仓库与本地目录

## 数据库迁移

- 启动时 `app/main.py:on_startup()` 会自动 `Base.metadata.create_all(bind=engine)` (兼容旧行为)
- **正式迁移必须走 Alembic**: `alembic revision --autogenerate -m "msg"` + `alembic upgrade head`
- 已有迁移文件在 `alembic/versions/`
- 当前仓库存在多条 migration 分支头时，优先用 `alembic heads` 检查，再用 `alembic upgrade heads`；旧库如果已经有表结构但没有 `alembic_version`，先确认现状再考虑 `alembic stamp heads`

## 容器端口

应用内部端口 **3434**, Docker 映射到宿主机 **8000** (dev) 或 **3434** (prod)。

## 测试

```bash
# 运行所有测试
make test  # 即 pytest

# 代码检查 (lint 必须在 format 之后)
make format && make lint
```

## Docker 验证

- 修改完成后，如果项目支持 Docker，必须在 Docker 中启动并验证可访问性
- 用户明确表示要看效果时，不能只给出代码改动，必须把服务跑起来并确认页面可打开
- 验证建议至少覆盖首页、新闻中心、我的文章页和关键 API 返回 200

## 已知问题 / 约束

- AI 客户端使用 `asyncio.run()` 在 `ThreadPoolExecutor` 内部执行异步请求 (`services.py:339-349`)
- 文章生词以 JSON 字符串存于 `vocab_json` 字段, 读取时需 `json.loads()`
- 日志使用北京时间 (`UTC+8`), 数据库时间存 UTC
- `app/main.py` 会在启动时重试数据库连接 (最多 10 次, 间隔 3 秒)
- 用户等级 `level` 字段 (1-5) 影响新闻简化难度
- 新闻中心以 RSSHub 订阅源为主，先预览再选择条目生成文章，后台任务仍在独立线程中执行
- 新闻任务和首页文章生成成功/失败都要写入通知中心，失败信息要可读，不能只靠瞬时 toast
- 通知卡片的“查看”入口优先跳转到对应页面，并通过 query 参数触发高亮/定位
- 朗读评测使用 `difflib.SequenceMatcher` 的字符串相似度, 非 AI
