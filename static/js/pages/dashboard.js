(function () {
  'use strict';

  function formatTime(value) {
    if (!window.Utils || typeof window.Utils.formatDateTime !== 'function') {
      return '';
    }

    return window.Utils.formatDateTime(value);
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-article-updated-at]').forEach(function (element) {
      const value = element.getAttribute('data-article-updated-at');
      const timeText = formatTime(value);
      element.textContent = '更新：' + timeText;
    });
  });
})();
