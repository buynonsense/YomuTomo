# Vocabulary Review and Word-Level Highlight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给生词本增加单页复习/翻牌模式，并让阅读页朗读高亮细化到句子内的词块级别，同时保留当前生词状态切换和句子播放能力。

**Architecture:** 生词本复习完全复用现有 `/vocabulary/toggle` 接口和页面渲染出的 `vocab_rows`，前端在同一页面内维护列表视图与复习视图两套状态。阅读页保持现有句子播放主链路，只在 TTS 播放时增加词块切分与高亮推进逻辑，并在浏览器能力不足时回退到原有句子级高亮。

**Tech Stack:** FastAPI + Jinja2 + 原生 JavaScript + 现有 `SpeechSynthesis` API + `Intl.Segmenter` + pytest

---

### Task 1: 给生词本页面补上复习模式骨架

**Files:**
- Modify: `templates/vocabulary.html`
- Modify: `static/css/new_style.css`

- [ ] **Step 1: 写失败测试前先确认页面结构约束**

本任务主要是模板和样式改造，不新增后端测试。先确认生词本页需要新增这些 DOM 入口：

```html
<button id="review-mode-btn" type="button" class="btn-secondary">开始复习</button>
<div id="review-panel" class="review-panel is-hidden">
  <div id="review-card" class="review-card" data-flipped="0"></div>
</div>
```

- [ ] **Step 2: 修改模板输出可供前端消费的数据**

在 `templates/vocabulary.html` 中保留现有列表渲染，同时为前端补充一个词条数据容器，建议直接把 `vocab_rows` 序列化到一个隐藏脚本标签里，避免重复解析 DOM：

```html
<script id="vocab-data" type="application/json">{{ vocab_rows | tojson }}</script>
```

列表卡片继续保留现有 `data-vocab-word`、`data-vocab-pronunciation`、`data-vocab-mastered`，因为现有切换接口仍要复用它们。

- [ ] **Step 3: 增加复习模式样式**

在 `static/css/new_style.css` 追加最小样式，确保复习卡片在桌面和移动端都能显示：

```css
.review-panel.is-hidden { display: none; }
.review-panel { margin-top: 18px; }
.review-card { perspective: 1000px; min-height: 240px; }
.review-card-inner { position: relative; width: 100%; min-height: 240px; transform-style: preserve-3d; transition: transform .4s ease; }
.review-card[data-flipped="1"] .review-card-inner { transform: rotateY(180deg); }
.review-card-face { position: absolute; inset: 0; backface-visibility: hidden; border-radius: 18px; padding: 24px; background: var(--card-bg); box-shadow: var(--shadow); }
.review-card-back { transform: rotateY(180deg); }
```

- [ ] **Step 4: 运行页面级检查**

在浏览器里确认普通列表仍正常显示，复习入口按钮和隐藏面板都能被选中但默认不展示。

- [ ] **Step 5: 提交**

```bash
git add templates/vocabulary.html static/css/new_style.css
git commit -m "feat: 增加生词本复习模式骨架"
```

### Task 2: 实现生词本翻牌、前后切换和状态切换

**Files:**
- Modify: `templates/vocabulary.html`
- Create: `static/js/pages/vocabulary.js`

- [ ] **Step 1: 先把失败测试写成可人工验证的交互断言**

本任务仍以页面交互为主，建议先明确前端必须具备的函数：

```js
window.startVocabularyReview
window.stopVocabularyReview
window.flipVocabularyCard
window.goToPreviousVocabularyCard
window.goToNextVocabularyCard
```

- [ ] **Step 2: 在模板中引入生词本专用脚本入口**

在 `templates/vocabulary.html` 的底部引入 `static/js/pages/vocabulary.js`，读取 `#vocab-data`，并初始化本地状态：

```js
const vocabRows = JSON.parse(document.getElementById('vocab-data').textContent || '[]');
```

然后根据当前 `reviewMode` 渲染卡片面板，正面显示：

