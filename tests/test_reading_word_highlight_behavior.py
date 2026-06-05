import json
from pathlib import Path
import subprocess


def run_node(script: str) -> str:
    completed = subprocess.run(
        ['node', '-e', script],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_boundary_event_cancels_fallback_and_updates_word_index():
    module_path = Path('/Users/buynonsense/Dev/YomuTomo/static/js/pages/reading.js')
    script = f"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync({module_path.as_posix()!r}, 'utf8') + '\\n;globalThis.ReadingPageController = ReadingPageController;';

const scheduledTimeouts = [];
const scheduledIntervals = [];
let nextTimerId = 1;

function makeWordNode(wordIndex) {{
  return {{
    dataset: {{ wordIndex: String(wordIndex) }},
    classList: {{ toggle() {{}} }}
  }};
}}

const sentenceItem = {{
  dataset: {{ index: '0' }},
  querySelectorAll(selector) {{
    if (selector === '.sentence-token--word') {{
      return [makeWordNode(0), makeWordNode(1), makeWordNode(2)];
    }}
    return [];
  }},
  classList: {{ toggle() {{}} }},
  setAttribute() {{}},
  scrollIntoView() {{}}
}};

const utterance = {{
  listeners: {{ }},
  addEventListener(type, callback) {{ this.listeners[type] = callback; }},
}};

const sandbox = {{
  console: {{ warn() {{}}, error() {{}} }},
  window: {{
    speechSynthesis: {{ speak() {{}}, cancel() {{}} }},
    setTimeout(callback) {{
      const id = nextTimerId++;
      scheduledTimeouts.push({{ id, callback }});
      return id;
    }},
    clearTimeout(id) {{
      const index = scheduledTimeouts.findIndex((timer) => timer.id === id);
      if (index >= 0) {{ scheduledTimeouts.splice(index, 1); }}
    }},
    setInterval(callback) {{
      const id = nextTimerId++;
      scheduledIntervals.push({{ id, callback }});
      return id;
    }},
    clearInterval(id) {{
      const index = scheduledIntervals.findIndex((timer) => timer.id === id);
      if (index >= 0) {{ scheduledIntervals.splice(index, 1); }}
    }},
    scrollTo() {{}}
  }},
  document: {{
    body: {{ dataset: {{}}, classList: {{ remove() {{}}, add() {{}} }} }},
    querySelectorAll(selector) {{
      if (selector === '.sentence-item') {{
        return [sentenceItem];
      }}
      return [];
    }},
    getElementById() {{ return null; }},
    addEventListener() {{}},
  }},
  localStorage: {{ getItem() {{ return null; }}, setItem() {{}} }},
  SpeechRecognitionManager: class {{ constructor() {{ this.isInitialized = false; }} }},
  TextHighlighter: class {{ setContent() {{}} highlightText() {{}} }},
  PDFExporter: class {{ exportToPDF() {{}} }},
  TTSWordHighlighter: class {{
    buildSentenceMarkup() {{
      return {{
        html: '<span class="sentence-token sentence-token--word" data-word-index="0">今日は</span><span class="sentence-token sentence-token--word" data-word-index="1">天気</span><span class="sentence-token sentence-token--word" data-word-index="2">です</span>。',
        wordCount: 3,
        wordRanges: [
          {{ text: '今日は', start: 0, end: 3, wordIndex: 0 }},
          {{ text: '天気', start: 3, end: 5, wordIndex: 1 }},
          {{ text: 'です', start: 5, end: 7, wordIndex: 2 }},
        ]
      }};
    }}
    findWordIndexAtCharIndex(wordRanges, charIndex) {{
      const match = wordRanges.find((range) => charIndex >= range.start && charIndex < range.end);
      return match ? match.wordIndex : -1;
    }}
  }},
  Intl: {{ Segmenter: class {{ constructor() {{}} segment() {{ return [{{ segment: '今日は', isWordLike: true }}, {{ segment: '天気', isWordLike: true }}, {{ segment: 'です', isWordLike: true }}, {{ segment: '。', isWordLike: false }}][Symbol.iterator](); }} }} }},
  module: {{ exports: {{}} }},
  exports: {{}} ,
  globalThis: null,
}};
sandbox.globalThis = sandbox;
sandbox.window.globalThis = sandbox;

vm.runInNewContext(code, sandbox);
const controller = new sandbox.ReadingPageController();
controller.sentenceItems = [{{ text: '今日は天気です。', html: '', wordCount: 3, wordRanges: [
  {{ text: '今日は', start: 0, end: 3, wordIndex: 0 }},
  {{ text: '天気', start: 3, end: 5, wordIndex: 1 }},
  {{ text: 'です', start: 5, end: 7, wordIndex: 2 }},
] }}];
controller.wordHighlighter = new sandbox.TTSWordHighlighter();
controller.currentSentenceIndex = 0;
controller.playbackSessionId = 42;
controller.ttsPlayBtn = {{ disabled: false }};
controller.ttsStopBtn = {{ disabled: true }};
controller.updateTtsButtons = function () {{}};
controller.syncSentenceHighlight = function () {{}};

controller.startWordHighlight(42, 0, utterance);
utterance.listeners.boundary({{ charIndex: 3 }});

for (const timer of [...scheduledTimeouts]) {{
  timer.callback();
}}

console.log(JSON.stringify({{
  wordIndex: controller.currentWordIndex,
  boundaryDriven: controller.boundaryDrivenPlayback,
  timeoutCount: scheduledTimeouts.length,
  intervalCount: scheduledIntervals.length,
}}));
"""

    output = run_node(script)
    result = json.loads(output)
    assert result == {
        'wordIndex': 1,
        'boundaryDriven': True,
        'timeoutCount': 0,
        'intervalCount': 0,
    }


def test_stop_speech_invalidates_old_playback_session():
    module_path = Path('/Users/buynonsense/Dev/YomuTomo/static/js/pages/reading.js')
    script = f"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync({module_path.as_posix()!r}, 'utf8') + '\\n;globalThis.ReadingPageController = ReadingPageController;';

const sandbox = {{
  console: {{ warn() {{}}, error() {{}} }},
  window: {{
    speechSynthesis: {{ cancel() {{}}, speak() {{}} }},
    setTimeout(callback) {{ return 1; }},
    clearTimeout() {{}},
    setInterval(callback) {{ return 2; }},
    clearInterval() {{}},
    scrollTo() {{}}
  }},
  document: {{
    body: {{ dataset: {{}}, classList: {{ remove() {{}}, add() {{}} }} }},
    querySelectorAll() {{ return []; }},
    getElementById() {{ return null; }},
    addEventListener() {{}},
  }},
  localStorage: {{ getItem() {{ return null; }}, setItem() {{}} }},
  SpeechRecognitionManager: class {{ constructor() {{ this.isInitialized = false; }} }},
  TextHighlighter: class {{ setContent() {{}} highlightText() {{}} }},
  PDFExporter: class {{ exportToPDF() {{}} }},
  TTSWordHighlighter: class {{ buildSentenceMarkup() {{ return {{ html: '', wordCount: 0, wordRanges: [] }}; }} findWordIndexAtCharIndex() {{ return -1; }} }},
  Intl: {{ Segmenter: class {{ constructor() {{}} segment() {{ return [{{ segment: '今天', isWordLike: true }}][Symbol.iterator](); }} }} }},
  module: {{ exports: {{}} }},
  exports: {{}} ,
  globalThis: null,
}};
sandbox.globalThis = sandbox;
sandbox.window.globalThis = sandbox;

vm.runInNewContext(code, sandbox);
const controller = new sandbox.ReadingPageController();
controller.currentSentenceIndex = 0;
controller.currentWordIndex = 2;
controller.stopWordHighlight = function () {{ this.currentWordIndex = -1; }};
controller.syncSentenceHighlight = function () {{}};
controller.updateTtsButtons = function () {{}};

controller.playbackSessionId = 7;
controller.stopSpeech();

console.log(JSON.stringify({{
  playbackSessionId: controller.playbackSessionId,
  currentWordIndex: controller.currentWordIndex,
  currentSentenceIndex: controller.currentSentenceIndex,
}}));
"""

    output = run_node(script)
    result = json.loads(output)
    assert result == {
        'playbackSessionId': 8,
        'currentWordIndex': -1,
        'currentSentenceIndex': -1,
    }
