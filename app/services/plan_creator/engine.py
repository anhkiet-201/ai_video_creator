import ast
import json
import logging
import random
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

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

# Pattern nhận diện emoji và các biểu tượng đồ họa Unicode
EMOJI_PATTERN = re.compile(
    r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]|[\u2b50-\u2b55]|[\ufe00-\ufe0f]|[\u200d]"
)

# Pattern nhận diện các ký tự đặc biệt không thể phát âm đối với engine TTS
UNPRONOUNCEABLE_PATTERN = re.compile(r"[*#@~^_|<>/\\=+–—$%`\"'{}()]")

# Import API làm sạch từ khóa nhạy cảm duy nhất từ module sensitive_rules chuyên trách
from app.services.plan_creator.sensitive_rules import clean_sensitive_text


def sanitize_script_tags(
    data: Dict[str, Any],
    sounds_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Lọc và chuẩn hóa toàn bộ thẻ trong srt_script của các kịch bản video.

    Hỗ trợ linh hoạt cả 2 định dạng đầu vào:
    1. Dict bọc danh sách kịch bản: {"total_scripts": N, "scripts": [...]}
    2. Single Script Object: {"script_id": 1, "scenes": [...]}

    Đảm bảo tuyệt đối:
    1. Chỉ giữ lại đúng 3 nhóm thẻ cảm xúc: [cười]/[chuckle], [thở dài]/[sigh], [hắng giọng]/[clear throat].
       Mọi thẻ trong ngoặc vuông tự bịa khác ([ngạc nhiên], [khóc], [vỗ tay]...) bị loại bỏ sạch sẽ.
    2. Thẻ [sound-effect:<filename>] chỉ giữ lại nếu tệp âm thanh thực sự tồn tại trong kho hiệu ứng.
       Thẻ âm thanh tự bịa (ví dụ [sound-effect:Boom.wav], [sound-effect:Cash.mp3]...) bị xóa bỏ.
    3. Luật tối đa 1 sound-effect trên mỗi script: Nếu có nhiều scene chứa sound-effect, chỉ giữ
       lại thẻ hợp lệ đầu tiên, các scene còn lại sẽ bị loại bỏ thẻ sound-effect.
    4. Thẻ sound-effect hợp lệ luôn được đưa về cuối câu srt_script (LAW 1: POSITION).
    5. Tuyệt đối không chứa emoji, icon biểu cảm hoặc ký tự đặc biệt không thể phát âm (*, #, @, ~, ^, _, |, etc.).
    """
    if not isinstance(data, dict):
        return data

    from app.services.video_render_engine.sound_effect_manager import (
        find_sound_effect_file,
        parse_sound_effect_tag,
    )

    scripts = data.get("scripts")
    if isinstance(scripts, list):
        script_items = scripts
    elif isinstance(data.get("scenes"), list):
        script_items = [data]
    else:
        return data

    bracket_pattern = re.compile(r"\[([^\]]+)\]")

    for script in script_items:
        if not isinstance(script, dict):
            continue

        raw_scenes = script.get("scenes")
        scenes = PlanCreatorEngine._normalize_scenes_list(raw_scenes)
        script["scenes"] = scenes
        if not isinstance(scenes, list):
            continue

        script_has_sfx = False

        for scene in scenes:
            if not isinstance(scene, dict):
                continue

            # 1. Làm sạch title và sub_title tránh bot OCR quét từ khóa nhạy cảm
            raw_title = scene.get("title")
            if isinstance(raw_title, str) and raw_title.strip():
                scene["title"] = clean_sensitive_text(raw_title, uppercase=True)

            raw_sub_title = scene.get("sub_title")
            if isinstance(raw_sub_title, str) and raw_sub_title.strip():
                scene["sub_title"] = clean_sensitive_text(raw_sub_title, uppercase=False)

            # 2. Làm sạch srt_script
            raw_script = scene.get("srt_script")
            if not isinstance(raw_script, str) or not raw_script.strip():
                continue

            # Phòng vệ: Loại bỏ hoàn toàn nếu lọt chuỗi code dict vào raw_script
            if "{" in raw_script and ("scene_index" in raw_script or "srt_script" in raw_script):
                dict_m = re.search(r"['\"]srt_script['\"]\s*:\s*['\"]([^'\"]+)['\"]", raw_script)
                if dict_m:
                    raw_script = dict_m.group(1).strip()
                else:
                    raw_script = re.sub(r"\{[^{}]*\}", "", raw_script).strip()

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

            # Loại bỏ emoji và biểu tượng đồ họa Unicode
            cleaned = EMOJI_PATTERN.sub(" ", cleaned)

            # Loại bỏ các ký tự đặc biệt không thể phát âm đối với engine TTS
            cleaned = UNPRONOUNCEABLE_PATTERN.sub(" ", cleaned)

            # 3. Làm sạch toàn bộ từ khóa nhạy cảm qua API duy nhất clean_sensitive_text
            cleaned = clean_sensitive_text(cleaned, uppercase=False)

            # Nếu scene được cấp sound-effect hợp lệ, gán ở cuối câu (LAW 1)
            if scene_sfx_filename:
                clean_no_sfx, _ = parse_sound_effect_tag(cleaned)
                cleaned = f"{clean_no_sfx} [sound-effect:{scene_sfx_filename}]".strip()

            scene["srt_script"] = cleaned

    return data


class PlanCreatorEngine:
    """Engine chuyên lên kịch bản video ngắn từ dữ liệu JSON bằng Gemini AI.

    Đặc điểm kiến trúc:
    - Nhận dữ liệu nội dung đầu vào (content) và số lượng kịch bản mong muốn (num_scripts).
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

    def create_single_plan(
        self,
        content: Union[Dict[str, Any], str],
        script_index: int = 1,
        total_scripts: int = 1,
        creative_style: Optional[str] = None,
        override_config: Optional[PlanCreatorConfig] = None,
    ) -> Dict[str, Any]:
        """Tạo duy nhất 1 kịch bản video từ nội dung văn bản (hoặc JSON) qua 1 request Gemini AI.

        Args:
            content: Dữ liệu nội dung bài đăng/tin tuyển dụng (chuỗi văn bản hoặc dict).
            script_index: Chỉ số thứ tự của kịch bản này (1-based, mặc định: 1).
            total_scripts: Tổng số kịch bản dự kiến tạo trong mẻ (mặc định: 1).
            creative_style: Phong cách/góc tiếp cận cụ thể cho kịch bản này (tùy chọn).
            override_config: Cấu hình ghi đè nếu muốn thay đổi config lúc gọi hàm.

        Returns:
            Dict[str, Any]: Dữ liệu 1 kịch bản video (single script object) đã làm sạch thẻ.

        Raises:
            EmptyContentError: Nếu nội dung rỗng hoặc không hợp lệ.
            MissingSystemPromptError: Nếu thiếu system_prompt.
            MissingJsonStructureError: Nếu thiếu cấu trúc json_structure.
            NoValidApiKeyError: Nếu không có API key hợp lệ hoặc toàn bộ key hết hạn mức.
            JSONParsingError: Nếu AI trả về kết quả không parse được sang JSON.
            PlanCreatorError: Các lỗi hệ thống khác.
        """
        # 0. Kiểm tra tính hợp lệ ban đầu của content
        if content is None:
            raise EmptyContentError("Nội dung đầu vào không được để trống!")

        content_str = self._serialize_content(content)
        if not content_str or not content_str.strip():
            raise EmptyContentError("Nội dung đầu vào không được để trống!")

        # 1. Xác định config áp dụng
        active_config = override_config or self.config
        if not active_config:
            raise PlanCreatorError("Chưa cung cấp cấu hình PlanCreatorConfig cho PlanCreatorEngine!")

        if not active_config.system_prompt or not active_config.system_prompt.strip():
            raise MissingSystemPromptError("system_prompt không được để trống trong cấu hình!")

        if not active_config.json_structure:
            raise MissingJsonStructureError("json_structure không được để trống trong cấu hình!")

        # 2. Đồng bộ danh sách API Keys vào KeyRotator nếu có override khác với hiện tại
        if override_config and override_config.api_keys:
            if override_config.api_keys != self.key_rotator._keys:
                self.key_rotator.set_keys(override_config.api_keys)

        if not self.key_rotator.has_available_keys():
            raise NoValidApiKeyError(
                "Không tìm thấy Gemini API Key khả dụng hoặc danh sách api_keys rỗng. "
                "Vui lòng cung cấp ít nhất một API Key hợp lệ."
            )

        # 3. Xây dựng prompt cho single plan & gọi Gemini AI có cơ chế xoay vòng key
        prompt_content = self._build_single_plan_prompt_content(
            config=active_config,
            content_str=content_str,
            script_index=script_index,
            total_scripts=total_scripts,
            creative_style=creative_style,
        )
        raw_result = self._execute_with_rotation(active_config, prompt_content)
        single_script = self._extract_single_script_data(raw_result, script_index=script_index)

        return sanitize_script_tags(
            data=single_script,
            sounds_dir=getattr(active_config, "sound_effects_dir", None),
        )

    def create_plans(
        self,
        content: Union[Dict[str, Any], str],
        num_scripts: int = 1,
        creative_styles: Optional[List[str]] = None,
        override_config: Optional[PlanCreatorConfig] = None,
        on_progress: Optional[Callable[[int, int, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Tạo danh sách các kịch bản video bằng cách gửi từng request Gemini cho mỗi kịch bản.

        Args:
            content: Dữ liệu nội dung bài đăng/tin tuyển dụng (chuỗi văn bản hoặc dict).
            num_scripts: Số lượng kịch bản cần tạo (mặc định: 1, phải > 0).
            creative_styles: Danh sách các phong cách/góc tiếp cận tùy chọn (ví dụ: ["Drama", "Hài hước"]).
            override_config: Cấu hình ghi đè nếu muốn thay đổi config lúc gọi hàm.
            on_progress: Callback tùy chọn nhận (script_index, total_scripts, script_data) khi từng plan hoàn thành.

        Returns:
            Dict[str, Any]: Danh sách kịch bản theo đúng cấu trúc JSON chuẩn {"total_scripts": N, "scripts": [...]}.

        Raises:
            EmptyContentError: Nếu nội dung rỗng hoặc không hợp lệ.
            InvalidNumScriptsError: Nếu num_scripts <= 0.
            MissingSystemPromptError: Nếu thiếu system_prompt.
            MissingJsonStructureError: Nếu thiếu cấu trúc json_structure.
            NoValidApiKeyError: Nếu không có API key hợp lệ hoặc toàn bộ key hết hạn mức.
            JSONParsingError: Nếu AI trả về kết quả không parse được sang JSON.
            PlanCreatorError: Các lỗi hệ thống khác.
        """
        # 0. Kiểm tra tính hợp lệ ban đầu của content
        if content is None:
            raise EmptyContentError("Nội dung đầu vào không được để trống!")

        # 1. Guard Clause: Kiểm tra num_scripts
        if not isinstance(num_scripts, int) or num_scripts <= 0:
            raise InvalidNumScriptsError(f"Số lượng kịch bản num_scripts phải là số nguyên dương lớn hơn 0 (nhận được: {num_scripts})")

        # 2. Guard Clause: Kiểm tra tính hợp lệ của content
        content_str = self._serialize_content(content)
        if not content_str or not content_str.strip():
            raise EmptyContentError("Nội dung đầu vào không được để trống!")

        # 3. Xác định config áp dụng
        active_config = override_config or self.config
        if not active_config:
            raise PlanCreatorError("Chưa cung cấp cấu hình PlanCreatorConfig cho PlanCreatorEngine!")

        if not active_config.system_prompt or not active_config.system_prompt.strip():
            raise MissingSystemPromptError("system_prompt không được để trống trong cấu hình!")

        if not active_config.json_structure:
            raise MissingJsonStructureError("json_structure không được để trống trong cấu hình!")

        # 4. Đồng bộ danh sách API Keys vào KeyRotator nếu có override khác với hiện tại
        if override_config and override_config.api_keys:
            if override_config.api_keys != self.key_rotator._keys:
                self.key_rotator.set_keys(override_config.api_keys)

        if not self.key_rotator.has_available_keys():
            raise NoValidApiKeyError(
                "Không tìm thấy Gemini API Key khả dụng hoặc danh sách api_keys rỗng. "
                "Vui lòng cung cấp ít nhất một API Key hợp lệ."
            )

        # 5. Lặp qua từng kịch bản, mỗi kịch bản là 1 request Gemini AI độc lập
        all_scripts: List[Dict[str, Any]] = []
        for i in range(1, num_scripts + 1):
            # Phân bổ phong cách sáng tạo riêng cho kịch bản thứ i (nếu có)
            current_style: Optional[str] = None
            if creative_styles:
                current_style = creative_styles[(i - 1) % len(creative_styles)]

            single_script = self.create_single_plan(
                content=content_str,
                script_index=i,
                total_scripts=num_scripts,
                creative_style=current_style,
                override_config=active_config,
            )
            all_scripts.append(single_script)

            if on_progress is not None:
                try:
                    on_progress(i, num_scripts, single_script)
                except Exception as e:
                    logger.warning(f"Lỗi trong callback on_progress kịch bản {i}/{num_scripts}: {e}")

        return {
            "total_scripts": len(all_scripts),
            "scripts": all_scripts,
        }

    def _serialize_content(self, content: Union[Dict[str, Any], str]) -> str:
        """Chuyển đổi dữ liệu đầu vào thành chuỗi nội dung văn bản hoặc chuỗi JSON."""
        if isinstance(content, dict):
            if not content:
                return ""
            return json.dumps(content, ensure_ascii=False, indent=2)
        if isinstance(content, str):
            stripped = content.strip()
            if not stripped or stripped in ("{}", "[]"):
                return ""
            return stripped
        raise EmptyContentError(f"Nội dung đầu vào phải là chuỗi văn bản hoặc dict, nhận được: {type(content).__name__}")

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
            .replace("{script_index}", "1")
            .replace("{total_scripts}", str(num_scripts))
            .replace("{num_scripts}", str(num_scripts))
            .replace("{styles_instruction}", styles_instruction)
            .replace("{sound_effects_instruction}", sound_effects_instruction)
            .replace("{schema_repr}", schema_repr)
        )

    def _build_single_plan_prompt_content(
        self,
        config: PlanCreatorConfig,
        content_str: str,
        script_index: int,
        total_scripts: int,
        creative_style: Optional[str] = None,
    ) -> str:
        """Xây dựng nội dung yêu cầu cho 1 kịch bản video đơn lẻ gửi cho Gemini AI."""
        schema_repr = config.get_single_plan_json_structure_str()

        styles_instruction = ""
        if creative_style and creative_style.strip():
            styles_instruction = (
                f"- Creative angle / style requested: \"{creative_style.strip()}\".\n"
                f"  Embody this specific tone and perspective deeply throughout the script."
            )

        from app.services.video_render_engine.sound_effect_manager import format_sound_effects_for_prompt

        sfx_dir = getattr(config, "sound_effects_dir", None)
        sound_effects_instruction = format_sound_effects_for_prompt(sfx_dir)

        template = config.get_single_plan_user_prompt_template()
        return (
            template
            .replace("{content_str}", content_str)
            .replace("{script_index}", str(script_index))
            .replace("{total_scripts}", str(total_scripts))
            .replace("{num_scripts}", "1")
            .replace("{styles_instruction}", styles_instruction)
            .replace("{sound_effects_instruction}", sound_effects_instruction)
            .replace("{schema_repr}", schema_repr)
        )

    @staticmethod
    def _normalize_scenes_list(raw_scenes: Any) -> List[Dict[str, Any]]:
        """Chuẩn hóa danh sách scenes, tự động bóc tách nếu AI trả về chuỗi dict lồng/gộp."""
        if not raw_scenes:
            return []

        if isinstance(raw_scenes, dict):
            raw_scenes = [raw_scenes]
        elif isinstance(raw_scenes, str):
            raw_scenes = [raw_scenes]
        elif not isinstance(raw_scenes, (list, tuple)):
            return []

        normalized: List[Dict[str, Any]] = []

        for item in raw_scenes:
            if isinstance(item, dict):
                normalized.append(item)
            elif isinstance(item, str):
                item_str = item.strip()
                if not item_str:
                    continue

                extracted_dicts: List[Dict[str, Any]] = []
                # Kiểm tra nếu chuỗi chứa cấu trúc dict (ví dụ: {'scene_index': ...} hoặc {"scene_index": ...})
                if "{" in item_str and "}" in item_str:
                    dict_pattern = re.compile(r"\{[^{}]*\}")
                    for m in dict_pattern.finditer(item_str):
                        block = m.group(0).strip()
                        # 1. Thử parse qua ast.literal_eval (hỗ trợ nháy đơn của Python dict)
                        try:
                            val = ast.literal_eval(block)
                            if isinstance(val, dict):
                                extracted_dicts.append(val)
                                continue
                        except Exception:
                            pass
                        # 2. Thử parse qua json.loads
                        try:
                            val = json.loads(block)
                            if isinstance(val, dict):
                                extracted_dicts.append(val)
                                continue
                        except Exception:
                            pass

                if extracted_dicts:
                    normalized.extend(extracted_dicts)
                else:
                    normalized.append({
                        "title": item_str[:30],
                        "sub_title": "",
                        "srt_script": item_str,
                        "transition": "fade",
                    })

        for idx, sc in enumerate(normalized, start=1):
            if isinstance(sc, dict):
                sc.setdefault("scene_index", idx)

        return normalized

    def _extract_single_script_data(
        self,
        raw_result: Dict[str, Any],
        script_index: int = 1,
    ) -> Dict[str, Any]:
        """Chuẩn hóa dữ liệu kịch bản đơn lẻ từ phản hồi của Gemini AI."""
        if not isinstance(raw_result, dict):
            raise JSONParsingError(f"Phản hồi từ AI phải là một đối tượng dict, nhận được: {type(raw_result).__name__}")

        # 1. Nếu AI bọc trong danh sách 'scripts'
        if "scripts" in raw_result and isinstance(raw_result["scripts"], list) and raw_result["scripts"]:
            idx = script_index - 1
            if 0 <= idx < len(raw_result["scripts"]):
                target = raw_result["scripts"][idx]
            else:
                target = raw_result["scripts"][0]
            if isinstance(target, dict):
                target.setdefault("script_id", script_index)
                target["scenes"] = self._normalize_scenes_list(target.get("scenes"))
                return target

        # 2. Nếu AI trả về trực tiếp Single Script Object chứa 'scenes'
        if "scenes" in raw_result and isinstance(raw_result["scenes"], list):
            raw_result.setdefault("script_id", script_index)
            raw_result["scenes"] = self._normalize_scenes_list(raw_result.get("scenes"))
            return raw_result

        # 3. Duyệt tìm object con chứa 'scenes'
        for v in raw_result.values():
            if isinstance(v, dict) and "scenes" in v:
                v.setdefault("script_id", script_index)
                v["scenes"] = self._normalize_scenes_list(v.get("scenes"))
                return v

        # 4. Fallback an toàn cho mock hoặc custom payload
        raw_result.setdefault("script_id", script_index)
        if "scenes" in raw_result:
            raw_result["scenes"] = self._normalize_scenes_list(raw_result.get("scenes"))
        return raw_result

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

        # Loại bỏ các định dạng comment vô tình phát sinh từ AI (// comment hoặc /* comment */)
        text = re.sub(r"//.*", "", text)
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # Thử làm sạch unquoted keys (ví dụ _comment: "...") và trailing commas (, ] hoặc , }) và parse lại
            cleaned_text = re.sub(r"([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1"\2":', text)
            cleaned_text = re.sub(r",\s*([\]\}])", r"\1", cleaned_text)
            try:
                parsed = json.loads(cleaned_text)
            except Exception as e:
                logger.error(f"Không thể parse JSON từ AI output: {text[:200]}... Lỗi: {e}")
                raise JSONParsingError(f"Phản hồi từ AI không đúng định dạng JSON hợp lệ: {e}") from e

        if not isinstance(parsed, dict):
            raise JSONParsingError(
                f"Dữ liệu JSON trả về phải là một Object (dict), nhận được: {type(parsed).__name__}"
            )
        return parsed
