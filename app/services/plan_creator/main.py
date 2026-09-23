"""
CLI & Demo Script cho PlanCreatorEngine.
Chạy trực tiếp từ terminal để kiểm thử tính năng lên kịch bản từ JSON content:
    python app/services/plan_creator/main.py
hoặc:
    python app/services/plan_creator/main.py --num-scripts 3 --api-keys AIzaSy...
"""

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

from app.services.plan_creator.prompts import (
    DEFAULT_JSON_STRUCTURE,
    DEFAULT_SYSTEM_PROMPT,
)

from app.services.plan_creator.engine import PlanCreatorEngine
from app.services.plan_creator.exceptions import PlanCreatorError
from app.services.plan_creator.models import PlanCreatorConfig


def main():
    parser = argparse.ArgumentParser(description="Chạy thử nghiệm Plan Creator Engine")
    parser.add_argument(
        "--input-file",
        "-i",
        type=str,
        required=True,
        help="Đường dẫn đến file JSON chứa thông tin/bài viết về công ty cần review (BẮT BUỘC)",
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
    parser.add_argument(
        "--num-scripts",
        type=int,
        default=3,
        help="Số lượng kịch bản cần sinh ra (mặc định: 3)",
    )
    args = parser.parse_args()

    # Nạp nội dung input từ file
    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"[✗] LỖI: Không tìm thấy file input: {input_path}")
        sys.exit(1)
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            content_data = json.load(f)
        print(f"[+] Đã nạp thành công nội dung từ file: {input_path}")
    except Exception as e:
        print(f"[✗] LỖI: Không thể đọc hoặc parse JSON từ file '{input_path}': {e}")
        sys.exit(1)

    # Thu thập danh sách api_keys
    api_keys = []
    if args.api_keys:
        api_keys = args.api_keys
    elif os.environ.get("GEMINI_API_KEYS"):
        api_keys = [k.strip() for k in os.environ.get("GEMINI_API_KEYS", "").split(",") if k.strip()]
    elif os.environ.get("GEMINI_API_KEY"):
        api_keys = [os.environ.get("GEMINI_API_KEY", "").strip()]

    print("==================================================================")
    print("         DEMO PLAN CREATOR ENGINE (KỊCH BẢN VIDEO NGẮN AI)        ")
    print("==================================================================")
    print(f"[i] Model: {args.model}")
    print(f"[i] Số lượng kịch bản yêu cầu: {args.num_scripts}")
    print(f"[i] Số lượng API Keys được nạp: {len(api_keys)}")

    if not api_keys:
        print("\n[!] CẢNH BÁO: Chưa cấu hình API Key nào!")
        print("    Vui lòng truyền qua CLI: python app/services/plan_creator/main.py --input-file <file.json> --api-keys YOUR_KEY_1 YOUR_KEY_2")
        print("    Hoặc đặt biến môi trường: export GEMINI_API_KEY=YOUR_KEY\n")
        sys.exit(1)


    print("\n[+] Đang khởi tạo cấu hình PlanCreatorConfig...")
    config = PlanCreatorConfig(
        model_name=args.model,
        api_keys=api_keys,
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        json_structure=DEFAULT_JSON_STRUCTURE,
        temperature=0.7,
    )

    engine = PlanCreatorEngine(config)

    styles = [
        "Góc nhìn trải nghiệm môi trường làm việc thực tế",
        "Góc nhìn đánh giá công nghệ, máy móc và quy mô doanh nghiệp",
        "Góc nhìn tiện ích nội khu, cơ sở vật chất và văn hóa công ty"
    ]

    def on_plan_progress(idx: int, total: int, script: dict):
        title = script.get("title") or f"Kịch bản #{idx}"
        scenes_count = len(script.get("scenes", []))
        print(f"    -> [✓] Đã tạo xong kịch bản {idx}/{total}: '{title}' ({scenes_count} scenes)")

    print(f"\n[+] Bắt đầu tạo {args.num_scripts} kịch bản video bằng Gemini AI (1 request / 1 plan)...")
    t_start = time.time()
    try:
        result = engine.create_plans(
            content=content_data,
            num_scripts=args.num_scripts,
            creative_styles=styles[: args.num_scripts],
            on_progress=on_plan_progress,
        )
        duration = time.time() - t_start

        print(f"\n[✓] TẠO KỊCH BẢN THÀNH CÔNG trong {duration:.2f}s!")
        print("\n[+] KẾT QUẢ JSON KỊCH BẢN:")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    except PlanCreatorError as e:
        print(f"\n[✗] LỖI LÊN KỊCH BẢN: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
