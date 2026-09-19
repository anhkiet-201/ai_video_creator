"""Configuration models for Video Render Engine."""

from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class VideoRenderConfig(BaseModel):
    """Configuration for the Video Render Engine.

    Platform-agnostic and extensible via `extra_params` so any user renderer
    implementation can receive its specific options without coupling the core engine.
    """

    width: int = Field(default=1080, ge=100, description="Target video canvas width in pixels")
    height: int = Field(default=1920, ge=100, description="Target video canvas height in pixels")
    fps: int = Field(default=30, ge=1, le=120, description="Target frames per second")
    max_concurrent_tasks: int = Field(
        default=3,
        ge=1,
        le=32,
        description="Maximum number of videos to render concurrently in parallel threads"
    )
    anti_reup_level: str = Field(
        default="medium",
        description="Default Anti-Reup algorithmic intensity ('none', 'low', 'medium', 'high')"
    )
    output_dir: Optional[Path] = Field(
        default=None,
        description="Default directory to write completed videos"
    )
    temp_dir: Optional[Path] = Field(
        default=None,
        description="Directory for temporary intermediate files"
    )
    enable_transition: bool = Field(
        default=True,
        description="Bật hoặc tắt hiệu ứng chuyển cảnh video (xfade) giữa các scenes"
    )
    transition_duration: float = Field(
        default=0.3,
        ge=0.05,
        le=2.0,
        description="Thời lượng hiệu ứng chuyển cảnh video xfade (giây)"
    )
    enable_transition_sound: bool = Field(
        default=True,
        description="Bật hoặc tắt âm thanh hiệu ứng khi chuyển cảnh giữa các scenes"
    )
    transition_sound_volume: float = Field(
        default=0.15,
        ge=0.0,
        le=2.0,
        description="Âm lượng cho hiệu ứng chuyển cảnh (mặc định 0.15 = 15%)"
    )
    transition_sound_dir: Optional[Path] = Field(
        default=None,
        description="Thư mục chứa các tệp âm thanh chuyển cảnh (mặc định: assets/sounds/transition)"
    )
    avoid_sfx_transition_collision: bool = Field(
        default=True,
        description="Tự động tắt Transition Sound nếu Scene trước đó đã có Sound Effect để tránh xung đột âm thanh"
    )
    enable_bgm: bool = Field(
        default=True,
        description="Bật hoặc tắt nhạc nền (BGM) phát xuyên suốt video"
    )
    bgm_volume: float = Field(
        default=0.10,
        ge=0.0,
        le=2.0,
        description="Âm lượng nhạc nền BGM (mặc định 0.10 = 10%)"
    )
    bgm_dir: Optional[Path] = Field(
        default=None,
        description="Thư mục chứa các tệp nhạc nền BGM (mặc định: assets/sounds/bgm)"
    )
    randomize_bgm: bool = Field(
        default=True,
        description="Tự động chọn ngẫu nhiên BGM từ thư mục nếu plan chưa có BGM hoặc chỉ định thư mục"
    )
    extra_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary user-defined parameters passed directly to custom renderer implementations"
    )
