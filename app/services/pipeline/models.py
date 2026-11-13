"""Domain data models and schemas for Video Creation Pipeline (6-Step Flow)."""

import logging
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator

from app.config import OUTPUTS_DIR, VIDEO_HEIGHT, VIDEO_WIDTH
from app.services.render_overlay_engine.styles import BaseOverlayStyle
from app.services.tts_engine.constants import VieNeuVoice
from app.services.video_render_engine.models import RenderResult, VideoRenderPlan

logger = logging.getLogger(__name__)


class RoughScene(BaseModel):
    """Một phân cảnh trong kịch bản thô (Bước 3)."""

    scene_index: int = Field(ge=0, description="Chỉ số phân cảnh (0, 1, 2...)")
    title: str = Field(
        ...,
        description="Chữ chính hiển thị to rõ trên màn hình (Headline ngắn gọn)"
    )
    sub_title: Optional[str] = Field(
        default=None,
        description="Nội dung phụ / Điểm nhấn / Quyền lợi nổi bật"
    )
    srt_script: Optional[str] = Field(
        default=None,
        description="Kịch bản lời thoại phụ đề (SRT) dùng để chuyển thành giọng nói AI"
    )
    transition: str = Field(
        default="fade",
        description="Hiệu ứng chuyển cảnh (fade, wipeleft, slideleft)"
    )


class RoughScript(BaseModel):
    """Một kịch bản thô hoàn chỉnh do AI sáng tạo (Bước 3)."""

    script_id: str = Field(description="Định danh duy nhất của kịch bản")
    title: str = Field(description="Tiêu đề video ngắn")
    overlay_style: str = Field(
        default="bubble_cloud",
        description="Phong cách đồ họa overlay (ví dụ: bubble_cloud, torn_paper...)"
    )
    scenes: List[RoughScene] = Field(
        ...,
        min_length=1,
        description="Danh sách các phân cảnh tuần tự"
    )


