"""
Fill Toutiao editor with international article (pre-generated image_queries).
Usage: python fill_intl_article.py <article_id>
"""
import json
import logging
import os
import re
import sys
import time
import httpx
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
sys.stdout.reconfigure(encoding='utf-8')

COOKIE_FILE = "toutiao_cookies.json"
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
COVER_IMAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "default_cover.png")


def load_cookies():
    if not os.path.exists(COOKIE_FILE):
        logger.error("No cookies found")
        return None
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _is_bw(hex_color):
    c = hex_color.lstrip("#")
    if len(c) < 6:
        return False
    try:
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        return max(r, g, b) - min(r, g, b) < 15
    except ValueError:
        return False


def download_unsplash(query, filename, prefer_color=True):
    access_key = os.getenv("UNSPLASH_ACCESS_KEY", "")
    if not access_key:
        return None, None
    try:
        logger.info(f"Unsplash: {query}")
        resp = httpx.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": 5, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {access_key}"},
            timeout=15
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            logger.info(f"No results for '{query}'")
            return None, None

        image_url = None
        for r in results:
            url = r["urls"]["regular"]
            color = r.get("color", "#000000")
            if prefer_color and _is_bw(color):
                logger.info(f"Skipping B&W ({color}) for '{query}'")
                continue
            image_url = url
            break

        if not image_url:
            if prefer_color:
                logger.info(f"All {len(results)} B&W for '{query}', using first")
            image_url = results[0]["urls"]["regular"]

        local_dir = os.path.dirname(COVER_IMAGE)
        local_path = os.path.join(local_dir, filename)
        img_resp = httpx.get(image_url, timeout=30, follow_redirects=True)
        img_resp.raise_for_status()
        if len(img_resp.content) < 10000:
            logger.info(f"Image too small ({len(img_resp.content)} bytes)")
            return None, None
        with open(local_path, "wb") as f:
            f.write(img_resp.content)
        logger.info(f"Downloaded: {filename} ({len(img_resp.content)} bytes)")
        return local_path, image_url
    except Exception as e:
        logger.warning(f"Unsplash '{query}': {e}")
        return None, None


