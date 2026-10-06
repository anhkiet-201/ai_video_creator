import colorsys
import logging
import random
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


def _normalize_hex(color_str: str) -> str:
    """Chuẩn hóa mã màu hex về định dạng chuẩn #rrggbb viết thường."""
    c = color_str.strip()
    if not c.startswith("#"):
        c = f"#{c}"
    if len(c) == 4:  # #rgb -> #rrggbb
        c = f"#{c[1]*2}{c[2]*2}{c[3]*2}"
    return c.lower()


def hex_to_rgb(hex_code: str) -> Tuple[int, int, int]:
    """Chuyển đổi mã màu hex sang tuple (R, G, B)."""
    clean = _normalize_hex(hex_code).lstrip("#")
    return int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Chuyển đổi các giá trị RGB (0-255) thành mã hex chuẩn #rrggbb."""
    clamped_r = max(0, min(255, int(round(r))))
    clamped_g = max(0, min(255, int(round(g))))
    clamped_b = max(0, min(255, int(round(b))))
    return f"#{clamped_r:02x}{clamped_g:02x}{clamped_b:02x}"


def get_luminance(hex_code: str) -> float:
    """Tính độ sáng tương đối (Relative Luminance) theo chuẩn WCAG 2.0 (0.0 đến 1.0)."""
    r, g, b = [x / 255.0 for x in hex_to_rgb(hex_code)]
    r = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
    g = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
    b = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def is_dark(hex_code: str, threshold: float = 0.45) -> bool:
    """Kiểm tra một màu có phải là màu tối hay không."""
    return get_luminance(hex_code) < threshold


def get_contrast_text_color(
    bg_hex: str,
    dark_color: str = "#18181b",
    light_color: str = "#ffffff"
) -> str:
    """Tự động trả về màu chữ tương phản cao nhất (#18181b hoặc #ffffff) dựa trên màu nền."""
    return light_color if is_dark(bg_hex) else dark_color


def get_vibrancy(hex_code: str) -> float:
    """Tính điểm độ rực rỡ và sống động của màu sắc dựa trên không gian HLS (0.0 đến 1.0)."""
    r, g, b = [x / 255.0 for x in hex_to_rgb(hex_code)]
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    lum_penalty = 1.0 - abs(l - 0.55) * 1.4
    return s * max(0.1, lum_penalty)


def to_candy_color(hex_code: str, target_l: float = 0.70, min_s: float = 0.68) -> str:
    """
    Chuyển đổi một màu bất kỳ thành màu kẹo ngọt (candy color) tươi sáng, rực rỡ và nịnh mắt:
    - Bảo tồn gốc sắc (Hue) của bảng màu.
    - Chuẩn hóa Độ sáng (L) và Độ bão hòa (S) trong không gian HLS.
    - Không bao giờ bị tối sẫm hoặc xỉn màu.
    """
    r, g, b = [x / 255.0 for x in hex_to_rgb(hex_code)]
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if s < 0.12:  # Màu phi sắc (đen, trắng, xám tro)
        h = 0.95  # Gán sắc hồng dâu ngọt ngào
        s = 0.75
    else:
        s = max(min_s, min(s, 0.95))
    clamped_l = max(0.62, min(target_l, 0.76))
    nr, ng, nb = colorsys.hls_to_rgb(h, clamped_l, s)
    return rgb_to_hex(int(nr * 255), int(ng * 255), int(nb * 255))


def to_pastel_cloud(hex_code: str, target_l: float = 0.88, target_s: float = 0.50) -> str:
    """
    Chuyển đổi một màu thành tông pastel bồng bềnh như đám mây marshmallow:
    - Độ sáng cao (L ~ 0.88) và độ bão hòa vừa phải (S ~ 0.50).
    - Tạo phông nền hoặc viền mềm mại, làm bừng sáng chữ chính.
    """
    r, g, b = [x / 255.0 for x in hex_to_rgb(hex_code)]
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if s < 0.12:
        h = 0.95
        s = 0.35
    else:
        s = max(0.32, min(s, target_s))
    clamped_l = max(0.84, min(target_l, 0.93))
    nr, ng, nb = colorsys.hls_to_rgb(h, clamped_l, s)
    return rgb_to_hex(int(nr * 255), int(ng * 255), int(nb * 255))


