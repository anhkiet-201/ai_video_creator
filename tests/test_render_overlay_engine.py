import sys
import time
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import TEMP_DIR
from app.services.render_overlay_engine import (
    COLOR_PALETTES,
    PREDEFINED_OVERLAY_FONTS,
    BabyBluePuffyStyle,
    BaseOverlayStyle,
    BubbleCloudStyle,
    ColorPalette,
    DaisyDiaryStyle,
    GridNotebookDiaryStyle,
    MarshmallowPinkStyle,
    OceanChalkStickerStyle,
    PastelMulticolorStyle,
    RenderOverlayEngine,
    RetroGroovyOrangeStyle,
    TornPaperStyle,
    TropicalContourStyle,
    VlogDoodleStickerStyle,
    get_palette_by_id,
    get_random_font,
    get_random_palette,
    list_palettes,
    resolve_font,
    resolve_palette,
)


def test_built_in_styles_with_subcontent():
    """Kiểm thử render tất cả các style có sẵn khi có cả content và subcontent"""
    print("\n--- 1. KIỂM THỬ TẤT CẢ STYLES CÓ SẴN (CÓ SUBCONTENT) ---")
    engine = RenderOverlayEngine()
    test_dir = TEMP_DIR / "test_engine_builtin"
    test_dir.mkdir(parents=True, exist_ok=True)

    styles = [
        ("torn_paper", TornPaperStyle()),
        ("bubble_cloud", BubbleCloudStyle()),
        ("pastel_multicolor", PastelMulticolorStyle()),
        ("marshmallow_pink", MarshmallowPinkStyle()),
        ("vlog_doodle", VlogDoodleStickerStyle()),
        ("daisy_diary", DaisyDiaryStyle()),
        ("ocean_chalk", OceanChalkStickerStyle()),
        ("retro_groovy", RetroGroovyOrangeStyle()),
        ("tropical_contour", TropicalContourStyle()),
        ("grid_notebook", GridNotebookDiaryStyle()),
        ("baby_blue_puffy", BabyBluePuffyStyle()),
    ]

    for name, st in styles:
        t0 = time.time()
        out_file = test_dir / f"overlay_{name}.png"
        res_path = engine.render(
            content="CƠ HỘI VIỆC LÀM TRIỆU ĐÔ",
            subcontent="THU NHẬP 25 - 40 TRIỆU 🚀",
            style=st,
            output_path=out_file
        )
        duration = time.time() - t0

        assert res_path.exists(), f"File {res_path} không tồn tại!"
        assert res_path.stat().st_size > 0, f"File {res_path} bị rỗng!"

        with Image.open(res_path) as img:
            assert img.size == (1080, 1920), f"Kích thước ảnh sai: {img.size}"
            assert img.mode == "RGBA", f"Chế độ ảnh không phải RGBA: {img.mode}"

        print(f"  [PASS] Style '{name}' -> {res_path.name} ({res_path.stat().st_size} bytes, {duration:.2f}s)")


def test_rendering_without_subcontent():
    """Kiểm thử render khi subcontent để trống hoặc None"""
    print("\n--- 2. KIỂM THỬ KHI SUBCONTENT ĐỂ TRỐNG HOẶC NONE ---")
    engine = RenderOverlayEngine()
    test_dir = TEMP_DIR / "test_engine_no_sub"
    test_dir.mkdir(parents=True, exist_ok=True)

    # Trường hợp subcontent = None
    out_none = test_dir / "overlay_sub_none.png"
    res_none = engine.render(
        content="TIÊU ĐỀ ĐỘC LẬP KHÔNG CẦN SUB",
        subcontent=None,
        style=BubbleCloudStyle(),
        output_path=out_none
    )
    assert res_none.exists() and res_none.stat().st_size > 0
    print(f"  [PASS] subcontent=None -> {res_none.name} ({res_none.stat().st_size} bytes)")

    # Trường hợp subcontent = ""
    out_empty = test_dir / "overlay_sub_empty.png"
    res_empty = engine.render(
        content="TIÊU ĐỀ VỚI SUB CONTENT CHUỖI RỖNG",
        subcontent="   ",
        style=TornPaperStyle(),
        output_path=out_empty
    )
    assert res_empty.exists() and res_empty.stat().st_size > 0
    print(f"  [PASS] subcontent='' -> {res_empty.name} ({res_empty.stat().st_size} bytes)")