class PipelineInput(BaseModel):
    """Tham số đầu vào cho toàn bộ luồng tạo video 6 bước (Bước 1)."""

    content: str = Field(
        ...,
        description="Văn bản nội dung gốc (tin tuyển dụng, bài viết, thông tin tuyển...)"
    )
    video_source_path: Union[Path, List[Path]] = Field(
        ...,
        description="Đường dẫn hoặc danh sách đường dẫn thư mục chứa video và ảnh b-roll nguồn"
    )
    num_videos: int = Field(
        default=1,
        ge=1,
        le=100,
        description="Số lượng video thành phẩm cần tạo"
    )
    api_keys: Union[List[str], str] = Field(
        default_factory=list,
        description="Danh sách Gemini API keys để xoay vòng (hỗ trợ list hoặc chuỗi phân tách bởi dấu phẩy)"
    )
    llm_provider: str = Field(
        default="gemini",
        description="Nhà cung cấp LLM: 'gemini' hoặc 'lm_studio'"
    )
    llm_base_url: Optional[str] = Field(
        default=None,
        description="Địa chỉ API cho LM Studio (mặc định: http://localhost:1234/v1)"
    )
    model_name: str = Field(
        default="gemini-3.5-flash-lite",
        description="Mô hình LLM AI sử dụng"
    )
    voice_id: Optional[Union[VieNeuVoice, str]] = Field(
        default=None,
        description="Định danh giọng đọc VieNeu-TTS (None nếu dùng Voice Cloning ngẫu nhiên từ assets/voices)"
    )
    tts_speed: float = Field(
        default=1.15,
        ge=0.5,
        le=2.0,
        description="Tốc độ giọng đọc TTS (mặc định: 1.15x cho video ngắn)"
    )
    tts_pitch: float = Field(
        default=0.0,
        ge=-20.0,
        le=20.0,
        description="Độ cao độ giọng đọc TTS"
    )
    sync_voice_speed: bool = Field(
        default=True,
        description="Tự động đồng bộ hóa và chuẩn hóa tốc độ đọc giữa các giọng clone khác nhau"
    )
    target_wps: Optional[float] = Field(
        default=None,
        ge=1.0,
        le=5.0,
        description="Tốc độ đọc mục tiêu cơ sở (từ/giây), mặc định 2.85 WPS"
    )
    voice_clone_path: Optional[Path] = Field(
        default=None,
        description="Đường dẫn file audio mẫu nếu dùng chế độ Voice Cloning cố định"
    )
    voices_dir: Optional[Path] = Field(
        default=None,
        description="Thư mục chứa các tệp audio mẫu để chọn ngẫu nhiên cho từng plan (mặc định: assets/voices)"
    )
    randomize_voice_clone: bool = Field(
        default=True,
        description="Tự động chọn ngẫu nhiên 1 voice trong voices_dir cho mỗi plan để clone"
    )
    scene_pause_duration: float = Field(
        default=0.5,
        ge=0.0,
        le=5.0,
        description="Khoảng nghỉ nhẹ giữa các phân cảnh (giây)"
    )
    tts_seed: Optional[int] = Field(
        default=None,
        description="Hạt giống ngẫu nhiên cố định cho giọng đọc (tự sinh per script nếu None)"
    )
    canvas_width: int = Field(
        default=VIDEO_WIDTH,
        description="Chiều rộng khung hình video (mặc định 1080)"
    )
    canvas_height: int = Field(
        default=VIDEO_HEIGHT,
        description="Chiều cao khung hình video (mặc định 1920)"
    )
    output_dir: Path = Field(
        default=OUTPUTS_DIR,
        description="Thư mục xuất video thành phẩm"
    )
    bgm_path: Optional[Path] = Field(
        default=None,
        description="Đường dẫn file nhạc nền hoặc thư mục chứa BGM (nếu None sẽ dùng BGM_SOUNDS_DIR)"
    )
    bgm_volume: float = Field(
        default=0.10,
        ge=0.0,
        le=2.0,
        description="Âm lượng nhạc nền BGM (mặc định 0.10 = 10%)"
    )
    randomize_bgm: bool = Field(
        default=True,
        description="Tự động chọn ngẫu nhiên BGM từ thư mục cho mỗi plan"
    )
    overlay_style: Optional[Union[str, BaseOverlayStyle]] = Field(
        default=None,
        description="Phong cách đồ họa chữ đè Overlay (ví dụ: bubble_cloud, torn_paper, retro_groovy...)"
    )
    overlay_font: Optional[str] = Field(
        default=None,
        description="Font chữ đồng nhất cho overlay (ví dụ: 'Cherry Bomb One', 'Montserrat'...)"
    )
    overlay_palette: Optional[Union[str, Any]] = Field(
        default=None,
        description="Bảng màu đồng nhất cho overlay (ID, ColorPalette, hoặc danh sách mã hex)"
    )
    overlay_palette_tag: Optional[str] = Field(
        default=None,
        description="Tag nhóm màu lọc khi random (ví dụ: 'pastel', 'retro', 'neon', 'candy'...)"
    )

    @field_validator("api_keys", mode="before")
    @classmethod
    def validate_api_keys(cls, v: Any) -> List[str]:
        if not v:
            return []
        items = v if isinstance(v, (list, tuple, set)) else [v]
        cleaned_keys: List[str] = []
        for it in items:
            if not isinstance(it, str):
                continue
            norm = it.replace(";", ",").replace("\n", ",").replace("\t", ",")
            for part in norm.split(","):
                for sub in part.strip().split():
                    token = sub.strip(" \"'\t\r\n")
                    if token and token not in cleaned_keys:
                        cleaned_keys.append(token)
        return cleaned_keys

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        cleaned = v.strip() if v else ""
        if not cleaned:
            raise ValueError("Nội dung 'content' không được để trống!")
        return cleaned

    @field_validator("video_source_path", mode="before")
    @classmethod
    def validate_video_source_path(cls, v: Any) -> Union[Path, List[Path]]:
        if v is None:
            raise ValueError("Thư mục 'video_source_path' không được để trống!")

        # Trường hợp truyền 1 Path hoặc 1 chuỗi đường dẫn đơn lẻ
        if isinstance(v, Path):
            resolved = v.expanduser().resolve()
            if not resolved.exists() or not resolved.is_dir():
                raise ValueError(f"Thư mục 'video_source_path' không tồn tại hoặc không phải thư mục: {resolved}")
            return resolved

        if isinstance(v, str):
            raw_str = v.strip()
            if not raw_str:
                raise ValueError("Thư mục 'video_source_path' không được để trống!")
            single_cand = Path(raw_str).expanduser()
            if ("," not in raw_str and ";" not in raw_str) or single_cand.exists():
                resolved = single_cand.resolve()
                if not resolved.exists() or not resolved.is_dir():
                    raise ValueError(f"Thư mục 'video_source_path' không tồn tại hoặc không phải thư mục: {resolved}")
                return resolved
            raw_items: List[Any] = [p.strip().strip("\"'") for p in re.split(r"[,;]+", raw_str) if p.strip()]
        elif isinstance(v, (list, tuple, set)):
            raw_items = list(v)
        else:
            raise ValueError(f"Kiểu dữ liệu 'video_source_path' không hợp lệ: {type(v)}")

        candidates: List[Path] = []
        seen: set = set()
        for item in raw_items:
            if item is None:
                continue
            if isinstance(item, Path):
                p = item.expanduser().resolve()
                if p not in seen:
                    seen.add(p)
                    candidates.append(p)
            else:
                s = str(item).strip().strip("\"'")
                if not s:
                    continue
                single_p = Path(s).expanduser()
                if ("," in s or ";" in s) and not single_p.exists():
                    for part in re.split(r"[,;]+", s):
                        clean_part = part.strip().strip("\"'")
                        if clean_part:
                            rp = Path(clean_part).expanduser().resolve()
                            if rp not in seen:
                                seen.add(rp)
                                candidates.append(rp)
                else:
                    rp = single_p.resolve()
                    if rp not in seen:
                        seen.add(rp)
                        candidates.append(rp)

        valid_paths: List[Path] = []
        for cand in candidates:
            if cand.exists() and cand.is_dir():
                valid_paths.append(cand)
            else:
                logger.warning(f"Thư mục 'video_source_path' không tồn tại hoặc không phải thư mục, bỏ qua: {cand}")

        if not valid_paths:
            raise ValueError(f"Thư mục 'video_source_path' không tồn tại hoặc không có thư mục nào hợp lệ: {v}")

        return valid_paths

    @property
    def video_source_paths(self) -> List[Path]:
        """Trả về danh sách các thư mục nguồn dưới dạng List[Path] thống nhất."""
        if isinstance(self.video_source_path, list):
            return list(self.video_source_path)
        return [self.video_source_path]


