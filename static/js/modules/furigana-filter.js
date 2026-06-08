(function () {
  'use strict';

  function parseRubyHtml(rubyHtml) {
    const container = document.createElement('div');
    container.innerHTML = rubyHtml || '';
    return container;
  }

  function shouldKeepRuby(baseText, level) {
    const normalizedLevel = [1, 2, 3, 4, 5].includes(Number(level)) ? Number(level) : 1;
    if (normalizedLevel >= 4) {
      return true;
    }

    const text = (baseText || '').trim();
    if (!text) {
      return false;
    }

    const hasKanji = /[\u4e00-\u9fff]/.test(text);
    if (!hasKanji) {
      return false;
    }

    const commonKanji = {
      1: new Set('日一国人年大十二本中長出三時行見月分後前生五間上東四今金九入学高円子外八六下気小七山話女北午百書先名川千水半男西電校語土木聞食車何南万白天母火右読友左休父雨'),
      2: new Set('気安会強同最勉私族店場体飲物使作町週新曜歩買歌鉄魚海図音園赤青黒茶黄早明暗正直計終開閉売考期記通試働住待取知答楽病院医薬昼夜春夏秋冬'),
      3: new Set('感想対別答義題続進復変敗夢術証都県度産約初習究解現規調情便理案伝界切短勢順質納察細資協済観能訪移減適配準導留'),
    };

    const allowed = new Set();
    [1, 2, 3].filter((n) => n <= normalizedLevel).forEach((n) => {
      commonKanji[n].forEach((char) => allowed.add(char));
    });

    return Array.from(text).some((char) => /[\u4e00-\u9fff]/.test(char) && !allowed.has(char));
  }

  function apply(rubyHtml, level) {
    if (!rubyHtml) {
      return '';
    }

    const container = parseRubyHtml(rubyHtml);
    const rubies = Array.from(container.querySelectorAll('ruby'));
    rubies.forEach((ruby) => {
      const base = Array.from(ruby.childNodes)
        .filter((node) => node.nodeName !== 'RT')
        .map((node) => node.textContent || '')
        .join('');
      if (!shouldKeepRuby(base, level)) {
        ruby.replaceWith(document.createTextNode(base));
      }
    });
    return container.innerHTML;
  }

  window.FuriganaFilter = {
    apply,
    shouldKeepRuby,
  };
})();
