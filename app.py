from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pykakasi
import speech_recognition as sr
import io
import difflib
import openai
import os
import json
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


from app.main import app  # type: ignore  # noqa
tags_metadata = [
    {"name": "主页", "description": "首页与静态页面相关接口。"},
    {"name": "认证", "description": "用户注册、登录、退出登录。"},
    {"name": "处理", "description": "对课文进行注音、翻译与生词提取。"},
    {"name": "文章", "description": "文章的查看、列表、删除与更新时间刷新。"},
    {"name": "评测", "description": "朗读评测接口。"},
]

