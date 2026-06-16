/**
 * 新闻中心 - Alpine.js 版本
 *
 * Alpine 局部状态机 (newsSelection 工厂) 负责：
 *   - 选中数量 (count)
 *   - 提交中 (isSubmitting) / 按钮 label (submitLabel)
 *   - 工具栏显隐 (x-bind:hidden)
 *   - 提交/清空入口 (x-on:click)
 *
 * 与命令式 card 选中逻辑的桥接：
 *   - 卡片 toggle 走全局 window.__newsSelectionBridge
 *   - 每次 count 变化时派发 `news:selection-changed` CustomEvent
 *   - Alpine 通过 x-on:news:selection-changed.window 同步 count
 *
 * 提交/清空走 Alpine 工厂方法 → 内部仍由 bridge 实际操作 fetch
 */

(function () {
  'use strict';

  // ---- 桥接层：被 Alpine 工厂方法直接调用 -------------------------------

  const bridge = {
    selectedBySource: new Map(),
    isSubmitting: false,

    selectionKey(newsUrl) {
      return (newsUrl || '').trim();
    },

    getCount() {
      let total = 0;
      this.selectedBySource.forEach((group) => {
        total += group.items.size;
      });
      return total;
    },

    emitChanged() {
      // 派发到 window: Alpine 模板用 x-on:news:selection-changed.window 监听
      // (派到 document 不会触发 window 监听器, 选中状态不会同步到工具栏 count)
      window.dispatchEvent(
        new CustomEvent('news:selection-changed', {
          detail: { count: this.getCount() }
        })
      );
    },

    add(card) {
      if (!card) {
        return;
      }
      const newsUrl = this.selectionKey(card.dataset.newsUrl);
      if (!newsUrl) {
        return;
      }
      const sourceUrl = card.dataset.newsSourceUrl || '';
      const endpoint = card.dataset.crawlEndpoint || '/crawl_news';
      const title = card.dataset.newsTitle || newsUrl;

      if (!this.selectedBySource.has(sourceUrl)) {
        this.selectedBySource.set(sourceUrl, { endpoint, items: new Map() });
      }
      const group = this.selectedBySource.get(sourceUrl);
      group.items.set(newsUrl, { title, sourceUrl, endpoint });
      this.emitChanged();
    },

    remove(card) {
      if (!card) {
        return;
      }
      const newsUrl = this.selectionKey(card.dataset.newsUrl);
      const sourceUrl = card.dataset.newsSourceUrl || '';
      const group = this.selectedBySource.get(sourceUrl);
      if (group) {
        group.items.delete(newsUrl);
        if (group.items.size === 0) {
          this.selectedBySource.delete(sourceUrl);
        }
      }
      this.emitChanged();
    },

    clearAll() {
      const cards = document.querySelectorAll('[data-news-card]');
      cards.forEach((card) => {
        card.classList.remove('is-selected');
        const cb = card.querySelector('[data-news-select]');
        if (cb) {
          cb.checked = false;
        }
      });
      this.selectedBySource.clear();
      this.emitChanged();
    },

    groups() {
      return Array.from(this.selectedBySource.entries()).filter(([, g]) => g.items.size > 0);
    },

    async postCrawlBatch(endpoint, sourceUrl, newsUrls) {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_url: sourceUrl,
          selected_urls: newsUrls,
          news_urls: newsUrls
        })
      });
      let data = null;
      try {
        data = await response.json();
      } catch (e) {
        data = null;
      }
      if (!response.ok || !data || !data.success) {
        throw new Error((data && (data.message || data.error)) || '启动失败');
      }
      return data;
    },

    async submitAll(onStateChange) {
      if (this.isSubmitting) {
        return { skipped: true };
      }
      const groups = this.groups();
      if (groups.length === 0) {
        return { skipped: true, empty: true };
      }
      this.isSubmitting = true;
      if (typeof onStateChange === 'function') {
        onStateChange({ isSubmitting: true });
      }
      let okCount = 0;
      let failCount = 0;
      const failed = [];
      for (const [sourceUrl, group] of groups) {
        const newsUrls = Array.from(group.items.keys());
        try {
          await this.postCrawlBatch(group.endpoint, sourceUrl, newsUrls);
          okCount += 1;
        } catch (err) {
          failCount += 1;
          failed.push(err.message || '启动失败');
        }
      }
      this.isSubmitting = false;
      if (typeof onStateChange === 'function') {
        onStateChange({ isSubmitting: false });
      }
      if (okCount > 0) {
        const totalItems = this.getCount();
        notify(`已提交 ${okCount} 个批次，共 ${totalItems} 篇文章到爬取队列`, 'success');
        this.clearAll();
        // htmx 自带每 2s 轮询，提交后无需手动启动
      }
      if (failCount > 0) {
        notify(`部分批次启动失败：${failed.join('；')}`, 'error');
      }
      return { okCount, failCount };
    }
  };

  window.__newsSelectionBridge = bridge;

  // ---- Alpine 工厂 -----------------------------------------------------

  window.newsSelection = function newsSelection() {
    return {
      count: 0,
      isSubmitting: false,

      init() {
        // 初始 count 同步
        this.count = bridge.getCount();
      },

      get submitLabel() {
        return this.isSubmitting ? '提交中…' : '加入爬取队列';
      },

      clear() {
        bridge.clearAll();
      },

      submit() {
        bridge
          .submitAll((state) => {
            this.isSubmitting = !!state.isSubmitting;
          })
          .catch((error) => {
            console.error('提交新闻选择失败', error);
            notify(error.message || '提交失败', 'error');
          });
      }
    };
  };

  // ---- 命令式工具 (预览 / 卡片初始化) -----------------------------------

  function getSafeLink(url) {
    if (typeof url !== 'string') {
      return '#';
    }
    const value = url.trim();
    if (value.startsWith('http://') || value.startsWith('https://')) {
      return value;
    }
    return '#';
  }

  function formatTime(value) {
    if (!window.Utils || typeof window.Utils.formatDateTime !== 'function') {
      return '';
    }
    return window.Utils.formatDateTime(value);
  }

  function notify(message, type) {
    if (typeof window.showToast === 'function') {
      window.showToast(message, type || 'info', 4000);
      return;
    }
    if (window.Toast && typeof window.Toast.show === 'function') {
      window.Toast.show(message, type || 'info', 4000);
      return;
    }
    console.log(message);
  }

  function setButtonLabel(button, label) {
    if (!button) {
      return;
    }
    const textNode = button.querySelector('.btn-label');
    if (textNode) {
      textNode.textContent = label;
      return;
    }
    button.textContent = label;
  }

  function setLoadingShellState(button, isLoading) {
    if (!button) {
      return;
    }
    const shell = button.closest('.btn-loading-shell');
    if (shell) {
      shell.classList.toggle('is-loading', isLoading);
    }
  }

  function formatNewsTimeElements(root) {
    const scope = root || document;
    scope.querySelectorAll('[data-news-published-at-display]').forEach((element) => {
      const value = element.getAttribute('data-news-published-at-display');
      const formattedTime = formatTime(value);
      if (formattedTime) {
        element.textContent = `发布时间：${formattedTime}`;
      } else {
        element.textContent = '发布时间：';
      }
    });
  }

  function bindCheckboxForCard(card) {
    const cb = card.querySelector('[data-news-select]');
    if (!cb) {
      return;
    }
    cb.addEventListener('change', function () {
      if (cb.checked) {
        card.classList.add('is-selected');
        bridge.add(card);
      } else {
        card.classList.remove('is-selected');
        bridge.remove(card);
      }
    });
    // 点击卡片其它区域时切换选中（除按钮、链接外）
    card.addEventListener('click', function (event) {
      const target = event.target;
      if (target.closest('a, button, input, label')) {
        return;
      }
      cb.checked = !cb.checked;
      if (cb.checked) {
        card.classList.add('is-selected');
        bridge.add(card);
      } else {
        card.classList.remove('is-selected');
        bridge.remove(card);
      }
    });
  }

  // --- 预览缓存 (localStorage) ----------------------------------------

  const PREVIEW_CACHE_KEY = 'yomutomo:news-preview:v1';
  const PREVIEW_CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 24h 临时保存

  function readStorage(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (err) {
      return null;
    }
  }

  function writeStorage(key, value) {
    try {
      window.localStorage.setItem(key, value);
      return true;
    } catch (err) {
      return false;
    }
  }

  function removeStorage(key) {
    try {
      window.localStorage.removeItem(key);
      return true;
    } catch (err) {
      return false;
    }
  }

  function savePreviewCache(sourceUrl, items) {
    if (!Array.isArray(items)) {
      return false;
    }
    const payload = {
      source_url: sourceUrl || '',
      items: items,
      saved_at: new Date().toISOString()
    };
    return writeStorage(PREVIEW_CACHE_KEY, JSON.stringify(payload));
  }

  function clearPreviewCache() {
    return removeStorage(PREVIEW_CACHE_KEY);
  }

  function loadPreviewCache() {
    const raw = readStorage(PREVIEW_CACHE_KEY);
    if (!raw) {
      return null;
    }
    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (err) {
      // 坏数据: 静默清掉
      clearPreviewCache();
      return null;
    }
    if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.items)) {
      clearPreviewCache();
      return null;
    }
    // 24h 过期
    const savedAt = Date.parse(parsed.saved_at || '');
    if (!savedAt || (Date.now() - savedAt) > PREVIEW_CACHE_TTL_MS) {
      clearPreviewCache();
      return null;
    }
    return parsed;
  }

  function formatRelativeTime(savedAtIso) {
    const savedAt = Date.parse(savedAtIso || '');
    if (!savedAt) {
      return '';
    }
    const diffSec = Math.max(0, Math.floor((Date.now() - savedAt) / 1000));
    if (diffSec < 60) {
      return `${diffSec} 秒前`;
    }
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) {
      return `${diffMin} 分钟前`;
    }
    const diffHour = Math.floor(diffMin / 60);
    if (diffHour < 24) {
      return `${diffHour} 小时前`;
    }
    return new Date(savedAt).toLocaleString();
  }

  function setCacheInfo(visible, savedAtIso) {
    const cacheInfo = document.getElementById('rsshub-preview-cache-info');
    if (!cacheInfo) {
      return;
    }
    if (!visible || !savedAtIso) {
      cacheInfo.hidden = true;
      cacheInfo.textContent = '';
      return;
    }
    cacheInfo.hidden = false;
    cacheInfo.textContent = `（临时缓存于 ${formatRelativeTime(savedAtIso)}，关闭浏览器后仍可见，24 小时后自动失效）`;
  }

  function setClearCacheButton(visible) {
    const btn = document.getElementById('rsshub-preview-clear-cache');
    if (!btn) {
      return;
    }
    btn.hidden = !visible;
  }

  // --- 预览 ------------------------------------------------------------

  function setPreviewPanelState(visible) {
    const previewPanel = document.getElementById('rsshub-preview-panel');
    if (!previewPanel) {
      return;
    }
    previewPanel.hidden = !visible;
  }

  function clearPreviewPanel() {
    const previewGrid = document.getElementById('rsshub-preview-grid');
    const previewEmpty = document.getElementById('rsshub-preview-empty');
    const previewMeta = document.getElementById('rsshub-preview-meta');
    if (previewGrid) {
      previewGrid.innerHTML = '';
    }
    if (previewEmpty) {
      previewEmpty.hidden = true;
    }
    if (previewMeta) {
      previewMeta.textContent = '预览结果会显示在这里，勾选条目后点击"加入爬取队列"即可批量生成文章。';
    }
    setCacheInfo(false);
    setClearCacheButton(false);
    setPreviewPanelState(false);
  }

  function createPreviewCard(item, sourceUrl) {
    const previewGrid = document.getElementById('rsshub-preview-grid');
    if (!previewGrid) {
      return null;
    }
    const article = document.createElement('article');
    article.className = 'news-card';
    article.dataset.newsCard = 'true';
    article.dataset.newsPreviewCard = 'true';
    article.dataset.newsUrl = (item && (item.source_url || item.url) ? String(item.source_url || item.url) : '').trim();
    article.dataset.newsTitle = (item && item.title ? String(item.title) : '未命名条目').trim();
    article.dataset.newsSourceUrl = sourceUrl || '';
    article.dataset.newsPublishedAt = (item && typeof item.published_at === 'string' ? item.published_at : '').trim();
    article.dataset.crawlEndpoint = '/crawl_custom_url';

    const selectLabel = document.createElement('label');
    selectLabel.className = 'news-card__select';
    selectLabel.title = '勾选加入爬取队列';
    const selectInput = document.createElement('input');
    selectInput.type = 'checkbox';
    selectInput.className = 'news-card__checkbox';
    selectInput.setAttribute('data-news-select', '');
    const selectBox = document.createElement('span');
    selectBox.className = 'news-card__select-box';
    selectBox.setAttribute('aria-hidden', 'true');
    selectLabel.appendChild(selectInput);
    selectLabel.appendChild(selectBox);

    const top = document.createElement('div');
    top.className = 'news-card__top';

    const badge = document.createElement('span');
    badge.className = 'news-card__badge';
    badge.textContent = '预览';

    const originalLink = document.createElement('a');
    originalLink.className = 'btn-secondary';
    originalLink.title = '查看原文';
    originalLink.setAttribute('aria-label', '查看原文');
    originalLink.target = '_blank';
    originalLink.rel = 'noreferrer noopener';
    originalLink.href = getSafeLink(article.dataset.newsUrl);
    originalLink.textContent = '原文';

    top.appendChild(badge);
    top.appendChild(originalLink);

    const title = document.createElement('h3');
    title.className = 'news-card__title';
    title.textContent = article.dataset.newsTitle || '未命名条目';

    const publishedAt = article.dataset.newsPublishedAt || '';
    if (publishedAt) {
      const time = document.createElement('div');
      time.className = 'news-card__time';
      const formattedTime = formatTime(publishedAt);
      time.textContent = formattedTime ? `发布时间：${formattedTime}` : '发布时间：';
      article.appendChild(time);
    }

    const outlineText = document.createElement('p');
    outlineText.className = 'news-card__outline';
    const outline = item && typeof item.outline === 'string' && item.outline.trim()
      ? item.outline.trim()
      : (item && typeof item.content === 'string' && item.content.trim() ? item.content.trim() : '暂无摘要');
    outlineText.textContent = outline;

    article.appendChild(selectLabel);
    article.appendChild(top);
    article.appendChild(title);
    article.appendChild(outlineText);
    bindCheckboxForCard(article);
    return article;
  }

  function renderPreviewItems(items, sourceUrl, options) {
    const opts = options || {};
    const previewGrid = document.getElementById('rsshub-preview-grid');
    const previewEmpty = document.getElementById('rsshub-preview-empty');
    const previewMeta = document.getElementById('rsshub-preview-meta');
    if (!previewGrid) {
      return;
    }
    previewGrid.innerHTML = '';
    const normalizedItems = Array.isArray(items) ? items : [];
    if (previewMeta) {
      const label = sourceUrl || '当前订阅源';
      previewMeta.textContent = normalizedItems.length > 0
        ? `已预览 ${normalizedItems.length} 条来自 ${label} 的内容，勾选后点击底部"加入爬取队列"即可批量生成。`
        : `已经获取到 ${label} 的预览结果，但没有可用条目。`;
    }
    if (normalizedItems.length === 0) {
      if (previewEmpty) {
        previewEmpty.hidden = false;
      }
      setPreviewPanelState(true);
      return;
    }
    if (previewEmpty) {
      previewEmpty.hidden = true;
    }
    normalizedItems.forEach((item) => {
      const card = createPreviewCard(item, sourceUrl);
      if (card) {
        previewGrid.appendChild(card);
      }
    });
    setPreviewPanelState(true);
    formatNewsTimeElements(previewGrid);
    // 缓存信息 (从缓存恢复时显示 "X 分钟前"; 实时预览时隐藏)
    setCacheInfo(Boolean(opts.fromCache && opts.savedAt), opts.savedAt);
    setClearCacheButton(Boolean(opts.fromCache));
  }

  async function previewCustomUrl() {
    const customUrlInput = document.getElementById('custom-url-input');
    const customUrlSubmit = document.getElementById('custom-url-submit');
    const customUrl = customUrlInput ? customUrlInput.value.trim() : '';
    if (!customUrl) {
      notify('请先输入一个订阅链接', 'error');
      return;
    }
    if (customUrlInput) {
      customUrlInput.disabled = true;
    }
    if (customUrlSubmit) {
      customUrlSubmit.disabled = true;
    }
    customUrlSubmit.dataset.originalText = customUrlSubmit.querySelector('.btn-label')?.textContent || customUrlSubmit.textContent;
    setButtonLabel(customUrlSubmit, '预览中…');
    customUrlSubmit.classList.add('is-loading');
    setLoadingShellState(customUrlSubmit, true);

    try {
      const response = await fetch('/preview_rsshub_feed', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_url: customUrl })
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.message || data.error || '预览失败');
      }
      renderPreviewItems(data.items || [], data.source_url || customUrl);
      // 实时预览成功: 写入 localStorage (24h 内重开浏览器可见)
      savePreviewCache(data.source_url || customUrl, data.items || []);
      notify(
        data.count > 0 ? `已预览 ${data.count} 条订阅内容` : (data.message || '未抓到可用条目'),
        data.count > 0 ? 'success' : 'warning'
      );
    } catch (error) {
      console.error('预览自定义订阅源失败', error);
      clearPreviewPanel();
      notify(error.message || '预览失败', 'error');
    } finally {
      if (customUrlInput) {
        customUrlInput.disabled = false;
      }
      if (customUrlSubmit) {
        customUrlSubmit.disabled = false;
      }
      setButtonLabel(customUrlSubmit, customUrlSubmit.dataset.originalText || '预览订阅源');
      customUrlSubmit.classList.remove('is-loading');
      setLoadingShellState(customUrlSubmit, false);
    }
  }

  // --- 初始化 ---------------------------------------------------------

  function bindInitial() {
    document.querySelectorAll('[data-news-card]').forEach((card) => {
      bindCheckboxForCard(card);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    const customUrlInput = document.getElementById('custom-url-input');
    const customUrlSubmit = document.getElementById('custom-url-submit');
    if (customUrlSubmit) {
      customUrlSubmit.addEventListener('click', function () {
        previewCustomUrl();
      });
    }
    if (customUrlInput) {
      customUrlInput.addEventListener('keydown', function (event) {
        if (event.key === 'Enter') {
          event.preventDefault();
          previewCustomUrl();
        }
      });
    }
    const clearCacheBtn = document.getElementById('rsshub-preview-clear-cache');
    if (clearCacheBtn) {
      clearCacheBtn.addEventListener('click', function () {
        if (clearPreviewCache()) {
          clearPreviewPanel();
          notify('预览缓存已清除', 'success');
        }
      });
    }
    formatNewsTimeElements(document);
    bindInitial();

    // 恢复上次预览 (24h 内的临时缓存)
    const cached = loadPreviewCache();
    if (cached && Array.isArray(cached.items) && cached.items.length > 0) {
      renderPreviewItems(cached.items, cached.source_url, {
        fromCache: true,
        savedAt: cached.saved_at
      });
    }
  });
})();
