import json
import pykakasi
import openai
from datetime import datetime
from passlib.context import CryptContext
from typing import List, Dict
from app.core.config import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

kks = pykakasi.kakasi()
_default_client = openai.OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL or None)


def get_openai_client(api_key: str | None, base_url: str | None):
    if api_key:
        return openai.OpenAI(api_key=api_key, base_url=base_url or None)
    return _default_client


def _kakasi_ruby(text: str) -> str:
    result = kks.convert(text)
    ruby_html = ''
    for item in result:
        orig = item['orig']
        hira = item['hira']
        if orig == hira:
            ruby_html += orig
        else:
            ruby_html += f"<ruby>{orig}<rt>{hira}</rt></ruby>"
    return ruby_html


def _ai_fix_ruby(original_text: str, kakasi_ruby_html: str, model: str, client: openai.OpenAI) -> str:
    prompt = (
        "你是日语教师。请对下面的带有ruby标注的HTML进行校对，确保每个汉字词的假名准确。"
        "只返回修正后的HTML，不要解释。\n\n"
        f"原文：\n{original_text}\n\n"
        f"当前ruby HTML：\n{kakasi_ruby_html}"
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = resp.choices[0].message.content.strip()
        return content or kakasi_ruby_html
    except Exception:
        return kakasi_ruby_html


def _ai_ruby(original_text: str, model: str, client: openai.OpenAI) -> str:
    prompt = (
        "请将下面的日语文本转换为带ruby注音的HTML，要求：只输出HTML本身，"
        "对需要注音的词使用 <ruby>漢字<rt>かな</rt></ruby>，对假名和标点原样输出。\n\n"
        f"文本：\n{original_text}"
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = resp.choices[0].message.content.strip()
        return content
    except Exception:
        return _kakasi_ruby(original_text)


def generate_ruby(text: str, model: str, client: openai.OpenAI) -> str:
    mode = settings.FURIGANA_MODE.lower()
    if mode == "kakasi":
        return _kakasi_ruby(text)
    if mode == "ai":
        return _ai_ruby(text, model, client)
    # hybrid
    base_html = _kakasi_ruby(text)
    return _ai_fix_ruby(text, base_html, model, client)


def extract_vocabulary(text: str, model: str, client: openai.OpenAI | None = None) -> List[Dict]:
    prompt = f"""分析以下日语文本，提取出可能对初学者或中级学习者困难的词语。
重点提取：
- 汉字复合词
- 生僻词语
- 专业术语
- 不常见的表达

对于每个词语，请提供：
- word: 日语词语
- meaning: 中文释义
- pronunciation: 罗马音读音

返回JSON格式的数组，例如：
[
  {{"word": "こんにちは", "meaning": "你好", "pronunciation": "konnichiwa"}},
  {{"word": "世界", "meaning": "世界", "pronunciation": "sekai"}}
]

文本：{text}"""
    try:
        response = (client or _default_client).chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content.strip()
        if content.startswith('[') and content.endswith(']'):
            vocab = json.loads(content)
            return vocab
        else:
            import re
            words = re.findall(r'"([^"]*)"', content)
            return [{"word": word, "meaning": "释义待补充", "pronunciation": "读音待补充"} for word in words]
    except Exception as _:
        return []


def translate_to_chinese(text: str, model: str, client: openai.OpenAI | None = None) -> str:
    prompt = f"""请将以下日语文本翻译成自然、流畅的中文。
要求：
- 保持原文的语气和风格
- 翻译要准确、易懂
- 适当处理文化差异
- 保持段落结构

日语文本：{text}

请直接返回中文翻译，不要添加其他说明。"""
    try:
        response = (client or _default_client).chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        translation = response.choices[0].message.content.strip()
        return translation
    except Exception:
        return "翻译失败，请检查AI配置"


def generate_title(text: str, model: str, client: openai.OpenAI | None = None) -> str:
    prompt = f"""下面是一段日语课文内容，请你基于主要主题生成一个『简体中文』标题：
要求：
1. 仅输出简体中文标题本身，不要任何前缀/引号/标点（例如“标题：”或冒号都不要）。
2. 长度 6~15 个汉字，尽量精炼概括主题。
3. 不要包含日文假名、罗马字、英文字母、数字或特殊符号。
4. 不要使用书名号、引号、感叹号、句号等标点。
5. 避免太空泛的词（如“故事”“文章”），应具体到语义核心。

日语原文（截断前800字符）：\n{text[:800]}\n\n请直接输出标题："""
    try:
        response = (client or _default_client).chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        title = response.choices[0].message.content.strip()
        title = title.strip('"“”『』「」')
        import re
        if re.search(r'[\u3040-\u30FF]', title) or re.search(r'[A-Za-z]', title):
            try:
                fix_prompt = f"请将下面这段标题改写成符合要求的纯简体中文（6~15个汉字，无标点，无外文）：{title}\n只输出改写后的标题。"
                fix_resp = (client or _default_client).chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": fix_prompt}]
                )
                fixed = fix_resp.choices[0].message.content.strip().strip('"“”『』「」')
                if fixed:
                    title = fixed
            except Exception:
                pass
        if len(title) > 15:
            title = title[:15]
        if not re.search(r'[\u4e00-\u9fff]', title):
            title = "朗读练习"
        return title or "朗读练习"
    except Exception:
        return "朗读练习"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def generate_emoji(text: str, model: str, client: openai.OpenAI | None = None) -> str:
    prompt = (
        "请从下面文本的主题中，选择一个最能代表它的 emoji。只输出一个 emoji 字符，不要任何其他内容。\n\n"
        f"文本：\n{text[:400]}"
    )
    try:
        resp = (client or _default_client).chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        emoji = resp.choices[0].message.content.strip()
        # 简单清洗：限制长度，避免返回描述文字
        if len(emoji) > 4:
            emoji = emoji.split()[0]
        return emoji
    except Exception:
        return "📝"


