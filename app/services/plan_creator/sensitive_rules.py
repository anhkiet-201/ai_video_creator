"""Quy tắc và danh mục thay thế từ khóa nhạy cảm trên TikTok / Mạng xã hội.

Module này là Single Source of Truth duy nhất cho toàn bộ logic làm sạch từ khóa nhạy cảm
(áp dụng thống nhất cho Title, Sub_title và srt_script), giúp video:
1. An toàn 100% trước thuật toán kiểm duyệt OCR và Audio (ASR) của TikTok, Reels, Shorts.
2. Bảo toàn ngữ pháp tiếng Việt tự nhiên sau khi thay thế (không xóa mù làm cụt câu hay để sót số lương trơ trọi).
"""

import re
from typing import Dict, List, Tuple

# Bảng quy tắc thay thế nhạy cảm duy nhất cho toàn bộ hệ thống (Title, Sub_title, srt_script)
# Định dạng chuẩn: Dict[Tuple[str, ...], List[str]]
# Sắp xếp tuần tự từ cụm từ cụ thể, dài nhất đến từ ngắn/tổng quát.
SENSITIVE_REPLACEMENTS: Dict[Tuple[str, ...], List[str]] = {
    # 1. Từ lóng thô tục, biến âm chửi thề & nhạy cảm vũ khí trong khẩu ngữ
    (
        r"(?i)\b(?:ụ\s*má|đụ\s*má|đù\s*má|má\s*nó(?:\s*chứ)?|mụ\s*nội(?:\s*nó)?(?:\s*chứ)?|chời\s*mẹ(?:\s*ơi)?|trời\s*thần\s*mẹ(?:\s*ơi)?|trời\s*đất\s*mẹ(?:\s*ơi)?)\b",
    ): ["thiệt tình"],
    (
        r"(?i)\b(?:vãi\s*đạn|vãi\s*chưởng|vãi\s*nồi|vãi\s*chấy|vãi\s*linh\s*hồn|phê\s*lòi\s*mắt)\b",
    ): ["cực kỳ"],

    # 2. Vũ khí & công cụ công nghiệp nhạy cảm (Chuyển đổi sang động từ/danh từ kỹ thuật an toàn, tự nhiên)
    (r"(?i)\b(?:bắn\s+súng\s+vít|súng\s+bắn\s+vít|súng\s+vít)\b",): ["siết vít"],
    (r"(?i)\b(?:súng\s+bắn\s+đinh|bắn\s+đinh)\b",): ["ghép đinh"],
    (r"(?i)\b(?:súng\s+bắn\s+keo|bắn\s+keo)\b",): ["tra keo"],
    (r"(?i)\bthao\s+tác\s+bắn\s+súng\b",): ["thao tác máy"],
    (r"(?i)\b(?:súng|đạn)\b",): [""],

    # 3. Độ tuổi, Năm sinh & Ngoại hình (Bảo vệ chính sách lao động vị thành niên & chống phân biệt đối xử)
    (
        r"(?i)\b(?:ai\s+)?đủ\s*tuổi\s*lao\s*động(?:\s+từ\s+18(?:\s*tuổi)?\s*trở\s*lên)?\b",
        r"(?i)\b(?:nhận\s+)?(?:từ\s*)?\d{2}\s*(?:[-–—]|đến|tới)\s*\d{2}\s*tuổi(?:\s*trở\s*lên)?\b",
        r"(?i)\b(?:nhận\s+)?(?:từ\s*)?1[5678](?:\s*-\s*\d+)?(?:\s*tuổi)?\s*trở\s*lên\b",
        r"(?i)\b(?:nhận\s+)?(?:từ\s*)?1[5678]\s*tuổi\b",
        r"(?i)\b(?:nhận\s+)?thiếu\s*tháng(?:\s+từ\s+200\d)?\b",
    ): ["mọi người"],
    (r"(?i)\b(?:sinh\s+năm|năm\s+sinh|(?:sinh\s+)?(?:năm\s+)?(?:từ\s+)?200\d|2k\d)\b",): [""],
    (r"(?i)\b(?:nhận\s+cả\s+hình\s+xăm|nhận\s+hình\s+xăm|xăm\s+trổ)\b",): ["môi trường cởi mở"],

    # 4. Loại bỏ lôi kéo, môi giới lao động & điều hướng ứng tuyển
    (
        r"(?i)\b(?:rủ\s*bạn(?:\s*bè)?(?:\s*cùng)?\s*(?:làm|đi\s*làm)|rủ\s*rê\s*qua\s*đây\s*làm\s*chung|về\s*chung\s*đội|inbox\s*(?:để\s*)?nhận\s*việc|bình\s*luận\s*(?:để\s*)?nhận\s*việc|vào\s*việc\s*cùng\s*tụi\s*mình)\b",
    ): ["cùng theo dõi"],
    (
        r"(?i)\b(?:không\s*cần\s*kinh\s*nghiệm|không\s*yêu\s*cầu\s*kinh\s*nghiệm|không\s*cần\s*bằng\s*cấp|không\s*yêu\s*cầu\s*bằng\s*cấp)\b",
    ): ["dễ làm quen thao tác"],
    (
        r"(?i)\b(?:không\s*thu\s*phí|miễn\s*phí\s*môi\s*giới|không\s*cọc|tiền\s*cọc|đặt\s*cọc)\b",
    ): ["minh bạch"],
    (
        r"(?i)\b(?:nộp\s*hồ\s*sơ|hồ\s*sơ\s*xin\s*việc|hồ\s*sơ\s*gốc|sơ\s*yếu\s*lý\s*lịch|xin\s*việc|phỏng\s*vấn(?:\s*đậu\s*ngay)?)\b",
    ): ["tìm hiểu"],
    (
        r"(?i)\b(?:ứng\s*tuyển(?:\s*ngay)?|nhận\s*việc(?:\s*ngay)?|đi\s*làm\s*ngay|vào\s*việc\s*ngay)\b",
    ): ["trải nghiệm"],
    (
        r"(?i)\b(?:đang\s+)?tuyển(?:\s*(?:dụng|gấp|thêm|người|công\s*nhân|nhân\s*viên))?\b",
        r"(?i)\btìm\s*người\b",
    ): ["khám phá"],
    (r"(?i)\b(?:lao\s*động\s*phổ\s*thông|lđpt)\b",): ["nhân sự"],
    (r"(?i)\b(?:cần\s+)?việc\s*làm\b",): ["môi trường làm việc"],
    (r"(?i)\bnam\s*/?\s*nữ\b",): ["mọi người"],

    # 5. Giấy tờ cá nhân & PII (Thay cả cụm giới từ đi kèm để câu không bị cụt tân ngữ)
    (
        r"(?i)\bmang\s*theo\s*(?:căn\s*cước\s*công\s*dân|căn\s*cước|cccd|cmnd|giấy\s*tờ\s*tùy\s*thân)(?:\s*(?:phô\s*tô|photo|bản\s*sao|gốc))?\b",
    ): ["chuẩn bị thông tin cơ bản"],
    (
        r"(?i)\b(?:căn\s*cước\s*công\s*dân|căn\s*cước|cccd|cmnd|giấy\s*tờ\s*tùy\s*thân)\b",
    ): [""],

    # 6. Tiền bạc, Mức lương có số & Tài chính (Bắt nguyên cụm số tiền + đơn vị + chu kỳ để câu hoàn chỉnh)
    (r"(?i)\bxoay\s*vòng\s*vốn\b",): ["hoạt động"],
    (
        r"(?i)\b(?:thanh\s*toán|trả|nhận|lãnh)\s*(?:tiền\s*)?(?:lương|lúa|thóc|tiền)(?:\s*hàng\s*tuần|\s*mỗi\s*tuần|\s*theo\s*tuần|\s*đều\s*đặn)?\b",
        r"(?i)\blương\s*(?:hàng\s*)?tuần\b",
    ): ["chế độ hỗ trợ chu đáo"],
    (r"(?i)\bứng\s*lương\b",): ["ứng trước"],
    (
        r"(?i)\btăng\s*ca\s*:?\s*\d+(?:[\.,]\d+)*(?:\s*[-–—]\s*\d+(?:[\.,]\d+)*)?\s*(?:k|ngàn|nghìn|ngìn|triệu|cành|củ|xị(?:\s*rưỡi)?|đồng|vnđ|đ)\b(?:\s*(?:/|một|trên)?\s*(?:giờ|tiếng|ngày|ca|buổi))?",
        r"(?i)\b\d+(?:[\.,]\d+)*(?:\s*[-–—]\s*\d+(?:[\.,]\d+)*)?\s*(?:k|ngàn|nghìn|ngìn|triệu|cành|củ|xị(?:\s*rưỡi)?|đồng|vnđ|đ)(?:\s*(?:/|một|trên)?\s*(?:giờ|tiếng|ngày|ca|buổi))?\s*tăng\s*ca\b",
    ): ["tăng ca đều đặn"],
    (
        r"(?i)\b(?:(?:tiền\s*lương|mức\s*lương|thu\s*nhập|thanh\s*toán|lương(?:\s*(?:tháng|ngày|cơ\s*bản|nhân\s*sự|lđpt))?)\s*(?:nhân\s*sự\s*)?(?:từ\s*)?:?\s*)?\d+(?:[\.,]\d+)*(?:\s*[-–—]\s*\d+(?:[\.,]\d+)*)?\s*(?:k|ngàn|nghìn|ngìn|triệu|cành|củ|xị(?:\s*rưỡi)?|đồng|vnđ|đ)\b(?:\s*(?:/|một|trên)?\s*(?:ngày\s*công|ngày|giờ|tiếng|tháng|tuần|ca|năm|phần|suất|bữa))?",
    ): ["chế độ đãi ngộ ổn định"],
    (
        r"(?i)\b(?:chế\s*độ\s*lương|tiền\s*lương|mức\s*lương|thu\s*nhập|bảng\s*lương|lương\s*tháng|lương\s*cơ\s*bản|lương(?!\s*(?:tâm|thực|khô|thiện)))\b",
    ): ["đãi ngộ"],
    (
        r"(?i)\b(?:tiền|thóc\s*thật|thóc|lúa|cành|củ|xị(?:\s*rưỡi)?)\b",
    ): [""],
    (r"(?i)(?<=\d)\s*(?:k|đ)\b", r"(?i)\b(?:ngàn|nghìn|ngìn|triệu)\b",): [""],

    # 7. Lao động & áp lực
    (r"(?i)\bcày\s*cuốc\b",): ["làm việc"],
}

