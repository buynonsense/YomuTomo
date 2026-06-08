(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    const statusEl = document.getElementById('news-center-status');
    const refreshBtn = document.getElementById('refresh-news-btn');
    const customUrlInput = document.getElementById('custom-url-input');
    const customUrlSubmit = document.getElementById('custom-url-submit');
    const cards = Array.from(document.querySelectorAll('[data-news-card]'));
    const crawlButtons = Array.from(document.querySelectorAll('.news-crawl-btn'));

    if (!statusEl) {
      return;
    }

    let pollTimer = null;

    function setStatus(message, state) {
      statusEl.textContent = message;
      statusEl.classList.remove('is-processing', 'is-success', 'is-error');
      if (state === 'processing') {
        statusEl.classList.add('is-processing');
      } else if (state === 'success') {
        statusEl.classList.add('is-success');
      } else if (state === 'error') {
        statusEl.classList.add('is-error');
      }
    }

    function setButtonsDisabled(disabled) {
      crawlButtons.forEach((button) => {
        button.disabled = disabled;
      });
      if (refreshBtn) {
        refreshBtn.disabled = disabled;
      }
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

        if (data.status === 'processing') {
          const progress = data.total_articles > 0 ? ` (${data.processed_articles}/${data.total_articles})` : '';
          setStatus(`后台处理中${progress}，完成后会自动更新。`, 'processing');
          setButtonsDisabled(true);
          startPolling();
          return;
        }

        stopPolling();
        setButtonsDisabled(false);

        if (data.status === 'completed') {
          setStatus('最近一次新闻生成已完成，可以继续选择下一条。', 'success');
        } else if (data.status === 'failed') {
          setStatus('最近一次新闻生成失败，请重新选择新闻重试。', 'error');
        } else {
          setStatus('请选择一条新闻开始生成文章。', 'idle');
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

          if (data.status === 'processing') {
            const progress = data.total_articles > 0 ? ` (${data.processed_articles}/${data.total_articles})` : '';
            setStatus(`后台处理中${progress}，完成后会自动更新。`, 'processing');
            setButtonsDisabled(true);
            return;
          }

          stopPolling();
          setButtonsDisabled(false);

          if (data.status === 'completed') {
            setStatus('新闻生成完成，可以前往“我的文章”查看。', 'success');
            notify('新闻生成完成，可以前往“我的文章”查看。', 'success');
          } else if (data.status === 'failed') {
            setStatus('新闻生成失败，请稍后重试。', 'error');
            notify('新闻生成失败，请稍后重试。', 'error');
          } else {
            setStatus('请选择一条新闻开始生成文章。', 'idle');
          }
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
      setStatus(`正在启动：${newsTitle}`, 'processing');
      button.disabled = true;

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

        notify(`${newsTitle} 已开始生成文章`, 'success');
        setStatus(`${newsTitle} 已提交后台生成`, 'processing');
        startPolling();
      } catch (error) {
        console.error('启动新闻爬取失败', error);
        notify(error.message || '启动失败', 'error');
        setStatus(`启动失败：${newsTitle}`, 'error');
        setButtonsDisabled(false);
      } finally {
        if (!pollTimer) {
          button.disabled = false;
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
      setStatus('正在启动自定义 URL 抓取…', 'processing');

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

        notify('自定义 URL 已开始处理', 'success');
        setStatus('自定义 URL 已提交后台生成', 'processing');
        startPolling();
      } catch (error) {
        console.error('启动自定义 URL 失败', error);
        notify(error.message || '启动失败', 'error');
        setStatus('自定义 URL 启动失败', 'error');
        setButtonsDisabled(false);
      }
    }

    crawlButtons.forEach((button) => {
      button.addEventListener('click', function () {
        startCrawl(button);
      });
    });

    if (refreshBtn) {
      refreshBtn.addEventListener('click', function () {
        window.location.reload();
      });
    }

    if (customUrlSubmit) {
      customUrlSubmit.addEventListener('click', function () {
        startCustomUrlCrawl();
      });
    }

    refreshStatus();
  });
})();
