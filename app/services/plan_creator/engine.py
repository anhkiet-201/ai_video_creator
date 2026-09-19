import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from app.services.key_rotator import KeyRotator
from app.services.plan_creator.constants import VALID_EMOTION_TAGS
from app.services.plan_creator.exceptions import (
    EmptyContentError,
    InvalidNumScriptsError,
    JSONParsingError,
    MissingJsonStructureError,
    MissingSystemPromptError,
    NoValidApiKeyError,
    PlanCreatorError,
)
from app.services.plan_creator.models import PlanCreatorConfig

logger = logging.getLogger(__name__)

# Tập hợp 3 nhóm thẻ cảm xúc chuẩn hóa (lowercase, không có ngoặc vuông)
ALLOWED_EMOTIONS: Set[str] = {
    tag.strip("[]").lower() for tag in VALID_EMOTION_TAGS
}


def sanitize_script_tags(
    data: Dict[str, Any],
    sounds_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Lọc và chuẩn hóa toàn bộ thẻ trong srt_script của các kịch bản video.

    Đảm bảo tuyệt đối:
    1. Chỉ giữ lại đúng 3 nhóm thẻ cảm xúc: [cười]/[chuckle], [thở dài]/[sigh], [hắng giọng]/[clear throat].
       Mọi thẻ trong ngoặc vuông tự bịa khác ([ngạc nhiên], [khóc], [vỗ tay]...) bị loại bỏ sạch sẽ.
    2. Thẻ [sound-effect:<filename>] chỉ giữ lại nếu tệp âm thanh thực sự tồn tại trong kho hiệu ứng.
       Thẻ âm thanh tự bịa (ví dụ [sound-effect:Boom.wav], [sound-effect:Cash.mp3]...) bị xóa bỏ.
    3. Luật tối đa 1 sound-effect trên mỗi script: Nếu có nhiều scene chứa sound-effect, chỉ giữ
       lại thẻ hợp lệ đầu tiên, các scene còn lại sẽ bị loại bỏ thẻ sound-effect.
    4. Thẻ sound-effect hợp lệ luôn được đưa về cuối câu srt_script (LAW 1: POSITION).
    """
    if not isinstance(data, dict):
        return data

    from app.services.video_render_engine.sound_effect_manager import (
        find_sound_effect_file,
        parse_sound_effect_tag,
    )

    scripts = data.get("scripts")
    if not isinstance(scripts, list):
        return data

    bracket_pattern = re.compile(r"\[([^\]]+)\]")

    for script in scripts:
        if not isinstance(script, dict):
            continue

        scenes = script.get("scenes")
        if not isinstance(scenes, list):
            continue

        script_has_sfx = False

        for scene in scenes:
            if not isinstance(scene, dict):
                continue

            raw_script = scene.get("srt_script")
            if not isinstance(raw_script, str) or not raw_script.strip():
                continue

            scene_sfx_filename: Optional[str] = None

            def _filter_tag(match: re.Match) -> str:
                nonlocal scene_sfx_filename, script_has_sfx
                inner = match.group(1).strip()
                inner_lower = inner.lower()

                # Kiểm tra thẻ sound-effect
                if inner_lower.startswith("sound-effect:"):
                    sfx_name = inner[len("sound-effect:"):].strip()
                    sfx_path = find_sound_effect_file(sfx_name, sounds_dir=sounds_dir) if sfx_name else None
                    if sfx_path is not None and not script_has_sfx:
                        script_has_sfx = True
                        scene_sfx_filename = sfx_path.name
                    # Xóa thẻ sfx tại vị trí hiện tại để sau đó đính về cuối câu
                    return ""

                # Kiểm tra thẻ cảm xúc hợp lệ
                if inner_lower in ALLOWED_EMOTIONS:
                    return f"[{inner_lower}]"

                # Thẻ tự bịa (hallucination tag) -> xóa bỏ hoàn toàn
                logger.info(f"Loại bỏ thẻ lạ tự bịa khỏi kịch bản: '[{inner}]'")
                return ""

            cleaned = bracket_pattern.sub(_filter_tag, raw_script)

            # Chuẩn hóa khoảng trắng và dấu câu
            cleaned = re.sub(r"\s+([,\.!\?:;\-])", r"\1", cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()

            # Nếu scene được cấp sound-effect hợp lệ, gán ở cuối câu (LAW 1)
            if scene_sfx_filename:
                clean_no_sfx, _ = parse_sound_effect_tag(cleaned)
                cleaned = f"{clean_no_sfx} [sound-effect:{scene_sfx_filename}]".strip()

            scene["srt_script"] = cleaned

    return data


class PlanCreatorEngine:
    """Engine chuyên lên kịch bản video ngắn từ dữ liệu JSON bằng Gemini AI.

    Đặc điểm kiến trúc:
    - Nhận dữ liệu nội dung đầu vào (json_content) và số lượng kịch bản mong muốn (num_scripts).
    - Tự động xoay vòng API Keys qua KeyRotator khi gặp lỗi Quota (429) hoặc mạng.
    - Nhận system_prompt và json_structure linh hoạt theo yêu cầu nghiệp vụ.
    - Trả về danh sách kịch bản chuẩn định dạng JSON, sẵn sàng cấp cho TTS Engine và Render Overlay.
    """

    def __init__(
        self,
        config: Optional[PlanCreatorConfig] = None,
        key_rotator: Optional[KeyRotator] = None,
    ):
        self.config = config
        if key_rotator is not None:
            self.key_rotator = key_rotator
        elif config and config.api_keys:
            self.key_rotator = KeyRotator(config.api_keys)
        else:
            self.key_rotator = KeyRotator([])

    def create_plans(
        self,
        json_content: Union[Dict[str, Any], str],
        num_scripts: int = 1,
        creative_styles: Optional[List[str]] = None,
        override_config: Optional[PlanCreatorConfig] = None,
    ) -> Dict[str, Any]:
        """Tạo danh sách các kịch bản video từ dữ liệu JSON content.

        Args:
            json_content: Dữ liệu nội dung có cấu trúc (dưới dạng dict hoặc chuỗi JSON).
            num_scripts: Số lượng kịch bản cần tạo (mặc định: 1, phải > 0).
            creative_styles: Danh sách các phong cách/góc tiếp cận tùy chọn (ví dụ: ["Drama", "Hài hước"]).
            override_config: Cấu hình ghi đè nếu muốn thay đổi config lúc gọi hàm.

        Returns:
            Dict[str, Any]: Danh sách kịch bản theo đúng cấu trúc JSON mong muốn.

        Raises:
            EmptyContentError: Nếu json_content rỗng hoặc không hợp lệ.
            InvalidNumScriptsError: Nếu num_scripts <= 0.
            MissingSystemPromptError: Nếu thiếu system_prompt.
            MissingJsonStructureError: Nếu thiếu cấu trúc json_structure.
            NoValidApiKeyError: Nếu không có API key hợp lệ hoặc toàn bộ key hết hạn mức.
            JSONParsingError: Nếu AI trả về kết quả không parse được sang JSON.
            PlanCreatorError: Các lỗi hệ thống khác.
        """
        # 1. Guard Clause: Kiểm tra num_scripts
        if not isinstance(num_scripts, int) or num_scripts <= 0:
            raise InvalidNumScriptsError(f"Số lượng kịch bản num_scripts phải là số nguyên dương lớn hơn 0 (nhận được: {num_scripts})")

        # 2. Guard Clause: Kiểm tra tính hợp lệ của json_content
        content_str = self._serialize_content(json_content)
        if not content_str or not content_str.strip():
            raise EmptyContentError("Nội dung json_content đầu vào không được để trống!")

        # 3. Xác định config áp dụng
        active_config = override_config or self.config
        if not active_config:
            raise PlanCreatorError("Chưa cung cấp cấu hình PlanCreatorConfig cho PlanCreatorEngine!")

        if not active_config.system_prompt or not active_config.system_prompt.strip():
            raise MissingSystemPromptError("system_prompt không được để trống trong cấu hình!")

        if not active_config.json_structure:
            raise MissingJsonStructureError("json_structure không được để trống trong cấu hình!")

        # 4. Đồng bộ danh sách API Keys vào KeyRotator nếu có override
        if override_config and override_config.api_keys:
            self.key_rotator.set_keys(override_config.api_keys)

        if not self.key_rotator.has_available_keys():
            raise NoValidApiKeyError(
                "Không tìm thấy Gemini API Key khả dụng hoặc danh sách api_keys rỗng. "
                "Vui lòng cung cấp ít nhất một API Key hợp lệ."
            )

        # 5. Xây dựng prompt & gọi Gemini AI có cơ chế xoay vòng key
        prompt_content = self._build_prompt_content(
            config=active_config,
            content_str=content_str,
            num_scripts=num_scripts,
            creative_styles=creative_styles,
        )
        raw_result = self._execute_with_rotation(active_config, prompt_content)
        return sanitize_script_tags(
            data=raw_result,
            sounds_dir=getattr(active_config, "sound_effects_dir", None),
        )

    def _serialize_content(self, content: Union[Dict[str, Any], str]) -> str:
        """Chuyển đổi dữ liệu đầu vào thành chuỗi JSON định dạng chuẩn."""
        if isinstance(content, dict):
            if not content:
                return ""
            return json.dumps(content, ensure_ascii=False, indent=2)
        if isinstance(content, str):
            stripped = content.strip()
            if not stripped:
                return ""
            # Thử parse JSON nếu là string JSON để kiểm tra tính hợp lệ
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict) and not parsed:
                    return ""
            except json.JSONDecodeError:
                pass
            return stripped
        raise EmptyContentError(f"json_content phải là dict hoặc chuỗi JSON, nhận được: {type(content).__name__}")

    def _build_prompt_content(
        self,
        config: PlanCreatorConfig,
        content_str: str,
        num_scripts: int,
        creative_styles: Optional[List[str]] = None,
    ) -> str:
        """Xây dựng nội dung yêu cầu gửi cho Gemini AI."""
        schema_repr = config.get_json_structure_str()

        styles_instruction = ""
        if creative_styles:
            styles_str = ", ".join(f'"{s}"' for s in creative_styles)
            styles_instruction = (
                f"- Creative angles / styles requested: [{styles_str}].\n"
                f"  Distribute these styles across the scripts for maximum diversity."
            )

        from app.services.video_render_engine.sound_effect_manager import format_sound_effects_for_prompt

        sfx_dir = getattr(config, "sound_effects_dir", None)
        sound_effects_instruction = format_sound_effects_for_prompt(sfx_dir)

        template = config.get_user_prompt_template()
        return (
            template
            .replace("{content_str}", content_str)
            .replace("{num_scripts}", str(num_scripts))
            .replace("{styles_instruction}", styles_instruction)
            .replace("{sound_effects_instruction}", sound_effects_instruction)
            .replace("{schema_repr}", schema_repr)
        )

    def _execute_with_rotation(
        self,
        config: PlanCreatorConfig,
        prompt_content: str,
    ) -> Dict[str, Any]:
        """Thực hiện gọi API qua Google GenAI SDK với cơ chế xoay vòng key và bắt lỗi."""
        last_error_reason: str = ""

        while self.key_rotator.has_available_keys():
            current_key = self.key_rotator.get_current_key()
            if not current_key:
                break

            masked_key = f"...{current_key[-6:]}" if len(current_key) >= 6 else current_key

            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=current_key)
                response = client.models.generate_content(
                    model=config.model_name,
                    contents=prompt_content,
                    config=types.GenerateContentConfig(
                        system_instruction=config.system_prompt,
                        response_mime_type="application/json",
                        temperature=config.temperature,
                    ),
                )

                if response and response.text:
                    return self._clean_and_parse_json(response.text)

                last_error_reason = "Phản hồi từ Gemini API rỗng (response.text is empty)."
                logger.warning(f"Phản hồi rỗng khi gọi model {config.model_name} với key {masked_key}")

            except JSONParsingError:
                # Lỗi cú pháp JSON do AI sinh ra sai
                raise
            except Exception as e:
                err_msg = str(e)
                last_error_reason = err_msg
                logger.warning(f"Lỗi khi lên kịch bản với key {masked_key}: {err_msg}")
                self.key_rotator.mark_key_failed(current_key, reason=err_msg)

        raise NoValidApiKeyError(
            f"Không thể lên kịch bản bằng AI: Toàn bộ API Key trong danh sách đã bị lỗi quota hoặc hết hạn mức. "
            f"Lỗi gần nhất: {last_error_reason}"
        )

    def _clean_and_parse_json(self, raw_text: str) -> Dict[str, Any]:
        """Làm sạch văn bản và phân tích cú pháp chuỗi JSON an toàn."""
        text = raw_text.strip()

        # Loại bỏ markdown code fences nếu AI vô tình sinh ra (```json ... ```)
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # Tìm kiếm khối JSON hợp lệ nằm giữa cặp ngoặc nhọn ngoài cùng
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

        try:
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise JSONParsingError(
                    f"Dữ liệu JSON trả về phải là một Object (dict), nhận được: {type(parsed).__name__}"
                )
            return parsed
        except (json.JSONDecodeError, JSONParsingError) as e:
            logger.error(f"Không thể parse JSON từ AI output: {text[:200]}... Lỗi: {e}")
            raise JSONParsingError(f"Phản hồi từ AI không đúng định dạng JSON hợp lệ: {e}") from e
