/**
 * Reading Page JavaScript
 * 阅读页面专用 JavaScript
 */

let speechRecognitionManager;
let textHighlighter;
let pdfExporter;

class ReadingPageController {
  constructor() {
    this.storageKey = 'yomu-reading-state';
    this.state = this.loadState();
    this.sentenceItems = [];
    this.currentSentenceIndex = -1;
    this.currentUtterance = null;
    this.speechSupported = 'speechSynthesis' in window;
    this.root = document.body;
  }

  init() {
    this.cacheDom();
    this.bindSpeechRecognition();
    this.bindPdfExport();
    this.bindFuriganaMode();
    this.bindTtsControls();
    this.bindVocabControls();
    this.bindBackToTop();
    this.restoreState();
    this.renderSentences();
    this.refreshVocabView();
    this.cacheContent();
  }

  cacheDom() {
    this.recordBtn = document.getElementById('record-btn');
    this.stopBtn = document.getElementById('stop-btn');
    this.ttsPlayBtn = document.getElementById('tts-play-btn');
    this.ttsStopBtn = document.getElementById('tts-stop-btn');
    this.toggleMasteredBtn = document.getElementById('toggle-mastered-btn');
    this.articleId = document.getElementById('article-id')?.textContent?.trim() || '';
    this.resultDiv = document.getElementById('result');
    this.highlightTextEl = document.getElementById('highlight-text');
    this.originalTextEl = document.getElementById('original-text');
    this.rubyTextEl = document.getElementById('ruby-text-data');
    this.sentenceListEl = document.getElementById('sentence-list');
    this.vocabGridEl = document.getElementById('vocab-grid');
  }

  loadState() {
    try {
      const raw = localStorage.getItem(this.storageKey);
      if (!raw) {
        return {
          furiganaMode: 'show',
          hideMastered: false
        };
      }
      const parsed = JSON.parse(raw);
      return {
        furiganaMode: parsed.furiganaMode || 'show',
        hideMastered: Boolean(parsed.hideMastered)
      };
    } catch (error) {
      console.warn('读取阅读页状态失败', error);
      return {
        furiganaMode: 'show',
        hideMastered: false
      };
    }
  }

  saveState() {
    try {
      localStorage.setItem(this.storageKey, JSON.stringify(this.state));
    } catch (error) {
      console.warn('保存阅读页状态失败', error);
    }
  }

  restoreState() {
    this.applyFuriganaMode(this.state.furiganaMode);
    this.updateToggleMasteredButton();
  }

  bindSpeechRecognition() {
    if (!speechRecognitionManager || !speechRecognitionManager.isInitialized) {
      return;
    }

    if (this.recordBtn) {
      this.recordBtn.addEventListener('click', () => {
        speechRecognitionManager.clearTranscript();
        speechRecognitionManager.startRecording();
      });
    }

    if (this.stopBtn) {
      this.stopBtn.addEventListener('click', () => {
        speechRecognitionManager.stopRecording();
      });
    }

    speechRecognitionManager.onResult((final, interim) => {
      if (this.resultDiv) {
        this.resultDiv.innerHTML = `
          <p><strong>识别文本：</strong>${final}<span style="color: var(--text-secondary); font-style: italic;">${interim}</span></p>
        `;
      }

      if (final) {
        textHighlighter.highlightText(final);
      }
    });

    speechRecognitionManager.onError((error) => {
      console.error('语音识别错误:', error);
      if (this.resultDiv) {
        this.resultDiv.innerHTML = `<p style="color: var(--danger-color);">语音识别错误: ${error}</p>`;
      }
    });

    speechRecognitionManager.onEnd((finalTranscript) => {
      if (finalTranscript) {
        this.evaluateSpeech(finalTranscript);
      }
    });
  }

  bindPdfExport() {
    const exportBtn = document.getElementById('export-pdf-btn');
    if (!exportBtn) {
      return;
    }
    exportBtn.addEventListener('click', () => {
      if (pdfExporter) {
        pdfExporter.exportToPDF();
      }
    });
  }

