import json
import pykakasi
import openai
import httpx
from passlib.hash import pbkdf2_sha256
from typing import List, Dict, Tuple
from app.core.config import settings
from app.utils.placeholder_texts import PLACEHOLDER_MEANINGS
import concurrent.futures
import threading
import asyncio
import inspect
import traceback
import logging
from app.services.ai_client_async import AIClient, AIClientError
from app.services.furigana_filter import apply_furigana_filter
from app.utils.time import beijing_now

try:
    import bcrypt as bcrypt_backend
except ImportError:
    bcrypt_backend = None


# 日志函数，包含北京时间
def log_with_time(message: str, level: str = "INFO"):
    """带北京时间的日志输出"""
    timestamp = beijing_now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [{level}] {message}")


kks = pykakasi.kakasi()
# 移除默认客户端，使用用户提供的配置


def get_openai_client(api_key: str | None, base_url: str | None):
    # 简单调试日志（生产可改为使用logging）
    try:
        masked = (api_key[:6] + '***' + api_key[-4:]) if api_key and len(api_key) > 10 else ('None' if not api_key else '***')
        log_with_time(f"[AI] Init client. Header API Key: {masked}; header base_url={base_url or 'None'}")
    except Exception:
        pass
    if api_key:
        # Return a synchronous compatibility client that routes through AIClient.factory
        provider = {"api_url": base_url or '', "api_key": api_key, "model": None, "extra": {}}
        return SyncCompatClient(provider)
    else:
        # Log caller stack to help trace which code path invoked this without an API key
        try:
            caller = inspect.stack()[1]
            logging.error("get_openai_client called without api_key. caller: %s:%s in %s", caller.filename, caller.lineno, caller.function)
            logging.error("Call stack:\n%s", ''.join(traceback.format_stack()))
        except Exception:
            pass
        raise ValueError("必须提供API key才能使用AI功能 (get_openai_client called without api_key)")


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
        log_with_time(f"[AI] CALL _ai_fix_ruby model={model} len(text)={len(original_text)}")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = resp.choices[0].message.content.strip()
        return content or kakasi_ruby_html
    except Exception as e:
        log_with_time(f"[AI] _ai_fix_ruby failed: {e}")
        return kakasi_ruby_html


def _ai_ruby(original_text: str, model: str, client: openai.OpenAI) -> str:
    prompt = (
        "请将下面的日语文本转换为带ruby注音的HTML，要求：只输出HTML本身，"
        "对需要注音的词使用 <ruby>漢字<rt>かな</rt></ruby>，对假名和标点原样输出。\n\n"
        f"文本：\n{original_text}"
    )
    try:
        log_with_time(f"[AI] CALL _ai_ruby model={model} len(text)={len(original_text)}")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = resp.choices[0].message.content.strip()
        return content
    except Exception as e:
        log_with_time(f"[AI] _ai_ruby failed: {e}")
        return _kakasi_ruby(original_text)


def generate_ruby(text: str, model: str, client: openai.OpenAI) -> str:
    mode = settings.FURIGANA_MODE.lower()
    if mode == "kakasi":
        ruby_html = _kakasi_ruby(text)
        return apply_furigana_filter(ruby_html, getattr(settings, "FURIGANA_LEVEL_FILTER", 1))
    if mode == "ai":
        ruby_html = _ai_ruby(text, model, client)
        return apply_furigana_filter(ruby_html, getattr(settings, "FURIGANA_LEVEL_FILTER", 1))
    # hybrid
    base_html = _kakasi_ruby(text)
    ruby_html = _ai_fix_ruby(text, base_html, model, client)
    return apply_furigana_filter(ruby_html, getattr(settings, "FURIGANA_LEVEL_FILTER", 1))


