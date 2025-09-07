// Form validation and modal management

// Initialize modules
let aiConfigManager;
let speechRecognitionManager;
let textHighlighter;
let pdfExporter;

// Ensure modal is hidden on load if present (defensive - avoid referencing undefined)
setTimeout(() => {
    const modal = document.getElementById('config-modal');
    if (modal && !modal.classList.contains('show')) {
        modal.style.display = 'none';
        modal.style.opacity = '';
        modal.style.transform = '';
        modal.style.pointerEvents = 'none';
        modal.style.visibility = 'hidden';
    }
}, 300); // Wait for transition to complete when DOM is loaded
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

// Modal event handlers - defined globally to allow proper removal
let modalOutsideClickHandler = null;
let modalEscapeKeyHandler = null;
let configBtnClickHandler = null;
// Stable modal open state to avoid classList race conditions
let isConfigModalOpen = false;
// Timeout handles to avoid race conditions between open/close
let modalCloseTimer = null;
let bodyRestoreTimer = null;

function setupModalEvents() {
    const configBtn = document.getElementById('config-btn');
    const closeBtn = document.getElementById('close-modal');
    const cancelBtn = document.getElementById('cancel-config');
    const saveBtn = document.getElementById('save-config');
    const modal = document.getElementById('config-modal');

    // Use event delegation for the config button to survive DOM replacements
    if (!window._hasDelegatedConfigClick) {
        window._configClickCount = 0;
        window._configOpenCount = 0;
        window._configCloseCount = 0;
        const delegatedHandler = function(e) {
            // allow clicks on the button or within it
            const btn = e.target.closest && e.target.closest('#config-btn');
            if (btn) {
                window._configClickCount++;
                if (e && typeof e.preventDefault === 'function') e.preventDefault();
                openConfigModal();
            }
        };
    document.addEventListener('click', delegatedHandler);
    window._hasDelegatedConfigClick = true;
    }

    if (closeBtn) {
        closeBtn.removeEventListener('click', closeConfigModal);
        closeBtn.addEventListener('click', closeConfigModal);
    }

    if (cancelBtn) {
        cancelBtn.removeEventListener('click', closeConfigModal);
        cancelBtn.addEventListener('click', closeConfigModal);
    }

    if (saveBtn) {
        saveBtn.removeEventListener('click', saveConfig);
        saveBtn.addEventListener('click', saveConfig);
    }

    // configBtn listener is attached above with guarding

    // Close modal when clicking outside
    if (modal) {
        if (modalOutsideClickHandler) {
            modal.removeEventListener('click', modalOutsideClickHandler);
        }
        modalOutsideClickHandler = function (e) {
            
            if (e.target === modal) {
                closeConfigModal();
            }
        };
    modal.addEventListener('click', modalOutsideClickHandler);
    }

    // Close modal on Escape key
    if (modalEscapeKeyHandler) {
        document.removeEventListener('keydown', modalEscapeKeyHandler);
    }
    modalEscapeKeyHandler = function (e) {
        if (e.key === 'Escape' && modal && modal.classList.contains('show')) {
            closeConfigModal();
        }
    };
    document.addEventListener('keydown', modalEscapeKeyHandler);
}

// Clean up handlers on page unload to avoid leaks
window.addEventListener('beforeunload', () => {
    const modal = document.getElementById('config-modal');
    const configBtn = document.getElementById('config-btn');
    if (configBtn && configBtnClickHandler) configBtn.removeEventListener('click', configBtnClickHandler);
    if (modal && modalOutsideClickHandler) modal.removeEventListener('click', modalOutsideClickHandler);
    if (modalEscapeKeyHandler) document.removeEventListener('keydown', modalEscapeKeyHandler);
    
});

function openConfigModal() {
    
    const modal = document.getElementById('config-modal');
    const config = aiConfigManager.config;

    // Prevent opening if already open (use stable boolean)
    if (isConfigModalOpen) {
        return;
    }

    // Cancel any pending close timers to avoid race where close's timeout hides the modal after reopen
    if (modalCloseTimer) {
        clearTimeout(modalCloseTimer);
        modalCloseTimer = null;
    }
    if (bodyRestoreTimer) {
        clearTimeout(bodyRestoreTimer);
        bodyRestoreTimer = null;
    }

    // Populate modal with stored values
    const apiKeyInput = document.getElementById('modal-api-key');
    const baseUrlInput = document.getElementById('modal-base-url');
    const modelSelect = document.getElementById('modal-model');

    // Display real values for editing
    if (apiKeyInput) apiKeyInput.value = config.apiKey || '';
    if (baseUrlInput) baseUrlInput.value = config.baseUrl || 'https://api.openai.com/v1';
    if (modelSelect) modelSelect.value = config.model || 'gpt-5-mini';

    if (modal) {
    // Reset inline styles in case previous cycles left stale values
    modal.style.display = '';
    modal.style.opacity = '';
    modal.style.transform = '';
    modal.style.pointerEvents = '';
    modal.style.visibility = '';

    modal.classList.add('show');
        document.body.style.overflow = 'hidden';
        document.body.style.overflowX = 'hidden';
        document.body.style.overflowY = 'hidden';

        // Ensure modal is visible and properly positioned
        modal.style.display = 'flex';
        modal.style.pointerEvents = 'auto';
        modal.style.visibility = 'visible';
    isConfigModalOpen = true;
    } else {
        console.error('Modal element not found!');
    }
}

function closeConfigModal() {
    
    const modal = document.getElementById('config-modal');
    if (modal) {
    // Mark closed flag immediately, but keep the `.show` class until the transition finishes
    isConfigModalOpen = false;

    // Disable pointer events on modal immediately to avoid interaction during closing
    modal.style.pointerEvents = 'none';
    // Add a 'closing' class to animate content smoothly without layout jumps
    try { modal.classList.add('closing'); } catch (e) {}

    // Schedule actual class removal and hiding after transition duration
    modalCloseTimer = setTimeout(() => {
        modalCloseTimer = null;
        // remove show to allow CSS to fall back, then hide the element
        try {
            modal.classList.remove('show');
            modal.classList.remove('closing');
        } catch (e) { /* defensive */ }
        if (modal) {
            modal.style.display = 'none';
            modal.style.opacity = '';
            modal.style.transform = '';
            modal.style.pointerEvents = '';
            modal.style.visibility = 'hidden';
            
        }
    }, 300); // Wait for transition to complete

        // Re-enable the config button after closing
        const configBtn = document.getElementById('config-btn');
        if (configBtn) {
            configBtn.disabled = false;
            configBtn.style.pointerEvents = 'auto';
        }

        // Force body scroll restoration (store timer so open can cancel it)
        bodyRestoreTimer = setTimeout(() => {
            bodyRestoreTimer = null;
            document.body.style.overflow = '';
            document.body.style.overflowX = '';
            document.body.style.overflowY = '';
            

            // Keep modal event handlers attached so repeated open/close works reliably.
            // They will be removed on page unload if needed.
        }, 350);
    } else {
        console.error('Modal element not found for closing!');
    }
}

async function saveConfig() {
    const apiKeyInput = document.getElementById('modal-api-key');
    const baseUrlInput = document.getElementById('modal-base-url');
    const modelSelect = document.getElementById('modal-model');

    const apiKey = apiKeyInput.value.trim();
    const baseUrl = baseUrlInput.value.trim();
    const model = modelSelect.value;

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
    // 浏览器不支持语音识别 - 静默降级
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
    } catch (e) { /* 缓存失败，静默忽略 */ }
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
