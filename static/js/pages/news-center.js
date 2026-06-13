(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    const customUrlInput = document.getElementById('custom-url-input');
    const customUrlSubmit = document.getElementById('custom-url-submit');
    const previewPanel = document.getElementById('rsshub-preview-panel');
    const previewGrid = document.getElementById('rsshub-preview-grid');
    const previewEmpty = document.getElementById('rsshub-preview-empty');
    const previewMeta = document.getElementById('rsshub-preview-meta');

    // 选中工具栏
    const selectionToolbar = document.getElementById('news-selection-toolbar');
    const selectionCount = document.getElementById('news-selection-count');
    const selectionSubmit = document.getElementById('news-selection-submit');
    const selectionClear = document.getElementById('news-selection-clear');

    let isSubmitting = false;

    // 已选条目按 (source_url, source_feed_url) 分组，方便按源分批提交
    const selectedBySource = new Map();

    function getNewsCards() {
      return Array.from(document.querySelectorAll('[data-news-card]'));
    }

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
      if (typeof showToast === 'function') {
        showToast(message, type || 'info', 4000);
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

    // --- 选中管理 ---------------------------------------------------------

    function selectionKey(newsUrl) {
      return (newsUrl || '').trim();
    }

    function getSelectedCount() {
      let total = 0;
      selectedBySource.forEach((group) => {
        total += group.items.size;
      });
      return total;
    }

    function updateSelectionToolbar() {
      const count = getSelectedCount();
      if (selectionCount) {
        selectionCount.textContent = String(count);
      }
      if (selectionToolbar) {
        selectionToolbar.hidden = count === 0;
      }
    }

    function addSelection(card) {
      if (!card) {
        return;
      }
      const newsUrl = selectionKey(card.dataset.newsUrl);
      if (!newsUrl) {
        return;
      }
      const sourceUrl = card.dataset.newsSourceUrl || '';
      const endpoint = card.dataset.crawlEndpoint || '/crawl_news';
      const title = card.dataset.newsTitle || newsUrl;

      if (!selectedBySource.has(sourceUrl)) {
        selectedBySource.set(sourceUrl, { endpoint, items: new Map() });
      }
      const group = selectedBySource.get(sourceUrl);
      group.items.set(newsUrl, { title, sourceUrl, endpoint });
      card.classList.add('is-selected');
      const cb = card.querySelector('[data-news-select]');
      if (cb && !cb.checked) {
        cb.checked = true;
      }
      updateSelectionToolbar();
    }

    function removeSelection(card) {
      if (!card) {
        return;
      }
      const newsUrl = selectionKey(card.dataset.newsUrl);
      const sourceUrl = card.dataset.newsSourceUrl || '';
      const group = selectedBySource.get(sourceUrl);
      if (group) {
        group.items.delete(newsUrl);
        if (group.items.size === 0) {
          selectedBySource.delete(sourceUrl);
        }
      }
      card.classList.remove('is-selected');
      const cb = card.querySelector('[data-news-select]');
      if (cb && cb.checked) {
        cb.checked = false;
      }
      updateSelectionToolbar();
    }

    function clearSelection() {
      getNewsCards().forEach((card) => {
        card.classList.remove('is-selected');
        const cb = card.querySelector('[data-news-select]');
        if (cb) {
          cb.checked = false;
        }
      });
      selectedBySource.clear();
      updateSelectionToolbar();
    }

    function bindCheckboxForCard(card) {
      const cb = card.querySelector('[data-news-select]');
      if (!cb) {
        return;
      }
      cb.addEventListener('change', function () {
        if (cb.checked) {
          addSelection(card);
        } else {
          removeSelection(card);
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
          addSelection(card);
        } else {
          removeSelection(card);
        }
      });
    }

    // --- 预览 ------------------------------------------------------------

    function setPreviewPanelState(visible) {
      if (!previewPanel) {
        return;
      }
      previewPanel.hidden = !visible;
    }

    function clearPreviewPanel() {
      if (previewGrid) {
        previewGrid.innerHTML = '';
      }
      if (previewEmpty) {
        previewEmpty.hidden = true;
      }
      if (previewMeta) {
        previewMeta.textContent = '预览结果会显示在这里，勾选条目后点击“加入爬取队列”即可批量生成文章。';
      }
      setPreviewPanelState(false);
    }

    function createPreviewCard(item, sourceUrl) {
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

    function renderPreviewItems(items, sourceUrl) {
      if (!previewGrid) {
        return;
      }
      previewGrid.innerHTML = '';
      const normalizedItems = Array.isArray(items) ? items : [];
      if (previewMeta) {
        const label = sourceUrl || '当前订阅源';
        previewMeta.textContent = normalizedItems.length > 0
          ? `已预览 ${normalizedItems.length} 条来自 ${label} 的内容，勾选后点击底部“加入爬取队列”即可批量生成。`
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
        previewGrid.appendChild(card);
      });
      setPreviewPanelState(true);
      formatNewsTimeElements(previewGrid);
    }

    async function previewCustomUrl() {
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
        notify(
          data.count > 0 ? `已预览 ${data.count} 条订阅内容` : (data.message || '未抓到可用条目'),
          data.count > 0 ? 'success' : 'warning',
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

    // --- 提交批量任务 ----------------------------------------------------

    async function postCrawlBatch(endpoint, sourceUrl, newsUrls) {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_url: sourceUrl,
          selected_urls: newsUrls,
          news_urls: newsUrls,
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
    }

    async function submitSelection() {
      if (isSubmitting) {
        return;
      }
      const groups = Array.from(selectedBySource.entries()).filter(([, g]) => g.items.size > 0);
      if (groups.length === 0) {
        notify('请先勾选要爬取的新闻', 'error');
        return;
      }
      isSubmitting = true;
      if (selectionSubmit) {
        selectionSubmit.disabled = true;
        selectionSubmit.dataset.originalText = selectionSubmit.querySelector('.btn-label')?.textContent || '加入爬取队列';
        setButtonLabel(selectionSubmit, '提交中…');
        selectionSubmit.classList.add('is-loading');
        setLoadingShellState(selectionSubmit, true);
      }

      let okCount = 0;
      let failCount = 0;
      const failed = [];
      for (const [sourceUrl, group] of groups) {
        const newsUrls = Array.from(group.items.keys());
        try {
          await postCrawlBatch(group.endpoint, sourceUrl, newsUrls);
          okCount += 1;
        } catch (err) {
          failCount += 1;
          failed.push(err.message || '启动失败');
        }
      }

      isSubmitting = false;
      if (selectionSubmit) {
        selectionSubmit.disabled = false;
        setButtonLabel(selectionSubmit, selectionSubmit.dataset.originalText || '加入爬取队列');
        selectionSubmit.classList.remove('is-loading');
        setLoadingShellState(selectionSubmit, false);
      }

      if (okCount > 0) {
        const totalItems = getSelectedCount();
        notify(`已提交 ${okCount} 个批次，共 ${totalItems} 篇文章到爬取队列`, 'success');
        clearSelection();
        // htmx 自带每 2s 轮询，提交后无需手动启动
      }
      if (failCount > 0) {
        notify(`部分批次启动失败：${failed.join('；')}`, 'error');
      }
    }

    // --- 初始化 ---------------------------------------------------------

    function bindInitial() {
      getNewsCards().forEach((card) => {
        bindCheckboxForCard(card);
      });
    }

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
    if (selectionSubmit) {
      selectionSubmit.addEventListener('click', submitSelection);
    }
    if (selectionClear) {
      selectionClear.addEventListener('click', function () {
        clearSelection();
      });
    }

    formatNewsTimeElements(document);
    bindInitial();
    // 爬取队列面板由 htmx 自动轮询，无需手动启动
  });
})();
