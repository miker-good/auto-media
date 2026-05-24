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
        try:
            data = self._request()
        except Exception:
            return []
        items = []
        realtime = data.get("data", {}).get("realtime", [])
        for entry in realtime:
            items.append({
                "source": self.source_name,
                "title": entry.get("word", ""),
                "content": entry.get("word", ""),
                "url": entry.get("word_scheme", f"https://s.weibo.com/weibo?q={entry.get('word', '')}"),
                "image_url": entry.get("icon", "")
            })
        return items
