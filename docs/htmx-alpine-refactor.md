# htmx 2 + Alpine 3 重构 — 开发者迁移指南

**适用版本**：Stage 1–Stage 5 全部合并后
**目标读者**：后续接手 YomuTomo 前后端的开发者 / 维护者
**对应计划**：[docs/superpowers/plans/2026-06-13-htmx-alpine-refactor.md](superpowers/plans/2026-06-13-htmx-alpine-refactor.md)

---

## 0. 一句话原则

- **htmx** 负责"与服务端的来回"（轮询、表单自提交、片段更新、事件通知）。
- **Alpine** 负责"客户端纯交互"（弹窗、翻卡、计数、显隐、派生 getter）。
- **零构建链、零 SPA、零 npm**。所有 vendor 资源进 `static/vendor/`，由 Jinja2 模板通过 `<script defer>` 引入。

---

## 1. Vendor 资源

| 文件 | 版本 | 引入位置 |
|---|---|---|
| `static/vendor/htmx.min.js` | htmx 2.0.3 | `templates/partials/global_nav.html`（已 defer） |
| `static/vendor/alpine.min.js` | Alpine 3.13.10 | 同上 |

升级时手动替换 vendor 文件 + 跑 `pytest -m e2e tests/e2e` 校验行为不破。

---

## 2. 服务端中间件：`HX-Request` 自动识别

`app/main.py` 的 `HtmxRequestMiddleware` 会在 `request.state` 上挂四个开关：

```python
request.state.htmx           # bool
request.state.htmx_target    # HX-Target
request.state.htmx_trigger   # HX-Trigger
request.state.htmx_current_url
```

后端 handler 用 `if request.state.htmx:` 决定返回 HTML 片段（htmx 请求）还是 303 重定向（普通表单提交）。两种形态都要实现。

**Htmx 响应头工具**：见 `app/routers/articles.py` 里保存 AI 配置 / 队列更新时返回的 `HX-Trigger: <event>`。该 header 会派发到 window，前端 Alpine 监听 `x-on:event.window` 就能拿到。

---

## 3. htmx 端点清单

| 端点 | 形态 | 用途 |
|---|---|---|
| `GET /api/crawl/queue/partial` | HTML 片段 | 爬取队列 2s 轮询 |
| `GET /api/notifications/unread_count` | HTML 片段 | 通知未读数 badge |
| `POST /save_ai_config` | 优先片段 / 回退 JSON | AI 配置保存 |
| `POST /vocab/{vocab_id}/toggle` | 优先片段 / 回退 JSON | 生词掌握 toggle |
| `POST /articles/{id}/delete` | 优先片段 / 回退 303 | 文章删除 |
| `POST /articles/{id}/rename` | 优先片段 / 回退 303 | 文章重命名 |

### 写法模板

```python
@router.post("/save_ai_config", response_model=None)
async def save_ai_config(
    request: Request,
    hx_request: bool = None,  # 也可以读 request.state.htmx
    ...
):
    if request.state.htmx:
        # 返回包含 HX-Trigger 头的模板片段
        return templates.TemplateResponse(
            request, "partials/_ai_config_feedback.html",
            {"ok": ok, "message": "..."},
            headers={"HX-Trigger": "ai-config:saved"},
        )
    # 普通表单提交：返回 JSON
    return {"success": ok, "message": "..."}
```

### 模板端

```html
<form hx-post="/save_ai_config"
      hx-target="#ai-config-feedback"
      hx-swap="innerHTML">
  ...
</form>
<div id="ai-config-feedback" hx-swap-oob="true"></div>
```

轮询更简单：

```html
<div id="crawl-queue-list"
     hx-get="/api/crawl/queue/partial"
     hx-trigger="every 2s"
     hx-swap="innerHTML">
  <!-- 初始 partial 内容 -->
</div>
```

---

## 4. Alpine 工厂索引

每个需要客户端状态的组件都暴露一个 `window.xxxFactory()` 函数，模板用 `x-data="xxxFactory()"` 挂载。

| 工厂 | 文件 | 用途 | 关键状态 |
|---|---|---|---|
| `settingsModal()` | `static/js/modules/settings-modal.js` | 全局设置弹窗 | `isOpen` / `activeTab` / `isSubmitting` |
| `vocabReview()` | `static/js/pages/vocabulary.js` | 生词翻卡 | `isOpen` / `index` / `flipped` / `cards` |
| `newsSelection()` | `static/js/pages/news-center.js` | 新闻多选工具栏 | `count` / `isSubmitting` / `submitLabel` |

### 工厂写法约定

```javascript
window.xxxFactory = function xxxFactory() {
  return {
    // 响应式状态
    isOpen: false,
    isSubmitting: false,
    // 派生 getter
    get submitLabel() { return this.isSubmitting ? '提交中…' : '提交'; },
    // 方法
    open() { this.isOpen = true; },
    close() { this.isOpen = false; },
    init() { /* 钩子，Alpine 挂载后调用 */ },
  };
};
```

模板侧：

```html
<div x-data="xxxFactory()"
     x-bind:aria-hidden="!isOpen"
     x-on:keydown.escape="close()"
     x-on:something.window="onSomething($event.detail)">
  <span x-text="submitLabel">fallback</span>
  <button x-on:click="submit()" x-bind:disabled="isSubmitting">提交</button>
</div>
```