```js
function renderReviewCard(card) {
  return `
    <div class="review-card-inner">
      <div class="review-card-face review-card-front">
        <div class="vocab-pronunciation">${card.pronunciation || ''}</div>
        <div class="vocab-word">${card.word || ''}</div>
        <div class="review-card-hint">点击翻牌查看释义</div>
      </div>
      <div class="review-card-face review-card-back">
        <div class="vocab-pronunciation">${card.pronunciation || ''}</div>
        <div class="vocab-word">${card.word || ''}</div>
        <div class="vocab-meaning">释义：${card.meaning || ''}</div>
      </div>
    </div>
  `;
}
```

卡片按钮需要支持继续调用现有 `/vocabulary/toggle`，所以翻牌区内也要保留“已掌握 / 取消掌握”的操作按钮。

- [ ] **Step 3: 让复习模式只依赖前端数组状态**

新增最小状态对象：

```js
const reviewState = {
  active: false,
  index: 0,
  flipped: false,
};
```

切换逻辑要求：

```js
function startVocabularyReview() {
  reviewState.active = true;
  reviewState.index = 0;
  reviewState.flipped = false;
  renderVocabularyView();
}

function stopVocabularyReview() {
  reviewState.active = false;
  reviewState.flipped = false;
  renderVocabularyView();
}
```

- [ ] **Step 4: 把已掌握切换逻辑接回现有接口**

继续复用现有 `fetch('/vocabulary/toggle', ...)`，但要保证在复习视图里切换状态后会同步更新当前卡片和底层列表数据：

```js
async function toggleVocabularyStatus(card) {
  const response = await fetch('/vocabulary/toggle', { /* 与现有接口一致 */ });
  const data = await response.json();
  if (!response.ok || !data.success) throw new Error(data.error || '保存失败');
  card.mastered = data.mastered;
}
```

- [ ] **Step 5: 运行浏览器验证**

验证点：

```text
1. 点击“开始复习”后普通网格隐藏，单卡复习视图出现
2. 点击卡片可正反翻转
3. 上一张 / 下一张在边界处不会越界
4. 标记已掌握后按钮文案和样式即时变化
5. 退出复习后回到原列表视图
```

- [ ] **Step 6: 提交**

```bash
git add templates/vocabulary.html static/js/pages/vocabulary.js
git commit -m "feat: 实现生词本翻牌复习"
```

### Task 3: 给阅读页补上词块切分与词级高亮状态

**Files:**
- Modify: `static/js/pages/reading.js`
- Modify: `static/css/new_style.css`

- [ ] **Step 1: 先写一个最小可验证的词块切分函数**

在 `ReadingPageController` 内新增一个专用方法，优先使用 `Intl.Segmenter`，失败时回退到整句：

```js
segmentSentenceToWords(sentence) {
  const text = (sentence || '').trim();
  if (!text) return [];
  if (typeof Intl !== 'undefined' && Intl.Segmenter) {
    try {
      const segmenter = new Intl.Segmenter('ja', { granularity: 'word' });
      return Array.from(segmenter.segment(text))
        .map((part) => part.segment)
        .filter((part) => part && part.trim());
    } catch (error) {
      console.warn('词块切分失败，回退到整句', error);
    }
  }
  return [text];
}
```

- [ ] **Step 2: 给句子项建立词块渲染结构**

把 `renderSentences()` 中的按钮文本，改为可嵌套词块的结构，保持按钮本身不变，只替换内容：

```js
const words = this.segmentSentenceToWords(sentence);
button.innerHTML = words
  .map((word, wordIndex) => `<span class="sentence-word" data-word-index="${wordIndex}">${word}</span>`)
  .join('');
```

同时给 `sentenceItems` 保存句子原文和词块序列，方便播放时同步：

```js
this.sentenceItems = sentences.map((sentence) => ({
  text: sentence,
  words: this.segmentSentenceToWords(sentence),
}));
```

- [ ] **Step 3: 在播放链路里推进当前词块索引**

把 `speakSequence()` 和 `playSentence()` 里的 `SpeechSynthesisUtterance` 回调补上词块状态更新。词块推进不需要精确到音节，只要在当前句子开始播放后，按固定节奏推进高亮即可：

