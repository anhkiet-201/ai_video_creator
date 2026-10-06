"""CLI & Demo Runner cho Video Creation Pipeline (Luồng 6 bước hoàn chỉnh).

Chạy trực tiếp từ terminal:
    python app/services/pipeline/main.py --help
Hoặc chạy thử nghiệm với file mẫu:
    python app/services/pipeline/main.py \\
        --content-file assets/samples/sample_job.txt \\
        --source-folder assets/samples/company_media \\
        --num-videos 1
"""

import argparse
import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, Optional

# Đảm bảo đường dẫn gốc dự án có trong sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import OUTPUTS_DIR
from app.services.pipeline import (
    PipelineInput,
    PipelineResult,
    VideoCreationPipeline,
)
from app.utils.terminal_logger import Colors, setup_terminal_logging

# Khởi tạo mặc định logger
tracker = setup_terminal_logging(verbose=False)
logger = logging.getLogger("PipelineRunner")


def format_duration(seconds: float) -> str:
    mins = int(seconds // 60)
    secs = seconds % 60
    if mins > 0:
        return f"{mins}m {secs:.1f}s"
    return f"{secs:.1f}s"


def main():
    parser = argparse.ArgumentParser(
        description="AI Video Creator - Luồng 6 bước sản xuất video tự động từ Content và Video Source"
    )
    parser.add_argument(
        "--content-file",
        type=str,
        help="Đường dẫn đến file văn bản chứa nội dung bài viết / tin tuyển dụng",
    )
    parser.add_argument(
        "--content",
        type=str,
        help="Chuỗi văn bản nội dung truyền trực tiếp qua CLI",
    )
    parser.add_argument(
        "--source-folder",
        type=str,
        default="assets/samples/company_media",
        help="Đường dẫn thư mục chứa video và ảnh b-roll nguồn (mặc định: assets/samples/company_media)",
    )
    parser.add_argument(
        "--num-videos",
        type=int,
        default=1,
        help="Số lượng video thành phẩm cần sản xuất (mặc định: 1)",
    )
    parser.add_argument(
        "--api-keys",
        nargs="+",
        help="Danh sách các Gemini API Keys (hỗ trợ phân tách bằng dấu phẩy, khoảng trắng hoặc truyền nhiều keys)",
    )
    parser.add_argument(
        "--llm-provider",
        "--provider",
        dest="llm_provider",
        default=None,
        choices=["gemini", "lm_studio", "lmstudio", "local"],
        help="Nhà cung cấp LLM: 'gemini' hoặc 'lm_studio' (mặc định: gemini)",
    )
    parser.add_argument(
        "--llm-base-url",
        "--base-url",
        dest="llm_base_url",
        default=None,
        help="Địa chỉ máy chủ API cho LM Studio (mặc định: http://localhost:1234/v1)",
    )
    parser.add_argument(
        "--model",
        default="gemini-3.5-flash-lite",
        help="Tên mô hình LLM AI (mặc định: gemini-3.5-flash-lite)",
    )
    parser.add_argument(
        "--voice",
        default=None,
        help="Giọng đọc VieNeu-TTS (mặc định: Minh Đức khi tắt voice clone. Gợi ý: Minh Đức, Mai Anh, Thái Sơn, Thùy Dung...)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(OUTPUTS_DIR),
        help="Thư mục xuất video hoàn phẩm",
    )
    parser.add_argument(
        "--bgm",
        type=str,
        help="Đường dẫn file nhạc nền MP3/WAV (tùy chọn)",
    )
    parser.add_argument(
        "--pause-duration",
        type=float,
        default=0.5,
        help="Khoảng nghỉ giữa các phân cảnh thoại (giây, mặc định: 0.5)",
    )
    parser.add_argument(
        "--tts-seed",
        type=int,
        default=None,
        help="Hạt giống ngẫu nhiên cố định cho giọng đọc (tự sinh per script nếu không truyền)",
    )
    parser.add_argument(
        "--tts-speed",
        "--speed",
        type=float,
        default=1.15,
        help="Tốc độ đọc giọng TTS (mặc định: 1.15x cho video ngắn sôi động, hỗ trợ 0.5 đến 2.0)",
    )
    parser.add_argument(
        "--voice-clone-path",
        type=str,
        default=None,
        help="Đường dẫn file audio mẫu (.wav, .mp3) để clone giọng (Voice Cloning Mode)",
    )
    parser.add_argument(
        "--voices-dir",
        type=str,
        default=None,
        help="Thư mục chứa các voice mẫu để chọn ngẫu nhiên cho từng plan (mặc định: assets/voices)",
    )
    parser.add_argument(
        "--randomize-voice-clone",
        "--random-voice",
        action="store_true",
        default=True,
        help="Tự động chọn ngẫu nhiên 1 voice trong voices-dir cho từng plan (mặc định: BẬT)",
    )
    parser.add_argument(
        "--no-random-voice",
        "--no-randomize-voice-clone",
        action="store_true",
        help="Tắt chế độ chọn ngẫu nhiên voice clone cho từng plan",
    )
    parser.add_argument(
        "--no-sync-voice-speed",
        action="store_true",
        help="Tắt chế độ tự động đồng bộ tốc độ âm thanh giữa các giọng clone (chuyển sang co giãn tĩnh thuần túy)",
    )
    parser.add_argument(
        "--sync-voice-speed",
        action="store_true",
        default=True,
        help="Bật chế độ tự động đồng bộ hóa nhịp đọc giữa các giọng clone (mặc định: BẬT)",
    )
    parser.add_argument(
        "--target-wps",
        type=float,
        default=None,
        help="Tốc độ đọc mục tiêu cơ sở (từ/giây), mặc định: 2.85 WPS (~171 WPM)",
    )
    parser.add_argument(
        "--bgm-volume",
        type=float,
        default=0.10,
        help="Mức âm lượng cho nhạc nền BGM (mặc định: 0.10 = 10%%)",
    )
    parser.add_argument(
        "--no-random-bgm",
        action="store_true",
        help="Tắt chế độ chọn ngẫu nhiên BGM từ thư mục assets/sounds/bgm cho từng plan",
    )
    parser.add_argument(
        "--overlay-style",
        type=str,
        default=None,
        help="Phong cách đồ họa Overlay (ví dụ: bubble_cloud, torn_paper, retro_groovy, tropical_contour...)",
    )
    parser.add_argument(
        "--overlay-font",
        type=str,
        default=None,
        help="Font chữ Google Fonts đồng nhất cho overlay (ví dụ: 'Cherry Bomb One', 'Montserrat', 'Bangers'...)",
    )
    parser.add_argument(
        "--overlay-palette",
        type=str,
        default=None,
        help="Bảng màu Color Hunt đồng nhất cho overlay (ID bảng màu hoặc chuỗi mã màu hex)",
    )
    parser.add_argument(
        "--overlay-tag",
        "--palette-tag",
        type=str,
        default=None,
        help="Tag nhóm bảng màu Color Hunt (pastel, retro, neon, warm, cold, candy...)",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Giữ lại các file tạm thời trong storage/temp sau khi hoàn tất (mặc định sẽ tự động dọn dẹp)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.json",
        help="Đường dẫn đến file cấu hình JSON (mặc định: config.json tại thư mục gốc)",
    )
    parser.add_argument(
        "--verbose",
        "--verbor",
        "-v",
        action="store_true",
        help="Hiển thị tất cả các log cùng lúc (chế độ chi tiết nhiều dòng)",
    )

    args = parser.parse_args()

    print(f"{Colors.GRAY}======================================================================{Colors.RESET}")
    print(f"{Colors.BOLD_CYAN}         AI VIDEO CREATOR - 6-STEP AUTOMATED VIDEO PRODUCTION         {Colors.RESET}")
    print(f"{Colors.GRAY}======================================================================{Colors.RESET}")

    # 1. Nạp cấu hình từ file JSON (mặc định config.json) và merge với cờ CLI runtime
    from app.services.pipeline.cli_config import (
        get_explicit_cli_flags,
        load_json_config,
        merge_config_with_cli,
        resolve_filesystem_path,
    )

    config_path = resolve_filesystem_path(args.config, BASE_DIR)

    json_config, config_exists, config_error = load_json_config(config_path)
    if config_error:
        print(f"{Colors.BOLD_RED}[✗] Cảnh báo cấu hình:{Colors.RESET} {Colors.RED}{config_error}{Colors.RESET}", file=sys.stderr)
        # Nếu người dùng cố ý chỉ định --config mà file lỗi thì dừng lại
        if any(arg == "--config" or arg.startswith("--config=") for arg in sys.argv):
            sys.exit(1)

    explicit_flags = get_explicit_cli_flags(sys.argv[1:])
    resolved, overridden, conflict_notices = merge_config_with_cli(json_config, args, explicit_flags)

    # 2. Đọc nội dung
    raw_content = ""
    content_file_val = resolved.get("content_file")
    content_str_val = resolved.get("content")

    if "content" in explicit_flags and content_str_val:
        raw_content = content_str_val
    elif "content_file" in explicit_flags and content_file_val:
        c_path = resolve_filesystem_path(content_file_val, BASE_DIR)
        if not c_path or not c_path.exists():
            print(f"[✗] Lỗi: Không tìm thấy file content: {c_path}", file=sys.stderr)
            sys.exit(1)
        raw_content = c_path.read_text(encoding="utf-8")
    elif content_str_val and not content_file_val:
        raw_content = content_str_val
    elif content_file_val:
        c_path = resolve_filesystem_path(content_file_val, BASE_DIR)
        if not c_path or not c_path.exists():
            print(f"[✗] Lỗi: Không tìm thấy file content: {c_path}", file=sys.stderr)
            sys.exit(1)
        raw_content = c_path.read_text(encoding="utf-8")
    elif content_str_val:
        raw_content = content_str_val
    else:
        # Sử dụng sample job nếu có
        sample_path = BASE_DIR / "assets" / "samples" / "sample_job.txt"
        if sample_path.exists():
            print(f"[i] Sử dụng nội dung văn bản mẫu từ: {sample_path}")
            raw_content = sample_path.read_text(encoding="utf-8")
        else:
            print("[✗] Lỗi: Vui lòng truyền --content hoặc --content-file!", file=sys.stderr)
            sys.exit(1)

    source_path = resolve_filesystem_path(resolved.get("source_folder", "assets/samples/company_media"), BASE_DIR)
    if not source_path or not source_path.exists():
        print(f"[✗] Lỗi: Thư mục tư liệu không tồn tại: {source_path}", file=sys.stderr)
        sys.exit(1)

    api_keys = resolved.get("api_keys") or []
    if isinstance(api_keys, str):
        api_keys = [k.strip() for k in api_keys.split(",") if k.strip()]

    output_dir_path = resolve_filesystem_path(resolved.get("output_dir", str(OUTPUTS_DIR)), BASE_DIR)
    bgm_path_val = resolve_filesystem_path(resolved.get("bgm"), BASE_DIR) if resolved.get("bgm") else None
    voice_clone_path_val = resolve_filesystem_path(resolved.get("voice_clone_path"), BASE_DIR) if resolved.get("voice_clone_path") else None
    voices_dir_val = resolve_filesystem_path(resolved.get("voices_dir"), BASE_DIR) if resolved.get("voices_dir") else None

    # 3. Khởi tạo PipelineInput
    try:
        pipeline_input = PipelineInput(
            content=raw_content,
            video_source_path=source_path,
            num_videos=int(resolved.get("num_videos", 1)),
            api_keys=api_keys,
            llm_provider=resolved.get("llm_provider") or resolved.get("provider", "gemini"),
            llm_base_url=resolved.get("llm_base_url") or resolved.get("base_url"),
            model_name=resolved.get("model", "gemini-3.5-flash-lite"),
            voice_id=resolved.get("voice"),
            output_dir=output_dir_path,
            bgm_path=bgm_path_val,
            bgm_volume=float(resolved.get("bgm_volume", 0.10)),
            randomize_bgm=bool(resolved.get("randomize_bgm", True)),
            scene_pause_duration=float(resolved.get("pause_duration", 0.5)),
            tts_speed=float(resolved.get("tts_speed", 1.15)),
            tts_seed=int(resolved["tts_seed"]) if resolved.get("tts_seed") is not None else None,
            sync_voice_speed=bool(resolved.get("sync_voice_speed", True)),
            target_wps=float(resolved["target_wps"]) if resolved.get("target_wps") is not None else None,
            voice_clone_path=voice_clone_path_val,
            voices_dir=voices_dir_val,
            randomize_voice_clone=bool(resolved.get("randomize_voice_clone", True)),
            overlay_style=resolved.get("overlay_style"),
            overlay_font=resolved.get("overlay_font"),
            overlay_palette=resolved.get("overlay_palette"),
            overlay_palette_tag=resolved.get("overlay_tag"),
        )
    except Exception as e:
        print(f"[✗] Lỗi tham số đầu vào: {e}", file=sys.stderr)
        sys.exit(1)

    def _print_param(label: str, value: str) -> None:
        print(f"  {Colors.BOLD_CYAN}▸{Colors.RESET} {Colors.GRAY}{label:<26}{Colors.RESET} {Colors.BOLD_WHITE}{value}{Colors.RESET}")

    if config_exists:
        _print_param("File cấu hình (Config):", f"{config_path.name} (Đã nạp)")
    else:
        _print_param("File cấu hình (Config):", "Không có file (Dùng mặc định)")

    if conflict_notices:
        for notice in conflict_notices:
            print(f"  {Colors.BOLD_YELLOW}⚠ Xử lý xung đột:{Colors.RESET} {Colors.YELLOW}{notice}{Colors.RESET}")

    if overridden:
        override_summary = ", ".join([f"--{f}" for f, _, _ in overridden])
        _print_param("Cờ CLI ghi đè runtime:", f"{len(overridden)} thông số ({override_summary})")

    if resolved.get("content"):
        content_preview = resolved["content"].strip().replace("\n", " ")
        if len(content_preview) > 35:
            content_preview = content_preview[:32] + "..."
        _print_param("Nội dung đầu vào:", f"Trực tiếp từ CLI ({len(resolved['content'])} ký tự: \"{content_preview}\")")
    elif resolved.get("content_file"):
        _print_param("Nội dung đầu vào:", f"Từ file: {resolved['content_file']} ({len(raw_content)} ký tự)")

    _print_param("Thư mục tư liệu nguồn:", str(pipeline_input.video_source_path))
    _print_param("Số lượng video yêu cầu:", f"{pipeline_input.num_videos} video thành phẩm")
    _print_param("Nhà cung cấp LLM:", f"{str(pipeline_input.llm_provider).upper()} ({pipeline_input.model_name})")
    if pipeline_input.llm_base_url:
        _print_param("Địa chỉ LLM Base URL:", str(pipeline_input.llm_base_url))
    _print_param("Tốc độ đọc (TTS Speed):", f"{pipeline_input.tts_speed}x")
    _print_param("Đồng bộ nhịp đọc:", f"{'BẬT (Smart Speaking Rate Sync)' if pipeline_input.sync_voice_speed else 'TẮT'}")
    _print_param("Thư mục xuất video:", str(pipeline_input.output_dir))
    if pipeline_input.overlay_style:
        _print_param("Overlay Style chỉ định:", str(pipeline_input.overlay_style))
    if pipeline_input.overlay_font:
        _print_param("Overlay Font chỉ định:", str(pipeline_input.overlay_font))
    if pipeline_input.overlay_palette:
        _print_param("Overlay Palette chỉ định:", str(pipeline_input.overlay_palette))
    if pipeline_input.overlay_palette_tag:
        _print_param("Overlay Palette Tag:", str(pipeline_input.overlay_palette_tag))
    if pipeline_input.randomize_voice_clone:
        _print_param("Chế độ Voice:", f"Clone ngẫu nhiên (từ {pipeline_input.voices_dir or 'assets/voices'})")
    elif pipeline_input.voice_clone_path and pipeline_input.voice_clone_path.is_file():
        _print_param("Chế độ Voice:", f"Clone cố định ({pipeline_input.voice_clone_path.name})")
    else:
        _print_param("Chế độ Voice:", f"Preset giọng ({pipeline_input.voice_id or 'Minh Đức'})")
    _print_param("Tự động xóa file tạm:", f"{'TẮT (giữ lại file để debug)' if resolved.get('keep_temp') else 'BẬT (sạch sẽ)'}")
    print(f"{Colors.GRAY}----------------------------------------------------------------------{Colors.RESET}")

    # Cấu hình lại terminal logger theo cờ verbose từ cấu hình đã merge
    tracker = setup_terminal_logging(verbose=bool(resolved.get("verbose", False)))
    pipeline = VideoCreationPipeline()

    t_start = time.time()
    result: PipelineResult = pipeline.execute(
        input_data=pipeline_input,
        on_progress=tracker.on_progress,
        cleanup_temp=not bool(resolved.get("keep_temp", False)),
    )
    tracker.ensure_newline()
    total_time = time.time() - t_start

    print(f"{Colors.GRAY}======================================================================{Colors.RESET}")
    if result.is_successful:
        print(f"{Colors.BOLD_GREEN}🎉 SẢN XUẤT {len(result.render_results)}/{pipeline_input.num_videos} VIDEO THÀNH CÔNG{Colors.RESET} {Colors.GRAY}trong{Colors.RESET} {Colors.BOLD_YELLOW}{format_duration(total_time)}{Colors.RESET}!")
        print(f"  {Colors.CYAN}•{Colors.RESET} {Colors.GRAY}Session ID:{Colors.RESET} {result.session_id}")
        print(f"  {Colors.CYAN}•{Colors.RESET} {Colors.GRAY}Số kịch bản thô:{Colors.RESET} {len(result.rough_scripts)} | {Colors.GRAY}Chi tiết:{Colors.RESET} {len(result.detailed_plans)}")
        print(f"{Colors.GRAY}----------------------------------------------------------------------{Colors.RESET}")
        for idx, res in enumerate(result.render_results):
            mb_size = res.file_size_bytes / (1024 * 1024)
            print(f"  {Colors.BOLD_CYAN}🎬 Video #{idx + 1}:{Colors.RESET} {Colors.BOLD_WHITE}{res.output_path.name}{Colors.RESET}")
            print(f"     {Colors.GRAY}Thời lượng:{Colors.RESET} {Colors.YELLOW}{res.duration:.2f}s{Colors.RESET} {Colors.GRAY}| Dung lượng:{Colors.RESET} {Colors.GREEN}{mb_size:.2f} MB{Colors.RESET}")
        print(f"{Colors.GRAY}======================================================================{Colors.RESET}")
    else:
        print(f"{Colors.BOLD_RED}💥 QUÁ TRÌNH SẢN XUẤT THẤT BẠI sau {format_duration(total_time)}!{Colors.RESET}")
        for err in result.errors:
            print(f"  {Colors.BOLD_RED}✗{Colors.RESET} {Colors.RED}{err}{Colors.RESET}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
