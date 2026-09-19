"""
Bộ kiểm thử tự động toàn diện cho ContentExtractorEngine.
Chạy:
    python tests/test_content_extractor.py
hoặc:
    pytest tests/test_content_extractor.py -v -s
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Thêm thư mục gốc vào sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.services.content_extractor import (
    ContentExtractorConfig,
    ContentExtractorEngine,
    ContentExtractorError,
    EmptyContentError,
    JSONParsingError,
    MissingJsonStructureError,
    MissingSystemPromptError,
    NoValidApiKeyError,
)
from app.services.key_rotator import KeyRotator


def test_empty_content_raises_empty_content_error():
    """Kiểm tra engine ném EmptyContentError khi nội dung rỗng."""
    config = ContentExtractorConfig(
        model_name="gemini-2.5-flash",
        api_keys=["test-key-1"],
        system_prompt="System prompt test",
        json_structure={"title": "Vị trí tuyển dụng"},
    )
    engine = ContentExtractorEngine(config)

    for empty_input in ["", "   ", "\n\t"]:
        try:
            engine.extract(empty_input)
            assert False, f"Lẽ ra phải ném EmptyContentError với input: '{empty_input}'"
        except EmptyContentError as e:
            assert "trống" in str(e).lower()
    print("-> PASS: test_empty_content_raises_empty_content_error")


def test_config_validation():
    """Kiểm tra pydantic validation của ContentExtractorConfig."""
    # 1. api_keys rỗng
    try:
        ContentExtractorConfig(
            api_keys=[],
            system_prompt="Test",
            json_structure={"test": "ok"},
        )
        assert False, "Lẽ ra phải báo lỗi khi api_keys rỗng"
    except ValueError as e:
        assert "api_keys" in str(e).lower()

    # 2. system_prompt rỗng
    try:
        ContentExtractorConfig(
            api_keys=["key1"],
            system_prompt="   ",
            json_structure={"test": "ok"},
        )
        assert False, "Lẽ ra phải báo lỗi khi system_prompt rỗng"
    except ValueError as e:
        assert "system_prompt" in str(e).lower()

    # 3. json_structure rỗng
    try:
        ContentExtractorConfig(
            api_keys=["key1"],
            system_prompt="Valid prompt",
            json_structure={},
        )
        assert False, "Lẽ ra phải báo lỗi khi json_structure rỗng"
    except ValueError as e:
        assert "json_structure" in str(e).lower()

    print("-> PASS: test_config_validation")


def test_no_valid_api_keys_raises_error():
    """Kiểm tra ném NoValidApiKeyError khi toàn bộ key trong rotator đã bị hỏng."""
    rotator = KeyRotator(["key1", "key2"])
    rotator.mark_key_failed("key1", "Quota 429")
    rotator.mark_key_failed("key2", "Invalid key")

    config = ContentExtractorConfig(
        api_keys=["key1", "key2"],
        system_prompt="Prompt",
        json_structure={"title": "Job"},
    )
    engine = ContentExtractorEngine(config, key_rotator=rotator)

    try:
        engine.extract("Tuyển dụng nhân viên sale lương 15tr")
        assert False, "Lẽ ra phải ném NoValidApiKeyError khi không còn key nào"
    except NoValidApiKeyError as e:
        assert "api key" in str(e).lower()
    print("-> PASS: test_no_valid_api_keys_raises_error")


def test_markdown_fence_stripping_and_json_parsing():
    """Kiểm tra hàm _clean_and_parse_json xử lý sạch markdown fences và trích xuất đúng json."""
    engine = ContentExtractorEngine()

    raw_response_1 = """```json
    {
        "title": "Kỹ Sư AI",
        "salary": "30 triệu"
    }
    ```"""
    parsed_1 = engine._clean_and_parse_json(raw_response_1)
    assert parsed_1["title"] == "Kỹ Sư AI"
    assert parsed_1["salary"] == "30 triệu"

    raw_response_2 = """Dưới đây là kết quả phân tích:
    {
        "company": "FPT Telecom",
        "benefits": ["Thưởng tết", "Bảo hiểm"]
    }
    Cảm ơn bạn!"""
    parsed_2 = engine._clean_and_parse_json(raw_response_2)
    assert parsed_2["company"] == "FPT Telecom"
    assert len(parsed_2["benefits"]) == 2

    # Trường hợp trả về text không phải json hợp lệ
    try:
        engine._clean_and_parse_json("Đây là bài viết bình thường không có json.")
        assert False, "Lẽ ra phải ném JSONParsingError"
    except JSONParsingError:
        pass

    print("-> PASS: test_markdown_fence_stripping_and_json_parsing")


def test_key_rotation_and_successful_extraction_mock():
    """Kiểm tra cơ chế xoay vòng: key 1 bị lỗi 429, tự động đổi sang key 2 và trích xuất thành công."""
    config = ContentExtractorConfig(
        model_name="gemini-2.5-flash",
        api_keys=["key-quota-exceeded", "key-working-well"],
        system_prompt="Hệ thống bóc tách JD",
        json_structure={
            "job_title": "string",
            "salary": "string"
        },
    )
    engine = ContentExtractorEngine(config)

    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "job_title": "Senior Python Backend Developer",
        "salary": "35 - 50 Triệu"
    })

    call_count = 0

    def mock_generate_content(model, contents, config):
        nonlocal call_count
        call_count += 1
        current_key = engine.key_rotator.get_current_key()
        if current_key == "key-quota-exceeded":
            raise RuntimeError("Resource has been exhausted (e.g. check quota) 429")
        return mock_response

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = mock_generate_content

    with patch("google.genai.Client", return_value=mock_client):
        result = engine.extract("Cần tuyển Senior Python Backend lương 35-50tr tại Q1")

    assert call_count == 2
    assert result["job_title"] == "Senior Python Backend Developer"
    assert result["salary"] == "35 - 50 Triệu"
    # Key đầu tiên phải bị đánh dấu lỗi
    assert engine.key_rotator.available_keys_count() == 1
    print("-> PASS: test_key_rotation_and_successful_extraction_mock")


def test_all_keys_fail_raises_no_valid_api_key_error():
    """Kiểm tra khi toàn bộ keys đều gặp lỗi từ Google GenAI API."""
    config = ContentExtractorConfig(
        model_name="gemini-2.5-flash",
        api_keys=["bad-key-1", "bad-key-2"],
        system_prompt="Test",
        json_structure={"title": "string"},
    )
    engine = ContentExtractorEngine(config)

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("API Key not valid")

    with patch("google.genai.Client", return_value=mock_client):
        try:
            engine.extract("Tuyển kế toán tổng hợp")
            assert False, "Lẽ ra phải ném NoValidApiKeyError khi toàn bộ key đều lỗi"
        except NoValidApiKeyError as e:
            assert "api key" in str(e).lower()
    print("-> PASS: test_all_keys_fail_raises_no_valid_api_key_error")


if __name__ == "__main__":
    print("=== BẮT ĐẦU KIỂM THỬ CONTENT EXTRACTOR ENGINE ===")
    test_empty_content_raises_empty_content_error()
    test_config_validation()
    test_no_valid_api_keys_raises_error()
    test_markdown_fence_stripping_and_json_parsing()
    test_key_rotation_and_successful_extraction_mock()
    test_all_keys_fail_raises_no_valid_api_key_error()
    print("✅ TẤT CẢ UNIT TESTS CHO CONTENT EXTRACTOR ĐÃ VƯỢT QUA 100% HOÀN HẢO!")
