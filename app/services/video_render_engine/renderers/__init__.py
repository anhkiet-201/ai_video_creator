"""Platform renderers, FFmpeg pipelines, and factory instantiation for Video Render Engine."""

from app.services.video_render_engine.renderers.base import (
    BaseVideoRenderer,
    SUPPORTED_VIDEO_EXTENSIONS,
)
from app.services.video_render_engine.renderers.factory import get_platform_renderer
from app.services.video_render_engine.renderers.ffmpeg import FFmpegBaseRenderer
from app.services.video_render_engine.renderers.macos import MacOSVideoRenderer
from app.services.video_render_engine.renderers.windows import WindowsVideoRenderer

__all__ = [
    "BaseVideoRenderer",
    "SUPPORTED_VIDEO_EXTENSIONS",
    "FFmpegBaseRenderer",
    "MacOSVideoRenderer",
    "WindowsVideoRenderer",
    "get_platform_renderer",
]