  bindFuriganaMode() {
    const buttons = document.querySelectorAll('.furigana-mode-btn');
    buttons.forEach((button) => {
      button.addEventListener('click', () => {
        const mode = button.dataset.furiganaMode || 'show';
        this.applyFuriganaMode(mode);
        this.state.furiganaMode = mode;
        this.saveState();
      });
    });
  }

  applyFuriganaMode(mode) {
    const normalized = ['show', 'hover', 'hide'].includes(mode) ? mode : 'show';
    this.state.furiganaMode = normalized;
    this.root.dataset.furiganaMode = normalized;
    this.root.classList.remove('furigana-mode-show', 'furigana-mode-hover', 'furigana-mode-hide');
    this.root.classList.add(`furigana-mode-${normalized}`);

    document.querySelectorAll('.furigana-mode-btn').forEach((button) => {
      button.classList.toggle('btn-primary', button.dataset.furiganaMode === normalized);
      button.classList.toggle('btn-secondary', button.dataset.furiganaMode !== normalized);
    });
  }

  bindTtsControls() {
    if (this.ttsPlayBtn) {
      this.ttsPlayBtn.addEventListener('click', () => {
        this.playAllSentences();
      });
    }

    if (this.ttsStopBtn) {
      this.ttsStopBtn.addEventListener('click', () => {
        this.stopSpeech();
      });
    }
  }

  bindVocabControls() {
    if (this.toggleMasteredBtn) {
      this.toggleMasteredBtn.addEventListener('click', () => {
        this.state.hideMastered = !this.state.hideMastered;
        this.updateToggleMasteredButton();
        this.refreshVocabView();
        this.saveState();
      });
    }

    document.querySelectorAll('.vocab-item').forEach((item) => {
      if (item.dataset.vocabMastered === '1') {
        item.classList.add('is-mastered');
      }
    });
  }

  bindBackToTop() {
    const backToTopBtn = document.getElementById('back-to-top');
    if (!backToTopBtn) {
      return;
    }

    window.addEventListener('scroll', () => {
      if (window.pageYOffset > 300) {
        backToTopBtn.classList.add('visible');
      } else {
        backToTopBtn.classList.remove('visible');
      }
    });

    backToTopBtn.addEventListener('click', () => {
      window.scrollTo({
        top: 0,
        behavior: 'smooth'
      });
    });
  }

  renderSentences() {
    if (!this.sentenceListEl || !this.originalTextEl) {
      return;
    }

    const originalText = this.originalTextEl.textContent || '';
    const sentences = this.splitSentences(originalText);
    this.sentenceItems = sentences;
    this.sentenceListEl.innerHTML = '';

    if (!sentences.length) {
      this.sentenceListEl.innerHTML = '<p class="sentence-empty">没有可播放的句子。</p>';
      return;
    }

    sentences.forEach((sentence, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'sentence-item';
      button.dataset.index = String(index);
      button.textContent = sentence;
      button.addEventListener('click', () => {
        this.playSentence(index);
      });
      this.sentenceListEl.appendChild(button);
    });
  }

  splitSentences(text) {
    const normalized = (text || '').replace(/\r\n/g, '\n').trim();
    if (!normalized) {
      return [];
    }

    const parts = normalized
      .split(/(?<=[。！？!?])\s*|\n+/)
      .map((part) => part.trim())
      .filter(Boolean);

    return parts.length ? parts : [normalized];
  }

  playAllSentences() {
    if (!this.speechSupported) {
      this.showSpeechUnsupported();
      return;
    }

    if (!this.sentenceItems.length) {
      return;
    }

    this.stopSpeech();
    this.speakSequence(0);
  }

  speakSequence(index) {
    if (index >= this.sentenceItems.length) {
      this.currentSentenceIndex = -1;
      this.syncSentenceHighlight();
      this.updateTtsButtons(false);
      return;
    }

    const sentence = this.sentenceItems[index];
    this.currentSentenceIndex = index;
    this.syncSentenceHighlight();
    this.updateTtsButtons(true);

    const utterance = this.createUtterance(sentence);
    utterance.onstart = () => {
      this.currentSentenceIndex = index;
      this.syncSentenceHighlight();
    };
    utterance.onend = () => {
      this.speakSequence(index + 1);
    };
    utterance.onerror = (event) => {
      console.error('TTS 播放失败', event.error);
      this.stopSpeech();
    };

    this.currentUtterance = utterance;
    window.speechSynthesis.speak(utterance);
  }