def main():
    article_id = int(sys.argv[1]) if len(sys.argv) > 1 else 174

    from storage.db import Database
    db = Database("auto_media.db")
    a = db.conn.execute(
        "SELECT id, rewritten_title, rewritten_content, original_image_url FROM articles WHERE id=?",
        (article_id,)
    ).fetchone()

    if not a:
        logger.error(f"Article #{article_id} not found")
        return 1

    title = a[1] or ""
    content = a[2] or ""
    image_queries = json.loads(a[3]) if a[3] else []

    print(f"\n{'='*60}")
    print(f"ARTICLE #{a[0]}")
    print(f"TITLE: {title}")
    print(f"CONTENT ({len(content)} chars):")
    paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
    for i, p in enumerate(paragraphs):
        print(f"  P{i+1}: {p[:100]}...")
    print(f"IMAGE QUERIES: {image_queries}")
    print(f"{'='*60}\n")

    # Step 1: Download images
    logger.info("--- Downloading images ---")
    seen_urls = set()

    # Cover: first query, prefer_color=True
    cover_path = None
    if image_queries:
        path, url = download_unsplash(image_queries[0], "temp_cover.jpg", prefer_color=True)
        if path and url:
            seen_urls.add(url)
            cover_path = path
            logger.info(f"Cover: {image_queries[0]}")

    # Inline: remaining queries
    inline_images = []
    for i, q in enumerate(image_queries[1:4]):
        path, url = download_unsplash(q, f"temp_inline_{i}.jpg", prefer_color=False)
        if path and url:
            if url in seen_urls:
                logger.info(f"Skipping duplicate for '{q}'")
                continue
            seen_urls.add(url)
            inline_images.append((path, url))
            logger.info(f"Inline {i}: {q}")

    if not cover_path and inline_images:
        cover_path = inline_images[0][0]
        inline_images = inline_images[1:]
    if not cover_path:
        cover_path = COVER_IMAGE if os.path.exists(COVER_IMAGE) else None

    logger.info(f"Cover: {bool(cover_path)}, Inline: {len(inline_images)}")

    # Step 2: Fill editor
    logger.info("--- Opening browser ---")
    from DrissionPage import ChromiumPage
    page = ChromiumPage()

    try:
        cookies = load_cookies()
        if not cookies:
            return 1

        for c in cookies:
            try:
                page.set.cookies(c)
            except Exception:
                pass

        page.get(PUBLISH_URL)
        time.sleep(8)
        logger.info("Editor loaded")

        # --- Upload cover ---
        if cover_path and os.path.exists(cover_path):
            logger.info("Uploading cover...")
            page.run_js('''
                (function() {
                    var labels = document.querySelectorAll('.article-cover-radio-group label');
                    for (var i = 0; i < labels.length; i++) {
                        if (labels[i].innerText.indexOf('单图') !== -1) {
                            labels[i].click(); return;
                        }
                    }
                    for (var i = 0; i < labels.length; i++) {
                        if (labels[i].innerText.indexOf('无封面') === -1) {
                            labels[i].click(); return;
                        }
                    }
                })();
            ''')
            time.sleep(1)

            page.run_js('''
                var el = document.querySelector(".article-cover-add")
                     || document.querySelector('[class*="cover-upload"]')
                     || document.querySelector('[class*="cover-wrap"]');
                if (el) { el.click(); }
            ''')
            time.sleep(2)

            for fel in page.eles('tag:input@type=file', timeout=5):
                try:
                    acc = fel.attr('accept') or ''
                    if 'image' in acc or not acc:
                        fel.input(cover_path)
                        logger.info("Cover file selected")
                        break
                except Exception as e:
                    pass

            page.run_js('''
                document.querySelectorAll('input[type="file"]').forEach(function(inp) {
                    inp.dispatchEvent(new Event('change', {bubbles: true, cancelable: true}));
                });
            ''')
            time.sleep(12)

            drawer = page.run_js('''
                var btns = document.querySelectorAll('.byte-drawer button, [class*="drawer"] button');
                for (var i = 0; i < btns.length; i++) {
                    var t = (btns[i].innerText || '').trim();
                    if ((t === '确定' || t === '确认') && btns[i].offsetParent !== null && !btns[i].disabled) {
                        btns[i].click(); return 'closed';
                    }
                }
                return 'not_closed';
            ''')
            logger.info(f"Drawer: {drawer}")
            time.sleep(2)
        else:
            logger.warning("No cover, selecting no-cover mode")
            page.run_js('''
                var labels = document.querySelectorAll('.article-cover-radio-group label');
                for (var i = 0; i < labels.length; i++) {
                    if (labels[i].innerText.indexOf('无封面') !== -1) {
                        labels[i].click(); break;
                    }
                }
            ''')
            time.sleep(1)

        # --- Fill title ---
        logger.info("Filling title...")
        page.run_js(f'''
            var el = document.querySelector('input[placeholder*="标题"], textarea[placeholder*="标题"]');
            if (el) {{
                var proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
                var desc = Object.getOwnPropertyDescriptor(proto, 'value');
                if (desc && desc.set) {{
                    desc.set.call(el, {json.dumps(title)});
                }} else {{
                    el.value = {json.dumps(title)};
                }}
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                el.dispatchEvent(new FocusEvent('focus', {{bubbles: true}}));
                el.dispatchEvent(new FocusEvent('blur', {{bubbles: true}}));
            }}
        ''')
        time.sleep(1)

        # --- Clear editor ---
        page.run_js('''
            var ed = document.querySelector('[contenteditable="true"]');
            if (ed) { ed.innerHTML = ''; }
        ''')
        time.sleep(0.5)

        # --- Helper functions ---
        def append_paragraph(page, text):
            # 检测小标题（**文字** 格式）→ 渲染为加粗大字
            is_heading = bool(re.match(r'^\*\*(.+)\*\*$', text))
            if is_heading:
                inner = text.strip('*')
                page.run_js(f'''
                    var ed = document.querySelector('[contenteditable="true"]');
                    ed.focus();
                    var range = document.createRange();
                    range.selectNodeContents(ed);
                    range.collapse(false);
                    var sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                    var p = document.createElement('p');
                    p.innerHTML = '<strong style="font-size:18px">' + {json.dumps(inner)} + '</strong>';
                    range.insertNode(p);
                    range.setStartAfter(p);
                    range.collapse(true);
                    sel.removeAllRanges();
                    sel.addRange(range);
                    ed.dispatchEvent(new Event('input', {{bubbles: true}}));
                ''')
            else:
                page.run_js(f'''
                    var ed = document.querySelector('[contenteditable="true"]');
                    ed.focus();
                    var range = document.createRange();
                    range.selectNodeContents(ed);
                    range.collapse(false);
                    var sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                    var p = document.createElement('p');
                    p.textContent = {json.dumps(text)};
                    range.insertNode(p);
                    range.setStartAfter(p);
                    range.collapse(true);
                    sel.removeAllRanges();
                    sel.addRange(range);
                    ed.dispatchEvent(new Event('input', {{bubbles: true}}));
                ''')

        def insert_image(page, local_path, label=""):
            # Click toolbar image button
            page.run_js('''
                var container = document.querySelector('.syl-toolbar-tool.image')
                             || document.querySelector('[class*="toolbar-tool"][class*="image"]');
                if (container) {
                    var btn = container.querySelector('button');
                    if (btn && btn.offsetParent !== null) { btn.click(); }
                }
            ''')
            time.sleep(1)

            for fel in page.eles('tag:input@type=file', timeout=5):
                try:
                    acc = fel.attr('accept') or ''
                    if 'image' in acc or not acc:
                        fel.input(local_path)
                        break
                except Exception:
                    continue

            page.run_js('''
                document.querySelectorAll('input[type="file"]').forEach(function(inp) {
                    inp.dispatchEvent(new Event('change', {bubbles: true, cancelable: true}));
                });
            ''')
            time.sleep(8)

            closed = page.run_js('''
                var btns = document.querySelectorAll('.byte-drawer button, [class*="drawer"] button, [class*="dialog"] button');
                for (var i = 0; i < btns.length; i++) {
                    var t = (btns[i].innerText || '').trim();
                    if ((t === '确定' || t === '确认') && btns[i].offsetParent !== null && !btns[i].disabled) {
                        btns[i].click(); return 'closed';
                    }
                }
                return 'not_closed';
            ''')
            logger.info(f"Image dialog: {closed}")
            time.sleep(2)

        # --- Progressive fill: paragraph → image → paragraph → image... ---
        img_idx = 0
        prev_was_heading = False
        for i, para in enumerate(paragraphs):
            logger.info(f"Writing P{i+1}: {para[:50]}...")
            append_paragraph(page, para)
            time.sleep(0.8)

            is_heading = bool(re.match(r'^\*\*(.+)\*\*$', para))
            is_last = (i == len(paragraphs) - 1)
            # 小标题后的正文段落 → 插入图片
            if not is_last and prev_was_heading and not is_heading and img_idx < len(inline_images):
                local_path, _ = inline_images[img_idx]
                logger.info(f"Inserting image {img_idx+1} after P{i+1}...")
                insert_image(page, local_path, f"img{img_idx+1}")
                img_idx += 1
            prev_was_heading = is_heading

        # Wait for autosave
        time.sleep(5)
        logger.info("\n*** EDITOR FILLED - READY FOR REVIEW ***")
        logger.info("*** BROWSER IS STILL OPEN ***")
        logger.info("*** Review the content and tell me to publish ***")
        logger.info("*** Waiting 180s before auto-close... ***")
        time.sleep(180)

    finally:
        try:
            page.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
