"""Video Creation Pipeline Coordinator.

Điều phối luồng sản xuất video tự động 5 bước tuân thủ Clean Architecture & SOLID:
1. Nhận Content & Video Source Path (Input & Validation)
2. Lên kịch bản thô bằng Gemini AI từ nội dung người dùng (Plan Creator)
3. Render Overlay PNG 32-bit & Audio TTS WAV (Render Overlay & TTS Engine)
4. Lên kịch bản chi tiết VideoRenderPlan (chứa overlay_path, audio_path, duration)
5. Render video thành phẩm MP4 (Video Render Engine + MacOSVideoRenderer)
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import os
from pathlib import Path
import re
import shutil
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Union

import soundfile as sf

from app.config import (
    BASE_DIR,
    OUTPUTS_DIR,
    TEMP_DIR,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
    VOICES_DIR,
)
from app.services.content_extractor import (
    DEFAULT_EXTRACTOR_JSON_STRUCTURE,
    DEFAULT_EXTRACTOR_SYSTEM_PROMPT,
    ContentExtractorConfig,
    ContentExtractorEngine,
    ContentExtractorError,
)
from app.services.key_rotator import KeyRotator
from app.services.pipeline.exceptions import (
    PipelineError,
    StepAssetRenderError,
    StepContentExtractionError,
    StepDetailedPlanError,
    StepPlanCreationError,
    StepValidationError,
    StepVideoRenderError,
)
from app.services.pipeline.models import (
    PipelineInput,
    PipelineResult,
    ProgressCallback,
    RoughScene,
    RoughScript,
)
from app.services.plan_creator import (
    DEFAULT_JSON_STRUCTURE as DEFAULT_PLAN_JSON_STRUCTURE,
    DEFAULT_SYSTEM_PROMPT as DEFAULT_PLAN_SYSTEM_PROMPT,
    PlanCreatorConfig,
    PlanCreatorEngine,
    PlanCreatorError,
)
from app.services.render_overlay_engine import (
    RenderOverlayEngine,
    resolve_font,
    resolve_palette,
)
from app.services.render_overlay_engine.styles import (
    BabyBluePuffyStyle,
    BaseOverlayStyle,
    BubbleCloudStyle,
    DaisyDiaryStyle,
    GridNotebookDiaryStyle,
    MarshmallowPinkStyle,
    OceanChalkStickerStyle,
    PastelMulticolorStyle,
    RetroGroovyOrangeStyle,
    TornPaperStyle,
    TropicalContourStyle,
    VlogDoodleStickerStyle,
)
from app.services.tts_engine import DEFAULT_VOICE, TTSEngine
from app.services.video_render_engine import (
    MacOSVideoRenderer,
    WindowsVideoRenderer,
    get_platform_renderer,
    RenderResult,
    ScenePlan,
    VideoRenderConfig,
    VideoRenderEngine,
    VideoRenderPlan,
    allocate_voices_for_plans,
    concatenate_tts_and_effect_audio,
    find_sound_effect_file,
    parse_sound_effect_tag,
)
from app.utils.terminal_logger import clean_voice_name

logger = logging.getLogger(__name__)

# Bảng tra cứu phong cách đồ họa Overlay
OVERLAY_STYLE_MAP: Dict[str, type] = {
    "bubble_cloud": BubbleCloudStyle,
    "torn_paper": TornPaperStyle,
    "pastel_multicolor": PastelMulticolorStyle,
    "marshmallow_pink": MarshmallowPinkStyle,
    "vlog_doodle": VlogDoodleStickerStyle,
    "daisy_diary": DaisyDiaryStyle,
    "ocean_chalk": OceanChalkStickerStyle,
    "retro_groovy": RetroGroovyOrangeStyle,
    "tropical_contour": TropicalContourStyle,
    "grid_notebook": GridNotebookDiaryStyle,
    "baby_blue": BabyBluePuffyStyle,
}

SUPPORTED_MEDIA_EXTS = {
    ".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi",
    ".jpg", ".jpeg", ".png", ".webp", ".heic"
}



class VideoCreationPipeline:
    """Enterprise Pipeline Coordinator kết nối 6 bước sản xuất video tự động."""

    def __init__(
        self,
        content_extractor: Optional[ContentExtractorEngine] = None,
        plan_creator: Optional[PlanCreatorEngine] = None,
        render_overlay_engine: Optional[RenderOverlayEngine] = None,
        tts_engine: Optional[TTSEngine] = None,
        video_render_engine: Optional[VideoRenderEngine] = None,
    ):
        """Dependency Injection: Khởi tạo với các engine chuyên biệt hoặc tạo mặc định."""
        self.content_extractor = content_extractor  # [Deprecated] Giữ tương thích ngược
        self.plan_creator = plan_creator or PlanCreatorEngine()
        self.render_overlay_engine = render_overlay_engine or RenderOverlayEngine()
        self.tts_engine = tts_engine or TTSEngine()

        if video_render_engine is not None:
            self.video_render_engine = video_render_engine
        else:
            default_renderer = get_platform_renderer(hardware_accel=True)
            self.video_render_engine = VideoRenderEngine(renderer=default_renderer)

    def resolve_overlay_style(self, style_input: Union[str, BaseOverlayStyle]) -> BaseOverlayStyle:
        """Chuyển đổi tên style dạng string sang đối tượng BaseOverlayStyle cụ thể."""
        if isinstance(style_input, BaseOverlayStyle):
            return style_input
        normalized_name = str(style_input).lower().strip().replace("-", "_").replace(" ", "_")
        style_class = OVERLAY_STYLE_MAP.get(normalized_name, BubbleCloudStyle)
        return style_class()

    @staticmethod
    def _resolve_api_keys(input_keys: Union[List[str], str, None]) -> List[str]:
        """Thu thập danh sách Gemini API Keys từ input hoặc biến môi trường.

        Hỗ trợ phân tách linh hoạt khi người dùng truyền chuỗi chứa dấu phẩy,
        dấu chấm phẩy, khoảng trắng hoặc mảng nhiều phần tử.
        """
        def _extract_tokens(raw_items: Any) -> List[str]:
            tokens: List[str] = []
            if not raw_items:
                return tokens
            items = raw_items if isinstance(raw_items, (list, tuple, set)) else [raw_items]
            for it in items:
                if not isinstance(it, str):
                    continue
                norm = it.replace(";", ",").replace("\n", ",").replace("\t", ",")
                for part in norm.split(","):
                    for sub in part.strip().split():
                        cleaned = sub.strip(" \"'\t\r\n")
                        if cleaned and cleaned not in tokens:
                            tokens.append(cleaned)
            return tokens

        cleaned = _extract_tokens(input_keys)
        if cleaned:
            return cleaned

        env_keys = os.environ.get("GEMINI_API_KEYS", "")
        if env_keys:
            parsed = _extract_tokens(env_keys)
            if parsed:
                return parsed

        single_key = os.environ.get("GEMINI_API_KEY", "")
        if single_key:
            parsed = _extract_tokens(single_key)
            if parsed:
                return parsed

        return []

    @staticmethod
    def _measure_audio_duration(audio_path: Path) -> float:
        """Đo thời lượng chính xác của file audio WAV bằng soundfile."""
        if not audio_path.exists():
            return 0.0
        try:
            info = sf.info(str(audio_path))
            return float(info.duration)
        except Exception as e:
            logger.warning(f"Không thể đọc metadata âm thanh qua soundfile ({e}), fallback về 5.0s")
            return 5.0

    # -------------------------------------------------------------------------
    # BƯỚC 1: NHẬN CONTENT & VIDEO SOURCE PATH (INPUT & VALIDATION)
    # -------------------------------------------------------------------------
    def step_1_validate_inputs(
        self,
        input_data: PipelineInput,
        on_progress: Optional[ProgressCallback] = None,
    ) -> Dict[str, Any]:
        """Bước 1: Tiếp nhận và kiểm tra tính sẵn sàng của dữ liệu đầu vào."""
        if on_progress:
            on_progress(1, "Bước 1: Đang thẩm định dữ liệu đầu vào và thư mục tư liệu nguồn...", None)

        # 1.1 Kiểm tra content
        if not input_data.content or not input_data.content.strip():
            raise StepValidationError("Lỗi Bước 1: Nội dung văn bản 'content' không được để trống!")

        # 1.2 Kiểm tra thư mục video_source_path
        source_dir = input_data.video_source_path
        if not source_dir.exists() or not source_dir.is_dir():
            raise StepValidationError(f"Lỗi Bước 1: Thư mục 'video_source_path' không tồn tại: {source_dir}")

        media_files = [
            f for f in source_dir.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_MEDIA_EXTS
        ]
        if not media_files:
            raise StepValidationError(
                f"Lỗi Bước 1: Thư mục tư liệu '{source_dir}' không chứa file video hoặc ảnh hợp lệ nào!"
            )

        # 1.3 Kiểm tra API Keys
        valid_keys = self._resolve_api_keys(input_data.api_keys)
        if not valid_keys:
            raise StepValidationError(
                "Lỗi Bước 1: Không tìm thấy Gemini API Key khả dụng. "
                "Vui lòng truyền vào danh sách api_keys hoặc thiết lập biến môi trường GEMINI_API_KEY."
            )

        # 1.4 Khởi tạo thư mục làm việc tạm thời cho phiên xử lý
        session_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
        session_dir = TEMP_DIR / f"pipeline_{session_id}"
        session_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[Bước 1] Thẩm định thành công: {len(media_files)} files tư liệu, session_id={session_id}")
        return {
            "session_id": session_id,
            "session_dir": session_dir,
            "api_keys": valid_keys,
            "media_files_count": len(media_files),
        }

    # -------------------------------------------------------------------------
    # BƯỚC 2: LÊN KỊCH BẢN THÔ (ROUGH SCRIPT CREATION TỪ NỘI DUNG NGƯỜI DÙNG)
    # -------------------------------------------------------------------------
    def step_2_create_rough_scripts(
        self,
        content: Union[str, Dict[str, Any]],
        num_videos: int,
        api_keys: List[str],
        model_name: str = "gemini-3.5-flash-lite",
        creative_styles: Optional[List[str]] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> List[RoughScript]:
        """Bước 2: Sử dụng PlanCreatorEngine để tạo danh sách kịch bản thô trực tiếp từ nội dung người dùng."""
        if on_progress:
            on_progress(2, f"Bước 2: Đang lên {num_videos} kịch bản thô trực tiếp từ nội dung người dùng...", None)

        config = PlanCreatorConfig(
            model_name=model_name,
            api_keys=api_keys,
            system_prompt=DEFAULT_PLAN_SYSTEM_PROMPT,
            json_structure=DEFAULT_PLAN_JSON_STRUCTURE,
            temperature=0.7,
        )

        try:
            raw_result = self.plan_creator.create_plans(
                content=content,
                num_scripts=num_videos,
                creative_styles=creative_styles,
                override_config=config,
            )

            # Chuẩn hóa cấu trúc đầu ra về danh sách RoughScript
            scripts_list = raw_result.get("scripts", [])
            if not scripts_list and isinstance(raw_result, list):
                scripts_list = raw_result

            rough_scripts: List[RoughScript] = []
            for idx, item in enumerate(scripts_list):
                if not isinstance(item, dict):
                    continue
                script_id = str(item.get("script_id", f"script_{idx + 1}"))
                title = str(item.get("title", f"Video Kịch Bản #{idx + 1}"))
                overlay_style = str(item.get("overlay_style", "bubble_cloud"))

                scenes: List[RoughScene] = []
                raw_scenes = item.get("scenes", [])
                from app.services.plan_creator.engine import PlanCreatorEngine
                raw_scenes = PlanCreatorEngine._normalize_scenes_list(raw_scenes)

                for s_idx, s in enumerate(raw_scenes):
                    if isinstance(s, dict):
                        title_text = str(s.get("title") or s.get("content") or s.get("screen_text") or "").strip()
                        sub_title_text = s.get("sub_title") or s.get("subcontent")
                        srt_script_text = s.get("srt_script") or s.get("voiceover_text") or s.get("voice_text")
                        transition = str(s.get("transition", "fade"))
                    elif isinstance(s, (list, tuple)):
                        title_text = " ".join(str(x) for x in s if x).strip()
                        sub_title_text = None
                        srt_script_text = title_text
                        transition = "fade"
                    else:
                        title_text = str(s).strip()
                        sub_title_text = None
                        srt_script_text = title_text
                        transition = "fade"

                    scenes.append(RoughScene(
                        scene_index=s_idx,
                        title=title_text,
                        sub_title=sub_title_text,
                        srt_script=srt_script_text,
                        transition=transition,
                    ))

                if not scenes:
                    # Tạo ít nhất một scene mặc định nếu AI không sinh scene con
                    scenes.append(RoughScene(
                        scene_index=0,
                        title=title,
                        sub_title=None,
                        srt_script=title,
                        transition="fade",
                    ))

                rough_scripts.append(RoughScript(
                    script_id=script_id,
                    title=title,
                    overlay_style=overlay_style,
                    scenes=scenes,
                ))

            logger.info(f"[Bước 2] Đã tạo thành công {len(rough_scripts)} kịch bản thô")
            if on_progress:
                on_progress(2, f"Bước 2: Lên {len(rough_scripts)} kịch bản thô thành công!", {
                    "rough_scripts": [s.model_dump() for s in rough_scripts]
                })
            return rough_scripts

        except PlanCreatorError as e:
            raise StepPlanCreationError(f"Lỗi Bước 2 khi lên kịch bản thô: {e}") from e

    def step_3_create_rough_scripts(
        self,
        extracted_content: Optional[Union[Dict[str, Any], str]] = None,
        num_videos: int = 1,
        api_keys: Optional[List[str]] = None,
        model_name: str = "gemini-3.5-flash-lite",
        creative_styles: Optional[List[str]] = None,
        on_progress: Optional[ProgressCallback] = None,
        content: Optional[Union[str, Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> List[RoughScript]:
        """[Deprecated Alias] Chuyển tiếp sang step_2_create_rough_scripts để giữ tương thích ngược."""
        target_content = content if content is not None else (extracted_content if extracted_content is not None else "")
        return self.step_2_create_rough_scripts(
            content=target_content,
            num_videos=num_videos,
            api_keys=api_keys or [],
            model_name=model_name,
            creative_styles=creative_styles,
            on_progress=on_progress,
        )

    def step_2_extract_content(
        self,
        content: str,
        api_keys: List[str],
        model_name: str = "gemini-3.5-flash-lite",
        on_progress: Optional[ProgressCallback] = None,
    ) -> Dict[str, Any]:
        """[Deprecated] Bước trích xuất thông tin cũ trước khi gộp trực tiếp vào Plan Creator."""
        if on_progress:
            on_progress(2, "Bước 2 (Legacy): Đang bóc tách thông tin có cấu trúc bằng Gemini AI...", None)

        extractor = self.content_extractor or ContentExtractorEngine()
        config = ContentExtractorConfig(
            model_name=model_name,
            api_keys=api_keys,
            system_prompt=DEFAULT_EXTRACTOR_SYSTEM_PROMPT,
            json_structure=DEFAULT_EXTRACTOR_JSON_STRUCTURE,
            temperature=0.2,
        )

        try:
            extracted_data = extractor.extract(
                content=content,
                override_config=config,
            )
            logger.info(f"[Legacy] Bóc tách nội dung thành công: {list(extracted_data.keys())}")
            if on_progress:
                on_progress(2, "Bước 2 (Legacy): Bóc tách thông tin thành công!", {"extracted_data": extracted_data})
            return extracted_data
        except ContentExtractorError as e:
            raise StepContentExtractionError(f"Lỗi Bước 2 khi trích xuất thông tin: {e}") from e

    # -------------------------------------------------------------------------
    # BƯỚC 3: RENDER OVERLAY & AUDIO (SONG SONG)
    # -------------------------------------------------------------------------
    def step_3_render_assets(
        self,
        rough_scripts: List[RoughScript],
        session_dir: Path,
        overlay_style: Optional[Union[str, BaseOverlayStyle]] = None,
        overlay_font: Optional[str] = None,
        overlay_palette: Optional[Union[str, Any]] = None,
        overlay_palette_tag: Optional[str] = None,
        voice_id: Optional[str] = DEFAULT_VOICE,
        tts_speed: float = 1.15,
        tts_pitch: float = 0.0,
        voice_clone_path: Optional[Path] = None,
        voices_dir: Optional[Path] = None,
        randomize_voice_clone: bool = True,
        scene_pause_duration: float = 0.5,
        tts_seed: Optional[int] = None,
        sync_voice_speed: bool = True,
        target_wps: Optional[float] = None,
        canvas_width: int = VIDEO_WIDTH,
        canvas_height: int = VIDEO_HEIGHT,
        on_progress: Optional[ProgressCallback] = None,
    ) -> Dict[str, Dict[Any, Dict[str, Any]]]:
        """Bước 3: Render Overlay ảnh PNG trong suốt và Audio TTS WAV cho từng scene."""
        effective_voice_id = voice_id or DEFAULT_VOICE
        if on_progress:
            sync_info = "Đồng bộ nhịp: BẬT" if sync_voice_speed else "Đồng bộ nhịp: TẮT"
            on_progress(3, f"Bước 3: Đang render Overlay PNG và Audio lồng tiếng (Tốc độ {tts_speed}x, {sync_info})...", None)

        assets_dir = session_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        rendered_assets: Dict[str, Dict[Any, Dict[str, Any]]] = {}

        # 3.1 Render Overlay PNG trước (hỗ trợ chạy song song qua Chrome Headless)
        overlay_tasks = []
        for script in rough_scripts:
            rendered_assets[script.script_id] = {}
            script_style = self.resolve_overlay_style(overlay_style or script.overlay_style)

            # Cố định Font chữ và Bảng màu đồng nhất cho TOÀN BỘ các phân cảnh của kịch bản này
            script_font = overlay_font or getattr(script_style, "font", None) or resolve_font(None)
            script_palette = (
                overlay_palette
                or getattr(script_style, "palette", None)
                or resolve_palette(None, tag=overlay_palette_tag)
            )

            script_style.apply_font(script_font)
            script_style.apply_palette(script_palette)

            # Lưu thông tin font & palette vào metadata để đưa vào detailed_plan ở Bước 5
            rendered_assets[script.script_id]["_overlay_style"] = script_style.__class__.__name__
            rendered_assets[script.script_id]["_overlay_font"] = script_font
            rendered_assets[script.script_id]["_overlay_palette"] = (
                script_palette.id if hasattr(script_palette, "id") else str(script_palette)
            )

            for scene in script.scenes:
                scene_dir = assets_dir / f"script_{script.script_id}" / f"scene_{scene.scene_index}"
                scene_dir.mkdir(parents=True, exist_ok=True)
                overlay_out = scene_dir / f"overlay_{scene.scene_index}.png"

                overlay_tasks.append({
                    "script_id": script.script_id,
                    "scene_index": scene.scene_index,
                    "content": scene.title,
                    "subcontent": scene.sub_title,
                    "style": script_style,
                    "font": script_font,
                    "palette": script_palette,
                    "overlay_out": overlay_out,
                })

        def _render_overlay_task(t_info: Dict[str, Any]) -> None:
            self.render_overlay_engine.render(
                content=t_info["content"],
                subcontent=t_info["subcontent"],
                style=t_info["style"],
                font=t_info.get("font"),
                palette=t_info.get("palette"),
                output_path=t_info["overlay_out"],
                width=canvas_width,
                height=canvas_height,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(_render_overlay_task, overlay_tasks))

        # 4.2 Phân bổ voice clone cho từng script (mỗi plan một voice ngẫu nhiên hoặc cố định)
        effective_voices_dir = voices_dir or VOICES_DIR
        if voice_clone_path and Path(voice_clone_path).is_dir():
            effective_voices_dir = Path(voice_clone_path)
            voice_clone_path = None

        allocated_voices: List[Optional[Path]] = []
        if voice_clone_path and Path(voice_clone_path).is_file():
            allocated_voices = [Path(voice_clone_path).resolve()] * len(rough_scripts)
            logger.info(f"[Bước 4] Áp dụng voice clone chỉ định: '{voice_clone_path.name}' cho {len(rough_scripts)} kịch bản.")
        elif randomize_voice_clone:
            allocated_voices = allocate_voices_for_plans(
                plan_count=len(rough_scripts),
                voices_dir=effective_voices_dir,
                seed=tts_seed,
            )
            logger.info(
                f"[Bước 4] Đã phân bổ {len(allocated_voices)} voice clone ngẫu nhiên từ thư mục '{effective_voices_dir}'."
            )
        else:
            allocated_voices = [None] * len(rough_scripts)

        # 4.3 Render Audio TTS tuần tự theo từng script để đảm bảo tính nhất quán của seed
        total_scenes_count = sum(len(s.scenes) for s in rough_scripts)
        processed_scenes = 0

        # Xóa cache speaker embedding từ session cũ trước khi bắt đầu session mới
        self.tts_engine.clear_ref_audio_cache()

        # Pre-encode tất cả voice clone được phân bổ trước khi render scene.
        # Mục tiêu: đảm bảo speaker embedding chỉ được tính 1 lần per voice file,
        # tất cả scene trong cùng script dùng lại cache đã encode.
        unique_voice_paths = set(v for v in allocated_voices if v is not None)
        for vp in unique_voice_paths:
            try:
                self.tts_engine.encode_ref_audio_once(vp)
            except Exception as e:
                logger.warning(f"[Bước 4] Không thể pre-encode voice clone '{vp.name}': {e}")

        for script_idx, script in enumerate(rough_scripts):
            script_voice_clone = allocated_voices[script_idx] if script_idx < len(allocated_voices) else None
            rendered_assets[script.script_id]["_voice_clone_path"] = script_voice_clone

            # Tính toán hạt giống cố định (seed) riêng biệt cho từng kịch bản video
            voice_suffix = f"_{script_voice_clone.name}" if script_voice_clone else ""
            script_seed = (
                tts_seed
                if tts_seed is not None
                else (abs(hash(f"{script.script_id}_{script.title}_{session_dir.name}{voice_suffix}")) % 1000000)
            )
            logger.info(
                f"[Bước 4] Kịch bản '{script.title}' (ID: {script.script_id}) - "
                f"Voice Clone: '{script_voice_clone.name if script_voice_clone else 'Mặc định (Preset)'}', "
                f"seed: {script_seed}, pause_duration: {scene_pause_duration:.2f}s"
            )

            # Cố định numpy RNG MỘT LẦN trước chuỗi scene của script này.
            # VieNeu v3 Turbo ONNX dùng np.random.choice() — chỉ seed numpy, không phải torch.
            # QUAN TRỌỬNG: không reset seed per-scene. Nếu reset, mỗi scene bắt đầu từ cùng
            # RNG state nhưng text length khác nhau → số np.random call khác nhau → RNG
            # kết thúc ở state khác nhau cho mỗi call → tone drift ở các scene sau.
            # Seed liên tục: RNG chạy xuôi tự nhiên → tone ổn định hơn giữa các scene.
            import numpy as _np_seed
            _np_seed.random.seed(script_seed % (2**31))
            logger.info(f"[Bước 4] Đã set np.random.seed({script_seed % (2**31)}) cho script '{script.title}'")

            for scene in script.scenes:
                scene_dir = assets_dir / f"script_{script.script_id}" / f"scene_{scene.scene_index}"
                overlay_out = scene_dir / f"overlay_{scene.scene_index}.png"
                audio_out = scene_dir / f"audio_{scene.scene_index}.wav"

                if scene.srt_script and scene.srt_script.strip():
                    raw_narration = scene.srt_script.strip()
                elif scene.sub_title:
                    raw_narration = f"{scene.title}. {scene.sub_title}"
                else:
                    raw_narration = scene.title

                # Phòng vệ: Loại bỏ hoàn toàn nếu lọt chuỗi code dict vào raw_narration
                if "{" in raw_narration and ("scene_index" in raw_narration or "srt_script" in raw_narration):
                    logger.warning(f"Phát hiện chuỗi mã code trong narration cảnh {scene.scene_index}: {raw_narration[:60]}... Đang làm sạch.")
                    dict_m = re.search(r"['\"]srt_script['\"]\s*:\s*['\"]([^'\"]+)['\"]", raw_narration)
                    if dict_m:
                        raw_narration = dict_m.group(1).strip()
                    else:
                        raw_narration = re.sub(r"\{[^{}]*\}", "", raw_narration).strip()

                # Bóc tách thẻ [sound-effect:<tên file>] nếu có
                clean_narration, sfx_tag = parse_sound_effect_tag(raw_narration)
                if not clean_narration.strip():
                    clean_narration = scene.title

                # Tìm file sound effect tương ứng trong kho
                sfx_file = find_sound_effect_file(sfx_tag) if sfx_tag else None

                try:
                    # Nếu có hiệu ứng âm thanh ở cuối câu, TTS đọc lời thoại thuần (không pause ở đuôi)
                    # sau đó ghép sound effect vào cuối câu và đệm scene_pause_duration ở cuối cùng
                    tts_pause = 0.0 if sfx_file else scene_pause_duration
                    raw_tts_out = scene_dir / f"tts_raw_{scene.scene_index}.wav" if sfx_file else audio_out

                    self.tts_engine.synthesize(
                        text=clean_narration,
                        speed=tts_speed,
                        voice=effective_voice_id,
                        pitch=tts_pitch,
                        voice_clone_path=script_voice_clone,
                        output_path=raw_tts_out,
                        seed=None,  # KHAI THÁC liên tục RNG đã seed trước vòng lặp, không reset
                        pause_duration=tts_pause,
                        sync_speed=sync_voice_speed,
                        target_wps=target_wps,
                    )

                    if sfx_file:
                        concatenate_tts_and_effect_audio(
                            tts_audio_path=raw_tts_out,
                            effect_audio_path=sfx_file,
                            output_path=audio_out,
                            pause_duration=scene_pause_duration,
                        )
                except Exception as e:
                    logger.error(f"Lỗi render audio script {script.script_id} scene {scene.scene_index}: {e}")
                    raise StepAssetRenderError(f"Lỗi tạo Audio TTS cảnh {scene.scene_index}: {e}") from e

                # Đo thời lượng thực tế của audio (thời gian scene = audio gen thực tế + sound effect)
                actual_duration = self._measure_audio_duration(audio_out)

                rendered_assets[script.script_id][scene.scene_index] = {
                    "overlay_path": overlay_out,
                    "audio_path": audio_out,
                    "duration": actual_duration,
                    "sound_effect": str(sfx_file.name) if sfx_file else None,
                }
                processed_scenes += 1
                if on_progress:
                    pct = int((processed_scenes / max(1, total_scenes_count)) * 100)
                    total_plans = len(rough_scripts)
                    plan_no = script_idx + 1
                    total_scenes_in_script = len(script.scenes)
                    on_progress(
                        3,
                        f"[Plan {plan_no}/{total_plans}] Đang tạo Voice AI & Overlay cảnh {scene.scene_index}/{total_scenes_in_script} (Tổng: {pct}%)",
                        {
                            "plan_index": plan_no,
                            "total_plans": total_plans,
                            "scene_index": scene.scene_index,
                            "total_scenes_in_script": total_scenes_in_script,
                            "processed_scenes": processed_scenes,
                            "total_scenes_count": total_scenes_count,
                        },
                    )

            if on_progress:
                total_plans = len(rough_scripts)
                plan_no = script_idx + 1
                voice_label = clean_voice_name(script_voice_clone.name if script_voice_clone else effective_voice_id)
                on_progress(
                    3,
                    f"✓ [Plan {plan_no}/{total_plans}] Hoàn tất Assets: {len(script.scenes)} cảnh | Giọng: {voice_label}",
                    {
                        "plan_completed": True,
                        "plan_index": plan_no,
                        "total_plans": total_plans,
                    },
                )

        logger.info(f"[Bước 3] Hoàn thành render toàn bộ {total_scenes_count} assets đồ họa và âm thanh")
        if on_progress:
            on_progress(
                3,
                f"Bước 3: Hoàn tất tạo {total_scenes_count} assets đồ họa và âm thanh thành công!",
                {"step_completed": True},
            )
        return rendered_assets

    def step_4_render_assets(self, *args: Any, **kwargs: Any) -> Dict[str, Dict[Any, Dict[str, Any]]]:
        """[Deprecated Alias] Gọi tới step_3_render_assets để giữ tương thích ngược."""
        return self.step_3_render_assets(*args, **kwargs)

    # -------------------------------------------------------------------------
    # BƯỚC 4: LÊN KỊCH BẢN CHI TIẾT (DETAILED RENDER PLANS)
    # -------------------------------------------------------------------------
    def step_4_build_detailed_plans(
        self,
        rough_scripts: List[RoughScript],
        rendered_assets: Dict[str, Dict[int, Dict[str, Any]]],
        bgm_path: Optional[Path],
        session_dir: Path,
        bgm_volume: float = 0.10,
        randomize_bgm: bool = True,
        bgm_dir: Optional[Path] = None,
        bgm_seed: Optional[int] = None,
        company_name: Optional[str] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> List[VideoRenderPlan]:
        """Bước 4: Lắp ráp thành VideoRenderPlan hoàn chỉnh có overlay_path, audio_path, bgm_path."""
        if on_progress:
            on_progress(4, "Bước 4: Đang lắp ráp kịch bản chi tiết (VideoRenderPlan)...", None)

        detailed_plans: List[VideoRenderPlan] = []
        plans_dir = session_dir / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)

        # Chuẩn bị BGM cho các kịch bản
        allocated_bgm: List[Optional[Path]] = []
        if bgm_path and Path(bgm_path).is_file():
            allocated_bgm = [Path(bgm_path).resolve()] * len(rough_scripts)
            logger.info(f"[Bước 4] Áp dụng file BGM cố định: '{bgm_path.name}' cho {len(rough_scripts)} kịch bản.")
        elif randomize_bgm:
            from app.services.video_render_engine.bgm_manager import allocate_bgm_for_plans
            effective_bgm_dir = bgm_path if (bgm_path and Path(bgm_path).is_dir()) else bgm_dir
            allocated_bgm = allocate_bgm_for_plans(
                plan_count=len(rough_scripts),
                bgm_dir=effective_bgm_dir,
                seed=bgm_seed,
            )
            bgm_names = [p.name if p else "None" for p in allocated_bgm]
            logger.info(f"[Bước 4] Phân bổ ngẫu nhiên BGM cho {len(rough_scripts)} kịch bản: {bgm_names}")
        else:
            allocated_bgm = [None] * len(rough_scripts)

        for script_idx, script in enumerate(rough_scripts):
            if on_progress:
                on_progress(
                    4,
                    f"[Plan {script_idx + 1}/{len(rough_scripts)}] Đang lắp ráp kịch bản chi tiết: '{script.title}'...",
                    {"plan_index": script_idx + 1, "total_plans": len(rough_scripts)},
                )
            scene_plans: List[ScenePlan] = []
            script_assets = rendered_assets.get(script.script_id, {})

            for scene in script.scenes:
                asset_info = script_assets.get(scene.scene_index, {})
                ovl_path = asset_info.get("overlay_path")
                aud_path = asset_info.get("audio_path")
                actual_dur = asset_info.get("duration", 5.0)
                sfx_name = asset_info.get("sound_effect")

                scene_plans.append(ScenePlan(
                    scene_index=scene.scene_index,
                    content=scene.title,
                    subcontent=scene.sub_title,
                    overlay_image_path=ovl_path,
                    audio_path=aud_path,
                    transition=scene.transition,
                    metadata={
                        "duration": actual_dur,
                        "srt_script": scene.srt_script,
                        "sound_effect": sfx_name,
                    },
                ))

            script_voice_clone = script_assets.get("_voice_clone_path")
            script_bgm = allocated_bgm[script_idx] if script_idx < len(allocated_bgm) else None

            plan = VideoRenderPlan(
                plan_id=str(script.script_id),
                title=script.title,
                company_name=company_name,
                video_index=script_idx + 1,
                scenes=scene_plans,
                voice_clone_path=script_voice_clone,
                bgm_path=script_bgm,
                bgm_volume=bgm_volume,
                output_filename=None,
                extra_data={
                    "overlay_style": script_assets.get("_overlay_style", script.overlay_style),
                    "overlay_font": script_assets.get("_overlay_font"),
                    "overlay_palette": script_assets.get("_overlay_palette"),
                    "voice_clone_path": str(script_voice_clone) if script_voice_clone else None,
                    "bgm_path": str(script_bgm) if script_bgm else None,
                    "bgm_volume": bgm_volume if script_bgm else 0.0,
                },
            )
            detailed_plans.append(plan)

            # Lưu file JSON kịch bản chi tiết để audit / preview
            plan_file = plans_dir / f"detailed_plan_{script.script_id}.json"
            plan_dict = plan.model_dump(mode="json")
            with open(plan_file, "w", encoding="utf-8") as f:
                json.dump(plan_dict, f, ensure_ascii=False, indent=2)

        logger.info(f"[Bước 4] Đã tạo thành công {len(detailed_plans)} kịch bản chi tiết VideoRenderPlan")
        if on_progress:
            on_progress(4, f"Bước 4: Lắp ráp {len(detailed_plans)} kịch bản chi tiết thành công!", {
                "step_completed": True,
                "detailed_plans": [p.model_dump(mode="json") for p in detailed_plans]
            })
        return detailed_plans

    def step_5_build_detailed_plans(self, *args: Any, **kwargs: Any) -> List[VideoRenderPlan]:
        """[Deprecated Alias] Gọi tới step_4_build_detailed_plans để giữ tương thích ngược."""
        return self.step_4_build_detailed_plans(*args, **kwargs)

    # -------------------------------------------------------------------------
    # BƯỚC 5: RENDER VIDEO (VIDEO RENDERING)
    # -------------------------------------------------------------------------
    def step_5_render_videos(
        self,
        source_folder: Path,
        detailed_plans: List[VideoRenderPlan],
        anti_reup_level: str = "medium",
        output_dir: Path = OUTPUTS_DIR,
        scene_pause_duration: float = 0.5,
        bgm_volume: float = 0.10,
        enable_bgm: bool = True,
        on_progress: Optional[ProgressCallback] = None,
    ) -> List[RenderResult]:
        """Bước 5: Dựng và xuất video MP4 hoàn chỉnh qua VideoRenderEngine."""
        if on_progress:
            on_progress(5, "Bước 5: Đang render video hoàn chỉnh bằng VideoRenderEngine...", None)

        # Cấu hình video render engine kèm extra_params
        render_config = VideoRenderConfig(
            output_dir=output_dir,
            anti_reup_level=anti_reup_level,
            hardware_accel=True,
            bgm_volume=bgm_volume,
            enable_bgm=enable_bgm,
            extra_params={"scene_pause_duration": scene_pause_duration},
        )
        self.video_render_engine.config = render_config

        results: List[RenderResult] = []
        total_plans = len(detailed_plans)
        for idx, plan in enumerate(detailed_plans):
            plan_no = idx + 1
            if on_progress:
                on_progress(
                    5,
                    f"[Plan {plan_no}/{total_plans}] Đang render video: '{plan.title}'...",
                    {"plan_index": plan_no, "total_plans": total_plans},
                )

            def _log_callback(p_id: str, level: str, msg: str) -> None:
                # msg có dạng: "[2026-09-18 11:26:59] [INFO] [Plan: 1 | Thread: MainThread]    [Ghép scene 2] ..."
                core = msg
                if "] " in msg:
                    parts = msg.split("] ")
                    core = parts[-1].strip()

                if level.upper() == "ERROR":
                    logger.error(f"[Plan {p_id}] {core}")
                    return

                total_sc = len(plan.scenes)
                if "Cắt segment" in core:
                    m = re.search(r"\[Scene (\d+)\]", core)
                    sc_idx = (int(m.group(1)) + 1) if m else "?"
                    if on_progress:
                        on_progress(
                            5,
                            f"[Plan {plan_no}/{total_plans}] Đang cắt phân cảnh video {sc_idx}/{total_sc}...",
                            {"plan_index": plan_no, "total_plans": total_plans},
                        )
                elif "[Ghép scene" in core:
                    m = re.search(r"\[Ghép scene (\d+)\]", core)
                    sc_idx = (int(m.group(1)) + 1) if m else "?"
                    if on_progress:
                        on_progress(
                            5,
                            f"[Plan {plan_no}/{total_plans}] Đang ghép visual cảnh {sc_idx}/{total_sc}...",
                            {"plan_index": plan_no, "total_plans": total_plans},
                        )
                elif "Nối các phân cảnh" in core or "concat" in core.lower():
                    if on_progress:
                        on_progress(
                            5,
                            f"[Plan {plan_no}/{total_plans}] Đang nối các phân cảnh video...",
                            {"plan_index": plan_no, "total_plans": total_plans},
                        )
                elif "Render thành phẩm cuối cùng" in core or "Lồng nhạc nền BGM" in core:
                    if on_progress:
                        on_progress(
                            5,
                            f"[Plan {plan_no}/{total_plans}] Đang xuất thành phẩm & hòa trộn BGM...",
                            {"plan_index": plan_no, "total_plans": total_plans},
                        )
                elif "Anti-Reup" in core:
                    if on_progress:
                        on_progress(
                            5,
                            f"[Plan {plan_no}/{total_plans}] Đang áp dụng hiệu ứng Anti-Reup...",
                            {"plan_index": plan_no, "total_plans": total_plans},
                        )
                else:
                    logger.debug(f"[Plan {p_id}] {core}")

            try:
                res = self.video_render_engine.render_plan(
                    source_folder=source_folder,
                    plan=plan,
                    on_log=_log_callback,
                )
                results.append(res)
                logger.debug(f"[Bước 5] Render thành công video '{plan.title}': {res.output_path}")

                if on_progress:
                    mb_size = res.file_size_bytes / (1024 * 1024)
                    on_progress(
                        5,
                        f"🎬 [Plan {plan_no}/{total_plans}] Xuất video thành công: {res.output_path.name} ({res.duration:.1f}s • {mb_size:.1f} MB)",
                        {
                            "plan_completed": True,
                            "plan_index": plan_no,
                            "total_plans": total_plans,
                            "result": res.model_dump(mode="json"),
                        },
                    )
            except Exception as e:
                logger.error(f"[Bước 5] Lỗi render video plan {plan.plan_id}: {e}")
                raise StepVideoRenderError(f"Lỗi render video '{plan.title}': {e}") from e

        if on_progress:
            on_progress(5, f"Bước 5: Hoàn tất render {len(results)} video thành công!", {
                "step_completed": True,
                "results": [r.model_dump(mode="json") for r in results]
            })
        return results

    def step_6_render_videos(self, *args: Any, **kwargs: Any) -> List[RenderResult]:
        """[Deprecated Alias] Gọi tới step_5_render_videos để giữ tương thích ngược."""
        return self.step_5_render_videos(*args, **kwargs)

    @staticmethod
    def cleanup_session(session_dir: Optional[Path]) -> None:
        """Xóa an toàn thư mục tạm thời của một phiên làm việc."""
        if session_dir and session_dir.exists():
            try:
                shutil.rmtree(session_dir, ignore_errors=True)
                logger.info(f"Đã xóa thành công thư mục tạm của phiên: {session_dir}")
            except Exception as e:
                logger.warning(f"Không thể xóa thư mục tạm {session_dir}: {e}")

    @staticmethod
    def cleanup_orphaned_sessions(temp_dir: Optional[Path] = None) -> int:
        """Quét và dọn dẹp các thư mục mồ côi 'pipeline_*' trong thư mục temp.

        Trả về số lượng thư mục đã được dọn dẹp.
        """
        target_dir = temp_dir or TEMP_DIR
        if not target_dir.exists():
            return 0

        cleaned_count = 0
        for item in target_dir.glob("pipeline_*"):
            if item.is_dir():
                try:
                    shutil.rmtree(item, ignore_errors=True)
                    cleaned_count += 1
                    logger.info(f"Đã dọn dẹp thư mục pipeline rác: {item}")
                except Exception as e:
                    logger.warning(f"Không thể xóa thư mục pipeline rác {item}: {e}")
        return cleaned_count

    # -------------------------------------------------------------------------
    # HÀM ĐIỀU PHỐI TỔNG THỂ TOÀN BỘ 5 BƯỚC (FULL ORCHESTRATION)
    # -------------------------------------------------------------------------
    def execute(
        self,
        input_data: PipelineInput,
        on_progress: Optional[ProgressCallback] = None,
        cleanup_temp: bool = True,
    ) -> PipelineResult:
        """Chạy toàn bộ 5 bước từ nhận content đến video hoàn phẩm."""
        start_time = time.time()
        errors: List[str] = []
        session_id = "unknown"
        session_dir: Optional[Path] = None
        extracted_content: Dict[str, Any] = {}
        rough_scripts: List[RoughScript] = []
        detailed_plans: List[VideoRenderPlan] = []
        render_results: List[RenderResult] = []

        try:
            # 1. Nhận content, video source path
            v_res = self.step_1_validate_inputs(input_data, on_progress=on_progress)
            session_id = v_res["session_id"]
            session_dir = v_res["session_dir"]
            api_keys = v_res["api_keys"]

            # 2. Lên kịch bản thô trực tiếp từ nội dung người dùng
            rough_scripts = self.step_2_create_rough_scripts(
                content=input_data.content,
                num_videos=input_data.num_videos,
                api_keys=api_keys,
                model_name=input_data.model_name,
                on_progress=on_progress,
            )

            # 3. Render overlay, audio (đảm bảo đồng nhất style, font & palette và giọng đọc per script)
            rendered_assets = self.step_3_render_assets(
                rough_scripts=rough_scripts,
                session_dir=session_dir,
                overlay_style=input_data.overlay_style,
                overlay_font=input_data.overlay_font,
                overlay_palette=input_data.overlay_palette,
                overlay_palette_tag=input_data.overlay_palette_tag,
                voice_id=input_data.voice_id,
                tts_speed=input_data.tts_speed,
                tts_pitch=input_data.tts_pitch,
                voice_clone_path=input_data.voice_clone_path,
                voices_dir=input_data.voices_dir,
                randomize_voice_clone=input_data.randomize_voice_clone,
                scene_pause_duration=input_data.scene_pause_duration,
                tts_seed=input_data.tts_seed,
                sync_voice_speed=input_data.sync_voice_speed,
                target_wps=input_data.target_wps,
                canvas_width=input_data.canvas_width,
                canvas_height=input_data.canvas_height,
                on_progress=on_progress,
            )

            # 4. Lên kịch bản chi tiết (có overlay path, audio path)
            detailed_plans = self.step_4_build_detailed_plans(
                rough_scripts=rough_scripts,
                rendered_assets=rendered_assets,
                bgm_path=input_data.bgm_path,
                session_dir=session_dir,
                bgm_volume=input_data.bgm_volume,
                randomize_bgm=input_data.randomize_bgm,
                company_name=None,
                on_progress=on_progress,
            )

            # 5. Render video
            render_results = self.step_5_render_videos(
                source_folder=input_data.video_source_path,
                detailed_plans=detailed_plans,
                output_dir=input_data.output_dir,
                scene_pause_duration=input_data.scene_pause_duration,
                bgm_volume=input_data.bgm_volume,
                enable_bgm=input_data.randomize_bgm or (input_data.bgm_path is not None),
                on_progress=on_progress,
            )

            if cleanup_temp and session_dir:
                self.cleanup_session(session_dir)

            total_duration = time.time() - start_time
            return PipelineResult(
                session_id=session_id,
                extracted_content=extracted_content,
                rough_scripts=rough_scripts,
                detailed_plans=detailed_plans,
                render_results=render_results,
                total_time_seconds=total_duration,
                is_successful=True,
                errors=[],
            )

        except Exception as e:
            total_duration = time.time() - start_time
            err_msg = str(e)
            logger.error(f"Lỗi trong quá trình chạy Pipeline: {err_msg}", exc_info=True)
            errors.append(err_msg)
            if cleanup_temp and session_dir:
                self.cleanup_session(session_dir)
            return PipelineResult(
                session_id=session_id,
                extracted_content=extracted_content,
                rough_scripts=rough_scripts,
                detailed_plans=detailed_plans,
                render_results=render_results,
                total_time_seconds=total_duration,
                is_successful=False,
                errors=errors,
            )