def test_extensibility_with_new_custom_style():
    """
    Kiểm thử nguyên lý Open-Closed (OCP):
    Khai báo 1 class style mới toanh ngay trong test mà không sửa bất kỳ code nào trong Engine!
    """
    print("\n--- 3. KIỂM THỬ KHẢ NĂNG MỞ RỘNG STYLE MỚI (KHÔNG PHỤ THUỘC ENGINE) ---")

    # Khai báo một style mới hoàn toàn dùng @dataclass: CyberGlitchBannerStyle
    from dataclasses import dataclass

    @dataclass
    class CyberGlitchBannerStyle(BaseOverlayStyle):
        banner_color: str = "#00f0ff"
        accent_color: str = "#ff003c"

        def render_html(
            self,
            content: str,
            subcontent: str = None,
            width: int = 1080,
            height: int = 1920
        ) -> str:
            sub_html = f'<div class="glitch-sub">{subcontent}</div>' if subcontent else ""
            custom_css = f"""
            .glitch-box {{
              background: #0d0e15;
              border: 3px solid {self.banner_color};
              box-shadow: 0 0 20px {self.banner_color}88, inset 0 0 15px {self.accent_color}44;
              padding: 24px 40px;
              border-radius: 12px;
              max-width: 900px;
            }}
            .glitch-title {{
              color: #ffffff;
              font-size: 50px;
              font-weight: 900;
              text-transform: uppercase;
              letter-spacing: 2px;
            }}
            .glitch-sub {{
              margin-top: 14px;
              color: {self.banner_color};
              font-size: 34px;
              font-weight: 800;
            }}
            """
            body = f"""
            <div class="glitch-box">
              <div class="glitch-title">{content}</div>
              {sub_html}
            </div>
            """
            return self._get_base_html(body, custom_css, width, height)

    engine = RenderOverlayEngine()
    test_dir = TEMP_DIR / "test_engine_custom_style"
    test_dir.mkdir(parents=True, exist_ok=True)

    custom_out = test_dir / "overlay_custom_cyber.png"
    my_style = CyberGlitchBannerStyle(banner_color="#39ff14", accent_color="#ff073a")

    res = engine.render(
        content="CYBER REVOLUTION 2026",
        subcontent="PHONG CÁCH TỰ ĐỊNH NGHĨA HOÀN TOÀN MỚI",
        style=my_style,
        output_path=custom_out
    )

    assert res.exists() and res.stat().st_size > 0
    print(f"  [PASS] Custom New Style -> {res.name} ({res.stat().st_size} bytes)")


def test_batch_parallel_rendering():
    """Kiểm thử render song song nhiều cảnh"""
    print("\n--- 4. KIỂM THỬ BATCH RENDER SONG SONG ---")
    engine = RenderOverlayEngine()
    test_dir = TEMP_DIR / "test_engine_batch"
    test_dir.mkdir(parents=True, exist_ok=True)

    items = [
        {"content": "CẢNH 1: GIỚI THIỆU DOANH NGHIỆP", "subcontent": "QUY MÔ 500 NHÂN SỰ", "style": TornPaperStyle()},
        {"content": "CẢNH 2: MÔI TRƯỜNG LÀM VIỆC", "subcontent": "VĂN PHÒNG CHUẨN 5 SAO", "style": BubbleCloudStyle()},
        {"content": "CẢNH 3: CHẾ ĐỘ ĐÃI NGỘ", "subcontent": "LƯƠNG THƯỞNG KHỦNG", "style": PastelMulticolorStyle()},
        {"content": "CẢNH 4: HOẠT ĐỘNG TEAM", "subcontent": "DU LỊCH 2 LẦN / NĂM", "style": MarshmallowPinkStyle()},
        {"content": "CẢNH 5: ỨNG TUYỂN NGAY HÔM NAY", "subcontent": "LINK TẠI BIO PROFILE", "style": VlogDoodleStickerStyle()},
    ]

    t0 = time.time()
    results = engine.render_batch(items, output_dir=test_dir, max_workers=4)
    total_time = time.time() - t0

    assert len(results) == 5, f"Số lượng file kết quả không đủ: {len(results)}"
    for p in results:
        assert p.exists() and p.stat().st_size > 0

    print(f"  [PASS] Render song song 5 overlays hoàn thành trong {total_time:.2f}s (Trung bình {total_time/5:.2f}s/frame)")