class PipelineResult(BaseModel):
    """Kết quả hoàn chỉnh của toàn bộ luồng tạo video 6 bước."""

    session_id: str = Field(description="Mã phiên làm việc duy nhất")
    extracted_content: Dict[str, Any] = Field(
        default_factory=dict,
        description="Dữ liệu JSON bóc tách được ở Bước 2"
    )
    rough_scripts: List[RoughScript] = Field(
        default_factory=list,
        description="Danh sách các kịch bản thô ở Bước 3"
    )
    detailed_plans: List[VideoRenderPlan] = Field(
        default_factory=list,
        description="Danh sách các kịch bản chi tiết ở Bước 5 (có overlay_path, audio_path)"
    )
    render_results: List[RenderResult] = Field(
        default_factory=list,
        description="Danh sách kết quả render video thành phẩm ở Bước 6"
    )
    total_time_seconds: float = Field(
        default=0.0,
        ge=0.0,
        description="Tổng thời gian thực thi toàn bộ pipeline"
    )
    is_successful: bool = Field(
        default=False,
        description="Trạng thái hoàn thành thành công hay không"
    )
    errors: List[str] = Field(
        default_factory=list,
        description="Danh sách các thông báo lỗi nếu có"
    )


# Callback định nghĩa hàm nhận thông báo tiến độ theo từng bước: callback(step_number, step_name, data)
ProgressCallback = Callable[[int, str, Optional[Dict[str, Any]]], None]
