"""CLI Configuration Loader, Cross-Platform Path Resolver, and Conflict Resolution Engine.

Chịu trách nhiệm:
1. Đọc và phân tích file cấu hình JSON (mặc định: config.json).
2. Tự động fallback các giá trị null sang giá trị mặc định chuẩn hệ thống (DEFAULT_CONFIG).
3. Hợp nhất cấu hình và giải quyết xung đột (conflict resolution) giữa CLI flags và config.
4. Chuẩn hóa đường dẫn tương thích đa nền tảng (cả macOS/Linux và Windows, hỗ trợ ./, .\\ và full path).
5. Đảm bảo tính bất biến: Không ghi đè lại file JSON trong suốt quá trình chạy.
"""

import argparse
import json
import logging
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("CLIConfig")

# Bảng hằng số cấu hình mặc định chuẩn của toàn bộ hệ thống
DEFAULT_CONFIG: Dict[str, Any] = {
    "content_file": "content.txt",
    "content": None,
    "source_folder": "assets/samples/company_media",
    "num_videos": 10,
    "api_keys": [],
    "model": "gemini-3.5-flash-lite",
    "voice": None,  # Mặc định null khi randomize_voice_clone bật
    "output_dir": "storage/outputs",
    "bgm": None,
    "bgm_volume": 0.10,
    "randomize_bgm": True,
    "pause_duration": 0.5,
    "tts_seed": None,
    "tts_speed": 1.15,
    "voice_clone_path": None,  # Mặc định null (chỉ điền khi ghim cố định 1 file audio mẫu)
    "voices_dir": "assets/voices",  # Thư mục kho voice phục vụ bốc ngẫu nhiên
    "randomize_voice_clone": True,
    "sync_voice_speed": True,
    "target_wps": None,
    "overlay_style": None,
    "overlay_font": None,
    "overlay_palette": None,
    "overlay_tag": None,
    "keep_temp": False,
    "verbose": False,
}

# Bản đồ ánh xạ cờ dòng lệnh (CLI flag aliases) sang key cấu hình chuẩn
CLI_FLAG_MAP: Dict[str, str] = {
    "--content-file": "content_file",
    "--content": "content",
    "--source-folder": "source_folder",
    "--num-videos": "num_videos",
    "--api-keys": "api_keys",
    "--model": "model",
    "--voice": "voice",
    "--output-dir": "output_dir",
    "--bgm": "bgm",
    "--pause-duration": "pause_duration",
    "--tts-seed": "tts_seed",
    "--tts-speed": "tts_speed",
    "--speed": "tts_speed",
    "--voice-clone-path": "voice_clone_path",
    "--voices-dir": "voices_dir",
    "--randomize-voice-clone": "randomize_voice_clone",
    "--random-voice": "randomize_voice_clone",
    "--no-random-voice": "no_random_voice",
    "--no-randomize-voice-clone": "no_random_voice",
    "--sync-voice-speed": "sync_voice_speed",
    "--no-sync-voice-speed": "no_sync_voice_speed",
    "--target-wps": "target_wps",
    "--bgm-volume": "bgm_volume",
    "--no-random-bgm": "no_random_bgm",
    "--overlay-style": "overlay_style",
    "--overlay-font": "overlay_font",
    "--overlay-palette": "overlay_palette",
    "--overlay-tag": "overlay_tag",
    "--palette-tag": "overlay_tag",
    "--keep-temp": "keep_temp",
    "--verbose": "verbose",
    "--verbor": "verbose",
    "-v": "verbose",
}


def is_cross_platform_absolute(path_str: str) -> bool:
    """Kiểm tra một chuỗi đường dẫn có phải là đường dẫn tuyệt đối (Full Path) hay không.
    
    Hỗ trợ đầy đủ:
    - POSIX (macOS, Linux): /Volumes/..., /Users/...
    - Windows Drive: C:\\..., D:/...
    - Windows UNC: \\\\server\\share\\... hoặc //server/...
    """
    if not path_str:
        return False
    # POSIX root / hoặc Windows backslash root \
    if path_str.startswith(("/", "\\")):
        return True
    # Windows drive letter (ví dụ: C:\ hoặc d:/)
    if len(path_str) >= 2 and path_str[0].isalpha() and path_str[1] == ":":
        return True
    return False


