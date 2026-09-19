"""Backward compatibility shim. Use `app.services.video_render_engine.audio.voice` instead."""

from app.services.video_render_engine.audio.voice import (
    VoiceCloneSelector,
    allocate_voices_for_plans,
    get_available_voices,
    pick_random_voice,
)

__all__ = [
    "VoiceCloneSelector",
    "get_available_voices",
    "pick_random_voice",
    "allocate_voices_for_plans",
]
