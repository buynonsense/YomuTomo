import requests
from bs4 import BeautifulSoup
import json
from typing import Iterable
from app.db import get_db
from app.model.models import Article, User, CrawlTask
from app.services.ai_client_async import AIClientError
from app.services.services import generate_all_content, get_openai_client, log_with_time
from app.core.config import settings
import os
import threading
import time
from app.utils.time import utc_now

NHK_EASY_NEWS_URL = "https://www3.nhk.or.jp/news/easy/top-list.json"
NHK_EASY_BASE_URL = "https://www3.nhk.or.jp/news/easy"


def _fallback_nhk_news() -> list[dict]:
    return [
        {
            'title': '台風15号で雨や風の被害　これからも気をつけて',
            'url': 'https://www3.nhk.or.jp/news/easy/ne2025090511573/ne2025090511573.html',
            'source_url': 'https://www3.nhk.or.jp/news/easy/ne2025090511573/ne2025090511573.html'
        },
        {
            'title': '日本がアメリカに輸出する車などの関税　15%になる',
            'url': 'https://www3.nhk.or.jp/news/easy/ne2025090511472/ne2025090511472.html',
            'source_url': 'https://www3.nhk.or.jp/news/easy/ne2025090511472/ne2025090511472.html'
        },
        {
            'title': '世界で有名なデザイナー　アルマーニさんが亡くなった',
            'url': 'https://www3.nhk.or.jp/news/easy/ne2025090516408/ne2025090516408.html',
            'source_url': 'https://www3.nhk.or.jp/news/easy/ne2025090516408/ne2025090516408.html'
        },
        {
            'title': '秋の魚「さんま」　今年はたくさんとれそうだ',
            'url': 'https://www3.nhk.or.jp/news/easy/ne2025090511546/ne2025090511546.html',
            'source_url': 'https://www3.nhk.or.jp/news/easy/ne2025090511546/ne2025090511546.html'
        },
        {
            'title': '台風15号が九州の近くを進んでいる　雨に気をつけて',
            'url': 'https://www3.nhk.or.jp/news/easy/ne2025090412073/ne2025090412073.html',
            'source_url': 'https://www3.nhk.or.jp/news/easy/ne2025090412073/ne2025090412073.html'
        }
    ]


def _normalize_selected_urls(selected_urls: Iterable[str] | None) -> list[str]:
    normalized: list[str] = []
    for url in selected_urls or []:
        if not isinstance(url, str):
            continue
        value = url.strip()
        if value and value.startswith(NHK_EASY_BASE_URL):
            normalized.append(value)
    return normalized


def get_nhk_easy_news(limit: int = 12):
    """获取NHK Easy新闻 - 使用真实JSON API"""
    try:
        # NHK Easy JSON API
        url = NHK_EASY_NEWS_URL
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        # 解析JSON数据
        news_data = response.json()
        
        news_list = []
        
        # 取前 N 条新闻，作为新闻中心的候选列表
        for item in news_data[:max(limit, 0)]:
            try:
                news_id = item.get('news_id', '')
                title = item.get('title', '')
                title_with_ruby = item.get('title_with_ruby', '')
                
                # 构建完整URL
                full_url = f"https://www3.nhk.or.jp/news/easy/{news_id}/{news_id}.html"
                
                # 提取概要文本（移除HTML标签）
                outline_with_ruby = item.get('outline_with_ruby', '')
                soup = BeautifulSoup(outline_with_ruby, 'html.parser')
                outline_text = soup.get_text()
                
                news_list.append({
                    'title': title,
                    'title_with_ruby': title_with_ruby,
                    'url': full_url,
                    'news_id': news_id,
                    'outline': outline_text,
                    'source_url': full_url  # 添加源URL用于追踪
                })
                
            except Exception as e:
                log_with_time(f"解析新闻项失败: {e}")
                continue
        
        log_with_time(f"成功获取 {len(news_list)} 条NHK Easy新闻")
        return news_list
        
    except Exception as e:
        log_with_time(f"获取NHK Easy新闻失败: {e}")
        # 返回示例数据作为fallback
        fallback = _fallback_nhk_news()
        return fallback[:max(limit, 0)] if limit else fallback


def resolve_nhk_news_items(selected_urls: Iterable[str] | None = None, limit: int = 12) -> list[dict]:
    """按 URL 过滤 NHK 新闻列表。"""
    news_items = get_nhk_easy_news(limit=limit)
    normalized_urls = _normalize_selected_urls(selected_urls)
    if not normalized_urls:
        return news_items

    selected = []
    news_map = {item.get('url'): item for item in news_items if item.get('url')}
    for url in normalized_urls:
        item = news_map.get(url)
        if item:
            selected.append(item)

    return selected

def get_houkago_news():
    """获取放課後NEWS - 暂时返回空列表（网站可能已变更）"""
    try:
        # 放課後NEWS网站可能已不存在或URL变更，暂时返回空列表
        log_with_time("放課後NEWS网站不可访问，跳过此部分")
        return []
    except Exception as e:
        log_with_time(f"获取放課後NEWS失败: {e}")
        return []

