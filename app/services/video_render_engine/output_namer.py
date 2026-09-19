"""Backward compatibility shim. Use `app.services.video_render_engine.processors.output_namer` instead."""

from app.services.video_render_engine.processors.output_namer import (
    TIK_FINAL_PATTERN,
    _ALLOCATION_LOCK,
    VIETNAMESE_MAP,
    allocate_next_output_path,
    build_company_dir_name,
    format_date_suffix,
    get_existing_max_index,
    sanitize_company_slug,
)

__all__ = [
    "TIK_FINAL_PATTERN",
    "_ALLOCATION_LOCK",
    "VIETNAMESE_MAP",
    "allocate_next_output_path",
    "build_company_dir_name",
    "format_date_suffix",
    "get_existing_max_index",
    "sanitize_company_slug",
]
