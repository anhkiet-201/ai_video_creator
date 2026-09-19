"""
CLI & Demo Script cho TTSEngine (OmniVoice).
Chạy trực tiếp từ terminal để kiểm thử tính năng tổng hợp giọng nói:
    python app/services/tts_engine/main.py
"""

import sys
import time
from pathlib import Path

# Đảm bảo thư mục gốc dự án có trong sys.path khi chạy script trực tiếp
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import OUTPUTS_DIR
from app.services.tts_engine import TTSEngine


def main():
    print("==================================================================")
    print("        DEMO TTS ENGINE (OMNIVOICE DIFFUSION TTS)                 ")
    print("==================================================================")

    output_dir = OUTPUTS_DIR / "demo_tts"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[+] Khởi tạo TTSEngine...")
    t_init = time.time()
    engine = TTSEngine()
    print(f"    -> Thiết bị hoạt động: {engine.device.upper()} (Khởi tạo trong {time.time() - t_init:.2f}s)\n")

    test_cases = [
        {
            "name": "1_female_standard",
            "desc": "Giọng Nữ Tiêu Chuẩn (speed=1.0, pitch='+0Hz')",
            "text": "Chào mừng bạn đến với hệ thống sáng tạo nội dung video ngắn tự động bằng trí tuệ nhân tạo.",
            "voice": "female",
            "speed": 1.0,
            "pitch": "+0Hz",
            "voice_clone_path": None,
        },
        {
            "name": "2_male_standard",
            "desc": "Giọng Nam Đĩnh Đạc (speed=1.1, pitch='+0Hz')",
            "text": "Khám phá cơ hội nghề nghiệp kỹ sư AI với mức thu nhập hấp dẫn lên đến bốn mươi triệu đồng một tháng.",
            "voice": "male",
            "speed": 1.1,
            "pitch": "+0Hz",
            "voice_clone_path": None,
        },
        {
            "name": "3_tiktok_fast_pitch",
            "desc": "Tốc Độ Cao TikTok & High Pitch (speed='+22%', pitch='+2Hz')",
            "text": "Bật mí bí quyết nhân ba thu nhập chỉ trong ba mươi ngày cực kỳ đơn giản cho người mới bắt đầu!",
            "voice": "female",
            "speed": "+22%",
            "pitch": "+2Hz",
            "voice_clone_path": None,
        },
    ]

    total_start = time.time()
    generated_files = []

    for idx, tc in enumerate(test_cases, 1):
        out_file = output_dir / f"{tc['name']}.mp3"
        print(f"[{idx}/{len(test_cases) + 1}] Đang xử lý: {tc['desc']}...")
        t0 = time.time()

        try:
            res_path = engine.synthesize(
                text=tc["text"],
                speed=tc["speed"],
                voice=tc["voice"],
                pitch=tc["pitch"],
                voice_clone_path=tc["voice_clone_path"],
                output_path=out_file
            )
            elapsed = time.time() - t0
            duration = engine.get_duration(res_path)
            file_kb = res_path.stat().st_size / 1024

            print(f"    -> Thành công! File: {res_path.name}")
            print(f"       Thời lượng âm thanh: {duration:.2f}s | Dung lượng: {file_kb:.1f} KB | Render: {elapsed:.2f}s")
            print(f"       Đường dẫn: {res_path.resolve()}\n")
            generated_files.append((res_path, tc["text"]))

        except Exception as exc:
            print(f"    -> Lỗi khi render {tc['name']}: {exc}\n")

    # Demo 4: Thử nghiệm Voice Cloning sử dụng file audio đầu tiên làm mẫu và transcript tương ứng
    if generated_files:
        sample_audio, sample_text = generated_files[0]
        clone_out_file = output_dir / "4_voice_cloned.mp3"
        print(f"[{len(test_cases) + 1}/{len(test_cases) + 1}] Đang xử lý: Voice Cloning (sao chép giọng từ mẫu {sample_audio.name})...")
        t0 = time.time()
        try:
            clone_res = engine.synthesize(
                text="Đây là giọng nói được nhân bản chính xác từ file âm thanh mẫu với mô hình OmniVoice.",
                speed=1.1,
                voice_clone_path=sample_audio,
                ref_text=sample_text,
                output_path=clone_out_file
            )
            elapsed = time.time() - t0
            dur = engine.get_duration(clone_res)
            file_kb = clone_res.stat().st_size / 1024
            print(f"    -> Thành công! File: {clone_res.name}")
            print(f"       Thời lượng âm thanh: {dur:.2f}s | Dung lượng: {file_kb:.1f} KB | Render: {elapsed:.2f}s")
            print(f"       Đường dẫn: {clone_res.resolve()}\n")
        except Exception as exc:
            print(f"    -> Lỗi khi render Voice Clone: {exc}\n")

    total_time = time.time() - total_start
    print("==================================================================")
    print(f"  Hoàn tất toàn bộ demo TTS Engine trong {total_time:.2f}s!")
    print(f"  Thư mục kết quả âm thanh: {output_dir.resolve()}")
    print("==================================================================")


if __name__ == "__main__":
    main()
