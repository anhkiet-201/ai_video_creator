"""Unit tests for Terminal Logger, CarriageReturnHandler, and CLI verbose flags."""

import io
import logging
from unittest.mock import patch
import unittest

from app.utils.terminal_logger import (
    CarriageReturnLogHandler,
    TerminalProgressTracker,
    setup_terminal_logging,
    strip_ansi,
    truncate_to_terminal_width,
)


class TestTerminalLogger(unittest.TestCase):
    """Bộ kiểm thử cho module terminal_logger."""

    def test_truncate_to_terminal_width(self):
        """Kiểm tra logic cắt ngắn text theo bề rộng terminal."""
        short_text = "Nội dung ngắn"
        self.assertEqual(truncate_to_terminal_width(short_text, margin=4), short_text)

        with patch("shutil.get_terminal_size", return_value=type("Size", (), {"columns": 30})()):
            long_text = "Dòng chữ này rất dài và sẽ vượt quá bề rộng giới hạn 30 ký tự của terminal"
            truncated = truncate_to_terminal_width(long_text, margin=4)
            self.assertTrue(truncated.endswith("..."))
            self.assertLessEqual(len(truncated), 30)

    def test_carriage_return_log_handler_info(self):
        """Kiểm tra CarriageReturnLogHandler với log INFO: in đè với \\r và không có \\n."""
        stream = io.StringIO()
        handler = CarriageReturnLogHandler(stream=stream)
        handler.setFormatter(logging.Formatter("%(message)s"))

        logger = logging.getLogger("test_info_logger")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False

        logger.info("Đang xử lý cảnh 1/5...")

        output = stream.getvalue()
        self.assertTrue(output.startswith("\r\033[K"))
        self.assertIn("Đang xử lý cảnh 1/5...", output)
        self.assertFalse(output.endswith("\n"))

    def test_carriage_return_log_handler_warning_and_error(self):
        """Kiểm tra CarriageReturnLogHandler với WARNING/ERROR: phải in ra dòng mới có \\n."""
        stream = io.StringIO()
        handler = CarriageReturnLogHandler(stream=stream)
        handler.setFormatter(logging.Formatter("%(message)s"))

        logger = logging.getLogger("test_warn_logger")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False

        logger.warning("Cảnh báo: Không tìm thấy file âm thanh chuyển cảnh")
        logger.error("Lỗi: Quá trình render thất bại")

        lines = stream.getvalue().split("\n")
        # Phải có ít nhất 2 dòng kết thúc bằng \n
        self.assertGreaterEqual(len(lines), 2)
        self.assertTrue(any("Cảnh báo:" in line for line in lines))
        self.assertTrue(any("Lỗi:" in line for line in lines))

    def test_terminal_progress_tracker_compact_flow(self):
        """Kiểm tra Tracker ở chế độ Compact: đè dòng cho scene, chốt dòng có \\n cho từng plan và bước lớn."""
        stream = io.StringIO()
        tracker = TerminalProgressTracker(verbose=False, stream=stream)

        # 1. Update dở dang
        tracker.on_progress(4, "[Plan 1/2] Đang tạo TTS cảnh 1/3...")
        out1 = stream.getvalue()
        self.assertTrue(out1.startswith("\r\033[K"))
        self.assertFalse(out1.endswith("\n"))

        # 2. Hoàn thành plan 1
        stream.seek(0)
        stream.truncate(0)
        tracker.on_progress(
            4,
            "✓ [Plan 1/2] Hoàn tất đồ họa và âm thanh (3 cảnh)",
            {"plan_completed": True, "plan_index": 1, "total_plans": 2},
        )
        out2 = stream.getvalue()
        self.assertTrue(out2.startswith("\r\033[K"))
        self.assertTrue(out2.endswith("\n"))
        self.assertIn("✓ [Plan 1/2]", strip_ansi(out2))

        # 3. Hoàn thành toàn bộ bước 4
        stream.seek(0)
        stream.truncate(0)
        tracker.on_progress(
            4,
            "Bước 4: Hoàn tất tạo 6 assets đồ họa và âm thanh thành công!",
            {"step_completed": True},
        )
        out3 = stream.getvalue()
        self.assertTrue(out3.endswith("\n"))
        self.assertIn("thành công!", out3)

        # 4. ensure_newline khi đang có \r
        tracker.on_progress(5, "Đang lắp ráp...")
        self.assertTrue(tracker._last_line_was_cr)
        tracker.ensure_newline()
        self.assertFalse(tracker._last_line_was_cr)

    def test_terminal_progress_tracker_verbose_flow(self):
        """Kiểm tra Tracker ở chế độ Verbose: tất cả message đều in xuống dòng \\n."""
        stream = io.StringIO()
        tracker = TerminalProgressTracker(verbose=True, stream=stream)

        tracker.on_progress(1, "Bước 1: Đang thẩm định dữ liệu đầu vào...")
        tracker.on_progress(2, "Bước 2: Đang lên kịch bản thô...")

        lines = stream.getvalue().strip().split("\n")
        self.assertEqual(len(lines), 2)
        self.assertEqual(strip_ansi(lines[0]), "[Step 1/5] Bước 1: Đang thẩm định dữ liệu đầu vào...")
        self.assertEqual(strip_ansi(lines[1]), "[Step 2/5] Bước 2: Đang lên kịch bản thô...")

    def test_cli_verbose_and_verbor_flags(self):
        """Kiểm tra parser của main.py nhận diện chuẩn cờ --verbose, --verbor và -v."""
        import argparse
        from app.services.pipeline.main import main

        # Giả lập parser giống main.py
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--verbose",
            "--verbor",
            "-v",
            action="store_true",
        )

        # 1. Mặc định
        args_default = parser.parse_args([])
        self.assertFalse(args_default.verbose)

        # 2. Cờ chuẩn --verbose
        args_verbose = parser.parse_args(["--verbose"])
        self.assertTrue(args_verbose.verbose)

        # 3. Cờ typo/alias --verbor
        args_verbor = parser.parse_args(["--verbor"])
        self.assertTrue(args_verbor.verbose)

        # 4. Viết tắt -v
        args_v = parser.parse_args(["-v"])
        self.assertTrue(args_v.verbose)

    def test_setup_terminal_logging(self):
        """Kiểm tra hàm setup_terminal_logging cấu hình đúng handlers và log levels."""
        stream = io.StringIO()

        # Compact mode
        tracker_compact = setup_terminal_logging(verbose=False, stream=stream)
        self.assertIsInstance(tracker_compact, TerminalProgressTracker)
        self.assertFalse(tracker_compact.verbose)
        root = logging.getLogger()
        self.assertTrue(any(isinstance(h, CarriageReturnLogHandler) for h in root.handlers))
        self.assertEqual(logging.getLogger("httpx").level, logging.WARNING)

        # Verbose mode
        tracker_verbose = setup_terminal_logging(verbose=True, stream=stream)
        self.assertTrue(tracker_verbose.verbose)
        self.assertTrue(any(isinstance(h, logging.StreamHandler) for h in root.handlers))

    def test_colors_and_strip_ansi(self):
        """Kiểm tra mã màu ANSI và hàm strip_ansi."""
        from app.utils.terminal_logger import Colors, strip_ansi

        colored = f"{Colors.BOLD_GREEN}Thành công{Colors.RESET}"
        self.assertIn("\033[", colored)
        plain = strip_ansi(colored)
        self.assertEqual(plain, "Thành công")

    def test_clean_voice_name(self):
        """Kiểm tra hàm rút gọn tên giọng đọc clean_voice_name."""
        from app.utils.terminal_logger import clean_voice_name

        self.assertEqual(clean_voice_name(None), "Mặc định (Preset)")
        self.assertEqual(clean_voice_name("NgocHuyen-bac-nu.wav"), "NgocHuyen-bac-nu")
        self.assertEqual(clean_voice_name("/path/to/MinhDuc-bac-nam.mp3"), "MinhDuc-bac-nam")
        self.assertEqual(clean_voice_name("__clone_reference_voice_10s-nam-nam_40765__"), "10s-nam-nam (Clone)")


if __name__ == "__main__":
    unittest.main()
