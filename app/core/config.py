import os


class Settings:
    APP_TITLE = "YomuTomo 日语朗读应用 API"
    APP_DESCRIPTION = (
        "提供课文注音、翻译、生词提取与朗读评测功能；"
        "支持用户登录后将生成结果保存为文章，并在仪表盘按更新时间排序。"
    )
    APP_VERSION = "1.0.0"

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:1234@localhost:5432/yomu_pg")
    RSSHUB_BASE_URL = os.getenv("RSSHUB_BASE_URL", "https://rsshub.rssforever.com")
    # 默认不预置固定来源，用户可在新闻中心直接输入 RSSHub 路由或订阅链接。
    NEWS_CENTER_SOURCE_URL = os.getenv("NEWS_CENTER_SOURCE_URL", "")

    # 假名模式：kakasi | hybrid | ai
    FURIGANA_MODE = os.getenv("FURIGANA_MODE", "hybrid")
    FURIGANA_LEVEL_FILTER = os.getenv("FURIGANA_LEVEL_FILTER", "1")

    # AI 请求层超时与重试配置
    AI_REQUEST_TIMEOUT_SECONDS = float(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "60"))
    AI_REQUEST_RETRIES = int(os.getenv("AI_REQUEST_RETRIES", "2"))
    AI_REQUEST_RETRY_DELAY_SECONDS = float(os.getenv("AI_REQUEST_RETRY_DELAY_SECONDS", "1"))


settings = Settings()
