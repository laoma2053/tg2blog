"""WordPress 发布器测试"""
import pytest
from unittest.mock import Mock, patch
from app.services.wordpress_publisher import publish_post, WordPressPublishError
from app.schemas.wordpress import WordPressPostPayload


def test_publish_post_success():
    """测试成功发布"""
    payload = WordPressPostPayload(
        title="测试文章",
        slug="test-article",
        excerpt="摘要",
        content="<p>内容</p>"
    )

    with patch('httpx.Client') as mock_client:
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": 123,
            "slug": "test-article",
            "link": "https://example.com/test-article"
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response

        result = publish_post(payload)

        assert result["id"] == 123
        assert result["slug"] == "test-article"


def test_publish_post_unauthorized():
    """测试 401 未授权"""
    payload = WordPressPostPayload(
        title="测试",
        slug="test",
        excerpt="摘要",
        content="内容"
    )

    with patch('httpx.Client') as mock_client:
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response

        with pytest.raises(WordPressPublishError):
            publish_post(payload)
