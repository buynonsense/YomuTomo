# htmx 2 + Alpine 3 重构计划

**状态**：Stage 0 — 调研已完成，待 Stage 1 落地
**分支**：`refactor/htmx-alpine` (基于 `dev`)
**目标**：用 htmx 2 接管"与服务端的来回"（轮询、表单、片段），用 Alpine 3 接管"客户端纯交互"（弹窗、翻卡、状态机）。零构建链、零 SPA、零 npm。

## 决策记录

| 项 | 决策 |
|---|---|
| htmx 版本 | 2.0.3 |
| Alpine 版本 | 3.13.x |
| 资源方式 | 离线 vendor (`static/vendor/`) |
| Commit 节奏 | 一个 Stage 一个 commit |
| 测试 | Stage 1-4 仅 `make test` + 手动；Stage 5 加 playwright |
| 范围 | 5 个 Stage 照单全做 |

## Stage 1：基建（vendor + 中间件）

1. 下载 `htmx.min.js@2.0.3` + `alpine.min.js@3.13.x` 到 `static/vendor/`
2. `templates/partials/global_nav.html` 注入 `<script defer src="/static/vendor/htmx.min.js">` 和 `<script defer src="/static/vendor/alpine.min.js">`
3. `app/main.py` 加 `HX-Request` 中间件：`request.state.htmx = request.headers.get('HX-Request') == 'true'`
4. 测试：访问首页 → 断言 vendor 资源 200
5. 重建 Docker + commit `chore(deps): 引入 htmx 2 + alpine 3 (vendor)`

## Stage 2：爬取队列 / 通知未读 → htmx 轮询

- `app/routers/articles.py` 新增 `GET /api/crawl/queue/partial` → `text/html`
- `templates/news_center.html` 的 `#crawl-queue-list` 改 `hx-get` + `hx-trigger="every 2s"`
- `templates/partials/global_notifications_panel.html` 类似
- 删 `news-center.js:615-625` 的 `setInterval/clearInterval` 段
- commit `refactor(news-center): 爬取队列 + 通知未读数改用 htmx 轮询`

## Stage 3：表单提交 → htmx

- **3a** AI 配置保存：`<form hx-post hx-swap="none" hx-on::after-request>`，删 `modules/ai-config.js`
- **3b** 生词掌握：`<button hx-post hx-swap="outerHTML">`，endpoint 按 HX-Request 头返回 HTML/JSON
- **3c** 文章重命名/删除：dashboard 操作 → hx-post + hx-redirect
- 每步一个 commit

## Stage 4：Alpine 局部状态机

- `global_settings_modal.html` → Alpine 化，删 `settings-modal.js` (402 行)
- `news-center.html` 多选 → `x-data="{ selected: new Set() }"`
- `vocabulary.html` 翻卡 → `x-data="{ idx, flipped, ... }"`
- 一个 commit

## Stage 5：测试 / CI / 文档

- `test_pages_templates.py` 加 htmx 片段路由覆盖
- `test_alpine_x_data.py`（新）→ jsdom 验证 Alpine 状态
- 加 playwright 端到端
- `AGENTS.md` 加 "前端增强" 小节

## 关键约束（不做）

- 不引入 npm/Vite/webpack
- 不把整个站改成 SPA
- 不动 TTS 批量加载（已 IndexedDB 化，与 htmx/Alpine 正交）
- 不删除现有 JSON API（向后兼容）
- 不动 auth / 评测 / 通知后端

## 风险

| 风险 | 对策 |
|---|---|
| HTML 路由与 JSON 冲突 | 新增 `*_partial` 端点，按 HX-Request 头分流 |
| 触发后丢失全局状态 | `hx-on::after-request` 派发 `show-toast` 事件，common.js 监听 |
| 回归覆盖不足 | 每个 commit 必须 `make test` 全绿 + 手动跑核心页 |
