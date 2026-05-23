import pytest
import os
from unittest.mock import patch, Mock

from storage.db import Database
from crawler.zhihu import ZhihuCrawler
from rewriter.rewriter import Rewriter
from publisher.toutiao import ToutiaoPublisher
from scheduler import pipeline
from config import Config


@pytest.fixture
def config():
    cfg = Config()
    cfg.ai_api_key = "sk-test"
    cfg.max_publish_per_day = 2
    return cfg


@pytest.fixture
def db():
    db = Database(":memory:")
    db.create_tables()
    yield db
    db.close()


@patch("crawler.zhihu.ZhihuCrawler._request")
def test_full_pipeline_crawl_to_publish(mock_request, config, db):
    """End-to-end: crawl -> rewrite -> publish without errors"""
    mock_request.return_value = {
        "data": [
            {"target": {"title": "测试问题", "excerpt": "测试内容", "id": 1, "url": "https://zhihu.com/q/1"}}
        ]
    }

    # 1. Crawl
    crawler = ZhihuCrawler()
    items = crawler.run()
    for item in items:
        if not db.article_exists_by_url(item["url"]):
            db.insert_article(item["source"], item["title"], item["content"], item["url"])
    assert db.get_articles_by_status("待洗稿")

    # 2. Rewrite
    mock_client = Mock()
    mock_client.chat.completions.create.return_value = Mock(
        choices=[Mock(message=Mock(content='{"title":"改写标题","content":"改写内容"}'))]
    )
    with patch("rewriter.rewriter.OpenAI", return_value=mock_client):
        from rewriter.rewriter import Rewriter
        rew = Rewriter(config)
        for article in db.get_articles_by_status("待洗稿"):
            result = rew.rewrite(article)
            db.update_article_status(article["id"], "已洗稿", result["title"], result["content"])

    rewritten = db.get_articles_by_status("已洗稿")
    assert len(rewritten) == 1
    assert rewritten[0]["rewritten_title"] == "改写标题"

    # 3. Publish
    publisher = ToutiaoPublisher(cookies={})
    published = 0
    for article in db.get_articles_by_status("已洗稿"):
        if published >= config.max_publish_per_day:
            break
        success, err = publisher.publish({
            "title": article["rewritten_title"],
            "content": article["rewritten_content"]
        })
        db.insert_publish_log(article["id"], publisher.platform_name, "成功" if success else "失败", err)
        if success:
            db.update_article_status(article["id"], "已发布")
            published += 1

    assert published > 0
    assert db.count_published_today() > 0
    assert not db.get_articles_by_status("已洗稿")
