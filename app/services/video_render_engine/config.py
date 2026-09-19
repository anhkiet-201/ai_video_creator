"""Backward compatibility shim. Use `app.services.video_render_engine.core.config` instead."""

from app.services.video_render_engine.core.config import VideoRenderConfig

__all__ = ["VideoRenderConfig"]
