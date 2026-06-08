/**
 * AI Configuration Management Module
 * AI配置管理模块
 */

class AIConfigManager {
  constructor() {
    this.config = this.getStoredConfig();
  }

  getStoredConfig() {
    const stored = localStorage.getItem('aiConfig');
    return stored ? JSON.parse(stored) : {};
  }

  saveConfig(config) {
    this.config = config;
    localStorage.setItem('aiConfig', JSON.stringify(config));
  }

  async testConfig(config) {
    const formData = new FormData();
    formData.append('api_key', config.apiKey);
    formData.append('base_url', config.baseUrl);
    formData.append('model', config.model);

    try {
      const response = await fetch('/test_ai_config', {
        method: 'POST',
        body: formData
      });
      return await response.json();
    } catch (error) {
      console.error('AI config test failed:', error);
      return { success: false, error: error.message };
    }
  }

  async saveToDatabase(config) {
    const formData = new FormData();
    formData.append('openai_api_key', config.apiKey);
    formData.append('openai_base_url', config.baseUrl);
    formData.append('openai_model', config.model);

    try {
      const response = await fetch('/save_ai_config', {
        method: 'POST',
        body: formData
      });
      return await response.json();
    } catch (error) {
      console.error('AI config save failed:', error);
      return { success: false, error: error.message };
    }
  }

  async loadFromBackend() {
    try {
      const response = await fetch('/get_ai_config');
      const data = await response.json();

      if (data.error) {
        this.updateStatus();
        return;
      }

      if (data.configured) {
        const config = {
          apiKey: data.api_key || '',
          baseUrl: data.base_url || '',
          model: data.model,
          timestamp: Date.now()
        };
        this.saveConfig(config);
        this.updateStatus(true, data.model);
      } else {
        this.updateStatus();
      }
    } catch (error) {
      console.error('Failed to load AI config from backend:', error);
      this.updateStatus();
    }
  }

  updateStatus(tested = false, modelOrError = '') {
    const statusDiv = document.getElementById('config-status');
    const statusIcon = document.getElementById('status-icon');
    const statusText = document.getElementById('status-text');

    if (statusDiv && statusIcon && statusText) {
      if (this.config.apiKey && tested !== false) {
        statusDiv.classList.add('configured');
        statusDiv.classList.remove('error');
        statusIcon.textContent = '✅';
        statusText.textContent = '已配置';
      } else {
        statusDiv.classList.remove('configured', 'error');
        statusIcon.textContent = '❌';
        statusText.textContent = '未配置';
      }
    }
  }

  getModelForForm() {
    return this.config && this.config.model ? this.config.model : null;
  }
}

// Export for global use
window.AIConfigManager = AIConfigManager;
