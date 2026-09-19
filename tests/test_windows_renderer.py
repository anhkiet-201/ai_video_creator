"""Unit & Integration tests for WindowsVideoRenderer."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from app.services.video_render_engine import (
    AntiReupProfile,
    FFmpegBaseRenderer,
    MacOSVideoRenderer,
    RenderResult,
    ScenePlan,
    TaskLogger,
    VideoRenderConfig,
    VideoRenderEngine,
    VideoRenderPlan,
    WindowsVideoRenderer,
    get_platform_renderer,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEST_TMP_DIR = PROJECT_ROOT / "storage" / "temp" / "test_windows_renderer"
TEST_OUTPUT_DIR = PROJECT_ROOT / "storage" / "temp" / "test_windows_outputs"


class TestWindowsVideoRenderer(unittest.TestCase):
    """Test suite for WindowsVideoRenderer on Windows OS."""

    @classmethod
    def setUpClass(cls):
        TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        cls.renderer = WindowsVideoRenderer(hardware_accel=True, default_fit_mode="crop")
        cls.is_env_valid = cls.renderer.validate_environment()

        # Tạo file audio test mẫu (thời lượng 1.5s)
        cls.test_audio_path = TEST_TMP_DIR / "sample_audio_1_5s.mp3"
        if cls.is_env_valid:
            subprocess.run(
                [
                    cls.renderer._ffmpeg_bin, "-y",
                    "-f", "lavfi",
                    "-i", "sine=frequency=1000:duration=1.5",
                    "-c:a", "libmp3lame",
                    "-b:a", "128k",
                    str(cls.test_audio_path),
                ],
                capture_output=True,
                check=True,
            )

            # Tạo file overlay PNG test mẫu (1080x300)
            cls.test_overlay_path = TEST_TMP_DIR / "sample_overlay.png"
            subprocess.run(
                [
                    cls.renderer._ffmpeg_bin, "-y",
                    "-f", "lavfi",
                    "-i", "color=c=red@0.5:s=1080x300",
                    "-frames:v", "1",
                    str(cls.test_overlay_path),
                ],
                capture_output=True,
                check=True,
            )

            # Tạo video b-roll mẫu 4.0s
            cls.test_broll_dir = TEST_TMP_DIR / "broll"
            cls.test_broll_dir.mkdir(parents=True, exist_ok=True)
            cls.test_broll_video = cls.test_broll_dir / "broll_sample.mp4"
            subprocess.run(
                [
                    cls.renderer._ffmpeg_bin, "-y",
                    "-f", "lavfi",
                    "-i", "testsrc=duration=4.0:size=1080x1920:rate=30",
                    "-c:v", cls.renderer._encoder,
                    "-pix_fmt", "yuv420p",
                    str(cls.test_broll_video),
                ],
                capture_output=True,
                check=True,
            )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEST_TMP_DIR, ignore_errors=True)
        shutil.rmtree(TEST_OUTPUT_DIR, ignore_errors=True)

    def setUp(self):
        self.renderer = WindowsVideoRenderer(hardware_accel=True, default_fit_mode="crop")
        self.task_logger = TaskLogger(plan_id="test_win_logger")

    def test_01_renderer_metadata_and_inheritance(self):
        """Kiểm tra kế thừa và định danh của WindowsVideoRenderer."""
        self.assertIsInstance(self.renderer, FFmpegBaseRenderer)
        self.assertEqual(self.renderer.renderer_name, "WindowsVideoRenderer")

    def test_02_validate_environment_discovery(self):
        """Kiểm tra cơ chế dò tìm binary và kích hoạt phần cứng NVIDIA NVENC."""
        is_valid = self.renderer.validate_environment()
        self.assertTrue(is_valid)
        self.assertTrue(Path(self.renderer._ffmpeg_bin).exists())
        self.assertTrue(Path(self.renderer._ffprobe_bin).exists())
        # Nếu máy có GPU NVIDIA NVENC, _encoder phải là h264_nvenc, ngược lại fallback libx264
        self.assertIn(self.renderer._encoder, ["h264_nvenc", "libx264"])

    def test_03_fallback_software_encoder_when_accel_disabled(self):
        """Kiểm tra fallback sang libx264 khi tắt hardware_accel."""
        cpu_renderer = WindowsVideoRenderer(hardware_accel=False)
        is_valid = cpu_renderer.validate_environment()
        self.assertTrue(is_valid)
        self.assertEqual(cpu_renderer._encoder, "libx264")

    def test_04_factory_get_platform_renderer(self):
        """Kiểm tra hàm get_platform_renderer tự động trả về WindowsVideoRenderer trên Windows."""
        platform_renderer = get_platform_renderer()
        if sys.platform == "win32":
            self.assertIsInstance(platform_renderer, WindowsVideoRenderer)
            self.assertEqual(platform_renderer.renderer_name, "WindowsVideoRenderer")
        elif sys.platform == "darwin":
            self.assertIsInstance(platform_renderer, MacOSVideoRenderer)

    def test_05_get_media_duration(self):
        """Kiểm tra hàm ffprobe đo chính xác độ dài file audio trên Windows."""
        if not self.is_env_valid or not self.test_audio_path.exists():
            self.skipTest("Môi trường FFmpeg chưa sẵn sàng")
        dur = self.renderer._get_media_duration(self.test_audio_path)
        self.assertAlmostEqual(dur, 1.5, delta=0.1)

    def test_06_render_pipeline_end_to_end(self):
        """Kiểm tra toàn bộ pipeline render từ on_render_start -> render_plan -> on_render_end."""
        if not self.is_env_valid or not self.test_broll_video.exists():
            self.skipTest("Môi trường FFmpeg chưa sẵn sàng")

        self.renderer.validate_environment()

        plan = VideoRenderPlan(
            plan_id="win_test_plan_001",
            title="Video Test Windows",
            scenes=[
                ScenePlan(
                    scene_index=0,
                    content="Phân cảnh thử nghiệm 1 trên Windows",
                    audio_path=self.test_audio_path,
                    overlay_image_path=self.test_overlay_path,
                    metadata={"scene_id": "scene_0"},
                ),
                ScenePlan(
                    scene_index=1,
                    content="Phân cảnh thử nghiệm 2 trên Windows",
                    audio_path=self.test_audio_path,
                    overlay_image_path=self.test_overlay_path,
                    metadata={"scene_id": "scene_1"},
                ),
            ],
            output_filename="output_test_windows.mp4",
        )

        config = VideoRenderConfig(
            width=1080,
            height=1920,
            fps=30,
            output_dir=TEST_OUTPUT_DIR,
            temp_dir=TEST_TMP_DIR,
            enable_bgm=False,
            enable_transition_sound=False,
        )

        profile = AntiReupProfile(
            profile_id="win_profile_01",
            speed=1.0,
            zoom=1.0,
            flip_horizontal=False,
        )

        # 1. on_render_start
        self.renderer.on_render_start(
            plan=plan,
            task_logger=self.task_logger,
            source_folder=self.test_broll_dir,
            config=config,
        )

        # 2. render_plan
        result = self.renderer.render_plan(
            plan=plan,
            source_folder=self.test_broll_dir,
            config=config,
            profile=profile,
            task_logger=self.task_logger,
        )

        self.assertIsInstance(result, RenderResult)
        self.assertTrue(result.output_path.exists())
        self.assertGreater(result.file_size_bytes, 0)
        self.assertAlmostEqual(result.duration, 3.0, delta=0.5)
        self.assertEqual(result.metadata.get("encoder_used"), self.renderer._encoder)

        # 3. on_render_end
        self.renderer.on_render_end(
            result=result,
            task_logger=self.task_logger,
            plan=plan,
            config=config,
        )
        temp_dir = self.renderer._get_temp_plan_dir(plan.plan_id, config)
        self.assertFalse(temp_dir.exists())


if __name__ == "__main__":
    unittest.main()
