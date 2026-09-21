"""Constants và Prompt mặc định cho Plan Creator Engine."""

# Danh sách đầy đủ 58 hiệu ứng chuyển cảnh chuẩn hỗ trợ bởi bộ lọc FFmpeg xfade
FFMPEG_TRANSITIONS = (
    # Fade & Dissolve
    "fade", "fadeblack", "fadewhite", "fadegrays", "fadefast", "fadeslow", "dissolve", "distance",
    # Wipe
    "wipeleft", "wiperight", "wipeup", "wipedown", "wipetl", "wipetr", "wipebl", "wipebr",
    # Slide & Smooth
    "slideleft", "slideright", "slideup", "slidedown",
    "smoothleft", "smoothright", "smoothup", "smoothdown",
    # Crop, Shape & Zoom
    "circlecrop", "rectcrop", "circleopen", "circleclose", "vertopen", "vertclose", "horzopen", "horzclose",
    "zoomin", "radial", "pixelize", "hblur", "squeezeh", "squeezev",
    # Diagonal, Slice & Wind
    "diagtl", "diagtr", "diagbl", "diagbr",
    "hlslice", "hrslice", "vuslice", "vdslice", "hlwind", "hrwind", "vuwind", "vdwind",
    # Cover & Reveal
    "coverleft", "coverright", "coverup", "coverdown", "revealleft", "revealright", "revealup", "revealdown",
)

# Whitelist 3 nhóm thẻ cảm xúc hợp lệ được mô hình TTS hỗ trợ (tuyệt đối cấm thẻ khác)
VALID_EMOTION_TAGS = (
    "[cười]", "[chuckle]",
    "[thở dài]", "[sigh]",
    "[hắng giọng]", "[clear throat]",
)
# Re-export các prompt và schema từ module prompts chuyên biệt để đảm bảo 100% Backward Compatibility
from app.services.plan_creator.prompts import (
    DEFAULT_JSON_STRUCTURE,
    DEFAULT_SINGLE_PLAN_JSON_STRUCTURE,
    DEFAULT_SINGLE_PLAN_USER_PROMPT_TEMPLATE,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_USER_PROMPT_TEMPLATE,
)

__all__ = [
    "FFMPEG_TRANSITIONS",
    "VALID_EMOTION_TAGS",
    "DEFAULT_SYSTEM_PROMPT",
    "DEFAULT_JSON_STRUCTURE",
    "DEFAULT_USER_PROMPT_TEMPLATE",
    "DEFAULT_SINGLE_PLAN_JSON_STRUCTURE",
    "DEFAULT_SINGLE_PLAN_USER_PROMPT_TEMPLATE",
]


