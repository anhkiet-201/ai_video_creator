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
        assert result["total_scripts"] == 2
        assert len(result["scripts"]) == 2
        assert result["scripts"][0]["status"] == "ok"
        assert call_count[0] == 3
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
            content=SAMPLE_CONTENT,
            num_scripts=3,
            creative_styles=["Drama", "Flex", "Review"]
        )
        assert mock_client.models.generate_content.call_count == 3
        assert result["total_scripts"] == 3
        assert len(result["scripts"]) == 3
        assert result["scripts"][0]["title"] == "Kịch bản Drama"

    print("-> PASS: test_create_plans_success")


def test_raw_user_input_content():
    """Kiểm tra PlanCreatorEngine tiếp nhận trực tiếp chuỗi văn bản thô (raw text) từ người dùng."""
    config = PlanCreatorConfig(
        api_keys=["valid-key"],
        system_prompt="Prompt test",
        json_structure=SAMPLE_STRUCTURE,
    )
    engine = PlanCreatorEngine(config)

    raw_user_posting = (
        "Tuyển nhân viên đóng gói tại KCN VSIP 2A Bình Dương. "
        "Yêu cầu đủ 18 tuổi trở lên, mang theo căn cước công dân phô tô nhận việc ngay. "
        "Giờ làm 8 tiếng rõ ràng, hỗ trợ cơm trưa, phụ cấp chuyên cần đầy đủ."
    )

    expected_output = {
        "total_scripts": 1,
        "scripts": [
            {
                "script_id": 1,
                "title": "KCN VSIP 2A",
                "scenes": [
                    {
                        "scene_index": 0,
                        "title": "ĐÓNG GÓI VSIP 2A",
                        "srt_script": "Bây ơi bây xem chỗ này nè nha.",
                        "transition": "fade",
                    }
                ],
            }
        ],
    }

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(expected_output)
    mock_client.models.generate_content.return_value = mock_resp

    with patch("google.genai.Client", return_value=mock_client):
        # Test truyền qua tham số 'content' với raw text
        res1 = engine.create_plans(content=raw_user_posting, num_scripts=1)
        assert res1["total_scripts"] == 1
        assert len(res1["scripts"]) == 1

        # Kiểm tra nội dung prompt gửi cho Gemini chứa chính xác raw text của user
        call_args = mock_client.models.generate_content.call_args
        sent_contents = call_args.kwargs.get("contents") or (call_args.args[1] if len(call_args.args) > 1 else "")
        assert "KCN VSIP 2A Bình Dương" in str(sent_contents)

    print("-> PASS: test_raw_user_input_content")


def test_create_single_plan():
    """Kiểm tra gọi trực tiếp create_single_plan sinh ra đúng 1 kịch bản đơn lẻ."""
    config = PlanCreatorConfig(
        api_keys=["valid-key"],
        system_prompt="Prompt test",
        json_structure=SAMPLE_STRUCTURE,
    )
    engine = PlanCreatorEngine(config)

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps({
        "script_id": 1,
        "title": "Kịch bản Độc Lập",
        "scenes": [
            {
                "scene_index": 1,
                "title": "XƯỞNG GHẾ MÂY",
                "sub_title": "Đan lát tỉ mỉ",
                "srt_script": "Bà con cô bác vào đây làm việc nha [cười].",
                "transition": "fade",
            }
        ]
    })
    mock_client.models.generate_content.return_value = mock_resp

    with patch("google.genai.Client", return_value=mock_client):
        res = engine.create_single_plan(
            content=SAMPLE_CONTENT,
            script_index=1,
            total_scripts=1,
            creative_style="Hài hước",
        )
        assert res["script_id"] == 1
        assert res["title"] == "Kịch bản Độc Lập"
        assert len(res["scenes"]) == 1
        assert "[cười]" in res["scenes"][0]["srt_script"]
    print("-> PASS: test_create_single_plan")


