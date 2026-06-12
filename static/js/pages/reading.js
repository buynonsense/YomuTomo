/**
 * Reading Page JavaScript
 * 阅读页面专用 JavaScript
 */

let speechRecognitionManager;
let textHighlighter;
let pdfExporter;
let ttsWordHighlighter;

class ReadingPageController {
  constructor() {
    this.storageKey = 'yomu-reading-state';
    this.state = this.loadState();
    this.sentenceItems = [];
    this.currentSentenceIndex = -1;
    this.currentWordIndex = -1;
    this.currentWordTimer = null;
    this.currentWordFallbackTimer = null;
    this.lastScrolledSentenceIndex = -1;
    this.playbackSessionId = 0;
    this.vocabSpeechSessionId = 0;
    this.currentUtterance = null;
    this.speechSupported = 'speechSynthesis' in window;
    this.root = document.body;
    this.wordHighlighter = null;
    this.boundaryDrivenPlayback = false;
    this.evaluationDetailEl = null;
    this.evaluationOriginalEl = null;
    this.evaluationRecognizedEl = null;
    this.evaluationSummaryEl = null;
    this.levelFilter = this.state.furiganaLevelFilter || 1;
  }

  init() {
    this.cacheDom();
    this.bindSpeechRecognition();
    this.bindPdfExport();
    this.bindFuriganaMode();
    this.bindTtsControls();
    this.bindVocabControls();
    this.bindBackToTop();
    this.bindFuriganaLevelFilter();
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
    this.evaluationDetailEl = document.getElementById('evaluation-detail');
    this.evaluationOriginalEl = document.getElementById('evaluation-original-html');
    this.evaluationRecognizedEl = document.getElementById('evaluation-recognized-html');
    this.evaluationSummaryEl = document.getElementById('evaluation-summary');
  }

