# 日语短文朗读与跟读应用

这是一个使用 FastAPI 和 Jinja2 开发的日语朗读练习应用。

## 功能

- 导入日语文本
- 自动生成假名注音和罗马音
- 语音录音和识别
- 发音评测

## 运行

1. 安装依赖：`pip install -r requirements.txt`
2. 配置环境变量（可选）：
   - `OPENAI_API_KEY`: OpenAI API Key
   - `OPENAI_BASE_URL`: 可选，自定义 API Base URL
   - `OPENAI_MODEL`: 可选，默认 `gpt-5-mini`
   - `SECRET_KEY`: 会话密钥（用于登录会话），建议设置为随机字符串
   - `DATABASE_URL`: 可选，默认 `sqlite:///./app.db`
3. 初始化数据库：应用启动时会自动在 `app.db` 创建表
4. 运行应用：`python -m uvicorn app:app --reload`
5. 打开浏览器访问 http://127.0.0.1:8000

## 注意

- 需要麦克风权限进行录音
- 语音识别使用 Google API，需要网络连接
- 登录后提交文本会自动保存为文章，可在“我的文章”中查看、打开或删除