def get_article_content(url):
    """获取文章内容 - 真实爬取"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # NHK Easy新闻页面的内容通常在特定的结构中
        content_selectors = [
            'div.article-main__body',  # NHK Easy的主要内容区域
            'div.article-body',
            'div.content-body',
            'div.main-text',
            'article .body',
            '.article-content'
        ]
        
        content = ""
        for selector in content_selectors:
            content_elem = soup.find(selector)
            if content_elem:
                # 移除脚本和样式元素
                for script in content_elem.find_all(['script', 'style']):
                    script.decompose()
                
                content = content_elem.get_text(separator='\n', strip=True)
                if content and len(content) > 50:  # 确保内容足够长
                    break
        
        # 如果没找到特定内容区域，尝试提取页面主要文本
        if not content or len(content) < 50:
            # 移除导航、页脚等无关元素
            for tag in soup.find_all(['nav', 'footer', 'header', 'aside', 'script', 'style']):
                tag.decompose()
            
            # 提取主要内容
            main_content = soup.find('main') or soup.find('body')
            if main_content:
                content = main_content.get_text(separator='\n', strip=True)
        
        # 清理内容
        if content:
            # 移除多余的空白字符
            import re
            content = re.sub(r'\n+', '\n', content)
            content = re.sub(r'\s+', ' ', content)
            content = content.strip()
            
            # 确保内容不为空且有意义
            if len(content) > 20:
                return content
        
        # 如果都失败了，返回提示信息
        return None
        
    except Exception as e:
        log_with_time(f"获取文章内容失败 {url}: {e}")
        return None

def generate_simplified_article(original_text, user_level, model, client):
    levels = {
        1: "JLPT N5水平（基础词汇和语法）", 
        2: "JLPT N4水平（日常会话）", 
        3: "JLPT N3水平（一般性话题）", 
        4: "JLPT N2水平（抽象话题）", 
        5: "JLPT N1水平（复杂话题）"
    }
    level_desc = levels.get(user_level, "JLPT N3水平（一般性话题）")
    prompt = f"请将以下日文文章简化到适合{level_desc}的学习者阅读水平。保持主要内容，但使用相应等级的词汇和句子结构，只输出结果，不要说无关的话。\n\n原文：{original_text}"
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except AIClientError as e:
        log_with_time(f"[AI] generate_simplified_article failed, fallback to original: {e}")
        return original_text

def crawl_and_save_articles_background(user_id, task_id, selected_urls: Iterable[str] | None = None):
    """后台处理爬虫任务"""
    db = next(get_db())
    selected_url_list = _normalize_selected_urls(selected_urls)
    
    try:
        # 更新任务状态为处理中
        task = db.query(CrawlTask).filter(CrawlTask.id == task_id).first()
        if not task:
            return
        
        task.status = "processing"
        task.updated_at = utc_now()
        db.commit()
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            task.status = "failed"
            db.commit()
            return
        
        # 检查用户是否配置了AI设置
        if not user.openai_api_key:
            task.status = "failed"
            db.commit()
            return
        
        user_level = user.level
        client = get_openai_client(user.openai_api_key, user.openai_base_url)
        model = user.openai_model
        
        if selected_url_list:
            all_news = resolve_nhk_news_items(selected_urls=selected_url_list, limit=max(20, len(selected_url_list)))
        else:
            # 只使用NHK Easy新闻，移除放課後NEWS
            all_news = get_nhk_easy_news(limit=1)
        
        task.total_articles = len(all_news)
        
        processed_count = 0
        
        for news in all_news:
            try:
                content = get_article_content(news['url'])
                if content:
                    # 添加溯源信息到内容第一行
                    source_content = f"来源: {news['url']}\n\n{content}"
                    
                    # 生成简化版
                    simplified = generate_simplified_article(content, user_level, model, client)
                    # 使用services生成完整内容
                    ruby_text, vocab, translation, title, emoji = generate_all_content(simplified, model, client)
                    
                    article = Article(
                        user_id=user_id,
                        title=title,
                        emoji_cover=emoji,
                        original=source_content,  # 包含溯源信息的内容
                        ruby_html=ruby_text,
                        translation=translation,
                        vocab_json=json.dumps(vocab, ensure_ascii=False),
                        source_url=news['url']  # 保存源URL
                    )
                    db.add(article)
                    
                    processed_count += 1
                    task.processed_articles = processed_count
                    task.updated_at = utc_now()
                    db.commit()
                    log_with_time(f"✅ 已处理 {processed_count}/{task.total_articles} 篇文章: {news['title']}")
                else:
                    log_with_time(f"⚠️ 抓取正文失败，跳过该条: {news['title']}")
                    continue
                    
            except AIClientError as e:
                log_with_time(f"⚠️ 处理文章时 AI 请求失败，已跳过该条: {news['title']}, 错误: {e}")
                continue
            except Exception as e:
                log_with_time(f"❌ 处理文章失败: {news['title']}, 错误: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        # 更新任务状态为完成
        task.status = "completed"
        task.updated_at = utc_now()
        db.commit()
        log_with_time(f"🎉 爬虫任务完成！共处理 {processed_count} 篇文章")
        
    except Exception as e:
        log_with_time(f"❌ 后台处理失败: {e}")
        import traceback
        traceback.print_exc()
        if task:
            task.status = "failed"
            task.updated_at = utc_now()
            db.commit()
    finally:
        db.close()


def crawl_and_save_articles(user_id, selected_urls: Iterable[str] | None = None):
    """启动后台爬虫任务"""
    db = next(get_db())
    selected_url_list = _normalize_selected_urls(selected_urls)
    
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"success": False, "message": "User not found"}
        
        # 创建新的爬虫任务
        task = CrawlTask(
            user_id=user_id,
            status="pending",
            total_articles=0,
            processed_articles=0
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        # 启动后台线程处理
        thread = threading.Thread(
            target=crawl_and_save_articles_background,
            args=(user_id, task.id, selected_url_list or None)
        )
        thread.daemon = True
        thread.start()
        
        return {
            "success": True, 
            "message": "爬虫任务已启动，后台处理中",
            "task_id": task.id
        }
        
    except Exception as e:
        db.rollback()
        return {"success": False, "message": f"启动失败: {str(e)}"}
    finally:
        db.close()