def test_create_plans_each_request_is_one_plan():
    """Kiểm tra create_plans gọi mỗi request là 1 plan độc lập và kích hoạt on_progress callback."""
    config = PlanCreatorConfig(
        api_keys=["valid-key"],
        system_prompt="Prompt test",
        json_structure=SAMPLE_STRUCTURE,
    )
    engine = PlanCreatorEngine(config)

    mock_client = MagicMock()

    def mock_gen(*args, **kwargs):
        resp = MagicMock()
        resp.text = json.dumps({
            "title": "Kịch bản test",
            "scenes": [
                {
                    "scene_index": 1,
                    "title": "LẮP RÁP BẮN VÍT",
                    "sub_title": "Việc làm đều đặn",
                    "srt_script": "Công việc ổn định anh em cùng tham gia nhé.",
                    "transition": "fade",
                }
            ]
        })
        return resp

    mock_client.models.generate_content.side_effect = mock_gen

    progress_calls = []

    def on_prog(idx, total, script):
        progress_calls.append((idx, total, script.get("title")))

    with patch("google.genai.Client", return_value=mock_client):
        res = engine.create_plans(
            content=SAMPLE_CONTENT,
            num_scripts=3,
            creative_styles=["Style 1", "Style 2", "Style 3"],
            on_progress=on_prog,
        )

        assert mock_client.models.generate_content.call_count == 3
        assert res["total_scripts"] == 3
        assert len(res["scripts"]) == 3
        assert len(progress_calls) == 3
        assert progress_calls[0] == (1, 3, "Kịch bản test")
        assert progress_calls[1] == (2, 3, "Kịch bản test")
        assert progress_calls[2] == (3, 3, "Kịch bản test")
    print("-> PASS: test_create_plans_each_request_is_one_plan")