def extract_vocabulary(text: str, model: str, client: openai.OpenAI) -> List[Dict]:
    """从日语文本中提取生词。

    返回 [{word, meaning}] 列表, meaning 必须由 AI 生成 (中文)。

    强约束:
    - 只返回 JSON 数组, 不返回任何解释/前言
    - 每个词必须带中文 meaning (没有就跳过这个, 不要留空)
    - 不再要求 pronunciation (用户不要读音)
    """
    prompt = f"""分析以下日语文本, 提取出可能对初学者或中级学习者困难的词语。
重点提取:
- 汉字复合词
- 生僻词语
- 专业术语
- 不常见的表达

对于每个词语, 请提供:
- word: 日语词语 (必须是日语, 不要包含英文)
- meaning: 中文释义 (必须给出, 5-15 字, 不要空着)

只提取真正困难的词语 (3-8 个), 跳过简单词语如 "です"、"ます" 等。

严格要求:
1. 你的回复必须且只能是一个合法 JSON 数组, 不允许任何解释、问候、markdown 代码块。
2. 不要在 JSON 前后写任何文字。
3. 重复的 word 只保留第一个。

返回格式示例 (注意: 这是示例, 你必须根据上面的文本生成对应内容):
[
  {{"word": "高校生", "meaning": "高中生"}},
  {{"word": "逮捕", "meaning": "逮捕, 依法捉拿"}}
]

文本: {text}"""
    try:
        log_with_time(f"[AI] CALL extract_vocabulary model={model} len(text)={len(text)}")
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        content = (response.choices[0].message.content or "").strip()

        # 1) 最常见路径: 严格 JSON 解析 (整段就是合法 JSON 数组)
        vocab = _parse_vocab_json(content)
        if vocab:
            return vocab[:8]

        # 2) AI 加了 markdown 代码块 (```json ... ```), 先把代码块抽出来
        for fence in ("```json", "```JSON", "```"):
            open_idx = content.find(fence)
            if open_idx == -1:
                continue
            fence_end = content.find("```", open_idx + len(fence))
            if fence_end == -1:
                continue
            inner = content[open_idx + len(fence):fence_end].strip()
            vocab = _parse_vocab_json(inner)
            if vocab:
                return vocab[:8]

        # 3) AI 在 JSON 前后加了前言/后语, 剥 [ ... ] 子串;
        #    或者 AI 只给了一个对象 { ... } (没包成数组), 也兼容。
        first = content.find('[')
        last = content.rfind(']')
        if first != -1 and last > first:
            vocab = _parse_vocab_json(content[first:last + 1])
            if vocab:
                return vocab[:8]
        # 3b) 没有 [ ... ] 但有 { ... }, 包成数组再试一次
        obj_first = content.find('{')
        obj_last = content.rfind('}')
        if obj_first != -1 and obj_last > obj_first:
            vocab = _parse_vocab_json("[" + content[obj_first:obj_last + 1] + "]")
            if vocab:
                return vocab[:8]

        # 4) 终极兜底: AI 实在不配合 (只给散文 / 解释), 用正则从原文抠日语词
        #    此时我们没有 AI 生成的 meaning, 留 None, 让模板显示 "—"
        fallback = _extract_japanese_words_fallback(content)
        if fallback:
            log_with_time(f"[AI] extract_vocabulary JSON 全失败, 走正则兜底, 拿到 {len(fallback)} 个词")
            return fallback[:8]

        log_with_time(f"[AI] extract_vocabulary 解析失败, content={content[:200]!r}")
        return []

    # AI 抛异常 (超时 / 5xx / 网络错误) 时, 重新抛出, 让上层把整篇文章标记为失败,
    # 通知中心写 "生词提取失败"。不要静默 return [], 否则用户会看到空生词但不知原因。
    except Exception as e:
        log_with_time(f"[AI] extract_vocabulary failed: {e}")
        raise


