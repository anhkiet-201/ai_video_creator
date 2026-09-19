"""Factory helper for instantiating the optimal video renderer for the current OS."""

import sys
from typing import Any, Optional

from app.services.video_render_engine.renderers.ffmpeg import FFmpegBaseRenderer
from app.services.video_render_engine.renderers.macos import MacOSVideoRenderer
from app.services.video_render_engine.renderers.windows import WindowsVideoRenderer
from app.services.video_render_engine.processors.segment import VideoSegmentAllocator
from app.services.video_render_engine.audio.transition_sound import TransitionSoundSelector


def get_platform_renderer(
    hardware_accel: bool = True,
    default_fit_mode: str = "crop",
    segment_allocator: Optional[VideoSegmentAllocator] = None,
    transition_sound_selector: Optional[TransitionSoundSelector] = None,
    **kwargs: Any,
) -> FFmpegBaseRenderer:
    """Factory helper returning the optimal video renderer for the current operating system."""
    if sys.platform == "darwin":
        return MacOSVideoRenderer(
            hardware_accel=hardware_accel,
            default_fit_mode=default_fit_mode,
            segment_allocator=segment_allocator,
            transition_sound_selector=transition_sound_selector,
            **kwargs,
        )
    elif sys.platform == "win32":
        return WindowsVideoRenderer(
            hardware_accel=hardware_accel,
            default_fit_mode=default_fit_mode,
            segment_allocator=segment_allocator,
            transition_sound_selector=transition_sound_selector,
            **kwargs,
        )
    else:
        return FFmpegBaseRenderer(
            hardware_accel=False,
            default_fit_mode=default_fit_mode,
            segment_allocator=segment_allocator,
            transition_sound_selector=transition_sound_selector,
            **kwargs,
        )

