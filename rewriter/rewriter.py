import json
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

PROMPT_ZH = """你是一个资深自媒体编辑。请对以下网络文章进行改写，要求：

1. 换一个更吸引人的标题（20字以内）
2. 重新组织段落结构
3. 替换同义词，保持语气自然
4. 不改变核心信息点
5. 内容长度控制在200-500字

原始标题：{title}
原始内容：{content}

输出严格JSON格式：
{{"title": "新标题", "content": "改写后的内容"}}"""

PROMPT_EN = """You are an editor for a Chinese news platform. Translate and rewrite the following English article into Chinese, in the style of "海外新鲜事" (International Buzz).

CRITICAL RULES — output will be rejected if any rule is violated:
1. Title: strictly NO emoji, NO special symbols. Pure Chinese text + optional Chinese punctuation only. 15-25 chars.
2. Structure — EXACTLY this format with MEANINGFUL sub-headings (NOT generic "小标题1/2/3"), each describing the paragraph's key point:

**有意义的概括性小标题**
详细正文段落（80-150字，包含具体数据、背景、案例）

**另一个有意义的概括性小标题**
详细正文段落（80-150字，包含具体数据、背景、案例）

**第三个有意义的概括性小标题**
详细正文段落（80-150字，包含具体数据、背景、案例）

结尾互动段落（无小标题，60-100字）

3. Body paragraphs must be RICH: include specific details, data, background context, vivid examples. NOT generic summaries.
4. Total content 500-700 Chinese characters
5. Generate 3 English Unsplash search phrases (2-4 words each) for images matching this topic visually
6. Names, places, technical terms must be accurate
7. End with an interactive question for Chinese readers

Output STRICT JSON only, no markdown fences:
{{"title": "中文标题", "content": "**小标题A**\\n段落内容\\n**小标题B**\\n段落内容\\n**小标题C**\\n段落内容\\n结尾互动", "image_queries": ["query1", "query2", "query3"]}}

English Title: {title}
English Content: {content}"""


def is_english(text):
    if not text:
        return False
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    return ascii_chars / max(len(text), 1) > 0.7


class Rewriter:
    def __init__(self, config):
        self._api_key = config.ai_api_key
        self._base_url = config.ai_base_url
        self.model = config.ai_model
        self.temperature = config.rewrite_temperature
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    def _build_prompt(self, article):
        title = article.get("title") or article.get("original_title", "")
        content = article.get("content") or article.get("original_content", "")
        if is_english(title) or is_english(content):
            return "EN", PROMPT_EN.format(title=title, content=content)
        return "ZH", PROMPT_ZH.format(title=title, content=content)

    def _parse_json(self, text):
        text = text.strip().lstrip("```json").rstrip("```").strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            text = text[start:end]

        strategies = [
            lambda t: json.loads(t),
            lambda t: json.loads(t, strict=False),
            lambda t: json.loads(
                t.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\r").replace("\t", " "),
                strict=False
            ),
        ]
        for fn in strategies:
            try:
                return fn(text)
            except Exception:
                continue
        raise ValueError("all json parse strategies failed")

    def _validate_en_result(self, result):
        """Validate EN rewrite against three rules. Returns (ok, reason)."""
        title = result.get("title", "")
        content = result.get("content", "")

        # Rule 1: No emoji in title
        emoji_pattern = re.compile(
            '[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF'
            '\U0001F1E0-\U0001F1FF\U00002600-\U000027BF\U0001F900-\U0001F9FF'
            '\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002702-\U000027B0'
            '\U000024C2-\U0001F251\U0001f004\U0001f0cf]'
        )
        if emoji_pattern.search(title):
            return False, "title contains emoji"

        # Rule 2: At least 2 meaningful sub-headings, 400+ chars
        subheadings = re.findall(r'\*\*(.+?)\*\*', content)
        if len(subheadings) < 2:
            return False, f"only {len(subheadings)} sub-headings, need >= 2"

        for s in subheadings:
            if re.match(r'^小标题\s*\d*$', s) or re.match(r'^sub(heading)?\s*\d*$', s, re.I):
                return False, f"generic sub-heading: {s}"

        if len(content) < 400:
            return False, f"content too short ({len(content)} chars)"

        return True, "ok"

    def rewrite(self, article):
        try:
            lang, prompt = self._build_prompt(article)
            result = None
            for attempt in range(3):
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                    timeout=30
                )
                text = resp.choices[0].message.content.strip()
                try:
                    result = self._parse_json(text)
                except ValueError:
                    logger.warning(f"rewrite attempt {attempt+1}: JSON parse failed, retrying")
                    prompt = f"Your previous response had invalid JSON format. Please output STRICT JSON only.\n\n{prompt}"
                    continue

                if lang == "EN":
                    ok, reason = self._validate_en_result(result)
                    if ok:
                        logger.info(f"rewrite passed validation (attempt {attempt+1})")
                        break
                    logger.warning(f"rewrite attempt {attempt+1}: {reason}, retrying...")
                    prompt = f"Your previous response was rejected because: {reason}.\nPlease follow ALL rules strictly.\n\n{PROMPT_EN.format(title=article.get('title') or article.get('original_title', ''), content=article.get('content') or article.get('original_content', ''))}"
                else:
                    break

            if result is None:
                raise ValueError("all rewrite attempts failed")

            rv = {
                "title": result.get("title") or article.get("title") or article.get("original_title", ""),
                "content": result.get("content") or article.get("content") or article.get("original_content", "")
            }
            if lang == "EN":
                rv["image_queries"] = result.get("image_queries", [])
            return rv
        except Exception as e:
            logger.warning(f"rewrite failed, using original: {e}")
            return {
                "title": article.get("title") or article.get("original_title", ""),
                "content": article.get("content") or article.get("original_content", "")
            }
