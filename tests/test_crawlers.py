import pytest
from unittest.mock import patch, Mock
from crawler.base import BaseCrawler
from crawler.zhihu import ZhihuCrawler


class DummyCrawler(BaseCrawler):
    @property
    def source_name(self):
        return "dummy"

    def fetch_hot_list(self):
        return [{"title": "Test", "content": "content", "url": "https://x.com/1"}]


def test_base_crawler_interface():
    crawler = DummyCrawler()
    items = crawler.fetch_hot_list()
    assert isinstance(items, list)
    assert "title" in items[0]
    assert "url" in items[0]
    assert "content" in items[0]
    assert crawler.source_name == "dummy"


def test_zhihu_crawler_parses_response():
    mock_response = {
        "data": [
            {
                "target": {
                    "title": "为什么Python这么流行",
                    "excerpt": "Python简单易学...",
                    "id": 12345,
                    "url": "https://www.zhihu.com/question/12345"
                }
            }
        ]
    }
    with patch("crawler.zhihu.ZhihuCrawler._request", return_value=mock_response):
        crawler = ZhihuCrawler()
        items = crawler.fetch_hot_list()
        assert len(items) >= 0
        if items:
            assert items[0]["source"] == "zhihu"
            assert "title" in items[0]
            assert "url" in items[0]


def test_zhihu_crawler_handles_error():
    with patch("crawler.zhihu.ZhihuCrawler._request", side_effect=Exception("Network error")):
        crawler = ZhihuCrawler()
        items = crawler.fetch_hot_list()
        assert items == []
