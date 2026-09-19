"""Unit tests for robust Gemini API keys parsing and rotation."""

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from app.services.key_rotator import KeyRotator
from app.services.pipeline.coordinator import VideoCreationPipeline
from app.services.pipeline.models import PipelineInput


class TestApiKeysHandling(unittest.TestCase):
    """Test suite verifying all formats of API key inputs are properly normalized."""

    def test_01_coordinator_resolve_comma_separated_string(self):
        # Trường hợp 1: Người dùng truyền 1 chuỗi chứa nhiều keys ngăn cách bởi dấu phẩy
        raw_keys = ["AIzaSyKey1,AIzaSyKey2,AIzaSyKey3"]
        resolved = VideoCreationPipeline._resolve_api_keys(raw_keys)
        self.assertEqual(resolved, ["AIzaSyKey1", "AIzaSyKey2", "AIzaSyKey3"])

    def test_02_coordinator_resolve_comma_with_spaces(self):
        # Trường hợp 2: Người dùng truyền chuỗi có dấu phẩy và khoảng trắng
        raw_keys = ["AIzaSyKey1,  AIzaSyKey2 ,   AIzaSyKey3"]
        resolved = VideoCreationPipeline._resolve_api_keys(raw_keys)
        self.assertEqual(resolved, ["AIzaSyKey1", "AIzaSyKey2", "AIzaSyKey3"])

    def test_03_coordinator_resolve_semicolon_and_newlines(self):
        # Trường hợp 3: Người dùng copy paste nhiều dòng hoặc dùng chấm phẩy
        raw_keys = ["AIzaSyKey1; AIzaSyKey2\nAIzaSyKey3\tAIzaSyKey4"]
        resolved = VideoCreationPipeline._resolve_api_keys(raw_keys)
        self.assertEqual(resolved, ["AIzaSyKey1", "AIzaSyKey2", "AIzaSyKey3", "AIzaSyKey4"])

    def test_04_coordinator_resolve_powershell_trailing_commas(self):
        # Trường hợp 4: PowerShell array truyền vào CLI dạng ["key1,", "key2"]
        raw_keys = ["AIzaSyKey1,", "AIzaSyKey2"]
        resolved = VideoCreationPipeline._resolve_api_keys(raw_keys)
        self.assertEqual(resolved, ["AIzaSyKey1", "AIzaSyKey2"])

    def test_05_coordinator_resolve_quotes_and_deduplication(self):
        # Trường hợp 5: Chuỗi dính dấu nháy đơn/kép và có key trùng lặp
        raw_keys = ['"AIzaSyKey1"', "'AIzaSyKey2'", "AIzaSyKey1"]
        resolved = VideoCreationPipeline._resolve_api_keys(raw_keys)
        self.assertEqual(resolved, ["AIzaSyKey1", "AIzaSyKey2"])

    def test_06_coordinator_fallback_env_gemini_api_keys(self):
        # Trường hợp 6: Không truyền input, đọc từ biến môi trường GEMINI_API_KEYS
        with patch.dict(os.environ, {"GEMINI_API_KEYS": "EnvKey1, EnvKey2; EnvKey3"}, clear=True):
            resolved = VideoCreationPipeline._resolve_api_keys([])
            self.assertEqual(resolved, ["EnvKey1", "EnvKey2", "EnvKey3"])

    def test_07_coordinator_fallback_single_env_key(self):
        # Trường hợp 7: Đọc từ biến môi trường GEMINI_API_KEY
        with patch.dict(os.environ, {"GEMINI_API_KEY": "SingleEnvKey123"}, clear=True):
            resolved = VideoCreationPipeline._resolve_api_keys([])
            self.assertEqual(resolved, ["SingleEnvKey123"])

    def test_08_key_rotator_tokenization(self):
        # Trường hợp 8: KeyRotator tự động phân tách chuỗi gộp
        rotator = KeyRotator(["KeyA, KeyB", "KeyC;KeyD"])
        self.assertEqual(rotator._keys, ["KeyA", "KeyB", "KeyC", "KeyD"])
        self.assertEqual(rotator.get_current_key(), "KeyA")

        # Đánh dấu KeyA hỏng -> tự động nhảy sang KeyB
        next_key = rotator.mark_key_failed("KeyA", "429 Quota Exceeded")
        self.assertEqual(next_key, "KeyB")
        self.assertEqual(rotator.get_current_key(), "KeyB")

    def test_09_pipeline_input_validation(self):
        # Trường hợp 9: PipelineInput validator tự động phân rã chuỗi string hoặc mảng dính
        dummy_dir = Path("assets/samples/company_media")
        
        inp1 = PipelineInput(
            content="Tuyển dụng kỹ sư",
            video_source_path=dummy_dir,
            api_keys="Key1, Key2, Key3",
        )
        self.assertEqual(inp1.api_keys, ["Key1", "Key2", "Key3"])

        inp2 = PipelineInput(
            content="Tuyển dụng kỹ sư",
            video_source_path=dummy_dir,
            api_keys=["KeyA, KeyB", "KeyC"],
        )
        self.assertEqual(inp2.api_keys, ["KeyA", "KeyB", "KeyC"])


if __name__ == "__main__":
    unittest.main()
