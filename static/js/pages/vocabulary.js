(function () {
  'use strict';

  function parseRows(raw) {
    if (!raw) {
      return [];
    }

    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (error) {
      console.error('解析生词数据失败', error);
      return [];
    }
  }

  function escapeText(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function getMeaningText(item) {
    const meaningNodes = item.querySelectorAll('.vocab-meaning');
    const firstMeaning = meaningNodes[0];
    if (!firstMeaning) {
      return '';
    }

    return firstMeaning.textContent.replace(/^释义：/, '').trim();
  }

  document.addEventListener('DOMContentLoaded', function () {
    const reviewEntryBtn = document.getElementById('vocab-review-entry');
    const reviewPanel = document.getElementById('vocab-review-panel');
    const reviewCloseBtn = document.getElementById('vocab-review-close');
    const reviewCard = document.querySelector('[data-review-card]');
    const reviewCardInner = reviewCard ? reviewCard.querySelector('.vocab-review-card__inner') : null;
    const reviewWordEl = document.querySelector('.vocab-review-card__word');
    const reviewMeaningEl = document.querySelector('.vocab-review-card__meaning');
    const reviewProgressEl = document.querySelector('[data-review-progress]');
    const reviewStateEl = document.querySelector('[data-review-state]');
    const reviewPrevBtn = document.getElementById('vocab-review-prev');
    const reviewNextBtn = document.getElementById('vocab-review-next');
    const reviewFlipBtn = document.getElementById('vocab-review-flip');
    const reviewToggleMasteredBtn = document.getElementById('vocab-review-toggle-mastered');
    const rowsDataEl = document.getElementById('vocab-rows-data');
    const vocabItems = Array.from(document.querySelectorAll('.vocab-item'));

    if (!reviewEntryBtn || !reviewPanel || !reviewCloseBtn || !reviewCard || !reviewCardInner || !reviewWordEl || !reviewMeaningEl || !reviewProgressEl || !reviewStateEl || !reviewPrevBtn || !reviewNextBtn || !reviewFlipBtn || !reviewToggleMasteredBtn || !rowsDataEl) {
      return;
    }

    const cards = parseRows(rowsDataEl.textContent)
      .map(function (row) {
        return {
          word: typeof row.word === 'string' ? row.word : '',
          pronunciation: typeof row.pronunciation === 'string' ? row.pronunciation : '',
          meaning: typeof row.meaning === 'string' ? row.meaning : '',
          mastered: row.status === 'mastered' || row.mastered === true,
          articleTitle: typeof row.article_title === 'string' ? row.article_title : ''
        };
      })
      .filter(function (row) {
        return row.word.trim().length > 0;
      });

    const state = {
      active: false,
      index: 0,
      flipped: false,
      cards: cards
    };
    let lastFocusedElement = null;

    function getCurrentCard() {
      return state.cards[state.index] || null;
    }

    function focusReviewCard() {
      if (reviewCloseBtn && typeof reviewCloseBtn.focus === 'function') {
        reviewCloseBtn.focus();
      }
    }

    function getReviewFocusableElements() {
      return Array.from(
        reviewPanel.querySelectorAll('button:not(:disabled), [href], [tabindex]:not([tabindex="-1"])')
      ).filter(function (element) {
        return element instanceof HTMLElement && !element.hasAttribute('disabled');
      });
    }

    function setReviewText(card) {
      if (!card) {
        reviewWordEl.textContent = '当前没有可复习词条';
        reviewMeaningEl.innerHTML = '<div class="vocab-review-card__hint">请先切换到有词条的筛选结果。</div>';
        reviewStateEl.textContent = state.active ? '暂无可复习内容' : '未开始';
        reviewToggleMasteredBtn.textContent = '标记已掌握';
        return;
      }

      if (state.flipped) {
        reviewWordEl.textContent = card.pronunciation || card.word;
        reviewMeaningEl.innerHTML = '<div>' + escapeText(card.meaning) + '</div>' + (card.articleTitle ? '<div class="vocab-review-card__hint">来源：' + escapeText(card.articleTitle) + '</div>' : '');
      } else {
        reviewWordEl.textContent = card.word;
        reviewMeaningEl.innerHTML = '<div class="vocab-review-card__hint">点击“翻牌”查看释义</div>';
      }

      reviewStateEl.textContent = card.mastered ? '已掌握' : '学习中';
      reviewToggleMasteredBtn.textContent = card.mastered ? '取消掌握' : '标记已掌握';
    }

    function syncReviewUI() {
      const card = getCurrentCard();
      const total = state.cards.length;
      const current = total > 0 ? state.index + 1 : 0;

      reviewCard.dataset.flipped = state.flipped ? '1' : '0';
      reviewCardInner.style.transform = state.flipped ? 'rotateY(180deg)' : 'rotateY(0deg)';
      reviewProgressEl.textContent = total > 0 ? current + ' / ' + total : '0 / 0';
      reviewPrevBtn.disabled = !state.active || state.index <= 0;
      reviewNextBtn.disabled = !state.active || state.index >= total - 1;
      reviewFlipBtn.disabled = !state.active || total === 0;
      reviewToggleMasteredBtn.disabled = !state.active || !card;
      setReviewText(card);
    }

    function findListItem(card) {
      return vocabItems.find(function (item) {
        return item.dataset.vocabWord === card.word && item.dataset.vocabPronunciation === card.pronunciation;
      }) || null;
    }

    function syncListItem(card) {
      const item = findListItem(card);
      if (!item) {
        return;
      }

      const toggleButton = item.querySelector('[data-vocab-action="toggle-mastered"]');
      item.dataset.vocabMastered = card.mastered ? '1' : '0';
      item.classList.toggle('is-mastered', card.mastered);
      if (toggleButton) {
        toggleButton.textContent = card.mastered ? '取消掌握' : '已掌握';
      }
    }

    function persistStatus(card, mastered, button) {
      if (button) {
        button.disabled = true;
      }

      return fetch('/vocabulary/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          word: card.word,
          pronunciation: card.pronunciation,
          meaning: card.meaning,
          mastered: mastered
        })
      })
        .then(function (response) {
          return response.json().then(function (data) {
            if (!response.ok || !data.success) {
              throw new Error(data.error || '保存失败');
            }

            return data;
          });
        })
        .finally(function () {
          if (button) {
            button.disabled = false;
          }
        });
    }

    function updateCurrentCardMastered(mastered, button) {
      const card = getCurrentCard();
      if (!card) {
        return;
      }

      persistStatus(card, mastered, button)
        .then(function (data) {
          card.mastered = Boolean(data.mastered);
          syncListItem(card);
          syncReviewUI();
        })
        .catch(function (error) {
          console.error('保存生词状态失败', error);
          alert(error.message);
        });
    }

    function toggleCurrentCardMastered(button) {
      const card = getCurrentCard();
      if (!card) {
        return;
      }

      updateCurrentCardMastered(!card.mastered, button);
    }

    function openReview() {
      if (state.cards.length === 0) {
        alert('当前筛选结果没有可复习的生词');
        return;
      }

      lastFocusedElement = document.activeElement instanceof HTMLElement ? document.activeElement : reviewEntryBtn;
      state.active = true;
      state.index = Math.min(state.index, state.cards.length - 1);
      state.flipped = false;
      reviewPanel.classList.remove('d-none');
      reviewPanel.setAttribute('aria-hidden', 'false');
      reviewEntryBtn.setAttribute('aria-expanded', 'true');
      syncReviewUI();
      focusReviewCard();
    }

    function closeReview() {
      state.active = false;
      state.flipped = false;
      reviewPanel.classList.add('d-none');
      reviewPanel.setAttribute('aria-hidden', 'true');
      reviewEntryBtn.setAttribute('aria-expanded', 'false');
      syncReviewUI();
      if (lastFocusedElement && typeof lastFocusedElement.focus === 'function') {
        lastFocusedElement.focus();
      } else {
        reviewEntryBtn.focus();
      }
    }

    function flipCurrentCard() {
      if (!state.active || state.cards.length === 0) {
        return;
      }

      state.flipped = !state.flipped;
      syncReviewUI();
    }

    function moveCurrentCard(step) {
      if (!state.active || state.cards.length === 0) {
        return;
      }

      const nextIndex = state.index + step;
      if (nextIndex < 0 || nextIndex >= state.cards.length) {
        return;
      }

      state.index = nextIndex;
      state.flipped = false;
      syncReviewUI();
    }

    function speakVocabWord(button) {
      const item = button.closest('.vocab-item');
      if (!item || !('speechSynthesis' in window)) {
        return;
      }

      const text = item.dataset.vocabPronunciation || item.dataset.vocabWord || '';
      if (!text.trim()) {
        return;
      }

      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = 'ja-JP';
      window.speechSynthesis.speak(utterance);
    }

    function toggleListMastered(button) {
      const item = button.closest('.vocab-item');
      if (!item) {
        return;
      }

      const card = state.cards.find(function (entry) {
        return entry.word === (item.dataset.vocabWord || '') && entry.pronunciation === (item.dataset.vocabPronunciation || '');
      });

      if (!card) {
        return;
      }

      const meaning = getMeaningText(item) || card.meaning;
      const nextMastered = item.dataset.vocabMastered !== '1';

      persistStatus({
        word: card.word,
        pronunciation: card.pronunciation,
        meaning: meaning
      }, nextMastered, button)
        .then(function (data) {
          card.mastered = Boolean(data.mastered);
          syncListItem(card);
          syncReviewUI();
        })
        .catch(function (error) {
          console.error('保存生词状态失败', error);
          alert(error.message);
        });
    }

    reviewEntryBtn.addEventListener('click', openReview);
    reviewCloseBtn.addEventListener('click', closeReview);
    reviewFlipBtn.addEventListener('click', flipCurrentCard);
    reviewPrevBtn.addEventListener('click', function () {
      moveCurrentCard(-1);
    });
    reviewNextBtn.addEventListener('click', function () {
      moveCurrentCard(1);
    });
    reviewToggleMasteredBtn.addEventListener('click', function () {
      const card = getCurrentCard();
      if (!card) {
        return;
      }

      updateCurrentCardMastered(!card.mastered, reviewToggleMasteredBtn);
    });

    reviewPanel.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeReview();
        return;
      }

      if (event.key !== 'Tab') {
        return;
      }

      const focusableElements = getReviewFocusableElements();
      if (focusableElements.length === 0) {
        event.preventDefault();
        return;
      }

      const currentIndex = focusableElements.indexOf(document.activeElement instanceof HTMLElement ? document.activeElement : null);
      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];

      if (event.shiftKey) {
        if (document.activeElement === firstElement || currentIndex <= 0) {
          event.preventDefault();
          lastElement.focus();
        }
        return;
      }

      if (document.activeElement === lastElement || currentIndex === focusableElements.length - 1) {
        event.preventDefault();
        firstElement.focus();
      }
    });

    document.addEventListener('click', function (event) {
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
        speakVocabWord(button);
        return;
      }

      if (action === 'toggle-mastered') {
        toggleListMastered(button);
      }
    });

    syncReviewUI();
  });
})();
