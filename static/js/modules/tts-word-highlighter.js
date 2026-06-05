/**
 * TTS Word Highlighter Module
 * 朗读词块高亮模块
 */

(function (root, factory) {
  const api = factory();

  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  }

  root.TTSWordHighlighter = api.TTSWordHighlighter;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  class TTSWordHighlighter {
    escapeHtml(text) {
      return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    segmentSentence(sentence) {
      const text = String(sentence || '').trim();
      if (!text) {
        return [];
      }

      if (typeof Intl !== 'undefined' && typeof Intl.Segmenter === 'function') {
        try {
          const segmenter = new Intl.Segmenter('ja', { granularity: 'word' });
          return Array.from(segmenter.segment(text))
            .map((part) => ({
              text: part.segment,
              isWordLike: Boolean(part.isWordLike)
            }))
            .filter((part) => part.text.length > 0);
        } catch (error) {
          console.warn('句子词块切分失败，回退为整句', error);
        }
      }

      return [{ text, isWordLike: false }];
    }

    buildSentenceMarkup(sentence) {
      const segments = this.segmentSentence(sentence);
      let wordIndex = 0;
      let charIndex = 0;
      const wordRanges = [];

      const html = segments
        .map((segment) => {
          const start = charIndex;
          charIndex += segment.text.length;
          const end = charIndex;
          const escaped = this.escapeHtml(segment.text);
          if (!segment.isWordLike) {
            return `<span class="sentence-token sentence-token--punct" data-char-start="${start}" data-char-end="${end}">${escaped}</span>`;
          }

          const index = wordIndex;
          wordIndex += 1;
          wordRanges.push({
            text: segment.text,
            start,
            end,
            wordIndex: index
          });
          return `<span class="sentence-token sentence-token--word" data-word-index="${index}" data-char-start="${start}" data-char-end="${end}">${escaped}</span>`;
        })
        .join('');

      return {
        html,
        wordCount: wordIndex,
        segments,
        wordRanges
      };
    }

    findWordIndexAtCharIndex(wordRanges, charIndex) {
      if (!Array.isArray(wordRanges) || typeof charIndex !== 'number' || Number.isNaN(charIndex)) {
        return -1;
      }

      const match = wordRanges.find((range) => charIndex >= range.start && charIndex < range.end);
      return match ? match.wordIndex : -1;
    }
  }

  return { TTSWordHighlighter };
});
