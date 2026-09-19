"""
CLI & Demo Script cho ContentExtractorEngine.
Chạy trực tiếp từ terminal để kiểm thử tính năng trích xuất nội dung tin tuyển dụng:
    python app/services/content_extractor/main.py
hoặc:
    python app/services/content_extractor/main.py --api-keys AIzaSy...
"""

from app.services.content_extractor import ContentExtractorError
import argparse
import json
import os
import sys
import time
from pathlib import Path

# Đảm bảo thư mục gốc dự án có trong sys.path khi chạy script trực tiếp
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.services.content_extractor import (
    ContentExtractorConfig,
    ContentExtractorEngine,
)
from app.services.content_extractor.prompts import (
    DEFAULT_EXTRACTOR_JSON_STRUCTURE,
    DEFAULT_EXTRACTOR_SYSTEM_PROMPT,
)



def main():
    parser = argparse.ArgumentParser(description="Chạy thử nghiệm Content Extractor Engine")
    parser.add_argument(
        "--input-file",
        "-i",
        type=str,
        help="Đường dẫn đến file văn bản chứa tin tuyển dụng cần bóc tách",
    )
    parser.add_argument(
        "--content",
        "-c",
        type=str,
        help="Nội dung văn bản tin tuyển dụng trực tiếp",
    )
    parser.add_argument(
        "--api-keys",
        nargs="+",
        help="Danh sách các Gemini API Keys phân tách bằng dấu cách. Nếu không truyền sẽ đọc từ GEMINI_API_KEY hoặc GEMINI_API_KEYS.",
    )
    parser.add_argument(
        "--model",
        default="gemini-2.5-flash",
        help="Tên mô hình Gemini AI (mặc định: gemini-2.5-flash)",
    )
    args = parser.parse_args()

    # Thu thập nội dung cần bóc tách
    raw_content = ""
    if args.input_file:
        input_path = Path(args.input_file)
        if not input_path.exists():
            print(f"\n[!] LỖI: File không tồn tại: {input_path}")
            sys.exit(1)
        raw_content = input_path.read_text(encoding="utf-8").strip()
    elif args.content:
        raw_content = args.content.strip()

    if not raw_content:
        print("\n[!] CẢNH BÁO: Chưa cung cấp nội dung tin tuyển dụng cần bóc tách!")
        print("    Vui lòng truyền: --input-file <đường_dẫn_file> hoặc --content '<nội dung>'")
        sys.exit(1)

    # Thu thập danh sách api_keys
    api_keys = []
    if args.api_keys:
        api_keys = args.api_keys
    elif os.environ.get("GEMINI_API_KEYS"):
        api_keys = [k.strip() for k in os.environ["GEMINI_API_KEYS"].split(",") if k.strip()]
    elif os.environ.get("GEMINI_API_KEY"):
        api_keys = [os.environ["GEMINI_API_KEY"].strip()]

    print("=" * 66)
    print("🚀 CHƯƠNG TRÌNH KIỂM THỬ CONTENT EXTRACTOR ENGINE (GEMINI AI)")
    print("=" * 66)
    print(f"[i] Model: {args.model}")
    print(f"[i] Số lượng API Keys được nạp: {len(api_keys)}")

    if not api_keys:
        print("\n[!] CẢNH BÁO: Chưa cấu hình API Key nào!")
        print("    Vui lòng truyền qua CLI: python app/services/content_extractor/main.py --api-keys YOUR_KEY_1 YOUR_KEY_2")
        print("    Hoặc đặt biến môi trường: export GEMINI_API_KEY=YOUR_KEY\n")
        sys.exit(1)

    print("\n[+] Đang khởi tạo cấu hình ContentExtractorConfig...")
    config = ContentExtractorConfig(
        model_name=args.model,
        api_keys=api_keys,
        system_prompt=DEFAULT_EXTRACTOR_SYSTEM_PROMPT,
        json_structure=DEFAULT_EXTRACTOR_JSON_STRUCTURE,
        temperature=0.2,
    )

    engine = ContentExtractorEngine(config)

    print("\n[+] Bắt đầu bóc tách tin tuyển dụng...")
    print("------------------------------------------------------------------")
    print(raw_content[:200] + ("\n... (đã cắt bớt cho gọn)" if len(raw_content) > 200 else ""))
    print("------------------------------------------------------------------")

    t_start = time.time()
    try:
        result = engine.extract(raw_content)
        duration = time.time() - t_start

        print(f"\n[✓] TRÍCH XUẤT THÀNH CÔNG trong {duration:.2f}s!")
        print("\n[+] KẾT QUẢ JSON:")
        print(json.dumps(result, ensure_ascii=False, indent=2))


    except ContentExtractorError as e:
        print(f"\n[✗] LỖI TRÍCH XUẤT: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
