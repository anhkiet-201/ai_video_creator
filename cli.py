#!/usr/bin/env python3
"""CLI Entrypoint cho AI Video Creator.

Tự động chuyển tiếp lệnh thực thi tới app.services.pipeline.main.
"""

from pathlib import Path
import sys

# Đảm bảo đường dẫn gốc dự án có trong sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.pipeline.main import main

if __name__ == "__main__":
    main()
