"""Unit & Integration tests for MacOSVideoRenderer."""

from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from app.services.video_render_engine import (
    AntiReupProfile,
    MacOSVideoRenderer,
    ScenePlan,
    TaskLogger,
    VideoRenderConfig,
    VideoRenderEngine,
    VideoRenderPlan,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = PROJECT_ROOT / "assets" / "samples" / "company_media"
TEST_TMP_DIR = PROJECT_ROOT / "storage" / "temp" / "test_macos_renderer"
TEST_OUTPUT_DIR = PROJECT_ROOT / "storage" / "temp" / "test_macos_outputs"


@unittest.skipUnless(sys.platform == "darwin", "MacOSVideoRenderer test suite chỉ chạy trên macOS")
class TestMacOSVideoRenderer(unittest.TestCase):
    """Test suite for MacOSVideoRenderer on macOS."""

    @classmethod
    def setUpClass(cls):
        TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Tạo file audio test mẫu (thời lượng 1.5s) bằng FFmpeg
        cls.test_audio_path = TEST_TMP_DIR / "sample_audio_1_5s.mp3"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "sine=frequency=1000:duration=1.5",
                "-c:a", "libmp3lame",
                "-b:a", "128k",
                str(cls.test_audio_path),
            ],
            capture_output=True,
            check=True,
        )

        # Tạo file overlay PNG test mẫu (1080x1920 có chữ hoặc vùng vẽ trong suốt)
        cls.test_overlay_path = TEST_TMP_DIR / "sample_overlay.png"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "color=c=red@0.5:s=1080x300",
                "-frames:v", "1",
                str(cls.test_overlay_path),
            ],
            capture_output=True,
            check=True,
        )

        # Tạo thư mục và các file SFX transition test mẫu
        cls.test_sfx_dir = TEST_TMP_DIR / "sounds" / "transition"
        cls.test_sfx_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "sine=frequency=400:duration=0.6",
                "-af", "volume=enable='between(t,0.25,0.35)':volume=5",
                "-c:a", "pcm_s16le",
                str(cls.test_sfx_dir / "whoosh_01.wav"),
            ],
            capture_output=True,
            check=True,
        )
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "sine=frequency=600:duration=0.5",
                "-af", "volume=enable='between(t,0.15,0.25)':volume=5",
                "-c:a", "pcm_s16le",
                str(cls.test_sfx_dir / "whoosh_02.wav"),
            ],
            capture_output=True,
            check=True,
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEST_TMP_DIR, ignore_errors=True)
        shutil.rmtree(TEST_OUTPUT_DIR, ignore_errors=True)

    def setUp(self):
        self.renderer = MacOSVideoRenderer(hardware_accel=True, default_fit_mode="crop")
        self.task_logger = TaskLogger(plan_id="test_logger")

    def test_01_validate_environment(self):
        """Kiểm tra môi trường macOS phát hiện đúng ffmpeg, ffprobe và encoder."""
        is_valid = self.renderer.validate_environment()
        self.assertTrue(is_valid)
        self.assertIn(self.renderer._encoder, ["h264_videotoolbox", "libx264"])

    def test_02_get_media_duration(self):
        """Kiểm tra hàm ffprobe đo chính xác độ dài file audio."""
        dur = self.renderer._get_media_duration(self.test_audio_path)
        self.assertAlmostEqual(dur, 1.5, delta=0.1)

    def test_03_on_render_start_cuts_segments(self):
        """Kiểm tra on_render_start đo độ dài audio và cắt segments vào tmp/video_render/{plan_id}/."""
        plan_id = "test_plan_start_01"
        plan = VideoRenderPlan(
            plan_id=plan_id,
            title="Test Plan Start",
            scenes=[
                ScenePlan(
                    scene_index=0,
                    content="Scene 1",
                    audio_path=self.test_audio_path,
                ),
            ],
        )
        config = VideoRenderConfig(
            width=540,
            height=960,
            fps=24,
            output_dir=TEST_OUTPUT_DIR,
            temp_dir=TEST_TMP_DIR,
            extra_params={"aspect_mode": "crop"},
        )

        self.renderer.validate_environment()
        self.renderer.on_render_start(
            plan=plan,
            task_logger=self.task_logger,
            source_folder=SAMPLES_DIR,
            config=config,
        )

        # Kiểm tra segment đã được cắt trong thư mục tạm
        plan_tmp_dir = TEST_TMP_DIR / "video_render" / plan_id
        self.assertTrue(plan_tmp_dir.exists())

        segment_file = plan_tmp_dir / "scene_0.mp4"
        self.assertTrue(segment_file.exists())
        self.assertGreater(segment_file.stat().st_size, 0)

        # Kiểm tra thời lượng của segment xấp xỉ 1.5s
        segment_dur = self.renderer._get_media_duration(segment_file)
        self.assertAlmostEqual(segment_dur, 1.5, delta=0.2)

        # Dọn dẹp
        self.renderer.on_render_end(
            result=None,
            task_logger=self.task_logger,
            plan=plan,
            config=config,
        )
        self.assertFalse(plan_tmp_dir.exists())

    def test_04_full_render_cycle_with_engine(self):
        """Kiểm tra trọn vẹn vòng đời render_plan qua VideoRenderEngine."""
        plan_id = "test_full_render_02"
        plan = VideoRenderPlan(
            plan_id=plan_id,
            title="Video Thử Nghiệm MacOS",
            scenes=[
                ScenePlan(
                    scene_index=0,
                    content="Phân cảnh 1",
                    audio_path=self.test_audio_path,
                    overlay_image_path=self.test_overlay_path,
                ),
                ScenePlan(
                    scene_index=1,
                    content="Phân cảnh 2",
                    audio_path=self.test_audio_path,
                ),
            ],
            output_filename="output_test_macos.mp4",
        )

        config = VideoRenderConfig(
            width=540,
            height=960,
            fps=24,
            output_dir=TEST_OUTPUT_DIR,
            temp_dir=TEST_TMP_DIR,
            extra_params={"aspect_mode": "pad"},  # Kiểm tra cả mode pad
        )

        engine = VideoRenderEngine(renderer=self.renderer, config=config)

        result = engine.render_plan(
            source_folder=SAMPLES_DIR,
            plan=plan,
        )

        # Xác minh kết quả trả về
        self.assertEqual(result.plan_id, plan_id)
        self.assertTrue(result.output_path.exists())
        self.assertGreater(result.file_size_bytes, 0)
        self.assertGreater(result.duration, 2.5)  # 2 scenes x 1.5s ~ 3.0s
        self.assertEqual(result.scenes_count, 2)
        self.assertEqual(result.metadata.get("fit_mode"), "pad")

        # Xác minh thư mục tạm tmp/video_render/{plan_id} đã được tự động xóa bởi on_render_end
        plan_tmp_dir = TEST_TMP_DIR / "video_render" / plan_id
        self.assertFalse(plan_tmp_dir.exists())

    def test_05_cleanup_on_failure(self):
        """Kiểm tra on_render_end tự động dọn dẹp thư mục tạm khi render gặp lỗi."""
        plan_id = "test_cleanup_failure_03"
        plan = VideoRenderPlan(
            plan_id=plan_id,
            title="Plan Lỗi Giả Lập",
            scenes=[
                ScenePlan(
                    scene_index=0,
                    content="Scene Lỗi",
                    audio_path=self.test_audio_path,
                ),
            ],
        )
        config = VideoRenderConfig(
            width=540,
            height=960,
            temp_dir=TEST_TMP_DIR,
        )

        plan_tmp_dir = TEST_TMP_DIR / "video_render" / plan_id
        plan_tmp_dir.mkdir(parents=True, exist_ok=True)
        (plan_tmp_dir / "garbage.tmp").write_text("rác dữ liệu")

        # Gọi on_render_end mô phỏng tình huống failure
        self.renderer.on_render_end(
            result=None,
            task_logger=self.task_logger,
            plan=plan,
            config=config,
        )

        self.assertFalse(plan_tmp_dir.exists())

    def test_06_render_with_flip_horizontal_keeps_overlay_safe(self):
        """Xác minh render với flip_horizontal=True xử lý hflip riêng cho background mà không làm lỗi overlay."""
        plan_id = "test_flip_h_overlay_safe"
        plan = VideoRenderPlan(
            plan_id=plan_id,
            title="Test Flip H Overlay Safe",
            scenes=[
                ScenePlan(
                    scene_index=0,
                    content="Phân cảnh lật nền",
                    audio_path=self.test_audio_path,
                    overlay_image_path=self.test_overlay_path,
                ),
            ],
            output_filename="output_test_flip_safe.mp4",
        )

        config = VideoRenderConfig(
            width=540,
            height=960,
            fps=24,
            output_dir=TEST_OUTPUT_DIR,
            temp_dir=TEST_TMP_DIR,
        )

        engine = VideoRenderEngine(renderer=self.renderer, config=config)
        # Bật thủ công flip_horizontal=True trong anti_reup_engine
        engine.anti_reup_engine.set_rule("flip_horizontal", True)

        result = engine.render_plan(
            source_folder=SAMPLES_DIR,
            plan=plan,
        )

        self.assertTrue(result.output_path.exists())
        self.assertGreater(result.file_size_bytes, 0)
        self.assertEqual(result.anti_reup_profile.get("flip_horizontal"), True)

    def test_07_on_render_start_ensures_scene_diversity(self):
        """Xác minh on_render_start phân bổ các cảnh không trùng lặp video kề nhau."""
        plan_id = "test_diversity_multi_scenes"
        plan = VideoRenderPlan(
            plan_id=plan_id,
            title="Test Multi Scene Diversity",
            scenes=[
                ScenePlan(
                    scene_index=i,
                    content=f"Scene content {i}",
                    audio_path=self.test_audio_path,
                )
                for i in range(4)
            ],
        )
        config = VideoRenderConfig(
            width=540,
            height=960,
            fps=24,
            output_dir=TEST_OUTPUT_DIR,
            temp_dir=TEST_TMP_DIR,
        )

        multi_broll_dir = TEST_TMP_DIR / "multi_brolls"
        multi_broll_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(SAMPLES_DIR / "sample_broll.mp4", multi_broll_dir / "broll_01.mp4")
        shutil.copy(SAMPLES_DIR / "sample_broll.mp4", multi_broll_dir / "broll_02.mp4")

        self.renderer.on_render_start(
            plan=plan,
            task_logger=self.task_logger,
            source_folder=multi_broll_dir,
            config=config,
        )

        # Kiểm tra tất cả các scene đều có segment_path và tồn tại
        chosen_videos = []
        for scene in plan.scenes:
            seg_path = Path(scene.metadata["segment_path"])
            self.assertTrue(seg_path.exists())
            self.assertGreater(seg_path.stat().st_size, 0)
            chosen_videos.append(scene.metadata.get("chosen_video"))

        # Kiểm tra các cảnh kề nhau không bị trùng video nguồn
        for i in range(1, len(chosen_videos)):
            self.assertNotEqual(
                chosen_videos[i - 1],
                chosen_videos[i],
                f"Scene {i-1} và Scene {i} bị trùng video: {chosen_videos[i]}",
            )

        # Dọn dẹp
        self.renderer.on_render_end(result=None, task_logger=self.task_logger, plan=plan, config=config)

    def test_08_render_plan_with_transition_sound_peak_alignment(self):
        """Xác minh render hoàn chỉnh có hòa trộn âm thanh chuyển cảnh căn theo đỉnh Waveform."""
        plan_id = "test_transition_sound_render"
        plan = VideoRenderPlan(
            plan_id=plan_id,
            title="Test Transition Sound SFX",
            scenes=[
                ScenePlan(
                    scene_index=0,
                    content="Scene Alpha",
                    overlay_image_path=self.test_overlay_path,
                    audio_path=self.test_audio_path,
                ),
                ScenePlan(
                    scene_index=1,
                    content="Scene Beta",
                    overlay_image_path=self.test_overlay_path,
                    audio_path=self.test_audio_path,
                ),
                ScenePlan(
                    scene_index=2,
                    content="Scene Gamma",
                    overlay_image_path=self.test_overlay_path,
                    audio_path=self.test_audio_path,
                ),
            ],
        )
        config = VideoRenderConfig(
            width=540,
            height=960,
            fps=24,
            output_dir=TEST_OUTPUT_DIR,
            temp_dir=TEST_TMP_DIR,
            enable_transition_sound=True,
            transition_sound_volume=0.15,
            transition_sound_dir=self.test_sfx_dir,
        )

        engine = VideoRenderEngine(renderer=self.renderer, config=config)
        result = engine.render_plan(
            source_folder=SAMPLES_DIR,
            plan=plan,
        )

        self.assertTrue(result.output_path.exists())
        self.assertGreater(result.file_size_bytes, 0)
        # 3 cảnh -> 2 điểm chuyển cảnh được chèn SFX
        self.assertEqual(result.metadata.get("transition_sfx_count"), 2)

    def test_09_render_plan_with_transition_sound_disabled(self):
        """Xác minh cờ enable_transition_sound=False tắt âm thanh chuyển cảnh."""
        plan_id = "test_transition_sound_off"
        plan = VideoRenderPlan(
            plan_id=plan_id,
            title="Test Transition Sound Disabled",
            scenes=[
                ScenePlan(
                    scene_index=0,
                    content="Scene Alpha",
                    audio_path=self.test_audio_path,
                ),
                ScenePlan(
                    scene_index=1,
                    content="Scene Beta",
                    audio_path=self.test_audio_path,
                ),
            ],
        )
        config = VideoRenderConfig(
            width=540,
            height=960,
            fps=24,
            output_dir=TEST_OUTPUT_DIR,
            temp_dir=TEST_TMP_DIR,
            enable_transition_sound=False,
            transition_sound_dir=self.test_sfx_dir,
        )

        engine = VideoRenderEngine(renderer=self.renderer, config=config)
        result = engine.render_plan(
            source_folder=SAMPLES_DIR,
            plan=plan,
        )

        self.assertTrue(result.output_path.exists())
        self.assertEqual(result.metadata.get("transition_sfx_count"), 0)

    def test_10_render_plan_skip_transition_sound_when_scene_has_sound_effect(self):
        """Xác minh bỏ qua âm thanh chuyển cảnh nếu cảnh trước đó đã chứa sound_effect."""
        plan_id = "test_sfx_collision_avoidance"
        plan = VideoRenderPlan(
            plan_id=plan_id,
            title="Test SFX Collision Avoidance",
            scenes=[
                ScenePlan(
                    scene_index=0,
                    content="Scene 0 with Sound Effect",
                    audio_path=self.test_audio_path,
                    metadata={"sound_effect": "Ding - Highlight Key Benefit.mp3"},
                ),
                ScenePlan(
                    scene_index=1,
                    content="Scene 1 without Sound Effect",
                    audio_path=self.test_audio_path,
                ),
                ScenePlan(
                    scene_index=2,
                    content="Scene 2 without Sound Effect",
                    audio_path=self.test_audio_path,
                ),
            ],
        )
        # TH1: avoid_sfx_transition_collision=True (Mặc định) -> bỏ qua transition 0->1, chỉ chèn 1->2 (tổng = 1)
        config_avoid = VideoRenderConfig(
            width=540,
            height=960,
            fps=24,
            output_dir=TEST_OUTPUT_DIR,
            temp_dir=TEST_TMP_DIR,
            enable_transition_sound=True,
            avoid_sfx_transition_collision=True,
            transition_sound_volume=0.15,
            transition_sound_dir=self.test_sfx_dir,
        )

        engine = VideoRenderEngine(renderer=self.renderer, config=config_avoid)
        result = engine.render_plan(
            source_folder=SAMPLES_DIR,
            plan=plan,
        )

        self.assertTrue(result.output_path.exists())
        self.assertEqual(result.metadata.get("transition_sfx_count"), 1)

    def test_11_render_plan_with_bgm_volume_10_percent(self):
        """Xác minh render video thành phẩm kết hợp BGM với âm lượng 10% và phát xuyên suốt."""
        test_bgm = TEST_TMP_DIR / "test_bgm_10pct.wav"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "sine=frequency=220:duration=1.0",
                "-c:a", "pcm_s16le",
                str(test_bgm),
            ],
            capture_output=True,
            check=True,
        )

        plan_id = "test_bgm_render_10pct"
        plan = VideoRenderPlan(
            plan_id=plan_id,
            title="Video Test BGM 10%",
            scenes=[
                ScenePlan(
                    scene_index=0,
                    content="Scene with BGM",
                    audio_path=self.test_audio_path,
                ),
            ],
            bgm_path=test_bgm,
            bgm_volume=0.10,
            output_filename="output_test_bgm_10pct.mp4",
        )

        config = VideoRenderConfig(
            width=540,
            height=960,
            fps=24,
            output_dir=TEST_OUTPUT_DIR,
            temp_dir=TEST_TMP_DIR,
            enable_bgm=True,
            bgm_volume=0.10,
        )

        engine = VideoRenderEngine(renderer=self.renderer, config=config)
        result = engine.render_plan(
            source_folder=SAMPLES_DIR,
            plan=plan,
        )

        self.assertTrue(result.output_path.exists())
        self.assertGreater(result.file_size_bytes, 0)
        self.assertEqual(result.metadata.get("bgm_path"), str(test_bgm))
        self.assertEqual(result.metadata.get("bgm_volume"), 0.10)
        self.assertEqual(result.metadata.get("bgm_name"), "test_bgm_10pct.wav")

    def test_12_seamless_audio_transitions_without_swallowing(self):
        """Xác minh render đa phân cảnh đảm bảo audio không bị nuốt hoặc drop packet tại ranh giới scene."""
        # Tạo 3 file audio test độc lập với thời lượng khác nhau
        aud1 = TEST_TMP_DIR / "test_aud_scene1.wav"
        aud2 = TEST_TMP_DIR / "test_aud_scene2.wav"
        aud3 = TEST_TMP_DIR / "test_aud_scene3.wav"

        for p, freq, dur in [(aud1, 300, 1.2), (aud2, 600, 1.4), (aud3, 900, 1.1)]:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "lavfi",
                    "-i", f"sine=frequency={freq}:duration={dur}",
                    "-c:a", "pcm_s16le",
                    "-ar", "48000",
                    str(p),
                ],
                capture_output=True,
                check=True,
            )

        expected_total_duration = 1.2 + 1.4 + 1.1  # 3.7s

        plan_id = "test_seamless_audio_transitions"
        plan = VideoRenderPlan(
            plan_id=plan_id,
            title="Video Test Seamless Transitions",
            scenes=[
                ScenePlan(scene_index=0, content="Scene 1", audio_path=aud1),
                ScenePlan(scene_index=1, content="Scene 2", audio_path=aud2),
                ScenePlan(scene_index=2, content="Scene 3", audio_path=aud3),
            ],
            output_filename="output_seamless_audio.mp4",
        )

        config = VideoRenderConfig(
            width=540,
            height=960,
            fps=24,
            output_dir=TEST_OUTPUT_DIR,
            temp_dir=TEST_TMP_DIR,
            enable_transition_sound=True,
            transition_sound_dir=self.test_sfx_dir,
            transition_sound_volume=0.15,
        )

        engine = VideoRenderEngine(renderer=self.renderer, config=config)
        result = engine.render_plan(
            source_folder=SAMPLES_DIR,
            plan=plan,
        )

        self.assertTrue(result.output_path.exists())
        self.assertAlmostEqual(result.duration, expected_total_duration, delta=0.15)
        self.assertEqual(result.scenes_count, 3)

        # Kiểm tra ffprobe stream audio để đảm bảo không bị đứt đoạn hay drop
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=duration,sample_rate,channels",
            "-of", "json",
            str(result.output_path),
        ]
        probe_res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
        import json
        probe_data = json.loads(probe_res.stdout)
        stream_info = probe_data["streams"][0]
        actual_audio_dur = float(stream_info["duration"])
        self.assertAlmostEqual(actual_audio_dur, expected_total_duration, delta=0.15)
        self.assertEqual(int(stream_info["sample_rate"]), 48000)
        self.assertEqual(int(stream_info["channels"]), 2)

    def test_13_render_plan_with_company_name_output_structure(self):
        """Kiểm tra video render tự động tạo thư mục outputs/{company}-{date}/tik_final_01.mp4."""
        from datetime import datetime
        plan_id = "test_company_output_01"
        scenes = [
            ScenePlan(
                scene_index=0,
                content="Kho Vận Tuyển Dụng",
                audio_path=self.test_audio_path,
                metadata={"measured_duration": 1.5},
            )
        ]
        plan = VideoRenderPlan(
            plan_id=plan_id,
            company_name="Kho Vận Thực Phẩm Hoàng Gia",
            video_index=1,
            title="Tuyển Dụng Kho Vận",
            scenes=scenes,
        )

        config = VideoRenderConfig(
            width=540,
            height=960,
            fps=24,
            output_dir=TEST_OUTPUT_DIR,
            temp_dir=TEST_TMP_DIR,
        )
        engine = VideoRenderEngine(renderer=self.renderer, config=config)
        result = engine.render_plan(source_folder=SAMPLES_DIR, plan=plan)

        self.assertTrue(result.output_path.exists())
        # Thư mục cha phải có dạng: kho-van-thuc-pham-hoang-gia-{DD-MM-YYYY}
        today_str = datetime.now().strftime("%d-%m-%Y")
        expected_folder_name = f"kho-van-thuc-pham-hoang-gia-{today_str}"
        self.assertEqual(result.output_path.parent.name, expected_folder_name)
        # Tên file phải là tik_final_01.mp4
        self.assertEqual(result.output_path.name, "tik_final_01.mp4")

    def test_14_render_plan_with_visual_transitions(self):
        """Xác minh render với visual xfade transition (wipeleft, slideleft, fallback invalid)."""
        plan_id = "test_visual_transitions_01"
        plan = VideoRenderPlan(
            plan_id=plan_id,
            title="Test Visual Transitions",
            scenes=[
                ScenePlan(
                    scene_index=0,
                    content="Scene 1",
                    audio_path=self.test_audio_path,
                    transition="wipeleft",
                ),
                ScenePlan(
                    scene_index=1,
                    content="Scene 2",
                    audio_path=self.test_audio_path,
                    transition="invalid_effect_fallback_fade",
                ),
                ScenePlan(
                    scene_index=2,
                    content="Scene 3",
                    audio_path=self.test_audio_path,
                    transition="slideleft",
                ),
            ],
            output_filename="test_visual_trans.mp4",
        )
        config = VideoRenderConfig(
            width=540,
            height=960,
            fps=24,
            output_dir=TEST_OUTPUT_DIR,
            temp_dir=TEST_TMP_DIR,
            enable_transition=True,
            transition_duration=0.3,
            enable_bgm=False,
            enable_transition_sound=True,
            transition_sound_dir=self.test_sfx_dir,
        )
        engine = VideoRenderEngine(renderer=self.renderer, config=config)
        result = engine.render_plan(source_folder=SAMPLES_DIR, plan=plan)

        self.assertTrue(result.output_path.exists())
        self.assertEqual(result.metadata.get("visual_transition_count"), 2)
        # 3 cảnh x 1.5s = 4.5s
        self.assertAlmostEqual(result.duration, 4.5, delta=0.3)

    def test_15_render_plan_with_visual_transitions_disabled(self):
        """Xác minh khi enable_transition=False, hệ thống dùng Concat Demuxer và visual_transition_count=0."""
        plan_id = "test_visual_transitions_disabled"
        plan = VideoRenderPlan(
            plan_id=plan_id,
            title="Test Visual Transitions Disabled",
            scenes=[
                ScenePlan(
                    scene_index=0,
                    content="Scene 1",
                    audio_path=self.test_audio_path,
                    transition="wipeleft",
                ),
                ScenePlan(
                    scene_index=1,
                    content="Scene 2",
                    audio_path=self.test_audio_path,
                ),
            ],
            output_filename="test_trans_off.mp4",
        )
        config = VideoRenderConfig(
            width=540,
            height=960,
            fps=24,
            output_dir=TEST_OUTPUT_DIR,
            temp_dir=TEST_TMP_DIR,
            enable_transition=False,
            enable_bgm=False,
            enable_transition_sound=False,
        )
        engine = VideoRenderEngine(renderer=self.renderer, config=config)
        result = engine.render_plan(source_folder=SAMPLES_DIR, plan=plan)

        self.assertTrue(result.output_path.exists())
        self.assertEqual(result.metadata.get("visual_transition_count"), 0)
        self.assertAlmostEqual(result.duration, 3.0, delta=0.3)


if __name__ == "__main__":
    unittest.main()



