import json
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """你是一个资深自媒体编辑。请对以下网络文章进行改写，要求：

1. 换一个更吸引人的标题（20字以内）
2. 重新组织段落结构
3. 替换同义词，保持语气自然
4. 不改变核心信息点
5. 内容长度控制在200-500字

原始标题：{title}
原始内容：{content}

输出严格JSON格式，不要加任何额外文字：
{{"title": "新标题", "content": "改写后的内容"}}"""


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
        return PROMPT_TEMPLATE.format(
            title=article.get("title", ""),
            content=article.get("content", "")
        )

    def rewrite(self, article):
        try:
            prompt = self._build_prompt(article)
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                timeout=30
            )
            text = resp.choices[0].message.content.strip()
            text = text.lstrip("```json").rstrip("```").strip()
            result = json.loads(text)
            return {
                "title": result.get("title", article.get("title", "")),
                "content": result.get("content", article.get("content", ""))
            }
        except Exception as e:
            logger.warning(f"rewrite failed, using original: {e}")
            return {
                "title": article.get("title", ""),
                "content": article.get("content", "")
            }
