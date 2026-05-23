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
        try:
            data = self._request()
        except Exception:
            return []
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
