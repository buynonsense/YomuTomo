(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    const toggleButton = document.getElementById('global-notifications-btn');
    const badge = document.getElementById('global-notifications-badge');
    const overlay = document.getElementById('global-notifications-overlay');
    const closeButton = document.getElementById('global-notifications-close');
    const list = document.getElementById('global-notifications-list');
    const markAllButton = document.getElementById('global-notifications-mark-all');

    if (!toggleButton || !overlay || !closeButton || !list || !markAllButton || !badge) {
      return;
    }

    let isOpen = false;

    function setBadgeCount(count) {
      const unreadCount = Number.isFinite(count) ? Math.max(0, count) : 0;
      if (unreadCount > 0) {
        badge.hidden = false;
        badge.textContent = String(unreadCount);
      } else {
        badge.hidden = true;
        badge.textContent = '0';
      }
    }

    function formatTime(value) {
      if (!value) {
        return '';
      }
      try {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
          return '';
        }
        return date.toLocaleString('zh-CN', { hour12: false });
      } catch (error) {
        console.error('格式化通知时间失败', error);
        return '';
      }
    }

    function buildNotificationLink(item) {
      const rawUrl = typeof item.source_url === 'string' && item.source_url ? item.source_url : '';
      if (!rawUrl) {
        return '';
      }

      try {
        const url = new URL(rawUrl, window.location.origin);
        if (item.type === 'article_generated' && item.source_task_id) {
          url.searchParams.set('highlight_article', String(item.source_task_id));
          url.searchParams.set('highlight_notification', String(item.id));
        }
        if (item.type === 'settings_saved') {
          url.searchParams.set('open_settings', 'ai');
          url.searchParams.set('highlight_notification', String(item.id));
        }
        if (item.type === 'system_error') {
          url.searchParams.set('highlight_notification', String(item.id));
        }
        return url.pathname + url.search + url.hash;
      } catch (error) {
        console.error('构建通知链接失败', error);
        return rawUrl;
      }
    }

    function handleNotificationClick(event) {
      const article = event.target.closest('.notifications-item');
      if (!article) {
        return;
      }

      const targetUrl = article.dataset.notificationUrl || '';
      if (!targetUrl) {
        return;
      }

      window.location.href = targetUrl;
    }

    function renderItems(items) {
      if (!Array.isArray(items) || items.length === 0) {
        list.innerHTML = '<div class="notifications-empty">暂无通知</div>';
        return;
      }

      list.innerHTML = items.map((item) => {
        const unreadClass = item.is_read ? '' : ' is-unread';
        const timeText = formatTime(item.created_at);
        const url = buildNotificationLink(item);
        const action = url ? '<span class="notifications-item__action">查看</span>' : '';
        return `
          <article class="notifications-item${unreadClass}" data-notification-id="${item.id}" data-notification-url="${url}">
            <div class="notifications-item__meta">
              <span class="notifications-item__type">${item.type}</span>
              <span class="notifications-item__time">${timeText}</span>
            </div>
            <h4 class="notifications-item__title">${item.title}</h4>
            <p class="notifications-item__message">${item.message}</p>
            <div class="notifications-item__footer">${action}</div>
          </article>
        `;
      }).join('');
    }

    async function fetchUnreadCount() {
      const response = await fetch('/notifications/unread-count');
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.message || '获取未读通知失败');
      }
      setBadgeCount(data.unread_count || 0);
    }

    async function loadNotifications() {
      const response = await fetch('/notifications');
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.message || '获取通知失败');
      }
      renderItems(data.items || []);
      setBadgeCount(data.unread_count || 0);
    }

    async function markAllRead() {
      const response = await fetch('/notifications/mark-read', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ all: true }),
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.message || '标记已读失败');
      }
      setBadgeCount(0);
      await loadNotifications();
    }

    function openPanel() {
      overlay.hidden = false;
      overlay.classList.add('is-open');
      toggleButton.setAttribute('aria-expanded', 'true');
      isOpen = true;
    }

    function closePanel() {
      overlay.classList.remove('is-open');
      overlay.hidden = true;
      toggleButton.setAttribute('aria-expanded', 'false');
      isOpen = false;
    }

    async function openAndRefresh() {
      try {
        openPanel();
        await loadNotifications();
        await markAllRead();
      } catch (error) {
        console.error('打开通知面板失败', error);
        if (typeof showToast === 'function') {
          showToast(error.message || '打开通知面板失败', 'error');
        }
      }
    }

    toggleButton.addEventListener('click', function () {
      if (isOpen) {
        closePanel();
        return;
      }
      void openAndRefresh();
    });

    closeButton.addEventListener('click', closePanel);
    overlay.addEventListener('click', function (event) {
      if (event.target === overlay) {
        closePanel();
      }
    });
    markAllButton.addEventListener('click', function () {
      void markAllRead();
    });

    list.addEventListener('click', handleNotificationClick);
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && isOpen) {
        closePanel();
      }
    });

    void fetchUnreadCount().catch((error) => {
      console.error('初始化未读通知数失败', error);
    });
  });
})();
