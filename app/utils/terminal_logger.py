"""Tiện ích quản lý hiển thị Terminal Logging, ANSI Colors và Progress Tracking.

Hỗ trợ 2 chế độ:
- Compact Mode (mặc định): Cập nhật trạng thái liên tục trên 1 dòng đơn bằng `\\r\\033[K`,
  in chốt kết quả từng plan và từng bước lớn bằng `\\n` với màu sắc ANSI sống động.
- Verbose Mode (--verbose / --verbor / -v): Hiển thị streaming tất cả các log nhiều dòng.
"""

import logging
import os
from pathlib import Path
import re
import shutil
import sys
import threading
from typing import Any, Dict, Optional, TextIO
import warnings

# Vô hiệu hóa cảnh báo symlinks và unauthenticated từ Hugging Face Hub
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
warnings.filterwarnings("ignore", message=".*unauthenticated requests to the HF Hub.*")
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub.*")


class Colors:
    """Bảng mã màu ANSI chuẩn dành cho giao diện dòng lệnh hiện đại."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"

    # Màu cơ bản
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"

    # Màu in đậm (Bold)
    BOLD_RED = "\033[1;31m"
    BOLD_GREEN = "\033[1;32m"
    BOLD_YELLOW = "\033[1;33m"
    BOLD_BLUE = "\033[1;34m"
    BOLD_MAGENTA = "\033[1;35m"
    BOLD_CYAN = "\033[1;36m"
    BOLD_WHITE = "\033[1;37m"

    # Màu nền
    BG_CYAN = "\033[46;30m"
    BG_GREEN = "\033[42;30m"


ANSI_REGEX = re.compile(r"\033\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """Loại bỏ toàn bộ mã màu ANSI để tính toán chính xác độ dài hiển thị trên màn hình."""
    return ANSI_REGEX.sub("", text)


def truncate_to_terminal_width(text: str, margin: int = 4) -> str:
    """Cắt ngắn chuỗi nếu độ dài hiển thị (không tính mã ANSI) vượt quá bề rộng màn hình terminal."""
    try:
        columns = shutil.get_terminal_size((80, 20)).columns
    except Exception:
        columns = 80

    max_visible_len = max(20, columns - margin)
    visible_len = len(strip_ansi(text))

    if visible_len <= max_visible_len:
        return text

    # Cắt tỉa ký tự hiển thị kèm giữ nguyên kết thúc Reset nếu có mã màu
    clean = strip_ansi(text)
    cut = clean[: max_visible_len - 3] + "..."
    if "\033[" in text:
        return f"{cut}{Colors.RESET}"
    return cut


def clean_voice_name(voice_raw: Optional[str]) -> str:
    """Rút gọn và làm đẹp tên giọng đọc (bỏ .wav, .mp3, prefix mã hóa nội bộ)."""
    if not voice_raw:
        return "Mặc định (Preset)"

    name = Path(voice_raw).stem

    # Xử lý voice clone id tự sinh nội bộ: __clone_reference_voice_10s-nam-nam_40765__
    if name.startswith("__clone_reference_voice_"):
        parts = name.replace("__clone_reference_voice_", "").rstrip("_").split("_")
        core = parts[0]
        return f"{core} (Clone)"

    # Xử lý các voice có định dạng Name-region-gender
    if "-" in name:
        return name.replace(".wav", "").replace(".mp3", "")

    return name


class CarriageReturnLogHandler(logging.Handler):
    """Logging Handler sử dụng `\\r` để in đè log INFO/DEBUG lên 1 dòng,

    và in `\\n` cho WARNING/ERROR/CRITICAL để lưu vết rõ ràng.
    """

    def __init__(self, stream: Optional[TextIO] = None):
        super().__init__()
        self.stream = stream or sys.stdout
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            with self._lock:
                if record.levelno >= logging.ERROR:
                    self.stream.write(f"\r\033[K{Colors.BOLD_RED}[ERROR]{Colors.RESET} {msg}\n")
                elif record.levelno >= logging.WARNING:
                    self.stream.write(f"\r\033[K{Colors.BOLD_YELLOW}[WARN]{Colors.RESET} {msg}\n")
                else:
                    truncated = truncate_to_terminal_width(msg)
                    self.stream.write(f"\r\033[K{truncated}")
                self.stream.flush()
        except RecursionError:
            raise
        except Exception:
            self.handleError(record)


class TerminalProgressTracker:
    """Quản lý hiển thị tiến trình 6 bước của Video Creation Pipeline.

    Đặc biệt hỗ trợ cơ chế update real-time theo từng Plan và in chốt mốc từng Plan
    với màu sắc ANSI rực rỡ và chuyên nghiệp.
    """

    def __init__(
        self,
        verbose: bool = False,
        stream: Optional[TextIO] = None,
        total_steps: int = 5,
    ):
        self.verbose = verbose
        self.stream = stream or sys.stdout
        self.total_steps = total_steps
        self._lock = threading.Lock()
        self._last_line_was_cr = False

    def on_progress(
        self,
        step: int,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Callback tiến độ được gọi từ VideoCreationPipeline."""
        data = data or {}

        # 1. Chế độ Verbose: In streaming toàn bộ từng dòng với ký tự xuống dòng \n
        if self.verbose:
            with self._lock:
                step_tag = f"{Colors.BOLD_MAGENTA}[Step {step}/{self.total_steps}]{Colors.RESET}"
                self.stream.write(f"{step_tag} {message}\n")
                self.stream.flush()
                self._last_line_was_cr = False
            return

        # 2. Chế độ Compact: Cập nhật đè dòng \r và in chốt mốc \n
        is_plan_completed = bool(data.get("plan_completed", False))
        is_step_completed = bool(
            data.get("step_completed", False)
            or ("thành công!" in message.lower())
            or ("hoàn tất render" in message.lower())
        )

        with self._lock:
            if is_plan_completed:
                # In chốt mốc khi hoàn tất 1 Plan (Assets hoặc Video)
                plan_no = data.get("plan_index")
                total_plans = data.get("total_plans")
                plan_tag = (
                    f"{Colors.BOLD_YELLOW}[Plan {plan_no}/{total_plans}]{Colors.RESET}"
                    if (plan_no and total_plans)
                    else ""
                )

                if "Xuất xong:" in message or "Render hoàn tất:" in message or "🎬" in message:
                    clean_msg = message.replace("🎬", "").strip()
                    if plan_tag and f"[Plan {plan_no}/{total_plans}]" in clean_msg:
                        clean_msg = clean_msg.replace(f"[Plan {plan_no}/{total_plans}]", "").strip()
                    line = f"  {Colors.BOLD_CYAN}🎬{Colors.RESET} {plan_tag} {Colors.BOLD_WHITE}{clean_msg}{Colors.RESET}\n"
                else:
                    clean_msg = message.replace("✓", "").strip()
                    if plan_tag and f"[Plan {plan_no}/{total_plans}]" in clean_msg:
                        clean_msg = clean_msg.replace(f"[Plan {plan_no}/{total_plans}]", "").strip()
                    line = f"  {Colors.BOLD_GREEN}✓{Colors.RESET} {plan_tag} {Colors.WHITE}{clean_msg}{Colors.RESET}\n"

                self.stream.write(f"\r\033[K{line}")
                self.stream.flush()
                self._last_line_was_cr = False

            elif is_step_completed:
                # In chốt mốc khi hoàn tất 1 bước lớn
                step_badge = f"{Colors.BOLD_GREEN}[✓]{Colors.RESET} {Colors.BOLD_MAGENTA}[Step {step}/{self.total_steps}]{Colors.RESET}"
                clean_msg = message
                if f"[Step {step}/{self.total_steps}]" in clean_msg:
                    clean_msg = clean_msg.replace(f"[Step {step}/{self.total_steps}]", "").strip()
                line = f"{step_badge} {Colors.BOLD_WHITE}{clean_msg}{Colors.RESET}\n"

                self.stream.write(f"\r\033[K{line}")
                self.stream.flush()
                self._last_line_was_cr = False

            else:
                # Đang xử lý dở dang (real-time): in đè bằng \r
                step_badge = f"{Colors.BOLD_MAGENTA}[Step {step}/{self.total_steps}]{Colors.RESET}"
                plan_no = data.get("plan_index")
                total_plans = data.get("total_plans")

                clean_msg = message
                if f"[Step {step}/{self.total_steps}]" in clean_msg:
                    clean_msg = clean_msg.replace(f"[Step {step}/{self.total_steps}]", "").strip()

                if plan_no and total_plans and f"[Plan {plan_no}/{total_plans}]" in clean_msg:
                    clean_msg = clean_msg.replace(f"[Plan {plan_no}/{total_plans}]", "").strip()
                    plan_badge = f"{Colors.BOLD_YELLOW}[Plan {plan_no}/{total_plans}]{Colors.RESET}"
                    full_text = f"{step_badge} {plan_badge} {Colors.WHITE}{clean_msg}{Colors.RESET}"
                else:
                    full_text = f"{step_badge} {Colors.WHITE}{clean_msg}{Colors.RESET}"

                truncated = truncate_to_terminal_width(full_text)
                self.stream.write(f"\r\033[K{truncated}")
                self.stream.flush()
                self._last_line_was_cr = True

    def ensure_newline(self) -> None:
        """Đảm bảo đẩy con trỏ xuống dòng mới nếu dòng trước đó đang treo `\\r`."""
        with self._lock:
            if self._last_line_was_cr:
                self.stream.write("\n")
                self.stream.flush()
                self._last_line_was_cr = False


