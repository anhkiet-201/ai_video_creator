"""Backward compatibility shim. Use `app.services.video_render_engine.renderers.ffmpeg` instead."""

from app.services.video_render_engine.renderers.ffmpeg import (
    FFmpegBaseRenderer,
    _get_subprocess_extra_kwargs,
)

__all__ = [
    "FFmpegBaseRenderer",
    "_get_subprocess_extra_kwargs",
]
