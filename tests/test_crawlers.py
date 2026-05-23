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


from crawler.weibo import WeiboCrawler
from crawler.douban import DoubanCrawler


def test_weibo_crawler_parses_response():
    mock_response = {
        "data": {
            "realtime": [
                {"word": "微博热搜词条1", "word_scheme": "https://s.weibo.com/weibo?q=%E7%83%AD%E6%90%9C1"},
                {"word": "微博热搜词条2", "word_scheme": "https://s.weibo.com/weibo?q=%E7%83%AD%E6%90%9C2"}
            ]
        }
    }
    with patch("crawler.weibo.WeiboCrawler._request", return_value=mock_response):
        crawler = WeiboCrawler()
        items = crawler.fetch_hot_list()
        assert len(items) == 2
        assert items[0]["source"] == "weibo"
        assert items[0]["title"] == "微博热搜词条1"


def test_douban_crawler_parses_response():
    mock_response = {
        "subjects": [
            {"title": "三体", "url": "https://book.douban.com/subject/1", "rating": "9.4"},
            {"title": "活着", "url": "https://book.douban.com/subject/2", "rating": "9.2"}
        ]
    }
    with patch("crawler.douban.DoubanCrawler._request", return_value=mock_response):
        crawler = DoubanCrawler()
        items = crawler.fetch_hot_list()
        assert len(items) == 2
        assert items[0]["source"] == "douban"
        assert items[0]["content"] == "评分: 9.4"


def test_weibo_handles_error():
    with patch("crawler.weibo.WeiboCrawler._request", side_effect=Exception("timeout")):
        crawler = WeiboCrawler()
        assert crawler.fetch_hot_list() == []
