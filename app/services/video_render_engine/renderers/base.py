"""Base video renderer contract, shared FFmpeg pipeline, and native macOS / Windows implementations.

This module defines the abstract BaseVideoRenderer contract and re-exports
concrete renderers and factory functions for complete backward compatibility.
"""

from abc import ABC, abstractmethod
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.video_render_engine.core.config import VideoRenderConfig
from app.services.video_render_engine.core.logger import TaskLogger
from app.services.video_render_engine.core.models import (
    AntiReupProfile,
    RenderResult,
    VideoRenderPlan,
)

logger = logging.getLogger(__name__)

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi"}


class BaseVideoRenderer(ABC):
    """Abstract contract for video renderers.

    Users implement this interface on their target platform using their tool of choice
    (FFmpeg, GStreamer, AVFoundation on macOS, MediaFoundation on Windows, MoviePy, etc.).
    The core engine does not dictate or depend on the rendering mechanism.
    """

    @property
    def renderer_name(self) -> str:
        """Friendly name of this renderer implementation."""
        return self.__class__.__name__

    @abstractmethod
    def validate_environment(self) -> bool:
        """Validate whether the required tools/libraries are available on this environment.

        Returns:
            True if the environment is ready to execute renders, False otherwise.
        """
        pass

    @abstractmethod
    def render_plan(
        self,
        plan: VideoRenderPlan,
        source_folder: Path,
        config: VideoRenderConfig,
        profile: AntiReupProfile,
        task_logger: TaskLogger,
    ) -> RenderResult:
        """Render a single video plan into a final video file.

        Args:
            plan: Blueprint containing scenes, texts, durations, and audio paths.
            source_folder: Directory containing b-roll video/image assets.
            config: VideoRenderConfig (resolution, fps, paths, extra_params).
            profile: AntiReupProfile with randomized micro-parameters.
            task_logger: In-memory thread-isolated logger (task_logger.info/warning/error).

        Returns:
            RenderResult containing output path, duration, file size, and execution stats.
        """
        pass

    def on_render_start(
        self,
        plan: VideoRenderPlan,
        task_logger: TaskLogger,
        source_folder: Optional[Path] = None,
        config: Optional[VideoRenderConfig] = None,
    ) -> None:
        """Optional hook invoked before rendering starts."""
        pass

    def on_render_end(
        self,
        result: Optional[RenderResult],
        task_logger: TaskLogger,
        plan: Optional[VideoRenderPlan] = None,
        config: Optional[VideoRenderConfig] = None,
    ) -> None:
        """Optional hook invoked after rendering finishes (success or failure)."""
        pass


# Re-exports for complete backward compatibility
from app.services.video_render_engine.ffmpeg_renderer import (
    FFmpegBaseRenderer,
    _get_subprocess_extra_kwargs,
)
from app.services.video_render_engine.macos_renderer import MacOSVideoRenderer
from app.services.video_render_engine.windows_renderer import WindowsVideoRenderer
from app.services.video_render_engine.factory import get_platform_renderer

__all__ = [
    "BaseVideoRenderer",
    "FFmpegBaseRenderer",
    "MacOSVideoRenderer",
    "WindowsVideoRenderer",
    "get_platform_renderer",
    "SUPPORTED_VIDEO_EXTENSIONS",
    "_get_subprocess_extra_kwargs",
]
