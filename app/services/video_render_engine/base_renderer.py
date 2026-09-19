"""Backward compatibility shim. Use `app.services.video_render_engine.renderers.base` instead."""

from app.services.video_render_engine.renderers.base import (
    BaseVideoRenderer,
    SUPPORTED_VIDEO_EXTENSIONS,
)

__all__ = [
    "BaseVideoRenderer",
    "SUPPORTED_VIDEO_EXTENSIONS",
]