  playSentence(index) {
    if (!this.speechSupported) {
      this.showSpeechUnsupported();
      return;
    }

    const sentence = this.sentenceItems[index];
    if (!sentence) {
      return;
    }

    this.stopSpeech();
    this.currentSentenceIndex = index;
    this.syncSentenceHighlight();
    this.updateTtsButtons(true);

    const utterance = this.createUtterance(sentence);
    utterance.onstart = () => {
      this.currentSentenceIndex = index;
      this.syncSentenceHighlight();
    };
    utterance.onend = () => {
      this.currentSentenceIndex = -1;
      this.syncSentenceHighlight();
      this.updateTtsButtons(false);
    };
    utterance.onerror = (event) => {
      console.error('单句 TTS 播放失败', event.error);
      this.stopSpeech();
    };

    this.currentUtterance = utterance;
    window.speechSynthesis.speak(utterance);
  }

  stopSpeech() {
    if (this.speechSupported) {
      window.speechSynthesis.cancel();
    }
    this.currentUtterance = null;
    this.currentSentenceIndex = -1;
    this.syncSentenceHighlight();
    this.updateTtsButtons(false);
  }

  createUtterance(text) {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'ja-JP';
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.volume = 1;
    return utterance;
  }

  syncSentenceHighlight() {
    document.querySelectorAll('.sentence-item').forEach((item) => {
      const index = Number(item.dataset.index);
      item.classList.toggle('is-active', index === this.currentSentenceIndex);
      item.setAttribute('aria-current', index === this.currentSentenceIndex ? 'true' : 'false');
    });

    if (this.currentSentenceIndex >= 0) {
      const activeItem = document.querySelector(`.sentence-item[data-index="${this.currentSentenceIndex}"]`);
      if (activeItem) {
        activeItem.scrollIntoView({ block: 'center', behavior: 'smooth' });
      }
    }
  }

  updateTtsButtons(isPlaying) {
    if (this.ttsPlayBtn) {
      this.ttsPlayBtn.disabled = isPlaying;
    }
    if (this.ttsStopBtn) {
      this.ttsStopBtn.disabled = !isPlaying;
    }
  }

  showSpeechUnsupported() {
    if (this.resultDiv) {
      this.resultDiv.innerHTML = '<p style="color: var(--warning-color);">当前浏览器不支持网页语音播放。</p>';
    }
  }

  speakVocabWord(button) {
    if (!this.speechSupported) {
      this.showSpeechUnsupported();
      return;
    }

    const item = button.closest('.vocab-item');
    if (!item) {
      return;
    }

    const pronunciation = item.dataset.vocabPronunciation || item.querySelector('.vocab-pronunciation')?.textContent || '';
    const word = item.dataset.vocabWord || item.querySelector('.vocab-word')?.textContent || '';
    const text = pronunciation || word;
    if (!text.trim()) {
      return;
    }

    this.stopSpeech();
    const utterance = this.createUtterance(text);
    this.currentUtterance = utterance;
    utterance.onend = () => {
      this.currentUtterance = null;
    };
    window.speechSynthesis.speak(utterance);
  }

  toggleVocabMastered(button) {
    const item = button.closest('.vocab-item');
    if (!item) {
      return;
    }

    const word = item.dataset.vocabWord || '';
    if (!word) {
      return;
    }

    const pronunciation = item.dataset.vocabPronunciation || item.querySelector('.vocab-pronunciation')?.textContent || '';
    const meaning = item.querySelector('.vocab-meaning')?.textContent || '';
    const mastered = item.dataset.vocabMastered !== '1';

    button.disabled = true;
    this.persistVocabularyStatus({ word, pronunciation, meaning, mastered, article_id: this.articleId ? Number(this.articleId) : null })
      .then((data) => {
        item.dataset.vocabMastered = data.mastered ? '1' : '0';
        this.refreshVocabView();
      })
      .catch((error) => {
        console.error('保存生词状态失败', error);
        if (this.resultDiv) {
          this.resultDiv.innerHTML = `<p style="color: var(--danger-color);">保存生词状态失败：${error.message}</p>`;
        }
      })
      .finally(() => {
        button.disabled = false;
      });
  }

