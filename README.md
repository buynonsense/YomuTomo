# YomuTomo（日语朗读与跟读）

简洁的 FastAPI 应用：输入日语文本，自动生成假名注音、中文翻译与生词列表；支持录音评测与用户登录后保存多篇文章（Dashboard 按最近更新时间排序，打开文章自动置顶）。

## 功能

- 假名注音（pykakasi）
- 中文翻译与生词提取（OpenAI 兼容接口）
- 跟读评测（相似度打分）
- 注册/登录/退出（会话）
- 文章保存/删除、Dashboard 按更新时间倒序；打开文章刷新 `updated_at`

## 快速开始（conda 环境）

1. 安装依赖：`pip install -r requirements.txt`
2. 启动（二选一）：
   - 推荐：`python -m uvicorn app.main:app --reload`
   - 兼容：`python -m uvicorn app:app --reload`
3. 访问：`http://127.0.0.1:8000`（首页） | 文档：`/docs` | ReDoc：`/redoc`

## 配置（环境变量）

- `OPENAI_API_KEY`：OpenAI/兼容网关的 API Key（必需）
- `OPENAI_BASE_URL`：可选，自定义网关地址
- `OPENAI_MODEL`：默认 `gpt-5-mini`
- `SECRET_KEY`：会话密钥（建议随机字符串）
- `DATABASE_URL`：默认 `sqlite:///./app.db`

## OpenAI 请求头覆盖（推荐）

优先级：请求头 > 环境变量；表单仅保留 `model`。

- `X-API-Key`：临时 API Key
- `X-Base-URL`：临时 Base URL
- `X-Model`：临时模型名

示例：

```bash
curl -X POST "http://127.0.0.1:8000/process_text" \
  -H "X-API-Key: DSK-xxxx" \
  -H "X-Base-URL: https://dashscope.aliyuncs.com/compatible-mode/v1" \
  -H "X-Model: qwen-plus" \
  -F "text=今日はいい天気ですね。" \
  -F "model=qwen-plus"
```

## 数据库与迁移

- ORM：SQLAlchemy ORM（`User` 一对多 `Article`）
- 默认数据库：SQLite（`app.db`）
- 迁移：Alembic
  1. 生成迁移：`alembic revision --autogenerate -m "init"`
  2. 应用迁移：`alembic upgrade head`
  3. 切换数据库：设置 `DATABASE_URL` 后再执行 1-2 步

## 项目结构（简要）

```
app/
  core/config.py        # 配置
  db.py                 # Engine/Session/Base
  models.py             # ORM 模型
  services.py           # 注音/翻译/生词/标题/密码
  routers/              # 路由（pages/auth/articles/evaluation）
  main.py               # 应用入口（推荐）
app.py                  # 兼容入口（转发到 app.main）
templates/ static/     # 前端资源
alembic/ alembic.ini    # 数据库迁移
```

## 常用命令

- 启动：`python -m uvicorn app.main:app --reload`
- 生成迁移：`alembic revision --autogenerate -m "msg"`
- 升级数据库：`alembic upgrade head`

# 日语短文朗读与跟读应用

这是一个使用 FastAPI 和 Jinja2 开发的日语朗读练习应用。

## 功能

- 导入日语文本
- 自动生成假名注音和罗马音
- 语音录音和识别
- 发音评测

## 运行

1. 安装依赖：`pip install -r requirements.txt`
2. 配置环境变量（可选）：
   - `OPENAI_API_KEY`: OpenAI API Key
   - `OPENAI_BASE_URL`: 可选，自定义 API Base URL
   - `OPENAI_MODEL`: 可选，默认 `gpt-5-mini`
   - `SECRET_KEY`: 会话密钥（用于登录会话），建议设置为随机字符串
   - `DATABASE_URL`: 可选，默认 `sqlite:///./app.db`
3. 初始化数据库：应用启动时会自动在 `app.db` 创建表
4. 运行应用：
   - 新入口：`python -m uvicorn app.main:app --reload`
   - 兼容入口（保留）：`python -m uvicorn app:app --reload`
5. 打开浏览器访问 http://127.0.0.1:8000

## 数据库迁移（Alembic）

在已激活的 conda 环境中：

1. 生成迁移：
   `alembic revision --autogenerate -m "init user and article"`
2. 应用迁移：
   `alembic upgrade head`
3. 切换数据库：设置 `DATABASE_URL` 环境变量后再执行 1-2 步。

## OpenAI 配置与请求头覆盖

默认从环境变量读取：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`（可选）
- `OPENAI_MODEL`（默认 `gpt-5-mini`）

同时支持在请求时用“请求头”临时覆盖（优先级：请求头 > 环境变量）。表单仅保留 `model` 字段（可选）。

- `X-API-Key`: 临时使用的 API Key
- `X-Base-URL`: 临时自定义 Base URL
- `X-Model`: 临时模型名

示例（使用 curl 调用 `/process_text`，并通过请求头覆盖配置）：

```bash
curl -X POST "http://127.0.0.1:8000/process_text" \
  -H "X-API-Key: DSK-xxxx" \
  -H "X-Base-URL: https://dashscope.aliyuncs.com/compatible-mode/v1" \
  -H "X-Model: qwen-plus" \
  -F "text=今日はいい天気ですね。" \
  -F "model=qwen-plus"
```

注意：如果未提供请求头，则使用环境变量与默认模型；提供了请求头则优先使用请求头的配置。

## 注意

- 需要麦克风权限进行录音
- 语音识别使用 Google API，需要网络连接
- 登录后提交文本会自动保存为文章，可在“我的文章”中查看、打开或删除
