"""Audio, voiceover, background music, and sound effect managers for Video Render Engine."""

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

__all__ = [
    # BGM
    "BGMSelector",
    "get_available_bgm",
    "pick_random_bgm",
    "allocate_bgm_for_plans",
    # Voice Clone
    "VoiceCloneSelector",
    "get_available_voices",
    "pick_random_voice",
    "allocate_voices_for_plans",
    # Sound Effects (SFX)
    "SoundEffectManager",
    "SOUND_EFFECT_TAG_REGEX",
    "get_available_sound_effects",
    "format_sound_effects_for_prompt",
    "parse_sound_effect_tag",
    "find_sound_effect_file",
    "concatenate_tts_and_effect_audio",
    "get_audio_duration",
    # Transition Sounds
    "TransitionSoundSelector",
    "get_available_transition_sounds",
    "detect_audio_peak_timestamp",
    "pick_random_transition_sound",
    "allocate_transition_sounds",
]
