"""Backward compatibility shim. Use `app.services.video_render_engine.processors.anti_reup` instead."""

from app.services.video_render_engine.processors.anti_reup import (
    DEFAULT_RANDOM_RULES,
    AntiReupEngine,
)

__all__ = [
    "AntiReupEngine",
    "DEFAULT_RANDOM_RULES",
]
