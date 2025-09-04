# 日语短文朗读与跟读应用

这是一个使用 FastAPI 和 Jinja2 开发的日语朗读练习应用。

## 功能

- 导入日语文本
- 自动生成假名注音和罗马音
- 语音录音和识别
- 发音评测

## 运行

1. 安装依赖：`pip install -r requirements.txt`
2. 运行应用：`python -m uvicorn app:app --reload`
3. 打开浏览器访问 http://127.0.0.1:8000

## 注意

- 需要麦克风权限进行录音
- 语音识别使用 Google API，需要网络连接
