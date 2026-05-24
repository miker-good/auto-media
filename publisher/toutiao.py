"""
头条号发布器 — 浏览器 UI 自动化：上传封面 → 填内容 → 点发布
"""
import json
import logging
import os
import re
import time
import httpx
from dotenv import load_dotenv
from DrissionPage import ChromiumPage
from .base import BasePublisher

load_dotenv()
logger = logging.getLogger(__name__)

COOKIE_FILE = "toutiao_cookies.json"
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
COVER_IMAGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "default_cover.png")


class ToutiaoPublisher(BasePublisher):
    @property
    def platform_name(self):
        return "toutiao"

    def _load_cookies(self):
        if not os.path.exists(COOKIE_FILE):
            return None
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def _prepare_cover_image(self, image_url, article_title=""):
        """准备封面图：文章图 > Unsplash 搜索 > 本地 default_cover.png"""
        # 1. 优先用文章自带的图片（但跳过太小的图标/logo）
        if image_url:
            local_path = os.path.join(os.path.dirname(COVER_IMAGE), "temp_cover.png")
            try:
                logger.info(f"[toutiao] downloading cover from {image_url[:100]}...")
                resp = httpx.get(image_url, timeout=30, follow_redirects=True)
                resp.raise_for_status()
                if len(resp.content) < 20000:
                    logger.info(f"[toutiao] image too small ({len(resp.content)} bytes), skip to Unsplash")
                else:
                    with open(local_path, "wb") as f:
                        f.write(resp.content)
                    logger.info(f"[toutiao] cover downloaded: {len(resp.content)} bytes")
                    return local_path
            except Exception as e:
                logger.warning(f"[toutiao] download cover failed: {e}")

        # 2. Unsplash 搜索相关图片
        unsplash_path = self._search_unsplash(article_title)
        if unsplash_path:
            return unsplash_path

        # 3. Fallback
        if os.path.exists(COVER_IMAGE):
            return COVER_IMAGE
        return None

    def _ai_image_queries(self, title, content):
        """用 AI 根据文章标题+内容生成英文 Unsplash 搜索词"""
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=os.getenv("AI_API_KEY", ""),
                base_url=os.getenv("AI_BASE_URL", "https://api.deepseek.com/v1")
            )
            prompt = f"""Given this Chinese article, generate 3-4 English keyword phrases for searching Unsplash photos. Each phrase should be 2-5 words, descriptive, and visually searchable. Return ONLY a JSON array of strings.

Title: {title}
Content: {content[:500]}

Example output: ["urban night traffic", "technology workplace abstract", "nature mountain sunrise"]"""
            resp = client.chat.completions.create(
                model=os.getenv("AI_MODEL", "deepseek-chat"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                timeout=20
            )
            text = resp.choices[0].message.content.strip()
            text = text.lstrip("```json").rstrip("```").strip()
            start = text.find("[")
            end = text.rfind("]") + 1
            if start != -1 and end > start:
                keywords = json.loads(text[start:end])
                if isinstance(keywords, list) and len(keywords) > 0:
                    logger.info(f"[toutiao] AI queries: {keywords}")
                    return [k.strip() for k in keywords if k.strip()]
        except Exception as e:
            logger.warning(f"[toutiao] AI queries failed: {e}")
        return None

    @staticmethod
    def _is_bw(hex_color):
        """Check if a hex color is effectively grayscale (all RGB channels within 15)."""
        c = hex_color.lstrip("#")
        if len(c) < 6:
            return False
        try:
            r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
            return max(r, g, b) - min(r, g, b) < 15
        except ValueError:
            return False

    def _download_unsplash(self, query, filename, prefer_color=True):
        """从 Unsplash 搜索并下载一张图片，返回 (本地路径, Unsplash原始URL)"""
        access_key = os.getenv("UNSPLASH_ACCESS_KEY", "")
        if not access_key:
            return None, None
        try:
            logger.info(f"[toutiao] Unsplash search: {query}")
            resp = httpx.get(
                "https://api.unsplash.com/search/photos",
                params={"query": query, "per_page": 5, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {access_key}"},
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            if not results:
                logger.info(f"[toutiao] Unsplash '{query}': no results")
                return None, None

            image_url = None
            for r in results:
                url = r["urls"]["regular"]
                color = r.get("color", "#000000")
                if prefer_color and self._is_bw(color):
                    logger.info(f"[toutiao] skipping B&W (color={color}) for '{query}'")
                    continue
                image_url = url
                break

            if not image_url:
                if prefer_color:
                    logger.info(f"[toutiao] all {len(results)} results B&W for '{query}', using first")
                image_url = results[0]["urls"]["regular"]

            local_path = os.path.join(os.path.dirname(COVER_IMAGE), filename)
            img_resp = httpx.get(image_url, timeout=30, follow_redirects=True)
            img_resp.raise_for_status()
            if len(img_resp.content) < 10000:
                logger.info(f"[toutiao] image too small ({len(img_resp.content)} bytes)")
                return None, None
            with open(local_path, "wb") as f:
                f.write(img_resp.content)
            logger.info(f"[toutiao] downloaded: {filename} ({len(img_resp.content)} bytes)")
            return local_path, image_url
        except Exception as e:
            logger.warning(f"[toutiao] Unsplash '{query}': {e}")
            return None, None

    @staticmethod
    def _parse_image_queries(image_url):
        """如果 image_url 是 JSON 数组（EN改写预生成的搜索词），直接返回；否则返回 None"""
        if not image_url:
            return None
        try:
            parsed = json.loads(image_url)
            if isinstance(parsed, list) and len(parsed) > 0 and all(isinstance(x, str) for x in parsed):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        return None

    def _prepare_images(self, title, content, image_queries=None):
        """下载封面图+正文插图，返回 (cover_path, [(local_path, unsplash_url), ...])

        image_queries: 预生成的英文 Unsplash 搜索词列表（来自 EN→ZH 改写），
                       如果提供则跳过 AI 关键词生成步骤。
        """
        # 1. 获取搜索词：优先用预生成的，否则 AI 生成
        if image_queries:
            queries = image_queries
            logger.info(f"[toutiao] using pre-generated queries: {queries}")
        else:
            queries = self._ai_image_queries(title, content)
            if not queries:
                cn = self._extract_keywords(title)
                queries = [cn] if cn else []
                queries.extend(["technology abstract", "nature landscape"])

        # 2. 下载图片（封面用 prefer_color=True 过滤黑白，正文插图不限制）
        images = []
        seen_urls = set()
        for i, q in enumerate(queries[:4]):
            prefer_color = (i == 0)  # only filter B&W for cover
            path, url = self._download_unsplash(q, f"temp_img_{i}.jpg", prefer_color=prefer_color)
            if path and url:
                if url in seen_urls:
                    logger.info(f"[toutiao] skipping duplicate: {url[:80]}...")
                    continue
                seen_urls.add(url)
                images.append((path, url))

        if not images:
            cover = COVER_IMAGE if os.path.exists(COVER_IMAGE) else None
            return cover, []

        cover_path = images[0][0]
        inline_images = images[1:] if len(images) > 1 else []
        return cover_path, inline_images

    def _upload_to_toutiao_cdn(self, page, local_path):
        """将本地图片上传到头条 CDN，返回 CDN URL"""
        # 触发文件上传
        file_uploaded = False
        file_inputs = page.eles('tag:input@type=file', timeout=5)
        for fel in file_inputs:
            try:
                accept = fel.attr('accept') or ''
                if 'image' in accept:
                    fel.input(local_path)
                    file_uploaded = True
                    break
            except Exception:
                continue

        if not file_uploaded:
            return None

        page.run_js('''
            document.querySelectorAll('input[type="file"]').forEach(function(inp) {
                inp.dispatchEvent(new Event('change', {bubbles: true, cancelable: true}));
            });
        ''')
        time.sleep(10)

        # 获取上传后的 CDN URL
        url = page.run_js('''
            var imgs = document.querySelectorAll('img[src*="toutiaoimg"], img[src*="tos-cn"], img[src*="p3"], img[src*="p3-sign"]');
            for (var i = imgs.length - 1; i >= 0; i--) {
                if (imgs[i].src && imgs[i].src.indexOf('data:') !== 0 && imgs[i].naturalWidth > 100) {
                    return imgs[i].src;
                }
            }
            return "";
        ''')
        return url if url else None

    def _search_unsplash(self, title):
        """从 Unsplash 搜索封面图（兼容旧接口）"""
        cover, _ = self._prepare_images(title, "")
        return cover

    @staticmethod
    def _extract_keywords(title):
        """从标题中提取关键词（AI 失败时的兜底方案）"""
        if not title:
            return "technology"
        cleaned = re.sub(r'[^一-鿿\w\s]', ' ', title)
        words = cleaned.split()
        keywords = [w for w in words if len(w) >= 2]
        if not keywords:
            return "technology"
        return " ".join(keywords[:3])

    def publish(self, article):
        if not self._validate_article(article):
            return False, "empty title or content"

        cookies = self._load_cookies()
        if not cookies:
            return False, "no cookies found — run login_toutiao.py first"

        title = article["title"]
        content = article["content"]

        # 下载图片 — 优先用 EN→ZH 改写预生成的 image_queries，否则 AI 实时生成
        image_queries = self._parse_image_queries(article.get("image_url", ""))
        cover_path, inline_images = self._prepare_images(title, content, image_queries=image_queries)
        logger.info(f"[toutiao] images ready: cover={bool(cover_path)}, inline={len(inline_images)}")

        # 构建正文段落列表
        paragraphs = [p.strip() for p in content.split("\n") if p.strip()]

        page = None
        try:
            logger.info(f"[toutiao] publishing: {title[:30]}...")
            page = ChromiumPage()
            for c in cookies:
                try:
                    page.set.cookies(c)
                except Exception:
                    pass

            page.get(PUBLISH_URL)
            time.sleep(8)

            # 注入拦截器 — 尽早注入，捕获所有自动保存和发布请求
            page.run_js('''
                window.__publishResult = null;
                window.__publishRequests = [];
                window.__allRequests = [];

                // Intercept ALL XHR
                var origOpen = XMLHttpRequest.prototype.open;
                var origSend = XMLHttpRequest.prototype.send;
                XMLHttpRequest.prototype.open = function(m, u) {
                    this.__debug_url = u;
                    this.__debug_method = m;
                    return origOpen.apply(this, arguments);
                };
                XMLHttpRequest.prototype.send = function(body) {
                    var self = this;
                    var url = self.__debug_url || '';
                    var isPublish = url.indexOf('/article/publish') !== -1;
                    if (isPublish) {
                        window.__publishResult = {url: url, body: body, ts: Date.now()};
                    }
                    self.addEventListener('readystatechange', function() {
                        if (self.readyState === 4) {
                            var respText = self.responseText || '';
                            var entry = {
                                url: url, method: self.__debug_method,
                                status: self.status,
                                body: typeof body === 'string' ? body.substring(0, 4000) : (body || ''),
                                response: isPublish ? respText : respText.substring(0, 500),
                                ts: Date.now(), type: 'xhr'
                            };
                            if (isPublish) {
                                window.__publishRequests.push(entry);
                                if (window.__publishResult) {
                                    window.__publishResult.status = self.status;
                                    window.__publishResult.response = respText;
                                    window.__publishResult.fullBody = entry.body;
                                }
                            }
                            window.__allRequests.push(entry);
                        }
                    });
                    return origSend.apply(this, arguments);
                };

                // Intercept ALL fetch
                var origFetch = window.fetch;
                window.fetch = function(input, init) {
                    var url = typeof input === 'string' ? input : (input.url || '');
                    var isPublish = url.indexOf('/article/publish') !== -1;
                    return origFetch.apply(this, arguments).then(function(resp) {
                        var clone = resp.clone();
                        return clone.text().then(function(text) {
                            var entry = {
                                url: url, method: (init && init.method) || 'GET',
                                status: resp.status,
                                body: (init && init.body) ? String(init.body).substring(0, 2000) : '',
                                response: isPublish ? text : text.substring(0, 500),
                                ts: Date.now(), type: 'fetch'
                            };
                            if (isPublish) {
                                window.__publishResult = {url: url, body: entry.body, ts: Date.now(), status: resp.status, response: text};
                                window.__publishRequests.push(entry);
                            }
                            window.__allRequests.push(entry);
                            return resp;
                        });
                    });
                };

                // Intercept sendBeacon
                var origSendBeacon = navigator.sendBeacon;
                navigator.sendBeacon = function(url, data) {
                    var entry = {
                        url: url, method: 'BEACON', status: 0,
                        body: typeof data === 'string' ? data.substring(0, 2000) : '',
                        response: '', ts: Date.now(), type: 'beacon'
                    };
                    window.__publishRequests.push(entry);
                    window.__allRequests.push(entry);
                    return origSendBeacon.apply(this, arguments);
                };

                // Intercept form submissions
                document.addEventListener('submit', function(e) {
                    var entry = {
                        url: e.target.action || window.location.href,
                        method: (e.target.method || 'GET').toUpperCase(),
                        status: 0,
                        body: '[FormData]',
                        response: '', ts: Date.now(), type: 'form_submit'
                    };
                    window.__publishRequests.push(entry);
                    window.__allRequests.push(entry);
                }, true);
            ''')
            logger.info("[toutiao] interceptor injected (XHR + fetch + beacon + form)")

            # ============ Step 1: 准备封面图 ============
            cover_url = None
            # cover_path 已在上面通过 _prepare_images() 获取，如果失败则 fallback
            if not cover_path:
                cover_path = self._prepare_cover_image(article.get("image_url", ""), title)

            if cover_path and os.path.exists(cover_path):
                logger.info("[toutiao] uploading cover image...")

                # 选择「单图」模式
                page.run_js('''
                    (function() {
                        var labels = document.querySelectorAll('.article-cover-radio-group label');
                        for (var i = 0; i < labels.length; i++) {
                            if (labels[i].innerText.indexOf('单图') !== -1) {
                                labels[i].click(); return;
                            }
                        }
                        // fallback: click first radio that is not "无封面"
                        for (var i = 0; i < labels.length; i++) {
                            if (labels[i].innerText.indexOf('无封面') === -1) {
                                labels[i].click(); return;
                            }
                        }
                    })();
                ''')
                time.sleep(1)

                # 触发封面上传对话框 — 鲁棒选择器
                click_result = page.run_js('''
                    var el = document.querySelector(".article-cover-add")
                         || document.querySelector('[class*="cover-upload"]')
                         || document.querySelector('[class*="cover-wrap"]')
                         || document.querySelector('[class*="CoverWrapper"]');
                    if (el) { el.click(); return "clicked"; }
                    return "no_element";
                ''')
                logger.info(f"[toutiao] cover upload trigger: {click_result}")
                time.sleep(2)

                # 找到 file input 并上传
                file_uploaded = False
                file_inputs = page.eles('tag:input@type=file', timeout=5)
                logger.info(f"[toutiao] found {len(file_inputs)} file inputs")

                for idx, fel in enumerate(file_inputs):
                    try:
                        accept = fel.attr('accept') or ''
                        logger.info(f"[toutiao] input {idx}: accept={accept}")
                        fel.input(cover_path)
                        logger.info(f"[toutiao] cover file selected via input {idx}")
                        file_uploaded = True
                        break
                    except Exception as e:
                        logger.info(f"[toutiao] input {idx} failed: {e}")

                if file_uploaded:
                    # 触发 change 事件（头条 JS 需要）
                    page.run_js('''
                        document.querySelectorAll('input[type="file"]').forEach(function(inp) {
                            inp.dispatchEvent(new Event('change', {bubbles: true, cancelable: true}));
                        });
                    ''')
                    logger.info("[toutiao] change event dispatched, waiting for upload...")
                    time.sleep(12)

                    # 关闭图片抽屉对话框（否则"预览并发布"按钮被挡住）
                    drawer_closed = page.run_js('''
                        // 找图片 drawer 中的「确定」按钮并点击
                        var btns = document.querySelectorAll('.byte-drawer button, [class*="drawer"] button');
                        for (var i = 0; i < btns.length; i++) {
                            var t = (btns[i].innerText || '').trim();
                            if ((t === '确定' || t === '确认') && btns[i].offsetParent !== null && !btns[i].disabled) {
                                btns[i].click();
                                return 'closed:' + t;
                            }
                        }
                        // 如果没找到确定按钮，尝试点关闭图标
                        var closeIcons = document.querySelectorAll('.byte-drawer-close-icon, [class*="drawer"] [class*="close"]');
                        for (var j = 0; j < closeIcons.length; j++) {
                            if (closeIcons[j].offsetParent !== null) {
                                closeIcons[j].click();
                                return 'closed:icon';
                            }
                        }
                        return 'not_closed';
                    ''')
                    logger.info(f"[toutiao] drawer close: {drawer_closed}")
                    time.sleep(2)

                    # 获取上传后的封面 URL
                    cover_urls = page.run_js('''
                        var imgs = document.querySelectorAll('img[src*="toutiaoimg"], img[src*="tos-cn"], img[src*="p3"], img[src*="p3-sign"]');
                        var urls = [];
                        imgs.forEach(function(img) {
                            if (img.src && img.src.indexOf('data:') !== 0 && img.naturalWidth > 100) {
                                urls.push(img.src);
                            }
                        });
                        if (urls.length === 0) {
                            // try background-image
                            var divs = document.querySelectorAll('[style*="background-image"]');
                            divs.forEach(function(d) {
                                var bg = d.style.backgroundImage || '';
                                var m = bg.match(/url\\(["']?([^"')]+)["']?\\)/);
                                if (m) urls.push(m[1]);
                            });
                        }
                        return JSON.stringify(urls);
                    ''')
                    try:
                        urls = json.loads(cover_urls)
                        cover_url = urls[0] if urls else None
                        logger.info(f"[toutiao] cover uploaded: {str(cover_url)[:100]}")
                    except Exception:
                        pass
                else:
                    logger.warning("[toutiao] no file input available for cover upload")
            else:
                logger.warning("[toutiao] no cover image available, using no-cover mode")
                page.run_js('''
                    var labels = document.querySelectorAll('.article-cover-radio-group label');
                    for (var i = 0; i < labels.length; i++) {
                        if (labels[i].innerText.indexOf('无封面') !== -1) {
                            labels[i].click(); break;
                        }
                    }
                ''')
                time.sleep(1)

            # ============ Step 2: 填标题和内容（React 兼容 native setter） ============
            logger.info("[toutiao] filling title with native setter...")
            title_result = page.run_js(f'''
                var el = document.querySelector('input[placeholder*="标题"], textarea[placeholder*="标题"]')
                     || document.querySelector('input[type="text"]:not([disabled]):not([readonly])');
                if (el) {{
                    var desc = Object.getOwnPropertyDescriptor(
                        Object.getPrototypeOf(el).constructor === HTMLInputElement
                            ? window.HTMLInputElement.prototype
                            : window.HTMLTextAreaElement.prototype,
                        'value'
                    );
                    if (desc && desc.set) {{
                        desc.set.call(el, {json.dumps(title)});
                    }} else {{
                        el.value = {json.dumps(title)};
                    }}
                    el.dispatchEvent(new Event('input', {{bubbles: true, cancelable: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true, cancelable: true}}));
                    el.dispatchEvent(new FocusEvent('focus', {{bubbles: true}}));
                    el.dispatchEvent(new FocusEvent('blur', {{bubbles: true}}));
                    return JSON.stringify({{found: true, value: el.value.substring(0, 50)}});
                }}
                return JSON.stringify({{found: false}});
            ''')
            logger.info(f"[toutiao] title fill result: {title_result}")

            # 填内容 — 逐段写入 + 通过工具栏上传正文图片到头条 CDN（避免外链被拒）
            logger.info("[toutiao] filling content progressively...")
            # 清空编辑器
            page.run_js('''
                var ed = document.querySelector('[contenteditable="true"]');
                if (ed) { ed.innerHTML = ''; }
            ''')
            time.sleep(0.5)

            def _append_paragraph(text):
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
                        p.innerHTML = '<strong style=\"font-size:18px\">' + {json.dumps(inner)} + '</strong>';
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

            def _upload_inline_image(local_path):
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
                page.run_js('''
                    var btns = document.querySelectorAll('.byte-drawer button, [class*="drawer"] button');
                    for (var i = 0; i < btns.length; i++) {
                        var t = (btns[i].innerText || '').trim();
                        if ((t === '确定' || t === '确认') && btns[i].offsetParent !== null && !btns[i].disabled) {
                            btns[i].click(); return;
                        }
                    }
                ''')
                time.sleep(2)

            placed = 0
            prev_was_heading = False
            for i, para in enumerate(paragraphs):
                _append_paragraph(para)
                time.sleep(0.8)
                is_heading = bool(re.match(r'^\*\*(.+)\*\*$', para))
                is_last = (i == len(paragraphs) - 1)
                # 小标题 → 正文 → 图片：在小标题后的正文段落之后插入图片
                if not is_last and prev_was_heading and not is_heading and placed < len(inline_images):
                    local_path, _ = inline_images[placed]
                    logger.info(f"[toutiao] uploading inline image {placed+1}/{len(inline_images)} after P{i+1}...")
                    _upload_inline_image(local_path)
                    placed += 1
                prev_was_heading = is_heading

            content_len = page.run_js('''
                var ed = document.querySelector('[contenteditable="true"]');
                return ed ? (ed.innerText || ed.textContent || '').length : 0;
            ''')
            logger.info(f"[toutiao] content filled: {len(paragraphs)} paragraphs, {placed} inline images, {content_len} chars")

            # 等待自动保存完成
            time.sleep(5)

            # 等待自动保存完成，然后提取 pgc_id
            time.sleep(5)

            # 从拦截器捕获的自动保存响应中提取 pgc_id
            pgc_id_from_autosave = page.run_js('''
                var reqs = window.__publishRequests || [];
                for (var i = reqs.length - 1; i >= 0; i--) {
                    var resp = reqs[i].response;
                    if (resp) {
                        try {
                            var data = JSON.parse(resp);
                            if (data.data && data.data.pgc_id) {
                                return data.data.pgc_id;
                            }
                        } catch(e) {}
                    }
                }
                return "";
            ''')
            logger.info(f"[toutiao] pgc_id from autosave: {pgc_id_from_autosave}")

            # 从自动保存请求中提取完整参数（用于 API 发布时参考）
            autosave_body = page.run_js('''
                var reqs = window.__publishRequests || [];
                for (var i = reqs.length - 1; i >= 0; i--) {
                    if (reqs[i].body && reqs[i].body.indexOf("save=0") !== -1) {
                        return reqs[i].body;
                    }
                }
                return "";
            ''')
            logger.info(f"[toutiao] autosave body (first 500): {autosave_body[:500]}")

            # ============ Step 3: 发布（预览并发布 → 确认发布） ============
            logger.info("[toutiao] Step 3: clicking '预览并发布' on main page...")

            # 先记录当前所有可见按钮（调试用）
            before_preview = page.run_js('''
                var btns = document.querySelectorAll('button');
                var v = [];
                for (var i = 0; i < btns.length; i++) {
                    var t = (btns[i].innerText || '').trim();
                    if (btns[i].offsetParent !== null && !btns[i].disabled && t) v.push(t);
                }
                return JSON.stringify(v);
            ''')
            logger.info(f"[toutiao] buttons before preview: {before_preview}")

            # 使用 DrissionPage 原生点击「预览并发布」（模拟真实鼠标点击，触发 React 事件）
            preview_clicked = "false"
            try:
                preview_btn = page.ele('text:预览并发布', timeout=3)
                if preview_btn:
                    preview_btn.click()
                    logger.info(f"[toutiao] preview button clicked via DrissionPage: {preview_btn.text}")
                    preview_clicked = "true"
                else:
                    logger.warning("[toutiao] preview button not found via DrissionPage")
            except Exception as e:
                logger.warning(f"[toutiao] DrissionPage click failed: {e}")
                # Fallback to JS click
                preview_clicked = page.run_js('''
                    var btns = document.querySelectorAll('button');
                    for (var i = 0; i < btns.length; i++) {
                        var t = (btns[i].innerText || '').trim();
                        if (t.indexOf('预览并发布') !== -1 && !btns[i].disabled && btns[i].offsetParent !== null) {
                            // Use full MouseEvent for React compatibility
                            btns[i].dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                            btns[i].dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
                            btns[i].dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
                            return JSON.stringify({clicked: true, text: t, index: i});
                        }
                    }
                    return JSON.stringify({clicked: false});
                ''')
            logger.info(f"[toutiao] preview button: {preview_clicked}")

            # 等待预览页面加载
            time.sleep(8)

            # 截图 — 看预览页面状态
            try:
                ss_path = os.path.join(os.path.dirname(COVER_IMAGE), "debug_preview.png")
                page.get_screenshot(path=ss_path, name="preview")
                logger.info(f"[toutiao] screenshot saved: {ss_path}")
            except Exception as e:
                logger.warning(f"[toutiao] screenshot failed: {e}")

            # 检查预览页面/弹窗是否出现 — 查找所有可见按钮和对话框元素
            preview_state = page.run_js('''
                var btns = document.querySelectorAll('button');
                var visibleBtns = [];
                for (var i = 0; i < btns.length; i++) {
                    var t = (btns[i].innerText || '').trim();
                    if (btns[i].offsetParent !== null && !btns[i].disabled && t) {
                        visibleBtns.push({index: i, text: t});
                    }
                }
                // 查找对话框/遮罩层
                var dialogs = document.querySelectorAll('[class*="dialog"], [class*="modal"], [class*="Modal"], [class*="overlay"], [class*="Overlay"], [class*="preview"], [class*="Preview"], [class*="drawer"], [class*="Drawer"], [role="dialog"]');
                var dialogInfo = [];
                for (var d = 0; d < dialogs.length; d++) {
                    dialogInfo.push({tag: dialogs[d].tagName, classes: (dialogs[d].className || '').substring(0, 100), visible: dialogs[d].offsetParent !== null});
                }
                return JSON.stringify({url: window.location.href, visibleButtons: visibleBtns.map(function(v){return v.text;}), dialogCount: dialogInfo.length, dialogs: dialogInfo});
            ''')
            logger.info(f"[toutiao] preview state: {preview_state}")

            # 用户说要先看预览页面，再点「确认发布」
            # 在预览弹窗中找「确认并发布」或「预览并发布」按钮（不要点「确定」）
            confirm_publish = page.run_js('''
                var allBtns = document.querySelectorAll('button');
                var visible = [];
                for (var i = 0; i < allBtns.length; i++) {
                    var t = (allBtns[i].innerText || '').trim();
                    if (allBtns[i].offsetParent !== null && !allBtns[i].disabled && t) {
                        visible.push({index: i, text: t});
                    }
                }
                // 优先找「确认并发布」- 用户说这才是真正的发布按钮
                var priority = ['确认并发布', '确认发布', '发布投稿', '预览并发布'];
                for (var p = 0; p < priority.length; p++) {
                    for (var i = visible.length - 1; i >= 0; i--) {
                        if (visible[i].text.indexOf(priority[p]) !== -1) {
                            allBtns[visible[i].index].click();
                            return JSON.stringify({clicked: true, text: visible[i].text, position: visible[i].index, allVisible: visible.map(function(v){return v.text;})});
                        }
                    }
                }
                return JSON.stringify({clicked: false, allVisible: visible.map(function(v){return v.text;})});
            ''')
            logger.info(f"[toutiao] confirm publish: {confirm_publish}")

            # 等待发布完成
            time.sleep(10)

            # Dump results
            all_reqs_raw = page.run_js('return JSON.stringify(window.__allRequests || []);')
            logger.info(f"[toutiao] ALL requests after publish: {all_reqs_raw[:3000]}")

            publish_reqs = page.run_js('return JSON.stringify(window.__publishRequests || []);')
            logger.info(f"[toutiao] publish requests after publish: {publish_reqs[:2000]}")

            pgc_id_from_publish = page.run_js('''
                var reqs = window.__publishRequests || [];
                var results = [];
                for (var i = 0; i < reqs.length; i++) {
                    if (reqs[i].response) {
                        try {
                            var data = JSON.parse(reqs[i].response);
                            results.push({msg: data.message, err_no: data.err_no, pgc_id: (data.data||{}).pgc_id});
                        } catch(e) {}
                    }
                }
                return JSON.stringify(results);
            ''')
            logger.info(f"[toutiao] all publish responses: {pgc_id_from_publish}")

            # 检查是否成功 — 头条 API 发布成功也返回 "保存成功"
            try:
                responses = json.loads(pgc_id_from_publish)
                for r in responses:
                    msg = str(r.get('msg', ''))
                    if r.get('err_no') == 0 and ('发布' in msg or '保存成功' in msg or 'success' in msg.lower()):
                        logger.info(f"[toutiao] 发布成功! pgc_id={r.get('pgc_id')}")
                        return True, ""
            except Exception:
                pass

            current_url = page.url
            logger.info(f"[toutiao] final URL: {current_url}")
            if 'content' in current_url or 'article' in current_url:
                logger.info("[toutiao] page redirected, publish likely succeeded")
                return True, ""

            # 如果确认发布按钮已点击且 err_no=0 的响应存在，视为成功
            try:
                confirm_data = json.loads(confirm_publish)
                if confirm_data.get('clicked'):
                    responses = json.loads(pgc_id_from_publish)
                    for r in responses:
                        if r.get('err_no') == 0 and r.get('pgc_id'):
                            logger.info(f"[toutiao] publish confirmed via UI, pgc_id={r.get('pgc_id')}")
                            return True, ""
            except Exception:
                pass

            logger.error("[toutiao] publish may have failed, check responses above")
            return False, "publish not confirmed"

        except Exception as e:
            logger.error(f"[toutiao] publish error: {e}")
            return False, str(e)
        finally:
            if page:
                try:
                    page.quit()
                except Exception:
                    pass

    def _publish_via_api(self, page, title, html_content, content, cover_url, pgc_id=""):
        """通过 JS XHR 直接调 API 发布（使用捕获到的 pgc_id）"""
        try:
            # 复用自动保存的请求体，只修改封面参数
            replay_result = page.run_js(f'''
                return new Promise((resolve, reject) => {{
                    var reqs = window.__publishRequests || [];
                    var lastBody = '';
                    for (var i = reqs.length - 1; i >= 0; i--) {{
                        if (reqs[i].body && reqs[i].body.indexOf('save=0') !== -1) {{
                            lastBody = reqs[i].body;
                            break;
                        }}
                    }}

                    if (!lastBody) {{
                        resolve(JSON.stringify({{error: 'no autosave body found'}}));
                        return;
                    }}

                    // 用 URLSearchParams 解析参数
                    var params = new URLSearchParams(lastBody);

                    // 确保 pgc_id 正确
                    if ({json.dumps(pgc_id)}) {{
                        params.set('pgc_id', {json.dumps(pgc_id)});
                    }}

                    var newBody = params.toString();
                    var results = [];

                    // Attempt 1: no cover params (baseline)
                    function sendRequest(body, label) {{
                        return new Promise(function(resolveReq) {{
                            var xhr = new XMLHttpRequest();
                            xhr.open('POST', '/mp/agw/article/publish?source=mp&type=article&aid=1231&mp_publish_ab_val=0');
                            xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded;charset=UTF-8');
                            xhr.onload = function() {{
                                resolveReq({{ label: label, status: xhr.status, body: xhr.responseText, sentBody: body.substring(0, 200) }});
                            }};
                            xhr.onerror = function() {{ resolveReq({{ label: label, error: 'xhr failed' }}); }};
                            xhr.send(body);
                        }});
                    }}

                    // Build test bodies
                    var promises = [sendRequest(newBody, 'no_cover')];

                    if ({json.dumps(cover_url is not None and cover_url != '')}) {{
                        var coverJson = {json.dumps(json.dumps([{"url": cover_url, "type": "1"}])) if cover_url else '[]'};

                        // Attempt 2: only pgc_feed_covers
                        var p1 = new URLSearchParams(newBody);
                        p1.set('pgc_feed_covers', coverJson);
                        promises.push(sendRequest(p1.toString(), 'only_covers'));

                        // Attempt 3: only draft_form_data
                        var p2 = new URLSearchParams(newBody);
                        p2.set('draft_form_data', JSON.stringify({{coverType: 1}}));
                        promises.push(sendRequest(p2.toString(), 'only_form_data'));

                        // Attempt 4: both (original approach)
                        var p3 = new URLSearchParams(newBody);
                        p3.set('pgc_feed_covers', coverJson);
                        p3.set('draft_form_data', JSON.stringify({{coverType: 1}}));
                        promises.push(sendRequest(p3.toString(), 'both'));
                    }}

                    Promise.all(promises).then(function(allResults) {{
                        resolve(JSON.stringify(allResults));
                    }});
                }});
                }});
            ''')

            all_results = json.loads(replay_result)
            if isinstance(all_results, dict) and 'error' in all_results:
                logger.error(f"[toutiao] API publish: {all_results['error']}")
                return False, all_results['error']

            for r in (all_results if isinstance(all_results, list) else [all_results]):
                if 'error' in r:
                    logger.warning(f"[toutiao] API {r.get('label', '?')}: {r['error']}")
                    continue
                resp = json.loads(r['body'])
                msg = resp.get('message', '') or resp.get('reason', '')
                err_no = resp.get('err_no', -1)
                logger.info(f"[toutiao] API [{r.get('label', '?')}]: err={err_no} msg='{msg}'")

                if err_no == 0:
                    if '发布' in msg or '提交' in msg:
                        logger.info(f"[toutiao] API 发布成功! pgc_id={resp.get('data', {}).get('pgc_id', '')}")
                        return True, ""

            logger.error("[toutiao] all API attempts failed")
            return False, str(all_results)

        except Exception as e:
            logger.error(f"[toutiao] API publish error: {e}")
            return False, str(e)
