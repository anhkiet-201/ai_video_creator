"""Backward compatibility shim. Use `app.services.video_render_engine.core.exceptions` instead."""

from app.services.video_render_engine.core.exceptions import (
    InvalidPlanError,
    RendererNotProvidedError,
    RenderExecutionError,
    SourceFolderNotFoundError,
    VideoRenderEngineError,
)

__all__ = [
    "VideoRenderEngineError",
    "RendererNotProvidedError",
    "SourceFolderNotFoundError",
    "InvalidPlanError",
    "RenderExecutionError",
]
