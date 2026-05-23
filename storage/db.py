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
