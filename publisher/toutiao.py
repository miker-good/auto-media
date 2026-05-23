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
            logger.warning("[toutiao] automated publishing not yet connected - returning stub success")
            return True, ""
        except Exception as e:
            logger.error(f"[toutiao] publish failed: {e}")
            return False, str(e)
