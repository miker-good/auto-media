def test_config_defaults():
    from config import Config
    cfg = Config()
    assert cfg.max_publish_per_day == 2
    assert cfg.crawl_interval_hours == 2
    assert cfg.ai_api_key == ""
    assert cfg.ai_model == "deepseek-chat"


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "sk-test")
    monkeypatch.setenv("AI_BASE_URL", "https://api.deepseek.com/v1")
    from config import Config
    cfg = Config()
    assert cfg.ai_api_key == "sk-test"
    assert cfg.ai_base_url == "https://api.deepseek.com/v1"