```js
startWordHighlightTimer(sentenceIndex) {
  const sentence = this.sentenceItems[sentenceIndex];
  if (!sentence || sentence.words.length <= 1) return;
  let wordIndex = 0;
  const interval = Math.max(180, Math.round(1200 / sentence.words.length));
  this.clearWordHighlightTimer();
  this.wordHighlightTimer = window.setInterval(() => {
    wordIndex += 1;
    this.currentWordIndex = wordIndex;
    this.syncSentenceHighlight();
    if (wordIndex >= sentence.words.length - 1) {
      this.clearWordHighlightTimer();
    }
  }, interval);
}
```

如果你更希望“严格跟随播放时长”，可在实现时再按句子长度微调间隔，但保持方案简单。

- [ ] **Step 4: 给词块样式补上高亮类**

在 `static/css/new_style.css` 追加：

```css
.sentence-word { display: inline-block; padding: 0 2px; border-radius: 6px; transition: background-color .2s ease, color .2s ease; }
.sentence-word.is-active { background: rgba(233, 30, 99, .18); color: var(--primary-color); }
.sentence-word.is-pending { opacity: .45; }
```

- [ ] **Step 5: 运行页面级验证**

确认以下行为：

```text
1. 全文播放时当前句子仍高亮
2. 当前句子内部会逐步点亮词块
3. 停止播放后词块高亮清空
4. 浏览器不支持 Intl.Segmenter 时仍能正常播放
5. 语音识别高亮不受这次改动影响
```

- [ ] **Step 6: 提交**

```bash
git add static/js/pages/reading.js static/css/new_style.css
git commit -m "feat: 增加阅读页词级朗读高亮"
```

### Task 4: 补齐测试并做最终验证

**Files:**
- Create: `tests/test_vocabulary_review.py`
- Modify: `tests/test_vocabulary_service.py`
- Modify: `tests/test_reading_state.py`
- Modify: `static/js/pages/vocabulary.js`

- [ ] **Step 1: 增加生词本服务测试覆盖复习数据源**

在 `tests/test_vocabulary_service.py` 里补一个针对 `build_vocabulary_view_rows()` 的断言，确保返回字段能支撑复习模式：

```python
def test_build_vocabulary_view_rows_contains_review_fields():
    db = make_session()
    user = User(email='test@example.com', password_hash='hash')
    db.add(user)
    db.flush()
    db.add(
        VocabularyEntry(
            user_id=user.id,
            word='天気',
            pronunciation='てんき',
            meaning='天气',
            status='mastered',
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.commit()

    rows = build_vocabulary_view_rows(db, user.id)

    assert rows[0]['word'] == '天気'
    assert rows[0]['pronunciation'] == 'てんき'
    assert rows[0]['meaning'] == '天气'
    assert rows[0]['status'] == 'mastered'
```

- [ ] **Step 2: 增加阅读状态序列化测试对新增前端状态字段的约束**

在 `tests/test_reading_state.py` 里把状态形状补充为复习模式相关字段，避免前端本地状态被误改：

```python
state = {
    "furiganaMode": "show",
    "hideMastered": False,
    "reviewMode": False,
    "reviewIndex": 0,
    "reviewFlipped": False,
}
```

- [ ] **Step 3: 跑最小测试集**

```bash
pytest tests/test_vocabulary_service.py tests/test_reading_state.py tests/test_evaluation.py -q
node --check static/js/pages/reading.js
```

期望：pytest 全绿，`node --check` 无语法错误。

- [ ] **Step 4: 跑应用级手动验证**

手动检查：

```text
1. /vocabulary 页面可以进入和退出复习模式
2. 复习卡片翻牌前后内容正确
3. 阅读页全文播放时句子内词块逐步高亮
4. 已有“生词状态切换”按钮不失效
```

- [ ] **Step 5: 提交**

```bash
git add tests/test_vocabulary_service.py tests/test_reading_state.py tests/test_vocabulary_review.py static/js/pages/reading.js
git commit -m "test: 补充复习和词级高亮验证"
```
