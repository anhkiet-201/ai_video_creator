import ast
import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from app.services.key_rotator import KeyRotator
from app.services.llm import (
    BaseLLMProvider,
    LLMProviderError,
    LLMQuotaExhaustedError,
    LLMResponseParsingError,
    create_llm_provider,
)
from app.services.plan_creator.constants import FFMPEG_TRANSITIONS, VALID_EMOTION_TAGS
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
from app.services.trending import SocialTrendingService

logger = logging.getLogger(__name__)

# Tập hợp 3 nhóm thẻ cảm xúc chuẩn hóa (lowercase, không có ngoặc vuông)
ALLOWED_EMOTIONS: Set[str] = {
    tag.strip("[]").lower() for tag in VALID_EMOTION_TAGS
}

# Tập hợp hiệu ứng chuyển cảnh hợp lệ và danh sách xoay vòng chống lặp liên tiếp
VALID_TRANSITIONS_SET: Set[str] = set(FFMPEG_TRANSITIONS)
SMOOTH_TRANSITION_ROTATION: Tuple[str, ...] = (
    "fade",
    "slideleft",
    "dissolve",
    "smoothleft",
    "wiperight",
    "circleopen",
    "fadeblack",
    "slideright",
    "smoothright",
)

# 5 Khung Góc Nhìn Vạn Năng (Universal Content Perspectives) thích ứng động cho mọi nội dung/ngành nghề
UNIVERSAL_STORY_PERSPECTIVES: Tuple[str, ...] = (
    "Story Focus 1 (Trải Nghiệm Thao Tác Thực Tế & Một Ngày Làm Việc): Chọn 1 quy trình/công việc cụ thể nhất trong nội dung để kể chi tiết từng bước trải nghiệm thực tế. Tuyệt đối KHÔNG kể lan man sang chế độ ăn uống hay quyền lợi khác ở kịch bản này.",
    "Story Focus 2 (Đãi Ngộ & Điểm Cộng Bất Ngờ): Tập trung DUY NHẤT vào các quyền lợi, hỗ trợ tốt nhất (cơm nước, tiền phụ cấp, máy móc hỗ trợ nhẹ việc, thu nhập trao tay, môi trường mát mẻ). Tuyệt đối KHÔNG kể chi tiết thao tác kỹ thuật ở kịch bản này.",
    "Story Focus 3 (Phản Biện Định Kiến / Bóc Trần Lời Đồn): Đặt vấn đề dưới góc độ người ngoài đồn thổi việc này cực / khó / áp lực vs sự thật trải nghiệm bên trong êm ái, nhẹ nhàng ra sao.",
    "Story Focus 4 (Không Gian, Văn Hóa & Quy Định Đặc Biệt): Tập trung vào môi trường làm việc, sự thoải mái, quy định đặc biệt (an toàn, trang phục, tác phong...) và sự chỉ dẫn nhiệt tình của đồng nghiệp.",
    "Story Focus 5 (Review Thẳng Thắn 100% Không Phông Bạt): Đóng vai đồng nghiệp chia sẻ thật lòng ưu điểm, nhược điểm, chốt lại ai chịu khó và phù hợp thì nên vô ngay.",
)
# Backward-compatible alias
DEFAULT_FACET_ANGLES = UNIVERSAL_STORY_PERSPECTIVES

