import random
from typing import List, Optional
from urllib.parse import quote_plus

PREDEFINED_OVERLAY_FONTS: List[str] = [
    # Nhóm Classic / Clean / Tiêu chuẩn
    "Be Vietnam Pro",
    "Noto Sans",
    "Inter",
    "Roboto",
    "Coiny",

    # Nhóm Display / 3D / Độc đáo / Cá tính (New Additions)
    "Cherry Bomb One",
    "Potta One",
    "Vina Sans",
    "Sigmar One",
    "Bungee",
    "Bungee Shade",
    "Bungee Outline",
    "Grenze",
    "Fruktur",
    "Tilt Prism",
    "Big Shoulders Inline",
    "Pacifico",
    "Borel",
    "Mynerve",
    "Shantell Sans",
    "Sansita Swashed",
    "Gluten",
]


def get_random_font() -> str:
    """Bốc ngẫu nhiên 1 font từ danh sách 27 font được định nghĩa sẵn."""
    return random.choice(PREDEFINED_OVERLAY_FONTS)


def resolve_font(font: Optional[str] = None) -> str:
    """
    Xác định font sử dụng.
    - Nếu font là None hoặc rỗng: Tự động bốc ngẫu nhiên 1 font trong danh mục định nghĩa sẵn.
    - Nếu có truyền font: Trả về font đã được làm sạch chuỗi (strip).
    """
    if font is None or not str(font).strip():
        return get_random_font()
    return str(font).strip()


def format_font_family(font_name: str) -> str:
    """
    Định dạng chuỗi CSS font-family chuẩn mực kèm fallback.
    Ví dụ: 'Cherry Bomb One' -> "'Cherry Bomb One', -apple-system, BlinkMacSystemFont, sans-serif"
    """
    clean_name = font_name.strip().strip("'\"")
    return f"'{clean_name}', -apple-system, BlinkMacSystemFont, sans-serif"


FONT_WEIGHTS_MAP = {
    "Be Vietnam Pro": "wght@400;600;700;800;900",
    "Noto Sans": "wght@400;700;900",
    "Inter": "wght@400;700;900",
    "Roboto": "wght@400;700;900",
    "Grenze": "wght@700;900",
    "Grenze Gotisch": "wght@700;900",
    "Shantell Sans": "wght@400;700;800",
    "Gluten": "wght@400;700;900",
}


def get_font_query_param(font_name: str) -> str:
    """Tạo query parameter cho Google Fonts CSS2 kèm weights nếu có."""
    clean_name = font_name.strip().strip("'\"")
    encoded = quote_plus(clean_name)
    if clean_name in FONT_WEIGHTS_MAP:
        return f"{encoded}:{FONT_WEIGHTS_MAP[clean_name]}"
    return encoded


def build_google_font_url(font_name: str) -> str:
    """
    Tạo link Google Fonts CSS2 nạp font được chỉ định một cách tối ưu.
    """
    param = get_font_query_param(font_name)
    return f"https://fonts.googleapis.com/css2?family={param}&display=swap"
