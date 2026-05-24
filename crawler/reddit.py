import httpx
from .base import BaseCrawler


class RedditCrawler(BaseCrawler):
    URL = "https://www.reddit.com/r/all/hot.json?limit=25"

    @property
    def source_name(self):
        return "reddit"

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
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            title = post.get("title", "")
            selftext = post.get("selftext", "")
            thumbnail = post.get("thumbnail", "")
            # Combine title + selftext for content
            content = selftext[:500] if selftext else title
            image_url = ""
            if thumbnail and thumbnail.startswith("https"):
                image_url = thumbnail
            # Skip stickied posts
            if post.get("stickied"):
                continue
            items.append({
                "source": self.source_name,
                "title": title,
                "content": content,
                "url": f"https://www.reddit.com{post.get('permalink', '')}",
                "image_url": image_url
            })
        return items
