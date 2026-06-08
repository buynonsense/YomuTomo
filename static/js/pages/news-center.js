(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    const customUrlInput = document.getElementById('custom-url-input');
    const customUrlSubmit = document.getElementById('custom-url-submit');
    const cards = Array.from(document.querySelectorAll('[data-news-card]'));
    const crawlButtons = Array.from(document.querySelectorAll('.news-crawl-btn'));

    let pollTimer = null;
    const NOTIFIED_TASK_IDS_KEY = 'newsCenterNotifiedTaskIds';

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
      crawlButtons.forEach((button) => {
        button.disabled = disabled;
      });
      if (customUrlSubmit) {
        customUrlSubmit.disabled = disabled;
      }
      if (customUrlInput) {
        customUrlInput.disabled = disabled;
      }
      cards.forEach((card) => {
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

      if (!newsUrl) {
        notify('未找到可用的新闻链接', 'error');
        return;
      }

      setButtonsDisabled(true);
      button.disabled = true;
      button.dataset.originalText = button.querySelector('.btn-label')?.textContent || button.textContent;
      setButtonLabel(button, '处理中…');
      button.classList.add('is-loading');
      setLoadingShellState(button, true);
      card.classList.add('is-busy');

      try {
        const response = await fetch('/crawl_news', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ news_url: newsUrl })
        });
        const data = await response.json();

        if (!response.ok || !data.success) {
          throw new Error(data.message || data.error || '启动失败');
        }

        setTaskProcessing(data.task_id, 'news_crawl', new Date().toISOString());
        notify(`${newsTitle} 已开始生成文章`, 'success');
        startPolling();
      } catch (error) {
        console.error('启动新闻爬取失败', error);
        notify(error.message || '启动失败', 'error');
        setButtonsDisabled(false);
        setButtonLabel(button, button.dataset.originalText || '生成文章');
        button.classList.remove('is-loading');
        setLoadingShellState(button, false);
        card.classList.remove('is-busy');
      } finally {
        if (!pollTimer) {
          button.disabled = false;
          setButtonLabel(button, button.dataset.originalText || '生成文章');
          button.classList.remove('is-loading');
          setLoadingShellState(button, false);
          card.classList.remove('is-busy');
        }
      }
    }

    async function startCustomUrlCrawl() {
      const customUrl = customUrlInput ? customUrlInput.value.trim() : '';
      if (!customUrl) {
        notify('请先输入一个 URL', 'error');
        return;
      }

      setButtonsDisabled(true);
      customUrlSubmit.dataset.originalText = customUrlSubmit.querySelector('.btn-label')?.textContent || customUrlSubmit.textContent;
      setButtonLabel(customUrlSubmit, '处理中…');
      customUrlSubmit.classList.add('is-loading');
      setLoadingShellState(customUrlSubmit, true);

      try {
        const response = await fetch('/crawl_custom_url', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ url: customUrl })
        });
        const data = await response.json();

        if (!response.ok || !data.success) {
          throw new Error(data.message || data.error || '启动失败');
        }

        setTaskProcessing(data.task_id, 'custom_url_crawl', new Date().toISOString());
        notify('自定义 URL 已开始处理', 'success');
        startPolling();
      } catch (error) {
        console.error('启动自定义 URL 失败', error);
        notify(error.message || '启动失败', 'error');
        setButtonsDisabled(false);
        setButtonLabel(customUrlSubmit, customUrlSubmit.dataset.originalText || '抓取并生成');
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

    crawlButtons.forEach((button) => {
      button.addEventListener('click', function () {
        startCrawl(button);
      });
    });

    if (customUrlSubmit) {
      customUrlSubmit.addEventListener('click', function () {
        startCustomUrlCrawl();
      });
    }

    initializeTaskState();
  });
})();
