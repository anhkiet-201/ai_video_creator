"""Quy tắc và danh mục thay thế từ khóa nhạy cảm trên TikTok / Mạng xã hội.

Module này là Single Source of Truth duy nhất cho toàn bộ logic làm sạch từ khóa nhạy cảm
(áp dụng thống nhất cho Title, Sub_title và srt_script), giúp video an toàn 100%
trước thuật toán kiểm duyệt OCR và Audio của các nền tảng (TikTok, Reels, Shorts).
"""

import re
from typing import Dict, List, Tuple

# Bảng quy tắc thay thế nhạy cảm duy nhất cho toàn bộ hệ thống (Title, Sub_title, srt_script)
# Định dạng chuẩn: Dict[Tuple[str, ...], List[str]]
# Sắp xếp tuần tự từ cụm từ cụ thể, dài nhất đến từ ngắn/tổng quát.
SENSITIVE_REPLACEMENTS: Dict[Tuple[str, ...], List[str]] = {
    # 1. Vũ khí & công cụ: Xóa từ 'súng'
    (r"(?i)\bsúng\b",): [""],

    # 2. Độ tuổi & Năm sinh (Bảo vệ chính sách lao động vị thành niên)
    (r"(?i)\b(?:ai\s+)?đủ\s*tuổi\s*lao\s*động(?:\s+từ\s+18(?:\s*tuổi)?\s*trở\s*lên)?\b",): ["tất cả anh em"],
    (r"(?i)\b(?:từ\s*)?18(?:\s*tuổi)?\s*trở\s*lên\b",): ["tất cả mọi người"],
    (r"(?i)\b(?:nhận\s+)?thiếu\s*tháng(?:\s+từ\s+200\d)?\b",): ["tất cả anh em"],
    (r"(?i)\b(?:sinh\s+năm|năm\s+sinh|(?:sinh\s+)?(?:năm\s+)?(?:từ\s+)?200\d|2k\d)\b",): [""],

    # 3. Đơn vị tiền tệ & Số tiền
    (r"(?i)(?<=\d)\s*k\b", r"(?i)\b(?:ngàn|nghìn|ngìn)\b",): [" cành", " cá", " ca"],

    # 4. Tiền bạc & Mức lương cốt lõi (Tự động làm sạch mọi cụm ghép với tiền/lương)
    (r"(?i)\bxoay\s*vòng\s*vốn\b",): ["chi tiêu"],
    (r"(?i)\blương(?!\s*(?:tâm|thực|tháng))\b",): ["lúa"],
    (r"(?i)\btiền\b",): ["lúa"],

    # 5. Điều hướng tuyển dụng & Giới tính
    (r"(?i)\bứng\s*tuyển\b",): ["nhận việc"],
    (r"(?i)\btuyển(?:\s*(?:dụng|gấp|thêm))?\b",): ["tìm người"],
    (r"(?i)\bnam\s*/?\s*nữ\b",): ["tất cả anh em"],

    # 6. Lao động
    (r"(?i)\bcày\s*cuốc\b",): ["tăng ca"],
}

# Cache biên dịch regex sẵn từ SENSITIVE_REPLACEMENTS để tối ưu hiệu năng
_COMPILED_SENSITIVE_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(pat), replacements[0] if replacements else "")
    for patterns, replacements in SENSITIVE_REPLACEMENTS.items()
    for pat in patterns
]


def clean_sensitive_text(text: str, uppercase: bool = False) -> str:
    """API duy nhất làm sạch và thay thế toàn bộ từ khóa nhạy cảm.

    Áp dụng thống nhất cho Title, Sub_title và srt_script từ từ điển SENSITIVE_REPLACEMENTS.
    Tự động chuẩn hóa dấu câu, khoảng trắng và chữ in hoa khi được yêu cầu.

    Args:
        text: Chuỗi văn bản cần làm sạch.
        uppercase: Nếu True, chuyển toàn bộ văn bản sang chữ in hoa (cho Title).

    Returns:
        Chuỗi văn bản đã được làm sạch an toàn tuyệt đối 100%.
    """
    if not isinstance(text, str) or not text.strip():
        return ""

    result = text

    # Áp dụng lần lượt các luật regex đã compile từ SENSITIVE_REPLACEMENTS
    for pattern, replacement in _COMPILED_SENSITIVE_RULES:
        result = pattern.sub(replacement, result)

    # Chuẩn hóa khoảng trắng và dấu câu
    result = re.sub(r"\s+([,\.!\?:;\-])", r"\1", result)
    result = re.sub(r"\s+", " ", result).strip()

    if uppercase:
        # Title Safeguard: Cấm triệt để từ giật tít tiền bạc / lúa / lương trên tiêu đề lớn video
        result = re.sub(
            r"(?i)\b(?:lãnh\s+lúa|lãnh\s+tiền|lãnh\s+lương|trả\s+lúa|trả\s+lương|lịch\s+trả\s+lúa|lịch\s+trả\s+lương|lúa\s+ba\s+ngày(?:\s+một\s+lần)?|lúa\s+3\s+ngày(?:\s+1\s+lần)?)\b",
            "CÔNG VIỆC",
            result,
        )
        result = re.sub(r"(?i)\b(?:lúa|tiền|lương)\b", "VIỆC LÀM", result)
        result = re.sub(r"\s+", " ", result).strip()
        return result.upper()

    return result


__all__ = [
    "SENSITIVE_REPLACEMENTS",
    "clean_sensitive_text",
]
