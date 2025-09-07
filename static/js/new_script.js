// Form validation and modal management

// Initialize modules
let aiConfigManager;
let speechRecognitionManager;
let textHighlighter;
let pdfExporter;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function () {
  // Initialize modules
  aiConfigManager = new AIConfigManager();
  speechRecognitionManager = new SpeechRecognitionManager();
  textHighlighter = new TextHighlighter();
  pdfExporter = new PDFExporter();

  // Load AI config from backend
  aiConfigManager.loadFromBackend();

  // Setup modal events
  setupModalEvents();

  // Setup speech recognition
  setupSpeechRecognition();

  // Setup PDF export
  setupPDFExport();

  // Setup floating labels
  setupFloatingLabels();

  // Setup back to top button
  setupBackToTop();

  // Cache content
  setTimeout(cacheContent, 800);
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
    const config = aiConfigManager.config;

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

async function saveConfig() {
    const apiKey = document.getElementById('modal-api-key').value.trim();
    const baseUrl = document.getElementById('modal-base-url').value.trim();
    const model = document.getElementById('modal-model').value;

    if (!apiKey) {
        showToast('请输入API Key', 'warning');
        return;
    }

    // Save to localStorage
    const config = {
        apiKey: apiKey,
        baseUrl: baseUrl,
        model: model,
        timestamp: Date.now()
    };

    aiConfigManager.saveConfig(config);

    // Show loading state
    const saveBtn = document.getElementById('save-config');
    const originalText = saveBtn.innerHTML;
    saveBtn.innerHTML = '⏳ 测试中...';
    saveBtn.disabled = true;

    try {
        // Test AI configuration
        const result = await aiConfigManager.testConfig(config);
        if (result.success) {
            // Save configuration to database
            const saveResult = await aiConfigManager.saveToDatabase(config);
            if (saveResult.success) {
                // Update status to configured
                aiConfigManager.updateStatus(true, config.model);
                showSaveSuccess();
            } else {
                // Update status to error
                aiConfigManager.updateStatus(false, saveResult.message);
                showSaveError(saveResult.message);
            }
        } else {
            // Update status to error
            aiConfigManager.updateStatus(false, result.error);
            showSaveError(result.error);
        }
    } catch (error) {
        console.error('AI config test failed:', error);
        aiConfigManager.updateStatus(false, '测试失败');
        showSaveError('测试失败，请检查配置');
    } finally {
        // Hide loading state after a short delay to show result
        setTimeout(() => {
            saveBtn.innerHTML = originalText;
            saveBtn.classList.remove('success-animation', 'error-animation');
            saveBtn.disabled = false;
        }, 1500);
    }

    // Close modal after a delay
    setTimeout(() => {
        closeConfigModal();
    }, 1500);
}

function updateConfigStatus(tested = false, modelOrError = '') {
    aiConfigManager.updateStatus(tested, modelOrError);
}

function showSaveSuccess() {
    const saveBtn = document.getElementById('save-config');
    if (saveBtn) {
        saveBtn.innerHTML = '✅ 保存成功！';
        saveBtn.classList.add('success-animation');
    }
}

function showSaveError(error) {
    const saveBtn = document.getElementById('save-config');
    if (saveBtn) {
        saveBtn.innerHTML = '❌ 保存失败';
        saveBtn.classList.add('error-animation');
    }
}

function evaluateSpeech(recognizedText) {
    const resultDiv = document.getElementById('result');
    const config = aiConfigManager.config;

    // Get original text from hidden element
    const originalTextElement = document.getElementById('original-text');
    const originalText = originalTextElement ? originalTextElement.textContent : '';

    fetch('/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
            original: originalText,
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

function setupSpeechRecognition() {
    if (!speechRecognitionManager.isInitialized) return;

    const recordBtn = document.getElementById('record-btn');
    const stopBtn = document.getElementById('stop-btn');

    if (recordBtn) {
        recordBtn.addEventListener('click', () => {
            speechRecognitionManager.clearTranscript();
            speechRecognitionManager.startRecording();
        });
    }

    if (stopBtn) {
        stopBtn.addEventListener('click', () => {
            speechRecognitionManager.stopRecording();
        });
    }

    // Setup event handlers
    speechRecognitionManager.onResult((final, interim) => {
        // Update result display
        const resultDiv = document.getElementById('result');
        if (resultDiv) {
            resultDiv.innerHTML = `
                <p><strong>识别文本：</strong>${final}<span style="color: var(--text-secondary); font-style: italic;">${interim}</span></p>
            `;
        }

        // Highlight matching text
        if (final) {
            textHighlighter.highlightText(final);
        }
    });

    speechRecognitionManager.onError((error) => {
        console.error('语音识别错误:', error);
        const resultDiv = document.getElementById('result');
        if (resultDiv) {
            resultDiv.innerHTML = `<p style="color: var(--danger-color);">语音识别错误: ${error}</p>`;
        }
    });

    speechRecognitionManager.onEnd((finalTranscript) => {
        if (finalTranscript) {
            // Send to backend for evaluation
            evaluateSpeech(finalTranscript);
        }
    });
}

function setupFloatingLabels() {
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
}

function setupPDFExport() {
    // Bind PDF export
    const exportBtn = document.getElementById('export-pdf-btn');
    if (exportBtn) {
        exportBtn.addEventListener('click', () => {
            pdfExporter.exportToPDF();
        });
    }
}

function setupBackToTop() {
    const backToTopBtn = document.getElementById('back-to-top');

    if (backToTopBtn) {
        // Show/hide button based on scroll position
        window.addEventListener('scroll', function() {
            if (window.pageYOffset > 300) {
                backToTopBtn.classList.add('visible');
            } else {
                backToTopBtn.classList.remove('visible');
            }
        });

        // Scroll to top when clicked
        backToTopBtn.addEventListener('click', function() {
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        });
    }
}

function evaluateSpeech(recognizedText) {
    const resultDiv = document.getElementById('result');
    const config = getStoredConfig();

    // 从隐藏元素获取原文数据
    const originalTextElement = document.getElementById('original-text');
    const originalText = originalTextElement ? originalTextElement.textContent : '';

    fetch('/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
            original: originalText,
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
    // 绑定 PDF 导出
    const exportBtn = document.getElementById('export-pdf-btn');
    if (exportBtn) exportBtn.addEventListener('click', exportToPDF);
    // 缓存内容（延迟避免尚未渲染完全）
    setTimeout(cacheContent, 800);
    // 清除任何遗留的 beforeunload
    window.onbeforeunload = null;
});

// ===== 内容缓存（避免刷新后重新调用AI） =====
function cacheContent() {
    try {
        const data = {
            original: document.getElementById('original-text')?.textContent || '',
            ruby: document.getElementById('highlight-text')?.innerHTML || '',
            translation: document.querySelector('.translation-text')?.innerHTML || '',
            title: document.getElementById('lesson-title')?.textContent || '',
            vocab: Array.from(document.querySelectorAll('.vocab-item')).map(v => ({
                word: v.querySelector('.vocab-word')?.textContent || '',
                pronunciation: v.querySelector('.vocab-pronunciation')?.textContent || '',
                meaning: v.querySelector('.vocab-meaning')?.textContent || ''
            })),
            ts: Date.now()
        };
        if (data.original) localStorage.setItem('lessonContent', JSON.stringify(data));
    } catch (e) { console.warn('缓存失败', e); }
}

// ===== Form processing =====
document.addEventListener('DOMContentLoaded', function () {
    // Intercept form submission for text processing
    const form = document.querySelector('form[action="/process_text"]');
    if (form) {
        form.addEventListener('submit', function (e) {
            const model = aiConfigManager.getModelForForm();
            if (model) {
                const modelInput = document.createElement('input');
                modelInput.type = 'hidden';
                modelInput.name = 'model';
                modelInput.value = model;
                form.appendChild(modelInput);
            }

            // Show loading state
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.innerHTML = '⏳ 处理中...';
                submitBtn.disabled = true;
            }
        });
    }
});
