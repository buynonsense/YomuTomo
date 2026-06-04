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


def test_segment_sentence_falls_back_to_sentence_when_no_segmenter():
    module_path = Path('/Users/buynonsense/Dev/YomuTomo/static/js/modules/tts-word-highlighter.js')
    script = f"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync({module_path.as_posix()!r}, 'utf8');
const sandbox = {{
  console: {{ warn() {{}} }},
  window: {{}},
  globalThis: {{}},
  module: {{ exports: {{}} }},
  exports: {{}},
  Intl: undefined,
}};
sandbox.globalThis = sandbox;
sandbox.window = sandbox;
vm.runInNewContext(code, sandbox);
const highlighter = new sandbox.TTSWordHighlighter();
const segments = highlighter.segmentSentence('今日は天気です。');
console.log(JSON.stringify(segments));
"""

    output = run_node(script)
    assert output == '[{"text":"今日は天気です。","isWordLike":false}]'


def test_build_sentence_markup_marks_words_and_punctuation():
    module_path = Path('/Users/buynonsense/Dev/YomuTomo/static/js/modules/tts-word-highlighter.js')
    script = f"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync({module_path.as_posix()!r}, 'utf8');
const sandbox = {{
  console: {{ warn() {{}} }},
  window: {{}},
  globalThis: {{}},
  module: {{ exports: {{}} }},
  exports: {{}},
  Intl: {{
    Segmenter: class {{
      constructor() {{}}
      segment(text) {{
        return [
          {{ segment: '今日は', isWordLike: true }},
          {{ segment: '天気', isWordLike: true }},
          {{ segment: 'です', isWordLike: true }},
          {{ segment: '。', isWordLike: false }},
        ][Symbol.iterator]();
      }}
    }}
  }},
}};
sandbox.globalThis = sandbox;
sandbox.window = sandbox;
vm.runInNewContext(code, sandbox);
const highlighter = new sandbox.TTSWordHighlighter();
const result = highlighter.buildSentenceMarkup('今日は天気です。');
console.log(JSON.stringify(result));
"""

    output = run_node(script)
    result = json.loads(output)
    assert 'sentence-token--word' in result['html']
    assert 'data-word-index="0"' in result['html']
    assert 'sentence-token--punct' in result['html']
    assert result['wordCount'] == 3


def test_find_word_index_at_char_index_maps_to_word_range():
    module_path = Path('/Users/buynonsense/Dev/YomuTomo/static/js/modules/tts-word-highlighter.js')
    script = f"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync({module_path.as_posix()!r}, 'utf8');
const sandbox = {{
  console: {{ warn() {{}} }},
  window: {{}},
  globalThis: {{}},
  module: {{ exports: {{}} }},
  exports: {{}},
  Intl: {{
    Segmenter: class {{
      constructor() {{}}
      segment(text) {{
        return [
          {{ segment: '今日は', isWordLike: true }},
          {{ segment: '天気', isWordLike: true }},
          {{ segment: 'です', isWordLike: true }},
          {{ segment: '。', isWordLike: false }},
        ][Symbol.iterator]();
      }}
    }}
  }},
}};
sandbox.globalThis = sandbox;
sandbox.window = sandbox;
vm.runInNewContext(code, sandbox);
const highlighter = new sandbox.TTSWordHighlighter();
const result = highlighter.buildSentenceMarkup('今日は天気です。');
console.log(JSON.stringify({{
  first: highlighter.findWordIndexAtCharIndex(result.wordRanges, 0),
  second: highlighter.findWordIndexAtCharIndex(result.wordRanges, 3),
  third: highlighter.findWordIndexAtCharIndex(result.wordRanges, 5),
  none: highlighter.findWordIndexAtCharIndex(result.wordRanges, 20),
}}));
"""

    output = run_node(script)
    result = json.loads(output)
    assert result == {'first': 0, 'second': 1, 'third': 2, 'none': -1}
