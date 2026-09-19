"""Backward compatibility shim. Use `app.services.video_render_engine.audio.sound_effect` instead."""

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

__all__ = [
    "SoundEffectManager",
    "SOUND_EFFECT_TAG_REGEX",
    "get_available_sound_effects",
    "format_sound_effects_for_prompt",
    "parse_sound_effect_tag",
    "find_sound_effect_file",
    "concatenate_tts_and_effect_audio",
    "get_audio_duration",
]
