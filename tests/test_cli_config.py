"""Unit tests cho module cli_config (nạp cấu hình JSON, chuẩn hóa đường dẫn & override runtime)."""

import argparse
import json
import os
from pathlib import Path
import tempfile
import unittest

from app.services.pipeline.cli_config import (
    DEFAULT_CONFIG,
    get_explicit_cli_flags,
    is_cross_platform_absolute,
    load_json_config,
    merge_config_with_cli,
    resolve_filesystem_path,
)


class TestCLIConfig(unittest.TestCase):
    """Bộ kiểm thử cho cơ chế nạp cấu hình, fallback null, giải quyết xung đột và chuẩn hóa đường dẫn."""

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.test_dir.name)

    def tearDown(self):
        self.test_dir.cleanup()

    def test_load_json_config_success(self):
        """Kiểm tra đọc file config.json hợp lệ thành công."""
        cfg_file = self.tmp_path / "config.json"
        sample_data = {
            "num_videos": 2,
            "model": "gemini-3.5-flash-lite",
            "voice": "Mai Anh",
            "tts_speed": 1.25,
        }
        cfg_file.write_text(json.dumps(sample_data), encoding="utf-8")

        data, exists, err = load_json_config(cfg_file)
        self.assertTrue(exists)
        self.assertIsNone(err)
        self.assertEqual(data["num_videos"], 2)
        self.assertEqual(data["model"], "gemini-3.5-flash-lite")
        self.assertEqual(data["voice"], "Mai Anh")
        self.assertEqual(data["tts_speed"], 1.25)

    def test_load_json_config_nonexistent(self):
        """Kiểm tra fallback khi file cấu hình không tồn tại (không gây crash)."""
        cfg_file = self.tmp_path / "nonexistent.json"
        data, exists, err = load_json_config(cfg_file)
        self.assertFalse(exists)
        self.assertIsNone(err)
        self.assertEqual(data, {})

    def test_load_json_config_invalid_json(self):
        """Kiểm tra thông báo lỗi khi file JSON hỏng cú pháp."""
        cfg_file = self.tmp_path / "corrupted.json"
        cfg_file.write_text("{ broken json: true, ", encoding="utf-8")

        data, exists, err = load_json_config(cfg_file)
        self.assertTrue(exists)
        self.assertIsNotNone(err)
        self.assertIn("Lỗi cú pháp JSON", err)

    def test_null_values_fallback_to_default(self):
        """Kiểm tra: Tất cả các giá trị null trong JSON đều tự động fallback về DEFAULT_CONFIG."""
        json_with_nulls = {
            "content_file": None,
            "source_folder": None,
            "num_videos": None,
            "model": None,
            "voice": None,
            "output_dir": None,
            "tts_speed": None,
            "voice_clone_path": None,
            "voices_dir": None,
            "randomize_voice_clone": None,
            "sync_voice_speed": None,
        }

        cli_args = argparse.Namespace()
        explicit_flags = set()

        resolved, overridden, notices = merge_config_with_cli(json_with_nulls, cli_args, explicit_flags)

        self.assertEqual(resolved["content_file"], DEFAULT_CONFIG["content_file"])
        self.assertEqual(resolved["source_folder"], DEFAULT_CONFIG["source_folder"])
        self.assertEqual(resolved["num_videos"], DEFAULT_CONFIG["num_videos"])
        self.assertEqual(resolved["model"], "gemini-3.5-flash-lite")
        self.assertEqual(resolved["output_dir"], DEFAULT_CONFIG["output_dir"])
        self.assertIsNone(resolved["voice_clone_path"])
        self.assertEqual(resolved["voices_dir"], "assets/voices")
        self.assertTrue(resolved["randomize_voice_clone"])
        self.assertTrue(resolved["sync_voice_speed"])

    def test_merge_config_cli_override(self):
        """Kiểm tra cờ CLI ghi đè (override) cấu hình từ JSON tại runtime mà không sửa file trên đĩa."""
        cfg_file = self.tmp_path / "config.json"
        original_json_data = {
            "content_file": "sample.txt",
            "num_videos": 1,
            "voice": None,
            "tts_speed": 1.15,
            "randomize_voice_clone": True,
        }
        cfg_file.write_text(json.dumps(original_json_data, indent=2), encoding="utf-8")

        data, exists, err = load_json_config(cfg_file)
        self.assertTrue(exists)

        # Người dùng truyền cờ --num-videos 3 và --voice "Thái Sơn" trên CLI
        argv = ["--num-videos", "3", "--voice", "Thái Sơn"]
        explicit_flags = get_explicit_cli_flags(argv)
        self.assertIn("num_videos", explicit_flags)
        self.assertIn("voice", explicit_flags)

        cli_args = argparse.Namespace(
            num_videos=3,
            voice="Thái Sơn",
        )

        resolved, overridden, notices = merge_config_with_cli(data, cli_args, explicit_flags)

        # 1. Giá trị ghi đè phải cập nhật
        self.assertEqual(resolved["num_videos"], 3)
        self.assertEqual(resolved["voice"], "Thái Sơn")
        # Do truyền cờ --voice, randomize_voice_clone phải tự động tắt
        self.assertFalse(resolved["randomize_voice_clone"])

        # 2. File trên đĩa không bị thay đổi
        content_on_disk = json.loads(cfg_file.read_text(encoding="utf-8"))
        self.assertEqual(content_on_disk, original_json_data)

    def test_conflict_voice_vs_randomize_clone(self):
        """Kiểm tra giải quyết xung đột giữa voice và randomize_voice_clone."""
        # Kịch bản 1: randomize_voice_clone = True và không có cờ --voice -> voice phải là None
        config_data = {"randomize_voice_clone": True, "voice": "Minh Đức"}
        cli_args = argparse.Namespace()
        resolved, _, notices = merge_config_with_cli(config_data, cli_args, explicit_keys=set())
        self.assertTrue(resolved["randomize_voice_clone"])
        self.assertIsNone(resolved["voice"])

        # Kịch bản 2: CLI truyền cờ --voice "Mai Anh" -> tắt randomize_voice_clone
        cli_args_2 = argparse.Namespace(voice="Mai Anh")
        explicit_2 = {"voice"}
        resolved_2, _, notices_2 = merge_config_with_cli(config_data, cli_args_2, explicit_2)
        self.assertFalse(resolved_2["randomize_voice_clone"])
        self.assertEqual(resolved_2["voice"], "Mai Anh")
        self.assertTrue(any("Tắt chế độ voice clone" in n for n in notices_2))

    def test_conflict_bgm_specified(self):
        """Kiểm tra giải quyết xung đột khi chỉ định file BGM cụ thể."""
        config_data = {"bgm": "my_music.mp3", "randomize_bgm": True}
        cli_args = argparse.Namespace(bgm="my_music.mp3")
        resolved, _, notices = merge_config_with_cli(config_data, cli_args, explicit_keys=set())
        # Tự động tắt randomize_bgm vì đã có file bgm cụ thể
        self.assertFalse(resolved["randomize_bgm"])
        self.assertTrue(any("Tắt tự động bốc BGM" in n for n in notices))

    def test_resolve_filesystem_path_cross_platform(self):
        """Kiểm tra chuẩn hóa đường dẫn hỗ trợ cả macOS (./, /...) và Windows (.\\, C:\\...)."""
        base_dir = Path("/Volumes/aki/workspace/AI_Video_Creator")

        # 1. Đường dẫn tương đối bắt đầu bằng ./ (macOS / Linux)
        p1 = resolve_filesystem_path("./storage/outputs", base_dir)
        self.assertEqual(p1, (base_dir / "storage/outputs").resolve())

        # 2. Đường dẫn tương đối bắt đầu bằng .\ (Windows style)
        p2 = resolve_filesystem_path(r".\storage\outputs", base_dir)
        self.assertEqual(p2, (base_dir / "storage/outputs").resolve())

        # 3. Đường dẫn tương đối không có ./
        p3 = resolve_filesystem_path("assets/voices", base_dir)
        self.assertEqual(p3, (base_dir / "assets/voices").resolve())

        # 4. Đường dẫn tuyệt đối POSIX (macOS)
        p4 = resolve_filesystem_path("/Volumes/aki/custom/path", base_dir)
        self.assertEqual(p4, Path("/Volumes/aki/custom/path").resolve())

        # 5. Kiểm tra hàm nhận diện tuyệt đối trên Windows
        self.assertTrue(is_cross_platform_absolute(r"C:\workspace\outputs"))
        self.assertTrue(is_cross_platform_absolute("D:/workspace/outputs"))
        self.assertTrue(is_cross_platform_absolute(r"\\server\share\folder"))
        self.assertTrue(is_cross_platform_absolute("/root/folder"))
        self.assertFalse(is_cross_platform_absolute("./storage/outputs"))
        self.assertFalse(is_cross_platform_absolute(r".\storage\outputs"))
        self.assertFalse(is_cross_platform_absolute("storage/outputs"))


if __name__ == "__main__":
    unittest.main()