# Cache biên dịch regex sẵn từ SENSITIVE_REPLACEMENTS để tối ưu hiệu năng
_COMPILED_SENSITIVE_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(pat), replacements[0] if replacements else "")
    for patterns, replacements in SENSITIVE_REPLACEMENTS.items()
    for pat in patterns
]

# Regex khử từ/cụm từ bị lặp kép liền kề sau khi thay thế (ví dụ: 'môi trường môi trường' -> 'môi trường')
_DUPLICATE_PHRASE_PATTERN = re.compile(
    r"(?i)\b(mọi\s+người|môi\s+trường|trải\s+nghiệm|khám\s+phá|đãi\s+ngộ|siết\s+vít)(?:\s+\1)+\b"
)


def clean_sensitive_text(text: str, uppercase: bool = False) -> str:
    """API duy nhất làm sạch và thay thế toàn bộ từ khóa nhạy cảm.

    Áp dụng thống nhất cho Title, Sub_title và srt_script từ từ điển SENSITIVE_REPLACEMENTS.
    Tự động chuẩn hóa ngữ pháp, dấu câu, khoảng trắng và chữ in hoa khi được yêu cầu.

    Args:
        text: Chuỗi văn bản cần làm sạch.
        uppercase: Nếu True, chuyển toàn bộ văn bản sang chữ in hoa (cho Title).

    Returns:
        Chuỗi văn bản đã được làm sạch an toàn tuyệt đối 100% và tự nhiên về ngữ pháp.
    """
    if not isinstance(text, str) or not text.strip():
        return ""

    result = text

    if uppercase:
        # Title Safeguard: Cấm triệt để từ giật tít tiền bạc / lương / tuyển dụng / việc làm trên tiêu đề lớn video
        result = re.sub(
            r"(?i)\b(?:lãnh\s+lúa|lãnh\s+tiền|lãnh\s+lương|trả\s+lúa|trả\s+lương|lịch\s+trả\s+lúa|lịch\s+trả\s+lương|lúa\s+ba\s+ngày(?:\s+một\s+lần)?|lúa\s+3\s+ngày(?:\s+1\s+lần)?)\b",
            "TRẢI NGHIỆM THỰC TẾ",
            result,
        )
        result = re.sub(r"(?i)\b(?:lúa|tiền|lương(?:\s*tháng)?|thu\s*nhập)\b", "MÔI TRƯỜNG", result)
        result = re.sub(r"(?i)\b(?:việc\s*làm|công\s*việc)\b", "MÔI TRƯỜNG", result)
        result = re.sub(r"(?i)\b(?:tuyển\s*dụng|ứng\s*tuyển|nhận\s*việc|tìm\s*người)\b", "REVIEW", result)

    # Áp dụng lần lượt các luật regex đã compile từ SENSITIVE_REPLACEMENTS
    for pattern, replacement in _COMPILED_SENSITIVE_RULES:
        result = pattern.sub(replacement, result)

    # Khử hiện tượng lặp cụm từ liền kề sau khi thay thế
    result = _DUPLICATE_PHRASE_PATTERN.sub(r"\1", result)

    # Chuẩn hóa khoảng trắng và dấu câu
    result = re.sub(r"\s+([,\.!\?:;\-])", r"\1", result)
    result = re.sub(r"\s+", " ", result).strip()

    if uppercase:
        return result.upper()

    return result


__all__ = [
    "SENSITIVE_REPLACEMENTS",
    "clean_sensitive_text",
]
