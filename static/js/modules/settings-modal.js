/**
 * 统一设置弹窗模块
 * 负责全局导航入口、AI 配置和用户设置切换
 */

(function () {
  let settingsModalOpen = false;
  let closingTimer = null;
  let bodyRestoreTimer = null;
  let outsideClickHandler = null;
  let escapeKeyHandler = null;
  let aiConfigLoaded = false;

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

  function getModalElements() {
    const modal = document.getElementById('settings-modal');
    return {
      modal,
      tabAi: document.getElementById('settings-tab-ai'),
      tabUser: document.getElementById('settings-tab-user'),
      panelAi: document.getElementById('settings-panel-ai'),
      panelUser: document.getElementById('settings-panel-user'),
      closeBtn: document.getElementById('close-settings-modal'),
      saveConfigBtn: document.getElementById('save-config'),
      cancelConfigBtn: document.getElementById('cancel-config'),
      saveSettingsBtn: document.getElementById('save-settings'),
      cancelSettingsBtn: document.getElementById('cancel-settings'),
      globalBtn: document.getElementById('global-settings-btn'),
      configBtn: document.getElementById('config-btn'),
      userSettingsBtn: document.getElementById('user-settings-btn'),
      apiKeyInput: document.getElementById('modal-api-key'),
      baseUrlInput: document.getElementById('modal-base-url'),
      modelInput: document.getElementById('modal-model'),
      userLevelSelect: document.getElementById('user-level'),
      statusDiv: document.getElementById('config-status'),
      statusIcon: document.getElementById('status-icon'),
      statusText: document.getElementById('status-text')
    };
  }

  function setActiveTab(tabName) {
    const { tabAi, tabUser, panelAi, panelUser } = getModalElements();
    const isUserTab = tabName === 'user';

    if (tabAi) {
      tabAi.classList.toggle('is-active', !isUserTab);
      tabAi.setAttribute('aria-selected', String(!isUserTab));
    }

    if (tabUser) {
      tabUser.classList.toggle('is-active', isUserTab);
      tabUser.setAttribute('aria-selected', String(isUserTab));
    }

    if (panelAi) {
      panelAi.hidden = isUserTab;
      panelAi.classList.toggle('is-active', !isUserTab);
    }

    if (panelUser) {
      panelUser.hidden = !isUserTab;
      panelUser.classList.toggle('is-active', isUserTab);
    }
  }

  function populateAiFields() {
    const manager = getAiConfigManager();
    const { apiKeyInput, baseUrlInput, modelInput } = getModalElements();

    if (!manager) {
      return;
    }

    const config = manager.config || {};
    if (apiKeyInput) {
      apiKeyInput.value = config.apiKey || '';
    }
    if (baseUrlInput) {
      baseUrlInput.value = config.baseUrl || 'https://api.openai.com/v1';
    }
    if (modelInput) {
      modelInput.value = config.model || '';
    }

    if (!aiConfigLoaded) {
      aiConfigLoaded = true;
      manager.loadFromBackend();
    }
  }

  async function loadUserLevel() {
    const { userLevelSelect } = getModalElements();
    if (!userLevelSelect) {
      return;
    }

    try {
      const response = await fetch('/get_user_level');
      const data = await response.json();
      if (response.ok && data && data.level) {
        userLevelSelect.value = String(data.level);
      }
    } catch (error) {
      console.error('获取用户等级失败:', error);
    }
  }

  function openSettingsModal(tabName = 'ai') {
    const { modal } = getModalElements();
    if (!modal || settingsModalOpen) {
      if (modal && settingsModalOpen) {
        setActiveTab(tabName);
        if (tabName === 'user') {
          loadUserLevel();
        }
      }
      return;
    }

    if (closingTimer) {
      clearTimeout(closingTimer);
      closingTimer = null;
    }
    if (bodyRestoreTimer) {
      clearTimeout(bodyRestoreTimer);
      bodyRestoreTimer = null;
    }

    populateAiFields();
    setActiveTab(tabName);
    if (tabName === 'user') {
      loadUserLevel();
    }

    modal.classList.remove('closing');
    modal.style.display = 'flex';
    modal.style.pointerEvents = 'auto';
    modal.style.visibility = 'visible';
    modal.classList.add('show');

    document.body.style.overflow = 'hidden';
    document.body.style.overflowX = 'hidden';
    document.body.style.overflowY = 'hidden';

    settingsModalOpen = true;
  }

  function closeSettingsModal() {
    const { modal } = getModalElements();
    if (!modal || !settingsModalOpen) {
      return;
    }

    settingsModalOpen = false;
    modal.style.pointerEvents = 'none';
    modal.classList.add('closing');

    closingTimer = setTimeout(() => {
      closingTimer = null;
      modal.classList.remove('show');
      modal.classList.remove('closing');
      modal.style.display = 'none';
      modal.style.opacity = '';
      modal.style.transform = '';
      modal.style.pointerEvents = '';
      modal.style.visibility = 'hidden';
    }, 300);

    bodyRestoreTimer = setTimeout(() => {
      bodyRestoreTimer = null;
      document.body.style.overflow = '';
      document.body.style.overflowX = '';
      document.body.style.overflowY = '';
    }, 350);
  }

  function showToast(message, type) {
    if (typeof window.showToast === 'function') {
      window.showToast(message, type);
      return;
    }
    // 兜底：直接 console 输出，避免静默失败
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
    const { statusIcon, statusText, statusDiv } = getModalElements();
    if (!manager || !statusIcon || !statusText) {
      return;
    }
    manager.updateStatus(success, success ? modelOrError : '');
    if (statusDiv) {
      statusDiv.classList.toggle('error', !success);
    }
  }

  // htmx 表单提交完成后，HX-Trigger 头里会带 ai-config-saved / ai-config-failed。
  // 这里负责 toast、关弹窗、状态徽标同步、隐藏模型同步。
  function handleAiConfigSaveEvent(event) {
    const detail = event && event.detail ? event.detail : {};
    const message = detail.message || '';
    const succeeded = !!(event.detail && event.detail.succeeded);

    if (succeeded) {
      const modelInput = document.getElementById('modal-model');
      syncHiddenModel(modelInput ? modelInput.value : '');
      updateStatusAfterSave(true, modelInput ? modelInput.value : '');
      showToast(message || 'AI 配置已保存', 'success');
      setTimeout(closeSettingsModal, 900);
    } else {
      updateStatusAfterSave(false, message);
      showToast(`保存失败：${message || '未知错误'}`, 'error');
    }
  }

  function attachHtmxListeners() {
    // htmx 会把 HX-Trigger 派发为同名 DOM 事件，事件 detail 来自服务端 json
    document.addEventListener('ai-config-saved', function (event) {
      handleAiConfigSaveEvent({ detail: Object.assign({ succeeded: true }, event.detail || {}) });
    });
    document.addEventListener('ai-config-failed', function (event) {
      handleAiConfigSaveEvent({ detail: Object.assign({ succeeded: false }, event.detail || {}) });
    });
  }

  async function saveUserSettings() {
    const { userLevelSelect, saveSettingsBtn } = getModalElements();
    if (!userLevelSelect || !saveSettingsBtn) {
      return;
    }

    const level = Number.parseInt(userLevelSelect.value, 10);
    if (!Number.isFinite(level)) {
      showToast('请选择有效的用户等级', 'warning');
      return;
    }

    const originalText = saveSettingsBtn.innerHTML;
    saveSettingsBtn.innerHTML = '⏳ 保存中...';
    saveSettingsBtn.disabled = true;

    try {
      const response = await fetch('/update_user_level', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ level })
      });

      const result = await response.json();
      if (!response.ok) {
        showToast(`保存失败：${result.error || '未知错误'}`, 'error');
        return;
      }

      showToast('用户设置保存成功！', 'success');
      setTimeout(closeSettingsModal, 700);
    } catch (error) {
      console.error('保存用户设置失败:', error);
      showToast('网络错误，请稍后重试', 'error');
    } finally {
      saveSettingsBtn.innerHTML = originalText;
      saveSettingsBtn.disabled = false;
    }
  }

  function bindEvents() {
    const {
      modal,
      globalBtn,
      configBtn,
      userSettingsBtn,
      closeBtn,
      saveConfigBtn,
      cancelConfigBtn,
      saveSettingsBtn,
      cancelSettingsBtn,
      tabAi,
      tabUser
    } = getModalElements();

    if (!modal) {
      return;
    }

    if (globalBtn) {
      globalBtn.addEventListener('click', () => openSettingsModal('ai'));
    }

    if (configBtn) {
      configBtn.addEventListener('click', () => openSettingsModal('ai'));
    }

    if (userSettingsBtn) {
      userSettingsBtn.addEventListener('click', () => openSettingsModal('user'));
    }

    if (closeBtn) {
      closeBtn.addEventListener('click', closeSettingsModal);
    }

    if (cancelConfigBtn) {
      cancelConfigBtn.addEventListener('click', closeSettingsModal);
    }

    if (cancelSettingsBtn) {
      cancelSettingsBtn.addEventListener('click', closeSettingsModal);
    }

    if (saveConfigBtn) {
      // Stage 3a: AI 配置改用 htmx <form hx-post> 自提交，不再走 saveAiConfig()。
      // 按钮本身是 type="submit"，htmx 会负责 fetch + 响应片段 swap。
      // 业务反馈（toast / 关弹窗 / 状态徽标）由 document 级 ai-config-* 事件处理。
      saveConfigBtn.setAttribute('type', 'submit');
    }

    if (saveSettingsBtn) {
      saveSettingsBtn.addEventListener('click', saveUserSettings);
    }

    if (tabAi) {
      tabAi.addEventListener('click', () => setActiveTab('ai'));
    }

    if (tabUser) {
      tabUser.addEventListener('click', async () => {
        setActiveTab('user');
        await loadUserLevel();
      });
    }

    if (outsideClickHandler) {
      modal.removeEventListener('click', outsideClickHandler);
    }
    outsideClickHandler = function (event) {
      if (event.target === modal) {
        closeSettingsModal();
      }
    };
    modal.addEventListener('click', outsideClickHandler);

    if (escapeKeyHandler) {
      document.removeEventListener('keydown', escapeKeyHandler);
    }
    escapeKeyHandler = function (event) {
      if (event.key === 'Escape' && settingsModalOpen) {
        closeSettingsModal();
      }
    };
    document.addEventListener('keydown', escapeKeyHandler);
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (window.AIConfigManager && !window.aiConfigManager) {
      window.aiConfigManager = new AIConfigManager();
    }

    bindEvents();
    attachHtmxListeners();

    window.openSettingsModal = openSettingsModal;
    window.closeSettingsModal = closeSettingsModal;
    window.setSettingsTab = setActiveTab;
  });
})();