def generate_pastel_rainbow(
    palette: Union["ColorPalette", List[str], Tuple[str, ...]],
    count: int = 6
) -> List[str]:
    """
    Tạo dải màu pastel cầu vồng ngọt ngào từ bảng màu:
    - Chuyển đổi các màu gốc thành các sắc pastel trong trẻo.
    - Tự động bổ sung các góc xoay sắc thái (Hue rotation) hài hòa để đủ số lượng từ.
    """
    if hasattr(palette, "colors"):
        raw_colors = list(palette.colors)
    elif isinstance(palette, (list, tuple)):
        raw_colors = [str(c) for c in palette]
    else:
        raw_colors = ["#ffb3c6", "#bbf2f6", "#ffeaa7", "#c7ecee"]

    res: List[str] = []
    base_candies = [to_candy_color(c, target_l=0.76, min_s=0.60) for c in raw_colors]
    for i in range(count):
        if i < len(base_candies):
            res.append(base_candies[i])
        else:
            base_c = raw_colors[i % len(raw_colors)]
            r, g, b = [x / 255.0 for x in hex_to_rgb(base_c)]
            h, l, s = colorsys.rgb_to_hls(r, g, b)
            h = (h + 0.16 * (i - len(base_candies) + 1)) % 1.0
            s = max(0.60, min(s if s >= 0.12 else 0.70, 0.90))
            nr, ng, nb = colorsys.hls_to_rgb(h, 0.76, s)
            res.append(rgb_to_hex(int(nr * 255), int(ng * 255), int(nb * 255)))
    return res


def to_pastel_tint(hex_code: str, factor: float = 0.58) -> str:
    """Chuyển đổi một mã màu hex thành màu pastel dịu mắt bằng cách pha trộn với màu trắng."""
    r, g, b = hex_to_rgb(hex_code)
    nr = int(r + (255 - r) * factor)
    ng = int(g + (255 - g) * factor)
    nb = int(b + (255 - b) * factor)
    return rgb_to_hex(nr, ng, nb)


def ensure_pastel(hex_code: str) -> str:
    """Tự động chuyển đổi màu thành màu pastel nhẹ nhàng, tươi sáng trong không gian HLS."""
    return to_candy_color(hex_code, target_l=0.78, min_s=0.55)


@dataclass(frozen=True)
class ColorPalette:
    """
    Cấu trúc bảng màu 4 sắc độ lấy cảm hứng từ Color Hunt (https://colorhunt.co/).
    Tập hợp 4 mã màu hài hòa, có độ tương phản và thẩm mỹ cao theo chuẩn thiết kế.
    """
    id: str
    name: str
    colors: Tuple[str, str, str, str]
    tags: Tuple[str, ...] = ()

    @property
    def c1(self) -> str:
        """Màu 1 (thường là màu chủ đạo / đậm / nền)"""
        return self.colors[0]

    @property
    def c2(self) -> str:
        """Màu 2 (màu phụ trợ / khối 3D)"""
        return self.colors[1]

    @property
    def c3(self) -> str:
        """Màu 3 (màu điểm nhấn / highlight)"""
        return self.colors[2]

    @property
    def c4(self) -> str:
        """Màu 4 (màu sáng / kem / tương phản)"""
        return self.colors[3]

    @property
    def primary(self) -> str:
        return self.c1

    @property
    def secondary(self) -> str:
        return self.c2

    @property
    def accent(self) -> str:
        return self.c3

    @property
    def neutral(self) -> str:
        return self.c4


