import os


class Settings:
    APP_TITLE = "YomuTomo 日语朗读应用 API"
    APP_DESCRIPTION = (
        "提供课文注音、翻译、生词提取与朗读评测功能；"
        "支持用户登录后将生成结果保存为文章，并在仪表盘按更新时间排序。"
    )
    APP_VERSION = "1.0.0"

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "your-api-key-here")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")

    # 假名模式：kakasi | hybrid | ai
    FURIGANA_MODE = os.getenv("FURIGANA_MODE", "hybrid")


settings = Settings()


