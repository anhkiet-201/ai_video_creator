import sys
import time
from pathlib import Path

# Đảm bảo đường dẫn root của dự án nằm trong sys.path khi chạy trực tiếp file main.py
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import OUTPUTS_DIR
from app.services.render_overlay_engine import (
    BabyBluePuffyStyle,
    BubbleCloudStyle,
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
)


def main():
    print("==================================================================")
    print("      DEMO RENDER CÁC STYLES - RENDER OVERLAY ENGINE              ")
    print("==================================================================")

    engine = RenderOverlayEngine()
    output_dir = OUTPUTS_DIR / "demo_overlays"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[+] Thư mục xuất ảnh: {output_dir.resolve()}\n")

    # Danh sách các style thử nghiệm (Bao gồm 4 mẫu mới nhất chuẩn theo ảnh mẫu)
    demos = [
        # --- 4 MẪU MỚI NHẤT THEO ẢNH MẪU ---
        {
            "name": "new_5_retro_groovy",
            "title": "Mẫu 5: Retro Groovy 70s (Title - Cam bí ngô 3D teal)",
            "style": RetroGroovyOrangeStyle(),
            "content": "Title",
            "subcontent": "RETRO VINTAGE VIBES ✌️",
        },
        {
            "name": "new_6_tropical_contour",
            "title": "Mẫu 6: Tropical Contour (BRAZIL - Viền 3 tầng Vàng/Cam/Hồng)",
            "style": TropicalContourStyle(),
            "content": "BRAZIL",
            "subcontent": "CARNIVAL SUMMER 🌴",
        },
        {
            "name": "new_7_grid_notebook",
            "title": "Mẫu 7: Grid Notebook Diary (A DAY IN MY LIFE - Vở kẻ ô Y2K)",
            "style": GridNotebookDiaryStyle(),
            "content": "A DAY IN MY LIFE",
            "subcontent": "DAILY ROUTINE & STUDY 📖",
        },
        {
            "name": "new_8_baby_blue_puffy",
            "title": "Mẫu 8: Baby Blue Puffy (Hello! - Mây xanh bồng bềnh 3D)",
            "style": BabyBluePuffyStyle(),
            "content": "Hello!",
            "subcontent": "HAVE A WONDERFUL DAY ✨",
        },
        # --- 4 MẪU ĐỢT TRƯỚC ---
        {
            "name": "new_1_marshmallow_pink",
            "title": "Mẫu 1: Marshmallow Pink (TODAY STORY - Kẹo dẻo mây hồng)",
            "style": MarshmallowPinkStyle(),
            "content": "TODAY STORY",
            "subcontent": "KHOẢNH KHẮC NGỌT NGÀO 🌸",
        },
        {
            "name": "new_2_vlog_doodle",
            "title": "Mẫu 2: Vlog Doodle Sticker (Mini Vlog - 3D vàng & icon phấn)",
            "style": VlogDoodleStickerStyle(),
            "content": "Mini Vlog",
            "subcontent": "MỘT NGÀY TẠI VĂN PHÒNG ✨",
        },
        {
            "name": "new_3_daisy_diary",
            "title": "Mẫu 3: Daisy Diary (DEAR DIARY - Hoa cúc vàng)",
            "style": DaisyDiaryStyle(),
            "content": "DEAR DIARY",
            "subcontent": "NHẬT KÝ ĐỜI THƯỜNG",
        },
        {
            "name": "new_4_ocean_chalk",
            "title": "Mẫu 4: Ocean Chalk Sticker (You are VALID - Tim phấn trắng)",
            "style": OceanChalkStickerStyle(),
            "content": "You are VALID",
            "subcontent": "TỰ TIN LÀ CHÍNH MÌNH 🤍",
        },
        # --- CÁC MẪU CƠ BẢN ĐÃ CÓ ---
        {
            "name": "base_torn_paper",
            "title": "Báo Xé Cổ Điển (Torn Paper)",
            "style": TornPaperStyle(),
            "content": "BÍ QUYẾT TĂNG THU NHẬP",
            "subcontent": "X3 THU NHẬP TRONG 30 NGÀY 🔥",
        },
        {
            "name": "base_bubble_cloud",
            "title": "Vệt Mây Pastel (Bubble Cloud)",
            "style": BubbleCloudStyle(),
            "content": "CƠ HỘI VIỆC LÀM TRIỆU ĐÔ",
            "subcontent": "THU NHẬP 25 - 40 TRIỆU 🌟",
        },
        {
            "name": "base_pastel_multicolor",
            "title": "Kẹo Ngọt Đa Sắc (Pastel Multicolor)",
            "style": PastelMulticolorStyle(),
            "content": "TUYỂN DỤNG GEN Z NĂNG ĐỘNG",
            "subcontent": "MÔI TRƯỜNG LÀM VIỆC TRONG MƠ 🌸",
        },
        {
            "name": "base_no_subcontent",
            "title": "Tiêu Đề Độc Lập (Không Subcontent - Marshmallow Pink)",
            "style": MarshmallowPinkStyle(),
            "content": "CHỈ CÓ TIÊU ĐỀ DUY NHẤT",
            "subcontent": None,
        },
        # --- THỬ NGHIỆM TÍNH NĂNG FONT MỚI ---
        {
            "name": "font_cherry_bomb_one",
            "title": "Font Cụ Thể: Cherry Bomb One (Pastel Multicolor)",
            "style": PastelMulticolorStyle(),
            "content": "CHERRY BOMB ONE",
            "subcontent": "POPULAR DISPLAY FONT 🍒",
            "font": "Cherry Bomb One",
        },
        {
            "name": "font_bungee_shade",
            "title": "Font Cụ Thể: Bungee Shade (Retro Groovy)",
            "style": RetroGroovyOrangeStyle(),
            "content": "BUNGEE SHADE",
            "subcontent": "GROOVY 3D SHADE VIBES ⚡",
            "font": "Bungee Shade",
        },
        {
            "name": "font_random_auto",
            "title": "Font Tự Động: Random từ 27 font định nghĩa sẵn (Bubble Cloud)",
            "style": BubbleCloudStyle(),
            "content": "RANDOM FONT AUTO",
            "subcontent": "TỰ ĐỘNG BỐC NGẪU NHIÊN 🎲",
            "font": None,
        },
    ]

    total_start = time.time()

    for idx, item in enumerate(demos, 1):
        filename = f"{item['name']}.png"
        out_path = output_dir / filename

        print(f"[{idx}/{len(demos)}] Đang render: {item['title']}...")
        t0 = time.time()

        try:
            res_path = engine.render(
                content=item["content"],
                subcontent=item["subcontent"],
                style=item["style"],
                font=item.get("font"),
                output_path=out_path
            )
            elapsed = time.time() - t0
            file_size_kb = res_path.stat().st_size / 1024

            print(f"    -> Thành công! File: {res_path.name}")
            print(f"       Dung lượng: {file_size_kb:.1f} KB | Thời gian: {elapsed:.2f}s")
            print(f"       Đường dẫn: {res_path.resolve()}\n")
        except Exception as exc:
            print(f"    -> Lỗi khi render {item['title']}: {exc}\n")

    total_time = time.time() - total_start
    print("==================================================================")
    print(f"  Hoàn tất render {len(demos)} mẫu overlays trong {total_time:.2f}s!")
    print(f"  Xem toàn bộ ảnh kết quả tại: {output_dir.resolve()}")
    print("==================================================================")


if __name__ == "__main__":
    main()