# =============================================================================
# KHO 50+ BẢNG MÀU TUYỂN CHỌN TỪ COLOR HUNT (https://colorhunt.co/)
# =============================================================================
COLOR_PALETTES: List[ColorPalette] = [
    # --- NHÓM 1: PASTEL & SWEET CANDY (Ngọt ngào, dịu mát, thịnh hành Gen Z) ---
    ColorPalette(
        id="pastel_macaron",
        name="Pastel Macaron",
        colors=("#ff9494", "#ffd1d1", "#ffe3e1", "#fff5e4"),
        tags=("pastel", "candy", "cute")
    ),
    ColorPalette(
        id="lavender_dream",
        name="Lavender Dream",
        colors=("#7f669d", "#ba94d1", "#ffb4b4", "#ffdeb4"),
        tags=("pastel", "purple", "cute")
    ),
    ColorPalette(
        id="soft_lilac",
        name="Soft Lilac Butter",
        colors=("#6c5ce7", "#a29bfe", "#ffeaa7", "#dfe6e9"),
        tags=("pastel", "purple", "sweet")
    ),
    ColorPalette(
        id="mint_peach_cream",
        name="Mint Peach Cream",
        colors=("#8cc0de", "#ffbfa9", "#ffacac", "#faf0d7"),
        tags=("pastel", "mint", "warm")
    ),
    ColorPalette(
        id="cloud_sky_pink",
        name="Cloud Sky Pink",
        colors=("#95bdff", "#b4e4ff", "#dfffd8", "#f7c8e0"),
        tags=("pastel", "cute", "soft")
    ),
    ColorPalette(
        id="y2k_fairy",
        name="Y2K Fairy",
        colors=("#dfccfb", "#d0bfff", "#beadfa", "#fff3da"),
        tags=("pastel", "y2k", "fairy")
    ),
    ColorPalette(
        id="matcha_latte",
        name="Matcha Latte",
        colors=("#a8bba2", "#c1d0b5", "#d6e8db", "#f5f5f5"),
        tags=("pastel", "nature", "clean")
    ),
    ColorPalette(
        id="strawberry_milk",
        name="Strawberry Milk",
        colors=("#ff7597", "#ff9eb5", "#ffc2d4", "#fff0f5"),
        tags=("pastel", "pink", "candy")
    ),
    ColorPalette(
        id="banana_vanilla",
        name="Banana Vanilla Bubble",
        colors=("#fdcb6e", "#ffeaa7", "#fab1a0", "#fd79a8"),
        tags=("pastel", "warm", "candy")
    ),
    ColorPalette(
        id="creamy_avocado",
        name="Creamy Avocado",
        colors=("#557153", "#7d8f69", "#a9af7e", "#e6e5a3"),
        tags=("pastel", "nature", "vintage")
    ),

    # --- NHÓM 2: RETRO & 70s GROOVY (Đậm chất hoài cổ, cá tính, bắt mắt) ---
    ColorPalette(
        id="retro_sunset_70s",
        name="Retro Sunset 70s",
        colors=("#ff7700", "#ffb703", "#0d6e7a", "#f4f1de"),
        tags=("retro", "groovy", "warm")
    ),
    ColorPalette(
        id="sunflower_honey",
        name="Sunflower Honey",
        colors=("#ffb703", "#fb8500", "#ffbe0b", "#fff3b0"),
        tags=("retro", "warm", "groovy")
    ),
    ColorPalette(
        id="70s_boho_orange",
        name="70s Boho Orange",
        colors=("#d97706", "#f59e0b", "#fbbf24", "#fef3c7"),
        tags=("retro", "warm", "boho")
    ),

    # --- NHÓM 3: NEON, CYBER & POP ART (Tương phản cực cao, hiện đại, kích thích thị giác) ---
    ColorPalette(
        id="electric_purple_orange",
        name="Electric Purple Orange",
        colors=("#8338ec", "#ff006e", "#fb5607", "#ffbe0b"),
        tags=("neon", "pop", "bold")
    ),
    ColorPalette(
        id="hyper_pop",
        name="Hyper Pop Splash",
        colors=("#ff005c", "#ff7a00", "#ff00a0", "#00e0ff"),
        tags=("neon", "pop", "vibrant")
    ),
    ColorPalette(
        id="bubblegum_pop",
        name="Bubblegum Pop",
        colors=("#f72585", "#ff007f", "#4cc9f0", "#4895ef"),
        tags=("neon", "pop", "candy")
    ),

    # --- NHÓM 4: WARM, SUNSET & TROPICAL (Ấm áp, rực rỡ, năng động) ---
    ColorPalette(
        id="sunset_sorbet",
        name="Sunset Sorbet",
        colors=("#ff6fa0", "#ffca3a", "#8ac926", "#1982c4"),
        tags=("warm", "candy", "tropical")
    ),
    ColorPalette(
        id="golden_hour",
        name="Golden Hour",
        colors=("#e63946", "#f1faee", "#a8dadc", "#457b9d"),
        tags=("warm", "vibrant", "clean")
    ),
    ColorPalette(
        id="fiery_mango",
        name="Fiery Mango",
        colors=("#fc8621", "#c24914", "#ff3f00", "#fff80a"),
        tags=("warm", "summer", "bold")
    ),
    ColorPalette(
        id="tropical_carnival",
        name="Tropical Carnival",
        colors=("#009b48", "#fed500", "#ff9f59", "#ff6b81"),
        tags=("warm", "tropical", "vibrant")
    ),
    ColorPalette(
        id="sunny_citrus",
        name="Sunny Citrus Punch",
        colors=("#f59e0b", "#fbbf24", "#f43f5e", "#fffbeb"),
        tags=("warm", "citrus", "summer")
    ),
    ColorPalette(
        id="desert_dune_blush",
        name="Desert Dune Blush",
        colors=("#b45309", "#d97706", "#fcd34d", "#fef3c7"),
        tags=("warm", "earth", "gold")
    ),
    ColorPalette(
        id="mango_passion_punch",
        name="Mango Passion Punch",
        colors=("#ff9f1c", "#ffbf69", "#ffd166", "#ffffff"),
        tags=("warm", "tropical", "candy")
    ),
    ColorPalette(
        id="coral_sunset_glow",
        name="Coral Sunset Glow",
        colors=("#ff6b6b", "#feca57", "#ff9ff3", "#fefae0"),
        tags=("warm", "sunset", "coral")
    ),

    # --- NHÓM 5: COLD, OCEAN & GLACIER (Thanh mát, sâu thẳm, dịu mắt) ---
    ColorPalette(
        id="deep_ocean_breeze",
        name="Deep Ocean Breeze",
        colors=("#2155cd", "#0aa1dd", "#79dae8", "#e8f9fd"),
        tags=("cold", "ocean", "blue")
    ),
    ColorPalette(
        id="nordic_glacier",
        name="Nordic Glacier",
        colors=("#71c9ce", "#a6e3e9", "#cbf1f5", "#e3fdfd"),
        tags=("cold", "clean", "minimal")
    ),
    ColorPalette(
        id="frosty_blue_puffy",
        name="Frosty Blue Puffy",
        colors=("#2563eb", "#5ea5ec", "#a9d6ff", "#f0f7ff"),
        tags=("cold", "blue", "soft")
    ),
    ColorPalette(
        id="mint_lemon_sorbet",
        name="Mint Lemon Sorbet",
        colors=("#06d6a0", "#ffd166", "#ef476f", "#f4f1de"),
        tags=("fresh", "mint", "citrus")
    ),

    # --- NHÓM 6: CUTE, VLOG & DIARY (Phong cách sticker hoạt hình, TikTok viral) ---
    ColorPalette(
        id="daisy_sunshine",
        name="Daisy Sunshine",
        colors=("#f59e0b", "#fde047", "#10b981", "#ffffff"),
        tags=("cute", "daisy", "vibrant")
    ),
    ColorPalette(
        id="candy_crush_pop",
        name="Candy Crush Pop",
        colors=("#ff6a88", "#ff9a8b", "#ff99ac", "#fee140"),
        tags=("cute", "candy", "sweet")
    ),
    ColorPalette(
        id="marshmallow_bubble",
        name="Marshmallow Bubble",
        colors=("#ffaec9", "#ffc2d4", "#ffeaa7", "#ffffff"),
        tags=("cute", "pink", "soft")
    ),
    ColorPalette(
        id="vlog_doodle_gold",
        name="Vlog Doodle Gold",
        colors=("#e5a93b", "#f6d860", "#38bdf8", "#ffffff"),
        tags=("cute", "doodle", "vlog")
    ),
    ColorPalette(
        id="notebook_y2k_vibes",
        name="Notebook Y2K Vibes",
        colors=("#ff4d6d", "#0096c7", "#ff007f", "#f77f00"),
        tags=("cute", "y2k", "multicolor")
    ),
    ColorPalette(
        id="baby_cheeks_blush",
        name="Baby Cheeks Blush",
        colors=("#ff8c94", "#ffaaa6", "#ffd3b5", "#dcedc2"),
        tags=("cute", "pastel", "soft")
    ),
    ColorPalette(
        id="peach_berry_smoothie",
        name="Peach Berry Smoothie",
        colors=("#ff8fab", "#fb6f92", "#ffe5ec", "#ffc2d1"),
        tags=("cute", "pastel", "sweet")
    ),
    ColorPalette(
        id="butter_toast",
        name="Butter Honey Toast",
        colors=("#d4a373", "#faedcd", "#fefae0", "#ccd5ae"),
        tags=("cute", "warm", "vintage")
    ),
    ColorPalette(
        id="sakura_spring",
        name="Sakura Spring Bloom",
        colors=("#e84393", "#fd79a8", "#fab1a0", "#ffeaa7"),
        tags=("cute", "pink", "spring")
    ),
    ColorPalette(
        id="galaxy_cotton_candy",
        name="Galaxy Cotton Candy",
        colors=("#a55eea", "#45aaf2", "#2bcbba", "#fed330"),
        tags=("candy", "pop", "bright")
    ),
    ColorPalette(
        id="strawberry_milk",
        name="Strawberry Milk Shake",
        colors=("#ff4d6d", "#ff758f", "#ffb3c1", "#fff0f3"),
        tags=("cute", "pink", "sweet")
    ),
    ColorPalette(
        id="lemonade_stand",
        name="Sunny Lemonade Stand",
        colors=("#ffe600", "#ffd000", "#ffaa00", "#ffffff"),
        tags=("yellow", "bright", "sunny")
    ),
    ColorPalette(
        id="tropical_island",
        name="Tropical Blue Island",
        colors=("#00b4d8", "#90e0ef", "#ffb703", "#fb8500"),
        tags=("summer", "vibrant", "blue")
    ),
    ColorPalette(
        id="lavender_dream",
        name="Lavender Dream Whisper",
        colors=("#b5838d", "#e5989b", "#ffb4a2", "#ffcdb2"),
        tags=("pastel", "soft", "aesthetic")
    ),
    ColorPalette(
        id="kiwi_lime_splash",
        name="Kiwi Lime Splash",
        colors=("#52b788", "#74c69d", "#95d5b2", "#d8f3dc"),
        tags=("fresh", "green", "nature")
    ),
    ColorPalette(
        id="matcha_cream",
        name="Bright Matcha Cream",
        colors=("#80b918", "#aacc00", "#d4d700", "#ffff3f"),
        tags=("green", "fresh", "bright")
    ),
    ColorPalette(
        id="watermelon_breeze",
        name="Watermelon Breeze",
        colors=("#ff5964", "#f7b2b7", "#35a7ff", "#fffbfe"),
        tags=("summer", "fresh", "candy")
    ),
    ColorPalette(
        id="sunlit_terrace",
        name="Sunlit Golden Terrace",
        colors=("#f39c12", "#f1c40f", "#e67e22", "#fdfefe"),
        tags=("warm", "orange", "sunny")
    ),
    ColorPalette(
        id="aquamarine_gem",
        name="Aquamarine Fresh Gem",
        colors=("#06d6a0", "#118ab2", "#48cae4", "#caf0f8"),
        tags=("teal", "cyan", "cold")
    ),
    ColorPalette(
        id="apricot_sherbet",
        name="Apricot Fruit Sherbet",
        colors=("#f9844a", "#f9c74f", "#90be6d", "#43aa8b"),
        tags=("spring", "fruit", "warm")
    ),
    ColorPalette(
        id="neon_sunset",
        name="Neon Sunset Glow",
        colors=("#ff0054", "#ff5400", "#ffbd00", "#ff70a6"),
        tags=("vibrant", "sunset", "pop")
    ),
    ColorPalette(
        id="sweet_violet",
        name="Sweet Violet Popsicle",
        colors=("#9b5de5", "#f15bb5", "#fee440", "#00f5d4"),
        tags=("pop", "fun", "rainbow")
    ),
    ColorPalette(
        id="cherry_blossom",
        name="Cherry Blossom Petals",
        colors=("#ff758f", "#ff8fa3", "#ffb3c6", "#ffffff"),
        tags=("pink", "flower", "pastel")
    ),
    ColorPalette(
        id="honey_mustard_pop",
        name="Honey Mustard Pop",
        colors=("#ffb703", "#fb8500", "#02c39a", "#f0f3f4"),
        tags=("pop", "bright", "retro")
    ),
]