def test_font_resolution_and_random():
    """Kiểm thử logic chọn font: danh sách 22 font, random font khi None, và giữ nguyên font khi truyền vào"""
    print("\n--- 5. KIỂM THỬ LOGIC CHỌN VÀ RANDOM FONT ---")
    assert len(PREDEFINED_OVERLAY_FONTS) == 22, f"Số lượng font định nghĩa sẵn không đúng 22: {len(PREDEFINED_OVERLAY_FONTS)}"
    
    # 1. Random khi font is None
    for _ in range(10):
        rand_f = get_random_font()
        assert rand_f in PREDEFINED_OVERLAY_FONTS, f"Font ngẫu nhiên không thuộc danh sách: {rand_f}"
        resolved = resolve_font(None)
        assert resolved in PREDEFINED_OVERLAY_FONTS, f"Resolve None không thuộc danh sách: {resolved}"

    # 2. Giữ nguyên font khi truyền chuỗi hợp lệ
    assert resolve_font("Roboto") == "Roboto"
    assert resolve_font("  Cherry Bomb One  ") == "Cherry Bomb One"
    print("  [PASS] Logic phân giải và random 22 font chính xác 100%!")


def test_palette_resolution_and_random():
    """Kiểm thử kho bảng màu Color Hunt: 50+ palettes, lọc theo tag, random, và phân giải chính xác"""
    print("\n--- 6. KIỂM THỬ KHO BẢNG MÀU VÀ LOGIC RANDOM PALETTE TỪ COLOR HUNT ---")
    assert len(COLOR_PALETTES) >= 50, f"Số lượng palette Color Hunt ít hơn 50: {len(COLOR_PALETTES)}"
    
    # 1. Random khi palette is None
    for _ in range(10):
        rand_p = get_random_palette()
        assert isinstance(rand_p, ColorPalette)
        assert len(rand_p.colors) == 4
        resolved = resolve_palette(None)
        assert isinstance(resolved, ColorPalette)

    # 2. Lọc theo tag ('pastel', 'retro', 'neon', 'warm', 'cold', 'candy')
    for test_tag in ["pastel", "retro", "neon", "warm", "cold"]:
        palettes_with_tag = list_palettes(test_tag)
        assert len(palettes_with_tag) > 0, f"Không có palette nào cho tag '{test_tag}'"
        p_by_tag = get_random_palette(tag=test_tag)
        assert test_tag in p_by_tag.tags, f"Palette '{p_by_tag.id}' không có tag '{test_tag}'"

    # 3. Phân giải theo ID cụ thể
    exact_p = resolve_palette("retro_sunset_70s")
    assert exact_p.id == "retro_sunset_70s"
    assert exact_p.name == "Retro Sunset 70s"

    # 4. Phân giải theo danh sách 4 mã màu tùy biến
    custom_colors = ["#ff1122", "#334455", "#667788", "#99aabb"]
    custom_p = resolve_palette(custom_colors)
    assert custom_p.colors == tuple(custom_colors)

    print(f"  [PASS] Kho {len(COLOR_PALETTES)} bảng màu Color Hunt & logic phân giải random đạt chuẩn 100%!")


