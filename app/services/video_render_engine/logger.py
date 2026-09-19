"""Backward compatibility shim. Use `app.services.video_render_engine.core.logger` instead."""

from app.services.video_render_engine.core.logger import TaskLogger

__all__ = ["TaskLogger"]