_PALETTE_BY_ID = {p.id: p for p in COLOR_PALETTES}


def list_palettes(tag: Optional[str] = None) -> List[ColorPalette]:
    """
    Lấy danh sách các bảng màu Color Hunt.
    Nếu có truyền 'tag', lọc các bảng màu chứa tag tương ứng.
    """
    if not tag or not tag.strip():
        return list(COLOR_PALETTES)
    normalized_tag = tag.strip().lower()
    return [p for p in COLOR_PALETTES if normalized_tag in p.tags]


def get_palette_by_id(palette_id: str) -> Optional[ColorPalette]:
    """Tìm bảng màu chính xác theo ID (ví dụ: 'retro_sunset_70s')."""
    clean_id = palette_id.strip().lower().replace("-", "_").replace(" ", "_")
    return _PALETTE_BY_ID.get(clean_id)


def get_random_palette(tag: Optional[str] = None) -> ColorPalette:
    """
    Bốc ngẫu nhiên 1 bảng màu từ Color Hunt.
    Có thể bốc ngẫu nhiên trong một danh mục (tag) nhất định.
    """
    candidates = list_palettes(tag)
    if not candidates:
        logger.warning(f"Không tìm thấy palette nào với tag '{tag}', fallback bốc ngẫu nhiên toàn bộ.")
        candidates = COLOR_PALETTES
    return random.choice(candidates)