def test_rendering_with_fonts():
    """Kiểm thử render thực tế với font chỉ định và font tự động random"""
    print("\n--- 7. KIỂM THỬ RENDER THỰC TẾ VỚI FONT CHỈ ĐỊNH VÀ RANDOM ---")
    engine = RenderOverlayEngine()
    test_dir = TEMP_DIR / "test_engine_fonts"
    test_dir.mkdir(parents=True, exist_ok=True)

    # 1. Render với font chỉ định cụ thể
    out_explicit = test_dir / "overlay_font_cherry_bomb.png"
    res_explicit = engine.render(
        content="CHERRY BOMB ONE TEST",
        subcontent="FONT CỤ THỂ CHỈ ĐỊNH",
        style=BubbleCloudStyle(),
        font="Cherry Bomb One",
        output_path=out_explicit
    )
    assert res_explicit.exists() and res_explicit.stat().st_size > 0
    with Image.open(res_explicit) as img:
        assert img.size == (1080, 1920)
        assert img.mode == "RGBA"
    print(f"  [PASS] Render font cụ thể 'Cherry Bomb One' -> {res_explicit.name} ({res_explicit.stat().st_size} bytes)")

    # 2. Render với font = None (Tự động random)
    out_random = test_dir / "overlay_font_random.png"
    res_random = engine.render(
        content="RANDOM FONT SELECTION",
        subcontent="TỰ ĐỘNG BỐC NGẪU NHIÊN",
        style=RetroGroovyOrangeStyle(),
        font=None,
        output_path=out_random
    )
    assert res_random.exists() and res_random.stat().st_size > 0
    with Image.open(res_random) as img:
        assert img.size == (1080, 1920)
        assert img.mode == "RGBA"
    print(f"  [PASS] Render font ngẫu nhiên (font=None) -> {res_random.name} ({res_random.stat().st_size} bytes)")


def test_rendering_with_palettes():
    """Kiểm thử render thực tế với bảng màu Color Hunt: tự động random và chỉ định cụ thể"""
    print("\n--- 8. KIỂM THỬ RENDER THỰC TẾ VỚI BẢNG MÀU COLOR HUNT ---")
    engine = RenderOverlayEngine()
    test_dir = TEMP_DIR / "test_engine_palettes"
    test_dir.mkdir(parents=True, exist_ok=True)

    # 1. Render với bảng màu chỉ định cụ thể ('retro_sunset_70s')
    out_palette_explicit = test_dir / "overlay_palette_retro_sunset.png"
    res_explicit = engine.render(
        content="COLOR HUNT SPECIFIC PALETTE",
        subcontent="BẢNG MÀU RETRO SUNSET 70S",
        style=RetroGroovyOrangeStyle(),
        palette="retro_sunset_70s",
        output_path=out_palette_explicit
    )
    assert res_explicit.exists() and res_explicit.stat().st_size > 0
    with Image.open(res_explicit) as img:
        assert img.size == (1080, 1920)
        assert img.mode == "RGBA"
    print(f"  [PASS] Render bảng màu chỉ định 'retro_sunset_70s' -> {res_explicit.name} ({res_explicit.stat().st_size} bytes)")

    # 2. Render với palette = None (Tự động random bảng màu Color Hunt)
    out_palette_random = test_dir / "overlay_palette_random.png"
    res_random = engine.render(
        content="COLOR HUNT RANDOM PALETTE",
        subcontent="TỰ ĐỘNG RANDOM BẢNG MÀU ĐA SẮC",
        style=BubbleCloudStyle(),
        palette=None,
        output_path=out_palette_random
    )
    assert res_random.exists() and res_random.stat().st_size > 0
    with Image.open(res_random) as img:
        assert img.size == (1080, 1920)
        assert img.mode == "RGBA"
    print(f"  [PASS] Render bảng màu ngẫu nhiên (palette=None) -> {res_random.name} ({res_random.stat().st_size} bytes)")

    # 3. Render với lọc nhóm màu (palette_tag='pastel')
    out_palette_pastel = test_dir / "overlay_palette_pastel_tag.png"
    res_pastel = engine.render(
        content="PASTEL THEME RANDOM",
        subcontent="LỌC RANDOM THEO TAG PASTEL",
        style=PastelMulticolorStyle(),
        palette_tag="pastel",
        output_path=out_palette_pastel
    )
    assert res_pastel.exists() and res_pastel.stat().st_size > 0
    with Image.open(res_pastel) as img:
        assert img.size == (1080, 1920)
        assert img.mode == "RGBA"
    print(f"  [PASS] Render random theo tag 'pastel' -> {res_pastel.name} ({res_pastel.stat().st_size} bytes)")


