(function () {
  var STORAGE_KEY = 'yomutomo.active_task';
  var NEWS_NAV_SELECTOR = '[data-nav-news-center], .global-nav__link[href="/news_center"]';
  var BUSY_CLASS = 'is-busy';

  function getStorage() {
    try {
      if (typeof window === 'undefined' || !window.sessionStorage) {
        return null;
      }
      return window.sessionStorage;
    } catch (error) {
      console.error('TaskState: 无法访问 sessionStorage', error);
      return null;
    }
  }

  function readJson(value) {
    if (!value) {
      return null;
    }

    try {
      return JSON.parse(value);
    } catch (error) {
      console.error('TaskState: 解析任务状态失败', error);
      return null;
    }
  }

  function getNewsNavLink() {
    return document.querySelector(NEWS_NAV_SELECTOR);
  }

  function isTaskObject(task) {
    return !!task && typeof task === 'object';
  }

  function normalizeTask(task) {
    if (!isTaskObject(task)) {
      return null;
    }

    var normalized = {
      task_id: task.task_id,
      task_type: task.task_type,
      status: task.status,
      started_at: task.started_at,
    };

    if (!normalized.task_id || !normalized.task_type || !normalized.status || !normalized.started_at) {
      return null;
    }

    return normalized;
  }

  function updateNewsNavBusy(isBusy) {
    var link = getNewsNavLink();
    if (!link) {
      return;
    }

    link.classList.toggle(BUSY_CLASS, !!isBusy);
    link.setAttribute('aria-busy', isBusy ? 'true' : 'false');
  }

  function readActiveTask() {
    var storage = getStorage();
    if (!storage) {
      return null;
    }

    return readJson(storage.getItem(STORAGE_KEY));
  }

  function writeActiveTask(task) {
    var storage = getStorage();
    if (!storage) {
      return;
    }

    var normalized = normalizeTask(task);
    if (!normalized) {
      clearActiveTask();
      return;
    }

    try {
      storage.setItem(STORAGE_KEY, JSON.stringify(normalized));
    } catch (error) {
      console.error('TaskState: 保存任务状态失败', error);
    }
  }

  function clearActiveTask() {
    var storage = getStorage();
    if (!storage) {
      return;
    }

    try {
      storage.removeItem(STORAGE_KEY);
    } catch (error) {
      console.error('TaskState: 清除任务状态失败', error);
    }
  }

  function setNewsNavBusy(isBusy) {
    updateNewsNavBusy(isBusy);
  }

  function syncNewsNavFromStorage() {
    var activeTask = readActiveTask();
    updateNewsNavBusy(!!activeTask && activeTask.status === 'processing');
  }

  // 监听 htmx 派发的 queue-update 事件（由 /crawl_queue/partial 响应头触发），
  // 保持导航"新闻中心"项的繁忙态与服务端爬取队列一致。
  function bindHtmxQueueUpdate() {
    if (typeof document === 'undefined') {
      return;
    }
    document.addEventListener('queue-update', function (event) {
      var detail = event && event.detail ? event.detail : {};
      var active = Number(detail.activeCount || 0);
      updateNewsNavBusy(active > 0);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindHtmxQueueUpdate);
  } else {
    bindHtmxQueueUpdate();
  }

  window.TaskState = {
    readActiveTask: readActiveTask,
    writeActiveTask: writeActiveTask,
    clearActiveTask: clearActiveTask,
    setNewsNavBusy: setNewsNavBusy,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', syncNewsNavFromStorage, { once: true });
  } else {
    syncNewsNavFromStorage();
  }
})();
