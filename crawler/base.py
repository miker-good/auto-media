from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class BaseCrawler(ABC):
    @property
    @abstractmethod
    def source_name(self):
        pass

    @abstractmethod
    def fetch_hot_list(self):
        pass

    def run(self):
        try:
            items = self.fetch_hot_list()
            logger.info(f"{self.source_name}: fetched {len(items)} items")
            return items
        except Exception as e:
            logger.error(f"{self.source_name}: fetch failed - {e}")
            return []
