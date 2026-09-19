"""Backward compatibility shim. Use `app.services.video_render_engine.renderers.windows` instead."""

from app.services.video_render_engine.renderers.windows import WindowsVideoRenderer

__all__ = ["WindowsVideoRenderer"]
