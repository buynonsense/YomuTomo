// Form validation and modal management
document.addEventListener('DOMContentLoaded', function () {
    const form = document.querySelector('form');
    if (form) {
        form.addEventListener('submit', function (e) {
            const config = getStoredConfig();
            if (!config.apiKey) {
                alert('请先配置AI设置');
                e.preventDefault();
                openConfigModal();
                return;
            }

            // Add config to form data
            const apiKeyInput = document.createElement('input');
            apiKeyInput.type = 'hidden';
            apiKeyInput.name = 'api_key';
            apiKeyInput.value = config.apiKey;

            const baseUrlInput = document.createElement('input');
            baseUrlInput.type = 'hidden';
            baseUrlInput.name = 'base_url';
            baseUrlInput.value = config.baseUrl || '';

            const modelInput = document.createElement('input');
            modelInput.type = 'hidden';
            modelInput.name = 'model';
            modelInput.value = config.model || 'gpt-5-mini';

            form.appendChild(apiKeyInput);
            form.appendChild(baseUrlInput);
            form.appendChild(modelInput);

            // Show loading state
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.innerHTML = '⏳ 处理中...';
                submitBtn.disabled = true;
            }
        });
    }

    // Initialize config status
    updateConfigStatus();

    // Modal event listeners
    setupModalEvents();

    // Floating label support (ensure labels float when value present even if :placeholder-shown not reliable)
    function refreshFloating() {
        document.querySelectorAll('.input-group').forEach(group => {
            const field = group.querySelector('input, textarea, select');
            const label = group.querySelector('label');
            if (!field || !label) return;
            if (field.value && field.value.trim() !== '') {
                label.classList.add('force-float');
            } else {
                label.classList.remove('force-float');
            }
        });
    }
    document.addEventListener('input', e => {
        if (e.target.matches('.input-group input, .input-group textarea, .input-group select')) {
            refreshFloating();
        }
    });
    refreshFloating();
});

function setupModalEvents() {
    const configBtn = document.getElementById('config-btn');
    const closeBtn = document.getElementById('close-modal');
    const cancelBtn = document.getElementById('cancel-config');
    const saveBtn = document.getElementById('save-config');
    const modal = document.getElementById('config-modal');

    if (configBtn) {
        configBtn.addEventListener('click', openConfigModal);
    }

    if (closeBtn) {
        closeBtn.addEventListener('click', closeConfigModal);
    }

    if (cancelBtn) {
        cancelBtn.addEventListener('click', closeConfigModal);
    }

    if (saveBtn) {
        saveBtn.addEventListener('click', saveConfig);
    }

    // Close modal when clicking outside
    if (modal) {
        modal.addEventListener('click', function (e) {
            if (e.target === modal) {
                closeConfigModal();
            }
        });
    }

    // Close modal on Escape key
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && modal && modal.classList.contains('show')) {
            closeConfigModal();
        }
    });
}

function openConfigModal() {
    const modal = document.getElementById('config-modal');
    const config = getStoredConfig();

    // Populate modal with stored values
    const apiKeyInput = document.getElementById('modal-api-key');
    const baseUrlInput = document.getElementById('modal-base-url');
    const modelSelect = document.getElementById('modal-model');

    if (apiKeyInput) apiKeyInput.value = config.apiKey || '';
    if (baseUrlInput) baseUrlInput.value = config.baseUrl || 'https://api.openai.com/v1';
    if (modelSelect) modelSelect.value = config.model || 'gpt-5-mini';

    if (modal) {
        modal.classList.add('show');
        document.body.style.overflow = 'hidden';
    }
}

function closeConfigModal() {
    const modal = document.getElementById('config-modal');
    if (modal) {
        modal.classList.remove('show');
        document.body.style.overflow = 'auto';
    }
}

function saveConfig() {
    const apiKey = document.getElementById('modal-api-key').value.trim();
    const baseUrl = document.getElementById('modal-base-url').value.trim();
    const model = document.getElementById('modal-model').value;

    if (!apiKey) {
        alert('请输入API Key');
        return;
    }

    // Save to localStorage
    const config = {
        apiKey: apiKey,
        baseUrl: baseUrl,
        model: model,
        timestamp: Date.now()
    };

    localStorage.setItem('aiConfig', JSON.stringify(config));

    // Update status
    updateConfigStatus();

    // Show success feedback
    showSaveSuccess();

    // Close modal
    setTimeout(() => {
        closeConfigModal();
    }, 1500);
}

function getStoredConfig() {
    const stored = localStorage.getItem('aiConfig');
    return stored ? JSON.parse(stored) : {};
}

function updateConfigStatus() {
    const config = getStoredConfig();
    const statusDiv = document.getElementById('config-status');
    const statusIcon = document.getElementById('status-icon');
    const statusText = document.getElementById('status-text');

    if (statusDiv && statusIcon && statusText) {
        if (config.apiKey) {
            statusDiv.classList.add('configured');
            statusIcon.textContent = '✅';
            statusText.textContent = `已配置 (${config.model})`;
        } else {
            statusDiv.classList.remove('configured');
            statusIcon.textContent = '❌';
            statusText.textContent = '未配置';
        }
    }
}

