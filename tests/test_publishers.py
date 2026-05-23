import pytest
from publisher.toutiao import ToutiaoPublisher
from publisher.baijiahao import BaijiahaoPublisher


def test_toutiao_publisher_name():
    p = ToutiaoPublisher(cookies={})
    assert p.platform_name == "toutiao"


def test_baijiahao_publisher_name():
    p = BaijiahaoPublisher(cookies={})
    assert p.platform_name == "baijiahao"


def test_publisher_validate_article():
    p = ToutiaoPublisher(cookies={})
    article = {"title": "测试", "content": "内容"}
    assert p._validate_article(article) is True


def test_publisher_rejects_empty_article():
    p = ToutiaoPublisher(cookies={})
    assert p._validate_article({"title": "", "content": ""}) is False


def test_publisher_rejects_no_title():
    p = ToutiaoPublisher(cookies={})
    assert p._validate_article({"title": "", "content": "有内容"}) is False


def test_publisher_rejects_no_content():
    p = ToutiaoPublisher(cookies={})
    assert p._validate_article({"title": "有标题", "content": ""}) is False


def test_all_publishers_have_required_methods():
    for publisher_cls in [ToutiaoPublisher, BaijiahaoPublisher]:
        p = publisher_cls(cookies={})
        assert hasattr(p, "platform_name")
        assert hasattr(p, "publish")
        assert hasattr(p, "_validate_article")
