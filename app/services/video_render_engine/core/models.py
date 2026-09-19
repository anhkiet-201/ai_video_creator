"""Domain models and data structures for Video Render Engine."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ScenePlan(BaseModel):
    """Execution plan for a single scene in the video."""

    scene_index: int = Field(ge=0, description="Zero-based index of the scene")
    content: str = Field(description="Headline or primary script text for this scene")
    subcontent: Optional[str] = Field(default=None, description="Subtitle, key benefit, or emphasis text")
    overlay_image_path: Optional[Path] = Field(
        default=None,
        description="Pre-rendered transparent PNG graphics overlay"
    )
    audio_path: Optional[Path] = Field(
        default=None,
        description="Scene-specific narration audio segment, if voiceover is per-scene"
    )
    transition: Optional[str] = Field(
        default=None,
        description="Transition effect into the next scene (e.g. fade, wipeleft, slideleft)"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary scene metadata"
    )


class VideoRenderPlan(BaseModel):
    """Complete blueprint for rendering a single video."""

    plan_id: str = Field(description="Unique identifier for this plan")
    title: str = Field(default="Untitled Video", description="Human-readable title or subject")
    scenes: List[ScenePlan] = Field(..., min_length=1, description="Ordered list of scenes to assemble")
    master_voiceover_path: Optional[Path] = Field(
        default=None,
        description="Master voiceover narration audio file"
    )
    bgm_path: Optional[Path] = Field(
        default=None,
        description="Background music file path"
    )
    bgm_volume: float = Field(
        default=0.10,
        ge=0.0,
        le=2.0,
        description="Âm lượng nhạc nền BGM (mặc định 0.10 = 10%)"
    )
    voice_clone_path: Optional[Path] = Field(
        default=None,
        description="Đường dẫn file voice mẫu được clone cho kịch bản/plan này"
    )
    company_name: Optional[str] = Field(
        default=None,
        description="Tên công ty hoặc thương hiệu để định danh thư mục đầu ra"
    )
    video_index: Optional[int] = Field(
        default=None,
        ge=1,
        description="Số thứ tự của video trong batch để đánh số tik_final_{seq:02d}.mp4"
    )
    output_filename: Optional[str] = Field(
        default=None,
        description="Custom target filename for the final output (e.g. video_01.mp4)"
    )
    extra_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Custom plan data passed to user renderer"
    )


class AntiReupProfile(BaseModel):
    """Bản ghi các thông số ngẫu nhiên hóa (randomized parameters) cho một video.

    Thiết kế động (dynamic): Không cố định cứng các trường, cho phép lưu trữ và truy xuất
    bất kỳ thông số nào được động cơ AntiReupEngine sinh ra theo quy tắc của người dùng.
    """

    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Từ điển chứa toàn bộ các thông số vi mô đã được sinh ngẫu nhiên"
    )

    def get(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.params[key]

    def __contains__(self, key: str) -> bool:
        return key in self.params

    def __getattr__(self, name: str) -> Any:
        # Hỗ trợ truy cập dạng profile.zoom_factor hoặc profile.speed_factor
        if "params" in self.__dict__ and name in self.__dict__["params"]:
            return self.__dict__["params"][name]
        raise AttributeError(f"'AntiReupProfile' không có thuộc tính '{name}'")


class RenderResult(BaseModel):
    """Detailed summary of a completed video render."""

    plan_id: str
    output_path: Path
    duration: float = Field(default=0.0, ge=0.0)
    file_size_bytes: int = Field(default=0, ge=0)
    render_time_seconds: float = Field(default=0.0, ge=0.0)
    scenes_count: int = Field(default=0, ge=0)
    logs: List[str] = Field(
        default_factory=list,
        description="Danh sách các log độc lập trong bộ nhớ của luồng render này (không ghi đĩa)"
    )
    anti_reup_profile: Optional[AntiReupProfile] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RenderBatchResult(BaseModel):
    """Summary of a concurrent or sequential batch rendering session."""

    total_plans: int
    successful_renders: int
    failed_renders: int
    results: List[RenderResult]
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    total_time_seconds: float = Field(default=0.0, ge=0.0)
