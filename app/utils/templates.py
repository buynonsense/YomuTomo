from __future__ import annotations

from fastapi.templating import Jinja2Templates

from app.utils.placeholder_texts import PLACEHOLDER_MEANINGS
from app.utils.time import to_beijing_time
from app.utils.url import safe_href


def _format_datetime(value) -> str:
    """Jinja2 filter: 把 datetime 转成北京时间 'YYYY-MM-DD HH:MM' 文本。

    用于爬取队列片段、通知中心等需要展示"更新于 …"的场景。
    """
    if value is None:
        return ""
    converted = to_beijing_time(value) if hasattr(value, "tzinfo") else None
    if converted is None:
        return ""
    return converted.strftime("%Y-%m-%d %H:%M")


def _task_progress_percent(task) -> int:
    """Jinja2 global: 计算单个 CrawlTask 的进度百分比 (0-100)。

    - 缺 total_articles：processing 给 5% 让进度条有动态感
    - 否则 processed / total
    """
    if not task:
        return 0
    total = int(getattr(task, "total_articles", 0) or 0)
    processed = int(getattr(task, "processed_articles", 0) or 0)
    if total <= 0:
        status = getattr(task, "status", "")
        return 5 if status == "processing" else 0
    ratio = max(0.0, min(1.0, processed / total))
    return int(round(ratio * 100))


def _clean_meaning(value) -> str:
    """Jinja2 filter: 清洗脏数据里的 placeholder 释义。

    历史脏数据 (旧版 AI 抽取 / 旧版 vocab_json) 经常存:
        pronunciation = "读音待补充"
        meaning = "释义待补充"
    这两个字段用户已明确不要, 但旧条目已经落库, 不能直接删,
    所以在渲染层把它映射成空串, 模板上用 "—" 占位或隐藏整行。
    """
    if value is None:
        return ""
    text = str(value).strip()
    if text in PLACEHOLDER_MEANINGS:
        return ""
    return text


def create_templates(directory: str = "templates") -> Jinja2Templates:
    templates = Jinja2Templates(directory=directory)
    templates.env.filters["safe_href"] = safe_href
    templates.env.filters["format_datetime"] = _format_datetime
    templates.env.filters["clean_meaning"] = _clean_meaning
    templates.env.globals["task_progress_percent"] = _task_progress_percent
    return templates