def resolve_filesystem_path(path_val: Any, base_dir: Path) -> Optional[Path]:
    """Chuẩn hóa và resolve đường dẫn tương thích trên cả macOS và Windows.
    
    Quy tắc:
    - Nếu là Full Path (tuyệt đối): Giữ nguyên đường dẫn đầy đủ.
    - Nếu bắt đầu bằng ./ hoặc .\\: Loại bỏ tiền tố và ghép với base_dir.
    - Nếu là đường dẫn tương đối thông thường: Ghép với base_dir.
    - Tự động mở rộng ký tự home (~).
    
    Args:
        path_val: Chuỗi hoặc Path cần chuẩn hóa.
        base_dir: Thư mục gốc dự án dùng làm mốc nếu là đường dẫn tương đối.
        
    Returns:
        Path đã được resolve tuyệt đối, hoặc None nếu path_val rỗng/None.
    """
    if path_val is None:
        return None
    raw_str = str(path_val).strip()
    if not raw_str:
        return None

    # Mở rộng ký tự home ~ nếu có
    expanded_str = os.path.expanduser(raw_str)

    # 1. Kiểm tra nếu đã là đường dẫn tuyệt đối
    if is_cross_platform_absolute(expanded_str) or Path(expanded_str).is_absolute():
        return Path(expanded_str).resolve()

    # 2. Xử lý đường dẫn tương đối: loại bỏ tiền tố ./ hoặc .\ nếu có và chuẩn hóa dấu gạch chéo
    normalized_relative = re.sub(r"^\.[\/\\]+", "", raw_str).replace("\\", "/")
    return (base_dir / normalized_relative).resolve()


def load_json_config(config_path: Path) -> Tuple[Dict[str, Any], bool, Optional[str]]:
    """Đọc và nạp dữ liệu cấu hình từ file JSON."""
    if not config_path.exists():
        return {}, False, None

    try:
        content = config_path.read_text(encoding="utf-8")
        data = json.loads(content)
        if not isinstance(data, dict):
            return {}, True, f"File {config_path} không phải là một JSON Object hợp lệ."
        return data, True, None
    except json.JSONDecodeError as err:
        return {}, True, f"Lỗi cú pháp JSON tại {config_path}: dòng {err.lineno}, cột {err.colno}: {err.msg}"
    except Exception as err:
        return {}, True, f"Lỗi không xác định khi đọc {config_path}: {err}"


def get_explicit_cli_flags(argv: Optional[List[str]] = None) -> Set[str]:
    """Phân tích các cờ CLI thực tế được người dùng truyền vào dòng lệnh."""
    if argv is None:
        argv = sys.argv[1:]

    explicit_keys: Set[str] = set()
    for arg in argv:
        flag = arg.split("=")[0]
        if flag in CLI_FLAG_MAP:
            explicit_keys.add(CLI_FLAG_MAP[flag])

    return explicit_keys


def resolve_config_conflicts(
    merged: Dict[str, Any],
    explicit_keys: Set[str],
) -> Tuple[Dict[str, Any], List[str]]:
    """Giải quyết các xung đột cấu hình theo thứ tự ưu tiên và chủ đích người dùng.
    
    Quy tắc:
    1. Voice vs Voice Clone:
       - Nếu có cờ --voice từ CLI: người dùng muốn giọng chỉ định ➔ Tắt randomize_voice_clone = False.
       - Nếu randomize_voice_clone bật (True) và không có cờ --voice: voice = None (dùng clone từ kho).
    2. Voice Clone Path:
       - Nếu voice_clone_path là null: mặc định lấy 'assets/voices'.
       - Nếu voice_clone_path là 1 file audio đơn lẻ: tắt randomize_voice_clone = False để dùng file đó.
    3. BGM vs Random BGM:
       - Nếu có file bgm chỉ định và CLI không ép random: randomize_bgm = False.
    4. Content vs Content File:
       - Nếu cả 2 đều có: ưu tiên content_file trong config; nếu CLI truyền cả 2 thì chuỗi --content ưu tiên.
    """
    notices: List[str] = []

    # 1. Chuẩn hóa voice_clone_path & voices_dir
    v_path_str = str(merged.get("voice_clone_path") or "").strip()
    if v_path_str:
        if any(v_path_str.lower().endswith(ext) for ext in [".wav", ".mp3", ".m4a", ".flac", ".ogg"]):
            if "randomize_voice_clone" not in explicit_keys:
                merged["randomize_voice_clone"] = False
                notices.append(f"Chỉ định file audio clone '{v_path_str}' -> Tắt chế độ chọn voice ngẫu nhiên.")
        else:
            # Nếu truyền vào là 1 thư mục thay vì file audio, chuyển sang voices_dir
            merged["voices_dir"] = v_path_str
            merged["voice_clone_path"] = None

    if not merged.get("voices_dir"):
        merged["voices_dir"] = DEFAULT_CONFIG["voices_dir"]

    # 2. Xử lý Voice vs Voice Clone
    if "voice" in explicit_keys and merged.get("voice"):
        # Người dùng chủ động truyền cờ --voice trên terminal
        if "randomize_voice_clone" not in explicit_keys:
            merged["randomize_voice_clone"] = False
            notices.append(f"Chỉ định cờ --voice '{merged['voice']}' -> Tắt chế độ voice clone ngẫu nhiên.")
    elif merged.get("randomize_voice_clone"):
        # Chế độ voice clone ngẫu nhiên đang BẬT -> voice preset phải là None
        merged["voice"] = None

    # 3. Xử lý BGM
    if merged.get("bgm"):
        if "no_random_bgm" not in explicit_keys and "randomize_bgm" not in explicit_keys:
            merged["randomize_bgm"] = False
            notices.append(f"Chỉ định file BGM '{merged['bgm']}' -> Tắt tự động bốc BGM ngẫu nhiên.")

    # 4. Xử lý Content vs Content File
    if "content" in explicit_keys and merged.get("content"):
        if "content_file" in explicit_keys and merged.get("content_file"):
            merged["content_file"] = None
            notices.append("Cả --content và --content-file đều được truyền trên CLI -> Ưu tiên chuỗi văn bản trực tiếp từ --content.")
        else:
            merged["content_file"] = None
    elif "content_file" in explicit_keys and merged.get("content_file"):
        merged["content"] = None
    elif merged.get("content_file"):
        # Trong config hoặc mặc định có content_file -> ưu tiên file hơn content trong config
        merged["content"] = None

    return merged, notices


