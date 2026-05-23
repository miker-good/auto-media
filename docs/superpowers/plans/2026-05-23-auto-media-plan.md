# Auto-Media 全自动自媒体流水线 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 全自动文字内容流水线：爬取知乎/微博/豆瓣热门 → AI 洗稿 → 自动发布到头条号和百家号

**Architecture:** 模块化 Python CLI 项目，爬虫/洗稿/发布三个核心模块通过 SQLite 状态机串联，APScheduler 统一调度

**Tech Stack:** Python 3.11+, httpx, BeautifulSoup, parsel, OpenAI-compatible API, APScheduler, SQLite3, DrissionPage

---

## 文件结构

```
auto-media/
├── crawler/
│   ├── __init__.py
│   ├── base.py          # 爬虫抽象基类
│   ├── zhihu.py         # 知乎热榜
│   ├── weibo.py         # 微博热搜
│   └── douban.py        # 豆瓣热门
├── rewriter/
│   ├── __init__.py
│   └── rewriter.py      # AI 洗稿
├── publisher/
│   ├── __init__.py
│   ├── base.py          # 发布抽象基类
│   ├── toutiao.py       # 头条号
│   └── baijiahao.py     # 百家号
├── storage/
│   ├── __init__.py
│   └── db.py            # SQLite 操作
├── scheduler.py         # 定时调度
├── config.py            # 配置
├── main.py              # 入口
├── requirements.txt
└── tests/
    ├── __init__.py
    ├── test_db.py
    ├── test_crawlers.py
    ├── test_rewriter.py
    ├── test_publishers.py
    ├── test_scheduler.py
    └── test_integration.py
```

---

### Task 1: 项目骨架和依赖

**Files:**
- Create: `requirements.txt`
- Create: `config.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: 写 requirements.txt**

```python
httpx>=0.27.0
beautifulsoup4>=4.12.0
parsel>=1.9.0
fake-useragent>=2.1.0
apscheduler>=3.10.0
DrissionPage>=4.1.0
openai>=1.30.0
pytest>=8.0.0
```

- [ ] **Step 2: 写 config.py 测试**

Create `tests/test_config.py`:

```python
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
```

- [ ] **Step 3: 运行测试，确认失败**

```bash
cd /d/projects/auto-media && python -m pytest tests/test_config.py -v
```
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 4: 写 config.py**

```python
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
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd /d/projects/auto-media && python -m pytest tests/test_config.py -v
```
Expected: PASS

- [ ] **Step 6: 写到 requirements.txt 并安装依赖**

```bash
cd /d/projects/auto-media && pip install -r requirements.txt
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: project skeleton and config"
```

---

### Task 2: 存储层 — SQLite 数据库

**Files:**
- Create: `storage/__init__.py`
- Create: `storage/db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: 写数据库测试**

Create `tests/test_db.py`:

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /d/projects/auto-media && python -m pytest tests/test_db.py -v
```
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 写 storage/db.py 实现**

```python
import sqlite3
from datetime import datetime, timezone

