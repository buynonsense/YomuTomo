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

  async function saveAiConfig() {
    const manager = getAiConfigManager();
    const { apiKeyInput, baseUrlInput, modelInput, saveConfigBtn } = getModalElements();

    if (!manager || !apiKeyInput || !baseUrlInput || !modelInput || !saveConfigBtn) {
      return;
    }

    const apiKey = apiKeyInput.value.trim();
    const baseUrl = baseUrlInput.value.trim();
    const model = modelInput.value.trim();

    if (!apiKey) {
      showToast('请输入API Key', 'warning');
      return;
    }

    try {
      if (baseUrl && baseUrl.includes('generativelanguage.googleapis.com') && !model) {
        showToast('Google Generative Language 需要填写模型名（例如 gemini-2.5-flash）', 'warning');
        return;
      }
    } catch (error) {
      console.error('校验 AI 配置失败:', error);
    }

    const config = {
      apiKey,
      baseUrl,
      model,
      timestamp: Date.now()
    };

    manager.saveConfig(config);

    const originalText = saveConfigBtn.innerHTML;
    saveConfigBtn.innerHTML = '⏳ 测试中...';
    saveConfigBtn.disabled = true;

    try {
      const testResult = await manager.testConfig(config);
      if (!testResult.success) {
        manager.updateStatus(false, testResult.error || '测试失败');
        showToast(`保存失败：${testResult.error || '测试失败'}`, 'error');
        return;
      }

      const saveResult = await manager.saveToDatabase(config);
      if (!saveResult.success) {
        manager.updateStatus(false, saveResult.message || '保存失败');
        showToast(`保存失败：${saveResult.message || '未知错误'}`, 'error');
        return;
      }

      manager.updateStatus(true, config.model || '默认模型');
      try {
        const hiddenModel = document.getElementById('model');
        if (hiddenModel) {
          hiddenModel.value = config.model || '';
        }
        sessionStorage.setItem('processing_model', config.model || '');
      } catch (error) {
        console.error('更新隐藏模型失败:', error);
      }

      showToast('AI 配置保存成功！', 'success');
      setTimeout(closeSettingsModal, 900);
    } catch (error) {
      console.error('AI 配置保存失败:', error);
      manager.updateStatus(false, '测试失败');
      showToast('测试失败，请检查配置', 'error');
    } finally {
      saveConfigBtn.innerHTML = originalText;
      saveConfigBtn.disabled = false;
    }
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
      saveConfigBtn.addEventListener('click', saveAiConfig);
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

    window.openSettingsModal = openSettingsModal;
    window.closeSettingsModal = closeSettingsModal;
    window.setSettingsTab = setActiveTab;
  });
})();