def setup_terminal_logging(
    verbose: bool = False,
    log_level: int = logging.INFO,
    stream: Optional[TextIO] = None,
) -> TerminalProgressTracker:
    """Cấu hình hệ thống logging ra terminal phù hợp với cờ verbose.

    Args:
        verbose: True nếu muốn hiển thị tất cả log dạng streaming nhiều dòng;
                 False để dùng chế độ gọn gàng (Carriage return `\\r` và màu sắc).
        log_level: Cấp độ log tối thiểu (mặc định logging.INFO).
        stream: Output stream (mặc định sys.stdout).

    Returns:
        TerminalProgressTracker được cấu hình đồng bộ.
    """
    out_stream = stream or sys.stdout
    root_logger = logging.getLogger()

    # Xóa các handlers cũ để tránh duplicate log
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Danh sách các module ồn ào cần hạ log level khi ở chế độ Compact
    noisy_loggers = [
        "httpx",
        "httpcore",
        "google",
        "google.genai",
        "urllib3",
        "filelock",
        "PIL",
        "huggingface_hub",
        "transformers",
        "app.services.render_overlay_engine.engine",
        "app.services.render_overlay_engine.palettes",
        "app.services.tts_engine.engine",
        "app.services.key_rotator",
        "app.services.video_render_engine.voice_manager",
        "app.services.video_render_engine.sound_effect_manager",
        "app.services.video_render_engine.transition_sound_manager",
        "app.services.video_render_engine.bgm_manager",
        "app.services.video_render_engine.anti_reup_engine",
        "app.services.video_render_engine.base_renderer",
        "app.services.video_render_engine.ffmpeg_renderer",
        "app.services.video_render_engine.macos_renderer",
        "app.services.video_render_engine.windows_renderer",
        "app.services.video_render_engine.engine",
        "app.services.video_render_engine.audio",
        "app.services.video_render_engine.renderers",
        "app.services.video_render_engine.processors",
        "app.services.video_render_engine.core",
    ]

    if verbose:
        handler = logging.StreamHandler(out_stream)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
        root_logger.setLevel(log_level)
        for lib in noisy_loggers:
            logging.getLogger(lib).setLevel(log_level)
    else:
        cr_handler = CarriageReturnLogHandler(out_stream)
        cr_handler.setFormatter(formatter)
        root_logger.addHandler(cr_handler)
        root_logger.setLevel(log_level)

        for lib in noisy_loggers:
            logging.getLogger(lib).setLevel(logging.WARNING)

    return TerminalProgressTracker(verbose=verbose, stream=out_stream)
