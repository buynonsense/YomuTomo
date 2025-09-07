/**
 * Reading Page JavaScript
 * 阅读页面专用JavaScript
 */

// Initialize modules
let speechRecognitionManager;
let textHighlighter;
let pdfExporter;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function () {
  // Initialize necessary modules
  speechRecognitionManager = new SpeechRecognitionManager();
  textHighlighter = new TextHighlighter();
  pdfExporter = new PDFExporter();

    // Initialize text highlighter content from DOM so highlightText() has data
    try {
        const originalText = document.getElementById('original-text')?.textContent || '';
        const rubyText = document.getElementById('ruby-text-data')?.innerHTML || '';
        textHighlighter.setContent(originalText, rubyText);
        const highlightEl = document.getElementById('highlight-text');
        if (highlightEl) highlightEl.innerHTML = rubyText;
    } catch (e) {
        console.error('初始化高亮文本失败', e);
    }

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

function setupPDFExport() {
    // Bind PDF export
    const exportBtn = document.getElementById('export-pdf-btn');
    if (exportBtn) {
        exportBtn.addEventListener('click', () => {
            pdfExporter.exportToPDF();
        });
    }
}

function setupFloatingLabels() {
    // Floating label support
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
    const config = { model: 'gpt-5-mini' }; // Default model

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

// ===== Content caching =====
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