DEFAULT_OVERLAY_STYLES: Tuple[str, ...] = (
    "bubble_cloud",
    "torn_paper",
    "pastel_multicolor",
    "marshmallow_pink",
    "vlog_doodle",
    "daisy_diary",
    "ocean_chalk",
    "retro_groovy",
    "tropical_contour",
    "grid_notebook",
    "baby_blue",
)

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
    """Lọc và chuẩn hóa toàn bộ thẻ, từ khóa nhạy cảm và hiệu ứng chuyển cảnh trong kịch bản video.

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
    6. Tự động xoay vòng transition nếu các scene liên tiếp bị trùng lặp cùng 1 hiệu ứng chuyển cảnh.
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
        prev_transition: Optional[str] = None

        for scene_idx, scene in enumerate(scenes):
            if not isinstance(scene, dict):
                continue

            # 0. Chuẩn hóa & chống lặp transition giữa các scene liên tiếp
            raw_trans = scene.get("transition")
            if isinstance(raw_trans, str) and raw_trans.strip():
                curr_trans = raw_trans.strip().lower()
                if curr_trans not in VALID_TRANSITIONS_SET:
                    curr_trans = SMOOTH_TRANSITION_ROTATION[scene_idx % len(SMOOTH_TRANSITION_ROTATION)]
                elif prev_transition is not None and curr_trans == prev_transition:
                    for candidate in SMOOTH_TRANSITION_ROTATION:
                        if candidate != prev_transition:
                            curr_trans = candidate
                            break
                scene["transition"] = curr_trans
                prev_transition = curr_trans

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

            # Chuẩn hóa nguyên âm lặp bất thường để Edge-TTS không đọc tách chữ (vd: 'ơiii' -> 'ơi', 'rồiii' -> 'rồi')
            cleaned = re.sub(r"([iIíÍìÌỉỈĩĨịỊyYýÝỳỲỷỶỹỸỵỴ]){2,}", r"\1", cleaned)
            cleaned = re.sub(r"([a-zA-ZÀ-ỹ])\1{2,}", r"\1", cleaned)

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
    - Tự động phân bổ góc tiếp cận (Facet), đại từ, kiểu mở đầu và truyền bộ nhớ chống lặp giữa các kịch bản.
    - Trả về danh sách kịch bản chuẩn định dạng JSON, sẵn sàng cấp cho TTS Engine và Render Overlay.
    """

    def __init__(
        self,
        config: Optional[PlanCreatorConfig] = None,
        key_rotator: Optional[KeyRotator] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
        trending_service: Optional[SocialTrendingService] = None,
    ):
        self.config = config
        self._custom_llm_provider = llm_provider
        self.llm_provider = llm_provider
        self.trending_service = trending_service

        if key_rotator is not None:
            self.key_rotator = key_rotator
        elif config and config.api_keys:
            self.key_rotator = KeyRotator(config.api_keys)
        else:
            self.key_rotator = KeyRotator([])

        if self.llm_provider is None:
            provider_type = config.provider if config else "gemini"
            model_name = config.model_name if config else "gemini-2.5-flash"
            base_url = config.base_url if config else None
            self.llm_provider = create_llm_provider(
                provider_type=provider_type,
                model_name=model_name,
                api_keys=config.api_keys if config else None,
                base_url=base_url,
                key_rotator=self.key_rotator,
            )

    def _resolve_llm_provider(
        self,
        active_config: PlanCreatorConfig,
        override_config: Optional[PlanCreatorConfig] = None,
    ) -> BaseLLMProvider:
        """Lấy provider thích hợp dựa trên active_config và self.llm_provider."""
        if override_config and override_config.api_keys and hasattr(self, "key_rotator"):
            if override_config.api_keys != self.key_rotator._keys:
                self.key_rotator.set_keys(override_config.api_keys)

        # 1. Nếu caller truyền custom provider (ví dụ mock trong unit tests), ưu tiên sử dụng
        if self._custom_llm_provider is not None:
            if hasattr(self._custom_llm_provider, "key_rotator"):
                self._custom_llm_provider.key_rotator = self.key_rotator
            if active_config.model_name:
                self._custom_llm_provider.model_name = active_config.model_name
            return self._custom_llm_provider

        # 2. Kiểm tra nếu provider hiện tại đã đúng loại provider và cấu hình tương ứng
        target_provider = (active_config.provider or "gemini").lower().strip()
        current_provider = getattr(self.llm_provider, "provider_name", None)

        if self.llm_provider is not None and current_provider == target_provider:
            if target_provider == "lm_studio":
                curr_base = getattr(self.llm_provider, "base_url", None)
                target_base = active_config.base_url
                if target_base and curr_base and target_base.rstrip("/").rstrip("/v1") != curr_base.rstrip("/").rstrip("/v1"):
                    pass
                else:
                    if active_config.model_name:
                        self.llm_provider.model_name = active_config.model_name
                    return self.llm_provider
            else:
                if hasattr(self.llm_provider, "key_rotator"):
                    self.llm_provider.key_rotator = self.key_rotator
                if active_config.model_name:
                    self.llm_provider.model_name = active_config.model_name
                return self.llm_provider

        # 3. Tạo mới provider theo đúng active_config
        new_provider = create_llm_provider(
            provider_type=target_provider,
            model_name=active_config.model_name,
            api_keys=active_config.api_keys,
            base_url=active_config.base_url,
            key_rotator=self.key_rotator,
        )
        self.llm_provider = new_provider
        return new_provider

    def create_single_plan(
        self,
        content: Union[Dict[str, Any], str],
        script_index: int = 1,
        total_scripts: int = 1,
        creative_style: Optional[str] = None,
        override_config: Optional[PlanCreatorConfig] = None,
        previous_scripts_summary: Optional[str] = None,
        trends_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Tạo duy nhất 1 kịch bản video từ nội dung văn bản (hoặc JSON) qua 1 request Gemini AI.

        Args:
            content: Dữ liệu nội dung bài đăng/thông tin công ty cần review (chuỗi văn bản hoặc dict).
            script_index: Chỉ số thứ tự của kịch bản này (1-based, mặc định: 1).
            total_scripts: Tổng số kịch bản dự kiến tạo trong mẻ (mặc định: 1).
            creative_style: Phong cách/góc tiếp cận cụ thể cho kịch bản này (tùy chọn).
            override_config: Cấu hình ghi đè nếu muốn thay đổi config lúc gọi hàm.
            previous_scripts_summary: Bản tóm tắt chống lặp từ các kịch bản trước trong cùng mẻ (tùy chọn).
            trends_context: Bối cảnh sự việc/drama bão mạng xã hội thời gian thực (tùy chọn).

        Returns:
            Dict[str, Any]: Dữ liệu 1 kịch bản video (single script object) đã làm sạch thẻ.
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
        provider = self._resolve_llm_provider(active_config, override_config=override_config)
        if (active_config.provider or "").lower().strip() == "gemini":
            rotator = getattr(provider, "key_rotator", self.key_rotator)
            if not rotator or not rotator.has_available_keys():
                raise NoValidApiKeyError(
                    "Không tìm thấy Gemini API Key khả dụng hoặc danh sách api_keys rỗng. "
                    "Vui lòng cung cấp ít nhất một API Key hợp lệ."
                )

        # 2.1 Context phụ trợ (nếu có cấu hình cụ thể)
        if trends_context is None:
            if active_config and getattr(active_config, "realtime_trends", None):
                trends_context = active_config.realtime_trends
            else:
                trends_context = ""

        # 3. Xây dựng prompt cho single plan & gọi Gemini AI có cơ chế xoay vòng key
        prompt_content = self._build_single_plan_prompt_content(
            config=active_config,
            content_str=content_str,
            script_index=script_index,
            total_scripts=total_scripts,
            creative_style=creative_style,
            previous_scripts_summary=previous_scripts_summary,
            trends_context=trends_context,
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
        """Tạo danh sách các kịch bản video bằng cách gửi từng request Gemini kèm bộ nhớ chống lặp."""
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
        provider = self._resolve_llm_provider(active_config, override_config=override_config)
        if (active_config.provider or "").lower().strip() == "gemini":
            rotator = getattr(provider, "key_rotator", self.key_rotator)
            if not rotator or not rotator.has_available_keys():
                raise NoValidApiKeyError(
                    "Không tìm thấy Gemini API Key khả dụng hoặc danh sách api_keys rỗng. "
                    "Vui lòng cung cấp ít nhất một API Key hợp lệ."
                )

        # 5. Context phụ trợ (nếu có cấu hình cụ thể)
        batch_trends_context = ""
        if active_config and getattr(active_config, "realtime_trends", None):
            batch_trends_context = active_config.realtime_trends

        # 6. Lặp qua từng kịch bản, truyền Cross-Script Memory Digest để chống lặp tuyệt đối
        all_scripts: List[Dict[str, Any]] = []
        for i in range(1, num_scripts + 1):
            current_style: Optional[str] = None
            if creative_styles:
                current_style = creative_styles[(i - 1) % len(creative_styles)]

            prev_summary = self._build_previous_scripts_digest(all_scripts)

            single_script = self.create_single_plan(
                content=content_str,
                script_index=i,
                total_scripts=num_scripts,
                creative_style=current_style,
                override_config=active_config,
                previous_scripts_summary=prev_summary,
                trends_context=batch_trends_context,
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

    @staticmethod
    def _build_previous_scripts_digest(previous_scripts: List[Dict[str, Any]]) -> str:
        """Trích xuất bản tóm tắt siêu gọn (~30-50 tokens) từ các kịch bản đã sinh để chống lặp."""
        if not previous_scripts:
            return ""

        used_pronouns: List[str] = []
        used_styles: List[str] = []
        used_openers: List[str] = []
        used_titles: List[str] = []
        used_sfx: List[str] = []

        for idx, sc in enumerate(previous_scripts, start=1):
            if not isinstance(sc, dict):
                continue
            pronoun = str(sc.get("selected_pronoun_pair") or "").strip()
            if pronoun and pronoun not in used_pronouns:
                used_pronouns.append(pronoun)

            ov_style = str(sc.get("overlay_style") or "").strip()
            if ov_style and ov_style not in used_styles:
                used_styles.append(ov_style)

            scenes = sc.get("scenes")
            if isinstance(scenes, list) and scenes:
                first_scene = scenes[0] if isinstance(scenes[0], dict) else {}
                first_srt = str(first_scene.get("srt_script") or "").strip()
                if first_srt:
                    opener_snippet = " ".join(first_srt.split()[:8])
                    used_openers.append(f"#{idx}: '{opener_snippet}...'")

                for body_sc in scenes[1:4]:
                    if isinstance(body_sc, dict):
                        t = str(body_sc.get("title") or "").strip()
                        if t and t not in used_titles:
                            used_titles.append(t)

                for any_sc in scenes:
                    if isinstance(any_sc, dict):
                        raw_srt = str(any_sc.get("srt_script") or "")
                        m = re.search(r"\[sound-effect:\s*([^\]]+)\]", raw_srt)
                        if m:
                            sfx_val = m.group(1).strip()
                            if sfx_val and sfx_val not in used_sfx:
                                used_sfx.append(sfx_val)

        digest_parts: List[str] = []
        if used_pronouns:
            digest_parts.append(f"used pronouns={used_pronouns}")
        if used_styles:
            digest_parts.append(f"used overlay_styles={used_styles}")
        if used_openers:
            digest_parts.append(
                f"used openers=[{', '.join(used_openers)}] (MANDATORY: Scene 1 must use a DIFFERENT hook angle and opener wording from these)"
            )
        if used_titles:
            digest_parts.append(f"used scene titles={used_titles[:6]}")
        if used_sfx:
            digest_parts.append(f"used sound_effects={used_sfx}")

        if not digest_parts:
            return ""

        return (
            "- ANTI-REPETITION LOCK (DO NOT repeat these from previous scripts in this batch): "
            + "; ".join(digest_parts)
            + "."
        )

    def _serialize_content(self, content: Union[Dict[str, Any], str]) -> str:
        """Chuyển đổi và nén dữ liệu đầu vào thành chuỗi văn bản gọn nhẹ, tiết kiệm token."""
        if isinstance(content, dict):
            if not content:
                return ""
            cleaned_dict = {
                k: v for k, v in content.items()
                if v is not None and v != "" and v != [] and v != {}
            }
            if not cleaned_dict:
                return ""
            return json.dumps(cleaned_dict, ensure_ascii=False, separators=(", ", ": "))
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
                f"- Creative angles / styles requested: [{styles_str}]. "
                f"Distribute these styles across the scripts for maximum diversity."
            )

        from app.services.video_render_engine.sound_effect_manager import format_sound_effects_for_prompt

        sfx_dir = getattr(config, "sound_effects_dir", None)
        sound_effects_instruction = format_sound_effects_for_prompt(sfx_dir)

        template = config.get_user_prompt_template()
        return (
            template
            .replace("{content_str}", content_str)
            .replace("{realtime_internet_trends}", "")
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
        previous_scripts_summary: Optional[str] = None,
        trends_context: Optional[str] = None,
    ) -> str:
        """Xây dựng nội dung yêu cầu cho 1 kịch bản video đơn lẻ kèm phân bổ đa dạng & chống lặp."""
        schema_repr = config.get_single_plan_json_structure_str()

        idx_zero = max(0, script_index - 1)
        assigned_facet = UNIVERSAL_STORY_PERSPECTIVES[idx_zero % len(UNIVERSAL_STORY_PERSPECTIVES)]
        suggested_overlay = DEFAULT_OVERLAY_STYLES[idx_zero % len(DEFAULT_OVERLAY_STYLES)]

        rustic_hook_archetypes = [
            (
                "Đập tan định kiến vất vả (Myth-Busting Heavy Labor)",
                "Ai bảo đi làm xưởng motor dầu mỡ lem luốc cực khổ lắm là chưa bước chân vô đây rồi, dàn máy tự động nó gánh hết trơn nè anh em ơi!",
                "Đập tan nỗi sợ bưng bê nặng nhọc hay dầu mỡ lem luốc bằng thực tế dàn máy tự động làm hết việc nặng.",
            ),
            (
                "Tâm sự anh em tìm việc (Sincere Job-Search Peer Talk)",
                "Mấy bữa nay ai đang lận đận kiếm việc mà chưa biết đi đâu về đâu thì ghé mắt ngó qua cái xưởng này thử coi nha, việc nhàn mà êm lắm!",
                "Tâm sự đồng cảm với người đang tìm việc, rủ rê anh em bạn bè ngó qua cơ hội thực tế, không tô vẽ.",
            ),
            (
                "Mắt thấy tai nghe / Trực quan dàn máy (First-Hand Machinery Relief)",
                "Bước chân vô xưởng nhìn dàn máy chạy ro ro gá phôi lẹ làng mà tui khoái cái bụng ghê, tay chân sạch bóng không dính tí dầu mỡ nào luôn!",
                "Trực tiếp chứng kiến xưởng thoáng mát, máy móc làm việc nhịp nhàng, bản thân chỉ đứng canh nhẹ nhõm.",
            ),
            (
                "Nỗi niềm cơm nước & đãi ngộ (Meal & Daily Welfare Reassurance)",
                "Đi làm xưởng điều anh em mình lo nhất là cơm nước lèo tèo với hụt hơi đúng không, qua đây trưa có cơm nóng sốt dẻo bao no tận răng nha!",
                "Đi thẳng vào mối lo ăn no, cơm trưa công ty lo chu đáo, ca kíp rõ ràng an tâm.",
            ),
            (
                "Bộc trực, thẳng thắn review thật (Candid Direct Walkthrough)",
                "Nói thiệt một câu cho anh em biết đường tính nha! Chỗ này việc có máy lo nên khỏe re, chỉ có điều nhớ xỏ đôi giày nghiêm chỉnh là vô làm ngon lành!",
                "Nói thẳng điều kiện thực tế (nhắc nhẹ quy định mang giày bảo hộ), chân thật 100% không phông bạt.",
            ),
        ]

        assigned_hook_name, assigned_hook_example, assigned_hook_guide = rustic_hook_archetypes[
            idx_zero % len(rustic_hook_archetypes)
        ]

        hook_directive = (
            f"Scene 1 Rustic & Authentic Hook Directive:\n"
            f"  * ASSIGNED RUSTIC HOOK ANGLE FOR THIS SCRIPT: {assigned_hook_name}\n"
            f"  * GUIDANCE: {assigned_hook_guide}\n"
            f"  * NATURAL SPOKEN EXAMPLE: \"{assigned_hook_example}\"\n"
            f"  * ABSOLUTE PROHIBITION ON NEWS & INTERNET DRAMA (STRICT BAN): "
            f"STRICTLY FORBIDDEN to mention social media trends, memes, internet drama, viral buzz, or news reporting. "
            f"NEVER say 'Trên mạng rần rần...', 'Bão mạng drama...', 'Dự án ma...', 'Mấy bữa nay trend...', 'Tin tức...'. "
            f"Talk 100% like a genuine coworker or peer sharing sincere, down-to-earth workplace experiences over coffee!\n"
            f"  * ANTI-FRANKENSTEIN & AUTHENTIC REALITY: "
            f"Describe factory parts, equipment, meals, and tasks 100% accurately as in the input facts. "
            f"NEVER combine unrelated words or fabricate fake details. Keep it grounded, rustic, and relatable."
        )

        directive_lines: List[str] = [
            f"- Assigned Story Focus: {assigned_facet}",
            f"- {hook_directive}",
            "- Pronoun Selection: Choose ONE natural speaker - listener pair from PILLAR 6 §1 that best fits the audience and vibe of this content (e.g. 'tui - mấy bà', 'mình - cả nhà', 'tui - anh em', 'tui - mấy bồ', 'em - cả nhà'). Lock it 100% throughout the script.",
            f"- Suggested overlay_style: '{suggested_overlay}'.",
            "- Scene 1 'title' MUST be a punchy UPPERCASE HOOK HEADLINE (3-6 words, e.g. BƯỚC VÔ MỚI BẬT NGỬA, CÓ ĐỈNH NHƯ LỜI ĐỒN?, NÉ BÃO MẠNG VÔ ĐÂY). NEVER use company name as title.",
            "- Strictly stick ONLY to the Assigned Story Perspective. Absolutely do NOT dump or summarize all facts into one script.",
        ]
        if creative_style and creative_style.strip():
            directive_lines.append(
                f"- Creative angle / style requested: \"{creative_style.strip()}\" (embody deeply throughout the script)."
            )
        if previous_scripts_summary and previous_scripts_summary.strip():
            directive_lines.append(previous_scripts_summary.strip())

        styles_instruction = "\n".join(directive_lines)

        from app.services.video_render_engine.sound_effect_manager import format_sound_effects_for_prompt

        sfx_dir = getattr(config, "sound_effects_dir", None)
        sound_effects_instruction = format_sound_effects_for_prompt(sfx_dir)

        trends_str = (trends_context or "").strip()

        template = config.get_single_plan_user_prompt_template()
        return (
            template
            .replace("{content_str}", content_str)
            .replace("{realtime_internet_trends}", trends_str)
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
                target["script_id"] = script_index
                target["scenes"] = self._normalize_scenes_list(target.get("scenes"))
                return target

        # 2. Nếu AI trả về trực tiếp Single Script Object chứa 'scenes'
        if "scenes" in raw_result and isinstance(raw_result["scenes"], list):
            raw_result["script_id"] = script_index
            raw_result["scenes"] = self._normalize_scenes_list(raw_result.get("scenes"))
            return raw_result

        # 3. Duyệt tìm object con chứa 'scenes'
        for v in raw_result.values():
            if isinstance(v, dict) and "scenes" in v:
                v["script_id"] = script_index
                v["scenes"] = self._normalize_scenes_list(v.get("scenes"))
                return v

        # 4. Fallback an toàn cho mock hoặc custom payload
        raw_result["script_id"] = script_index
        if "scenes" in raw_result:
            raw_result["scenes"] = self._normalize_scenes_list(raw_result.get("scenes"))
        return raw_result

    def _execute_with_rotation(
        self,
        config: PlanCreatorConfig,
        prompt_content: str,
    ) -> Dict[str, Any]:
        """Thực hiện gọi API qua LLM Provider với cơ chế bắt lỗi chuẩn hóa."""
        provider = self._resolve_llm_provider(config)

        if (config.provider or "").lower().strip() == "gemini":
            rotator = getattr(provider, "key_rotator", self.key_rotator)
            if not rotator or not rotator.has_available_keys():
                raise NoValidApiKeyError(
                    "Không tìm thấy Gemini API Key khả dụng hoặc danh sách api_keys rỗng. "
                    "Vui lòng cung cấp ít nhất một API Key hợp lệ."
                )

        max_parse_retries = 2
        for attempt in range(max_parse_retries + 1):
            try:
                return provider.generate_json(
                    prompt=prompt_content,
                    system_prompt=config.system_prompt,
                    temperature=config.temperature,
                )
            except LLMQuotaExhaustedError as e:
                raise NoValidApiKeyError(str(e)) from e
            except LLMResponseParsingError as e:
                if attempt < max_parse_retries:
                    logger.warning(
                        f"Phản hồi LLM lỗi cú pháp JSON (lần thử {attempt + 1}/{max_parse_retries + 1}), đang tự động thử lại: {e}"
                    )
                    continue
                raise JSONParsingError(str(e)) from e
            except LLMProviderError as e:
                raise PlanCreatorError(str(e)) from e

    def _clean_and_parse_json(self, raw_text: str) -> Dict[str, Any]:
        """Làm sạch văn bản và phân tích cú pháp chuỗi JSON an toàn."""
        try:
            if self.llm_provider:
                return self.llm_provider.clean_and_parse_json(raw_text)
            from app.services.llm.base import BaseLLMProvider
            return BaseLLMProvider.clean_and_parse_json(self.llm_provider, raw_text)
        except (LLMResponseParsingError, Exception) as e:
            if isinstance(e, JSONParsingError):
                raise
            raise JSONParsingError(f"Phản hồi từ AI không đúng định dạng JSON hợp lệ: {e}") from e
