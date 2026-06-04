import difflib
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


def calculate_similarity(left: str, right: str) -> float:
    return difflib.SequenceMatcher(None, left, right).ratio()


@router.post("/evaluate", summary="朗读评测")
async def evaluate(original: str = Form(..., description="原始日语文本"), recognized: str = Form(..., description="语音识别得到的文本")):
    original_similarity = calculate_similarity(original, recognized)
    kana_similarity = calculate_similarity(normalize_to_hiragana(original), normalize_to_hiragana(recognized))

    similarity = max(original_similarity, kana_similarity)
    score = int(similarity * 100)

    return JSONResponse({
        "score": score,
        "similarity": similarity,
        "original_similarity": original_similarity,
        "kana_similarity": kana_similarity,
    })

