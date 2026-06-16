"""占位符 / 兜底文本的 single source of truth。

历史背景: 旧版 AI 抽取生词失败时会回退到正则启发式, 把
"释义待补充" / "读音待补充" 之类的占位串写进 vocab_json 和
user_vocabulary.meaning / pronunciation 字段。

用户已经明确:
  1) 不要读音
  2) 释义必须是 AI 真给的中文, 看不到就当没有

所以这些占位串在三个地方都需要识别并清掉:
  - app/services/services.py::_parse_vocab_json  (写入时过滤)
  - app/utils/templates.py::_clean_meaning       (渲染时映射)
  - alembic/versions/f1a2b3c4d5e6_*              (历史数据清理)

抽到这一个文件, 三个调用方都从这里 import, 避免加新占位符时漏改。
"""
from __future__ import annotations

from typing import FrozenSet

# 释义 / meaning 的占位串集合
PLACEHOLDER_MEANINGS: FrozenSet[str] = frozenset({
    "",
    "释义待补充",
    "待补充",
    "暂无",
    "暂无释义",
    "?",
    "？",
    "无",
    "TBD",
    "tbd",
    "todo",
})

# 读音 / pronunciation 的占位串集合 (空串也算, 因为旧代码可能落空)
PLACEHOLDER_PRONUNCIATIONS: FrozenSet[str] = frozenset({
    "",
    "读音待补充",
    "待补充",
})
