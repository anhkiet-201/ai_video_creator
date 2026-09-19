"""Video processors, anti-reup algorithms, segment allocators, and output naming."""

from app.services.video_render_engine.processors.anti_reup import (
    DEFAULT_RANDOM_RULES,
    AntiReupEngine,
)
from app.services.video_render_engine.processors.output_namer import (
    allocate_next_output_path,
    build_company_dir_name,
    format_date_suffix,
    get_existing_max_index,
    sanitize_company_slug,
)
from app.services.video_render_engine.processors.segment import (
    SegmentCutPlan,
    VideoSegmentAllocator,
)

__all__ = [
    # Anti-Reup
    "AntiReupEngine",
    "DEFAULT_RANDOM_RULES",
    # Segment Allocator
    "SegmentCutPlan",
    "VideoSegmentAllocator",
    # Output Namer
    "allocate_next_output_path",
    "build_company_dir_name",
    "format_date_suffix",
    "get_existing_max_index",
    "sanitize_company_slug",
]