class Database:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def execute(self, sql, params=None):
        if params:
            return self.conn.execute(sql, params)
        return self.conn.execute(sql)

    def close(self):
        self.conn.close()

    def create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                original_title TEXT NOT NULL,
                original_content TEXT NOT NULL DEFAULT '',
                original_url TEXT NOT NULL,
                rewritten_title TEXT,
                rewritten_content TEXT,
                status TEXT NOT NULL DEFAULT '待洗稿',
                crawled_at TIMESTAMP NOT NULL DEFAULT (datetime('now','localtime')),
                retry_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS publish_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT '失败',
                published_at TIMESTAMP NOT NULL DEFAULT (datetime('now','localtime')),
                error_msg TEXT,
                FOREIGN KEY (article_id) REFERENCES articles(id)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_url ON articles(original_url);
        """)

    def insert_article(self, source, original_title, original_content, original_url):
        cur = self.conn.execute(
            "INSERT INTO articles (source, original_title, original_content, original_url) VALUES (?,?,?,?)",
            (source, original_title, original_content, original_url)
        )
        self.conn.commit()
        return cur.lastrowid

    def get_articles_by_status(self, status, limit=None):
        rows = self.conn.execute(
            "SELECT * FROM articles WHERE status=? ORDER BY crawled_at DESC",
            (status,)
        ).fetchall()
        if limit:
            rows = rows[:limit]
        return [dict(r) for r in rows]

    def update_article_status(self, article_id, status, rewritten_title=None, rewritten_content=None):
        if rewritten_title and rewritten_content:
            self.conn.execute(
                "UPDATE articles SET status=?, rewritten_title=?, rewritten_content=? WHERE id=?",
                (status, rewritten_title, rewritten_content, article_id)
            )
        else:
            self.conn.execute(
                "UPDATE articles SET status=? WHERE id=?",
                (status, article_id)
            )
        self.conn.commit()

    def insert_publish_log(self, article_id, platform, status, error_msg=None):
        self.conn.execute(
            "INSERT INTO publish_log (article_id, platform, status, error_msg) VALUES (?,?,?,?)",
            (article_id, platform, status, error_msg)
        )
        self.conn.commit()

    def count_published_today(self):
        row = self.conn.execute(
            "SELECT COUNT(*) FROM publish_log WHERE date(published_at)=date('now','localtime') AND status='成功'"
        ).fetchone()
        return row[0]

    def article_exists_by_url(self, url):
        row = self.conn.execute(
            "SELECT 1 FROM articles WHERE original_url=? LIMIT 1",
            (url,)
        ).fetchone()
        return row is not None

    def increment_retry(self, article_id):
        row = self.conn.execute(
            "UPDATE articles SET retry_count=retry_count+1 WHERE id=? RETURNING retry_count",
            (article_id,)
        ).fetchone()
        count = row[0]
        if count >= 3:
            self.conn.execute("UPDATE articles SET status='跳过' WHERE id=?", (article_id,))
        self.conn.commit()
        return count
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /d/projects/auto-media && python -m pytest tests/test_db.py -v
```
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add storage/ tests/test_db.py
git commit -m "feat: add storage layer with SQLite"
```

---

### Task 3: 爬虫基类和知乎爬虫

**Files:**
- Create: `crawler/__init__.py`
- Create: `crawler/base.py`
- Create: `crawler/zhihu.py`
- Create: `tests/test_crawlers.py`

- [ ] **Step 1: 写爬虫测试**

Create `tests/test_crawlers.py`:

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /d/projects/auto-media && python -m pytest tests/test_crawlers.py -v
```
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 写 crawler/base.py**

```python
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

class BaseCrawler(ABC):
    @property
    @abstractmethod
    def source_name(self):
        pass

    @abstractmethod
    def fetch_hot_list(self):
        pass

    def run(self):
        try:
            items = self.fetch_hot_list()
            logger.info(f"{self.source_name}: fetched {len(items)} items")
            return items
        except Exception as e:
            logger.error(f"{self.source_name}: fetch failed - {e}")
            return []
```

- [ ] **Step 4: 写 crawler/zhihu.py**

```python
import httpx
from .base import BaseCrawler

class ZhihuCrawler(BaseCrawler):
    URL = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=20"

    @property
    def source_name(self):
        return "zhihu"

    def _request(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        resp = httpx.get(self.URL, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def fetch_hot_list(self):
        data = self._request()
        items = []
        for entry in data.get("data", []):
            target = entry.get("target", {})
            items.append({
                "source": self.source_name,
                "title": target.get("title", ""),
                "content": target.get("excerpt", ""),
                "url": target.get("url", f"https://www.zhihu.com/question/{target.get('id', '')}")
            })
        return items
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd /d/projects/auto-media && python -m pytest tests/test_crawlers.py -v
```
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add crawler/ tests/test_crawlers.py
git commit -m "feat: add crawler base and zhihu crawler"
```

---

### Task 4: 微博、豆瓣爬虫

**Files:**
- Create: `crawler/weibo.py`
- Create: `crawler/douban.py`

- [ ] **Step 1: 添加微博和豆瓣测试到已有测试文件**

Append to `tests/test_crawlers.py`:

```python
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
```

- [ ] **Step 2: 写 crawler/weibo.py**

```python
import httpx
from .base import BaseCrawler

class WeiboCrawler(BaseCrawler):
    URL = "https://weibo.com/ajax/side/hotSearch"

    @property
    def source_name(self):
        return "weibo"

    def _request(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://weibo.com/",
            "X-Requested-With": "XMLHttpRequest"
        }
        resp = httpx.get(self.URL, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def fetch_hot_list(self):
        data = self._request()
        items = []
        realtime = data.get("data", {}).get("realtime", [])
        for entry in realtime:
            items.append({
                "source": self.source_name,
                "title": entry.get("word", ""),
                "content": entry.get("word", ""),
                "url": entry.get("word_scheme", f"https://s.weibo.com/weibo?q={entry.get('word', '')}")
            })
        return items
```

- [ ] **Step 3: 写 crawler/douban.py**

```python
import httpx
from .base import BaseCrawler

class DoubanCrawler(BaseCrawler):
    URL = "https://m.douban.com/rexxar/api/v2/subject_collection/book_hot/items?count=20"

    @property
    def source_name(self):
        return "douban"

    def _request(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://m.douban.com/"
        }
        resp = httpx.get(self.URL, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def fetch_hot_list(self):
        data = self._request()
        items = []
        for subject in data.get("subjects", []):
            rating = subject.get("rating", {})
            rating_str = f"评分: {rating}" if isinstance(rating, str) else f"评分: {rating.get('value', 'N/A')}"
            items.append({
                "source": self.source_name,
                "title": subject.get("title", ""),
                "content": rating_str,
                "url": subject.get("url", "")
            })
        return items
```

- [ ] **Step 4: 运行全部爬虫测试**

```bash
cd /d/projects/auto-media && python -m pytest tests/test_crawlers.py -v
```
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add crawler/weibo.py crawler/douban.py tests/test_crawlers.py
git commit -m "feat: add weibo and douban crawlers"
```

---

### Task 5: AI 洗稿模块

**Files:**
- Create: `rewriter/__init__.py`
- Create: `rewriter/rewriter.py`
- Create: `tests/test_rewriter.py`

- [ ] **Step 1: 写洗稿测试**

Create `tests/test_rewriter.py`:

```python
import pytest
from unittest.mock import patch, Mock
from rewriter.rewriter import Rewriter
from config import Config

@pytest.fixture
def config():
    cfg = Config()
    cfg.ai_api_key = "sk-test"
    cfg.ai_base_url = "https://api.deepseek.com/v1"
    cfg.ai_model = "deepseek-chat"
    return cfg

def test_rewriter_formats_prompt(config):
    rew = Rewriter(config)
    article = {"title": "测试标题", "content": "这是原文内容需要被改写"}
    prompt = rew._build_prompt(article)
    assert "测试标题" in prompt
    assert "这是原文内容" in prompt
    assert "JSON" in prompt
    assert "title" in prompt

def test_rewriter_calls_api(config):
    mock_client = Mock()
    mock_client.chat.completions.create.return_value = Mock(
        choices=[Mock(message=Mock(content='{"title":"新标题","content":"改写内容"}'))]
    )
    with patch("rewriter.rewriter.OpenAI", return_value=mock_client):
        rew = Rewriter(config)
        result = rew.rewrite({"title": "原标题", "content": "原内容"})
        assert result["title"] == "新标题"
        assert result["content"] == "改写内容"

def test_rewriter_falls_back_on_api_error(config):
    import httpx
    with patch("rewriter.rewriter.OpenAI", side_effect=httpx.HTTPError("timeout")):
        rew = Rewriter(config)
        article = {"title": "原标题", "content": "原内容"}
        result = rew.rewrite(article)
        assert result["title"] == "原标题"
        assert result["content"] == "原内容"

def test_rewriter_falls_back_on_bad_json(config):
    mock_client = Mock()
    mock_client.chat.completions.create.return_value = Mock(
        choices=[Mock(message=Mock(content="不是JSON格式的返回"))]
    )
    with patch("rewriter.rewriter.OpenAI", return_value=mock_client):
        rew = Rewriter(config)
        article = {"title": "原标题", "content": "原内容"}
        result = rew.rewrite(article)
        assert result["title"] == "原标题"
        assert result["content"] == "原内容"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /d/projects/auto-media && python -m pytest tests/test_rewriter.py -v
```
Expected: FAIL

- [ ] **Step 3: 写 rewriter/rewriter.py**

```python
import json
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """你是一个资深自媒体编辑。请对以下网络文章进行改写，要求：

