import httpx
import logging
from .base import BaseCrawler

logger = logging.getLogger(__name__)


class HackerNewsCrawler(BaseCrawler):
    TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
    ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"

    @property
    def source_name(self):
        return "hackernews"

    def fetch_hot_list(self):
        try:
            # Get top story IDs
            resp = httpx.get(self.TOP_URL, timeout=15)
            resp.raise_for_status()
            ids = resp.json()[:20]
        except Exception as e:
            logger.error(f"hackernews: fetch top IDs failed - {e}")
            return []

        # Fetch each story detail (in parallel batches of 5)
        items = []
        for story_id in ids:
            try:
                r = httpx.get(self.ITEM_URL.format(story_id), timeout=10)
                r.raise_for_status()
                story = r.json()
                title = story.get("title", "")
                url = story.get("url", f"https://news.ycombinator.com/item?id={story_id}")
                text = story.get("text", "")
                # HN stories are mostly links; use title as content
                content = text[:500] if text else title
                items.append({
                    "source": self.source_name,
                    "title": title,
                    "content": content,
                    "url": url,
                    "image_url": ""
                })
            except Exception as e:
                logger.warning(f"hackernews: fetch item {story_id} failed - {e}")
                continue

        return items
