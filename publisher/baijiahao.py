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
            # TODO: browser automation via DrissionPage after account registration
            logger.warning("[baijiahao] automated publishing not yet connected - returning stub success")
            return True, ""
        except Exception as e:
            logger.error(f"[baijiahao] publish failed: {e}")
            return False, str(e)