def test_user_prompt_template_and_sync():
    """Kiểm tra tính năng template hóa user prompt và đồng bộ hóa giữa các prompt theo 5 trụ cột."""
    from app.services.plan_creator.constants import (
        DEFAULT_SYSTEM_PROMPT,
        DEFAULT_USER_PROMPT_TEMPLATE,
    )

    # 1. Kiểm tra System Prompt chứa đầy đủ 5 trụ cột và các nguyên tắc cốt lõi
    system_core_keywords = [
        "PILLAR 1",
        "ROLE & PERSONA",
        "PILLAR 2",
        "TARGET AUDIENCE",
        "PILLAR 3",
        "OBJECTIVES",
        "PILLAR 4",
        "RULES & CONSTRAINTS",
        "PILLAR 5",
        "SCRIPT STRUCTURE",
        "zero hallucination",
        "5 to 7 scenes",
        "[cười]",
        "[chuckle]",
        "[thở dài]",
        "[sigh]",
        "[hắng giọng]",
        "[clear throat]",
        "transition",
        "FFmpeg xfade",
        "58",
        "ZERO TAG HALLUCINATION",
        "Phonetic",
        "Abbreviation",
        "zero emojis",
        "unpronounceable",
        "accented vietnamese",
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
        "zero hallucination",
        "phonetic",
        "zero emojis",
        "5-pillar",
        "accented vietnamese",
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
    """Kiểm tra sự hiện diện đầy đủ của các rào chắn kiểm duyệt nền tảng (Policy Firewalls) theo 5 trụ cột."""
    from app.services.plan_creator.constants import (
        DEFAULT_SYSTEM_PROMPT,
        DEFAULT_USER_PROMPT_TEMPLATE,
    )

    # 1. Kiểm tra Policy 1: Banned concepts (Không phân biệt giới tính, độ tuổi, không PII/thủ tục)
    policy_1_concepts = [
        "zero gender",
        "zero age",
        "omit all pii",
        "personal paperwork",
        "instant money",
        "scam",
    ]
    for concept in policy_1_concepts:
        assert concept.lower() in DEFAULT_SYSTEM_PROMPT.lower(), f"Thiếu concept cấm '{concept}' trong DEFAULT_SYSTEM_PROMPT"

    # 2. Kiểm tra Policy 2: Cấm điều hướng và vũ khí
    policy_2_concepts = [
        "safe peer redirection",
        "weapon",
        "firearms",
    ]
    for concept in policy_2_concepts:
        assert concept.lower() in DEFAULT_SYSTEM_PROMPT.lower(), f"Thiếu concept cấm '{concept}' trong DEFAULT_SYSTEM_PROMPT"

    # 3. Kiểm tra Policy 3: Chống phóng đại & chuẩn mực ngôn từ đời thường
    policy_3_concepts = [
        "anti-hyperbole",
        "administrative",
        "corporate bulletin",
        "anti-verbatim",
    ]
    for concept in policy_3_concepts:
        assert concept.lower() in DEFAULT_SYSTEM_PROMPT.lower(), f"Thiếu concept phong cách '{concept}' trong DEFAULT_SYSTEM_PROMPT"

    # 4. Kiểm tra User Prompt tham chiếu tuân thủ 5-Pillar instructions
    assert "5-pillar" in DEFAULT_USER_PROMPT_TEMPLATE.lower()
    assert "zero hallucination" in DEFAULT_USER_PROMPT_TEMPLATE.lower()
    assert "zero gender" in DEFAULT_USER_PROMPT_TEMPLATE.lower()
    assert "zero age" in DEFAULT_USER_PROMPT_TEMPLATE.lower()

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


def test_sanitize_script_tags_removes_emojis_and_unpronounceable_chars():
    """Kiểm tra sanitize_script_tags loại bỏ sạch sẽ mọi emoji và ký tự đặc biệt không thể phát âm."""
    from app.services.plan_creator.engine import sanitize_script_tags

    mock_ai_output = {
        "total_scripts": 1,
        "scripts": [
            {
                "script_id": 1,
                "scenes": [
                    {
                        "scene_index": 1,
                        # Chứa nhiều emoji (🔥, 👍, 😊, 🚀, ❤️) và ký tự rác (*, #, @, ~, ^, _, |, <, >)
                        "srt_script": "Bây ơi bây 🔥 xem chỗ này nè nha! 👍 #tuyenviec *cực hot* ~đỉnh~ @team [cười] phô-tô và vi-đê-ô.",
                    },
                    {
                        "scene_index": 2,
                        # Chứa ngoặc đơn, gạch dưới, dấu bằng và icon
                        "srt_script": "Lương tháng ổn áp (rất chuẩn chỉ) _chuẩn_ 100% = ngon lành 🌟 [thở dài].",
                    },
                ],
            }
        ],
    }

    sanitized = sanitize_script_tags(mock_ai_output)
    s1_text = sanitized["scripts"][0]["scenes"][0]["srt_script"]
    s2_text = sanitized["scripts"][0]["scenes"][1]["srt_script"]

    # 1. Kiểm tra không còn emoji
    for emoji_char in ["🔥", "👍", "😊", "🚀", "❤️", "🌟"]:
        assert emoji_char not in s1_text, f"Emoji {emoji_char} chưa bị loại bỏ khỏi srt_script!"
        assert emoji_char not in s2_text, f"Emoji {emoji_char} chưa bị loại bỏ khỏi srt_script!"

    # 2. Kiểm tra không còn ký tự đặc biệt rác
    for special_char in ["*", "#", "@", "~", "^", "_", "|", "=", "(", ")"]:
        assert special_char not in s1_text, f"Ký tự đặc biệt {special_char} chưa bị loại bỏ!"
        assert special_char not in s2_text, f"Ký tự đặc biệt {special_char} chưa bị loại bỏ!"

    # 3. Kiểm tra các từ ngữ, dấu câu ngắt nghỉ tự nhiên và từ ghép phiên âm được bảo tồn
    assert "Bây ơi bây xem chỗ này nè nha!" in s1_text
    assert "tuyenviec cực hot đỉnh team [cười] phô-tô và vi-đê-ô." in s1_text
    assert "Lương tháng ổn áp rất chuẩn chỉ chuẩn 100 ngon lành [thở dài]." in s2_text

    print("-> PASS: test_sanitize_script_tags_removes_emojis_and_unpronounceable_chars")


def test_sanitize_script_tags_removes_gun_and_sensitive_words():
    """Kiểm tra sanitize_script_tags tự động loại bỏ từ 'súng', 'cày cuốc', 'xoay vòng vốn' và chuẩn hóa an toàn."""
    from app.services.plan_creator.engine import sanitize_script_tags

    mock_data = {
        "total_scripts": 1,
        "scripts": [
            {
                "script_id": 1,
                "scenes": [
                    {
                        "scene_index": 1,
                        "title": "ƯU TIÊN BẮN SÚNG VÍT",
                        "sub_title": "Nam nữ biết sử dụng súng vít nhận việc ngay",
                        "srt_script": "Ai có tay nghề bắn súng vít cực đỉnh thì ứng tuyển ngay, công ty đang tuyển dụng cần thợ nhận thiếu tháng từ 2008, lương lđpt 240k ngày công và 40 nghìn tăng ca, ai thích cày cuốc để xoay vòng vốn thoải mái nha.",
                    }
                ],
            }
        ],
    }

    sanitized = sanitize_script_tags(mock_data)
    scene = sanitized["scripts"][0]["scenes"][0]

    # Kiểm tra title không còn 'súng'
    assert "SÚNG" not in scene["title"], f"Từ 'SÚNG' vẫn còn trong title: {scene['title']}"
    assert any(word in scene["title"] for word in ["BẮN VÍT", "SIẾT VÍT"]), f"Kỳ vọng BẮN VÍT hoặc SIẾT VÍT trong title, nhận được: {scene['title']}"

    # Kiểm tra sub_title không còn 'súng'
    assert "súng" not in scene["sub_title"].lower(), f"Từ 'súng' vẫn còn trong sub_title: {scene['sub_title']}"

    # Kiểm tra srt_script không còn 'súng', 'cày cuốc', 'xoay vòng vốn', 'ứng tuyển', 'tuyển dụng', 'vào việc ngay', '2008', 'nghìn', 'ngàn', 'k'
    srt_text = scene["srt_script"]
    assert "súng" not in srt_text.lower(), f"Từ 'súng' vẫn còn trong srt_script: {srt_text}"
    assert "bắn vít" in srt_text.lower(), f"Kỳ vọng 'bắn vít' trong srt_script: {srt_text}"
    assert "cày cuốc" not in srt_text.lower(), f"Từ 'cày cuốc' vẫn còn trong srt_script: {srt_text}"
    assert "xoay vòng vốn" not in srt_text.lower(), f"Từ 'xoay vòng vốn' vẫn còn trong srt_script: {srt_text}"
    assert "ứng tuyển" not in srt_text.lower(), f"Từ 'ứng tuyển' vẫn còn trong srt_script: {srt_text}"
    assert "tuyển dụng" not in srt_text.lower(), f"Từ 'tuyển dụng' vẫn còn trong srt_script: {srt_text}"
    assert "vào việc ngay" not in srt_text.lower(), f"Cụm từ 'vào việc ngay' không nên xuất hiện: {srt_text}"
    assert "nhận việc" in srt_text.lower(), f"Kỳ vọng 'nhận việc' trong srt_script: {srt_text}"
    assert "tìm người" in srt_text.lower(), f"Kỳ vọng 'tìm người' trong srt_script: {srt_text}"
    assert "2008" not in srt_text, f"Năm sinh 2008 vẫn còn trong srt_script: {srt_text}"
    assert "nghìn" not in srt_text.lower(), f"Từ 'nghìn' chưa được chuyển sang 'cành': {srt_text}"
    assert "ngàn" not in srt_text.lower(), f"Từ 'ngàn' chưa được chuyển sang 'cành': {srt_text}"
    assert "240k" not in srt_text.lower(), f"Cụm '240k' chưa được chuyển sang '240 cành': {srt_text}"
    assert "240 cành" in srt_text.lower(), f"Kỳ vọng '240 cành' trong srt_script: {srt_text}"
    assert "40 cành" in srt_text.lower(), f"Kỳ vọng '40 cành' trong srt_script: {srt_text}"

    print("-> PASS: test_sanitize_script_tags_removes_gun_and_sensitive_words")


def test_sensitive_rules_module_and_random_choice():
    """Kiểm tra tính toàn vẹn của module sensitive_rules với duy nhất 1 Dict SENSITIVE_REPLACEMENTS và 1 hàm clean_sensitive_text."""
    from app.services.plan_creator.sensitive_rules import (
        SENSITIVE_REPLACEMENTS,
        clean_sensitive_text,
    )
    from app.services.plan_creator import (
        SENSITIVE_REPLACEMENTS as EXPORTED_REPLACEMENTS,
        clean_sensitive_text as exported_clean_sensitive_text,
    )

    # Đảm bảo re-export đúng
    assert SENSITIVE_REPLACEMENTS is EXPORTED_REPLACEMENTS
    assert clean_sensitive_text is exported_clean_sensitive_text

    # Kiểm tra cấu trúc Dict[Tuple[str, ...], List[str]] duy nhất
    assert isinstance(SENSITIVE_REPLACEMENTS, dict)
    for patterns, replacements in SENSITIVE_REPLACEMENTS.items():
        assert isinstance(patterns, tuple), f"Key phải là tuple regex: {patterns}"
        assert isinstance(replacements, list), f"Value phải là list từ thay thế: {replacements}"
        assert len(patterns) > 0

    # Kiểm tra clean_sensitive_text (API duy nhất)
    from app.services.plan_creator.sensitive_rules import clean_sensitive_text
    
    # 1. Quy tắc chỉ cần xóa từ súng (áp dụng cho mọi trường hợp súng, súng vít, súng đinh...)
    assert clean_sensitive_text("Bắn súng vít chuyên nghiệp") == "Bắn vít chuyên nghiệp"
    assert clean_sensitive_text("Thao tác bắn súng") == "Thao tác bắn"
    assert clean_sensitive_text("Dùng súng vít để làm") == "Dùng vít để làm"
    assert clean_sensitive_text("Dùng súng bắn đinh") == "Dùng bắn đinh"
    assert clean_sensitive_text("Cầm súng đi làm") == "Cầm đi làm"

    # 2. Quy tắc năm sinh & thiếu tháng
    assert clean_sensitive_text("Nhận thiếu tháng từ 2008") == "tất cả anh em"
    assert "2008" not in clean_sensitive_text("Sinh năm 2008 hoặc 2k8")
    assert "2k8" not in clean_sensitive_text("Sinh năm 2008 hoặc 2k8")

    # 3. Quy tắc tiền tệ & mức lương tự nhiên (không từ ngữ ngô nghê hay cờ bạc)
    assert clean_sensitive_text("Lương 240k ngày công") == "lúa 240 cành ngày công"
    assert clean_sensitive_text("Tăng ca 40 nghìn một giờ") == "Tăng ca 40 cành một giờ"
    assert clean_sensitive_text("Tiền tăng ca 40 nghìn một giờ") == "lúa tăng ca 40 cành một giờ"
    assert clean_sensitive_text("Lương 200 ngàn") == "lúa 200 cành"
    # 4. Quy tắc Title Safeguard: Cấm triệt để từ giật tít tiền bạc / lúa / lương trên tiêu đề video
    t1 = clean_sensitive_text("LÃNH LƯƠNG 3 NGÀY 1 LẦN", uppercase=True)
    assert "LÚA" not in t1 and "LƯƠNG" not in t1 and "TIỀN" not in t1
    assert "CÔNG VIỆC" in t1 or "VIỆC LÀM" in t1

    t2 = clean_sensitive_text("LỊCH TRẢ LƯƠNG ĐỀU ĐẶN", uppercase=True)
    assert "LÚA" not in t2 and "LƯƠNG" not in t2 and "TIỀN" not in t2
    assert "CÔNG VIỆC" in t2 or "VIỆC LÀM" in t2

    print("-> PASS: test_sensitive_rules_module_and_random_choice")


if __name__ == "__main__":
    test_invalid_num_scripts()
    test_empty_content_raises_empty_content_error()
    test_config_validation()
    test_no_api_key_available()
    test_clean_and_parse_json()
    test_key_rotation_on_failure()
    test_create_plans_success()
    test_create_single_plan()
    test_create_plans_each_request_is_one_plan()
    test_raw_user_input_content()
    test_user_prompt_template_and_sync()
    test_ffmpeg_transitions_completeness()
    test_platform_policy_compliance_and_slang_rules()
    test_valid_emotion_tags_and_strict_whitelist()
    test_sanitize_script_tags_enforces_whitelist_and_removes_hallucinated_tags()
    test_sanitize_script_tags_removes_emojis_and_unpronounceable_chars()
    test_sanitize_script_tags_removes_gun_and_sensitive_words()
    test_sensitive_rules_module_and_random_choice()
    print("\n==================================================")
    print(" TOÀN BỘ UNIT TESTS CỦA PLAN CREATOR ĐÃ VƯỢT QUA! ")
    print("==================================================")
