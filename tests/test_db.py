import os
import pytest
from storage.db import Database


@pytest.fixture
def db():
    db = Database(":memory:")
    yield db
    db.close()


def test_create_tables(db):
    db.create_tables()
    tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = [t[0] for t in tables]
    assert "articles" in names
    assert "publish_log" in names


def test_insert_article(db):
    db.create_tables()
    aid = db.insert_article(
        source="zhihu",
        original_title="Test Title",
        original_content="Test content here",
        original_url="https://example.com/test"
    )
    assert aid == 1
    row = db.execute("SELECT * FROM articles WHERE id=?", (aid,)).fetchone()
    assert row["source"] == "zhihu"
    assert row["status"] == "待洗稿"
    assert row["retry_count"] == 0


def test_get_articles_by_status(db):
    db.create_tables()
    db.insert_article("zhihu", "A", "content", "url1")
    db.insert_article("weibo", "B", "content", "url2")
    db.update_article_status(1, "已洗稿")
    pending = db.get_articles_by_status("待洗稿")
    assert len(pending) == 1
    assert pending[0]["original_title"] == "B"
    rewritten = db.get_articles_by_status("已洗稿")
    assert len(rewritten) == 1
    assert rewritten[0]["original_title"] == "A"


def test_update_article_status(db):
    db.create_tables()
    db.insert_article("zhihu", "A", "content", "url1")
    db.update_article_status(1, "已洗稿", rewritten_title="New Title", rewritten_content="New Content")
    row = db.execute("SELECT * FROM articles WHERE id=1").fetchone()
    assert row["status"] == "已洗稿"
    assert row["rewritten_title"] == "New Title"
    assert row["rewritten_content"] == "New Content"


def test_insert_publish_log(db):
    db.create_tables()
    db.insert_article("zhihu", "A", "content", "url1")
    db.insert_publish_log(article_id=1, platform="toutiao", status="成功")
    log = db.execute("SELECT * FROM publish_log WHERE article_id=1").fetchone()
    assert log["platform"] == "toutiao"


def test_count_published_today(db):
    db.create_tables()
    db.insert_article("zhihu", "A", "content", "url1")
    db.insert_publish_log(1, "toutiao", "成功")
    db.insert_publish_log(1, "baijiahao", "成功")
    count = db.count_published_today()
    assert count == 2


def test_article_exists_by_url(db):
    db.create_tables()
    db.insert_article("zhihu", "A", "content", "https://example.com/1")
    assert db.article_exists_by_url("https://example.com/1") is True
    assert db.article_exists_by_url("https://example.com/2") is False


def test_mark_skipped_after_retries(db):
    db.create_tables()
    db.insert_article("zhihu", "A", "content", "url1")
    for _ in range(3):
        count = db.increment_retry(1)
    assert count == 3
    row = db.execute("SELECT status FROM articles WHERE id=1").fetchone()
    assert row["status"] == "跳过"
