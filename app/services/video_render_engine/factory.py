"""Backward compatibility shim. Use `app.services.video_render_engine.renderers.factory` instead."""

from app.services.video_render_engine.renderers.factory import get_platform_renderer

__all__ = ["get_platform_renderer"]