def _is_transient_ai_error(err: Exception) -> bool:
    """判断 AI 调用异常是否值得重试。

    优先级:
    1. AIClientError.transient 标志: ai_client_async.py 在包装异常时已经
       区分过瞬时 (timeout/网络/5xx/429) vs 永久 (4xx 配置错误), 这里
       直接信任这个标志。这是最可靠的信号 — 不要去子串匹配 message。
    2. 直接看到 httpx 瞬时异常 (兜底, 一般 AIClient 内部已经包过)。
    3. 4xx / 解析失败等: 不重试, 浪费时间。
    """
    # 1) AIClientError 自带 transient 标志, 这是最准确的信号
    if isinstance(err, AIClientError):
        if err.transient:
            return True
        return False
    # 2) 直连 httpx 瞬时异常 (理论上游 AIClient 都会包装, 这里是兜底)
    if isinstance(err, (httpx.TimeoutException, httpx.ConnectError, ConnectionError, TimeoutError)):
        return True
    return False


def _extract_vocabulary_with_retry(text: str, model: str, client: openai.OpenAI) -> List[Dict]:
    """对 extract_vocabulary 包一层应用层重试。

    底层 AIClient 已有 AI_REQUEST_RETRIES 次内部重试, 这里再重试一次纯粹是兜底,
    给瞬时网络问题再多一次机会。最多 2 次尝试 (本身 + 1 次重试)。
    4xx / 解析失败等非瞬时错误, 一次后直接抛, 不浪费用户时间。
    """
    for attempt in (1, 2):
        try:
            return extract_vocabulary(text, model, client)
        except Exception as e:
            log_with_time(
                f"[AI] extract_vocabulary attempt {attempt} failed: {e} (transient={_is_transient_ai_error(e)})"
            )
            if not _is_transient_ai_error(e) or attempt == 2:
                raise


def _extract_japanese_words_fallback(content: str) -> List[Dict]:
    """终极兜底: AI 没返回可用 JSON, 从 AI 整段回复里抠日语词。

    - 只在严格 JSON 解析 + markdown 剥离 + [...]/ {...} 剥离全部失败时用
    - 词从 AI 的整段回复里抠 (AI 通常会把词写进 ```json ``` 或者散落在散文里)
    - meaning 留 None: 用户在 UI 上看到 "释义：—"
    - 入库过滤在调用方统一做 (有 word 但没 meaning 的条目, 调用方可以选择
      丢弃或保存)。当前 extract_vocabulary 直接返回, 由保存路径决定。
    """
    import re
    # 抠两种: 带引号的 "日语词" / 散文中明显的 2-8 个汉字/假名词
    quoted = re.findall(r'["\'「『]([^"\'」』\n]{2,10})["\'」』]', content)
    bare = re.findall(r'[々〆〇ーゝゞ]|[一-龯]{2,}|[ぁ-ゖ]{2,}|[ァ-ヺ]{2,}', content)
    candidates = quoted + bare
    # 中文虚词 / 助词 (日语不会用这些字), 一旦词里出现就大概率是中文短语
    _chinese_particles = set("的是在了和与为于从到对把被给让使请要能会可以可能")
    seen = set()
    out: List[Dict] = []
    for w in candidates:
        word = w.strip()
        if not word or word in seen:
            continue
        if word.isascii() or len(word) <= 1:
            continue
        if any(ch.isdigit() for ch in word):
            continue
        # 排除 schema 字段名 / 常见噪声
        if word in ('word', 'meaning', 'pronunciation', 'taifuu'):
            continue
        # 含中文虚词的整段话不要 (是 Japanese 的话用 の / は / を, 不会用 的 / 是)
        if any(ch in _chinese_particles for ch in word):
            continue
        seen.add(word)
        out.append({"word": word, "meaning": None})
    return out


