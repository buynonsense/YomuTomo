import difflib
import re
from html import escape

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse
import pykakasi

router = APIRouter(prefix="", tags=["评测"])

kks = pykakasi.kakasi()


def normalize_to_hiragana(text: str) -> str:
    """将文本尽量转换为纯平假名，便于更客观地比较发音相似度。"""
    if not text:
        return ""

    converted = []
    for item in kks.convert(text):
        hira = item.get("hira", "")
        if hira:
            converted.append(hira)
        else:
            converted.append(item.get("orig", ""))
    return "".join(converted)


def _collapse_for_compare(text: str) -> str:
    """去掉空白与常见标点，让评分更关注实际发音。"""
    if not text:
      return ""

    cleaned = re.sub(r"[\s\u3000]+", "", text)
    cleaned = re.sub(r"[、。！？?!.,，；;：:「」『』（）()【】\[\]{}〈〉《》·・…-]", "", cleaned)
    return cleaned


def _tokenize_for_diff(text: str) -> list[dict]:
    tokens: list[dict] = []
    source = text or ""
    if not source:
        return tokens

    try:
        converted = kks.convert(source)
    except Exception:
        converted = [{"orig": source, "hira": source}]

    for item in converted:
        orig = item.get("orig", "")
        hira = item.get("hira", "") or orig
        display = orig or hira
        if not display:
            continue
        tokens.append(
            {
                "display": display,
                "normalized": _collapse_for_compare(hira or orig),
            }
        )

    if not tokens and source:
        tokens.append({"display": source, "normalized": _collapse_for_compare(source)})

    return tokens


def _token_class(status: str) -> str:
    base = "evaluation-token"
    if status == "match":
        return f"{base} evaluation-token--match"
    if status == "miss":
        return f"{base} evaluation-token--miss"
    if status == "extra":
        return f"{base} evaluation-token--extra"
    return base


def _build_diff_html(original_text: str, recognized_text: str) -> dict:
    original_tokens = _tokenize_for_diff(original_text)
    recognized_tokens = _tokenize_for_diff(recognized_text)

    matcher = difflib.SequenceMatcher(
        None,
        [token["normalized"] for token in original_tokens],
        [token["normalized"] for token in recognized_tokens],
    )

    original_status = ["neutral"] * len(original_tokens)
    recognized_status = ["neutral"] * len(recognized_tokens)
    matched_tokens = 0
    miss_tokens = 0
    extra_tokens = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for index in range(i1, i2):
                original_status[index] = "match"
                matched_tokens += 1
            for index in range(j1, j2):
                recognized_status[index] = "match"
        elif tag == "replace":
            for index in range(i1, i2):
                original_status[index] = "miss"
                miss_tokens += 1
            for index in range(j1, j2):
                recognized_status[index] = "extra"
                extra_tokens += 1
        elif tag == "delete":
            for index in range(i1, i2):
                original_status[index] = "miss"
                miss_tokens += 1
        elif tag == "insert":
            for index in range(j1, j2):
                recognized_status[index] = "extra"
                extra_tokens += 1

    original_html = "".join(
        f'<span class="{_token_class(original_status[index])}">{escape(token["display"])}</span>'
        for index, token in enumerate(original_tokens)
    )
    recognized_html = "".join(
        f'<span class="{_token_class(recognized_status[index])}">{escape(token["display"])}</span>'
        for index, token in enumerate(recognized_tokens)
    )

    return {
        "original_html": original_html,
        "recognized_html": recognized_html,
        "matched_tokens": matched_tokens,
        "miss_tokens": miss_tokens,
        "extra_tokens": extra_tokens,
        "original_tokens": len(original_tokens),
        "recognized_tokens": len(recognized_tokens),
    }


def calculate_similarity(left: str, right: str) -> float:
    return difflib.SequenceMatcher(None, left, right).ratio()


@router.post("/evaluate", summary="朗读评测")
async def evaluate(original: str = Form(..., description="原始日语文本"), recognized: str = Form(..., description="语音识别得到的文本")):
    original_clean = _collapse_for_compare(original)
    recognized_clean = _collapse_for_compare(recognized)
    original_similarity = calculate_similarity(original_clean, recognized_clean)
    kana_similarity = calculate_similarity(normalize_to_hiragana(original_clean), normalize_to_hiragana(recognized_clean))
    diff_html = _build_diff_html(original, recognized)

    similarity = max(original_similarity, kana_similarity)
    score = int(similarity * 100)

    return JSONResponse({
        "score": score,
        "similarity": similarity,
        "original_similarity": original_similarity,
        "kana_similarity": kana_similarity,
        **diff_html,
    })
