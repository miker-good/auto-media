import pytest
from unittest.mock import patch, Mock
from rewriter.rewriter import Rewriter
from config import Config


@pytest.fixture
def config():
    cfg = Config()
    cfg.ai_api_key = "sk-test"
    cfg.ai_base_url = "https://api.deepseek.com/v1"
    cfg.ai_model = "deepseek-chat"
    return cfg


def test_rewriter_formats_prompt(config):
    rew = Rewriter(config)
    article = {"title": "测试标题", "content": "这是原文内容需要被改写"}
    prompt = rew._build_prompt(article)
    assert "测试标题" in prompt
    assert "这是原文内容" in prompt
    assert "JSON" in prompt
    assert "title" in prompt


def test_rewriter_calls_api(config):
    mock_client = Mock()
    mock_client.chat.completions.create.return_value = Mock(
        choices=[Mock(message=Mock(content='{"title":"新标题","content":"改写内容"}'))]
    )
    with patch("rewriter.rewriter.OpenAI", return_value=mock_client):
        rew = Rewriter(config)
        result = rew.rewrite({"title": "原标题", "content": "原内容"})
        assert result["title"] == "新标题"
        assert result["content"] == "改写内容"


def test_rewriter_falls_back_on_api_error(config):
    import httpx
    with patch("rewriter.rewriter.OpenAI", side_effect=httpx.HTTPError("timeout")):
        rew = Rewriter(config)
        article = {"title": "原标题", "content": "原内容"}
        result = rew.rewrite(article)
        assert result["title"] == "原标题"
        assert result["content"] == "原内容"


def test_rewriter_falls_back_on_bad_json(config):
    mock_client = Mock()
    mock_client.chat.completions.create.return_value = Mock(
        choices=[Mock(message=Mock(content="不是JSON格式的返回"))]
    )
    with patch("rewriter.rewriter.OpenAI", return_value=mock_client):
        rew = Rewriter(config)
        article = {"title": "原标题", "content": "原内容"}
        result = rew.rewrite(article)
        assert result["title"] == "原标题"
        assert result["content"] == "原内容"