function showSaveSuccess() {
    const saveBtn = document.getElementById('save-config');
    if (saveBtn) {
        const originalText = saveBtn.innerHTML;
        saveBtn.innerHTML = '✅ 保存成功！';
        saveBtn.classList.add('success-animation');
        saveBtn.disabled = true;

        setTimeout(() => {
            saveBtn.innerHTML = originalText;
            saveBtn.classList.remove('success-animation');
            saveBtn.disabled = false;
        }, 1500);
    }
}

// Speech Recognition
let recognition;
let finalTranscript = '';

if ('webkitSpeechRecognition' in window) {
    recognition = new webkitSpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'ja-JP';
} else {
    console.warn('浏览器不支持语音识别');
}

function initSpeechRecognition() {
    if (!recognition) return;

    const recordBtn = document.getElementById('record-btn');
    const stopBtn = document.getElementById('stop-btn');
    const resultDiv = document.getElementById('result');

    if (recordBtn) {
        recordBtn.addEventListener('click', () => {
            finalTranscript = '';
            recognition.start();
            recordBtn.disabled = true;
            recordBtn.innerHTML = '🎤 录音中...';
            if (stopBtn) stopBtn.disabled = false;
            if (resultDiv) resultDiv.innerHTML = '<p style="color: var(--success-color);">正在录音，请开始朗读...</p>';
            const highlightText = document.getElementById('highlight-text');
            if (highlightText) highlightText.innerHTML = '{{ original }}';
        });
    }

    if (stopBtn) {
        stopBtn.addEventListener('click', () => {
            recognition.stop();
            recordBtn.disabled = false;
            recordBtn.innerHTML = '▶️ 开始录音';
            stopBtn.disabled = true;
            if (resultDiv) resultDiv.innerHTML = '<p style="color: var(--warning-color);">录音已停止，正在处理...</p>';
        });
    }

    recognition.onresult = (event) => {
        let interimTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
            let transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
                finalTranscript += transcript;
            } else {
                interimTranscript += transcript;
            }
        }

        if (resultDiv) {
            resultDiv.innerHTML = `
                <p><strong>识别文本：</strong>${finalTranscript}<span style="color: var(--text-secondary); font-style: italic;">${interimTranscript}</span></p>
            `;
        }

        // Highlight matching text
        if (finalTranscript) {
            highlightText(finalTranscript);
        }
    };

    recognition.onerror = (event) => {
        console.error('语音识别错误:', event.error);
        if (resultDiv) {
            resultDiv.innerHTML = `<p style="color: var(--danger-color);">语音识别错误: ${event.error}</p>`;
        }
        resetButtons();
    };

    recognition.onend = () => {
        resetButtons();
        if (finalTranscript) {
            // Send to backend for evaluation
            evaluateSpeech(finalTranscript);
        }
    };
}

function resetButtons() {
    const recordBtn = document.getElementById('record-btn');
    const stopBtn = document.getElementById('stop-btn');

    if (recordBtn) {
        recordBtn.disabled = false;
        recordBtn.innerHTML = '▶️ 开始录音';
    }
    if (stopBtn) {
        stopBtn.disabled = true;
    }
}

function highlightText(recognized) {
    const highlightText = document.getElementById('highlight-text');
    if (!highlightText) return;

    const text = '{{ original }}';
    const start = text.indexOf(recognized);
    if (start !== -1) {
        const before = text.substring(0, start);
        const match = text.substring(start, start + recognized.length);
        const after = text.substring(start + recognized.length);
        highlightText.innerHTML = `${before}<span class="highlight">${match}</span>${after}`;
    } else {
        highlightText.innerHTML = text;
    }
}

function evaluateSpeech(recognizedText) {
    const resultDiv = document.getElementById('result');
    const config = getStoredConfig();

    fetch('/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
            original: '{{ original }}',
            recognized: recognizedText
        })
    })
        .then(response => response.json())
        .then(data => {
            if (resultDiv) {
                const scoreColor = data.score >= 80 ? 'var(--success-color)' : data.score >= 60 ? 'var(--warning-color)' : 'var(--danger-color)';
                resultDiv.innerHTML += `<p><strong>评分：</strong><span style="color: ${scoreColor}; font-size: 1.2em;">${data.score}/100</span></p>`;
            }
        })
        .catch(error => {
            console.error('评测错误:', error);
            if (resultDiv) {
                resultDiv.innerHTML += `<p style="color: var(--danger-color);">评测失败，请重试</p>`;
            }
        });
}

function removeWord(btn) {
    const item = btn.closest('.vocab-item');
    if (item) {
        item.style.animation = 'fadeOut 0.3s ease-out';
        setTimeout(() => {
            item.remove();
        }, 300);
    }
}

// Add fadeOut animation
const style = document.createElement('style');
style.textContent = `
    @keyframes fadeOut {
        to {
            opacity: 0;
            transform: translateX(100%);
        }
    }
`;
document.head.appendChild(style);

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function () {
    initSpeechRecognition();
});
