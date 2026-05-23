import os


class Config:
    def __init__(self):
        self.ai_api_key = os.getenv("AI_API_KEY", "")
        self.ai_base_url = os.getenv("AI_BASE_URL", "https://api.deepseek.com/v1")
        self.ai_model = os.getenv("AI_MODEL", "deepseek-chat")
        self.max_publish_per_day = int(os.getenv("MAX_PUBLISH_PER_DAY", "2"))
        self.crawl_interval_hours = int(os.getenv("CRAWL_INTERVAL_HOURS", "2"))
        self.rewrite_temperature = float(os.getenv("REWRITE_TEMPERATURE", "0.7"))
        self.db_path = os.getenv("DB_PATH", "auto_media.db")
        self.publish_hour_1 = int(os.getenv("PUBLISH_HOUR_1", "9"))
        self.publish_hour_2 = int(os.getenv("PUBLISH_HOUR_2", "17"))
        self.publish_timeout = int(os.getenv("PUBLISH_TIMEOUT", "60"))