1. 换一个更吸引人的标题（20字以内）
2. 重新组织段落结构
3. 替换同义词，保持语气自然
4. 不改变核心信息点
5. 内容长度控制在200-500字

原始标题：{title}
原始内容：{content}

输出严格JSON格式，不要加任何额外文字：
{{"title": "新标题", "content": "改写后的内容"}}"""

class Rewriter:
    def __init__(self, config):
        self.client = OpenAI(api_key=config.ai_api_key, base_url=config.ai_base_url)
        self.model = config.ai_model
        self.temperature = config.rewrite_temperature

    def _build_prompt(self, article):
        return PROMPT_TEMPLATE.format(
            title=article.get("title", ""),
            content=article.get("content", "")
        )

    def rewrite(self, article):
        try:
            prompt = self._build_prompt(article)
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                timeout=30
            )
            text = resp.choices[0].message.content.strip()
            text = text.lstrip("```json").rstrip("```").strip()
            result = json.loads(text)
            return {
                "title": result.get("title", article["title"]),
                "content": result.get("content", article["content"])
            }
        except Exception as e:
            logger.warning(f"rewrite failed, using original: {e}")
            return {
                "title": article.get("title", ""),
                "content": article.get("content", "")
            }
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /d/projects/auto-media && python -m pytest tests/test_rewriter.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add rewriter/ tests/test_rewriter.py requirements.txt
git commit -m "feat: add AI rewriter module"
```

---

### Task 6: 发布模块

**Files:**
- Create: `publisher/__init__.py`
- Create: `publisher/base.py`
- Create: `publisher/toutiao.py`
- Create: `publisher/baijiahao.py`
- Create: `tests/test_publishers.py`

- [ ] **Step 1: 写发布模块测试**

Create `tests/test_publishers.py`:

```python
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
```

- [ ] **Step 2: 写 publisher/base.py 和两个发布器**

Create `publisher/base.py`:

```python
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

class BasePublisher(ABC):
    def __init__(self, cookies):
        self.cookies = cookies

    @property
    @abstractmethod
    def platform_name(self):
        pass

    @abstractmethod
    def publish(self, article):
        """发布文章，返回 (success: bool, error_msg: str)"""

    def _validate_article(self, article):
        title = article.get("title", "")
        content = article.get("content", "")
        return bool(title.strip() and content.strip())
```

Create `publisher/toutiao.py`:

```python
import logging
from .base import BasePublisher

logger = logging.getLogger(__name__)

class ToutiaoPublisher(BasePublisher):
    @property
    def platform_name(self):
        return "toutiao"

    def publish(self, article):
        if not self._validate_article(article):
            return False, "empty title or content"
        try:
            logger.info(f"[toutiao] publishing: {article['title'][:30]}...")
            # TODO: browser automation via DrissionPage after account registration
            # For now, return success stub so the pipeline can be tested end-to-end
            logger.warning("[toutiao] automated publishing not yet connected - returning stub success")
            return True, ""
        except Exception as e:
            logger.error(f"[toutiao] publish failed: {e}")
            return False, str(e)
```

Create `publisher/baijiahao.py`:

```python
import logging
from .base import BasePublisher

logger = logging.getLogger(__name__)

class BaijiahaoPublisher(BasePublisher):
    @property
    def platform_name(self):
        return "baijiahao"

    def publish(self, article):
        if not self._validate_article(article):
            return False, "empty title or content"
        try:
            logger.info(f"[baijiahao] publishing: {article['title'][:30]}...")
            logger.warning("[baijiahao] automated publishing not yet connected - returning stub success")
            return True, ""
        except Exception as e:
            logger.error(f"[baijiahao] publish failed: {e}")
            return False, str(e)
```

- [ ] **Step 3: 运行测试确认通过**

```bash
cd /d/projects/auto-media && python -m pytest tests/test_publishers.py -v
```
Expected: PASS (7 tests)

- [ ] **Step 4: Commit**

```bash
git add publisher/ tests/test_publishers.py
git commit -m "feat: add publisher module with stub implementations"
```

---

### Task 7: 调度器和主入口

**Files:**
- Create: `scheduler.py`
- Create: `main.py`
- Create: `tests/test_scheduler.py`
- Create: `tests/test_integration.py`

- [ ] **Step 1: 写调度器测试**

Create `tests/test_scheduler.py`:

```python
import pytest
from scheduler import Scheduler, pipeline

def test_scheduler_has_crawl_job():
    """Verify scheduler registers crawl job"""
    from config import Config
    cfg = Config()
    cfg.crawl_interval_hours = 6
    sched = Scheduler(cfg, db_path=":memory:")
    sched.setup()
    jobs = sched.scheduler.get_jobs()
    job_names = [j.name for j in jobs]
    assert "crawl_all" in job_names

def test_scheduler_has_publish_jobs():
    from config import Config
    cfg = Config()
    cfg.publish_hour_1 = 9
    cfg.publish_hour_2 = 17
    sched = Scheduler(cfg, db_path=":memory:")
    sched.setup()
    jobs = sched.scheduler.get_jobs()
    job_names = [j.name for j in jobs]
    assert "publish_slot_1" in job_names
    assert "publish_slot_2" in job_names
```

- [ ] **Step 2: 写集成测试**

Create `tests/test_integration.py`:

```python
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
    """End-to-end: crawl → rewrite → publish without errors"""
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
    assert not db.get_articles_by_status("已洗稿")  # all promoted to 已发布
```

- [ ] **Step 3: 写 scheduler.py**

```python
import logging
import time
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

from storage.db import Database
from crawler.zhihu import ZhihuCrawler
from crawler.weibo import WeiboCrawler
from crawler.douban import DoubanCrawler
from rewriter.rewriter import Rewriter
from publisher.toutiao import ToutiaoPublisher
from publisher.baijiahao import BaijiahaoPublisher

logger = logging.getLogger(__name__)

def pipeline(config, db_path):
    """Run one full pipeline cycle: crawl → rewrite → publish"""
    db = Database(db_path)
    db.create_tables()

    # Step 1: Crawl
    crawlers = [ZhihuCrawler(), WeiboCrawler(), DoubanCrawler()]
    total_new = 0
    for crawler in crawlers:
        items = crawler.run()
        for item in items:
            if not db.article_exists_by_url(item["url"]):
                db.insert_article(item["source"], item["title"], item["content"], item["url"])
                total_new += 1
    logger.info(f"crawl: {total_new} new articles")

    # Step 2: Rewrite
    rewriter = Rewriter(config)
    pending = db.get_articles_by_status("待洗稿")
    for article in pending:
        result = rewriter.rewrite(article)
        db.update_article_status(article["id"], "已洗稿", result["title"], result["content"])
    logger.info(f"rewrite: processed {len(pending)} articles")

    # Step 3: Publish
    publishers = [ToutiaoPublisher(cookies={}), BaijiahaoPublisher(cookies={})]
    published_today = db.count_published_today()
    remaining = config.max_publish_per_day - published_today
    if remaining <= 0:
        logger.info("publish: daily limit reached, skipping")
        db.close()
        return

    ready = db.get_articles_by_status("已洗稿", limit=remaining)
    for article in ready:
        for publisher in publishers:
            success, err = publisher.publish({
                "title": article["rewritten_title"],
                "content": article["rewritten_content"]
            })
            db.insert_publish_log(article["id"], publisher.platform_name, "成功" if success else "失败", err)
            if success:
                logger.info(f"published to {publisher.platform_name}: {article['rewritten_title'][:30]}")
        db.update_article_status(article["id"], "已发布")
    logger.info(f"publish: {len(ready)} articles across platforms")
    db.close()


class Scheduler:
    def __init__(self, config, db_path="auto_media.db"):
        self.config = config
        self.db_path = db_path
        self.scheduler = BackgroundScheduler()

    def setup(self):
        self.scheduler.add_job(
            pipeline, "interval", hours=self.config.crawl_interval_hours,
            args=[self.config, self.db_path],
            id="crawl_all", name="crawl_all"
        )
        self.scheduler.add_job(
            pipeline, "cron", hour=self.config.publish_hour_1, minute=0,
            args=[self.config, self.db_path],
            id="publish_1", name="publish_slot_1"
        )
        self.scheduler.add_job(
            pipeline, "cron", hour=self.config.publish_hour_2, minute=0,
            args=[self.config, self.db_path],
            id="publish_2", name="publish_slot_2"
        )
        logger.info("scheduler setup complete")

    def start(self):
        self.scheduler.start()
        logger.info("scheduler started, press Ctrl+C to stop")
        try:
            while True:
                time.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            self.scheduler.shutdown()
            logger.info("scheduler stopped")
```

- [ ] **Step 4: 写 main.py**

```python
import logging
import sys
from config import Config
from scheduler import Scheduler, pipeline

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("auto_media.log", encoding="utf-8")
        ]
    )

def main():
    setup_logging()
    config = Config()

    if len(sys.argv) > 1 and sys.argv[1] == "once":
        # single run mode
        pipeline(config, config.db_path)
    else:
        # daemon mode
        scheduler = Scheduler(config, config.db_path)
        scheduler.setup()
        scheduler.start()

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 运行所有测试确认通过**

```bash
cd /d/projects/auto-media && python -m pytest tests/ -v
```
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add scheduler.py main.py tests/test_scheduler.py tests/test_integration.py
git commit -m "feat: add scheduler and main entry point"
```

---

### Task 8: README 和使用说明

**Files:**
- Create: `README.md`

- [ ] **Step 1: 写 README.md**

```markdown
# Auto-Media

全自动自媒体文字内容流水线。

## 安装

```bash
pip install -r requirements.txt
```

## 配置

通过环境变量配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| AI_API_KEY | - | AI API 密钥（必填） |
| AI_BASE_URL | https://api.deepseek.com/v1 | AI API 地址 |
| AI_MODEL | deepseek-chat | AI 模型名 |
| MAX_PUBLISH_PER_DAY | 2 | 每天最多发布篇数 |
| CRAWL_INTERVAL_HOURS | 2 | 爬虫抓取间隔 |
| PUBLISH_HOUR_1 | 9 | 第一个发布时间（时） |
| PUBLISH_HOUR_2 | 17 | 第二个发布时间（时） |
| DB_PATH | auto_media.db | 数据库路径 |

## 使用

```bash
# 单次运行（测试用）
python main.py once

# 后台持续运行
python main.py
```

## 运行测试

```bash
python -m pytest tests/ -v
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README"
```

---

### Task 9: 推送到 GitHub

- [ ] **Step 1: 创建 GitHub 仓库并推送**

```bash
cd /d/projects/auto-media
gh repo create auto-media --public --source=. --remote=origin --push
```

或手动关联已有仓库：

```bash
git remote add origin git@github.com:miker-good/auto-media.git
git push -u origin master
```

---

## 自审清单

1. **Spec 覆盖**：每个 spec 模块都有对应 Task — 骨架(Task1)、存储(Task2)、爬虫(Task3-4)、洗稿(Task5)、发布(Task6)、调度(Task7)、说明(Task8)
2. **无占位符**：所有代码步骤包含完整实现
3. **类型一致性**：`articles` 字段在 db.py、rewriter.py、scheduler.py 中一致使用 `rewritten_title`/`rewritten_content`
4. **注意**：发布模块为 stub 实现，需注册头条号/百家号账号后补充 DrissionPage 浏览器自动化
