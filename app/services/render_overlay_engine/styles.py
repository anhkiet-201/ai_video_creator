import html
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union

from app.services.render_overlay_engine.fonts import (
    format_font_family,
    get_font_query_param,
)
from app.services.render_overlay_engine.palettes import (
    ColorPalette,
    generate_pastel_rainbow,
    get_contrast_text_color,
    get_luminance,
    get_vibrancy,
    is_dark,
    resolve_palette,
    to_candy_color,
    to_pastel_cloud,
)


def wrap_text_lines(text: str, max_chars: int = 18) -> List[str]:
    """Ngắt dòng tiếng Việt thông minh cho tiêu đề overlay để bố cục cân đối và không bị tràn khung hình"""
    words = text.split()
    if not words:
        return []
    lines: List[str] = []
    curr: List[str] = []
    curr_len = 0
    for w in words:
        add_len = len(w) + (1 if curr else 0)
        if curr_len + add_len <= max_chars:
            curr.append(w)
            curr_len += add_len
        else:
            if curr:
                lines.append(" ".join(curr))
            curr = [w]
            curr_len = len(w)
    if curr:
        lines.append(" ".join(curr))
    return lines


@dataclass
class BaseOverlayStyle(ABC):
    """
    Lớp cơ sở trừu tượng cho mọi phong cách đồ họa Overlay.
    Các class con chứa các thuộc tính riêng của từng style và tự định nghĩa cách render ra HTML/CSS.
    Hoàn toàn độc lập, không phụ thuộc vào RenderOverlayEngine.
    """
    font_family: str = "'Nunito', -apple-system, BlinkMacSystemFont, sans-serif"
    google_font_url: str = (
        "https://fonts.googleapis.com/css2?"
        "family=Comfortaa:wght@700&"
        "family=Fredoka:wght@700;900&"
        "family=Montserrat:wght@800;900&"
        "family=Nunito:wght@800;900&"
        "family=Playfair+Display:wght@800;900&"
        "family=Quicksand:wght@700;800&"
        "family=Shrikhand&"
        "family=Titan+One&display=swap"
    )
    font: Optional[str] = None
    palette: Optional[Union[str, ColorPalette, List[str], Tuple[str, ...]]] = None

    def __post_init__(self) -> None:
        if self.font:
            self.apply_font(self.font)
        if self.palette:
            self.apply_palette(self.palette)

    def apply_palette(self, palette: Union[str, ColorPalette, List[str], Tuple[str, ...]]) -> None:
        """
        Phương thức cơ sở để áp dụng bảng màu ColorPalette vào style.
        Các class style con override phương thức này để ánh xạ mã màu vào thành phần đồ họa của mình.
        """
        resolved = resolve_palette(palette)
        self.palette = resolved

    def apply_font(self, font_name: str) -> None:
        """
        Áp dụng font được chỉ định cho style:
        - Cập nhật self.font
        - Cập nhật self.font_family
        - Nạp link Google Fonts tương ứng vào template
        """
        if not font_name or not str(font_name).strip():
            return
        clean_font = str(font_name).strip().strip("'\"")
        self.font = clean_font
        self.font_family = format_font_family(clean_font)
        param = get_font_query_param(clean_font)
        font_token = f"family={param}"
        if font_token not in self.google_font_url and clean_font not in self.google_font_url:
            if "&display=swap" in self.google_font_url:
                base_part = self.google_font_url.replace("&display=swap", "")
                self.google_font_url = f"{base_part}&{font_token}&display=swap"
            else:
                self.google_font_url = f"{self.google_font_url}&{font_token}&display=swap"

    def _get_base_html(self, body_content: str, custom_css: str, width: int, height: int) -> str:
        """Tạo khung HTML5 hoàn chỉnh với canvas trong suốt và font chuẩn"""
        return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="{self.google_font_url}" rel="stylesheet">
  <style>
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    body {{
      width: {width}px;
      height: {height}px;
      background: transparent;
      display: flex;
      flex-direction: column;
      justify-content: flex-start;
      align-items: center;
      padding-top: 220px;
      padding-left: 40px;
      padding-right: 40px;
      font-family: {self.font_family};
      overflow: hidden;
      position: relative;
    }}
    .overlay-container {{
      width: 100%;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
    }}
    {custom_css}
  </style>
</head>
<body>
  <div class="overlay-container">
    {body_content}
  </div>
