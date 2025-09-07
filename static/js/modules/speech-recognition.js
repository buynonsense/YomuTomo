/**
 * Speech Recognition Module
 * 语音识别模块
 */

class SpeechRecognitionManager {
  constructor() {
    this.recognition = null;
    this.finalTranscript = '';
    this.isInitialized = false;

    this.init();
  }

  init() {
    if ('webkitSpeechRecognition' in window) {
      this.recognition = new webkitSpeechRecognition();
      this.recognition.continuous = true;
      this.recognition.interimResults = true;
      this.recognition.lang = 'ja-JP';
      this.isInitialized = true;
    } else {
      console.warn('浏览器不支持语音识别');
    }
  }

  startRecording() {
    if (!this.recognition) return false;

    this.finalTranscript = '';
    this.recognition.start();

    // Update UI
    this.updateRecordingUI(true);
    return true;
  }

  stopRecording() {
    if (!this.recognition) return;

    this.recognition.stop();
    this.updateRecordingUI(false);
  }

  updateRecordingUI(isRecording) {
    const recordBtn = document.getElementById('record-btn');
    const stopBtn = document.getElementById('stop-btn');
    const resultDiv = document.getElementById('result');

    if (recordBtn) {
      recordBtn.disabled = isRecording;
      recordBtn.innerHTML = isRecording ? '🎤 录音中...' : '▶️ 开始录音';
    }

    if (stopBtn) {
      stopBtn.disabled = !isRecording;
    }

    if (resultDiv && !isRecording) {
      resultDiv.innerHTML = '<p style="color: var(--warning-color);">录音已停止，正在处理...</p>';
    } else if (resultDiv && isRecording) {
      resultDiv.innerHTML = '<p style="color: var(--success-color);">正在录音，请开始朗读...</p>';
    }

    // Toggle recording effects
    const readingContainer = document.querySelector('.main-content');
    const highlightText = document.getElementById('highlight-text');

    if (readingContainer) {
      if (isRecording) {
        readingContainer.classList.add('recording-active');
      } else {
        readingContainer.classList.remove('recording-active');
      }
    }

    if (highlightText) {
      if (isRecording) {
        // Show ruby text with glow effect
        const rubyTextElement = document.getElementById('ruby-text-data');
        const rubyText = rubyTextElement ? rubyTextElement.innerHTML : '';
        highlightText.innerHTML = rubyText;
        highlightText.classList.add('glow-active');
      } else {
        highlightText.classList.remove('glow-active');
      }
    }
  }

  onResult(callback) {
    if (!this.recognition) return;

    this.recognition.onresult = (event) => {
      let interimTranscript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        let transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          this.finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }

      // Update result display
      const resultDiv = document.getElementById('result');
      if (resultDiv) {
        resultDiv.innerHTML = `
          <p><strong>识别文本：</strong>${this.finalTranscript}<span style="color: var(--text-secondary); font-style: italic;">${interimTranscript}</span></p>
        `;
      }

      // Call callback with results
      if (callback) {
        callback(this.finalTranscript, interimTranscript);
      }
    };
  }

  onError(callback) {
    if (!this.recognition) return;

    this.recognition.onerror = (event) => {
      console.error('语音识别错误:', event.error);

      const resultDiv = document.getElementById('result');
      if (resultDiv) {
        resultDiv.innerHTML = `<p style="color: var(--danger-color);">语音识别错误: ${event.error}</p>`;
      }

      this.resetButtons();

      if (callback) {
        callback(event.error);
      }
    };
  }

  onEnd(callback) {
    if (!this.recognition) return;

    this.recognition.onend = () => {
      this.resetButtons();

      if (this.finalTranscript && callback) {
        callback(this.finalTranscript);
      }
    };
  }

  resetButtons() {
    const recordBtn = document.getElementById('record-btn');
    const stopBtn = document.getElementById('stop-btn');

    if (recordBtn) {
      recordBtn.disabled = false;
      recordBtn.innerHTML = '▶️ 开始录音';
    }
    if (stopBtn) {
      stopBtn.disabled = true;
    }

    // Remove recording effects
    const readingContainer = document.querySelector('.main-content');
    const highlightText = document.getElementById('highlight-text');

    if (readingContainer) {
      readingContainer.classList.remove('recording-active');
    }

    if (highlightText) {
      highlightText.classList.remove('glow-active');
    }
  }

  getFinalTranscript() {
    return this.finalTranscript;
  }

  clearTranscript() {
    this.finalTranscript = '';
  }
}

// Export for global use
window.SpeechRecognitionManager = SpeechRecognitionManager;
