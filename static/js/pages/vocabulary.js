/**
 * 生词复习面板 - Alpine.js 版本
 *
 * 状态机集中在 Alpine x-data 工厂 vocabReview()：
 * - cards: 当前筛选结果对应的生词列表（从 #vocab-rows-data 注入）
 * - index / flipped / isOpen: 翻牌/分页状态
 * - 派生 frontText / backHtml / progressText / stateText / toggleLabel 走 x-text/x-html
 *
 * 与 htmx 互通：
 * - 服务端 vocab-toggled 事件 → Alpine 同步卡片 mastered 状态 + 列表项 .is-mastered
 * - 仍保留 window.openVocabReview() 兼容入口
 */

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

  function formatTime(value) {
    if (!window.Utils || typeof window.Utils.formatDateTime !== 'function') {
      return '';
    }
    return window.Utils.formatDateTime(value);
  }

  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === 'function') {
      return window.CSS.escape(value);
    }
    return String(value).replace(/["\\]/g, '\\$&');
  }

  function loadCardsFromDom() {
    const rowsDataEl = document.getElementById('vocab-rows-data');
    if (!rowsDataEl) {
      return [];
    }
    return parseRows(rowsDataEl.textContent)
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
  }

  // Alpine 工厂
  window.vocabReview = function vocabReview() {
    return {
      isOpen: false,
      index: 0,
      flipped: false,
      cards: [],
      lastFocusedElement: null,
      _submitting: false,

      init() {
        this.cards = loadCardsFromDom();
        // 初始化展示：让 .vocab-review-panel 的 d-none 一直存在直到 isOpen = true
        // 这里不主动 toggle className，由 x-bind:class 接管
        this._bindTriggers();
        this._bindHtmxVocabEvents();
        this._formatTimeSpans();
      },

      _bindTriggers() {
        const entryBtn = document.getElementById('vocab-review-entry');
        if (entryBtn) {
          entryBtn.addEventListener('click', () => this.open());
        }
      },

      _formatTimeSpans() {
        document.querySelectorAll('[data-vocab-mastered-at]').forEach((element) => {
          const masteredAt = element.getAttribute('data-vocab-mastered-at');
          const masteredText = formatTime(masteredAt);
          if (masteredText) {
            element.textContent = '掌握时间：' + masteredText;
          }
        });
      },

      _bindHtmxVocabEvents() {
        document.addEventListener('vocab-toggled', (event) => {
          const detail = (event && event.detail) || {};
          const word = detail.word;
          if (!word) {
            return;
          }
          const mastered = !!detail.mastered;
          // 同步 Alpine 内卡片
          this.cards.forEach((card) => {
            if (card.word === word) {
              card.mastered = mastered;
            }
          });
          // 同步页面内 .vocab-item
          const selector = `.vocab-item[data-vocab-word="${cssEscape(word)}"]`;
          document.querySelectorAll(selector).forEach((item) => {
            item.dataset.vocabMastered = mastered ? '1' : '0';
            item.classList.toggle('is-mastered', mastered);
            // htmx 已经把正确的按钮 outerHTML 换回来了, 这里只需要同步
            // 父容器的 class / data-attr, 不再去覆写按钮 textContent
            // (避免把模板里的 "已掌握 / 标记掌握" 改回旧的 "已掌握 / 取消掌握")。
          });
        });
      },

      get totalCards() {
        return this.cards.length;
      },

      get currentCard() {
        return this.cards[this.index] || null;
      },

      get progressText() {
        const total = this.totalCards;
        const current = total > 0 ? this.index + 1 : 0;
        return total > 0 ? current + ' / ' + total : '0 / 0';
      },

      get stateText() {
        const card = this.currentCard;
        if (!card) {
          return this.isOpen ? '暂无可复习内容' : '未开始';
        }
        return card.mastered ? '已掌握' : '学习中';
      },

      get toggleLabel() {
        const card = this.currentCard;
        if (!card) {
          return '标记已掌握';
        }
        return card.mastered ? '取消掌握' : '标记已掌握';
      },

      get frontText() {
        const card = this.currentCard;
        if (!card) {
          return '当前没有可复习词条';
        }
        if (this.flipped) {
          return card.pronunciation || card.word;
        }
        return card.word;
      },

      get backHtml() {
        const card = this.currentCard;
        if (!card) {
          return '<div class="vocab-review-card__hint">请先切换到有词条的筛选结果。</div>';
        }
        if (!this.flipped) {
          return '<div class="vocab-review-card__hint">点击“翻牌”查看释义</div>';
        }
        const meaning = '<div>' + escapeText(card.meaning) + '</div>';
        const hint = card.articleTitle
          ? '<div class="vocab-review-card__hint">来源：' + escapeText(card.articleTitle) + '</div>'
          : '';
        return meaning + hint;
      },

      // 让 d-none 与 isOpen 联动：使用 $watch 风格无法直接在 template 里绑 className 表达式
      // 这里用一个派生属性返回 class 字符串
      get panelClass() {
        return this.isOpen ? 'vocab-review-panel' : 'vocab-review-panel d-none';
      },

      open() {
        if (this.totalCards === 0) {
          alert('当前筛选结果没有可复习的生词');
          return;
        }
        const active = document.activeElement;
        this.lastFocusedElement = active instanceof HTMLElement ? active : null;
        this.isOpen = true;
        this.index = Math.min(this.index, this.totalCards - 1);
        this.flipped = false;
        const closeBtn = document.getElementById('vocab-review-close');
        if (closeBtn && typeof closeBtn.focus === 'function') {
          closeBtn.focus();
        }
      },

      close() {
        if (!this.isOpen) {
          return;
        }
        this.isOpen = false;
        this.flipped = false;
        if (this.lastFocusedElement && typeof this.lastFocusedElement.focus === 'function') {
          this.lastFocusedElement.focus();
        }
      },

      flip() {
        if (!this.isOpen || this.totalCards === 0) {
          return;
        }
        this.flipped = !this.flipped;
      },

      move(step) {
        if (!this.isOpen || this.totalCards === 0) {
          return;
        }
        const nextIndex = this.index + step;
        if (nextIndex < 0 || nextIndex >= this.totalCards) {
          return;
        }
        this.index = nextIndex;
        this.flipped = false;
      },

      shuffle() {
        for (let i = this.cards.length - 1; i > 0; i -= 1) {
          const j = Math.floor(Math.random() * (i + 1));
          const a = this.cards[i];
          const b = this.cards[j];
          this.cards[i] = b;
          this.cards[j] = a;
        }
        this.index = 0;
        this.flipped = false;
      },

      _persistStatus(card, mastered, button) {
        if (button) {
          button.disabled = true;
        }
        this._submitting = true;
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
          .finally(() => {
            this._submitting = false;
            if (button) {
              button.disabled = false;
            }
          });
      },

      toggleMastered(button) {
        const card = this.currentCard;
        if (!card) {
          return;
        }
        this._persistStatus(card, !card.mastered, button)
          .then((data) => {
            card.mastered = Boolean(data.mastered);
            // 列表项同步 (只同步 class / data, 不要去覆写按钮 textContent,
            // htmx swap 已经把正确的 outerHTML 换回来了)。
            const selector = `.vocab-item[data-vocab-word="${cssEscape(card.word)}"]`;
            document.querySelectorAll(selector).forEach((item) => {
              item.dataset.vocabMastered = card.mastered ? '1' : '0';
              item.classList.toggle('is-mastered', card.mastered);
            });
          })
          .catch((error) => {
            console.error('保存生词状态失败', error);
            alert(error.message);
          });
      },

      speakVocabWord(button) {
        const item = button.closest('.vocab-item');
        if (!item || !('speechSynthesis' in window)) {
          return;
        }
        const text = item.dataset.vocabWord || '';
        if (!text.trim()) {
          return;
        }
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'ja-JP';
        window.speechSynthesis.speak(utterance);
      },

      // 处理 tab 键焦点循环
      trapFocus(event) {
        const panel = event.currentTarget;
        if (!panel) {
          return;
        }
        const focusable = Array.from(
          panel.querySelectorAll('button:not(:disabled), [href], [tabindex]:not([tabindex="-1"])')
        ).filter((element) => element instanceof HTMLElement && !element.hasAttribute('disabled'));
        if (focusable.length === 0) {
          event.preventDefault();
          return;
        }
        const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        const firstEl = focusable[0];
        const lastEl = focusable[focusable.length - 1];
        const idx = focusable.indexOf(active);
        if (event.shiftKey) {
          if (active === firstEl || idx <= 0) {
            event.preventDefault();
            lastEl.focus();
          }
          return;
        }
        if (active === lastEl || idx === focusable.length - 1) {
          event.preventDefault();
          firstEl.focus();
        }
      },
    };
  };

  // 老的 window.openVocabReview() 入口
  function findAlpineInstance() {
    const panelEl = document.getElementById('vocab-review-panel');
    if (panelEl && panelEl._x_dataStack && panelEl._x_dataStack[0]) {
      return panelEl._x_dataStack[0];
    }
    return null;
  }

  function openVocabReview() {
    const instance = findAlpineInstance();
    if (instance) {
      instance.open();
    }
  }

  function closeVocabReview() {
    const instance = findAlpineInstance();
    if (instance) {
      instance.close();
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    window.openVocabReview = openVocabReview;
    window.closeVocabReview = closeVocabReview;
  });
})();
