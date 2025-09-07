/**
 * Text Highlighting Module
 * 文本高亮模块
 */

class TextHighlighter {
  constructor() {
    this.originalText = '';
    this.rubyText = '';
  }

  setContent(originalText, rubyText) {
    this.originalText = originalText || '';
    this.rubyText = rubyText || '';
  }

  highlightText(recognizedText) {
    const highlightElement = document.getElementById('highlight-text');
    if (!highlightElement) return;

    // If no recognized text, show original ruby text
    if (!recognizedText || recognizedText.trim() === '') {
      highlightElement.innerHTML = this.rubyText;
      return;
    }

    // Karaoke-style highlighting: gradually light up text based on recognition progress
    const recognizedWords = recognizedText.trim().split(/\s+/);
    const originalWords = this.originalText.split(/\s+/);

    let highlightedHTML = '';
    let recognizedIndex = 0;
    let originalIndex = 0;

    // Parse ruby text to extract plain text words
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = this.rubyText;
    const textContent = tempDiv.textContent || tempDiv.innerText || '';

    // Rebuild HTML with highlighting
    let rubyHTML = this.rubyText;
    let currentPos = 0;

    while (originalIndex < originalWords.length && recognizedIndex < recognizedWords.length) {
      const originalWord = originalWords[originalIndex];
      const recognizedWord = recognizedWords[recognizedIndex];

      // Check if words match
      if (this.checkWordMatch(originalWord, recognizedWord)) {
        // Find and highlight the matching word in rubyHTML
        const wordIndex = rubyHTML.indexOf(originalWord, currentPos);
        if (wordIndex !== -1) {
          const beforeWord = rubyHTML.substring(0, wordIndex);
          const afterWord = rubyHTML.substring(wordIndex + originalWord.length);
          rubyHTML = beforeWord + `<span class="karaoke-highlight">${originalWord}</span>` + afterWord;
          currentPos = wordIndex + originalWord.length + `<span class="karaoke-highlight">${originalWord}</span>`.length;
        }

        recognizedIndex++;
      } else {
        // Try to find match further ahead
        let found = false;
        for (let i = 0; i < 3 && originalIndex + i < originalWords.length; i++) {
          if (this.checkWordMatch(originalWords[originalIndex + i], recognizedWord)) {
            // Mark skipped words as pending
            for (let j = 0; j < i; j++) {
              const skipWord = originalWords[originalIndex + j];
              const skipIndex = rubyHTML.indexOf(skipWord, currentPos);
              if (skipIndex !== -1) {
                const beforeSkip = rubyHTML.substring(0, skipIndex);
                const afterSkip = rubyHTML.substring(skipIndex + skipWord.length);
                rubyHTML = beforeSkip + `<span class="karaoke-pending">${skipWord}</span>` + afterSkip;
              }
            }

            // Highlight matching word
            const matchWord = originalWords[originalIndex + i];
            const matchIndex = rubyHTML.indexOf(matchWord, currentPos);
            if (matchIndex !== -1) {
              const beforeMatch = rubyHTML.substring(0, matchIndex);
              const afterMatch = rubyHTML.substring(matchIndex + matchWord.length);
              rubyHTML = beforeMatch + `<span class="karaoke-highlight">${matchWord}</span>` + afterMatch;
              currentPos = matchIndex + matchWord.length + `<span class="karaoke-highlight">${matchWord}</span>`.length;
            }

            originalIndex += i;
            recognizedIndex++;
            found = true;
            break;
          }
        }

        if (!found) {
          // Mark as pending if no match found
          const pendingWord = originalWord;
          const pendingIndex = rubyHTML.indexOf(pendingWord, currentPos);
          if (pendingIndex !== -1) {
            const beforePending = rubyHTML.substring(0, pendingIndex);
            const afterPending = rubyHTML.substring(pendingIndex + pendingWord.length);
            rubyHTML = beforePending + `<span class="karaoke-pending">${pendingWord}</span>` + afterPending;
          }
        }
      }

      originalIndex++;
    }

    // Handle remaining words
    while (originalIndex < originalWords.length) {
      const remainingWord = originalWords[originalIndex];
      const remainingIndex = rubyHTML.indexOf(remainingWord, currentPos);
      if (remainingIndex !== -1) {
        const beforeRemaining = rubyHTML.substring(0, remainingIndex);
        const afterRemaining = rubyHTML.substring(remainingIndex + remainingWord.length);
        rubyHTML = beforeRemaining + `<span class="karaoke-pending">${remainingWord}</span>` + afterRemaining;
      }
      originalIndex++;
    }

    highlightElement.innerHTML = rubyHTML;
  }

  checkWordMatch(originalWord, recognizedWord) {
    // Remove punctuation for comparison
    const cleanOriginal = originalWord.replace(/[。、，！？「」『』()（）【】《》〈〉]/g, '');
    const cleanRecognized = recognizedWord.replace(/[。、，！？「」『』()（）【】《》〈〉]/g, '');

    // Exact match
    if (cleanOriginal === cleanRecognized) {
      return true;
    }

    // Similar length and contains same characters
    if (Math.abs(cleanOriginal.length - cleanRecognized.length) <= 1) {
      const similarity = this.calculateSimilarity(cleanOriginal, cleanRecognized);
      return similarity > 0.8;
    }

    return false;
  }

  calculateSimilarity(str1, str2) {
    const longer = str1.length > str2.length ? str1 : str2;
    const shorter = str1.length > str2.length ? str2 : str1;

    if (longer.length === 0) return 1.0;

    const distance = this.levenshteinDistance(longer, shorter);
    return (longer.length - distance) / longer.length;
  }

  levenshteinDistance(str1, str2) {
    const matrix = [];

    for (let i = 0; i <= str2.length; i++) {
      matrix[i] = [i];
    }

    for (let j = 0; j <= str1.length; j++) {
      matrix[0][j] = j;
    }

    for (let i = 1; i <= str2.length; i++) {
      for (let j = 1; j <= str1.length; j++) {
        if (str2.charAt(i - 1) === str1.charAt(j - 1)) {
          matrix[i][j] = matrix[i - 1][j - 1];
        } else {
          matrix[i][j] = Math.min(
            matrix[i - 1][j - 1] + 1,
            matrix[i][j - 1] + 1,
            matrix[i - 1][j] + 1
          );
        }
      }
    }

    return matrix[str2.length][str1.length];
  }
}

// Export for global use
window.TextHighlighter = TextHighlighter;
