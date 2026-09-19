"""Backward compatibility shim. Use `app.services.video_render_engine.renderers.macos` instead."""

from app.services.video_render_engine.renderers.macos import MacOSVideoRenderer

__all__ = ["MacOSVideoRenderer"]
