"""Unit and integration tests for the 6-step Video Creation Pipeline."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app.services.pipeline import (
    PipelineInput,
    PipelineResult,
    RoughScene,
    RoughScript,
    StepValidationError,
    VideoCreationPipeline,
)
from app.services.render_overlay_engine.styles import BubbleCloudStyle, TornPaperStyle
from app.services.video_render_engine.models import RenderResult, ScenePlan, VideoRenderPlan


class TestVideoCreationPipeline(unittest.TestCase):
    """Kiểm thử chuyên sâu cho từng bước và toàn bộ luồng 6 bước của VideoCreationPipeline."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_temp = Path(self.temp_dir.name)

        # Tạo thư mục b-roll giả lập có file video hợp lệ
        self.mock_source_folder = self.root_temp / "source_media"
        self.mock_source_folder.mkdir(parents=True)
        (self.mock_source_folder / "clip_01.mp4").write_bytes(b"dummy video data")
        (self.mock_source_folder / "image_01.jpg").write_bytes(b"dummy image data")

        self.mock_output_dir = self.root_temp / "outputs"
        self.mock_output_dir.mkdir(parents=True)

        # Mock các engine phụ thuộc
        self.mock_extractor = MagicMock()
        self.mock_plan_creator = MagicMock()
        self.mock_overlay_engine = MagicMock()
        self.mock_tts_engine = MagicMock()
        self.mock_video_render_engine = MagicMock()

        self.mock_temp_dir = self.root_temp / "temp"
        self.mock_temp_dir.mkdir(parents=True)
        self.patcher_temp = patch("app.services.pipeline.coordinator.TEMP_DIR", self.mock_temp_dir)
        self.patcher_temp.start()

        self.pipeline = VideoCreationPipeline(
            content_extractor=self.mock_extractor,
            plan_creator=self.mock_plan_creator,
            render_overlay_engine=self.mock_overlay_engine,
            tts_engine=self.mock_tts_engine,
            video_render_engine=self.mock_video_render_engine,
        )

        self.sample_content = (
            "Tuyển Kỹ sư AI Generative tại TP.HCM. Lương 30-40 triệu/tháng. "
            "MacBook Pro M3 Max, hỗ trợ remote 2 ngày/tuần. Gửi CV về hr@ai.vn"
        )

    def tearDown(self):
        self.patcher_temp.stop()
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # TEST BƯỚC 1: INPUT VALIDATION
    # -------------------------------------------------------------------------
    def test_step_1_validate_inputs_success(self):
        """Thẩm định thành công khi đầy đủ content, thư mục media và API keys."""
        inp = PipelineInput(
            content=self.sample_content,
            video_source_path=self.mock_source_folder,
            num_videos=1,
            api_keys=["AIzaSyFakeKey123"],
            output_dir=self.mock_output_dir,
        )

        res = self.pipeline.step_1_validate_inputs(inp)
        self.assertIn("session_id", res)
        self.assertIn("session_dir", res)
        self.assertTrue(res["session_dir"].exists())
        self.assertEqual(res["media_files_count"], 2)
        self.assertEqual(res["api_keys"], ["AIzaSyFakeKey123"])

    def test_step_1_validate_inputs_missing_keys(self):
        """Báo lỗi khi không có API key nào trong input lẫn env."""
        inp = PipelineInput(
            content=self.sample_content,
            video_source_path=self.mock_source_folder,
            num_videos=1,
            api_keys=[],
            output_dir=self.mock_output_dir,
        )
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(StepValidationError):
                self.pipeline.step_1_validate_inputs(inp)

    def test_step_1_validate_inputs_empty_media_folder(self):
        """Báo lỗi khi thư mục video_source_path không có file media nào."""
        empty_folder = self.root_temp / "empty_folder"
        empty_folder.mkdir()

        inp = PipelineInput(
            content=self.sample_content,
            video_source_path=empty_folder,
            num_videos=1,
            api_keys=["AIzaSyFakeKey"],
            output_dir=self.mock_output_dir,
        )
        with self.assertRaises(StepValidationError):
            self.pipeline.step_1_validate_inputs(inp)

    # -------------------------------------------------------------------------
    # TEST BƯỚC 2: CONTENT EXTRACTION
    # -------------------------------------------------------------------------
    def test_step_2_extract_content(self):
        """Trích xuất thông tin có cấu trúc qua ContentExtractorEngine."""
        mock_extracted = {
            "job_title": "Kỹ sư AI Generative",
            "company_name": "Tech Company",
            "salary_range": "30-40 triệu",
            "top_benefits": ["MacBook Pro M3 Max", "Remote 2 ngày"],
        }
        self.mock_extractor.extract.return_value = mock_extracted

        data = self.pipeline.step_2_extract_content(
            content=self.sample_content,
            api_keys=["AIzaSyFakeKey"],
        )
        self.assertEqual(data["job_title"], "Kỹ sư AI Generative")
        self.assertEqual(len(data["top_benefits"]), 2)
        self.mock_extractor.extract.assert_called_once()

    # -------------------------------------------------------------------------
    # TEST BƯỚC 3: ROUGH SCRIPT CREATION
    # -------------------------------------------------------------------------
    def test_step_3_create_rough_scripts(self):
        """Lên kịch bản thô với các scene và thoại."""
        self.mock_plan_creator.create_plans.return_value = {
            "total_scripts": 1,
            "scripts": [
                {
                    "script_id": 1,
                    "title": "Deal Khủng Kỹ Sư AI",
                    "angle_and_style": "Flex đãi ngộ",
                    "hook_text": "30 triệu và MacBook M3 Max?",
                    "scenes": [
                        {
                            "scene_index": 0,
                            "visual_description": "Cận cảnh laptop",
                            "voiceover_text": "Mức lương 30-40 củ khoai cực xịn",
                            "screen_text": "LƯƠNG 30-40 TRIỆU",
                            "subcontent": "MacBook Pro M3 Max",
                            "estimated_duration_seconds": 4.5,
                        },
                        {
                            "scene_index": 1,
                            "visual_description": "Không gian văn phòng",
                            "voiceover_text": "Apply ngay hôm nay bạn nhé",
                            "screen_text": "ỨNG TUYỂN NGAY",
                            "subcontent": "hr@ai.vn",
                            "estimated_duration_seconds": 3.0,
                        },
                    ],
                }
            ],
        }

        scripts = self.pipeline.step_3_create_rough_scripts(
            extracted_content={"job_title": "AI Dev"},
            num_videos=1,
            api_keys=["AIzaSyFakeKey"],
        )
        self.assertEqual(len(scripts), 1)
        self.assertEqual(scripts[0].title, "Deal Khủng Kỹ Sư AI")
        self.assertEqual(len(scripts[0].scenes), 2)
        self.assertEqual(scripts[0].scenes[0].title, "LƯƠNG 30-40 TRIỆU")
        self.assertEqual(scripts[0].scenes[0].sub_title, "MacBook Pro M3 Max")
        self.assertEqual(scripts[0].scenes[0].srt_script, "Mức lương 30-40 củ khoai cực xịn")

    # -------------------------------------------------------------------------
    # TEST BƯỚC 4: RENDER ASSETS (OVERLAY & AUDIO)
    # -------------------------------------------------------------------------
    def test_step_4_render_assets(self):
        """Render overlay PNG và audio TTS WAV cho từng scene."""
        session_dir = self.root_temp / "session_test"
        session_dir.mkdir()

        # Tạo dummy files khi render() và synthesize() được gọi
        def mock_render(content, output_path, **kwargs):
            Path(output_path).write_bytes(b"dummy png content")
            return Path(output_path)

        def mock_synthesize(text, output_path, **kwargs):
            Path(output_path).write_bytes(b"dummy wav content")
            return Path(output_path)

        self.mock_overlay_engine.render.side_effect = mock_render
        self.mock_tts_engine.synthesize.side_effect = mock_synthesize

        rough_scripts = [
            RoughScript(
                script_id="1",
                title="Test Video",
                scenes=[
                    RoughScene(
                        scene_index=0,
                        title="TIÊU ĐỀ 1",
                        sub_title="Sub 1",
                        srt_script="Giọng đọc phụ đề cảnh 1",
                    ),
                    RoughScene(
                        scene_index=1,
                        title="TIÊU ĐỀ 2",
                        sub_title=None,
                        srt_script="Giọng đọc phụ đề cảnh 2",
                    ),
                ],
            )
        ]

        with patch.object(self.pipeline, "_measure_audio_duration", return_value=4.2):
            assets = self.pipeline.step_4_render_assets(
                rough_scripts=rough_scripts,
                session_dir=session_dir,
                overlay_style="bubble_cloud",
            )

        self.assertIn("1", assets)
        self.assertIn(0, assets["1"])
        self.assertIn(1, assets["1"])
        self.assertTrue(assets["1"][0]["overlay_path"].exists())
        self.assertTrue(assets["1"][0]["audio_path"].exists())
        self.assertEqual(assets["1"][0]["duration"], 4.2)
        # Đảm bảo metadata font và palette được lưu trữ
        self.assertIn("_overlay_font", assets["1"])
        self.assertIn("_overlay_palette", assets["1"])

    def test_step_4_render_assets_with_none_voice_id(self):
        """Kiểm tra step_4_render_assets xử lý an toàn khi voice_id=None (chế độ config mặc định)."""
        session_dir = self.root_temp / "session_test_none_voice"
        session_dir.mkdir()

        def mock_render(content, output_path, **kwargs):
            Path(output_path).write_bytes(b"dummy png content")
            return Path(output_path)

        def mock_synthesize(text, output_path, **kwargs):
            Path(output_path).write_bytes(b"dummy wav content")
            return Path(output_path)

        self.mock_overlay_engine.render.side_effect = mock_render
        self.mock_tts_engine.synthesize.side_effect = mock_synthesize

        rough_scripts = [
            RoughScript(
                script_id="test_none_voice",
                title="Tiêu đề test voice None",
                scenes=[
                    RoughScene(
                        scene_index=0,
                        title="Cảnh 0 test",
                        sub_title="Nội dung kiểm tra voice None",
                        srt_script="Lời thoại kiểm tra giọng đọc None",
                    )
                ],
            )
        ]

        with patch.object(self.pipeline, "_measure_audio_duration", return_value=3.5):
            # Truyền rõ voice_id=None để mô phỏng chính xác lỗi thực tế từ config.json
            assets = self.pipeline.step_4_render_assets(
                rough_scripts=rough_scripts,
                session_dir=session_dir,
                voice_id=None,
                randomize_voice_clone=False,
            )

        self.assertIn("test_none_voice", assets)
        self.assertIn(0, assets["test_none_voice"])
        self.assertTrue(assets["test_none_voice"][0]["audio_path"].exists())
        # Đảm bảo fallback voice=Minh Đức được truyền vào synthesize
        called_kwargs = self.mock_tts_engine.synthesize.call_args.kwargs
        self.assertEqual(called_kwargs.get("voice"), "Minh Đức")

    def test_step_4_overlay_font_and_palette_consistency(self):
        """Kiểm tra tất cả các phân cảnh trong cùng kịch bản dùng chung font và palette."""
        session_dir = self.root_temp / "session_test_consistency"
        session_dir.mkdir()

        called_tasks = []

        def mock_render(content, output_path, **kwargs):
            Path(output_path).write_bytes(b"dummy png")
            called_tasks.append(kwargs)
            return Path(output_path)

        def mock_synthesize(text, output_path, **kwargs):
            Path(output_path).write_bytes(b"dummy wav")
            return Path(output_path)

        self.mock_overlay_engine.render.side_effect = mock_render
        self.mock_tts_engine.synthesize.side_effect = mock_synthesize

        rough_scripts = [
            RoughScript(
                script_id="1",
                title="Consistency Test Video",
                scenes=[
                    RoughScene(scene_index=0, title="CẢNH 1", srt_script="Lời thoại 1"),
                    RoughScene(scene_index=1, title="CẢNH 2", srt_script="Lời thoại 2"),
                    RoughScene(scene_index=2, title="CẢNH 3", srt_script="Lời thoại 3"),
                ],
            )
        ]

        with patch.object(self.pipeline, "_measure_audio_duration", return_value=3.0):
            # 1. Kiểm tra khi không truyền custom overlay_font/palette: Hệ thống tự random 1 lần và dùng chung
            assets = self.pipeline.step_4_render_assets(
                rough_scripts=rough_scripts,
                session_dir=session_dir,
                overlay_style="bubble_cloud",
            )

        self.assertEqual(len(called_tasks), 3)
        # Font và Palette của 3 scenes phải giống hệt nhau
        s0_font = called_tasks[0].get("font")
        s0_palette = called_tasks[0].get("palette")
        self.assertIsNotNone(s0_font)
        self.assertIsNotNone(s0_palette)

        for i, task in enumerate(called_tasks):
            self.assertEqual(task.get("font"), s0_font, f"Scene {i} bị đổi font khác Scene 0!")
            self.assertEqual(task.get("palette"), s0_palette, f"Scene {i} bị đổi palette khác Scene 0!")

        # 2. Kiểm tra khi truyền chỉ định overlay_font và overlay_palette cụ thể
        called_tasks.clear()
        custom_font = "Montserrat"
        custom_palette = "retro_sunset_70s"

        with patch.object(self.pipeline, "_measure_audio_duration", return_value=3.0):
            assets_custom = self.pipeline.step_4_render_assets(
                rough_scripts=rough_scripts,
                session_dir=session_dir,
                overlay_style="retro_groovy",
                overlay_font=custom_font,
                overlay_palette=custom_palette,
            )

        self.assertEqual(len(called_tasks), 3)
        for i, task in enumerate(called_tasks):
            self.assertEqual(task.get("font"), custom_font)
            self.assertEqual(task.get("palette"), custom_palette)

        self.assertEqual(assets_custom["1"]["_overlay_font"], custom_font)
        self.assertEqual(assets_custom["1"]["_overlay_palette"], custom_palette)

    # -------------------------------------------------------------------------
    # TEST BƯỚC 5: DETAILED PLANS
    # -------------------------------------------------------------------------
    def test_step_5_build_detailed_plans(self):
        """Lắp ráp VideoRenderPlan hoàn chỉnh có overlay_path, audio_path, duration."""
        session_dir = self.root_temp / "session_test_5"
        session_dir.mkdir()

        ovl_path = session_dir / "overlay_0.png"
        ovl_path.write_bytes(b"png")
        aud_path = session_dir / "audio_0.wav"
        aud_path.write_bytes(b"wav")

        rough_scripts = [
            RoughScript(
                script_id="vid_1",
                title="Video Tuyển Dụng #1",
                scenes=[
                    RoughScene(
                        scene_index=0,
                        title="LƯƠNG 30 TRIỆU",
                        sub_title="Remote 2 ngày",
                        srt_script="Lương 30 triệu làm từ xa",
                    )
                ],
            )
        ]

        rendered_assets = {
            "vid_1": {
                0: {
                    "overlay_path": ovl_path,
                    "audio_path": aud_path,
                    "duration": 5.4,
                }
            }
        }

        detailed_plans = self.pipeline.step_5_build_detailed_plans(
            rough_scripts=rough_scripts,
            rendered_assets=rendered_assets,
            bgm_path=None,
            session_dir=session_dir,
        )

        self.assertEqual(len(detailed_plans), 1)
        plan = detailed_plans[0]
        self.assertEqual(plan.plan_id, "vid_1")
        self.assertEqual(len(plan.scenes), 1)
        self.assertEqual(plan.scenes[0].overlay_image_path, ovl_path)
        self.assertEqual(plan.scenes[0].audio_path, aud_path)
        self.assertEqual(plan.scenes[0].metadata["duration"], 5.4)

        # Kiểm tra file JSON kịch bản chi tiết đã được ghi ra đĩa
        plan_json = session_dir / "plans" / "detailed_plan_vid_1.json"
        self.assertTrue(plan_json.exists())
        with open(plan_json, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(data["plan_id"], "vid_1")

    def test_step_4_and_5_with_sound_effects(self):
        """Kiểm tra tích hợp thẻ sound effect [sound-effect:<tên file>] ở Bước 4 và Bước 5."""
        session_dir = self.root_temp / "session_test_sfx"
        session_dir.mkdir()

        sfx_file = session_dir / "Ting - Quyền lợi hấp dẫn.mp3"
        sfx_file.write_bytes(b"dummy_mp3")

        rough_scripts = [
            RoughScript(
                script_id="sfx_script",
                title="Video Có Hiệu Ứng Âm Thanh",
                scenes=[
                    RoughScene(
                        scene_index=0,
                        title="ĐÃI NGỘ CAO",
                        sub_title="Thưởng nóng 2 triệu",
                        srt_script="Đãi ngộ bao ăn ở máy lạnh cực đã nha! [sound-effect:Ting - Quyền lợi hấp dẫn.mp3]",
                    )
                ],
            )
        ]

        with patch("app.services.pipeline.coordinator.find_sound_effect_file", return_value=sfx_file) as mock_find, \
             patch("app.services.pipeline.coordinator.concatenate_tts_and_effect_audio") as mock_concat, \
             patch.object(self.pipeline, "_measure_audio_duration", return_value=6.5):

            assets = self.pipeline.step_4_render_assets(
                rough_scripts=rough_scripts,
                session_dir=session_dir,
                overlay_style="bubble_cloud",
            )

            mock_find.assert_called_once_with("Ting - Quyền lợi hấp dẫn.mp3")
            mock_concat.assert_called_once()
            # Kiểm tra text truyền vào TTS đã được loại bỏ thẻ sound-effect
            tts_call_kwargs = self.pipeline.tts_engine.synthesize.call_args.kwargs
            self.assertEqual(tts_call_kwargs["text"], "Đãi ngộ bao ăn ở máy lạnh cực đã nha!")
            self.assertEqual(assets["sfx_script"][0]["sound_effect"], "Ting - Quyền lợi hấp dẫn.mp3")
            self.assertEqual(assets["sfx_script"][0]["duration"], 6.5)

            # Kiểm tra bước 5 nhận diện đúng sound_effect trong metadata
            plans = self.pipeline.step_5_build_detailed_plans(
                rough_scripts=rough_scripts,
                rendered_assets=assets,
                bgm_path=None,
                session_dir=session_dir,
            )
            self.assertEqual(plans[0].scenes[0].metadata["sound_effect"], "Ting - Quyền lợi hấp dẫn.mp3")
            self.assertEqual(plans[0].scenes[0].metadata["duration"], 6.5)

    # -------------------------------------------------------------------------
    # TEST BƯỚC 6: RENDER VIDEO
    # -------------------------------------------------------------------------
    def test_step_6_render_videos(self):
        """Render video qua VideoRenderEngine."""
        out_mp4 = self.mock_output_dir / "final_video.mp4"
        out_mp4.write_bytes(b"video mp4")

        mock_render_result = RenderResult(
            plan_id="plan_1",
            output_path=out_mp4,
            duration=15.0,
            file_size_bytes=1024 * 1024 * 5,
            render_time_seconds=2.5,
            scenes_count=2,
        )
        self.mock_video_render_engine.render_plan.return_value = mock_render_result

        scene = ScenePlan(
            scene_index=0,
            content="Title",
            subcontent=None,
            overlay_image_path=None,
            audio_path=None,
            transition=None,
            metadata={},
        )
        plan = VideoRenderPlan(
            plan_id="plan_1",
            title="Video 1",
            scenes=[scene],
        )

        results = self.pipeline.step_6_render_videos(
            source_folder=self.mock_source_folder,
            detailed_plans=[plan],
            output_dir=self.mock_output_dir,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].output_path, out_mp4)
        self.assertEqual(results[0].duration, 15.0)

    # -------------------------------------------------------------------------
    # TEST TOÀN BỘ LUỒNG (END-TO-END EXECUTION)
    # -------------------------------------------------------------------------
    def test_execute_full_6_steps_success(self):
        """Kiểm thử chạy một mạch từ Bước 1 đến Bước 6 thành công."""
        # 1. Setup mock responses
        self.mock_extractor.extract.return_value = {
            "job_title": "AI Engineer",
            "company_name": "Antigravity Corp",
        }

        self.mock_plan_creator.create_plans.return_value = {
            "scripts": [
                {
                    "script_id": 1,
                    "title": "AI Hiring 2026",
                    "scenes": [
                        {
                            "scene_index": 0,
                            "content": "TUYỂN AI ENGINEER",
                            "subcontent": "Đãi ngộ khủng",
                        }
                    ],
                }
            ]
        }

        def mock_render(content, output_path, **kwargs):
            Path(output_path).write_bytes(b"dummy png")
            return Path(output_path)

        def mock_synthesize(text, output_path, **kwargs):
            Path(output_path).write_bytes(b"dummy wav")
            return Path(output_path)

        self.mock_overlay_engine.render.side_effect = mock_render
        self.mock_tts_engine.synthesize.side_effect = mock_synthesize

        final_mp4 = self.mock_output_dir / "final_01.mp4"
        final_mp4.write_bytes(b"mp4")
        self.mock_video_render_engine.render_plan.return_value = RenderResult(
            plan_id="1",
            output_path=final_mp4,
            duration=12.0,
            file_size_bytes=1024 * 1024,
            render_time_seconds=1.2,
            scenes_count=1,
        )

        inp = PipelineInput(
            content=self.sample_content,
            video_source_path=self.mock_source_folder,
            num_videos=1,
            api_keys=["AIzaSyFakeKey"],
            output_dir=self.mock_output_dir,
        )

        progress_events = []
        def on_progress(step, msg, data):
            progress_events.append((step, msg))

        with patch.object(self.pipeline, "_measure_audio_duration", return_value=5.0):
            result: PipelineResult = self.pipeline.execute(
                input_data=inp,
                on_progress=on_progress,
            )

        self.assertTrue(result.is_successful)
        self.assertEqual(len(result.errors), 0)
        self.assertEqual(len(result.rough_scripts), 1)
        self.assertEqual(len(result.detailed_plans), 1)
        self.assertEqual(len(result.render_results), 1)
        self.assertEqual(result.render_results[0].output_path, final_mp4)

        # Đảm bảo đã phát sự kiện qua đầy đủ 6 bước
        steps_recorded = {event[0] for event in progress_events}
        for s in range(1, 7):
            self.assertIn(s, steps_recorded, f"Thiếu sự kiện của Bước {s}")

    def test_overlay_style_resolution(self):
        """Kiểm tra việc tra cứu style từ string hoặc đối tượng."""
        style1 = self.pipeline.resolve_overlay_style("torn_paper")
        self.assertIsInstance(style1, TornPaperStyle)

        style2 = self.pipeline.resolve_overlay_style("bubble_cloud")
        self.assertIsInstance(style2, BubbleCloudStyle)

        style3 = self.pipeline.resolve_overlay_style("unknown_style")
        self.assertIsInstance(style3, BubbleCloudStyle)

        custom_style = TornPaperStyle()
        style4 = self.pipeline.resolve_overlay_style(custom_style)
        self.assertIs(style4, custom_style)

    def test_step_4_voice_seed_and_pause_duration(self):
        """Đảm bảo TTSEngine nhận đúng seed cố định và pause_duration."""
        session_dir = self.root_temp / "session_test_seed"
        session_dir.mkdir()

        def mock_render(content, output_path, **kwargs):
            Path(output_path).write_bytes(b"dummy png content")
            return Path(output_path)

        def mock_synthesize(text, output_path, **kwargs):
            Path(output_path).write_bytes(b"dummy wav content")
            return Path(output_path)

        self.mock_overlay_engine.render.side_effect = mock_render
        self.mock_tts_engine.synthesize.side_effect = mock_synthesize

        rough_scripts = [
            RoughScript(
                script_id="1",
                title="Test Video 1",
                scenes=[
                    RoughScene(scene_index=0, title="SCENE 1", srt_script="Kịch bản nói cảnh 1"),
                    RoughScene(scene_index=1, title="SCENE 2", srt_script="Kịch bản nói cảnh 2"),
                ],
            )
        ]

        with patch.object(self.pipeline, "_measure_audio_duration", return_value=4.5):
            self.pipeline.step_4_render_assets(
                rough_scripts=rough_scripts,
                session_dir=session_dir,
                scene_pause_duration=0.6,
                tts_seed=12345,
            )

        # Kiểm tra hai lần gọi TTS đều dùng pause_duration=0.6 và seed=None (do seed đã set tập trung ở script level)
        self.assertEqual(self.mock_tts_engine.synthesize.call_count, 2)
        for call in self.mock_tts_engine.synthesize.call_args_list:
            self.assertIsNone(call.kwargs.get("seed"))
            self.assertEqual(call.kwargs.get("pause_duration"), 0.6)

    def test_step_4_tts_narration_priority_with_srt_script(self):
        """Xác thực ưu tiên srt_script khi tạo giọng đọc TTS và fallback về title + sub_title."""
        session_dir = self.root_temp / "session_test_tts_priority"
        session_dir.mkdir()

        def mock_render(content, output_path, **kwargs):
            Path(output_path).write_bytes(b"dummy png content")
            return Path(output_path)

        def mock_synthesize(text, output_path, **kwargs):
            Path(output_path).write_bytes(b"dummy wav content")
            return Path(output_path)

        self.mock_overlay_engine.render.side_effect = mock_render
        self.mock_tts_engine.synthesize.side_effect = mock_synthesize

        rough_scripts = [
            RoughScript(
                script_id="priority_test",
                title="Priority Test Video",
                scenes=[
                    # Scene 0: Có srt_script riêng biệt -> TTS phải đọc srt_script
                    RoughScene(
                        scene_index=0,
                        title="TIÊU ĐỀ OVERLAY 1",
                        sub_title="Nội dung phụ 1",
                        srt_script="Lời thoại phụ đề chuyên biệt cảnh 1",
                    ),
                    # Scene 1: Không có srt_script -> TTS phải fallback đọc title + sub_title
                    RoughScene(
                        scene_index=1,
                        title="TIÊU ĐỀ OVERLAY 2",
                        sub_title="Nội dung phụ 2",
                        srt_script=None,
                    ),
                    # Scene 2: Không có srt_script và không có sub_title -> TTS đọc title
                    RoughScene(
                        scene_index=2,
                        title="TIÊU ĐỀ OVERLAY 3",
                        sub_title=None,
                        srt_script=None,
                    ),
                ],
            )
        ]

        with patch.object(self.pipeline, "_measure_audio_duration", return_value=3.0):
            self.pipeline.step_4_render_assets(
                rough_scripts=rough_scripts,
                session_dir=session_dir,
            )

        self.assertEqual(self.mock_tts_engine.synthesize.call_count, 3)
        calls = self.mock_tts_engine.synthesize.call_args_list
        # Scene 0 dùng srt_script
        self.assertEqual(calls[0].kwargs["text"], "Lời thoại phụ đề chuyên biệt cảnh 1")
        # Scene 1 fallback về title. sub_title
        self.assertEqual(calls[1].kwargs["text"], "TIÊU ĐỀ OVERLAY 2. Nội dung phụ 2")
        self.assertEqual(calls[2].kwargs["text"], "TIÊU ĐỀ OVERLAY 3")

    def test_step_4_and_5_random_voice_clone_per_plan(self):
        """Kiểm thử mỗi plan chọn ngẫu nhiên 1 voice trong thư mục voices để clone."""
        session_dir = self.root_temp / "session_voice_clone_test"
        session_dir.mkdir()

        # Tạo thư mục mock voices có 2 file
        mock_voices_dir = self.root_temp / "mock_voices"
        mock_voices_dir.mkdir()
        v_a = mock_voices_dir / "voice_alice.wav"
        v_b = mock_voices_dir / "voice_bob.wav"
        v_a.write_bytes(b"wav data a")
        v_b.write_bytes(b"wav data b")

        # Mock render overlay và synthesize audio
        self.mock_overlay_engine.render.return_value = None
        self.mock_tts_engine.synthesize.return_value = None

        rough_scripts = [
            RoughScript(
                script_id="script_1",
                title="Video 1",
                scenes=[
                    RoughScene(scene_index=0, title="Cảnh 1", srt_script="Thoại 1"),
                ],
            ),
            RoughScript(
                script_id="script_2",
                title="Video 2",
                scenes=[
                    RoughScene(scene_index=0, title="Cảnh 2", srt_script="Thoại 2"),
                ],
            ),
        ]

        with patch.object(self.pipeline, "_measure_audio_duration", return_value=4.0):
            rendered_assets = self.pipeline.step_4_render_assets(
                rough_scripts=rough_scripts,
                session_dir=session_dir,
                voices_dir=mock_voices_dir,
                randomize_voice_clone=True,
                tts_seed=123,
            )

        # Kiểm tra synthesize được gọi với 2 voice clone khác nhau
        self.assertEqual(self.mock_tts_engine.synthesize.call_count, 2)
        calls = self.mock_tts_engine.synthesize.call_args_list
        voice_1 = calls[0].kwargs.get("voice_clone_path")
        voice_2 = calls[1].kwargs.get("voice_clone_path")

        self.assertIsNotNone(voice_1)
        self.assertIsNotNone(voice_2)
        self.assertTrue(voice_1.exists())
        self.assertTrue(voice_2.exists())
        self.assertIn(voice_1.name, {"voice_alice.wav", "voice_bob.wav"})
        self.assertIn(voice_2.name, {"voice_alice.wav", "voice_bob.wav"})

        # Kiểm tra bước 5 gán voice_clone_path vào VideoRenderPlan
        detailed_plans = self.pipeline.step_5_build_detailed_plans(
            rough_scripts=rough_scripts,
            rendered_assets=rendered_assets,
            bgm_path=None,
            session_dir=session_dir,
        )

        self.assertEqual(len(detailed_plans), 2)
        self.assertEqual(detailed_plans[0].voice_clone_path, voice_1)
        self.assertEqual(detailed_plans[1].voice_clone_path, voice_2)
        self.assertEqual(detailed_plans[0].extra_data.get("voice_clone_path"), str(voice_1))
        self.assertEqual(detailed_plans[1].extra_data.get("voice_clone_path"), str(voice_2))

    def test_execute_cleanup_temp_default(self):
        """Đảm bảo mặc định cleanup_temp=True sẽ xóa sạch thư mục session_dir trong TEMP_DIR sau khi render xong."""
        from app.config import TEMP_DIR

        self.mock_extractor.extract.return_value = {"title": "Test JD", "benefits": ["Bao ăn ở"]}
        self.mock_plan_creator.create_plans.return_value = {
            "scripts": [
                {
                    "script_id": 1,
                    "title": "Test Video",
                    "scenes": [
                        {
                            "scene_index": 0,
                            "content": "Cảnh 1",
                            "subcontent": "Sub 1",
                            "srt_script": "Thoại 1",
                        }
                    ],
                }
            ]
        }
        def mock_render(content, output_path, **kwargs):
            Path(output_path).write_bytes(b"dummy png")
            return Path(output_path)

        def mock_synthesize(text, output_path, **kwargs):
            Path(output_path).write_bytes(b"dummy wav")
            return Path(output_path)

        self.mock_overlay_engine.render.side_effect = mock_render
        self.mock_tts_engine.synthesize.side_effect = mock_synthesize
        final_mp4 = self.mock_output_dir / "video_1_final.mp4"
        final_mp4.write_bytes(b"dummy final mp4")
        self.mock_video_render_engine.render_plan.return_value = RenderResult(
            plan_id="1",
            output_path=final_mp4,
            duration=5.0,
            file_size_bytes=1000,
            scenes_count=1,
        )

        inp = PipelineInput(
            content=self.sample_content,
            video_source_path=self.mock_source_folder,
            num_videos=1,
            api_keys=["AIzaSyFakeKey"],
            output_dir=self.mock_output_dir,
        )

        with patch.object(self.pipeline, "_measure_audio_duration", return_value=5.0):
            result = self.pipeline.execute(input_data=inp)

        self.assertTrue(result.is_successful)
        session_dir = self.mock_temp_dir / f"pipeline_{result.session_id}"
        self.assertFalse(session_dir.exists(), f"Thư mục session {session_dir} phải bị xóa sau khi render xong!")

    def test_execute_keep_temp_when_cleanup_false(self):
        """Khi truyền cleanup_temp=False, thư mục session_dir phải được giữ lại để phục vụ debug."""
        self.mock_extractor.extract.return_value = {"title": "Test JD", "benefits": ["Bao ăn ở"]}
        self.mock_plan_creator.create_plans.return_value = {
            "scripts": [
                {
                    "script_id": 1,
                    "title": "Test Video",
                    "scenes": [
                        {
                            "scene_index": 0,
                            "content": "Cảnh 1",
                            "subcontent": "Sub 1",
                            "srt_script": "Thoại 1",
                        }
                    ],
                }
            ]
        }
        def mock_render(content, output_path, **kwargs):
            Path(output_path).write_bytes(b"dummy png")
            return Path(output_path)

        def mock_synthesize(text, output_path, **kwargs):
            Path(output_path).write_bytes(b"dummy wav")
            return Path(output_path)

        self.mock_overlay_engine.render.side_effect = mock_render
        self.mock_tts_engine.synthesize.side_effect = mock_synthesize
        final_mp4 = self.mock_output_dir / "video_1_final.mp4"
        final_mp4.write_bytes(b"dummy final mp4")
        self.mock_video_render_engine.render_plan.return_value = RenderResult(
            plan_id="1",
            output_path=final_mp4,
            duration=5.0,
            file_size_bytes=1000,
            scenes_count=1,
        )

        inp = PipelineInput(
            content=self.sample_content,
            video_source_path=self.mock_source_folder,
            num_videos=1,
            api_keys=["AIzaSyFakeKey"],
            output_dir=self.mock_output_dir,
        )

        session_dir = None
        try:
            with patch.object(self.pipeline, "_measure_audio_duration", return_value=5.0):
                result = self.pipeline.execute(input_data=inp, cleanup_temp=False)

            self.assertTrue(result.is_successful)
            session_dir = self.mock_temp_dir / f"pipeline_{result.session_id}"
            self.assertTrue(session_dir.exists(), f"Thư mục session {session_dir} phải tồn tại khi cleanup_temp=False!")
        finally:
            if session_dir and session_dir.exists():
                import shutil
                shutil.rmtree(session_dir, ignore_errors=True)

    def test_execute_cleanup_on_error(self):
        """Khi xảy ra lỗi ở bất kỳ bước nào, session_dir vẫn phải được dọn dẹp nếu cleanup_temp=True."""
        from app.services.content_extractor import ContentExtractorError

        self.mock_extractor.extract.side_effect = ContentExtractorError("Giả lập lỗi bóc tách nội dung")

        inp = PipelineInput(
            content=self.sample_content,
            video_source_path=self.mock_source_folder,
            num_videos=1,
            api_keys=["AIzaSyFakeKey"],
            output_dir=self.mock_output_dir,
        )

        result = self.pipeline.execute(input_data=inp, cleanup_temp=True)
        self.assertFalse(result.is_successful)
        self.assertIn("Lỗi Bước 2", result.errors[0])

        session_dir = self.mock_temp_dir / f"pipeline_{result.session_id}"
        self.assertFalse(session_dir.exists(), "session_dir phải được dọn dẹp sạch khi gặp lỗi!")

    def test_cleanup_orphaned_sessions(self):
        """Kiểm tra phương thức dọn dẹp các session mồ côi cũ."""
        custom_temp = self.root_temp / "orphaned_test_dir"
        custom_temp.mkdir()

        # Tạo một số thư mục mồ côi
        dir1 = custom_temp / "pipeline_old_1"
        dir1.mkdir()
        (dir1 / "some_file.txt").write_text("junk")

        dir2 = custom_temp / "pipeline_old_2"
        dir2.mkdir()

        # Thư mục không khớp prefix
        dir_keep = custom_temp / "other_dir"
        dir_keep.mkdir()

        cleaned = VideoCreationPipeline.cleanup_orphaned_sessions(temp_dir=custom_temp)
        self.assertEqual(cleaned, 2)
        self.assertFalse(dir1.exists())
        self.assertFalse(dir2.exists())
        self.assertTrue(dir_keep.exists())

    def test_step_5_allocate_random_bgm_10_percent(self):
        """Kiểm tra Bước 5 tự động chọn ngẫu nhiên BGM từ assets/sounds/bgm với âm lượng 10%."""
        rough_scripts = [
            RoughScript(
                script_id="script_1",
                title="Kịch bản 1",
                scenes=[RoughScene(scene_index=0, title="Cảnh 1", sub_title="Sub 1", duration=3.0, srt_script="Srt 1")],
            ),
            RoughScript(
                script_id="script_2",
                title="Kịch bản 2",
                scenes=[RoughScene(scene_index=0, title="Cảnh 2", sub_title="Sub 2", duration=4.0, srt_script="Srt 2")],
            ),
        ]
        rendered_assets = {
            "script_1": {0: {"overlay_path": Path("ovl1.png"), "audio_path": Path("aud1.wav"), "duration": 3.0}},
            "script_2": {0: {"overlay_path": Path("ovl2.png"), "audio_path": Path("aud2.wav"), "duration": 4.0}},
        }
        session_dir = self.mock_temp_dir / "session_bgm_test"
        session_dir.mkdir(parents=True, exist_ok=True)

        # TH1: Tự động chọn ngẫu nhiên BGM từ thư mục mặc định (assets/sounds/bgm) với âm lượng 10%
        detailed_plans = self.pipeline.step_5_build_detailed_plans(
            rough_scripts=rough_scripts,
            rendered_assets=rendered_assets,
            bgm_path=None,
            session_dir=session_dir,
            bgm_volume=0.10,
            randomize_bgm=True,
        )

        self.assertEqual(len(detailed_plans), 2)
        for plan in detailed_plans:
            self.assertIsNotNone(plan.bgm_path)
            self.assertTrue(plan.bgm_path.exists())
            self.assertEqual(plan.bgm_volume, 0.10)
            self.assertEqual(plan.extra_data.get("bgm_volume"), 0.10)
            self.assertEqual(plan.extra_data.get("bgm_path"), str(plan.bgm_path))

        # TH2: Chỉ định 1 file BGM cụ thể
        custom_bgm = self.mock_temp_dir / "custom_bgm.wav"
        custom_bgm.write_bytes(b"custom audio data")

        fixed_plans = self.pipeline.step_5_build_detailed_plans(
            rough_scripts=rough_scripts,
            rendered_assets=rendered_assets,
            bgm_path=custom_bgm,
            session_dir=session_dir,
            bgm_volume=0.10,
        )

        self.assertEqual(len(fixed_plans), 2)
        self.assertEqual(fixed_plans[0].bgm_path, custom_bgm.resolve())
        self.assertEqual(fixed_plans[1].bgm_path, custom_bgm.resolve())
        self.assertEqual(fixed_plans[0].bgm_volume, 0.10)
        self.assertEqual(fixed_plans[1].bgm_volume, 0.10)


if __name__ == "__main__":
    unittest.main()


