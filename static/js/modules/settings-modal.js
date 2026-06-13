/**
 * 统一设置弹窗 - Alpine.js 版本
 *
 * 状态机集中在 Alpine x-data 工厂 settingsModal()：
 * - isOpen / activeTab / isSubmitting 等响应式状态
 * - open/close/switchTab/saveUserSettings 等方法
 * - 通过 window.openSettingsModal(tab) 提供对外的同步 API
 *
 * 仍保留的功能：
 * - 关闭后恢复 body 滚动
 * - 顶部 ESC 关闭
 * - 模态外点击关闭
 * - 监听 ai-config-saved / ai-config-failed 同步状态徽标和提示 toast
 */

(function () {
  'use strict';

  function getAiConfigManager() {
    if (window.aiConfigManager) {
      return window.aiConfigManager;
    }
    if (window.AIConfigManager) {
      window.aiConfigManager = new AIConfigManager();
      return window.aiConfigManager;
    }
    return null;
  }

  function showToast(message, type) {
    if (typeof window.showToast === 'function') {
      window.showToast(message, type);
      return;
    }
    if (type === 'error') {
      console.error(message);
    } else {
      console.log(message);
    }
  }

  function syncHiddenModel(model) {
    try {
      const hiddenModel = document.getElementById('model');
      if (hiddenModel) {
        hiddenModel.value = model || '';
      }
      sessionStorage.setItem('processing_model', model || '');
    } catch (error) {
      console.error('更新隐藏模型失败:', error);
    }
  }

  function updateStatusAfterSave(success, modelOrError) {
    const manager = getAiConfigManager();
    const statusIcon = document.getElementById('status-icon');
    const statusText = document.getElementById('status-text');
    const statusDiv = document.getElementById('config-status');
    if (!manager || !statusIcon || !statusText) {
      return;
    }
    manager.updateStatus(success, success ? modelOrError : '');
    if (statusDiv) {
      statusDiv.classList.toggle('error', !success);
    }
  }

  // Alpine 工厂
  window.settingsModal = function settingsModal() {
    return {
      isOpen: false,
      activeTab: 'ai',
      isSubmitting: false,
      aiConfigLoaded: false,
      closeTimer: null,
      bodyRestoreTimer: null,

      init() {
        // 让 init 阶段的 init 调用能跑：populate 字段、绑定 ESC 等
        this._populateAiFields();
      },

      _populateAiFields() {
        const manager = getAiConfigManager();
        if (!manager) {
          return;
        }
        const config = manager.config || {};
        const apiKeyInput = document.getElementById('modal-api-key');
        const baseUrlInput = document.getElementById('modal-base-url');
        const modelInput = document.getElementById('modal-model');
        if (apiKeyInput) {
          apiKeyInput.value = config.apiKey || '';
        }
        if (baseUrlInput) {
          baseUrlInput.value = config.baseUrl || 'https://api.openai.com/v1';
        }
        if (modelInput) {
          modelInput.value = config.model || '';
        }
        if (!this.aiConfigLoaded) {
          this.aiConfigLoaded = true;
          manager.loadFromBackend();
        }
      },

      open(tabName) {
        const targetTab = tabName === 'user' ? 'user' : 'ai';
        this.activeTab = targetTab;
        if (this.isOpen) {
          if (targetTab === 'user') {
            this._loadUserLevel();
          }
          return;
        }
        // 取消任何正在进行的关闭动画
        if (this.closeTimer) {
          clearTimeout(this.closeTimer);
          this.closeTimer = null;
        }
        if (this.bodyRestoreTimer) {
          clearTimeout(this.bodyRestoreTimer);
          this.bodyRestoreTimer = null;
        }
        this._populateAiFields();
        if (targetTab === 'user') {
          this._loadUserLevel();
        }
        this.isOpen = true;
        // 锁滚动
        document.body.style.overflow = 'hidden';
        document.body.style.overflowX = 'hidden';
        document.body.style.overflowY = 'hidden';
      },

      close() {
        if (!this.isOpen) {
          return;
        }
        this.isOpen = false;
        this.closeTimer = setTimeout(() => {
          this.closeTimer = null;
        }, 300);
        this.bodyRestoreTimer = setTimeout(() => {
          this.bodyRestoreTimer = null;
          document.body.style.overflow = '';
          document.body.style.overflowX = '';
          document.body.style.overflowY = '';
        }, 350);
      },

      switchTab(tabName) {
        const target = tabName === 'user' ? 'user' : 'ai';
        this.activeTab = target;
        if (target === 'user') {
          this._loadUserLevel();
        }
      },

      _loadUserLevel() {
        const select = document.getElementById('user-level');
        if (!select) {
          return;
        }
        fetch('/get_user_level')
          .then((response) => response.json())
          .then((data) => {
            if (data && data.level) {
              select.value = String(data.level);
            }
          })
          .catch((error) => {
            console.error('获取用户等级失败:', error);
          });
      },

      async saveUserSettings() {
        const select = document.getElementById('user-level');
        if (!select) {
          return;
        }
        const level = Number.parseInt(select.value, 10);
        if (!Number.isFinite(level)) {
          showToast('请选择有效的用户等级', 'warning');
          return;
        }
        this.isSubmitting = true;
        try {
          const response = await fetch('/update_user_level', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ level })
          });
          const result = await response.json();
          if (!response.ok) {
            showToast(`保存失败：${result.error || '未知错误'}`, 'error');
            return;
          }
          showToast('用户设置保存成功！', 'success');
          setTimeout(() => this.close(), 700);
        } catch (error) {
          console.error('保存用户设置失败:', error);
          showToast('网络错误，请稍后重试', 'error');
        } finally {
          this.isSubmitting = false;
        }
      },

      // 由 htmx:after-request 触发，自动给反馈区域添加状态。
      handleHtmxAfterRequest(event) {
        const xhr = event.detail && event.detail.xhr;
        const target = event.detail && event.detail.target;
        if (!xhr || !target) {
          return;
        }
        if (target.id !== 'ai-config-feedback') {
          return;
        }
        const status = xhr.status;
        if (status >= 200 && status < 300) {
          this.isSubmitting = false;
        } else {
          this.isSubmitting = false;
        }
      },
    };
  };

  function handleAiConfigSaveEvent(event) {
    const detail = (event && event.detail) ? event.detail : {};
    const message = detail.message || '';
    const succeeded = !!(event.detail && event.detail.succeeded);

    if (succeeded) {
      const modelInput = document.getElementById('modal-model');
      syncHiddenModel(modelInput ? modelInput.value : '');
      updateStatusAfterSave(true, modelInput ? modelInput.value : '');
      showToast(message || 'AI 配置已保存', 'success');
      // Alpine 实例在 document 上：x-data 元素就是 #settings-modal
      const modalEl = document.getElementById('settings-modal');
      if (modalEl && modalEl._x_dataStack && modalEl._x_dataStack[0]) {
        setTimeout(() => modalEl._x_dataStack[0].close(), 900);
      }
    } else {
      updateStatusAfterSave(false, message);
      showToast(`保存失败：${message || '未知错误'}`, 'error');
    }
  }

  function attachHtmxListeners() {
    document.addEventListener('ai-config-saved', function (event) {
      handleAiConfigSaveEvent({ detail: Object.assign({ succeeded: true }, event.detail || {}) });
    });
    document.addEventListener('ai-config-failed', function (event) {
      handleAiConfigSaveEvent({ detail: Object.assign({ succeeded: false }, event.detail || {}) });
    });
  }

  // 兼容老的 window.openSettingsModal 入口
  function findAlpineModal() {
    const modalEl = document.getElementById('settings-modal');
    if (modalEl && modalEl._x_dataStack && modalEl._x_dataStack[0]) {
      return modalEl._x_dataStack[0];
    }
    return null;
  }

  function openSettingsModal(tabName) {
    const instance = findAlpineModal();
    if (!instance) {
      // Alpine 还没初始化：直接显示 modal（不依赖状态机），等 Alpine 就绪再接管
      const modalEl = document.getElementById('settings-modal');
      if (modalEl) {
        modalEl.classList.add('show');
        modalEl.style.display = 'flex';
      }
      return;
    }
    instance.open(tabName);
  }

  function closeSettingsModal() {
    const instance = findAlpineModal();
    if (!instance) {
      const modalEl = document.getElementById('settings-modal');
      if (modalEl) {
        modalEl.classList.remove('show');
        modalEl.style.display = 'none';
      }
      return;
    }
    instance.close();
  }

  function setSettingsTab(tabName) {
    const instance = findAlpineModal();
    if (!instance) {
      return;
    }
    instance.switchTab(tabName);
  }

  function bindTriggerButtons() {
    const triggers = [
      { id: 'global-settings-btn', tab: 'ai' },
      { id: 'config-btn', tab: 'ai' },
      { id: 'user-settings-btn', tab: 'user' }
    ];
    triggers.forEach(({ id, tab }) => {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener('click', () => openSettingsModal(tab));
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (window.AIConfigManager && !window.aiConfigManager) {
      window.aiConfigManager = new AIConfigManager();
    }
    attachHtmxListeners();
    bindTriggerButtons();
    window.openSettingsModal = openSettingsModal;
    window.closeSettingsModal = closeSettingsModal;
    window.setSettingsTab = setSettingsTab;
  });
})();
