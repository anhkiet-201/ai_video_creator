"""Video Render Engine Package.

A clean, platform-agnostic video rendering framework with:
- Structured subpackages: `core`, `renderers`, `audio`, `processors`.
- Abstract BaseVideoRenderer contract (implement on any platform with any tool).
- Multi-threaded parallel rendering.
- In-memory isolated per-thread logging.
- Independent Anti-Reup profile generation.
- Full backward compatibility for legacy module paths.
"""

from app.services.video_render_engine.core.config import VideoRenderConfig
from app.services.video_render_engine.core.exceptions import (
    InvalidPlanError,
    RendererNotProvidedError,
    RenderExecutionError,
    SourceFolderNotFoundError,
    VideoRenderEngineError,
)
from app.services.video_render_engine.core.logger import TaskLogger
from app.services.video_render_engine.core.models import (
    AntiReupProfile,
    RenderBatchResult,
    RenderResult,
    ScenePlan,
    VideoRenderPlan,
)
from app.services.video_render_engine.renderers.base import (
    BaseVideoRenderer,
    SUPPORTED_VIDEO_EXTENSIONS,
)
from app.services.video_render_engine.renderers.factory import get_platform_renderer
from app.services.video_render_engine.renderers.ffmpeg import FFmpegBaseRenderer
from app.services.video_render_engine.renderers.macos import MacOSVideoRenderer
from app.services.video_render_engine.renderers.windows import WindowsVideoRenderer
from app.services.video_render_engine.processors.anti_reup import (
    DEFAULT_RANDOM_RULES,
    AntiReupEngine,
)
from app.services.video_render_engine.processors.output_namer import (
    allocate_next_output_path,
    build_company_dir_name,
    format_date_suffix,
    get_existing_max_index,
    sanitize_company_slug,
)
from app.services.video_render_engine.processors.segment import (
    SegmentCutPlan,
    VideoSegmentAllocator,
)
from app.services.video_render_engine.audio.bgm import (
    BGMSelector,
    allocate_bgm_for_plans,
    get_available_bgm,
    pick_random_bgm,
)
from app.services.video_render_engine.audio.sound_effect import (
    SOUND_EFFECT_TAG_REGEX,
    SoundEffectManager,
    concatenate_tts_and_effect_audio,
    find_sound_effect_file,
    format_sound_effects_for_prompt,
    get_audio_duration,
    get_available_sound_effects,
    parse_sound_effect_tag,
)
from app.services.video_render_engine.audio.transition_sound import (
    TransitionSoundSelector,
    allocate_transition_sounds,
    detect_audio_peak_timestamp,
    get_available_transition_sounds,
    pick_random_transition_sound,
)
from app.services.video_render_engine.audio.voice import (
    VoiceCloneSelector,
    allocate_voices_for_plans,
    get_available_voices,
    pick_random_voice,
)
from app.services.video_render_engine.engine import VideoRenderEngine

__all__ = [
    # Engine & Base Contract
    "VideoRenderEngine",
    "BaseVideoRenderer",
    "SUPPORTED_VIDEO_EXTENSIONS",
    "FFmpegBaseRenderer",
    "MacOSVideoRenderer",
    "WindowsVideoRenderer",
    "get_platform_renderer",
    # Segment Allocator
    "SegmentCutPlan",
    "VideoSegmentAllocator",
    # Config
    "VideoRenderConfig",
    # Anti-Reup
    "AntiReupEngine",
    "DEFAULT_RANDOM_RULES",
    # Models
    "VideoRenderPlan",
    "ScenePlan",
    "AntiReupProfile",
    "RenderResult",
    "RenderBatchResult",
    # In-memory Logging
    "TaskLogger",
    # Transition Sound SFX Manager
    "TransitionSoundSelector",
    "get_available_transition_sounds",
    "detect_audio_peak_timestamp",
    "pick_random_transition_sound",
    "allocate_transition_sounds",
    # Sound Effect Manager
    "SoundEffectManager",
    "SOUND_EFFECT_TAG_REGEX",
    "get_available_sound_effects",
    "format_sound_effects_for_prompt",
    "parse_sound_effect_tag",
    "find_sound_effect_file",
    "concatenate_tts_and_effect_audio",
    "get_audio_duration",
    # Voice Clone Manager
    "VoiceCloneSelector",
    "get_available_voices",
    "pick_random_voice",
    "allocate_voices_for_plans",
    # BGM Manager
    "BGMSelector",
    "get_available_bgm",
    "pick_random_bgm",
    "allocate_bgm_for_plans",
    # Output Namer / Folder Manager
    "allocate_next_output_path",
    "build_company_dir_name",
    "format_date_suffix",
    "get_existing_max_index",
    "sanitize_company_slug",
    # Exceptions
    "VideoRenderEngineError",
    "RendererNotProvidedError",
    "SourceFolderNotFoundError",
    "InvalidPlanError",
    "RenderExecutionError",
]
