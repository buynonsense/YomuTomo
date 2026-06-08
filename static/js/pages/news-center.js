(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    const customUrlInput = document.getElementById('custom-url-input');
    const customUrlSubmit = document.getElementById('custom-url-submit');
    const cards = Array.from(document.querySelectorAll('[data-news-card]'));
    const crawlButtons = Array.from(document.querySelectorAll('.news-crawl-btn'));

    let pollTimer = null;
    const ACTIVE_TASK_ID_KEY = 'newsCenterActiveTaskId';
    const NOTIFIED_TASK_IDS_KEY = 'newsCenterNotifiedTaskIds';

    function getActiveTaskId() {
      try {
        return sessionStorage.getItem(ACTIVE_TASK_ID_KEY) || '';
      } catch (error) {
        console.error('读取新闻任务 ID 失败', error);
        return '';
      }
    }

    function setActiveTaskId(taskId) {
      try {
        if (taskId) {
          sessionStorage.setItem(ACTIVE_TASK_ID_KEY, String(taskId));
        }
      } catch (error) {
        console.error('保存新闻任务 ID 失败', error);
      }
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

    function hasNotifiedTask(taskId) {
      if (!taskId) {
        return false;
      }

      return getNotifiedTaskIds().includes(String(taskId));
    }

    function markTaskNotified(taskId) {
      if (!taskId) {
        return;
      }

      try {
        const current = new Set(getNotifiedTaskIds());
        current.add(String(taskId));
        sessionStorage.setItem(NOTIFIED_TASK_IDS_KEY, JSON.stringify(Array.from(current)));
      } catch (error) {
        console.error('保存已通知任务列表失败', error);
      }
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
      const taskId = data && data.task_id ? String(data.task_id) : getActiveTaskId();

      if (data.status === 'processing') {
        setButtonsDisabled(true);
        return;
      }

      stopPolling();
      setButtonsDisabled(false);

      if (data.status === 'completed') {
        if (taskId && !hasNotifiedTask(taskId)) {
          markTaskNotified(taskId);
          notify('新闻生成完成，可以前往“我的文章”查看。', 'success');
          window.setTimeout(() => window.location.reload(), 1500);
        }
        return;
      }

      if (data.status === 'failed') {
        notify('新闻生成失败，请稍后重试。', 'error');
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

    async function refreshStatus() {
      try {
        const response = await fetch('/crawl_status');
        const data = await response.json();

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
          const response = await fetch('/crawl_status');
          const data = await response.json();

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
      button.dataset.originalText = button.textContent;
      button.textContent = '处理中…';
      button.classList.add('is-loading');
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

        setActiveTaskId(data.task_id);
        notify(`${newsTitle} 已开始生成文章`, 'success');
        startPolling();
      } catch (error) {
        console.error('启动新闻爬取失败', error);
        notify(error.message || '启动失败', 'error');
        setButtonsDisabled(false);
        button.textContent = button.dataset.originalText || '生成文章';
        button.classList.remove('is-loading');
        card.classList.remove('is-busy');
      } finally {
        if (!pollTimer) {
          button.disabled = false;
          button.textContent = button.dataset.originalText || '生成文章';
          button.classList.remove('is-loading');
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
      customUrlSubmit.dataset.originalText = customUrlSubmit.textContent;
      customUrlSubmit.textContent = '处理中…';
      customUrlSubmit.classList.add('is-loading');

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

        setActiveTaskId(data.task_id);
        notify('自定义 URL 已开始处理', 'success');
        startPolling();
      } catch (error) {
        console.error('启动自定义 URL 失败', error);
        notify(error.message || '启动失败', 'error');
        setButtonsDisabled(false);
        customUrlSubmit.textContent = customUrlSubmit.dataset.originalText || '抓取并生成';
        customUrlSubmit.classList.remove('is-loading');
      }
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

    refreshStatus();
  });
})();
