import json
import logging
import time
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

from storage.db import Database
from crawler.zhihu import ZhihuCrawler
from crawler.weibo import WeiboCrawler
from crawler.douban import DoubanCrawler
from crawler.reddit import RedditCrawler
from crawler.hackernews import HackerNewsCrawler
from rewriter.rewriter import Rewriter
from publisher.toutiao import ToutiaoPublisher
from publisher.baijiahao import BaijiahaoPublisher

logger = logging.getLogger(__name__)


def pipeline(config, db_path):
    """Run one full pipeline cycle: crawl -> rewrite -> publish"""
    db = Database(db_path)
    db.create_tables()

    # Step 1: Crawl
    crawlers = [ZhihuCrawler(), WeiboCrawler(), DoubanCrawler(), RedditCrawler(), HackerNewsCrawler()]
    total_new = 0
    for crawler in crawlers:
        items = crawler.run()
        for item in items:
            if not db.article_exists_by_url(item["url"]):
                db.insert_article(item["source"], item["title"], item["content"], item["url"], item.get("image_url", ""))
                total_new += 1
    logger.info(f"crawl: {total_new} new articles")

    # Step 2: Rewrite
    rewriter = Rewriter(config)
    pending = db.get_articles_by_status("待洗稿")
    for article in pending:
        result = rewriter.rewrite(article)
        img_queries = result.get("image_queries", [])
        extra_img = article.get("original_image_url", "")
        # If EN rewrite generated image queries, store as JSON in image_url field
        if img_queries:
            extra_img = json.dumps(img_queries, ensure_ascii=False)
        db.update_article_status(article["id"], "已洗稿", result["title"], result["content"], extra_img)
    logger.info(f"rewrite: processed {len(pending)} articles")

    # Step 3: Publish
    publishers = [ToutiaoPublisher(cookies={}), BaijiahaoPublisher(cookies={})]
    published_today = db.count_published_today()
    remaining = config.max_publish_per_day - published_today
    if remaining <= 0:
        logger.info("publish: daily limit reached, skipping")
        db.close()
        return

    ready = db.get_articles_by_status("已洗稿", limit=remaining)
    for article in ready:
        for publisher in publishers:
            success, err = publisher.publish({
                "title": article["rewritten_title"],
                "content": article["rewritten_content"],
                "image_url": article.get("original_image_url", "")
            })
            db.insert_publish_log(article["id"], publisher.platform_name, "成功" if success else "失败", err)
            if success:
                logger.info(f"published to {publisher.platform_name}: {article['rewritten_title'][:30]}")
        db.update_article_status(article["id"], "已发布")
    logger.info(f"publish: {len(ready)} articles across platforms")
    db.close()


class Scheduler:
    def __init__(self, config, db_path="auto_media.db"):
        self.config = config
        self.db_path = db_path
        self.scheduler = BackgroundScheduler()

    def setup(self):
        self.scheduler.add_job(
            pipeline, "interval", hours=self.config.crawl_interval_hours,
            args=[self.config, self.db_path],
            id="crawl_all", name="crawl_all"
        )
        self.scheduler.add_job(
            pipeline, "cron", hour=self.config.publish_hour_1, minute=0,
            args=[self.config, self.db_path],
            id="publish_1", name="publish_slot_1"
        )
        self.scheduler.add_job(
            pipeline, "cron", hour=self.config.publish_hour_2, minute=0,
            args=[self.config, self.db_path],
            id="publish_2", name="publish_slot_2"
        )
        logger.info("scheduler setup complete")

    def start(self):
        self.scheduler.start()
        logger.info("scheduler started, press Ctrl+C to stop")
        try:
            while True:
                time.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            self.scheduler.shutdown()
            logger.info("scheduler stopped")
