import json
import pykakasi
import openai
from passlib.hash import pbkdf2_sha256
from typing import List, Dict, Tuple
from app.core.config import settings
import concurrent.futures
import threading
import asyncio
import inspect
import traceback
import logging
from app.services.ai_client_async import AIClient, AIClientError
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
        return _kakasi_ruby(text)
    if mode == "ai":
        return _ai_ruby(text, model, client)
    # hybrid
    base_html = _kakasi_ruby(text)
    return _ai_fix_ruby(text, base_html, model, client)


def extract_vocabulary(text: str, model: str, client: openai.OpenAI) -> List[Dict]:
    prompt = f"""分析以下日语文本，提取出可能对初学者或中级学习者困难的词语。
重点提取：
- 汉字复合词
- 生僻词语
- 专业术语
- 不常见的表达

对于每个词语，请提供：
- word: 日语词语（必须是日语，不要包含英文）
- meaning: 中文释义
- pronunciation: 罗马音读音

只提取真正困难的词语（3-8个），跳过简单词语如"です"、"ます"等。
返回JSON格式的数组，例如：
[
  {{"word": "こんにちは", "meaning": "你好", "pronunciation": "konnichiwa"}},
  {{"word": "世界", "meaning": "世界", "pronunciation": "sekai"}}
]

文本：{text}"""
    try:
        log_with_time(f"[AI] CALL extract_vocabulary model={model} len(text)={len(text)}")
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content.strip()

        # 尝试解析JSON
        if content.startswith('[') and content.endswith(']'):
            vocab = json.loads(content)

            # 过滤和验证结果
            filtered_vocab = []
            for item in vocab:
                if isinstance(item, dict) and 'word' in item and 'meaning' in item and 'pronunciation' in item:
                    word = item['word'].strip()
                    meaning = item['meaning'].strip()
                    pronunciation = item['pronunciation'].strip()

                    # 过滤掉英文单词和无效内容
                    if (word and meaning and pronunciation and
                        not word.isascii() and  # 确保是日语（包含非ASCII字符）
                        len(word) > 1 and  # 跳过单字符
                        not any(char.isdigit() for char in word) and  # 不包含数字
                        word not in ['word', 'meaning', 'pronunciation', 'taifuu']):  # 过滤已知错误

                        filtered_vocab.append({
                            'word': word,
                            'meaning': meaning,
                            'pronunciation': pronunciation
                        })

            return filtered_vocab[:8]  # 限制最多8个词语

        else:
            # 如果不是JSON格式，尝试提取可能的日语词语
            import re
            # 只匹配包含汉字或平假名的词语
            japanese_words = re.findall(r'["\']([^\x00-\x7F]{1,10})["\']', content)
            filtered_words = []

            for word in japanese_words:
                word = word.strip()
                if (len(word) > 1 and
                    not any(char.isdigit() for char in word) and
                    word not in ['word', 'meaning', 'pronunciation', 'taifuu']):
                    filtered_words.append({
                        'word': word,
                        'meaning': '释义待补充',
                        'pronunciation': '读音待补充'
                    })

            return filtered_words[:5]  # 限制最多5个词语

    except Exception as e:
        log_with_time(f"[AI] extract_vocabulary failed: {e}")
        return []


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
        return extract_vocabulary(text, model, client)

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
            # 重新抛出异常，保持质量优先原则
            raise Exception(f"AI生成失败: {str(e)}")


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
