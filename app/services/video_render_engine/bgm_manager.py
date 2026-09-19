"""Backward compatibility shim. Use `app.services.video_render_engine.audio.bgm` instead."""

from app.services.video_render_engine.audio.bgm import (
    BGMSelector,
    allocate_bgm_for_plans,
    get_available_bgm,
    pick_random_bgm,
)

__all__ = [
    "BGMSelector",
    "get_available_bgm",
    "pick_random_bgm",
    "allocate_bgm_for_plans",
]