### 桥接层（命令式代码 ↔ Alpine）

新闻多选场景下，**Alpine 状态机**只持有工具栏的 `count` / `isSubmitting`，**真正的卡片选中状态**还在 `window.__newsSelectionBridge`（一个命令式 Map）。卡片点击 → 调 `bridge.add/remove` → `bridge` 派发 `news:selection-changed` 事件 → Alpine 工具栏 `x-on:news:selection-changed.window="count = $event.detail.count"` 同步。

> 原则：**Alpine 管 UI 状态，原有命令式代码管领域状态**。新功能建议直接全 Alpine；旧功能用桥接层平滑过渡。

---

## 5. 测试组织

### 单元 / 集成测试（默认跑）

```bash
make test                    # 即 pytest，自动 collect tests/ 全部
pytest tests/test_htmx_alpine_vendor.py   # 46 个 htmx+alpine 专项用例
```

`tests/test_htmx_alpine_vendor.py` 覆盖：
- vendor 文件存在 + 注入到全局 nav
- 中间件对 `HX-Request: true` 正确置位
- `format_datetime` 过滤器 / `task_progress_percent` 全局函数
- 爬取队列 htmx 端点
- AI 配置、生词 toggle、文章重命名/删除的 htmx 形态 + 非 htmx 形态
- 三个 Alpine 工厂暴露在 `window` + 模板 `x-data` 绑定
- 旧命令式状态代码已彻底删除

### 端到端测试（opt-in）

```bash
pytest -m e2e tests/e2e/
```

`tests/e2e/test_htmx_alpine_e2e.py` 起一个真实 uvicorn + sqlite 文件 DB + playwright Chromium，跑 8 个用例：
1. vendor 资源 200
2. 登录表单 → 跳 /dashboard
3. 设置弹窗 Alpine 显隐
4. 新闻多选 Alpine 工具栏显隐 + 计数事件
5. 生词翻卡 Alpine 状态机注册
6. dashboard 含 htmx 表单
7. 通知 badge 元素
8. 新闻中心含 htmx 轮询

**前置**：`python -m playwright install chromium`（首次需要从 CDN 拉一次 headless shell）。

---

## 6. 改动一览（按 commit）

| Stage | Commit | 关键改动 |
|---|---|---|
| 1 | `chore(deps): 引入 htmx 2.0.3 + alpine 3.13.10 (vendor)` | vendor + nav + 中间件 |
| 2 | `refactor(htmx): 爬取队列改用 htmx 片段轮询` | `/api/crawl/queue/partial` + 通知未读轮询 |
| 3a | `refactor(htmx): AI 配置保存改用 htmx 表单自提交` | `/save_ai_config` 片段 + HX-Trigger |
| 3b | `refactor(htmx): 生词掌握 toggle 改用 hx-post 片段` | `/vocab/{id}/toggle` 片段 |
| 3c | `refactor(htmx): 文章重命名/删除改用 htmx 自提交` | `/articles/{id}/...` 片段 + 303 回退 |
| 4a | `refactor(alpine): 设置弹窗改 Alpine 局部状态机` | `settingsModal()` |
| 4b | `refactor(alpine): 生词翻卡改 Alpine 局部状态机` | `vocabReview()` |
| 4c | `refactor(alpine): 新闻多选改 Alpine 局部状态机` | `newsSelection()` + `__newsSelectionBridge` |

---

## 7. 后续可清理点（out of scope）

- 移除 Stage 1-4 期间残留的旧命令式 DOM 操作代码（搜索 `querySelectorAll` / `addEventListener` 旧路径）
- 通知中心 badge 计数可以走 SSE 而非 2s 轮询
- `task-state.js` 监听 `htmx:afterRequest` 事件，未来可以收口到 Alpine 派生状态
- `newsSelection` 的桥接层可以在确认稳定后拆掉，把选中状态直接进 Alpine

---

## 8. 常见坑

1. **`x-on:event.window` 监听的是 `window`**，不是 `document` —— E2E 测试时用 `window.dispatchEvent(new CustomEvent(...))`。
2. **`x-bind:hidden` 不是布尔属性**。`x-bind:hidden="count === 0"` 当表达式为真时设置 `hidden=""`，Alpine 同时也设 `el.hidden = true`，测试时两者都要查。
3. **Alpine 启动是异步的**。在 `init()` 里立刻 `this._x_dataStack[0]` 是 undefined。模板里 `x-data` 的元素挂载后用 `page.wait_for_timeout(50)` 等渲染。
4. **HX-Trigger 的事件名是 window 派发**。同一页多组件都要监听时记得加 namespace（如 `ai-config:saved`）。
5. **非 htmx 请求要 303 重定向**，不能用 200 + HTML 替换。`TestClient.post(..., follow_redirects=False)` 才会看到 303。

---

## 9. 跑通清单

```bash
make format                 # black + isort
make lint                   # flake8 + black --check
make test                   # 158 个单测应全绿
python -m playwright install chromium   # 首次
pytest -m e2e tests/e2e/    # 8 个 e2e 用例应全绿
make dev                    # uvicorn 启动，浏览器打开 /login 验证
```