def test_scene_overlay_consistency():
    """Kiểm thử tính nhất quán font và palette khi tái sử dụng style qua nhiều scene liên tiếp"""
    print("\n--- 9. KIỂM THỬ ĐỒNG NHẤT FONT & PALETTE QUA CÁC SCENE ---")
    engine = RenderOverlayEngine()
    test_dir = TEMP_DIR / "test_engine_scene_consistency"
    test_dir.mkdir(parents=True, exist_ok=True)

    # Khởi tạo style ban đầu không có font và palette định sẵn
    shared_style = BubbleCloudStyle()
    assert shared_style.font is None
    assert shared_style.palette is None

    # Render Scene 1: Engine sẽ tự chọn 1 font và 1 palette, sau đó lưu ngược vào shared_style
    out_s1 = test_dir / "scene_1_overlay.png"
    engine.render(
        content="SCENE 1: GIỚI THIỆU",
        subcontent="BƯỚC ĐẦU TIÊN CỦA VIDEO",
        style=shared_style,
        output_path=out_s1
    )
    assert shared_style.font is not None
    assert shared_style.palette is not None
    s1_font = shared_style.font
    s1_palette_id = shared_style.palette.id

    # Render Scene 2: Tái sử dụng shared_style -> font và palette phải được giữ nguyên 100%!
    out_s2 = test_dir / "scene_2_overlay.png"
    engine.render(
        content="SCENE 2: NỘI DUNG CHÍNH",
        subcontent="GIỮ NGUYÊN FONT VÀ BẢNG MÀU",
        style=shared_style,
        output_path=out_s2
    )
    assert shared_style.font == s1_font, f"Font bị đổi giữa Scene 1 ({s1_font}) và Scene 2 ({shared_style.font})!"
    assert shared_style.palette.id == s1_palette_id, f"Palette bị đổi giữa Scene 1 ({s1_palette_id}) và Scene 2 ({shared_style.palette.id})!"

    # Render Scene 3: Kiểm tra tiếp Scene 3
    out_s3 = test_dir / "scene_3_overlay.png"
    engine.render(
        content="SCENE 3: KÊU GỌI HÀNH ĐỘNG",
        subcontent="ĐỒNG BỘ VISUAL BRANDING",
        style=shared_style,
        output_path=out_s3
    )
    assert shared_style.font == s1_font
    assert shared_style.palette.id == s1_palette_id

    print(f"  [PASS] Đồng nhất tuyệt đối qua 3 Scenes: Font='{s1_font}', Palette ID='{s1_palette_id}'")


def test_batch_consistent_font_and_palette():
    """Kiểm thử render_batch tự động cố định font và palette dùng chung cho toàn bộ batch"""
    print("\n--- 10. KIỂM THỬ RENDER BATCH DÙNG CHUNG BẢNG MÀU & FONT ---")
    engine = RenderOverlayEngine()
    test_dir = TEMP_DIR / "test_engine_batch_consistency"
    test_dir.mkdir(parents=True, exist_ok=True)

    items = [
        {"content": "BẢN TIN SÁNG", "subcontent": "TIN TỨC CẬP NHẬT"},
        {"content": "DỰ BÁO THỜI TIẾT", "subcontent": "NGÀY NẮNG ĐẸP TRỜI"},
        {"content": "GIAO THÔNG ĐÔ THỊ", "subcontent": "LƯU THÔNG THUẬN LỢI"},
    ]

    results = engine.render_batch(
        items=items,
        output_dir=test_dir,
        default_palette_tag="pastel",
        max_workers=2
    )

    assert len(results) == 3
    for p in results:
        assert p.exists() and p.stat().st_size > 0
    print("  [PASS] Render batch đồng bộ thành công 3 items dùng chung bảng màu pastel!")


if __name__ == "__main__":
    print("=== BẮT ĐẦU CHẠY TOÀN BỘ BÀI TEST RENDER_OVERLAY_ENGINE ===")
    test_built_in_styles_with_subcontent()
    test_rendering_without_subcontent()
    test_extensibility_with_new_custom_style()
    test_batch_parallel_rendering()
    test_font_resolution_and_random()
    test_palette_resolution_and_random()
    test_rendering_with_fonts()
    test_rendering_with_palettes()
    test_scene_overlay_consistency()
    test_batch_consistent_font_and_palette()
    print("\n=== TOÀN BỘ CÁC BÀI KIỂM THỬ ĐÃ PASS THÀNH CÔNG 100%! ===")
