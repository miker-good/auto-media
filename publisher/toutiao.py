import json
import logging
import os
import time
from DrissionPage import ChromiumPage
from .base import BasePublisher

logger = logging.getLogger(__name__)

COOKIE_FILE = "toutiao_cookies.json"
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"


class ToutiaoPublisher(BasePublisher):
    @property
    def platform_name(self):
        return "toutiao"

    def _load_cookies(self):
        if not os.path.exists(COOKIE_FILE):
            return None
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def _fill_content(self, page, article):
        title = article["title"]
        content = article["content"]

        # 填标题
        title_input = page.ele("css:textarea[placeholder*='标题']", timeout=5)
        if not title_input:
            title_input = page.ele("css:[class*='title'] textarea", timeout=5)
        if not title_input:
            title_input = page.ele("css:input[placeholder*='标题']", timeout=5)
        if title_input:
            title_input.input(title)
            time.sleep(0.5)
        else:
            return False, "找不到标题输入框，头条后台可能改版了"

        # 填正文 — 头条用 contenteditable div 或 iframe
        content_area = page.ele("css:[contenteditable='true']", timeout=5)
        if not content_area:
            content_area = page.ele("css:.editor-rich-text", timeout=5)
        if not content_area:
            content_area = page.ele("css:.ql-editor", timeout=5)
        if not content_area:
            iframe = page.ele("tag:iframe", timeout=3)
            if iframe:
                page.to_frame(iframe)
                content_area = page.ele("css:body", timeout=3)

        if content_area:
            # 逐段填入
            paragraphs = content.split("\n")
            for i, para in enumerate(paragraphs):
                if not para.strip():
                    continue
                content_area.input(para.strip())
                if i < len(paragraphs) - 1:
                    page.actions.key_down("ENTER").key_up("ENTER")
                time.sleep(0.3)
        else:
            return False, "找不到正文输入区域，头条后台可能改版了"

        return True, ""

    def _click_publish(self, page):
        # 找发布按钮，可能先需要点"预览并发布"再点"发布"
        btn = page.ele("css:button:contains('发布')", timeout=3)
        if not btn:
            btn = page.ele("css:span:contains('发布')", timeout=3)
        if not btn:
            btn = page.ele("css:[class*='publish'] button", timeout=3)
        if btn:
            btn.click()
            time.sleep(1)
            # 看看有没有确认弹窗
            confirm = page.ele("css:button:contains('确认')", timeout=2)
            if not confirm:
                confirm = page.ele("css:button:contains('确定')", timeout=2)
            if confirm:
                confirm.click()
                time.sleep(1)
            return True
        return False

    def publish(self, article):
        if not self._validate_article(article):
            return False, "empty title or content"

        cookies = self._load_cookies()
        if not cookies:
            return False, "no cookies found — run login_toutiao.py first"

        try:
            logger.info(f"[toutiao] publishing: {article['title'][:30]}...")
            page = ChromiumPage()
            for c in cookies:
                try:
                    page.set.cookies(c)
                except Exception:
                    pass

            page.get(PUBLISH_URL)
            time.sleep(3)

            ok, err = self._fill_content(page, article)
            if not ok:
                page.quit()
                return False, err

            # 点封面图可以跳过（头条会自动生成默认封面）
            time.sleep(2)
            published = self._click_publish(page)
            time.sleep(2)
            page.quit()

            if published:
                logger.info(f"[toutiao] published: {article['title'][:30]}")
                return True, ""
            else:
                return False, "could not find publish button"

        except Exception as e:
            logger.error(f"[toutiao] publish failed: {e}")
            return False, str(e)
