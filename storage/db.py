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
                original_image_url TEXT NOT NULL DEFAULT '',
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

    def insert_article(self, source, original_title, original_content, original_url, original_image_url=""):
        cur = self.conn.execute(
            "INSERT INTO articles (source, original_title, original_content, original_url, original_image_url) VALUES (?,?,?,?,?)",
            (source, original_title, original_content, original_url, original_image_url)
        )
        self.conn.commit()
        return cur.lastrowid

    def get_articles_by_status(self, status, limit=None):
        query = "SELECT * FROM articles WHERE status=? ORDER BY crawled_at DESC"
        params = [status]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def update_article_status(self, article_id, status, rewritten_title=None, rewritten_content=None, image_url=None):
        fields = ["status=?"]
        values = [status]
        if rewritten_title is not None:
            fields.append("rewritten_title=?")
            values.append(rewritten_title)
        if rewritten_content is not None:
            fields.append("rewritten_content=?")
            values.append(rewritten_content)
        if image_url is not None:
            fields.append("original_image_url=?")
            values.append(image_url)
        values.append(article_id)
        self.conn.execute(
            f"UPDATE articles SET {', '.join(fields)} WHERE id=?",
            values
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
            "SELECT COUNT(DISTINCT article_id) FROM publish_log WHERE date(published_at)=date('now','localtime') AND status='成功'"
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
