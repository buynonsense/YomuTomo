from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pykakasi
import speech_recognition as sr
import io
import difflib
import openai
import os
import json

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

kks = pykakasi.kakasi()

# 配置OpenAI（请设置环境变量OPENAI_API_KEY或修改此处）
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY", "your-api-key-here"))

def generate_ruby(text):
    result = kks.convert(text)
    ruby_html = ''
    for item in result:
        orig = item['orig']
        hira = item['hira']
        if orig == hira:  # 假名或标点
            ruby_html += orig
        else:
            ruby_html += f"<ruby>{orig}<rt>{hira}</rt></ruby>"
    return ruby_html

def extract_vocabulary(text, model="gpt-5-mini"):
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
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content.strip()
        # 尝试解析JSON
        if content.startswith('[') and content.endswith(']'):
            vocab = json.loads(content)
            return vocab
        else:
            # 如果不是JSON，提取引号内的词并创建基本结构
            import re
            words = re.findall(r'"([^"]*)"', content)
            return [{"word": word, "meaning": "释义待补充", "pronunciation": "读音待补充"} for word in words]
    except Exception as e:
        print(f"AI提取生词失败: {e}")
        return []

def translate_to_chinese(text, model="gpt-5-mini"):
    """将日语文本翻译成中文"""
    prompt = f"""请将以下日语文本翻译成自然、流畅的中文。
要求：
- 保持原文的语气和风格
- 翻译要准确、易懂
- 适当处理文化差异
- 保持段落结构

日语文本：{text}

请直接返回中文翻译，不要添加其他说明。"""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        translation = response.choices[0].message.content.strip()
        return translation
    except Exception as e:
        print(f"AI翻译失败: {e}")
        return "翻译失败，请检查AI配置"

def generate_title(text, model="gpt-5-mini"):
    """根据课文内容生成简洁中文标题（不超过15个汉字，强制中文）。"""
    prompt = f"""下面是一段日语课文内容，请你基于主要主题生成一个『简体中文』标题：
要求：
1. 仅输出简体中文标题本身，不要任何前缀/引号/标点（例如“标题：”或冒号都不要）。
2. 长度 6~15 个汉字，尽量精炼概括主题。
3. 不要包含日文假名、罗马字、英文字母、数字或特殊符号。
4. 不要使用书名号、引号、感叹号、句号等标点。
5. 避免太空泛的词（如“故事”“文章”），应具体到语义核心。

日语原文（截断前800字符）：\n{text[:800]}\n\n请直接输出标题："""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        title = response.choices[0].message.content.strip()
        # 清理可能的引号
        title = title.strip('"“”『』「」')
        # 如果包含日文假名或拉丁字符，尝试再次转换为中文
        import re
        if re.search(r'[\u3040-\u30FF]', title) or re.search(r'[A-Za-z]', title):
            try:
                fix_prompt = f"请将下面这段标题改写成符合要求的纯简体中文（6~15个汉字，无标点，无外文）：{title}\n只输出改写后的标题。"
                fix_resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": fix_prompt}]
                )
                fixed = fix_resp.choices[0].message.content.strip().strip('"“”『』「」')
                if fixed:
                    title = fixed
            except Exception as _:
                pass
        # 再做长度截断（安全）
        if len(title) > 15:
            title = title[:15]
        # 兜底：若仍为空或不含任何中文，使用默认
        if not re.search(r'[\u4e00-\u9fff]', title):
            title = "朗读练习"
        return title or "朗读练习"
    except Exception as e:
        print(f"AI生成标题失败: {e}")
        return "朗读练习"

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/process_text", response_class=HTMLResponse)
async def process_text(
    request: Request,
    text: str = Form(...),
    api_key: str = Form(None),
    base_url: str = Form(None),
    model: str = Form(None)
):
    """处理文本并生成阅读页面。
    优先顺序：自定义请求头 > 表单字段 > 环境变量默认值。
    这样前端可以用两种方式传递配置，避免不一致。"""
    header_api_key = request.headers.get('X-API-Key')
    header_base_url = request.headers.get('X-Base-URL')
    header_model = request.headers.get('X-Model')

    final_api_key = header_api_key or api_key or os.getenv("OPENAI_API_KEY", "")
    final_base_url = header_base_url or base_url or os.getenv("OPENAI_BASE_URL", "")
    final_model = header_model or model or os.getenv("OPENAI_MODEL", "gpt-5-mini")

    # 配置OpenAI客户端
    global client
    if final_api_key:
        try:
            client = openai.OpenAI(api_key=final_api_key, base_url=final_base_url if final_base_url else None)
        except Exception as e:
            print("OpenAI客户端初始化失败:", e)

    # 处理文本，生成ruby文本
    ruby_text = generate_ruby(text)
    # 提取生词
    vocab = extract_vocabulary(text, final_model)
    # 生成中文翻译
    translation = translate_to_chinese(text, final_model)
    # 生成标题
    title = generate_title(text, final_model)
    return templates.TemplateResponse(
        "reading.html",
        {"request": request, "original": text, "ruby_text": ruby_text, "vocab": vocab, "translation": translation, "title": title}
    )

@app.post("/evaluate")
async def evaluate(request: Request, original: str = Form(...), recognized: str = Form(...)):
    # 简单评测：相似度
    similarity = difflib.SequenceMatcher(None, original, recognized).ratio()
    score = int(similarity * 100)
    return JSONResponse({"score": score, "similarity": similarity})
