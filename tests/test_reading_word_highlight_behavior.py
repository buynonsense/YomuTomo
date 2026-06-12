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


def test_audio_time_update_progresses_word_index_by_char_position():
    """audio.currentTime 推进时，word index 按 char position 比例前进。"""
    module_path = Path('/Users/buynonsense/Dev/YomuTomo/static/js/pages/reading.js')
    script = f"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync({module_path.as_posix()!r}, 'utf8') + '\\n;globalThis.ReadingPageController = ReadingPageController;';

const sandbox = {{
  console: {{ warn() {{}}, error() {{}} }},
  window: {{
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
  TTSWordHighlighter: class {{
    buildSentenceMarkup() {{ return {{ html: '', wordCount: 3, wordRanges: [
      {{ text: '今日は', start: 0, end: 3, wordIndex: 0 }},
      {{ text: '天気', start: 3, end: 5, wordIndex: 1 }},
      {{ text: 'です', start: 5, end: 7, wordIndex: 2 }},
    ] }}; }}
    findWordIndexAtCharIndex(wordRanges, charIndex) {{
      const match = wordRanges.find((range) => charIndex >= range.start && charIndex < range.end);
      return match ? match.wordIndex : -1;
    }}
  }},
  Intl: {{ Segmenter: class {{ constructor() {{}} segment() {{ return [].values(); }} }} }},
  module: {{ exports: {{}} }},
  exports: {{}},
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
controller.syncSentenceHighlight = function () {{}};

// duration=7, totalChars=7：currentTime × (totalChars/duration) = currentTime
// charIndex 0→word 0; charIndex 3→word 1; charIndex 4→word 1; charIndex 5→word 2;
// charIndex 7 边界：findWordIndexAtCharIndex 返回 -1，强制落到最后一个 word 2
const samples = [];
for (const t of [0, 3, 4, 5, 7]) {{
  controller.audio = {{ duration: 7.0, currentTime: t }};
  controller.onAudioTimeUpdate(42, 0);
  samples.push(controller.currentWordIndex);
}}
console.log(JSON.stringify({{ progress: samples }}));
"""

    output = run_node(script)
    result = json.loads(output)
    assert result == {'progress': [0, 1, 1, 2, 2]}


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
