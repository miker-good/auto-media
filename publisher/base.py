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