def resolve_palette(
    palette: Optional[Union[str, ColorPalette, List[str], Tuple[str, ...]]] = None,
    tag: Optional[str] = None
) -> ColorPalette:
    """
    Phân giải bảng màu để áp dụng cho Overlay Style:
    - Nếu là ColorPalette object: Trả về trực tiếp.
    - Nếu là chuỗi ID hợp lệ: Lấy bảng màu tương ứng.
    - Nếu là chuỗi tag (ví dụ: 'pastel', 'retro', 'neon'): Bốc ngẫu nhiên trong tag đó.
    - Nếu là list/tuple 4 mã hex: Tạo một ColorPalette động tùy chỉnh.
    - Nếu là None hoặc 'random': Bốc ngẫu nhiên 1 bảng màu từ kho Color Hunt.
    """
    if isinstance(palette, ColorPalette):
        return palette

    if isinstance(palette, (list, tuple)) and len(palette) >= 4:
        normalized_colors = tuple(_normalize_hex(str(c)) for c in palette[:4])
        return ColorPalette(
            id="custom_user_palette",
            name="Custom User Palette",
            colors=(normalized_colors[0], normalized_colors[1], normalized_colors[2], normalized_colors[3]),
            tags=("custom",)
        )

    if isinstance(palette, str):
        cleaned = palette.strip().lower()
        if cleaned and cleaned != "random":
            by_id = get_palette_by_id(cleaned)
            if by_id is not None:
                return by_id
            # Thử xem có phải người dùng truyền tag không
            by_tag = list_palettes(cleaned)
            if by_tag:
                return random.choice(by_tag)

    # Mặc định random từ kho Color Hunt (hoặc theo tag nếu có)
    return get_random_palette(tag)
