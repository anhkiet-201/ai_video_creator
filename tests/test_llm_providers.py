"""Bộ kiểm thử đơn vị toàn diện cho BaseLLMProvider, GeminiLLMProvider, LMStudioLLMProvider và LLMFactory."""

import json
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch
import httpx

# Thêm thư mục gốc dự án vào sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.services.key_rotator import KeyRotator
from app.services.llm import (
    BaseLLMProvider,
    GeminiLLMProvider,
    LMStudioLLMProvider,
    create_llm_provider,
    LLMConnectionError,
    LLMEmptyResponseError,
    LLMProviderError,
    LLMQuotaExhaustedError,
    LLMResponseParsingError,
)
from app.services.plan_creator import PlanCreatorConfig, PlanCreatorEngine


# -------------------------------------------------------------------------
# 1. TEST BASE LLM PROVIDER & JSON PARSER
# -------------------------------------------------------------------------

class DummyLLMProvider(BaseLLMProvider):
    def generate_text(self, prompt: str, system_prompt=None, temperature=0.7, **kwargs) -> str:
        return "dummy text"

    def generate_json(self, prompt: str, system_prompt=None, temperature=0.7, json_schema=None, **kwargs):
        return self.clean_and_parse_json('{"key": "value"}')


def test_base_clean_and_parse_json_valid():
    """Kiểm tra parse JSON hợp lệ cơ bản."""
    provider = DummyLLMProvider()
    result = provider.clean_and_parse_json('{"name": "TikTok AI", "status": 200}')
    assert result == {"name": "TikTok AI", "status": 200}
    print("-> PASS: test_base_clean_and_parse_json_valid")


def test_base_clean_and_parse_json_markdown_fence():
    """Kiểm tra bóc tách JSON bọc trong markdown code fence."""
    provider = DummyLLMProvider()
    raw = "```json\n{\n  \"title\": \"Video Kịch Bản\",\n  \"scenes\": [1, 2, 3]\n}\n```"
    result = provider.clean_and_parse_json(raw)
    assert result["title"] == "Video Kịch Bản"
    assert len(result["scenes"]) == 3
    print("-> PASS: test_base_clean_and_parse_json_markdown_fence")


def test_base_clean_and_parse_json_surrounding_text():
    """Kiểm tra bóc tách JSON khi AI sinh thêm văn bản giải thích ở trước và sau."""
    provider = DummyLLMProvider()
    raw = (
        "Chào bạn, dưới đây là kịch bản video:\n\n"
        "{\n  \"hook\": \"Bí quyết làm video triệu view\",\n  \"duration\": 30\n}\n\n"
        "Chúc bạn sản xuất video thành công!"
    )
    result = provider.clean_and_parse_json(raw)
    assert result["hook"] == "Bí quyết làm video triệu view"
    assert result["duration"] == 30
    print("-> PASS: test_base_clean_and_parse_json_surrounding_text")


def test_base_clean_and_parse_json_comments_and_trailing_commas():
    """Kiểm tra xử lý comment // và trailing comma trong JSON."""
    provider = DummyLLMProvider()
    raw = """
    {
        // Đây là comment giải thích
        "title": "Test Title",
        /* Comment nhiều dòng */
        "items": [
            "one",
            "two",
        ],
    }
    """
    result = provider.clean_and_parse_json(raw)
    assert result["title"] == "Test Title"
    assert len(result["items"]) == 2
    print("-> PASS: test_base_clean_and_parse_json_comments_and_trailing_commas")


def test_base_clean_and_parse_json_invalid():
    """Kiểm tra ném LLMResponseParsingError khi nội dung không chứa JSON."""
    provider = DummyLLMProvider()
    try:
        provider.clean_and_parse_json("Đây hoàn toàn là văn bản thường, không có ngoặc nhọn")
        assert False, "Lẽ ra phải ném LLMResponseParsingError"
    except LLMResponseParsingError:
        pass

    try:
        provider.clean_and_parse_json("")
        assert False, "Lẽ ra phải ném LLMResponseParsingError khi chuỗi rỗng"
    except LLMResponseParsingError:
        pass
    print("-> PASS: test_base_clean_and_parse_json_invalid")


# -------------------------------------------------------------------------
# 2. TEST GEMINI LLM PROVIDER
# -------------------------------------------------------------------------

