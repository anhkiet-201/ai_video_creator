"""Backward compatibility shim. Use `app.services.video_render_engine.processors.segment` instead."""

from app.services.video_render_engine.processors.segment import (
    SegmentCutPlan,
    VideoSegmentAllocator,
)

__all__ = [
    "SegmentCutPlan",
    "VideoSegmentAllocator",
]