def _parse_vocab_json(raw: str) -> List[Dict]:
    """把 AI 返回的 JSON 解析成 [{word, meaning}] 列表。

    - 必须严格 JSON 数组
    - 必须有 word / meaning 两个字段
    - 丢掉所有 meaning 缺失/为空的项 (避免占位符)
    - 同一 word 去重
    """
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    seen = set()
    out: List[Dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        word = (item.get("word") or "").strip()
        meaning = (item.get("meaning") or "").strip()
        # 过滤无效项
        if not word or not meaning:
            continue
        if word.isascii() or len(word) <= 1:
            continue
        if any(ch.isdigit() for ch in word):
            continue
        if word in ('word', 'meaning', 'pronunciation'):
            continue
        if word in seen:
            continue
        # 释义是占位符 (如 "释义待补充" / "待补充" / "?") 视为无效
        if meaning in PLACEHOLDER_MEANINGS:
            continue
        seen.add(word)
        out.append({"word": word, "meaning": meaning})
    return out


def translate_to_chinese(text: str, model: str, client: openai.OpenAI) -> str:
    prompt = f"""请将以下日语文本翻译成自然、流畅的中文。
要求：
- 保持原文的语气和风格
- 翻译要准确、易懂
- 适当处理文化差异
- 保持段落结构

日语文本：{text}

请直接返回中文翻译，不要添加其他说明。"""
    try:
        log_with_time(f"[AI] CALL translate_to_chinese model={model} len(text)={len(text)}")
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        translation = response.choices[0].message.content.strip()
        return translation
    except Exception as e:
        log_with_time(f"[AI] translate_to_chinese failed: {e}")
        return "翻译失败，请检查AI配置"


def generate_title(text: str, model: str, client: openai.OpenAI) -> str:
    prompt = f"""下面是一段日语课文内容，请你基于主要主题生成一个『简体中文』标题：
要求：
1. 仅输出简体中文标题本身，不要任何前缀/引号/标点（例如“标题：”或冒号都不要）。
2. 长度 6~15 个汉字，尽量精炼概括主题。
3. 不要包含日文假名、罗马字、英文字母、数字或特殊符号。
4. 不要使用书名号、引号、感叹号、句号等标点。
5. 避免太空泛的词（如“故事”“文章”），应具体到语义核心。

日语原文（截断前800字符）：\n{text[:800]}\n\n请直接输出标题："""
    try:
        log_with_time(f"[AI] CALL generate_title model={model} len(text)={len(text)}")
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        title = response.choices[0].message.content.strip()
        title = title.strip('"“”『』「」')
        import re
        if re.search(r'[ぁ-ゖ]', title) or re.search(r'[A-Za-z]', title):
            try:
                fix_prompt = f"请将下面这段标题改写成符合要求的纯简体中文（6~15个汉字，无标点，无外文）：{title}\n只输出改写后的标题。"
                fix_resp = client.chat.completions.create(
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
        if not re.search(r'[一-龯]', title):
            title = "朗读练习"
        return title or "朗读练习"
    except Exception as e:
        log_with_time(f"[AI] generate_title failed: {e}")
        return "朗读练习"


def hash_password(password: str) -> str:
    # Use a long-password-safe default for new hashes.
    return pbkdf2_sha256.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith("$pbkdf2-sha256$"):
        try:
            return pbkdf2_sha256.verify(password, password_hash)
        except (ValueError, TypeError):
            return False

    if is_legacy_bcrypt_hash(password_hash):
        return verify_legacy_bcrypt_password(password, password_hash)

    return False


def is_legacy_bcrypt_hash(password_hash: str) -> bool:
    return password_hash.startswith(("$2a$", "$2b$", "$2x$", "$2y$"))


def verify_legacy_bcrypt_password(password: str, password_hash: str) -> bool:
    if bcrypt_backend is None:
        return False

    try:
        return bcrypt_backend.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except (AttributeError, TypeError, ValueError):
        return False


def generate_all_content(text: str, model: str, client: openai.OpenAI) -> Tuple[str, List[Dict], str, str, str]:
    """
    并发生成所有AI内容：注音、词汇、翻译、标题、emoji
    返回：(ruby_text, vocab, translation, title, emoji)
    """
    def generate_ruby_task():
        return generate_ruby(text, model, client)

    def extract_vocab_task():
        # 用带重试的版本: AI 超时 / 5xx 会重试一次; 4xx / 解析失败直接抛
        return _extract_vocabulary_with_retry(text, model, client)

    def translate_task():
        return translate_to_chinese(text, model, client)

    def generate_title_task():
        return generate_title(text, model, client)

    def generate_emoji_task():
        return generate_emoji(text, model, client)

    # 使用ThreadPoolExecutor并发执行所有任务
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # 提交所有任务
        ruby_future = executor.submit(generate_ruby_task)
        vocab_future = executor.submit(extract_vocab_task)
        translation_future = executor.submit(translate_task)
        title_future = executor.submit(generate_title_task)
        emoji_future = executor.submit(generate_emoji_task)

        # 等待所有任务完成并获取结果
        try:
            ruby_text = ruby_future.result(timeout=300)  # 300秒超时
            vocab = vocab_future.result(timeout=300)
            translation = translation_future.result(timeout=300)
            title = title_future.result(timeout=300)
            emoji = emoji_future.result(timeout=300)

            return ruby_text, vocab, translation, title, emoji

        except concurrent.futures.TimeoutError:
            # 如果超时，抛出异常让上层处理
            raise Exception("AI生成超时：请求处理时间超过5分钟")

        except Exception as e:
            # 重新抛出异常, 附带可操作的提示
            if isinstance(e, AIClientError):
                status = e.status_code
                if e.transient and status and 500 <= status < 600:
                    raise Exception(
                        f"AI 服务端暂时不可用 (HTTP {status})，已自动重试，请稍后再试或换其他 AI 配置"
                    ) from e
                if e.transient:
                    raise Exception(
                        f"AI 接口超时，已自动重试仍失败，请检查网络或稍后再试"
                    ) from e
                if status:
                    if status in (401, 403):
                        raise Exception(
                            f"AI 接口鉴权失败 (HTTP {status})，请检查 API Key 是否正确"
                        ) from e
                    if status == 429:
                        raise Exception(
                            "AI 接口调用次数超限 (HTTP 429)，请稍后再试或升级套餐"
                        ) from e
                    raise Exception(
                        f"AI 接口返回错误 (HTTP {status})，请检查配置或稍后再试"
                    ) from e
                # transient=False 但也没 status_code: 通常是 4xx 解析失败之类
                raise Exception(
                    f"AI 接口调用失败：{str(e)}，请检查 API 配置"
                ) from e
            # 非 AIClientError, 保持原行为但去掉了 "AI生成失败:" 前缀的重复
            raise Exception(f"AI 生成失败: {str(e)}")


def generate_emoji(text: str, model: str, client: openai.OpenAI) -> str:
    prompt = (
        "请从下面文本的主题中，选择一个最能代表它的 emoji。只输出一个 emoji 字符，不要任何其他内容。\n\n"
        f"文本：\n{text[:400]}"
    )
    try:
        log_with_time(f"[AI] CALL generate_emoji model={model} len(text)={len(text)}")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        emoji = resp.choices[0].message.content.strip()
        # 简单清洗：限制长度，避免返回描述文字
        if len(emoji) > 4:
            emoji = emoji.split()[0]
        return emoji
    except Exception as e:
        log_with_time(f"[AI] generate_emoji failed: {e}")
        return "📝"


class SyncCompatCompletions:
    def __init__(self, provider: dict):
        self.provider = provider

    def create(self, model: str, messages: list, max_tokens: int = None):
        # Ensure provider model is set
        self.provider['model'] = model
        client = AIClient.factory(self.provider)
        try:
            # Run async client in this sync context (safe inside ThreadPoolExecutor worker threads)
            resp = asyncio.run(client.chat(messages))
        except Exception as e:
            # Normalize to raise as-is so callers see the error
            raise e
        # Build a small object compatible with existing usage: resp.choices[0].message.content
        class _Message:
            def __init__(self, content):
                self.content = content

        class _Choice:
            def __init__(self, text):
                self.message = _Message(text)

        class _Resp:
            def __init__(self, text, raw):
                self.choices = [_Choice(text)]
                self.raw = raw

        return _Resp(resp.get('text', ''), resp.get('raw'))


class SyncCompatClient:
    def __init__(self, provider: dict):
        self.chat = type('C', (), {'completions': SyncCompatCompletions(provider)})()
