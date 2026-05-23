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
