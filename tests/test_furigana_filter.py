from app.services.furigana_filter import apply_furigana_filter, should_show_furigana


def test_should_show_furigana_hides_common_kanji_for_low_levels():
    assert should_show_furigana("日本語", 1) is False
    assert should_show_furigana("感想", 1) is True
    assert should_show_furigana("感想", 3) is False


def test_apply_furigana_filter_keeps_common_and_removes_advanced_ruby():
    ruby_html = "<p><ruby>日本<rt>にほん</rt></ruby>と<ruby>感想<rt>かんそう</rt></ruby></p>"

    level_one = apply_furigana_filter(ruby_html, 1)
    level_four = apply_furigana_filter(ruby_html, 4)

    assert "<rt>にほん</rt>" not in level_one
    assert "<rt>かんそう</rt>" in level_one
    assert "<rt>にほん</rt>" in level_four
    assert "<rt>かんそう</rt>" in level_four
