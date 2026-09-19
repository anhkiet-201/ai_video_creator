"""Backward compatibility shim. Use `app.services.video_render_engine.audio.transition_sound` instead."""

from app.services.video_render_engine.audio.transition_sound import (
    TransitionSoundSelector,
    allocate_transition_sounds,
    detect_audio_peak_timestamp,
    get_available_transition_sounds,
    pick_random_transition_sound,
)

__all__ = [
    "TransitionSoundSelector",
    "get_available_transition_sounds",
    "detect_audio_peak_timestamp",
    "pick_random_transition_sound",
    "allocate_transition_sounds",
]