def test_gemini_provider_success():
    """Kiểm tra GeminiLLMProvider sinh văn bản và JSON thành công."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps({"status": "ok", "message": "hello gemini"})
    mock_client.models.generate_content.return_value = mock_resp

    provider = GeminiLLMProvider(api_keys=["valid_key_1"], model_name="gemini-2.5-flash")

    with patch("google.genai.Client", return_value=mock_client):
        text_res = provider.generate_text("Chào Gemini")
        assert "hello gemini" in text_res

        json_res = provider.generate_json("Tạo JSON", system_prompt="Bạn là biên kịch")
        assert json_res["status"] == "ok"

    print("-> PASS: test_gemini_provider_success")


def test_gemini_provider_key_rotation_and_exhaustion():
    """Kiểm tra GeminiLLMProvider tự động xoay key khi 429 và ném LLMQuotaExhaustedError."""
    rotator = KeyRotator(["key_fail_1", "key_fail_2"])
    provider = GeminiLLMProvider(key_rotator=rotator)

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("429 Quota Exceeded")

    with patch("google.genai.Client", return_value=mock_client):
        try:
            provider.generate_json("Prompt")
            assert False, "Lẽ ra phải ném LLMQuotaExhaustedError"
        except LLMQuotaExhaustedError as e:
            assert "toàn bộ api key" in str(e).lower()

    assert not rotator.has_available_keys()
    print("-> PASS: test_gemini_provider_key_rotation_and_exhaustion")


# -------------------------------------------------------------------------
# 3. TEST LM STUDIO LLM PROVIDER
# -------------------------------------------------------------------------

def test_lm_studio_provider_success():
    """Kiểm tra LMStudioLLMProvider gọi HTTP thành công và parse kết quả."""
    fake_response_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"title": "Local Script", "score": 9.5}),
                }
            }
        ]
    }

    mock_http_resp = MagicMock()
    mock_http_resp.status_code = 200
    mock_http_resp.json.return_value = fake_response_data

    provider = LMStudioLLMProvider(
        base_url="http://localhost:1234/v1",
        model_name="qwen2.5-7b-instruct",
    )

    with patch("httpx.Client.post", return_value=mock_http_resp) as mock_post:
        result = provider.generate_json("Lên kịch bản", system_prompt="Biên kịch")
        assert result["title"] == "Local Script"
        assert result["score"] == 9.5

        # Xác thực tham số request gửi tới LM Studio
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["model"] == "qwen2.5-7b-instruct"
        assert call_kwargs["json"]["messages"][0]["content"] == "Biên kịch"

    print("-> PASS: test_lm_studio_provider_success")


def test_lm_studio_provider_connection_error():
    """Kiểm tra LMStudioLLMProvider ném LLMConnectionError kèm hướng dẫn khi server offline."""
    provider = LMStudioLLMProvider(base_url="http://localhost:1234/v1")

    with patch("httpx.Client.post", side_effect=httpx.ConnectError("Connection refused")):
        try:
            provider.generate_text("Hello local")
            assert False, "Lẽ ra phải ném LLMConnectionError"
        except LLMConnectionError as e:
            assert "không thể kết nối đến máy chủ lm studio" in str(e).lower()
            assert "local server" in str(e).lower()

    print("-> PASS: test_lm_studio_provider_connection_error")


def test_lm_studio_provider_retry_without_response_format():
    """Kiểm tra fallback tự động khi LM Studio server báo lỗi 400 do không hỗ trợ response_format."""
    provider = LMStudioLLMProvider()

    # Lần 1 trả về 400 response_format không hỗ trợ, lần 2 trả về 200 thành công
    resp_400 = MagicMock()
    resp_400.status_code = 400
    resp_400.text = "Error: response_format is not supported by this model"

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {
        "choices": [{"message": {"content": "{\"fallback\": true}"}}]
    }

    with patch("httpx.Client.post", side_effect=[resp_400, resp_200]):
        result = provider.generate_json("Prompt")
        assert result["fallback"] is True

    print("-> PASS: test_lm_studio_provider_retry_without_response_format")


def test_lm_studio_provider_base_url_normalization():
    """Kiểm tra tự động thêm /v1 vào base_url nếu người dùng chỉ nhập domain/port."""
    p1 = LMStudioLLMProvider(base_url="http://127.0.0.1:1234")
    assert p1.base_url == "http://127.0.0.1:1234/v1"

    p2 = LMStudioLLMProvider(base_url="http://127.0.0.1:1234/")
    assert p2.base_url == "http://127.0.0.1:1234/v1"

    p3 = LMStudioLLMProvider(base_url="http://localhost:1234/v1")
    assert p3.base_url == "http://localhost:1234/v1"

    print("-> PASS: test_lm_studio_provider_base_url_normalization")


# -------------------------------------------------------------------------
# 4. TEST FACTORY & REGISTRY
# -------------------------------------------------------------------------

def test_llm_factory():
    """Kiểm tra LLMFactory tạo đúng instance theo provider type."""
    p_gemini = create_llm_provider("gemini", api_keys=["k1"])
    assert isinstance(p_gemini, GeminiLLMProvider)
    assert p_gemini.model_name == "gemini-2.5-flash"

    p_lm = create_llm_provider("lm_studio", base_url="http://127.0.0.1:1234/v1", model_name="local-qwen")
    assert isinstance(p_lm, LMStudioLLMProvider)
    assert p_lm.base_url == "http://127.0.0.1:1234/v1"
    assert p_lm.model_name == "local-qwen"

    # Alias test
    p_local = create_llm_provider("local")
    assert isinstance(p_local, LMStudioLLMProvider)

    # Provider không hợp lệ
    try:
        create_llm_provider("unsupported_ai")
        assert False, "Lẽ ra phải ném ValueError"
    except ValueError as e:
        assert "không hỗ trợ llm provider" in str(e).lower()

    print("-> PASS: test_llm_factory")


# -------------------------------------------------------------------------
# 5. TEST DEPENDENCY INJECTION VÀO PLAN CREATOR ENGINE
# -------------------------------------------------------------------------

def test_plan_creator_engine_with_custom_lm_studio_provider():
    """Kiểm tra PlanCreatorEngine chạy trơn tru khi inject trực tiếp LMStudioLLMProvider (không cần Gemini API Key)."""
    mock_provider = MagicMock(spec=BaseLLMProvider)
    mock_provider.generate_json.return_value = {
        "script_id": 1,
        "title": "Video hoàn toàn sinh từ LM Studio",
        "scenes": [
            {
                "scene_index": 0,
                "title": "Cảnh 1 Local",
                "srt_script": "Chào mừng đến với LM Studio",
                "transition": "fade",
            }
        ],
    }

    config = PlanCreatorConfig(
        provider="lm_studio",
        system_prompt="Prompt biên kịch",
        json_structure={"title": "string"},
    )
    # Không cần api_keys!
    engine = PlanCreatorEngine(config=config, llm_provider=mock_provider)

    result = engine.create_single_plan(content="Nội dung test không cần Gemini API Key")
    assert result["title"] == "Video hoàn toàn sinh từ LM Studio"
    assert len(result["scenes"]) == 1
    mock_provider.generate_json.assert_called_once()

    print("-> PASS: test_plan_creator_engine_with_custom_lm_studio_provider")


# -------------------------------------------------------------------------
# ENTRYPOINT CHẠY TẤT CẢ TESTS
# -------------------------------------------------------------------------

def run_all_tests():
    print("\n=== BẮT ĐẦU KIỂM THỬ LLM PROVIDER SUITE ===")
    test_base_clean_and_parse_json_valid()
    test_base_clean_and_parse_json_markdown_fence()
    test_base_clean_and_parse_json_surrounding_text()
    test_base_clean_and_parse_json_comments_and_trailing_commas()
    test_base_clean_and_parse_json_invalid()
    test_gemini_provider_success()
    test_gemini_provider_key_rotation_and_exhaustion()
    test_lm_studio_provider_success()
    test_lm_studio_provider_connection_error()
    test_lm_studio_provider_retry_without_response_format()
    test_lm_studio_provider_base_url_normalization()
    test_llm_factory()
    test_plan_creator_engine_with_custom_lm_studio_provider()
    print("\n✅ TOÀN BỘ UNIT TESTS CHO LLM PROVIDERS ĐÃ VƯỢT QUA 100% HOÀN HẢO!\n")


if __name__ == "__main__":
    run_all_tests()
