(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    const toggleButton = document.getElementById('global-notifications-btn');
    const badge = document.getElementById('global-notifications-badge');
    const overlay = document.getElementById('global-notifications-overlay');
    const closeButton = document.getElementById('global-notifications-close');
    const list = document.getElementById('global-notifications-list');
    const deleteAllButton = document.getElementById('global-notifications-delete-all');

    if (!toggleButton || !overlay || !closeButton || !list || !deleteAllButton || !badge) {
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
      if (!window.Utils || typeof window.Utils.formatDateTime !== 'function') {
        return '';
      }

      try {
        return window.Utils.formatDateTime(value);
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

    async function deleteNotifications(notificationId) {
      const body = notificationId ? { notification_id: notificationId } : { all: true };
      const response = await fetch('/notifications/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.message || '删除通知失败');
      }
      await loadNotifications();
      const unreadResponse = await fetch('/notifications/unread-count');
      const unreadData = await unreadResponse.json();
      if (unreadResponse.ok && unreadData.success) {
        setBadgeCount(unreadData.unread_count || 0);
      }
    }

    function handleNotificationActionClick(event) {
      const clearButton = event.target.closest('.notifications-item__clear');
      if (clearButton) {
        event.preventDefault();
        event.stopPropagation();
        const article = clearButton.closest('.notifications-item');
        const notificationId = article ? article.dataset.notificationId : '';
        if (!notificationId) {
          return;
        }
        void deleteNotifications(notificationId).catch((error) => {
          console.error('删除单条通知失败', error);
          if (typeof showToast === 'function') {
            showToast(error.message || '删除通知失败', 'error');
          }
        });
        return;
      }

      const actionButton = event.target.closest('.notifications-item__action');
      if (actionButton) {
        event.preventDefault();
        event.stopPropagation();
        const article = actionButton.closest('.notifications-item');
        const targetUrl = article ? article.dataset.notificationUrl || '' : '';
        if (!targetUrl) {
          return;
        }

        window.location.href = targetUrl;
        return;
      }

      const article = event.target.closest('.notifications-item');
      if (!article) {
        return;
      }

      const targetUrl = article.dataset.notificationUrl || '';
      if (!targetUrl) {
        return;
      }

      if (article.contains(event.target)) {
        window.location.href = targetUrl;
      }
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
        const action = url ? '<button type="button" class="notifications-item__action">查看</button>' : '';
        const clearButton = '<button type="button" class="notifications-item__clear">清除</button>';
        return `
          <article class="notifications-item${unreadClass}" data-notification-id="${item.id}" data-notification-url="${url}" tabindex="0" role="button" aria-label="通知 ${item.title}">
            <div class="notifications-item__meta">
              <span class="notifications-item__type">${item.type}</span>
              <span class="notifications-item__time">${timeText}</span>
            </div>
            <h4 class="notifications-item__title">${item.title}</h4>
            <p class="notifications-item__message">${item.message}</p>
            <div class="notifications-item__footer">${action}${clearButton}</div>
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

    async function deleteAllNotifications() {
      const response = await fetch('/notifications/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ all: true }),
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.message || '清除通知失败');
      }
      await loadNotifications();
      setBadgeCount(0);
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
        await fetch('/notifications/mark-read', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ all: true }),
        });
        await fetchUnreadCount();
        await loadNotifications();
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
    deleteAllButton.addEventListener('click', function () {
      void deleteAllNotifications().catch((error) => {
        console.error('一键清除通知失败', error);
        if (typeof showToast === 'function') {
          showToast(error.message || '清除通知失败', 'error');
        }
      });
    });

    list.addEventListener('click', handleNotificationActionClick);
    list.addEventListener('keydown', function (event) {
      if (event.key !== 'Enter' && event.key !== ' ') {
        return;
      }

      const clearButton = event.target.closest('.notifications-item__clear');
      if (clearButton) {
        event.preventDefault();
        clearButton.click();
        return;
      }

      const actionButton = event.target.closest('.notifications-item__action');
      if (actionButton) {
        event.preventDefault();
        actionButton.click();
        return;
      }

      const target = event.target.closest('.notifications-item');
      if (!target) {
        return;
      }

      const targetUrl = target.dataset.notificationUrl || '';
      if (targetUrl) {
        window.location.href = targetUrl;
      }
    });
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