  loadState() {
    try {
      const raw = localStorage.getItem(this.storageKey);
      if (!raw) {
        return {
          furiganaMode: 'show',
          hideMastered: false,
          furiganaLevelFilter: 1
        };
      }
      const parsed = JSON.parse(raw);
      return {
        furiganaMode: parsed.furiganaMode || 'show',
        hideMastered: Boolean(parsed.hideMastered),
        furiganaLevelFilter: Number(parsed.furiganaLevelFilter || 1)
      };
    } catch (error) {
      console.warn('读取阅读页状态失败', error);
      return {
        furiganaMode: 'show',
        hideMastered: false,
        furiganaLevelFilter: 1
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
    this.applyFuriganaLevelFilter(this.state.furiganaLevelFilter);
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

  bindFuriganaLevelFilter() {
    const levelButtons = document.querySelectorAll('[data-furigana-level]');
    levelButtons.forEach((button) => {
      button.addEventListener('click', () => {
        const level = Number(button.dataset.furiganaLevel || '1');
        this.applyFuriganaLevelFilter(level);
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

  applyFuriganaLevelFilter(level) {
    const normalized = [1, 2, 3, 4, 5].includes(Number(level)) ? Number(level) : 1;
    this.levelFilter = normalized;
    this.state.furiganaLevelFilter = normalized;
    document.body.dataset.furiganaLevelFilter = String(normalized);

    document.querySelectorAll('[data-furigana-level]').forEach((button) => {
      button.classList.toggle('btn-primary', Number(button.dataset.furiganaLevel || '1') === normalized);
      button.classList.toggle('btn-secondary', Number(button.dataset.furiganaLevel || '1') !== normalized);
    });

    const rubyText = this.rubyTextEl?.innerHTML || this.highlightTextEl?.innerHTML || '';
    if (!rubyText) {
      return;
    }

    const parsed = window.FuriganaFilter && typeof window.FuriganaFilter.apply === 'function'
      ? window.FuriganaFilter.apply(rubyText, normalized)
      : rubyText;
    if (this.highlightTextEl) {
      this.highlightTextEl.innerHTML = parsed;
    }
    if (textHighlighter && typeof textHighlighter.setContent === 'function') {
      textHighlighter.setContent(this.originalTextEl?.textContent || '', parsed);
    }
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

    document.addEventListener('click', (event) => {
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }

      const button = target.closest('[data-vocab-action]');
      if (!button) {
        return;
      }

      const action = button.getAttribute('data-vocab-action');
      if (action === 'speak') {
        this.speakVocabWord(button);
        return;
      }

      if (action === 'toggle-mastered') {
        this.toggleVocabMastered(button);
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
    this.wordHighlighter = ttsWordHighlighter || (window.TTSWordHighlighter ? new window.TTSWordHighlighter() : null);
    this.sentenceItems = sentences.map((sentence) => {
      const built = this.buildSentenceView(sentence);
      return {
        text: sentence,
        html: built.html,
        wordCount: built.wordCount
      };
    });
    this.sentenceListEl.innerHTML = '';

    if (!this.sentenceItems.length) {
      this.sentenceListEl.innerHTML = '<p class="sentence-empty">没有可播放的句子。</p>';
      return;
    }

    this.sentenceItems.forEach((sentenceItem, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'sentence-item';
      button.dataset.index = String(index);
      button.dataset.wordCount = String(sentenceItem.wordCount);
      button.dataset.wordRanges = JSON.stringify(sentenceItem.wordRanges || []);
      button.innerHTML = sentenceItem.html;
      button.addEventListener('click', () => {
        this.playSentence(index);
      });
      this.sentenceListEl.appendChild(button);
    });
  }

  buildSentenceView(sentence) {
    if (this.wordHighlighter && typeof this.wordHighlighter.buildSentenceMarkup === 'function') {
      return this.wordHighlighter.buildSentenceMarkup(sentence);
    }

    const text = (sentence || '').trim();
    return {
      html: text,
      wordCount: text ? 1 : 0,
      segments: [{ text, isWordLike: Boolean(text) }]
    };
  }

  splitSentences(text) {
    const normalized = (text || '').replace(/\r\n/g, '\n').trim();
    if (!normalized) {
      return [];
    }

    // 防御性清理：历史数据里 article.original 开头可能带 "来源: <url>\n\n" 前缀
    // 这里只 strip 行首的 "来源:" 行，避免污染句子列表
    const stripped = normalized.replace(/^来源\s*[:：]\s*[^\n]*\n+/, '').trim();
    if (!stripped) {
      return [];
    }

    const parts = stripped
      .split(/(?<=[。！？!?])\s*|\n+/)
      .map((part) => part.trim())
      .filter(Boolean);

    return parts.length ? parts : [stripped];
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
    this.lastScrolledSentenceIndex = -1;
    this.startPlaybackSession();
    this.speakSequence(this.playbackSessionId, 0);
  }

  clearWordTimer() {
    if (this.currentWordTimer) {
      window.clearInterval(this.currentWordTimer);
      this.currentWordTimer = null;
    }
    if (this.currentWordFallbackTimer) {
      window.clearTimeout(this.currentWordFallbackTimer);
      this.currentWordFallbackTimer = null;
    }
  }

  startPlaybackSession() {
    this.playbackSessionId += 1;
    return this.playbackSessionId;
  }

  isActivePlayback(sessionId) {
    return sessionId === this.playbackSessionId;
  }

  startWordHighlight(sessionId, sentenceIndex, utterance) {
    const sentenceItem = this.sentenceItems[sentenceIndex];
    if (!sentenceItem || sentenceItem.wordCount <= 0) {
      this.currentWordIndex = -1;
      this.clearWordTimer();
      this.syncSentenceHighlight();
      return;
    }

    this.clearWordTimer();
    this.currentWordIndex = -1;
    this.boundaryDrivenPlayback = false;
    this.syncSentenceHighlight();

    const canUseBoundaryEvents = Boolean(utterance && typeof utterance.addEventListener === 'function');

    if (canUseBoundaryEvents) {
      utterance.addEventListener('boundary', (event) => {
        if (!this.isActivePlayback(sessionId)) {
          return;
        }

        if (!event || typeof event.charIndex !== 'number') {
          return;
        }

        const wordIndex = this.wordHighlighter?.findWordIndexAtCharIndex(sentenceItem.wordRanges, event.charIndex) ?? -1;
        if (wordIndex < 0) {
          return;
        }

        this.boundaryDrivenPlayback = true;
        this.clearWordTimer();
        this.currentWordIndex = wordIndex;
        this.syncSentenceHighlight();
      });
    }

    if (sentenceItem.wordCount === 1) {
      return;
    }

    this.currentWordFallbackTimer = window.setTimeout(() => {
      if (!this.isActivePlayback(sessionId) || this.boundaryDrivenPlayback) {
        return;
      }

      const interval = Math.max(180, Math.round(1200 / sentenceItem.wordCount));
      let wordIndex = 0;
      this.currentWordIndex = 0;
      this.syncSentenceHighlight();

      this.currentWordTimer = window.setInterval(() => {
        if (!this.isActivePlayback(sessionId)) {
          this.clearWordTimer();
          return;
        }

        wordIndex += 1;
        this.currentWordIndex = Math.min(wordIndex, sentenceItem.wordCount - 1);
        this.syncSentenceHighlight();

        if (wordIndex >= sentenceItem.wordCount - 1) {
          this.clearWordTimer();
        }
      }, interval);
    }, 80);
  }

  stopWordHighlight() {
    this.clearWordTimer();
    this.currentWordIndex = -1;
    this.boundaryDrivenPlayback = false;
  }

  speakSequence(sessionId, index) {
    if (!this.isActivePlayback(sessionId)) {
      return;
    }

    if (index >= this.sentenceItems.length) {
      this.currentSentenceIndex = -1;
      this.stopWordHighlight();
      this.syncSentenceHighlight();
      this.updateTtsButtons(false);
      return;
    }

    const sentenceItem = this.sentenceItems[index];
    const sentence = sentenceItem.text;
    this.currentSentenceIndex = index;
    this.currentWordIndex = -1;
    this.syncSentenceHighlight();
    this.updateTtsButtons(true);

    const utterance = this.createUtterance(sentence);
    utterance.onstart = () => {
      if (!this.isActivePlayback(sessionId)) {
        return;
      }

      this.currentSentenceIndex = index;
      this.lastScrolledSentenceIndex = -1;
      this.startWordHighlight(sessionId, index, utterance);
      this.syncSentenceHighlight();
    };
    utterance.onend = () => {
      if (!this.isActivePlayback(sessionId)) {
        return;
      }

      this.stopWordHighlight();
      this.speakSequence(sessionId, index + 1);
    };
    utterance.onerror = (event) => {
      if (!this.isActivePlayback(sessionId)) {
        return;
      }

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

    const sentenceItem = this.sentenceItems[index];
    if (!sentenceItem) {
      return;
    }

    this.stopSpeech();
    const sessionId = this.startPlaybackSession();
    this.currentSentenceIndex = index;
    this.currentWordIndex = -1;
    this.lastScrolledSentenceIndex = -1;
    this.syncSentenceHighlight();
    this.updateTtsButtons(true);

    const utterance = this.createUtterance(sentenceItem.text);
    utterance.onstart = () => {
      if (!this.isActivePlayback(sessionId)) {
        return;
      }

      this.currentSentenceIndex = index;
      this.lastScrolledSentenceIndex = -1;
      this.startWordHighlight(sessionId, index, utterance);
      this.syncSentenceHighlight();
    };
    utterance.onend = () => {
      if (!this.isActivePlayback(sessionId)) {
        return;
      }

      this.currentSentenceIndex = -1;
      this.stopWordHighlight();
      this.syncSentenceHighlight();
      this.updateTtsButtons(false);
    };
    utterance.onerror = (event) => {
      if (!this.isActivePlayback(sessionId)) {
        return;
      }

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
    this.playbackSessionId += 1;
    this.vocabSpeechSessionId += 1;
    this.currentUtterance = null;
    this.currentSentenceIndex = -1;
    this.stopWordHighlight();
    this.lastScrolledSentenceIndex = -1;
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

      const words = item.querySelectorAll('.sentence-token--word');
      words.forEach((wordNode) => {
        const wordIndex = Number(wordNode.dataset.wordIndex);
        const isSentenceActive = index === this.currentSentenceIndex;
        const isCurrentWord = isSentenceActive && this.currentWordIndex === wordIndex;
        const isPastWord = isSentenceActive && this.currentWordIndex > wordIndex;
        wordNode.classList.toggle('is-active', isCurrentWord);
        wordNode.classList.toggle('is-pending', isSentenceActive && (isPastWord || (this.currentWordIndex >= 0 && this.currentWordIndex < wordIndex)));
      });
    });

    if (this.currentSentenceIndex >= 0 && this.currentSentenceIndex !== this.lastScrolledSentenceIndex) {
      const activeItem = document.querySelector(`.sentence-item[data-index="${this.currentSentenceIndex}"]`);
      if (activeItem) {
        activeItem.scrollIntoView({ block: 'center', behavior: 'smooth' });
        this.lastScrolledSentenceIndex = this.currentSentenceIndex;
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
    const sessionId = ++this.vocabSpeechSessionId;
    const utterance = this.createUtterance(text);
    this.currentUtterance = utterance;
    utterance.onstart = () => {
      if (sessionId !== this.vocabSpeechSessionId) {
        return;
      }

      this.currentUtterance = utterance;
    };
    utterance.onend = () => {
      if (sessionId !== this.vocabSpeechSessionId) {
        return;
      }

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
    if (this.evaluationSummaryEl) {
      this.evaluationSummaryEl.innerHTML = '<p>正在评测朗读结果…</p>';
    }
    if (this.evaluationDetailEl) {
      this.evaluationDetailEl.hidden = true;
    }

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
        if (this.evaluationDetailEl) {
          this.evaluationDetailEl.hidden = false;
        }
        if (this.evaluationOriginalEl) {
          this.evaluationOriginalEl.innerHTML = data.original_html || '';
        }
        if (this.evaluationRecognizedEl) {
          this.evaluationRecognizedEl.innerHTML = data.recognized_html || '';
        }
        if (this.evaluationSummaryEl) {
          this.evaluationSummaryEl.innerHTML = `
            <p><strong>评分：</strong><span style="color: ${scoreColor}; font-size: 1.2em;">${data.score}/100</span></p>
            <p>匹配词块：${data.matched_tokens || 0} / ${data.original_tokens || 0}</p>
            <p>遗漏词块：${data.miss_tokens || 0}，多读词块：${data.extra_tokens || 0}</p>
          `;
        }
      })
      .catch((error) => {
        console.error('评测错误:', error);
        if (this.evaluationSummaryEl) {
          this.evaluationSummaryEl.innerHTML = '<p style="color: var(--danger-color);">评测失败，请重试</p>';
        }
        if (this.evaluationDetailEl) {
          this.evaluationDetailEl.hidden = true;
        }
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
    ttsWordHighlighter = new TTSWordHighlighter();
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

    const highlightDataEl = document.getElementById('notification-highlight-data');
    const highlightNotificationId = highlightDataEl?.dataset.highlightNotification || new URLSearchParams(window.location.search).get('highlight_notification') || '';
    const highlightArticleId = highlightDataEl?.dataset.highlightArticle || new URLSearchParams(window.location.search).get('highlight_article') || '';

    if (highlightNotificationId) {
      const highlightTarget = document.getElementById('highlight-text');
      if (highlightTarget) {
        highlightTarget.classList.add('notification-highlight-pulse');
        window.setTimeout(() => {
          highlightTarget.classList.remove('notification-highlight-pulse');
        }, 2200);
        window.setTimeout(() => {
          highlightTarget.scrollIntoView({ block: 'center', behavior: 'smooth' });
        }, 120);
      }
    }

    if (highlightArticleId) {
      const articleEl = document.getElementById(`article-${highlightArticleId}`);
      if (articleEl) {
        articleEl.classList.add('notification-highlight-pulse');
        window.setTimeout(() => {
          articleEl.classList.remove('notification-highlight-pulse');
        }, 2200);
        window.setTimeout(() => {
          articleEl.scrollIntoView({ block: 'center', behavior: 'smooth' });
        }, 120);
      }
    }
  } catch (error) {
    console.error('阅读页初始化失败', error);
  }
});
