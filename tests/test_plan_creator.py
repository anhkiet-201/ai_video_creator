"""
Bộ kiểm thử tự động toàn diện cho PlanCreatorEngine.
Chạy:
    python tests/test_plan_creator.py
hoặc:
    pytest tests/test_plan_creator.py -v -s
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Thêm thư mục gốc vào sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.services.key_rotator import KeyRotator
from app.services.plan_creator import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_USER_PROMPT_TEMPLATE,
    EmptyContentError,
    FFMPEG_TRANSITIONS,
    InvalidNumScriptsError,
    JSONParsingError,
    MissingJsonStructureError,
    MissingSystemPromptError,
    NoValidApiKeyError,
    PlanCreatorConfig,
    PlanCreatorEngine,
    PlanCreatorError,
)

SAMPLE_CONTENT = {
    "job_title": "AI Engineer",
    "company": "TechNova",
    "salary": "30 - 45 triệu",
}

SAMPLE_STRUCTURE = {
    "total_scripts": 2,
    "scripts": [
        {
            "script_id": 1,
            "title": "Tiêu đề kịch bản",
            "hook": "Câu mở đầu",
        }
    ],
}


def test_invalid_num_scripts():
    """Kiểm tra engine ném InvalidNumScriptsError khi num_scripts <= 0."""
    config = PlanCreatorConfig(
        api_keys=["key1"],
        system_prompt="Prompt test",
        json_structure=SAMPLE_STRUCTURE,
    )
    engine = PlanCreatorEngine(config)

    for invalid_num in [0, -1, -5]:
        try:
            engine.create_plans(SAMPLE_CONTENT, num_scripts=invalid_num)
            assert False, f"Lẽ ra phải ném InvalidNumScriptsError với num_scripts = {invalid_num}"
        except InvalidNumScriptsError as e:
            assert "số nguyên dương" in str(e).lower()
    print("-> PASS: test_invalid_num_scripts")


def test_empty_content_raises_empty_content_error():
    """Kiểm tra engine ném EmptyContentError khi nội dung rỗng."""
    config = PlanCreatorConfig(
        api_keys=["key1"],
        system_prompt="Prompt test",
        json_structure=SAMPLE_STRUCTURE,
    )
    engine = PlanCreatorEngine(config)

    for empty_input in ["", "   ", "\n\t", {}, "{}"]:
        try:
            engine.create_plans(empty_input, num_scripts=2)
            assert False, f"Lẽ ra phải ném EmptyContentError với input: {repr(empty_input)}"
        except EmptyContentError as e:
            assert "không được để trống" in str(e).lower() or "rỗng" in str(e).lower()
    print("-> PASS: test_empty_content_raises_empty_content_error")


def test_config_validation():
    """Kiểm tra validation của PlanCreatorConfig."""
    # 1. api_keys rỗng
    try:
        PlanCreatorConfig(
            api_keys=[],
            system_prompt="Test",
            json_structure=SAMPLE_STRUCTURE,
        )
        assert False, "Lẽ ra phải báo lỗi khi api_keys rỗng"
    except ValueError as e:
        assert "api_keys" in str(e).lower()

    # 2. system_prompt rỗng
    try:
        PlanCreatorConfig(
            api_keys=["key1"],
            system_prompt="   ",
            json_structure=SAMPLE_STRUCTURE,
        )
        assert False, "Lẽ ra phải báo lỗi khi system_prompt rỗng"
    except ValueError as e:
        assert "system_prompt" in str(e).lower()

    # 3. json_structure rỗng
    try:
        PlanCreatorConfig(
            api_keys=["key1"],
            system_prompt="Prompt",
            json_structure={},
        )
        assert False, "Lẽ ra phải báo lỗi khi json_structure rỗng"
    except ValueError as e:
        assert "json_structure" in str(e).lower()

    # 4. Temperature ngoài khoảng [0.0, 2.0]
    try:
        PlanCreatorConfig(
            api_keys=["key1"],
            system_prompt="Prompt",
            json_structure=SAMPLE_STRUCTURE,
            temperature=3.5,
        )
        assert False, "Lẽ ra phải báo lỗi khi temperature > 2.0"
    except ValueError:
        pass

    print("-> PASS: test_config_validation")


def test_no_api_key_available():
    """Kiểm tra ném NoValidApiKeyError khi KeyRotator không có key khả dụng."""
    config = PlanCreatorConfig(
        api_keys=["key1"],
        system_prompt="Prompt test",
        json_structure=SAMPLE_STRUCTURE,
    )
    rotator = KeyRotator([])
    engine = PlanCreatorEngine(config, key_rotator=rotator)

    try:
        engine.create_plans(SAMPLE_CONTENT, num_scripts=2)
        assert False, "Lẽ ra phải ném NoValidApiKeyError khi rotator không có key"
    except NoValidApiKeyError as e:
        assert "không tìm thấy gemini api key" in str(e).lower()

    print("-> PASS: test_no_api_key_available")


def test_clean_and_parse_json():
    """Kiểm tra khả năng phân tích JSON và gỡ markdown fences."""
    engine = PlanCreatorEngine()

    # 1. JSON bọc trong markdown ```json ... ```
    raw_with_markdown = "```json\n{\"total_scripts\": 1, \"scripts\": [{\"id\": 1}]}\n```"
    parsed = engine._clean_and_parse_json(raw_with_markdown)
    assert parsed["total_scripts"] == 1
    assert len(parsed["scripts"]) == 1

    # 2. JSON có text thừa ở trước và sau
    raw_with_extra = "Dưới đây là kịch bản:\n{\"status\": \"success\"}\nHy vọng bạn hài lòng!"
    parsed = engine._clean_and_parse_json(raw_with_extra)
    assert parsed["status"] == "success"

    # 3. Text sai cú pháp JSON
    try:
        engine._clean_and_parse_json("Đây không phải JSON gì cả")
        assert False, "Lẽ ra phải ném JSONParsingError"
    except JSONParsingError:
        pass

    print("-> PASS: test_clean_and_parse_json")


def test_key_rotation_on_failure():
    """Kiểm tra tính năng xoay vòng key khi gọi API thất bại."""
    keys = ["key-fail-1", "key-success-2"]
    config = PlanCreatorConfig(
        api_keys=keys,
        system_prompt="Prompt test",
        json_structure=SAMPLE_STRUCTURE,
    )
    engine = PlanCreatorEngine(config)

    mock_client = MagicMock()
    call_count = [0]

    def mock_generate_content(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("429 ResourceExhausted Quota Exceeded")
        mock_resp = MagicMock()
        mock_resp.text = json.dumps({"total_scripts": 2, "status": "ok"})
        return mock_resp

    mock_client.models.generate_content.side_effect = mock_generate_content

    with patch("google.genai.Client", return_value=mock_client):
        result = engine.create_plans(SAMPLE_CONTENT, num_scripts=2)
        assert result["status"] == "ok"
        assert result["total_scripts"] == 2
        assert call_count[0] == 2
        # Key fail phải bị đánh dấu failed
        assert "key-fail-1" in engine.key_rotator._failed_keys
        assert engine.key_rotator.available_keys_count() == 1

    print("-> PASS: test_key_rotation_on_failure")


def test_create_plans_success():
    """Kiểm tra luồng tạo kịch bản thành công trả về đúng dict JSON."""
    config = PlanCreatorConfig(
        api_keys=["valid-key"],
        system_prompt="Prompt test",
        json_structure=SAMPLE_STRUCTURE,
    )
    engine = PlanCreatorEngine(config)

    expected_output = {
        "total_scripts": 3,
        "scripts": [
            {"script_id": 1, "title": "Kịch bản Drama", "hook": "Ai bảo lương AI 40 củ sướng?"},
            {"script_id": 2, "title": "Kịch bản Flex", "hook": "Vừa vào công ty đã phát MacBook?"},
            {"script_id": 3, "title": "Kịch bản Review", "hook": "JD TechNova có gì hot?"},
        ]
    }

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(expected_output)
    mock_client.models.generate_content.return_value = mock_resp

    with patch("google.genai.Client", return_value=mock_client):
        result = engine.create_plans(
            json_content=SAMPLE_CONTENT,
            num_scripts=3,
            creative_styles=["Drama", "Flex", "Review"]
        )
        assert result["total_scripts"] == 3
        assert len(result["scripts"]) == 3
        assert result["scripts"][0]["title"] == "Kịch bản Drama"

    print("-> PASS: test_create_plans_success")


def test_user_prompt_template_and_sync():
    """Kiểm tra tính năng template hóa user prompt và đồng bộ hóa giữa các prompt."""
    from app.services.plan_creator.constants import (
        DEFAULT_SYSTEM_PROMPT,
        DEFAULT_USER_PROMPT_TEMPLATE,
    )

    # 1. Kiểm tra System Prompt chứa đầy đủ các nguyên tắc cốt lõi (Single Source of Truth)
    system_core_keywords = [
        "zero hallucination",
        "4 scenes",
        "salary",
        "[cười]",
        "[chuckle]",
        "[thở dài]",
        "[sigh]",
        "[hắng giọng]",
        "[clear throat]",
        "transition",
        "FFmpeg xfade",
        "tao - bay",
        "Ủa alo tin nổi hông",
        "colloquial Vietnamese",
        "58",
        "ZERO TAG HALLUCINATION",
        "Phonetic Transcription",
        "vi-đê-ô",
        "síp-pơ",
        "Abbreviation Expansion",
        "khu công nghiệp",
        "KCN",
    ]
    for kw in system_core_keywords:
        assert kw.lower() in DEFAULT_SYSTEM_PROMPT.lower(), f"Thiếu keyword '{kw}' trong DEFAULT_SYSTEM_PROMPT"

    # Kiểm tra User Prompt Template tuân thủ DRY: không lặp lại luật, chỉ chứa placeholder và chỉ thị thực thi
    user_template_required_elements = [
        "{content_str}",
        "{num_scripts}",
        "{styles_instruction}",
        "{sound_effects_instruction}",
        "{schema_repr}",
        "System Prompt",
        "zero hallucination",
        "phonetic",
    ]
    for elem in user_template_required_elements:
        assert elem.lower() in DEFAULT_USER_PROMPT_TEMPLATE.lower(), f"Thiếu thành phần '{elem}' trong DEFAULT_USER_PROMPT_TEMPLATE"

    # 2. Kiểm tra fallback khi user_prompt_template=None
    config_default = PlanCreatorConfig(
        api_keys=["key1"],
        system_prompt="System prompt",
        json_structure=SAMPLE_STRUCTURE,
    )
    assert config_default.get_user_prompt_template() == DEFAULT_USER_PROMPT_TEMPLATE

    # 3. Kiểm tra tùy biến user_prompt_template
    custom_template = "CUSTOM PROMPT: {content_str} | SCRIPTS: {num_scripts} | SCHEMA: {schema_repr}"
    config_custom = PlanCreatorConfig(
        api_keys=["key1"],
        system_prompt="System prompt",
        json_structure=SAMPLE_STRUCTURE,
        user_prompt_template=custom_template,
    )
    assert config_custom.get_user_prompt_template() == custom_template

    # 4. Kiểm tra _build_prompt_content lắp ráp chính xác
    engine = PlanCreatorEngine(config_custom)
    built_prompt = engine._build_prompt_content(
        config=config_custom,
        content_str='{"job": "Tester"}',
        num_scripts=2,
    )
    assert 'CUSTOM PROMPT: {"job": "Tester"}' in built_prompt
    assert "SCRIPTS: 2" in built_prompt
    assert "SCHEMA:" in built_prompt

    print("-> PASS: test_user_prompt_template_and_sync")


def test_ffmpeg_transitions_completeness():
    """Kiểm tra danh sách 58 hiệu ứng chuyển cảnh FFmpeg xfade đầy đủ, không trùng lặp và đồng bộ."""
    # 1. Kiểm tra số lượng chính xác 58 hiệu ứng chuẩn của filter xfade
    assert len(FFMPEG_TRANSITIONS) == 58, f"Kỳ vọng đúng 58 transition, nhận được: {len(FFMPEG_TRANSITIONS)}"
    assert len(set(FFMPEG_TRANSITIONS)) == 58, "Danh sách FFMPEG_TRANSITIONS không được chứa phần tử trùng lặp!"

    # 2. Kiểm tra các hiệu ứng tiêu chuẩn quan trọng
    expected_samples = [
        "fade", "wipeleft", "wiperight", "wipeup", "wipedown",
        "slideleft", "slideright", "slideup", "slidedown",
        "circlecrop", "rectcrop", "distance", "fadeblack", "fadewhite",
        "radial", "smoothleft", "smoothright", "smoothup", "smoothdown",
        "circleopen", "circleclose", "vertopen", "vertclose",
        "horzopen", "horzclose", "dissolve", "pixelize",
        "diagtl", "diagtr", "diagbl", "diagbr",
        "hlslice", "hrslice", "vuslice", "vdslice",
        "hblur", "fadegrays", "wipetl", "wipetr", "wipebl", "wipebr",
        "squeezeh", "squeezev", "zoomin", "fadefast", "fadeslow",
        "hlwind", "hrwind", "vuwind", "vdwind",
        "coverleft", "coverright", "coverup", "coverdown",
        "revealleft", "revealright", "revealup", "revealdown",
    ]
    for trans in expected_samples:
        assert trans in FFMPEG_TRANSITIONS, f"Hiệu ứng {trans} phải có mặt trong FFMPEG_TRANSITIONS!"

    # 3. Kiểm tra sự hiện diện trong DEFAULT_SYSTEM_PROMPT và DEFAULT_USER_PROMPT_TEMPLATE
    assert "transition" in DEFAULT_SYSTEM_PROMPT
    assert "58" in DEFAULT_SYSTEM_PROMPT
    assert "transition" in DEFAULT_USER_PROMPT_TEMPLATE
    assert "FFmpeg xfade" in DEFAULT_USER_PROMPT_TEMPLATE

    print("-> PASS: test_ffmpeg_transitions_completeness")


def test_platform_policy_compliance_and_slang_rules():
    """Kiểm tra sự hiện diện đầy đủ của 3 chính sách kiểm duyệt nội dung (từ lóng, cấm chuyển hướng, chống phóng đại)."""
    from app.services.plan_creator.constants import (
        DEFAULT_SYSTEM_PROMPT,
        DEFAULT_USER_PROMPT_TEMPLATE,
    )

    # 1. Kiểm tra Policy 1: Banned words & Ethical replacements
    policy_1_keywords = [
        "thành quả xứng đáng",
        "khoản bồi dưỡng",
        "phúc lợi chu đáo",
        "khoản hỗ trợ",
        "đủ tuổi lao động",
        "từ 18 trở lên",
        "giấy tờ tùy thân",
        "tất cả mọi người",
        "CCCD",
        "VNeID",
        "chuyển khoản",
        "tài khoản",
        "lương",
        "tiền",
        "bạc",
    ]
    for kw in policy_1_keywords:
        assert kw.lower() in DEFAULT_SYSTEM_PROMPT.lower(), f"Thiếu keyword từ vựng/cấm '{kw}' trong DEFAULT_SYSTEM_PROMPT"

    # 2. Kiểm tra Policy 2: Zero off-platform traffic redirection trong System Prompt (Source of Truth)
    policy_2_keywords = [
        "ứng tuyển",
        "liên hệ",
        "nhắn tin",
        "inbox",
    ]
    for kw in policy_2_keywords:
        assert kw.lower() in DEFAULT_SYSTEM_PROMPT.lower(), f"Thiếu keyword cấm điều hướng '{kw}' trong DEFAULT_SYSTEM_PROMPT"

    # Kiểm tra bộ từ vựng CTA mới (Comment, Peer-sharing, Bio, Review)
    new_cta_keywords = [
        "thả nhẹ chiếc cmt",
        "tag nhẹ",
        "bio đầu kênh",
        "review dưới bình luận",
    ]
    for kw in new_cta_keywords:
        assert kw.lower() in DEFAULT_SYSTEM_PROMPT.lower(), f"Thiếu keyword CTA mới '{kw}' trong DEFAULT_SYSTEM_PROMPT"

    # 3. Kiểm tra Policy 3: Zero hyperbole / over-promising / urgency trong System Prompt (Source of Truth)
    policy_3_keywords = [
        "gấp",
        "tuyển gấp",
        "cần gấp",
        "100%",
        "đảm bảo",
        "chắc chắn",
        "cam kết",
    ]
    for kw in policy_3_keywords:
        assert kw.lower() in DEFAULT_SYSTEM_PROMPT.lower(), f"Thiếu keyword chống phóng đại '{kw}' trong DEFAULT_SYSTEM_PROMPT"

    # Kiểm tra bộ từ vựng Tính cấp bách mới (Slot scarcity, Real rhythm)
    new_urgency_keywords = [
        "cơ hội tốt số lượng có hạn",
        "slot cuối",
        "chốt sổ",
        "thủ tục gọn gàng",
        "làm việc ngay",
    ]
    for kw in new_urgency_keywords:
        assert kw.lower() in DEFAULT_SYSTEM_PROMPT.lower(), f"Thiếu keyword cấp bách mới '{kw}' trong DEFAULT_SYSTEM_PROMPT"

    # 4. Kiểm tra Policy 4: Anti-Verbatim & Creative Angles (Chống rập khuôn, kích thích sáng tạo)
    creative_keywords = [
        "anti-verbatim",
        "creative angles",
        "zero cross-script repetition",
        "illustrative examples",
    ]
    for kw in creative_keywords:
        assert kw.lower() in DEFAULT_SYSTEM_PROMPT.lower(), f"Thiếu keyword sáng tạo/anti-verbatim '{kw}' trong DEFAULT_SYSTEM_PROMPT"

    # Kiểm tra User Prompt tham chiếu tuân thủ các policy trên
    assert "System Prompt" in DEFAULT_USER_PROMPT_TEMPLATE
    assert "lexicon replacements" in DEFAULT_USER_PROMPT_TEMPLATE
    assert "blindly copy" in DEFAULT_USER_PROMPT_TEMPLATE.lower()

    print("-> PASS: test_platform_policy_compliance_and_slang_rules")


def test_valid_emotion_tags_and_strict_whitelist():
    """Kiểm tra Whitelist đúng 3 nhóm thẻ cảm xúc và quy tắc chống bịa thẻ trong prompt."""
    from app.services.plan_creator.constants import (
        DEFAULT_SYSTEM_PROMPT,
        DEFAULT_USER_PROMPT_TEMPLATE,
        VALID_EMOTION_TAGS,
    )

    # 1. Kiểm tra VALID_EMOTION_TAGS gồm 6 định dạng chuẩn (3 cặp VN / EN)
    expected_tags = {"[cười]", "[chuckle]", "[thở dài]", "[sigh]", "[hắng giọng]", "[clear throat]"}
    assert set(VALID_EMOTION_TAGS) == expected_tags, f"Kỳ vọng {expected_tags}, nhận được {set(VALID_EMOTION_TAGS)}"

    # 2. Kiểm tra các cảnh báo cấm tự bịa thẻ trong System Prompt (Source of Truth)
    anti_hallucination_kw = [
        "ZERO TAG HALLUCINATION",
        "[ngạc nhiên]",
        "[khóc]",
        "[vỗ tay]",
        "AVAILABLE SOUND EFFECTS",
    ]
    for kw in anti_hallucination_kw:
        assert kw in DEFAULT_SYSTEM_PROMPT, f"Thiếu keyword '{kw}' trong DEFAULT_SYSTEM_PROMPT"

    # Kiểm tra User Prompt Template chỉ thị tuân thủ thẻ cảm xúc & sound effects
    assert "audio emotion tags" in DEFAULT_USER_PROMPT_TEMPLATE
    assert "sound effects rules" in DEFAULT_USER_PROMPT_TEMPLATE

    print("-> PASS: test_valid_emotion_tags_and_strict_whitelist")


def test_sanitize_script_tags_enforces_whitelist_and_removes_hallucinated_tags():
    """Kiểm tra hàm sanitize_script_tags loại bỏ sạch thẻ tự bịa và bảo vệ tính toàn vẹn của kịch bản."""
    from app.services.plan_creator.engine import sanitize_script_tags

    # Dữ liệu giả lập đầu ra từ AI chứa cả thẻ hợp lệ và thẻ tự bịa
    mock_ai_output = {
        "total_scripts": 1,
        "scripts": [
            {
                "script_id": 1,
                "scenes": [
                    {
                        "scene_index": 1,
                        # Chứa thẻ hợp lệ [cười], thẻ tự bịa [ngạc nhiên], [khóc] và thẻ sound-effect giả mạo [sound-effect:FakeSoundDoesNotExist.wav]
                        "srt_script": "Ủa alo tin nổi hông [cười] [ngạc nhiên], công việc xịn ghê [khóc] nè mấy bà! [sound-effect:FakeSoundDoesNotExist.wav]",
                    },
                    {
                        "scene_index": 2,
                        # Chứa thẻ hợp lệ [thở dài], thẻ tự bịa [vỗ tay] và sound-effect có thực
                        "srt_script": "Nghĩ lại mà nản [thở dài], hồi xưa bị lừa tiền cọc [vỗ tay] cay cú thiệt chớ! [sound-effect:Ding - Highlight Key Benefit.mp3]",
                    },
                    {
                        "scene_index": 3,
                        # Chứa thẻ sound-effect hợp lệ thứ 2 (vi phạm luật max 1 SFX/script)
                        "srt_script": "Bao ăn ở phòng máy lạnh cực mát [sound-effect:Ta-da - Reveal Workplace Perks.mp3], sướng tê người.",
                    },
                ],
            }
        ],
    }

    sanitized = sanitize_script_tags(mock_ai_output)
    scenes = sanitized["scripts"][0]["scenes"]

    # Scene 1:
    # - [cười] phải được giữ lại
    # - [ngạc nhiên], [khóc] phải bị xóa bỏ
    # - [sound-effect:FakeSoundDoesNotExist.wav] (file không có thực) phải bị xóa bỏ
    s1_text = scenes[0]["srt_script"]
    assert "[cười]" in s1_text, "Thẻ [cười] hợp lệ phải được giữ lại!"
    assert "[ngạc nhiên]" not in s1_text, "Thẻ [ngạc nhiên] tự bịa phải bị loại bỏ!"
    assert "[khóc]" not in s1_text, "Thẻ [khóc] tự bịa phải bị loại bỏ!"
    assert "[sound-effect:FakeSoundDoesNotExist.wav]" not in s1_text, "Thẻ sound effect giả mạo phải bị loại bỏ!"

    assert "Ủa alo tin nổi hông [cười]," in s1_text, f"Dấu phẩy phải được kéo sát sau khi xóa thẻ! Nhận được: {s1_text}"

    # Scene 2:
    # - [thở dài] phải được giữ lại
    # - [vỗ tay] phải bị xóa bỏ
    # - [sound-effect:Ding - Highlight Key Benefit.mp3] là file có thực và là SFX đầu tiên hợp lệ -> giữ lại ở cuối câu
    s2_text = scenes[1]["srt_script"]
    assert "[thở dài]" in s2_text, "Thẻ [thở dài] hợp lệ phải được giữ lại!"
    assert "[vỗ tay]" not in s2_text, "Thẻ [vỗ tay] tự bịa phải bị loại bỏ!"
    assert s2_text.endswith("[sound-effect:Ding - Highlight Key Benefit.mp3]"), f"Thẻ SFX hợp lệ phải nằm ở cuối câu! Nhận được: {s2_text}"

    # Scene 3:
    # - [sound-effect:Ta-da - Reveal Workplace Perks.mp3] phải bị loại bỏ vì Scene 2 đã dùng SFX (luật max 1 SFX/script)
    s3_text = scenes[2]["srt_script"]
    assert "sound-effect" not in s3_text, "Scene 3 không được chứa SFX do vượt quá hạn mức 1 SFX/script!"
    assert "Bao ăn ở phòng máy lạnh cực mát, sướng tê người." in s3_text

    print("-> PASS: test_sanitize_script_tags_enforces_whitelist_and_removes_hallucinated_tags")


if __name__ == "__main__":
    test_invalid_num_scripts()
    test_empty_content_raises_empty_content_error()
    test_config_validation()
    test_no_api_key_available()
    test_clean_and_parse_json()
    test_key_rotation_on_failure()
    test_create_plans_success()
    test_user_prompt_template_and_sync()
    test_ffmpeg_transitions_completeness()
    test_platform_policy_compliance_and_slang_rules()
    test_valid_emotion_tags_and_strict_whitelist()
    test_sanitize_script_tags_enforces_whitelist_and_removes_hallucinated_tags()
    print("\n==================================================")
    print(" TOÀN BỘ UNIT TESTS CỦA PLAN CREATOR ĐÃ VƯỢT QUA! ")
    print("==================================================")