</body>
</html>"""

    @abstractmethod
    def render_html(
        self,
        content: str,
        subcontent: Optional[str] = None,
        width: int = 1080,
        height: int = 1920
    ) -> str:
        """
        Sinh chuỗi HTML5 & CSS hoàn chỉnh để Chrome Headless chụp ra ảnh PNG.
        - content: Nội dung chính
        - subcontent: Nội dung phụ/điểm nhấn (có thể để trống)
        - width, height: Kích thước canvas
        """
        pass


@dataclass
class TornPaperStyle(BaseOverlayStyle):
    """
    Phong cách Báo Xé Cổ Điển (Torn Paper).
    Mẩu giấy xé rách lởm chởm, xoay nhẹ tự nhiên theo phong cách CapCut thịnh hành.
    """
    paper_color: str = "#f7f1e5"
    text_color: str = "#42211d"
    highlight_bg: str = "#fde8d0"
    highlight_text: str = "#801d1d"
    dot_color: str = "#d3c5b4"
    tilt_intensity: float = 1.6
    font_size_content: int = 48
    font_size_subcontent: int = 38

    def apply_palette(self, palette: Union[str, ColorPalette, List[str], Tuple[str, ...]]) -> None:
        p = resolve_palette(palette)
        self.palette = p
        sorted_by_lum = sorted(p.colors, key=get_luminance)
        self.paper_color = sorted_by_lum[3]
        self.text_color = sorted_by_lum[0]
        self.highlight_bg = sorted_by_lum[2]
        self.highlight_text = sorted_by_lum[1] if is_dark(sorted_by_lum[1]) else sorted_by_lum[0]
        self.dot_color = sorted_by_lum[2]

    def render_html(
        self,
        content: str,
        subcontent: Optional[str] = None,
        width: int = 1080,
        height: int = 1920
    ) -> str:
        escaped_content = html.escape(content.strip())
        escaped_subcontent = html.escape(subcontent.strip()) if subcontent and subcontent.strip() else ""

        words = escaped_content.split()
        words_html = []
        for i, w in enumerate(words):
            words_html.append(f'<span class="torn-word" style="--rot: {i % 3}">{w}</span>')

        sub_html = ""
        if escaped_subcontent:
            sub_html = f'<div class="torn-sub-wrapper"><span class="torn-word torn-highlight">{escaped_subcontent}</span></div>'

        custom_css = f"""
        .svg-defs {{
          position: absolute;
          width: 0;
          height: 0;
        }}
        .torn-group {{
          display: flex;
          flex-wrap: wrap;
          justify-content: center;
          align-items: center;
          gap: 10px 14px;
          max-width: 960px;
        }}
        .torn-word {{
          background-color: {self.paper_color};
          background-image: radial-gradient({self.dot_color} 0.75px, transparent 0.75px);
          background-size: 6px 6px;
          padding: 8px 22px;
          font-size: {self.font_size_content}px;
          font-weight: 900;
          color: {self.text_color};
          filter: url(#torn-filter) drop-shadow(0 3px 6px rgba(0,0,0,0.3));
          display: inline-block;
          letter-spacing: 0.5px;
          line-height: 1.15;
          transform: rotate(calc((var(--rot, 0) - 1.5) * {self.tilt_intensity}deg));
          text-transform: uppercase;
        }}
        .torn-sub-wrapper {{
          margin-top: 18px;
        }}
        .torn-highlight {{
          background-color: {self.highlight_bg};
          color: {self.highlight_text};
          font-size: {self.font_size_subcontent}px;
          padding: 8px 26px;
        }}
        """

        svg_defs = """
        <svg class="svg-defs">
          <defs>
            <filter id="torn-filter">
              <feTurbulence type="fractalNoise" baseFrequency="0.06" numOctaves="3" result="noise"/>
              <feDisplacementMap in="SourceGraphic" in2="noise" scale="5" xChannelSelector="R" yChannelSelector="G"/>
            </filter>
          </defs>
        </svg>
        """

        body_content = f"""
        {svg_defs}
        <div class="torn-group">
          {"".join(words_html)}
        </div>
        {sub_html}
        """
        return self._get_base_html(body_content, custom_css, width, height)


@dataclass
class BubbleCloudStyle(BaseOverlayStyle):
    """
    Phong cách Vệt Mây Highlight Bồng Bềnh (Bubble Cloud).
    Đám mây pastel mềm mại với bộ lọc mờ SVG Soft Feathering chuẩn TikTok CapCut.
    """
    cloud_color: str = "#ff6fa0"
    sub_cloud_color: str = "#ffca3a"
    content_stroke_color: str = "#18181b"
    content_fill_color: str = "#ffffff"
    pill_bg_color: str = "#ffea79"
    pill_text_color: str = "#1a1a1a"
    pill_icon: str = "✨"
    font_size_content: int = 76
    font_size_subcontent: int = 34

    def apply_palette(self, palette: Union[str, ColorPalette, List[str], Tuple[str, ...]]) -> None:
        p = resolve_palette(palette)
        self.palette = p
        self.cloud_color = p.c1
        self.sub_cloud_color = p.c2
        self.pill_bg_color = p.c3
        self.pill_text_color = get_contrast_text_color(self.pill_bg_color)
        self.content_fill_color = "#ffffff"
        self.content_stroke_color = "#18181b"

    def render_html(
        self,
        content: str,
        subcontent: Optional[str] = None,
        width: int = 1080,
        height: int = 1920
    ) -> str:
        escaped_content = html.escape(content.strip())
        escaped_subcontent = html.escape(subcontent.strip()) if subcontent and subcontent.strip() else ""

        lines = wrap_text_lines(escaped_content, max_chars=14)
        if not lines:
            lines = [escaped_content]

        line_height = int(self.font_size_content * 1.35)
        total_h = line_height * len(lines) + 80
        start_y = int(total_h / 2 - (len(lines) - 1) * line_height / 2) + 6

        svg_cloud_blur = ""
        svg_cloud_core = ""
        svg_stroke = ""
        svg_fill = ""

        for idx, line in enumerate(lines):
            curr_y = start_y + idx * line_height
            # Lớp 1: Vệt mây hồng tỏa mờ mềm mại
            svg_cloud_blur += (
                f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                f'fill="none" stroke="{self.cloud_color}" stroke-width="48" stroke-linejoin="round" '
                f'stroke-linecap="round" opacity="0.95" filter="url(#cloud-feather)">{line}</text>'
            )
            # Lớp 2: Vệt mây hồng cốt lõi định hình mây bồng bềnh
            svg_cloud_core += (
                f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                f'fill="none" stroke="{self.cloud_color}" stroke-width="36" stroke-linejoin="round" '
                f'stroke-linecap="round" opacity="0.98">{line}</text>'
            )
            # Lớp 3: Viền đen mực sắc nét
            svg_stroke += (
                f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                f'fill="none" stroke="{self.content_stroke_color}" stroke-width="8" stroke-linejoin="round" '
                f'stroke-linecap="round">{line}</text>'
            )
            # Lớp 4: Lòng chữ trắng tinh khôi
            svg_fill += (
                f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                f'fill="{self.content_fill_color}">{line}</text>'
            )

        sub_html = ""
        if escaped_subcontent:
            sub_lines = wrap_text_lines(escaped_subcontent, max_chars=22)
            if not sub_lines:
                sub_lines = [escaped_subcontent]

            sub_line_height = int(self.font_size_subcontent * 1.35)
            sub_total_h = sub_line_height * len(sub_lines) + 40
            sub_start_y = int(sub_total_h / 2 - (len(sub_lines) - 1) * sub_line_height / 2) + 4

            sub_cloud_blur = ""
            sub_cloud_core = ""
            sub_stroke = ""
            sub_fill = ""

            for idx, line in enumerate(sub_lines):
                curr_y = sub_start_y + idx * sub_line_height
                sub_cloud_blur += (
                    f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                    f'fill="none" stroke="{self.sub_cloud_color}" stroke-width="28" stroke-linejoin="round" '
                    f'stroke-linecap="round" opacity="0.95" filter="url(#cloud-feather)">{line}</text>'
                )
                sub_cloud_core += (
                    f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                    f'fill="none" stroke="{self.sub_cloud_color}" stroke-width="20" stroke-linejoin="round" '
                    f'stroke-linecap="round" opacity="0.98">{line}</text>'
                )
                sub_stroke += (
                    f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                    f'fill="none" stroke="{self.content_stroke_color}" stroke-width="5.5" stroke-linejoin="round" '
                    f'stroke-linecap="round">{line}</text>'
                )
                sub_fill += (
                    f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                    f'fill="#ffffff">{line}</text>'
                )

            sub_html = f"""
            <div class="cloud-sub-wrap">
              <svg class="cloud-sub-svg" width="1000" height="{sub_total_h}" viewBox="0 0 1000 {sub_total_h}">
                <g font-family="{self.font_family}" font-weight="900" font-size="{self.font_size_subcontent}" letter-spacing="1">
                  {sub_cloud_blur}
                  {sub_cloud_core}
                  {sub_stroke}
                  {sub_fill}
                </g>
              </svg>
            </div>
            """

        custom_css = f"""
        .cloud-container-wrap {{
          position: relative;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          max-width: 1000px;
        }}
        .cloud-svg-canvas {{
          overflow: visible;
          filter: drop-shadow(0 12px 24px rgba(0,0,0,0.3));
        }}

        /* Subcontent: Thuần chữ vệt mây mềm SVG không có khối hộp pill */
        .cloud-sub-wrap {{
          margin-top: 18px;
          display: flex;
          justify-content: center;
          align-items: center;
          max-width: 1000px;
        }}
        .cloud-sub-svg {{
          overflow: visible;
          filter: drop-shadow(0 8px 18px rgba(0,0,0,0.25));
        }}
        """

        svg_defs = """
        <svg style="position: absolute; width: 0; height: 0; overflow: hidden;">
          <defs>
            <filter id="cloud-feather" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur in="SourceGraphic" stdDeviation="4.5" result="blur"/>
              <feMerge>
                <feMergeNode in="blur"/>
                <feMergeNode in="blur"/>
                <feMergeNode in="SourceGraphic"/>
              </feMerge>
            </filter>
          </defs>
        </svg>
        """

        body_content = f"""
        {svg_defs}
        <div class="cloud-container-wrap">
          <svg class="cloud-svg-canvas" width="1000" height="{total_h}" viewBox="0 0 1000 {total_h}">
            <g font-family="{self.font_family}" font-weight="900" font-size="{self.font_size_content}" letter-spacing="0.5">
              {svg_cloud_blur}
              {svg_cloud_core}
              {svg_stroke}
              {svg_fill}
            </g>
          </svg>
          {sub_html}
        </div>
        """
        return self._get_base_html(body_content, custom_css, width, height)


@dataclass
class PastelMulticolorStyle(BaseOverlayStyle):
    """
    Phong cách Kẹo Ngọt Đa Sắc (Pastel Multicolor) kèm icon hoa mini hoặc sticker.
    Mỗi từ được bao bọc bởi dải viền màu pastel ngọt ngào.
    """
    color_palette: List[str] = field(default_factory=lambda: [
        "#ffb3c6", "#bbf2f6", "#ffeaa7", "#c7ecee", "#e8d7ff", "#bbf7d0"
    ])
    flower_icons: List[str] = field(default_factory=lambda: ["🌸", "🌼", "✨", "🌺", "⭐"])
    sub_bg_color: str = "#ffeaa7"
    sub_icon: str = "🌸"
    text_color: str = "#18181b"
    font_size_content: int = 48
    font_size_subcontent: int = 38

    def apply_palette(self, palette: Union[str, ColorPalette, List[str], Tuple[str, ...]]) -> None:
        p = resolve_palette(palette)
        self.palette = p
        # Tự động tạo dải màu pastel cầu vồng ngọt ngào từ bảng màu
        self.color_palette = generate_pastel_rainbow(p, count=6)
        self.sub_bg_color = to_pastel_cloud(p.c3)
        self.text_color = "#18181b"

    def render_html(
        self,
        content: str,
        subcontent: Optional[str] = None,
        width: int = 1080,
        height: int = 1920
    ) -> str:
        escaped_content = html.escape(content.strip())
        escaped_subcontent = html.escape(subcontent.strip()) if subcontent and subcontent.strip() else ""

        words = escaped_content.split()
        items_html = []
        for i, w in enumerate(words):
            c = self.color_palette[i % len(self.color_palette)]
            fl = f'<span class="flower-mini">{self.flower_icons[i % len(self.flower_icons)]}</span>' if (i % 2 == 0) else ''
            items_html.append(f'<span class="pastel-word" data-text="{w}" style="--p-color: {c};">{w}{fl}</span>')

        sub_html = ""
        if escaped_subcontent:
            icon_part = f" {self.sub_icon}" if self.sub_icon else ""
            sub_html = (
                f'<div class="pastel-sub-wrapper">'
                f'<span class="pastel-word pastel-sub" data-text="{escaped_subcontent}" '
                f'style="--p-color: {self.sub_bg_color};">{escaped_subcontent}{icon_part}</span>'
                f'</div>'
            )

        custom_css = f"""
        .pastel-group {{
          display: flex;
          flex-wrap: wrap;
          justify-content: center;
          gap: 10px 14px;
          max-width: 960px;
        }}
        .pastel-word {{
          position: relative;
          font-size: {self.font_size_content}px;
          font-weight: 900;
          color: {self.text_color};
          display: inline-block;
          line-height: 1.2;
          text-transform: uppercase;
        }}
        .pastel-word::before {{
          content: attr(data-text);
          position: absolute;
          left: 0;
          top: 0;
          z-index: -1;
          -webkit-text-stroke: 18px var(--p-color);
          filter: drop-shadow(0 2px 5px rgba(0,0,0,0.18));
        }}
        .flower-mini {{
          position: absolute;
          top: -16px;
          right: -10px;
          font-size: 24px;
          filter: drop-shadow(0 2px 4px rgba(0,0,0,0.2));
        }}
        .pastel-sub-wrapper {{
          margin-top: 18px;
        }}
        .pastel-sub {{
          font-size: {self.font_size_subcontent}px;
        }}
        """

        body_content = f"""
        <div class="pastel-group">
          {"".join(items_html)}
        </div>
        {sub_html}
        """
        return self._get_base_html(body_content, custom_css, width, height)


# ==============================================================================
# 4 PHONG CÁCH STICKER & 3D BUBBLE TYPOGRAPHY CAO CẤP MỚI
# ==============================================================================

@dataclass
class MarshmallowPinkStyle(BaseOverlayStyle):
    """
    Phong cách 1: Kẹo Dẻo Marshmallow Hồng & Hoa Mặt Trời (Lấy cảm hứng từ mẫu 'TODAY STORY').
    Chữ bong bóng 3D phồng dày màu hồng dâu, bao bọc bởi đám mây marshmallow pastel nhiều lớp,
    hoa mặt trời cười dễ thương và các ngôi sao lấp lánh vàng.
    """
    font_family: str = "'Comfortaa', 'Nunito', cursive, sans-serif"
    pink_text_color: str = "#ffaec9"
    pink_cloud_color: str = "#ffc2d4"
    stroke_black_color: str = "#18181b"
    outer_white_color: str = "#ffffff"
    flower_petal_color: str = "#ffaec9"
    font_size_content: int = 56
    font_size_subcontent: int = 32
    show_decorations: bool = True

    def apply_palette(self, palette: Union[str, ColorPalette, List[str], Tuple[str, ...]]) -> None:
        p = resolve_palette(palette)
        self.palette = p
        # Lòng chữ kẹo ngọt ngào tươi sáng (bảo tồn sắc độ của bảng màu, không bao giờ bị trắng toát)
        self.pink_text_color = to_candy_color(p.c1)
        # Đám mây marshmallow pastel bồng bềnh như kem
        self.pink_cloud_color = to_pastel_cloud(p.c1)
        # Cánh hoa mặt trời đồng bộ màu điểm nhấn từ palette
        self.flower_petal_color = to_candy_color(p.c3)
        self.stroke_black_color = "#18181b"
        self.outer_white_color = "#ffffff"

    def render_html(
        self,
        content: str,
        subcontent: Optional[str] = None,
        width: int = 1080,
        height: int = 1920
    ) -> str:
        escaped_content = html.escape(content.strip())
        escaped_subcontent = html.escape(subcontent.strip()) if subcontent and subcontent.strip() else ""

        lines = wrap_text_lines(escaped_content, max_chars=14)
        if not lines:
            lines = [escaped_content]

        line_h = 95
        start_y = 80
        total_h = len(lines) * line_h + 50

        # Sinh các lớp SVG để tạo chữ phồng marshmallow 3D hoàn mỹ
        svg_white_border = ""
        svg_pink_cloud = ""
        svg_black_stroke = ""
        svg_pink_fill = ""

        for idx, line in enumerate(lines):
            y = start_y + idx * line_h
            svg_white_border += f'<text x="50%" y="{y}" text-anchor="middle" fill="none" stroke="{self.outer_white_color}" stroke-width="48" stroke-linejoin="round" stroke-linecap="round">{line}</text>\n'
            svg_pink_cloud += f'<text x="50%" y="{y}" text-anchor="middle" fill="none" stroke="{self.pink_cloud_color}" stroke-width="36" stroke-linejoin="round" stroke-linecap="round">{line}</text>\n'
            svg_black_stroke += f'<text x="50%" y="{y}" text-anchor="middle" fill="none" stroke="{self.stroke_black_color}" stroke-width="8" stroke-linejoin="round" stroke-linecap="round">{line}</text>\n'
            svg_pink_fill += f'<text x="50%" y="{y}" text-anchor="middle" fill="{self.pink_text_color}">{line}</text>\n'

        sub_html = ""
        if escaped_subcontent:
            sub_html = f"""
            <div class="marshmallow-sub-pill">
              <span class="sub-daisy-flower">🌸</span>
              <span class="sub-text-label">{escaped_subcontent}</span>
              <span class="sub-sparkle-star">✨</span>
            </div>
            """

        decorations_html = ""
        if self.show_decorations:
            decorations_html = f"""
            <div class="marshmallow-flower-tl">
              <svg width="90" height="90" viewBox="0 0 100 100">
                <!-- 8 Cánh hoa đồng bộ màu -->
                <g fill="{self.flower_petal_color}" stroke="#18181b" stroke-width="3.5">
                  <circle cx="50" cy="22" r="16"/>
                  <circle cx="50" cy="78" r="16"/>
                  <circle cx="22" cy="50" r="16"/>
                  <circle cx="78" cy="50" r="16"/>
                  <circle cx="30" cy="30" r="16"/>
                  <circle cx="70" cy="70" r="16"/>
                  <circle cx="30" cy="70" r="16"/>
                  <circle cx="70" cy="30" r="16"/>
                </g>
                <!-- Nhụy vàng mặt cười -->
                <circle cx="50" cy="50" r="18" fill="#ffd700" stroke="#18181b" stroke-width="3.5"/>
                <circle cx="44" cy="47" r="2.5" fill="#18181b"/>
                <circle cx="56" cy="47" r="2.5" fill="#18181b"/>
                <path d="M 44 54 Q 50 60 56 54" fill="none" stroke="#18181b" stroke-width="2.5" stroke-linecap="round"/>
              </svg>
            </div>
            <div class="marshmallow-flower-br">
              <svg width="80" height="80" viewBox="0 0 100 100">
                <g fill="{self.flower_petal_color}" stroke="#18181b" stroke-width="3.5">
                  <circle cx="50" cy="22" r="16"/>
                  <circle cx="50" cy="78" r="16"/>
                  <circle cx="22" cy="50" r="16"/>
                  <circle cx="78" cy="50" r="16"/>
                  <circle cx="30" cy="30" r="16"/>
                  <circle cx="70" cy="70" r="16"/>
                  <circle cx="30" cy="70" r="16"/>
                  <circle cx="70" cy="30" r="16"/>
                </g>
                <circle cx="50" cy="50" r="18" fill="#ffd700" stroke="#18181b" stroke-width="3.5"/>
                <circle cx="44" cy="47" r="2.5" fill="#18181b"/>
                <circle cx="56" cy="47" r="2.5" fill="#18181b"/>
                <path d="M 44 54 Q 50 60 56 54" fill="none" stroke="#18181b" stroke-width="2.5" stroke-linecap="round"/>
              </svg>
            </div>
            <span class="sparkle-star star-1">✦</span>
            <span class="sparkle-star star-2">★</span>
            <span class="sparkle-star star-3">✦</span>
            <span class="sparkle-star star-4">★</span>
            """

        custom_css = f"""
        .marshmallow-wrap {{
          position: relative;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          max-width: 980px;
        }}
        .marshmallow-svg-card {{
          overflow: visible;
          filter: drop-shadow(0 14px 28px rgba(0, 0, 0, 0.18));
        }}
        .marshmallow-flower-tl {{
          position: absolute;
          top: -35px;
          left: -20px;
          transform: rotate(-15deg);
          filter: drop-shadow(0 4px 10px rgba(0,0,0,0.2));
        }}
        .marshmallow-flower-br {{
          position: absolute;
          bottom: -15px;
          right: -25px;
          transform: rotate(20deg);
          filter: drop-shadow(0 4px 10px rgba(0,0,0,0.2));
        }}
        .sparkle-star {{
          position: absolute;
          color: #ffc93c;
          font-weight: bold;
          filter: drop-shadow(0 2px 4px rgba(255,200,50,0.5));
          user-select: none;
        }}
        .star-1 {{ top: 15px; left: 18%; font-size: 28px; }}
        .star-2 {{ top: 5px; right: 20%; font-size: 22px; }}
        .star-3 {{ bottom: 25px; left: 22%; font-size: 24px; }}
        .star-4 {{ bottom: 15px; right: 28%; font-size: 26px; }}

        /* Subcontent: Puffy Marshmallow Pill ngọt ngào đồng điệu */
        .marshmallow-sub-pill {{
          margin-top: 22px;
          background: #ffffff;
          border: 3.5px solid {self.stroke_black_color};
          color: #18181b;
          font-size: {self.font_size_subcontent}px;
          font-weight: 900;
          padding: 10px 32px;
          border-radius: 999px;
          box-shadow: 
            0 0 0 5px {self.pink_cloud_color},
            0 0 0 8px #ffffff,
            0 10px 22px rgba(0, 0, 0, 0.18);
          display: inline-flex;
          align-items: center;
          gap: 10px;
          letter-spacing: 0.8px;
          text-transform: uppercase;
          transform: rotate(-0.8deg);
          max-width: 880px;
          line-height: 1.3;
          text-align: center;
        }}
        .sub-daisy-flower {{
          font-size: 26px;
          filter: drop-shadow(0 2px 4px rgba(0,0,0,0.15));
        }}
        .sub-sparkle-star {{
          font-size: 22px;
          color: #ffb703;
          filter: drop-shadow(0 2px 4px rgba(255, 183, 3, 0.5));
        }}
        """

        body_content = f"""
        <div class="marshmallow-wrap">
          {decorations_html}
          <svg class="marshmallow-svg-card" width="1000" height="{total_h}" viewBox="0 0 1000 {total_h}">
            <g font-family="{self.font_family}" font-weight="900" font-size="{self.font_size_content}" letter-spacing="1">
              {svg_white_border}
              {svg_pink_cloud}
              {svg_black_stroke}
              {svg_pink_fill}
            </g>
          </svg>
          {sub_html}
        </div>
        """
        return self._get_base_html(body_content, custom_css, width, height)


@dataclass
class VlogDoodleStickerStyle(BaseOverlayStyle):
    """
    Phong cách 2: Vlog Sticker Chữ 3D Vân Giấy & Doodle Phấn Trắng (Lấy cảm hứng từ mẫu 'Mini Vlog').
    Chữ trắng vân giấy nổi khối 3D vàng mù tạt, viền đen kép và viền sticker die-cut trắng,
    kèm tia hành động comic và dải icon doodle phấn trắng (tim, chat, máy bay, bookmark).
    """
    font_family: str = "'Comfortaa', 'Quicksand', -apple-system, sans-serif"
    text_color: str = "#ffffff"
    shadow_3d_color: str = "#e5a93b"
    stroke_color: str = "#18181b"
    burst_dash_color: str = "#ffffff"
    doodle_icons_color: str = "#ffffff"
    font_size_content: int = 56
    font_size_subcontent: int = 32
    show_doodles: bool = True

    def apply_palette(self, palette: Union[str, ColorPalette, List[str], Tuple[str, ...]]) -> None:
        p = resolve_palette(palette)
        self.palette = p
        # Sắp xếp các màu theo mức độ rực rỡ và sống động (Chroma / Saturation)
        vibrant_sorted = sorted(p.colors, key=get_vibrancy, reverse=True)
        # Màu chính của khối 3D chữ
        self.shadow_3d_color = vibrant_sorted[0]
        # Màu rực rỡ thứ 2 cho các tia comic action góc trên
        self.burst_dash_color = vibrant_sorted[1] if len(vibrant_sorted) > 1 and get_vibrancy(vibrant_sorted[1]) > 0.1 else to_candy_color(p.c3)
        # Màu cho các icon doodle (lấy màu rực rỡ kẹo ngọt đồng bộ)
        self.doodle_icons_color = to_candy_color(self.burst_dash_color)

    def render_html(
        self,
        content: str,
        subcontent: Optional[str] = None,
        width: int = 1080,
        height: int = 1920
    ) -> str:
        escaped_content = html.escape(content.strip())
        escaped_subcontent = html.escape(subcontent.strip()) if subcontent and subcontent.strip() else ""

        lines = wrap_text_lines(escaped_content, max_chars=16)
        if not lines:
            lines = [escaped_content]
        lines_html = "<br>".join(lines)

        doodles_bar_html = ""
        if self.show_doodles:
            doodles_bar_html = f"""
            <div class="vlog-doodle-bar">
              <svg width="34" height="30" viewBox="0 0 32 30" fill="none" stroke="{self.doodle_icons_color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                <path d="M16 26 C16 26 3 18 3 9 C3 5 6 2 10 2 C13 2 15 4 16 6 C17 4 19 2 22 2 C26 2 29 5 29 9 C29 18 16 26 16 26 Z"/>
              </svg>
              <svg width="34" height="30" viewBox="0 0 32 30" fill="none" stroke="{self.doodle_icons_color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                <path d="M4 14 C4 8 9 4 16 4 C23 4 28 8 28 14 C28 20 23 24 16 24 C13 24 11 23 9 22 L4 25 L5 20 C4.5 18 4 16 4 14 Z"/>
              </svg>
              <svg width="34" height="30" viewBox="0 0 32 30" fill="none" stroke="{self.doodle_icons_color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                <path d="M3 15 L28 4 L18 27 L14 17 L3 15 Z"/>
              </svg>
              <svg width="30" height="30" viewBox="0 0 28 30" fill="none" stroke="{self.doodle_icons_color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                <path d="M5 4 C5 3 6 2 7 2 L21 2 C22 2 23 3 23 4 L23 28 L14 21 L5 28 L5 4 Z"/>
              </svg>
            </div>
            """

        sub_html = ""
        if escaped_subcontent:
            sub_html = f"""
            <div class="vlog-sub-badge">
              <span class="vlog-sub-bullet">✨</span>
              <span>{escaped_subcontent}</span>
              <span class="vlog-sub-bullet">✨</span>
            </div>
            """

        custom_css = f"""
        .vlog-sticker-wrap {{
          position: relative;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          max-width: 960px;
        }}
        /* Tia hành động comic góc trên */
        .vlog-rays-left {{
          position: absolute;
          top: -30px;
          left: 40px;
          display: flex;
          gap: 6px;
        }}
        .vlog-rays-right {{
          position: absolute;
          top: -30px;
          right: 40px;
          display: flex;
          gap: 6px;
        }}
        .burst-dash {{
          width: 6px;
          background: {self.burst_dash_color};
          border-radius: 4px;
          filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5));
        }}
        .b-l1 {{ height: 26px; transform: rotate(-35deg); margin-top: 10px; }}
        .b-l2 {{ height: 32px; transform: rotate(-10deg); }}
        .b-l3 {{ height: 26px; transform: rotate(15deg); margin-top: 10px; }}

        .b-r1 {{ height: 26px; transform: rotate(-15deg); margin-top: 10px; }}
        .b-r2 {{ height: 32px; transform: rotate(10deg); }}
        .b-r3 {{ height: 26px; transform: rotate(35deg); margin-top: 10px; }}

        /* Chữ nổi 3D vân giấy viền sticker */
        .vlog-title-box {{
          position: relative;
          text-align: center;
          padding: 20px 30px;
        }}
        .vlog-title-text {{
          color: {self.text_color};
          font-size: {self.font_size_content}px;
          font-weight: 900;
          line-height: 1.25;
          letter-spacing: 1.5px;
          text-transform: capitalize;
          -webkit-text-stroke: 3.5px {self.stroke_color};
          /* Đổ bóng 3D vàng cam mù tạt */
          text-shadow: 
            2px 2px 0 {self.shadow_3d_color},
            4px 4px 0 {self.shadow_3d_color},
            6px 6px 0 {self.shadow_3d_color},
            8px 8px 0 {self.shadow_3d_color},
            9px 9px 0 {self.stroke_color},
            10px 10px 0 {self.stroke_color},
            11px 11px 0 {self.stroke_color};
          /* Viền ngoài cùng Sticker Die-cut màu trắng */
          filter: 
            drop-shadow(0 0 0 10px #ffffff)
            drop-shadow(0 12px 28px rgba(0,0,0,0.6));
        }}

        /* Subcontent: Sticker Tag 3D vàng cam hòa hợp với tiêu đề chính */
        .vlog-sub-badge {{
          margin-top: 16px;
          background: #ffffff;
          border: 3px solid {self.stroke_color};
          color: #18181b;
          font-size: {self.font_size_subcontent}px;
          font-weight: 900;
          padding: 9px 34px;
          border-radius: 14px;
          box-shadow: 
            3px 3px 0 {self.shadow_3d_color},
            5px 5px 0 {self.stroke_color},
            0 10px 22px rgba(0,0,0,0.45);
          letter-spacing: 0.8px;
          text-transform: uppercase;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          max-width: 880px;
          line-height: 1.3;
          text-align: center;
        }}
        .vlog-sub-bullet {{
          color: {self.shadow_3d_color};
          font-size: 20px;
        }}

        .vlog-doodle-bar {{
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 24px;
          margin-top: 20px;
          padding: 8px 24px;
          background: rgba(24, 24, 27, 0.88);
          border: 2.5px solid {self.shadow_3d_color};
          border-radius: 999px;
          box-shadow: 
            0 4px 14px rgba(0,0,0,0.4),
            0 0 0 4px rgba(255,255,255,0.9);
        }}
        """

        # Đặt subcontent ngay dưới title, và doodle bar ở đáy làm dải footer
        body_content = f"""
        <div class="vlog-sticker-wrap">
          <div class="vlog-rays-left">
            <span class="burst-dash b-l1"></span>
            <span class="burst-dash b-l2"></span>
            <span class="burst-dash b-l3"></span>
          </div>
          <div class="vlog-rays-right">
            <span class="burst-dash b-r1"></span>
            <span class="burst-dash b-r2"></span>
            <span class="burst-dash b-r3"></span>
          </div>
          <div class="vlog-title-box">
            <div class="vlog-title-text">{lines_html}</div>
          </div>
          {sub_html}
          {doodles_bar_html}
        </div>
        """
        return self._get_base_html(body_content, custom_css, width, height)


@dataclass
class DaisyDiaryStyle(BaseOverlayStyle):
    """
    Phong cách 3: Nhật Ký Hoa Cúc Vàng Sunny Daisy (Lấy cảm hứng từ mẫu 'DEAR DIARY').
    Chữ khối đậm màu trắng viền 3D vàng mật ong rực rỡ, viền đen sắc nét,
    ôm trọn bởi viền sticker trắng liền khối đính các cụm hoa cúc daisy tươi vui.
    """
    font_family: str = "'Montserrat', 'Nunito', sans-serif"
    text_color: str = "#ffffff"
    honey_yellow: str = "#f59e0b"
    stroke_color: str = "#18181b"
    font_size_content: int = 58
    font_size_subcontent: int = 32
    show_daisies: bool = True

    def apply_palette(self, palette: Union[str, ColorPalette, List[str], Tuple[str, ...]]) -> None:
        p = resolve_palette(palette)
        self.palette = p
        self.honey_yellow = p.c1

    def render_html(
        self,
        content: str,
        subcontent: Optional[str] = None,
        width: int = 1080,
        height: int = 1920
    ) -> str:
        escaped_content = html.escape(content.strip())
        escaped_subcontent = html.escape(subcontent.strip()) if subcontent and subcontent.strip() else ""

        lines = wrap_text_lines(escaped_content, max_chars=12)
        if not lines:
            lines = [escaped_content]
        lines_html = "<br>".join(lines)

        daisy_svg = """
        <svg width="42" height="42" viewBox="0 0 50 50" class="mini-daisy">
          <g fill="#ffffff" stroke="#18181b" stroke-width="2.2">
            <circle cx="25" cy="11" r="7"/>
            <circle cx="25" cy="39" r="7"/>
            <circle cx="11" cy="25" r="7"/>
            <circle cx="39" cy="25" r="7"/>
            <circle cx="15" cy="15" r="7"/>
            <circle cx="35" cy="35" r="7"/>
            <circle cx="15" cy="35" r="7"/>
            <circle cx="35" cy="15" r="7"/>
          </g>
          <circle cx="25" cy="25" r="8.5" fill="#ffd700" stroke="#18181b" stroke-width="2.2"/>
        </svg>
        """

        daisies_html = ""
        if self.show_daisies:
            daisies_html = f"""
            <div class="daisy-cluster-tl">
              {daisy_svg}
              {daisy_svg}
              {daisy_svg}
            </div>
            <div class="daisy-cluster-br">
              {daisy_svg}
              {daisy_svg}
              {daisy_svg}
            </div>
            """

        sub_icon_svg = """
        <svg width="24" height="24" viewBox="0 0 50 50" style="vertical-align: middle; flex-shrink: 0;">
          <g fill="#ffffff" stroke="#18181b" stroke-width="2.5">
            <circle cx="25" cy="11" r="7"/>
            <circle cx="25" cy="39" r="7"/>
            <circle cx="11" cy="25" r="7"/>
            <circle cx="39" cy="25" r="7"/>
            <circle cx="15" cy="15" r="7"/>
            <circle cx="35" cy="35" r="7"/>
            <circle cx="15" cy="35" r="7"/>
            <circle cx="35" cy="15" r="7"/>
          </g>
          <circle cx="25" cy="25" r="8.5" fill="#ffd700" stroke="#18181b" stroke-width="2.5"/>
        </svg>
        """

        sub_html = ""
        if escaped_subcontent:
            sub_html = f"""
            <div class="daisy-sub-pill">
              {sub_icon_svg}
              <span class="daisy-sub-text">{escaped_subcontent}</span>
            </div>
            """

        custom_css = f"""
        .daisy-diary-wrap {{
          position: relative;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          max-width: 960px;
        }}
        .daisy-cluster-tl {{
          position: absolute;
          top: -18px;
          left: -14px;
          display: flex;
          gap: -8px;
          transform: rotate(-18deg);
          filter: drop-shadow(0 4px 8px rgba(0,0,0,0.3));
          z-index: 5;
        }}
        .daisy-cluster-br {{
          position: absolute;
          bottom: 2px;
          right: -14px;
          display: flex;
          gap: -8px;
          transform: rotate(22deg);
          filter: drop-shadow(0 4px 8px rgba(0,0,0,0.3));
          z-index: 5;
        }}
        .mini-daisy:nth-child(2) {{
          transform: scale(1.2) translateY(-6px);
        }}
        .mini-daisy:nth-child(3) {{
          transform: scale(0.9) translateY(4px);
        }}
        .daisy-text-block {{
          position: relative;
          display: inline-block;
          padding: 20px 36px;
        }}
        .daisy-title-text {{
          color: {self.text_color};
          font-size: {self.font_size_content}px;
          font-weight: 900;
          line-height: 1.25;
          letter-spacing: 2px;
          text-transform: uppercase;
          text-align: center;
          -webkit-text-stroke: 4px {self.stroke_color};
          text-shadow: 
            2px 2px 0 {self.honey_yellow},
            4px 4px 0 {self.honey_yellow},
            6px 6px 0 {self.honey_yellow},
            8px 8px 0 {self.honey_yellow},
            10px 10px 0 {self.stroke_color},
            11px 11px 0 {self.stroke_color};
          filter: 
            drop-shadow(0 0 0 14px #ffffff)
            drop-shadow(0 14px 30px rgba(0,0,0,0.55));
        }}

        /* Subcontent: Ribbon Sticker hoa cúc viền 3D mật ong */
        .daisy-sub-pill {{
          margin-top: 38px;
          background: #ffffff;
          border: 3px solid {self.stroke_color};
          color: #18181b;
          font-size: {self.font_size_subcontent}px;
          font-weight: 900;
          padding: 10px 36px;
          border-radius: 999px;
          box-shadow: 
            3px 3px 0 {self.honey_yellow},
            5px 5px 0 {self.stroke_color},
            0 10px 24px rgba(0,0,0,0.35);
          letter-spacing: 0.8px;
          display: inline-flex;
          align-items: center;
          gap: 12px;
          text-transform: uppercase;
          transform: rotate(0.8deg);
          max-width: 880px;
          line-height: 1.3;
          text-align: center;
        }}
        """

        body_content = f"""
        <div class="daisy-diary-wrap">
          <div class="daisy-text-block">
            {daisies_html}
            <div class="daisy-title-text">{lines_html}</div>
          </div>
          {sub_html}
        </div>
        """
        return self._get_base_html(body_content, custom_css, width, height)


@dataclass
class OceanChalkStickerStyle(BaseOverlayStyle):
    """
    Phong cách 4: Sticker Đại Dương & Trái Tim Phấn Trắng (Lấy cảm hứng từ mẫu 'You are VALID').
    Chữ bong bóng nảy nở màu trắng, viền xanh đại dương đậm, viền ngoài cùng sticker màu kem bơ,
    kèm tia nhấn chalk và hình vẽ trái tim phấn trắng nghệ thuật.
    """
    font_family: str = "'Comfortaa', 'Quicksand', cursive, sans-serif"
    text_color: str = "#ffffff"
    ocean_blue: str = "#247ba0"
    butter_cream: str = "#fff7d6"
    font_size_content: int = 56
    font_size_subcontent: int = 32
    show_accents: bool = True

    def apply_palette(self, palette: Union[str, ColorPalette, List[str], Tuple[str, ...]]) -> None:
        p = resolve_palette(palette)
        self.palette = p
        self.ocean_blue = p.c1
        self.butter_cream = p.c4 if not is_dark(p.c4) else p.c3

    def render_html(
        self,
        content: str,
        subcontent: Optional[str] = None,
        width: int = 1080,
        height: int = 1920
    ) -> str:
        escaped_content = html.escape(content.strip())
        escaped_subcontent = html.escape(subcontent.strip()) if subcontent and subcontent.strip() else ""

        lines = wrap_text_lines(escaped_content, max_chars=15)
        if not lines:
            lines = [escaped_content]

        line_h = 92
        start_y = 80
        total_h = len(lines) * line_h + 40

        svg_cream_border = ""
        svg_ocean_stroke = ""
        svg_white_fill = ""

        for idx, line in enumerate(lines):
            y = start_y + idx * line_h
            svg_cream_border += f'<text x="50%" y="{y}" text-anchor="middle" fill="none" stroke="{self.butter_cream}" stroke-width="44" stroke-linejoin="round" stroke-linecap="round">{line}</text>\n'
            svg_ocean_stroke += f'<text x="50%" y="{y}" text-anchor="middle" fill="none" stroke="{self.ocean_blue}" stroke-width="24" stroke-linejoin="round" stroke-linecap="round">{line}</text>\n'
            svg_white_fill += f'<text x="50%" y="{y}" text-anchor="middle" fill="{self.text_color}">{line}</text>\n'

        sub_html = ""
        if escaped_subcontent:
            sub_html = f"""
            <div class="ocean-sub-pill">
              <span class="ocean-chalk-icon">🤍</span>
              <span class="ocean-sub-text">{escaped_subcontent}</span>
              <span class="ocean-chalk-icon">🤍</span>
            </div>
            """

        accents_html = ""
        if self.show_accents:
            accents_html = """
            <!-- Tia phấn trắng góc trên trái -->
            <div class="ocean-chalk-rays">
              <span class="chalk-ray cr-1"></span>
              <span class="chalk-ray cr-2"></span>
              <span class="chalk-ray cr-3"></span>
            </div>
            <!-- Trái tim phấn trắng nghệ thuật góc phải -->
            <div class="ocean-chalk-heart">
              <svg width="68" height="64" viewBox="0 0 100 90" fill="none">
                <!-- Hiệu ứng nét phấn vẽ tay thô mộc -->
                <path d="M50 82 C50 82 12 55 12 28 C12 15 22 7 35 7 C43 7 48 11 50 16 C52 11 57 7 65 7 C78 7 88 15 88 28 C88 55 50 82 50 82 Z" 
                      fill="#ffffff" opacity="0.9" filter="url(#chalk-blur)"/>
                <path d="M50 78 C50 78 18 52 18 28 C18 17 26 11 36 11 C43 11 47 15 50 20 C53 15 57 11 64 11 C74 11 82 17 82 28 C82 52 50 78 50 78 Z" 
                      stroke="#ffffff" stroke-width="4" stroke-linecap="round" fill="none" opacity="0.95"/>
              </svg>
            </div>
            """

        custom_css = f"""
        .svg-defs {{
          position: absolute;
          width: 0;
          height: 0;
        }}
        .ocean-sticker-wrap {{
          position: relative;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          max-width: 980px;
        }}
        .ocean-svg-canvas {{
          overflow: visible;
          filter: drop-shadow(0 14px 30px rgba(0, 0, 0, 0.5));
        }}
        .ocean-chalk-rays {{
          position: absolute;
          top: -24px;
          left: 50px;
          display: flex;
          gap: 6px;
        }}
        .chalk-ray {{
          width: 5px;
          background: #ffffff;
          border-radius: 4px;
          filter: drop-shadow(0 2px 4px rgba(0,0,0,0.4));
        }}
        .cr-1 {{ height: 24px; transform: rotate(-30deg); margin-top: 8px; }}
        .cr-2 {{ height: 30px; transform: rotate(-8deg); }}
        .cr-3 {{ height: 24px; transform: rotate(18deg); margin-top: 8px; }}

        .ocean-chalk-heart {{
          position: absolute;
          bottom: 10px;
          right: 30px;
          transform: rotate(18deg);
          filter: drop-shadow(0 4px 10px rgba(0,0,0,0.3));
        }}

        /* Subcontent: Sticker viền kép Đại dương & Kem bơ hài hòa */
        .ocean-sub-pill {{
          margin-top: 22px;
          background: {self.butter_cream};
          border: 3.5px solid {self.ocean_blue};
          color: #124559;
          font-size: {self.font_size_subcontent}px;
          font-weight: 900;
          padding: 10px 36px;
          border-radius: 999px;
          box-shadow: 
            0 0 0 5px #ffffff,
            0 10px 26px rgba(0, 0, 0, 0.45);
          letter-spacing: 0.8px;
          display: inline-flex;
          align-items: center;
          gap: 10px;
          text-transform: uppercase;
          transform: rotate(-1deg);
          max-width: 880px;
          line-height: 1.3;
          text-align: center;
        }}
        .ocean-chalk-icon {{
          font-size: 22px;
          filter: drop-shadow(0 1px 3px rgba(0,0,0,0.25));
        }}
        """

        svg_defs = """
        <svg class="svg-defs">
          <defs>
            <filter id="chalk-blur">
              <feGaussianBlur stdDeviation="0.8" result="blur"/>
            </filter>
          </defs>
        </svg>
        """

        body_content = f"""
        {svg_defs}
        <div class="ocean-sticker-wrap">
          {accents_html}
          <svg class="ocean-svg-canvas" width="1000" height="{total_h}" viewBox="0 0 1000 {total_h}">
            <g font-family="{self.font_family}" font-weight="900" font-size="{self.font_size_content}" letter-spacing="1">
              {svg_cream_border}
              {svg_ocean_stroke}
              {svg_white_fill}
            </g>
          </svg>
          {sub_html}
        </div>
        """
        return self._get_base_html(body_content, custom_css, width, height)


@dataclass
class RetroGroovyOrangeStyle(BaseOverlayStyle):
    """
    Phong cách 5: Retro Groovy 70s (Lấy cảm hứng từ mẫu 'Title' cam 3D viền xanh teal cổ điển).
    Chữ bo tròn phúng phính màu cam bí ngô rực rỡ, viền đen espresso sắc nét,
    khối đùn 3D góc nghiêng màu xanh teal/peacock đậm chất pop art thập niên 70,
    kèm viền sticker bao bọc toàn bộ khối chữ.
    """
    font_family: str = "'Titan One', 'Shrikhand', 'Fredoka', cursive, sans-serif"
    orange_fill: str = "#ff7700"
    orange_highlight: str = "#ffb703"
    teal_extrusion: str = "#0d6e7a"
    dark_outline: str = "#18181b"
    font_size_content: int = 84
    font_size_subcontent: int = 34

    def apply_palette(self, palette: Union[str, ColorPalette, List[str], Tuple[str, ...]]) -> None:
        p = resolve_palette(palette)
        self.palette = p
        # Chọn màu sáng và rực rỡ nhất cho mặt chữ để đảm bảo luôn tương phản mạnh với dark_outline
        bright_candidates = [c for c in p.colors if not is_dark(c, threshold=0.35)]
        if bright_candidates:
            self.orange_fill = max(bright_candidates, key=get_vibrancy)
            remaining = [c for c in p.colors if c != self.orange_fill]
            self.orange_highlight = remaining[0] if remaining else p.c2
            self.teal_extrusion = remaining[1] if len(remaining) > 1 else p.c3
        else:
            self.orange_fill = to_candy_color(p.c1, target_l=0.72)
            self.orange_highlight = to_candy_color(p.c2, target_l=0.75)
            self.teal_extrusion = p.c3

    def render_html(
        self,
        content: str,
        subcontent: Optional[str] = None,
        width: int = 1080,
        height: int = 1920
    ) -> str:
        escaped_content = html.escape(content.strip())
        escaped_subcontent = html.escape(subcontent.strip()) if subcontent and subcontent.strip() else ""

        lines = wrap_text_lines(escaped_content, max_chars=12)
        if not lines:
            lines = [escaped_content]

        line_height = int(self.font_size_content * 1.25)
        total_h = line_height * len(lines) + 80
        start_y = int(total_h / 2 - (len(lines) - 1) * line_height / 2) + 6

        svg_3d_extrusion = ""
        svg_3d_choke = ""
        svg_black_outline = ""
        svg_orange_face = ""

        # Sinh các lớp SVG cho từng dòng:
        # Lớp 1: Khối đùn 3D Teal cổ điển góc 135 độ (dịch chéo xuống dưới-phải)
        for idx, line in enumerate(lines):
            curr_y = start_y + idx * line_height

            # Khối đùn 3D Teal góc nghiêng
            for step in range(3, 16, 2):
                dx = step
                dy = int(step * 1.1)
                svg_3d_extrusion += (
                    f'<text x="{500 + dx}" y="{curr_y + dy}" text-anchor="middle" dominant-baseline="middle" '
                    f'fill="{self.teal_extrusion}" stroke="{self.teal_extrusion}" stroke-width="8" '
                    f'stroke-linejoin="round" stroke-linecap="round">{line}</text>'
                )

            # Lớp viền đen chốt góc đáy của khối đùn
            dx_end = 16
            dy_end = int(16 * 1.1)
            svg_3d_choke += (
                f'<text x="{500 + dx_end}" y="{curr_y + dy_end}" text-anchor="middle" dominant-baseline="middle" '
                f'fill="{self.dark_outline}" stroke="{self.dark_outline}" stroke-width="12" '
                f'stroke-linejoin="round" stroke-linecap="round">{line}</text>'
            )

            # Lớp 2: Viền đen Espresso bao bọc ngay dưới mặt chữ
            svg_black_outline += (
                f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                f'fill="{self.dark_outline}" stroke="{self.dark_outline}" stroke-width="12" '
                f'stroke-linejoin="round" stroke-linecap="round">{line}</text>'
            )

            # Lớp 3: Mặt chữ Cam Bí Ngô Rực Rỡ nằm trên cùng (không bị viền ăn lấn)
            svg_orange_face += (
                f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                f'fill="{self.orange_fill}">{line}</text>'
            )

        sub_html = ""
        if escaped_subcontent:
            sub_lines = wrap_text_lines(escaped_subcontent, max_chars=22)
            if not sub_lines:
                sub_lines = [escaped_subcontent]

            sub_line_height = int(self.font_size_subcontent * 1.35)
            sub_total_h = sub_line_height * len(sub_lines) + 40
            sub_start_y = int(sub_total_h / 2 - (len(sub_lines) - 1) * sub_line_height / 2) + 4

            sub_3d_extrusion = ""
            sub_black_outline = ""
            sub_cream_fill = ""

            for idx, line in enumerate(sub_lines):
                curr_y = sub_start_y + idx * sub_line_height
                for step in range(2, 9, 2):
                    dx = step
                    dy = int(step * 1.1)
                    sub_3d_extrusion += (
                        f'<text x="{500 + dx}" y="{curr_y + dy}" text-anchor="middle" dominant-baseline="middle" '
                        f'fill="{self.teal_extrusion}" stroke="{self.teal_extrusion}" stroke-width="5" '
                        f'stroke-linejoin="round" stroke-linecap="round">{line}</text>'
                    )

                sub_black_outline += (
                    f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                    f'fill="{self.dark_outline}" stroke="{self.dark_outline}" stroke-width="7" '
                    f'stroke-linejoin="round" stroke-linecap="round">{line}</text>'
                )
                sub_cream_fill += (
                    f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                    f'fill="#fff3e0">{line}</text>'
                )

            sub_html = f"""
            <div class="retro-sub-wrap">
              <svg class="retro-sub-svg" width="1000" height="{sub_total_h}" viewBox="0 0 1000 {sub_total_h}">
                <g font-family="{self.font_family}" font-weight="900" font-size="{self.font_size_subcontent}" letter-spacing="2">
                  {sub_3d_extrusion}
                  {sub_black_outline}
                  {sub_cream_fill}
                </g>
              </svg>
            </div>
            """

        custom_css = f"""
        .retro-groovy-wrap {{
          position: relative;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          max-width: 1000px;
        }}
        .retro-svg-canvas {{
          overflow: visible;
          filter: drop-shadow(0 14px 28px rgba(0,0,0,0.38));
        }}
        .retro-sub-wrap {{
          margin-top: 20px;
          display: flex;
          justify-content: center;
          align-items: center;
          max-width: 1000px;
        }}
        .retro-sub-svg {{
          overflow: visible;
          filter: drop-shadow(0 8px 18px rgba(0,0,0,0.3));
        }}
        """

        body_content = f"""
        <div class="retro-groovy-wrap">
          <svg class="retro-svg-canvas" width="1000" height="{total_h}" viewBox="0 0 1000 {total_h}">
            <g font-family="{self.font_family}" font-weight="900" font-size="{self.font_size_content}" letter-spacing="2">
              {svg_3d_extrusion}
              {svg_3d_choke}
              {svg_black_outline}
              {svg_orange_face}
            </g>
          </svg>
          {sub_html}
        </div>
        """
        return self._get_base_html(body_content, custom_css, width, height)


@dataclass
class TropicalContourStyle(BaseOverlayStyle):
    """
    Phong cách 6: Tropical Multi-Contour Sticker (Lấy cảm hứng từ mẫu 'BRAZIL').
    Chữ màu xanh ngọc lục bảo rực rỡ, bao bọc bởi 3 tầng viền hào quang đồng tâm:
    Vàng chanh tươi -> Cam đào tươi ấm -> Hồng dưa hấu dịu dàng.
    """
    font_family: str = "'Montserrat', 'Rubik', 'Lilita One', sans-serif"
    green_color: str = "#009b48"
    yellow_contour: str = "#fed500"
    orange_contour: str = "#ff9f59"
    pink_contour: str = "#ff6b81"
    font_size_content: int = 84
    font_size_subcontent: int = 34

    def apply_palette(self, palette: Union[str, ColorPalette, List[str], Tuple[str, ...]]) -> None:
        p = resolve_palette(palette)
        self.palette = p
        self.green_color = to_candy_color(p.c1, target_l=0.55) if is_dark(p.c1, threshold=0.18) else p.c1
        self.yellow_contour = p.c2
        self.orange_contour = p.c3
        self.pink_contour = p.c4

    def render_html(
        self,
        content: str,
        subcontent: Optional[str] = None,
        width: int = 1080,
        height: int = 1920
    ) -> str:
        escaped_content = html.escape(content.strip())
        escaped_subcontent = html.escape(subcontent.strip()) if subcontent and subcontent.strip() else ""

        lines = wrap_text_lines(escaped_content, max_chars=14)
        if not lines:
            lines = [escaped_content]

        line_height = int(self.font_size_content * 1.32)
        total_h = line_height * len(lines) + 110
        start_y = int(total_h / 2 - (len(lines) - 1) * line_height / 2) + 14

        svg_pink_layer = ""
        svg_orange_layer = ""
        svg_yellow_layer = ""
        svg_green_fill = ""

        for idx, line in enumerate(lines):
            curr_y = start_y + idx * line_height
            svg_pink_layer += (
                f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                f'fill="{self.pink_contour}" stroke="{self.pink_contour}" stroke-width="56" '
                f'stroke-linejoin="round" stroke-linecap="round">{line}</text>'
            )
            svg_orange_layer += (
                f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                f'fill="{self.orange_contour}" stroke="{self.orange_contour}" stroke-width="38" '
                f'stroke-linejoin="round" stroke-linecap="round">{line}</text>'
            )
            svg_yellow_layer += (
                f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                f'fill="{self.yellow_contour}" stroke="{self.yellow_contour}" stroke-width="20" '
                f'stroke-linejoin="round" stroke-linecap="round">{line}</text>'
            )
            svg_green_fill += (
                f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                f'fill="{self.green_color}">{line}</text>'
            )

        sub_html = ""
        if escaped_subcontent:
            sub_lines = wrap_text_lines(escaped_subcontent, max_chars=22)
            if not sub_lines:
                sub_lines = [escaped_subcontent]

            sub_line_height = int(self.font_size_subcontent * 1.35)
            sub_total_h = sub_line_height * len(sub_lines) + 50
            sub_start_y = int(sub_total_h / 2 - (len(sub_lines) - 1) * sub_line_height / 2) + 4

            sub_pink_layer = ""
            sub_orange_layer = ""
            sub_yellow_layer = ""
            sub_green_fill = ""

            for idx, line in enumerate(sub_lines):
                curr_y = sub_start_y + idx * sub_line_height
                sub_pink_layer += (
                    f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                    f'fill="{self.pink_contour}" stroke="{self.pink_contour}" stroke-width="28" '
                    f'stroke-linejoin="round" stroke-linecap="round">{line}</text>'
                )
                sub_orange_layer += (
                    f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                    f'fill="{self.orange_contour}" stroke="{self.orange_contour}" stroke-width="18" '
                    f'stroke-linejoin="round" stroke-linecap="round">{line}</text>'
                )
                sub_yellow_layer += (
                    f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                    f'fill="{self.yellow_contour}" stroke="{self.yellow_contour}" stroke-width="10" '
                    f'stroke-linejoin="round" stroke-linecap="round">{line}</text>'
                )
                sub_green_fill += (
                    f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                    f'fill="{self.green_color}">{line}</text>'
                )

            sub_html = f"""
            <div class="tropical-sub-wrap">
              <svg class="tropical-sub-svg" width="1000" height="{sub_total_h}" viewBox="0 0 1000 {sub_total_h}">
                <g font-family="{self.font_family}" font-weight="900" font-size="{self.font_size_subcontent}" letter-spacing="1.5">
                  {sub_pink_layer}
                  {sub_orange_layer}
                  {sub_yellow_layer}
                  {sub_green_fill}
                </g>
              </svg>
            </div>
            """

        custom_css = f"""
        .tropical-contour-wrap {{
          position: relative;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          max-width: 1000px;
        }}
        .tropical-svg-canvas {{
          overflow: visible;
          filter: drop-shadow(0 14px 28px rgba(0,0,0,0.35));
        }}

        /* Subcontent: Thuần SVG multi-contour viền 3 lớp không có nền pill */
        .tropical-sub-wrap {{
          margin-top: 20px;
          display: flex;
          justify-content: center;
          align-items: center;
          max-width: 1000px;
        }}
        .tropical-sub-svg {{
          overflow: visible;
          filter: drop-shadow(0 10px 20px rgba(0,0,0,0.35));
        }}
        """

        body_content = f"""
        <div class="tropical-contour-wrap">
          <svg class="tropical-svg-canvas" width="1000" height="{total_h}" viewBox="0 0 1000 {total_h}">
            <g font-family="{self.font_family}" font-weight="900" font-size="{self.font_size_content}" letter-spacing="2">
              {svg_pink_layer}
              {svg_orange_layer}
              {svg_yellow_layer}
              {svg_green_fill}
            </g>
          </svg>
          {sub_html}
        </div>
        """
        return self._get_base_html(body_content, custom_css, width, height)


@dataclass
class GridNotebookDiaryStyle(BaseOverlayStyle):
    """
    Phong cách 7: Nhật Ký Vở Kẻ Ô Y2K (Lấy cảm hứng từ mẫu 'A DAY IN MY LIFE').
    Từng từ mang màu sắc pastel tươi tắn kẹo ngọt trên tấm sticker trang vở kẻ ô ly
    học sinh Y2K trong trẻo, thanh lịch và không bị rối mắt.
    """
    font_family: str = "'Fredoka', 'Quicksand', 'Nunito', sans-serif"
    font_size_content: int = 70
    font_size_subcontent: int = 30
    grid_spacing: int = 18
    word_palette: Optional[List[Tuple[str, str]]] = None

    def apply_palette(self, palette: Union[str, ColorPalette, List[str], Tuple[str, ...]]) -> None:
        p = resolve_palette(palette)
        self.palette = p
        pairs: List[Tuple[str, str]] = []
        for c in p.colors:
            actual_c = to_candy_color(c, target_l=0.60) if is_dark(c, threshold=0.35) else c
            shadow = "#18181b"
            pairs.append((actual_c, shadow))
        self.word_palette = pairs

    def render_html(
        self,
        content: str,
        subcontent: Optional[str] = None,
        width: int = 1080,
        height: int = 1920
    ) -> str:
        clean_content = content.strip()
        clean_subcontent = subcontent.strip() if subcontent and subcontent.strip() else ""

        # Bảng màu pastel Y2K theo TỪ (Word-by-word)
        default_palette = [
            ("#ff4d6d", "#a4161a"),
            ("#0096c7", "#023e8a"),
            ("#7209b7", "#3a0ca3"),
            ("#f77f00", "#9a031e"),
            ("#2a9d8f", "#1b4332"),
        ]
        palette = self.word_palette or default_palette

        lines = wrap_text_lines(clean_content, max_chars=12)
        if not lines:
            lines = [clean_content]

        formatted_lines: List[str] = []
        word_counter = 0

        for line in lines:
            words = line.split()
            line_parts: List[str] = []
            for w in words:
                color_fill, color_shadow = palette[word_counter % len(palette)]
                word_escaped = html.escape(w)
                line_parts.append(
                    f'<span class="grid-word" style="--word-fill: {color_fill}; --word-shadow: {color_shadow};">{word_escaped}</span>'
                )
                word_counter += 1
            formatted_lines.append(" ".join(line_parts))

        lines_html = "<br>".join(formatted_lines)

        sub_html = ""
        if clean_subcontent:
            escaped_sub = html.escape(clean_subcontent)
            sub_html = f"""
            <div class="grid-sub-wrap">
              <div class="grid-sub-tape">
                <span class="grid-sub-icon">📖</span>
                <span class="grid-sub-text">{escaped_sub}</span>
                <span class="grid-sub-icon">✨</span>
              </div>
            </div>
            """

        custom_css = f"""
        .grid-diary-wrap {{
          position: relative;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          max-width: 960px;
        }}
        .grid-notebook-card {{
          position: relative;
          background-color: #ffffff;
          background-image: 
            linear-gradient(rgba(170, 195, 225, 0.35) 1px, transparent 1px),
            linear-gradient(90deg, rgba(170, 195, 225, 0.35) 1px, transparent 1px);
          background-size: {self.grid_spacing}px {self.grid_spacing}px;
          border-radius: 32px;
          padding: 34px 56px;
          border: 4px solid #18181b;
          box-shadow: 
            6px 6px 0 #18181b,
            0 16px 36px rgba(0,0,0,0.25);
          text-align: center;
        }}
        .washi-tape {{
          position: absolute;
          width: 70px;
          height: 22px;
          background: rgba(255, 200, 221, 0.85);
          border: 1.5px dashed rgba(216, 70, 110, 0.5);
          border-radius: 4px;
        }}
        .washi-left {{
          top: -11px;
          left: 36px;
          transform: rotate(-10deg);
        }}
        .washi-right {{
          top: -11px;
          right: 36px;
          transform: rotate(12deg);
          background: rgba(200, 230, 255, 0.85);
          border-color: rgba(70, 130, 200, 0.5);
        }}
        .grid-word {{
          display: inline-block;
          color: var(--word-fill);
          font-family: {self.font_family};
          font-size: {self.font_size_content}px;
          font-weight: 900;
          line-height: 1.25;
          letter-spacing: 2px;
          margin: 0 8px;
          -webkit-text-stroke: 1.5px #18181b;
          text-shadow:
            3px 3px 0 var(--word-shadow),
            4.5px 4.5px 0 #18181b;
        }}
        .grid-sub-wrap {{
          margin-top: 22px;
          display: flex;
          justify-content: center;
          align-items: center;
        }}
        .grid-sub-tape {{
          background: #ffea79;
          color: #18181b;
          font-family: {self.font_family};
          font-size: {self.font_size_subcontent}px;
          font-weight: 800;
          padding: 8px 24px;
          border-radius: 12px;
          border: 2.5px solid #18181b;
          box-shadow: 3.5px 3.5px 0 #18181b;
          letter-spacing: 1.5px;
          display: inline-flex;
          align-items: center;
          gap: 10px;
          text-transform: uppercase;
        }}
        .grid-sub-icon {{
          font-size: 20px;
        }}
        """

        body_content = f"""
        <div class="grid-diary-wrap">
          <div class="grid-notebook-card">
            <div class="washi-tape washi-left"></div>
            <div class="washi-tape washi-right"></div>
            <div class="grid-content-box">{lines_html}</div>
          </div>
          {sub_html}
        </div>
        """
        return self._get_base_html(body_content, custom_css, width, height)


@dataclass
class BabyBluePuffyStyle(BaseOverlayStyle):
    """
    Phong cách 8: Mây Xanh Bồng Bềnh 3D (Lấy cảm hứng từ mẫu 'Hello!').
    Chữ bong bóng phồng căng tròn màu trắng tuyết tinh khôi, viền xanh da trời nhẹ nhàng,
    đổ bóng 3D dày màu xanh lam đậm và bao bọc bởi lớp viền sticker đám mây dịu êm.
    """
    font_family: str = "'Titan One', 'Fredoka', cursive, sans-serif"
    cloud_outer: str = "#a9d6ff"
    blue_stroke: str = "#5ea5ec"
    blue_shadow: str = "#2563eb"
    text_color: str = "#ffffff"
    font_size_content: int = 84
    font_size_subcontent: int = 34

    def apply_palette(self, palette: Union[str, ColorPalette, List[str], Tuple[str, ...]]) -> None:
        p = resolve_palette(palette)
        self.palette = p
        self.blue_shadow = p.c1
        self.blue_stroke = p.c2
        self.cloud_outer = p.c3
        self.text_color = "#ffffff"

    def render_html(
        self,
        content: str,
        subcontent: Optional[str] = None,
        width: int = 1080,
        height: int = 1920
    ) -> str:
        escaped_content = html.escape(content.strip())
        escaped_subcontent = html.escape(subcontent.strip()) if subcontent and subcontent.strip() else ""

        lines = wrap_text_lines(escaped_content, max_chars=12)
        if not lines:
            lines = [escaped_content]

        line_height = int(self.font_size_content * 1.3)
        total_h = line_height * len(lines) + 100
        start_y = int(total_h / 2 - (len(lines) - 1) * line_height / 2) + 12

        svg_cloud_border = ""
        svg_3d_shadow = ""
        svg_blue_stroke = ""
        svg_white_fill = ""

        for idx, line in enumerate(lines):
            curr_y = start_y + idx * line_height
            # Lớp 1: Viền sticker mây bao ngoài cùng
            svg_cloud_border += (
                f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                f'fill="{self.cloud_outer}" stroke="{self.cloud_outer}" stroke-width="44" '
                f'stroke-linejoin="round" stroke-linecap="round">{line}</text>'
            )
            # Lớp 2: Khối đùn 3D xanh lam đổ lệch xuống dưới bên phải
            svg_3d_shadow += (
                f'<text x="506" y="{curr_y + 10}" text-anchor="middle" dominant-baseline="middle" '
                f'fill="{self.blue_shadow}" stroke="{self.blue_shadow}" stroke-width="16" '
                f'stroke-linejoin="round" stroke-linecap="round">{line}</text>'
            )
            # Lớp 3: Viền nét xanh thiên thanh bao quanh chữ trắng
            svg_blue_stroke += (
                f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                f'fill="{self.blue_stroke}" stroke="{self.blue_stroke}" stroke-width="12" '
                f'stroke-linejoin="round" stroke-linecap="round">{line}</text>'
            )
            # Lớp 4: Lòng chữ màu trắng muốt tinh khiết
            svg_white_fill += (
                f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                f'fill="{self.text_color}">{line}</text>'
            )

        sub_html = ""
        if escaped_subcontent:
            sub_lines = wrap_text_lines(escaped_subcontent, max_chars=22)
            if not sub_lines:
                sub_lines = [escaped_subcontent]

            sub_line_height = int(self.font_size_subcontent * 1.35)
            sub_total_h = sub_line_height * len(sub_lines) + 50
            sub_start_y = int(sub_total_h / 2 - (len(sub_lines) - 1) * sub_line_height / 2) + 4

            sub_cloud_border = ""
            sub_3d_shadow = ""
            sub_blue_stroke = ""
            sub_white_fill = ""

            for idx, line in enumerate(sub_lines):
                curr_y = sub_start_y + idx * sub_line_height
                sub_cloud_border += (
                    f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                    f'fill="{self.cloud_outer}" stroke="{self.cloud_outer}" stroke-width="26" '
                    f'stroke-linejoin="round" stroke-linecap="round">{line}</text>'
                )
                sub_3d_shadow += (
                    f'<text x="504" y="{curr_y + 6}" text-anchor="middle" dominant-baseline="middle" '
                    f'fill="{self.blue_shadow}" stroke="{self.blue_shadow}" stroke-width="10" '
                    f'stroke-linejoin="round" stroke-linecap="round">{line}</text>'
                )
                sub_blue_stroke += (
                    f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                    f'fill="{self.blue_stroke}" stroke="{self.blue_stroke}" stroke-width="7" '
                    f'stroke-linejoin="round" stroke-linecap="round">{line}</text>'
                )
                sub_white_fill += (
                    f'<text x="500" y="{curr_y}" text-anchor="middle" dominant-baseline="middle" '
                    f'fill="{self.text_color}">{line}</text>'
                )

            sub_html = f"""
            <div class="puffy-sub-wrap">
              <svg class="puffy-sub-svg" width="1000" height="{sub_total_h}" viewBox="0 0 1000 {sub_total_h}">
                <g font-family="{self.font_family}" font-weight="900" font-size="{self.font_size_subcontent}" letter-spacing="1.5">
                  {sub_cloud_border}
                  {sub_3d_shadow}
                  {sub_blue_stroke}
                  {sub_white_fill}
                </g>
              </svg>
            </div>
            """

        custom_css = f"""
        .baby-blue-puffy-wrap {{
          position: relative;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          max-width: 1000px;
        }}
        .puffy-svg-canvas {{
          overflow: visible;
          filter: drop-shadow(0 14px 28px rgba(37, 99, 235, 0.35));
        }}

        /* Subcontent: Thuần SVG Puffy 3D đám mây không có nền pill */
        .puffy-sub-wrap {{
          margin-top: 22px;
          display: flex;
          justify-content: center;
          align-items: center;
          max-width: 1000px;
        }}
        .puffy-sub-svg {{
          overflow: visible;
          filter: drop-shadow(0 10px 20px rgba(37, 99, 235, 0.35));
        }}
        """

        body_content = f"""
        <div class="baby-blue-puffy-wrap">
          <svg class="puffy-svg-canvas" width="1000" height="{total_h}" viewBox="0 0 1000 {total_h}">
            <g font-family="{self.font_family}" font-weight="900" font-size="{self.font_size_content}" letter-spacing="2">
              {svg_cloud_border}
              {svg_3d_shadow}
              {svg_blue_stroke}
              {svg_white_fill}
            </g>
          </svg>
          {sub_html}
        </div>
        """
        return self._get_base_html(body_content, custom_css, width, height)


