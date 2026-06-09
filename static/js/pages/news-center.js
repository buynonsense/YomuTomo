(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    const customUrlInput = document.getElementById('custom-url-input');
    const customUrlSubmit = document.getElementById('custom-url-submit');
    const previewPanel = document.getElementById('rsshub-preview-panel');
    const previewGrid = document.getElementById('rsshub-preview-grid');
    const previewEmpty = document.getElementById('rsshub-preview-empty');
    const previewMeta = document.getElementById('rsshub-preview-meta');
    const crawlButtons = Array.from(document.querySelectorAll('.news-crawl-btn'));

    let pollTimer = null;
    let activeCrawlButton = null;
    const NOTIFIED_TASK_IDS_KEY = 'newsCenterNotifiedTaskIds';

    function getNewsCards() {
      return Array.from(document.querySelectorAll('[data-news-card]'));
    }

    function getCrawlButtons() {
      return Array.from(document.querySelectorAll('.news-crawl-btn'));
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

    function getNotifiedTaskIds() {
      try {
        const raw = sessionStorage.getItem(NOTIFIED_TASK_IDS_KEY);
        if (!raw) {
          return [];
        }

        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed.map((value) => String(value)) : [];
      } catch (error) {
        console.error('读取已通知任务列表失败', error);
        return [];
      }
    }

    function getTaskState() {
      if (!window.TaskState || typeof window.TaskState.readActiveTask !== 'function') {
        return null;
      }

      return window.TaskState.readActiveTask();
    }

    function writeTaskState(taskId, taskType, startedAt) {
      if (!window.TaskState || typeof window.TaskState.writeActiveTask !== 'function') {
        return;
      }

      window.TaskState.writeActiveTask({
        task_id: String(taskId),
        task_type: taskType,
        status: 'processing',
        started_at: startedAt || new Date().toISOString(),
      });
    }

    function clearTaskState() {
      if (!window.TaskState) {
        return;
      }

      if (typeof window.TaskState.clearActiveTask === 'function') {
        window.TaskState.clearActiveTask();
      }

      if (typeof window.TaskState.setNewsNavBusy === 'function') {
        window.TaskState.setNewsNavBusy(false);
      }
    }

    function restoreActiveCrawlButton() {
      if (!activeCrawlButton) {
        return;
      }

      const button = activeCrawlButton;
      activeCrawlButton = null;
      button.disabled = false;
      setButtonLabel(button, button.dataset.originalText || '生成文章');
      button.classList.remove('is-loading');
      setLoadingShellState(button, false);

      const card = button.closest('[data-news-card]');
      if (card) {
        card.classList.remove('is-busy');
      }
    }

    function setTaskProcessing(taskId, taskType, startedAt) {
      writeTaskState(taskId, taskType, startedAt);

      if (window.TaskState && typeof window.TaskState.setNewsNavBusy === 'function') {
        window.TaskState.setNewsNavBusy(true);
      }
    }

    function keepTaskProcessing(taskId, taskType) {
      const activeTask = getTaskState();

      if (activeTask && activeTask.task_id) {
        if (window.TaskState && typeof window.TaskState.setNewsNavBusy === 'function') {
          window.TaskState.setNewsNavBusy(true);
        }
        return;
      }

      writeTaskState(taskId, taskType, new Date().toISOString());

      if (window.TaskState && typeof window.TaskState.setNewsNavBusy === 'function') {
        window.TaskState.setNewsNavBusy(true);
      }
    }

    function restoreBusyStateFromStorage() {
      const activeTask = getTaskState();
      if (activeTask && activeTask.status === 'processing') {
        if (window.TaskState && typeof window.TaskState.setNewsNavBusy === 'function') {
          window.TaskState.setNewsNavBusy(true);
        }
        return true;
      }

      clearTaskState();
      return false;
    }

    function makeNotificationKey(taskId, status, message) {
      if (!taskId || !status) {
        return '';
      }

      return [String(taskId), String(status), String(message || '').trim()].join('::');
    }

    function hasNotifiedTask(taskId, status, message) {
      const key = makeNotificationKey(taskId, status, message);
      if (!key) {
        return false;
      }

      return getNotifiedTaskIds().includes(key);
    }

    function markTaskNotified(taskId, status, message) {
      const key = makeNotificationKey(taskId, status, message);
      if (!key) {
        return;
      }

      try {
        const current = new Set(getNotifiedTaskIds());
        current.add(key);
        sessionStorage.setItem(NOTIFIED_TASK_IDS_KEY, JSON.stringify(Array.from(current)));
      } catch (error) {
        console.error('保存已通知任务列表失败', error);
      }
    }

    function getProcessedArticlesCount(data) {
      if (!data || typeof data.processed_articles !== 'number') {
        return 0;
      }

      return data.processed_articles;
    }

    function getToastMessage(data, fallbackMessage) {
      if (data && typeof data.message === 'string') {
        const message = data.message.trim();
        if (message) {
          return message;
        }
      }

      return fallbackMessage;
    }

    function setButtonsDisabled(disabled) {
      getCrawlButtons().forEach((button) => {
        button.disabled = disabled;
      });
      if (customUrlSubmit) {
        customUrlSubmit.disabled = disabled;
      }
      if (customUrlInput) {
        customUrlInput.disabled = disabled;
      }
      getNewsCards().forEach((card) => {
        card.classList.toggle('is-busy', disabled);
      });
    }

    function handleCrawlStatus(data) {
      const activeTask = getTaskState();
      const taskId = data && data.task_id ? String(data.task_id) : (activeTask && activeTask.task_id) || '';
      const taskType = (data && data.task_type) || (activeTask && activeTask.task_type) || 'news_crawl';

      if (data.status === 'processing') {
        keepTaskProcessing(taskId, taskType);
        setButtonsDisabled(true);
        return;
      }

      stopPolling();
      restoreActiveCrawlButton();
      setButtonsDisabled(false);
      clearTaskState();

      if (data.status === 'completed') {
        const message = getToastMessage(data, data.processed_articles <= 0 ? '新闻生成失败，请稍后重试。' : '新闻生成完成，可以前往“我的文章”查看。');

        if (getProcessedArticlesCount(data) <= 0) {
          if (taskId && !hasNotifiedTask(taskId, data.status, message)) {
            markTaskNotified(taskId, data.status, message);
            notify(message, 'error');
          }
          return;
        }

        if (taskId && !hasNotifiedTask(taskId, data.status, message)) {
          markTaskNotified(taskId, data.status, message);
          notify(message, 'success');
          window.setTimeout(() => window.location.reload(), 1500);
        }
        return;
      }

      if (data.status === 'failed') {
        const message = getToastMessage(data, '新闻生成失败，请稍后重试。');
        if (taskId && hasNotifiedTask(taskId, data.status, message)) {
          return;
        }
        if (taskId) {
          markTaskNotified(taskId, data.status, message);
        }
        notify(message, 'error');
        return;
      }

      restoreActiveCrawlButton();
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

    function stopPolling() {
      if (pollTimer) {
        window.clearInterval(pollTimer);
        pollTimer = null;
      }
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

    async function fetchCrawlStatus() {
      const response = await fetch('/crawl_status');
      let data = null;

      try {
        data = await response.json();
      } catch (error) {
        throw new Error('新闻任务状态响应解析失败');
      }

      if (!response.ok) {
        throw new Error((data && data.message) || (data && data.error) || '获取新闻任务状态失败');
      }

      return data;
    }

    async function refreshStatus() {
      try {
        const data = await fetchCrawlStatus();

        handleCrawlStatus(data);

        if (data.status === 'processing') {
          startPolling();
        }
      } catch (error) {
        console.error('同步新闻任务状态失败', error);
      }
    }

    function startPolling() {
      if (pollTimer) {
        return;
      }

      pollTimer = window.setInterval(async () => {
        try {
          const data = await fetchCrawlStatus();

          handleCrawlStatus(data);
        } catch (error) {
          console.error('轮询新闻任务状态失败', error);
        }
      }, 2000);
    }

    async function startCrawl(button) {
      const card = button.closest('[data-news-card]');
      const newsUrl = card ? card.dataset.newsUrl || '' : '';
      const newsTitle = card ? card.dataset.newsTitle || '这条新闻' : '这条新闻';
      const sourceUrl = card ? card.dataset.newsSourceUrl || '' : '';
      const endpoint = card ? card.dataset.crawlEndpoint || '/crawl_news' : '/crawl_news';

      if (!newsUrl) {
        notify('未找到可用的新闻链接', 'error');
        return;
      }

      if (!sourceUrl) {
        notify('未找到可用的订阅源链接', 'error');
        return;
      }

      setButtonsDisabled(true);
      activeCrawlButton = button;
      button.disabled = true;
      button.dataset.originalText = button.querySelector('.btn-label')?.textContent || button.textContent;
      setButtonLabel(button, '处理中…');
      button.classList.add('is-loading');
      setLoadingShellState(button, true);
      card.classList.add('is-busy');

      try {
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            source_url: sourceUrl,
            selected_urls: [newsUrl],
            news_url: newsUrl
          })
        });
        const data = await response.json();

        if (!response.ok || !data.success) {
          throw new Error(data.message || data.error || '启动失败');
        }

        setTaskProcessing(data.task_id, endpoint === '/crawl_custom_url' ? 'custom_url_crawl' : 'news_crawl', new Date().toISOString());
        notify(`${newsTitle} 已开始生成文章`, 'success');
        startPolling();
      } catch (error) {
        console.error('启动新闻爬取失败', error);
        notify(error.message || '启动失败', 'error');
        restoreActiveCrawlButton();
        setButtonsDisabled(false);
      } finally {
        if (!pollTimer) {
          if (activeCrawlButton === button) {
            restoreActiveCrawlButton();
          } else {
            button.disabled = false;
            setButtonLabel(button, button.dataset.originalText || '生成文章');
            button.classList.remove('is-loading');
            setLoadingShellState(button, false);
            card.classList.remove('is-busy');
          }
        }
      }
    }

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
        previewMeta.textContent = '预览结果会显示在这里，点击条目上的按钮即可生成文章。';
      }
      setPreviewPanelState(false);
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

      const actions = document.createElement('div');
      actions.className = 'news-card__actions';

      const shell = document.createElement('div');
      shell.className = 'btn-loading-shell';

      const ring = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      ring.setAttribute('class', 'loading-ring');
      ring.setAttribute('viewBox', '0 0 120 52');
      ring.setAttribute('aria-hidden', 'true');
      ring.setAttribute('focusable', 'false');
      ring.setAttribute('preserveAspectRatio', 'none');

      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('x', '2');
      rect.setAttribute('y', '2');
      rect.setAttribute('width', '116');
      rect.setAttribute('height', '48');
      rect.setAttribute('rx', '24');
      rect.setAttribute('ry', '24');
      ring.appendChild(rect);

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn-primary news-crawl-btn btn-with-loading-ring';
      button.innerHTML = '<span class="btn-label">生成文章</span>';
      button.addEventListener('click', function () {
        startCrawl(button);
      });

      shell.appendChild(ring);
      shell.appendChild(button);
      actions.appendChild(shell);

      article.appendChild(top);
      article.appendChild(title);
      article.appendChild(outlineText);
      article.appendChild(actions);

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
          ? `已预览 ${normalizedItems.length} 条来自 ${label} 的内容，点击“生成文章”即可入库。`
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
          headers: {
            'Content-Type': 'application/json'
          },
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
        setButtonLabel(customUrlSubmit, customUrlSubmit.dataset.originalText || '预览订阅源');
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

    function initializeTaskState() {
      if (restoreBusyStateFromStorage()) {
        setButtonsDisabled(true);
        startPolling();
        return;
      }

      refreshStatus();
    }

    formatNewsTimeElements(document);

    crawlButtons.forEach((button) => {
      button.addEventListener('click', function () {
        startCrawl(button);
      });
    });

    if (customUrlSubmit) {
      customUrlSubmit.addEventListener('click', function () {
        previewCustomUrl();
      });
    }

    initializeTaskState();
  });
})();
