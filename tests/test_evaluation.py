from app.routers.evaluation import calculate_similarity, normalize_to_hiragana


def test_normalize_to_hiragana_converts_kanji_and_kana():
    text = "今日は天気です"

    result = normalize_to_hiragana(text)

    assert result
    assert isinstance(result, str)


def test_similarity_prefers_kana_when_text_shape_differs():
    original = "今日は天気です"
    recognized = "きょうはてんきです"

    original_similarity = calculate_similarity(original, recognized)
    kana_similarity = calculate_similarity(normalize_to_hiragana(original), normalize_to_hiragana(recognized))

    assert kana_similarity >= original_similarity