def merge_config_with_cli(
    json_config: Dict[str, Any],
    cli_args: argparse.Namespace,
    explicit_keys: Set[str],
) -> Tuple[Dict[str, Any], List[Tuple[str, Any, Any]], List[str]]:
    """Hợp nhất cấu hình JSON với CLI flags, fallback giá trị null và giải quyết xung đột.
    
    Thứ tự ưu tiên:
    1. Cờ CLI truyền rõ ràng (Explicit CLI flags)
    2. Giá trị trong json_config (nếu khác null)
    3. Giá trị mặc định chuẩn (DEFAULT_CONFIG)
    """
    merged: Dict[str, Any] = {}
    overridden_fields: List[Tuple[str, Any, Any]] = []

    direct_fields = [
        "content_file",
        "content",
        "source_folder",
        "num_videos",
        "api_keys",
        "model",
        "voice",
        "output_dir",
        "bgm",
        "pause_duration",
        "tts_seed",
        "tts_speed",
        "voice_clone_path",
        "voices_dir",
        "target_wps",
        "bgm_volume",
        "overlay_style",
        "overlay_font",
        "overlay_palette",
        "overlay_tag",
        "keep_temp",
        "verbose",
    ]

    for field in direct_fields:
        cli_val = getattr(cli_args, field, None)
        has_cli_explicit = field in explicit_keys
        has_json = field in json_config
        json_val = json_config.get(field)

        if has_cli_explicit:
            merged[field] = cli_val
            if has_json and json_val != cli_val:
                overridden_fields.append((field, json_val, cli_val))
        elif has_json and json_val is not None:
            merged[field] = json_val
        else:
            # Fallback về giá trị mặc định từ DEFAULT_CONFIG
            default_val = DEFAULT_CONFIG.get(field)
            merged[field] = default_val if default_val is not None else cli_val

    # Xử lý các cờ boolean đảo nghịch / kép (Boolean Flags)
    # 1. randomize_voice_clone
    if "no_random_voice" in explicit_keys:
        val = False
        if json_config.get("randomize_voice_clone") is True:
            overridden_fields.append(("randomize_voice_clone", True, False))
        merged["randomize_voice_clone"] = val
    elif "randomize_voice_clone" in explicit_keys:
        val = True
        if json_config.get("randomize_voice_clone") is False:
            overridden_fields.append(("randomize_voice_clone", False, True))
        merged["randomize_voice_clone"] = val
    elif "randomize_voice_clone" in json_config and json_config["randomize_voice_clone"] is not None:
        merged["randomize_voice_clone"] = bool(json_config["randomize_voice_clone"])
    else:
        merged["randomize_voice_clone"] = DEFAULT_CONFIG["randomize_voice_clone"]

    # 2. sync_voice_speed
    if "no_sync_voice_speed" in explicit_keys:
        val = False
        if json_config.get("sync_voice_speed") is True:
            overridden_fields.append(("sync_voice_speed", True, False))
        merged["sync_voice_speed"] = val
    elif "sync_voice_speed" in explicit_keys:
        val = True
        if json_config.get("sync_voice_speed") is False:
            overridden_fields.append(("sync_voice_speed", False, True))
        merged["sync_voice_speed"] = val
    elif "sync_voice_speed" in json_config and json_config["sync_voice_speed"] is not None:
        merged["sync_voice_speed"] = bool(json_config["sync_voice_speed"])
    else:
        merged["sync_voice_speed"] = DEFAULT_CONFIG["sync_voice_speed"]

    # 3. randomize_bgm
    if "no_random_bgm" in explicit_keys:
        val = False
        if json_config.get("randomize_bgm") is True:
            overridden_fields.append(("randomize_bgm", True, False))
        merged["randomize_bgm"] = val
    elif "randomize_bgm" in json_config and json_config["randomize_bgm"] is not None:
        merged["randomize_bgm"] = bool(json_config["randomize_bgm"])
    else:
        merged["randomize_bgm"] = DEFAULT_CONFIG["randomize_bgm"]

    # Giải quyết xung đột cấu hình logic
    merged, conflict_notices = resolve_config_conflicts(merged, explicit_keys)

    return merged, overridden_fields, conflict_notices
