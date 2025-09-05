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

## 使用 Makefile（推荐）

项目提供了 Makefile 来简化常见操作：

```bash
# 安装依赖
make install

# 启动开发服务器
make dev

# Docker 操作
make build    # 构建镜像
make up       # 启动服务
make down     # 停止服务
make logs     # 查看日志

# 生产部署
make deploy   # 生产环境部署

# 数据库维护
make backup   # 备份数据库
make restore file=backup.sql  # 恢复数据库

# 代码质量
make format   # 格式化代码
make lint     # 检查代码
```

## Docker 部署

### 使用 Docker Compose（推荐）

1. **克隆项目并进入目录**：
   ```bash
   git clone <repository-url>
   cd YomuTomo
   ```

2. **配置环境变量**：
   ```bash
   cp .env.example .env
   # 编辑 .env 文件，设置你的配置
   ```

3. **启动服务**：
   ```bash
   docker-compose up -d
   ```

### 生产环境部署

1. **使用生产配置**：
   ```bash
   docker-compose -f docker-compose.prod.yml up -d
   ```

2. **启用 Nginx 反向代理**：
   ```bash
   docker-compose -f docker-compose.prod.yml --profile nginx up -d
   ```

3. **查看日志**：
   ```bash
   docker-compose logs -f
   ```

4. **停止服务**：
   ```bash
   docker-compose down
   ```

## 架构说明

### 开发环境
- **数据库**：PostgreSQL（Docker容器）
- **应用**：直接运行 FastAPI
- **配置**：环境变量或 .env 文件

### 生产环境
- **数据库**：PostgreSQL（容器化）
- **应用**：Docker 容器
- **代理**：Nginx（可选）
- **网络**：内部网络隔离
- **安全**：最小权限原则

### 服务说明
- **postgres**：PostgreSQL 15 数据库
- **yomu_app**：FastAPI 应用
- **nginx**：反向代理（生产环境可选）

## 备份与维护

### 数据库备份
```bash
# 备份数据库
docker exec yomu_postgres pg_dump -U postgres yomu_pg > backup.sql

# 恢复数据库
docker exec -i yomu_postgres psql -U postgres yomu_pg < backup.sql
```

### 日志查看
```bash
# 查看应用日志
docker-compose logs -f yomu_app

# 查看数据库日志
docker-compose logs -f postgres
```

### 单独使用 Docker

1. **构建镜像**：
   ```bash
   docker build -t yomu-app .
   ```

2. **运行容器**：
   ```bash
   docker run -d \
     --name yomu-app \
     -p 8000:3434 \
     -e OPENAI_API_KEY=your_key \
     -e DATABASE_URL=postgresql://host:port/db \
     yomu-app
   ```

## 环境变量配置

创建 `.env` 文件或直接设置环境变量：

```bash
# 数据库配置
POSTGRES_PASSWORD=your_secure_password

# AI配置
OPENAI_API_KEY=your_openai_api_key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-5-mini

# 应用配置
SECRET_KEY=your_secret_key_here
FURIGANA_MODE=hybrid
```

## 数据库

项目使用 PostgreSQL 数据库：

- **开发环境**：PostgreSQL（Docker容器）
- **生产环境**：PostgreSQL（推荐）

Docker Compose 会自动启动 PostgreSQL 容器并创建数据库。

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
  -H "X-Furigana-Mode: hybrid" \
  -F "text=今日はいい天気ですね。" \
  -F "model=qwen-plus"
```

说明：

- `FURIGANA_MODE=kakasi`：仅 pykakasi（最快，可能有误）
- `FURIGANA_MODE=hybrid`：先 kakasi，后 AI 校正（推荐）
- `FURIGANA_MODE=ai`：完全由 AI 生成 ruby（最准确，最慢/成本最高）

## 数据库与迁移

- ORM：SQLAlchemy ORM（`User` 一对多 `Article`）
- 默认数据库：PostgreSQL（Docker容器）
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
   - `DATABASE_URL`: 可选，默认 `postgresql://postgres:1234@localhost:5432/yomu_pg`
3. 初始化数据库：启动 Docker Compose 会自动创建数据库和表
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