  persistVocabularyStatus(payload) {
    return fetch('/vocabulary/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(async (response) => {
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.error || '保存失败');
      }
      return data;
    });
  }

  refreshVocabView() {
    document.querySelectorAll('.vocab-item').forEach((item) => {
      const isMastered = item.dataset.vocabMastered === '1';
      item.classList.toggle('is-mastered', isMastered);
      item.classList.toggle('is-hidden', this.state.hideMastered && isMastered);
      const button = item.querySelector('.btn-remove');
      if (button) {
        button.textContent = isMastered ? '取消掌握' : '已掌握';
      }
    });
  }

  updateToggleMasteredButton() {
    if (!this.toggleMasteredBtn) {
      return;
    }
    this.toggleMasteredBtn.textContent = this.state.hideMastered ? '显示已掌握' : '隐藏已掌握';
  }

  evaluateSpeech(recognizedText) {
    if (!this.resultDiv || !this.originalTextEl) {
      return;
    }

    const originalText = this.originalTextEl.textContent || '';

    fetch('/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        original: originalText,
        recognized: recognizedText
      })
    })
      .then((response) => response.json())
      .then((data) => {
        const scoreColor = data.score >= 80 ? 'var(--success-color)' : data.score >= 60 ? 'var(--warning-color)' : 'var(--danger-color)';
        this.resultDiv.innerHTML += `<p><strong>评分：</strong><span style="color: ${scoreColor}; font-size: 1.2em;">${data.score}/100</span></p>`;
      })
      .catch((error) => {
        console.error('评测错误:', error);
        this.resultDiv.innerHTML += '<p style="color: var(--danger-color);">评测失败，请重试</p>';
      });
  }

  cacheContent() {
    try {
      const data = {
        original: this.originalTextEl?.textContent || '',
        ruby: this.highlightTextEl?.innerHTML || '',
        translation: document.querySelector('.translation-text')?.innerHTML || '',
        title: document.getElementById('lesson-title')?.textContent || '',
        vocab: Array.from(document.querySelectorAll('.vocab-item')).map((item) => ({
          word: item.dataset.vocabWord || item.querySelector('.vocab-word')?.textContent || '',
          pronunciation: item.dataset.vocabPronunciation || item.querySelector('.vocab-pronunciation')?.textContent || '',
          meaning: item.querySelector('.vocab-meaning')?.textContent || '',
          mastered: item.dataset.vocabMastered === '1',
          article_id: this.articleId ? Number(this.articleId) : null
        })),
        ts: Date.now()
      };

      if (data.original) {
        localStorage.setItem('lessonContent', JSON.stringify(data));
      }
    } catch (error) {
      console.warn('缓存失败', error);
    }
  }
}

document.addEventListener('DOMContentLoaded', function () {
  try {
    speechRecognitionManager = new SpeechRecognitionManager();
    textHighlighter = new TextHighlighter();
    pdfExporter = new PDFExporter();

    const originalText = document.getElementById('original-text')?.textContent || '';
    const rubyText = document.getElementById('ruby-text-data')?.innerHTML || '';
    textHighlighter.setContent(originalText, rubyText);

    const highlightEl = document.getElementById('highlight-text');
    if (highlightEl) {
      highlightEl.innerHTML = rubyText;
    }

    const controller = new ReadingPageController();
    controller.init();

    window.speakVocabWord = controller.speakVocabWord.bind(controller);
    window.toggleVocabMastered = controller.toggleVocabMastered.bind(controller);
    window.stopReadingSpeech = controller.stopSpeech.bind(controller);
  } catch (error) {
    console.error('阅读页初始化失败', error);
  }
});
