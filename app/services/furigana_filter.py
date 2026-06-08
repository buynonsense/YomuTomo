from __future__ import annotations

import re
from functools import lru_cache
from html import escape as html_escape
from html.parser import HTMLParser

_COMMON_KANJI_BY_LEVEL = {
    1: set("日一国人年大十二本中長出三時行見月分後前生五間上東四今金九入学高円子外八六下来気小七山話女北午百書先名川千水半男西電校語土木聞食車何南万白天母火右読友左休父雨"),
    2: set("気安会強同最勉私族店場体飲物使作町週新曜歩買歌鉄魚海図音園赤青黒茶黄明直計終開閉売考期記通試働住待取知答楽病院医薬昼夜春夏秋冬"),
    3: set("感想対別答義題続進復変敗夢術証都県度産約初習究解現規調情便理案伝界切短勢順質納察細資協済観能訪移減適配準導留"),
}


def _normalize_level(level: int | str | None) -> int:
    try:
        return max(1, min(5, int(level or 1)))
    except Exception:
        return 1


@lru_cache(maxsize=1)
def _common_kanji_sets() -> dict[int, set[str]]:
    # N5/N4/N3 的默认滤镜，尽量保守。后续可替换为更完整的常用汉字表。
    return {level: set(chars) for level, chars in _COMMON_KANJI_BY_LEVEL.items()}


def should_show_furigana(token: str, level: int | str | None = None) -> bool:
    """按难度决定是否显示假名。"""
    text = token or ""
    if not text.strip():
        return False

    normalized_level = _normalize_level(level)
    if normalized_level >= 4:
        return True

    if not re.search(r"[\u4e00-\u9fff]", text):
        return False

    allowed_kanji = set()
    for current_level in range(1, normalized_level + 1):
        allowed_kanji.update(_common_kanji_sets().get(current_level, set()))

    kanji_chars = re.findall(r"[\u4e00-\u9fff]", text)
    if not kanji_chars:
        return False

    # 只要包含一个不在允许集里的汉字，就保留假名。
    return any(char not in allowed_kanji for char in kanji_chars)


class _FuriganaFilterParser(HTMLParser):
    def __init__(self, level: int | str | None):
        super().__init__(convert_charrefs=False)
        self.level = _normalize_level(level)
        self.parts: list[str] = []
        self._ruby_buffer: list[str] = []
        self._ruby_original_parts: list[str] = []
        self._in_ruby = False
        self._in_rt = False
        self._ruby_base_buffer: list[str] = []

    def _serialize_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        attrs_str = "".join(
            f' {name}="{html_escape(value or "", quote=True)}"' for name, value in attrs
        )
        return f"<{tag}{attrs_str}>"

    def handle_starttag(self, tag, attrs):
        if tag == "ruby":
            self._in_ruby = True
            self._ruby_buffer = []
            self._ruby_base_buffer = []
            self._ruby_original_parts = [self._serialize_starttag(tag, attrs)]
            return
        if self._in_ruby:
            self._ruby_original_parts.append(self._serialize_starttag(tag, attrs))
            if tag == "rt":
                self._in_rt = True
            return

        self.parts.append(self._serialize_starttag(tag, attrs))

    def handle_endtag(self, tag):
        if tag == "ruby" and self._in_ruby:
            base = "".join(self._ruby_base_buffer).strip()
            self._ruby_original_parts.append(f"</{tag}>")
            ruby_html = "".join(self._ruby_original_parts)
            if should_show_furigana(base, self.level):
                self.parts.append(ruby_html)
            else:
                self.parts.append(base)
            self._in_ruby = False
            self._in_rt = False
            self._ruby_buffer = []
            self._ruby_original_parts = []
            self._ruby_base_buffer = []
            return

        if self._in_ruby and tag == "rt":
            self._ruby_original_parts.append(f"</{tag}>")
            self._in_rt = False
            return

        if self._in_ruby:
            self._ruby_original_parts.append(f"</{tag}>")
            return

        if not self._in_ruby:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if self._in_ruby:
            self._ruby_buffer.append(data)
            self._ruby_original_parts.append(data)
            if not self._in_rt:
                self._ruby_base_buffer.append(data)
        else:
            self.parts.append(data)

    def handle_entityref(self, name):
        value = f"&{name};"
        if self._in_ruby:
            self._ruby_buffer.append(value)
            self._ruby_original_parts.append(value)
            if not self._in_rt:
                self._ruby_base_buffer.append(value)
        else:
            self.parts.append(value)

    def handle_charref(self, name):
        value = f"&#{name};"
        if self._in_ruby:
            self._ruby_buffer.append(value)
            self._ruby_original_parts.append(value)
            if not self._in_rt:
                self._ruby_base_buffer.append(value)
        else:
            self.parts.append(value)

    def get_html(self) -> str:
        return "".join(self.parts)


def apply_furigana_filter(ruby_html: str, level: int | str | None = None) -> str:
    """基于难度过滤 ruby 标签。"""
    if not ruby_html:
        return ""

    normalized_level = _normalize_level(level)
    if normalized_level >= 4:
        return ruby_html

    parser = _FuriganaFilterParser(normalized_level)
    parser.feed(ruby_html)
    parser.close()
    return parser.get_html()
