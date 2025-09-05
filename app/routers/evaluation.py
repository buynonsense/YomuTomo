import difflib
from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

router = APIRouter(prefix="", tags=["评测"])


@router.post("/evaluate", summary="朗读评测")
async def evaluate(original: str = Form(..., description="原始日语文本"), recognized: str = Form(..., description="语音识别得到的文本")):
    similarity = difflib.SequenceMatcher(None, original, recognized).ratio()
    score = int(similarity * 100)
    return JSONResponse({"score": score, "similarity": similarity})


