"""Unit tests for Video Render Engine (In-Memory Logging & Concurrency)."""

from pathlib import Path
import time
import unittest

from app.services.video_render_engine import (
    AntiReupEngine,
    AntiReupProfile,
    BaseVideoRenderer,
    InvalidPlanError,
    RendererNotProvidedError,
    RenderExecutionError,
    RenderResult,
    ScenePlan,
    SourceFolderNotFoundError,
    TaskLogger,
    VideoRenderConfig,
    VideoRenderEngine,
    VideoRenderPlan,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = PROJECT_ROOT / "assets" / "samples" / "company_media"
TEST_RUNS_DIR = PROJECT_ROOT / "storage" / "temp" / "test_engine_abstract"


class MockSuccessRenderer(BaseVideoRenderer):
    """Mock renderer for testing successful render cycles."""

    def __init__(self, delay: float = 0.05):
        self.delay = delay

    @property
    def renderer_name(self) -> str:
        return "MockSuccessRenderer"

    def validate_environment(self) -> bool:
        return True

    def render_plan(
        self,
        plan: VideoRenderPlan,
        source_folder: Path,
        config: VideoRenderConfig,
        profile: AntiReupProfile,
        task_logger: TaskLogger,
    ) -> RenderResult:
        task_logger.info(f"Mocking render for {plan.plan_id}")
        time.sleep(self.delay)
        out_file = config.output_dir / f"{plan.plan_id}.mp4"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text("dummy video")

        return RenderResult(
            plan_id=plan.plan_id,
            output_path=out_file,
            duration=5.0,
            file_size_bytes=100,
            scenes_count=len(plan.scenes),
        )


class MockFailingRenderer(BaseVideoRenderer):
    """Mock renderer that fails environment or rendering."""

    def __init__(self, fail_env: bool = False):
        self.fail_env = fail_env

    def validate_environment(self) -> bool:
        return not self.fail_env

    def render_plan(
        self,
        plan: VideoRenderPlan,
        source_folder: Path,
        config: VideoRenderConfig,
        profile: AntiReupProfile,
        task_logger: TaskLogger,
    ) -> RenderResult:
        raise RuntimeError("Simulated render crash")


class TestVideoRenderEngine(unittest.TestCase):
    """Test suite verifying abstract architecture, concurrency, and in-memory isolated logging."""

    @classmethod
    def setUpClass(cls):
        TEST_RUNS_DIR.mkdir(parents=True, exist_ok=True)

    def test_task_logger_in_memory(self):
        """Test that TaskLogger accumulates logs in memory without disk writes."""
        logger = TaskLogger(plan_id="test_plan_memory")
        logger.info("Message 1")
        logger.warning("Message 2")
        logger.error("Message 3")

        logs = logger.get_logs()
        self.assertEqual(len(logs), 3)
        self.assertIn("Message 1", logs[0])
        self.assertIn("[INFO]", logs[0])
        self.assertIn("[Plan: test_plan_memory", logs[0])

    def test_config_and_extra_params(self):
        """Test configuration defaults and extensibility via extra_params."""
        cfg = VideoRenderConfig(
            width=1080,
            height=1920,
            max_concurrent_tasks=4,
            extra_params={"ffmpeg_preset": "ultrafast", "crf": 22},
        )
        self.assertEqual(cfg.width, 1080)
        self.assertEqual(cfg.max_concurrent_tasks, 4)
        self.assertEqual(cfg.extra_params["ffmpeg_preset"], "ultrafast")

    def test_anti_reup_engine(self):
        """Test AntiReupEngine dynamic rules and parameter randomization."""
        engine = AntiReupEngine()

        # Thêm các quy tắc random tùy chỉnh
        engine.set_rule("rotation_angle", (-2.0, 2.0))
        engine.set_rule("filter_mode", ["warm", "cool", "vintage"])
        engine.set_rule("gamma", lambda rng: round(rng.uniform(0.9, 1.1), 3))

        profile = engine.randomize()

        # Kiểm tra truy cập động qua attribute và dict
        self.assertIn("rotation_angle", profile)
        self.assertIn("filter_mode", profile)
        self.assertIn("gamma", profile)
        self.assertIn("metadata_uuid", profile)

        self.assertGreaterEqual(profile.rotation_angle, -2.0)
        self.assertLessEqual(profile.rotation_angle, 2.0)
        self.assertIn(profile.filter_mode, ["warm", "cool", "vintage"])
        self.assertGreaterEqual(profile.gamma, 0.9)
        self.assertLessEqual(profile.gamma, 1.1)

        # Test dictionary-like access
        self.assertEqual(profile["filter_mode"], profile.filter_mode)
        self.assertIsNotNone(profile.get("metadata_date"))

    def test_base_renderer_contract(self):
        """Test that subclasses must implement abstract methods."""
        class IncompleteRenderer(BaseVideoRenderer):
            pass

        with self.assertRaises(TypeError):
            IncompleteRenderer()

    def test_engine_validations(self):
        """Test validation of missing renderer, invalid source folder, and empty plans."""
        # 1. No renderer
        engine_no_renderer = VideoRenderEngine()
        dummy_plan = VideoRenderPlan(
            plan_id="p1",
            scenes=[ScenePlan(scene_index=0, content="s1")],
        )
        with self.assertRaises(RendererNotProvidedError):
            engine_no_renderer.render_plan(SAMPLES_DIR, dummy_plan)

        # 2. Non-existent source folder
        engine = VideoRenderEngine(renderer=MockSuccessRenderer())
        with self.assertRaises(SourceFolderNotFoundError):
            engine.render_plan(Path("/non/existent/path/here"), dummy_plan)

        # 3. Plan with empty scenes
        empty_plan = VideoRenderPlan.model_construct(plan_id="empty", scenes=[])
        with self.assertRaises(InvalidPlanError):
            engine.render_plan(SAMPLES_DIR, empty_plan)

        # 4. Renderer environment not ready
        engine_fail_env = VideoRenderEngine(renderer=MockFailingRenderer(fail_env=True))
        with self.assertRaises(RenderExecutionError):
            engine_fail_env.render_plan(SAMPLES_DIR, dummy_plan)

    def test_single_render_and_in_memory_logs(self):
        """Test single plan execution and verify in-memory logs collection."""
        config = VideoRenderConfig(output_dir=TEST_RUNS_DIR)
        renderer = MockSuccessRenderer()
        engine = VideoRenderEngine(renderer=renderer, config=config)

        plan = VideoRenderPlan(
            plan_id="test_single_mem",
            title="Single Test Video",
            scenes=[
                ScenePlan(scene_index=0, content="Scene 1"),
            ],
        )

        result = engine.render_plan(source_folder=SAMPLES_DIR, plan=plan)

        self.assertEqual(result.plan_id, "test_single_mem")
        self.assertTrue(result.output_path.exists())
        self.assertIsInstance(result.logs, list)
        self.assertGreater(len(result.logs), 0)

        # Verify log lines in memory
        combined_text = "\n".join(result.logs)
        self.assertIn("Bắt đầu render video: 'Single Test Video'", combined_text)
        self.assertIn("Mocking render for test_single_mem", combined_text)
        self.assertIn("Hoàn thành render plan 'test_single_mem'", combined_text)

    def test_concurrent_batch_render_with_isolated_memory_logs(self):
        """Test multi-threaded parallel batch execution and isolated in-memory logs."""
        config = VideoRenderConfig(
            output_dir=TEST_RUNS_DIR,
            max_concurrent_tasks=3,
        )
        renderer = MockSuccessRenderer(delay=0.08)
        engine = VideoRenderEngine(renderer=renderer, config=config)

        plans = [
            VideoRenderPlan(plan_id=f"concurrent_mem_{i}", scenes=[ScenePlan(scene_index=0, content=f"C{i}")])
            for i in range(3)
        ]

        batch_result = engine.render_batch(
            source_folder=SAMPLES_DIR,
            plans=plans,
            max_workers=3,
        )

        self.assertEqual(batch_result.total_plans, 3)
        self.assertEqual(batch_result.successful_renders, 3)
        self.assertEqual(batch_result.failed_renders, 0)

        # Check each result has its own isolated logs
        for res in batch_result.results:
            self.assertGreater(len(res.logs), 0)
            for log_line in res.logs:
                # All logs in this result belong ONLY to this plan
                self.assertIn(f"Plan: {res.plan_id}", log_line)

    def test_voice_clone_selector_empty_and_single(self):
        """Kiểm thử VoiceCloneSelector với thư mục rỗng và thư mục có 1 voice."""
        from app.services.video_render_engine.voice_manager import (
            VoiceCloneSelector,
            allocate_voices_for_plans,
            get_available_voices,
            pick_random_voice,
        )

        empty_dir = TEST_RUNS_DIR / "empty_voices"
        empty_dir.mkdir(parents=True, exist_ok=True)

        # Thư mục rỗng
        self.assertEqual(get_available_voices(empty_dir), [])
        self.assertIsNone(pick_random_voice(empty_dir))
        self.assertEqual(allocate_voices_for_plans(3, voices_dir=empty_dir), [None, None, None])

        # Thư mục có 1 voice
        single_dir = TEST_RUNS_DIR / "single_voice"
        single_dir.mkdir(parents=True, exist_ok=True)
        v1 = single_dir / "voice_01.wav"
        v1.write_bytes(b"dummy wav")

        avail = get_available_voices(single_dir)
        self.assertEqual(len(avail), 1)
        self.assertEqual(avail[0].name, "voice_01.wav")

        picked = pick_random_voice(single_dir)
        self.assertEqual(picked.name, "voice_01.wav")

        alloc = allocate_voices_for_plans(4, voices_dir=single_dir)
        self.assertEqual(len(alloc), 4)
        for a in alloc:
            self.assertEqual(a.name, "voice_01.wav")

    def test_voice_clone_selector_multiple_and_cyclic_allocation(self):
        """Kiểm thử VoiceCloneSelector với nhiều voice và thuật toán cyclic-shuffle."""
        from app.services.video_render_engine.voice_manager import (
            VoiceCloneSelector,
            allocate_voices_for_plans,
        )

        multi_dir = TEST_RUNS_DIR / "multi_voices"
        multi_dir.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            (multi_dir / f"voice_{i:02d}.wav").write_bytes(b"wav")

        selector = VoiceCloneSelector(voices_dir=multi_dir)
        self.assertEqual(len(selector.available_voices), 3)

        # Phân bổ cho 6 plans với seed cố định
        alloc = selector.allocate(plan_count=6, seed=42)
        self.assertEqual(len(alloc), 6)
        # Đảm bảo cả 3 voice đều xuất hiện
        names = {v.name for v in alloc}
        self.assertEqual(names, {"voice_00.wav", "voice_01.wav", "voice_02.wav"})

    def test_render_plan_with_voice_clone_path_metadata(self):
        """Kiểm thử VideoRenderPlan kèm voice_clone_path được ghi vào logs và metadata."""
        config = VideoRenderConfig(output_dir=TEST_RUNS_DIR)
        renderer = MockSuccessRenderer()
        engine = VideoRenderEngine(renderer=renderer, config=config)

        mock_voice = TEST_RUNS_DIR / "sample_voice.wav"
        mock_voice.write_bytes(b"sample wav")

        plan = VideoRenderPlan(
            plan_id="test_voice_plan",
            title="Voice Plan Video",
            scenes=[ScenePlan(scene_index=0, content="Content with voice")],
            voice_clone_path=mock_voice,
        )

        result = engine.render_plan(source_folder=SAMPLES_DIR, plan=plan)
        self.assertEqual(result.metadata.get("voice_clone_path"), str(mock_voice))
        self.assertEqual(result.metadata.get("voice_clone_name"), "sample_voice.wav")

        # Kiểm tra in-memory log
        combined_logs = "\n".join(result.logs)
        self.assertIn("Voice Clone: 'sample_voice.wav'", combined_logs)

    def test_bgm_manager_get_available_bgm(self):
        """Kiểm thử quét danh sách BGM hợp lệ từ assets/sounds/bgm."""
        from app.services.video_render_engine.bgm_manager import BGMSelector, get_available_bgm

        # 1. Quét thư mục mặc định assets/sounds/bgm
        bgms = get_available_bgm()
        self.assertGreater(len(bgms), 0)
        for bgm in bgms:
            self.assertTrue(bgm.exists())
            self.assertIn(bgm.suffix.lower(), {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"})

        # 2. Quét thư mục tạm giả lập
        temp_bgm_dir = TEST_RUNS_DIR / "temp_bgm"
        temp_bgm_dir.mkdir(parents=True, exist_ok=True)
        (temp_bgm_dir / "track_01.wav").write_bytes(b"bgm1")
        (temp_bgm_dir / "track_02.mp3").write_bytes(b"bgm2")
        (temp_bgm_dir / "ignored.txt").write_text("text")

        selector = BGMSelector(bgm_dir=temp_bgm_dir)
        self.assertEqual(len(selector.available_bgm), 2)
        names = [f.name for f in selector.available_bgm]
        self.assertEqual(names, ["track_01.wav", "track_02.mp3"])

    def test_bgm_manager_pick_random_bgm(self):
        """Kiểm thử chọn ngẫu nhiên BGM có hỗ trợ seed tái lập."""
        from app.services.video_render_engine.bgm_manager import pick_random_bgm

        temp_bgm_dir = TEST_RUNS_DIR / "temp_bgm_pick"
        temp_bgm_dir.mkdir(parents=True, exist_ok=True)
        (temp_bgm_dir / "bgm_a.wav").write_bytes(b"a")
        (temp_bgm_dir / "bgm_b.wav").write_bytes(b"b")

        pick1 = pick_random_bgm(bgm_dir=temp_bgm_dir, seed=123)
        pick2 = pick_random_bgm(bgm_dir=temp_bgm_dir, seed=123)
        self.assertIsNotNone(pick1)
        self.assertEqual(pick1, pick2)

    def test_bgm_manager_allocate_cyclic_shuffle(self):
        """Kiểm thử phân bổ BGM cho danh sách N plans bằng Cyclic-Shuffle."""
        from app.services.video_render_engine.bgm_manager import BGMSelector

        multi_dir = TEST_RUNS_DIR / "multi_bgm"
        multi_dir.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            (multi_dir / f"bgm_{i:02d}.wav").write_bytes(b"wav")

        selector = BGMSelector(bgm_dir=multi_dir)
        self.assertEqual(len(selector.available_bgm), 3)

        # Phân bổ cho 6 plans với seed cố định
        alloc = selector.allocate(plan_count=6, seed=42)
        self.assertEqual(len(alloc), 6)
        # Đảm bảo cả 3 track đều xuất hiện
        names = {b.name for b in alloc}
        self.assertEqual(names, {"bgm_00.wav", "bgm_01.wav", "bgm_02.wav"})

    def test_bgm_manager_empty_fallback(self):
        """Kiểm thử fallback khi thư mục BGM rỗng hoặc không tồn tại."""
        from app.services.video_render_engine.bgm_manager import allocate_bgm_for_plans, pick_random_bgm

        empty_dir = TEST_RUNS_DIR / "empty_bgm_dir"
        empty_dir.mkdir(parents=True, exist_ok=True)

        self.assertIsNone(pick_random_bgm(bgm_dir=empty_dir))
        alloc = allocate_bgm_for_plans(plan_count=3, bgm_dir=empty_dir)
        self.assertEqual(alloc, [None, None, None])

    def test_render_plan_with_bgm_path_and_volume_10_percent(self):
        """Kiểm thử VideoRenderPlan kèm bgm_path và bgm_volume=0.10 được ghi vào logs và metadata."""
        config = VideoRenderConfig(output_dir=TEST_RUNS_DIR)
        renderer = MockSuccessRenderer()
        engine = VideoRenderEngine(renderer=renderer, config=config)

        mock_bgm = TEST_RUNS_DIR / "sample_bgm.wav"
        mock_bgm.write_bytes(b"sample bgm wav")

        plan = VideoRenderPlan(
            plan_id="test_bgm_plan",
            title="BGM Plan Video",
            scenes=[ScenePlan(scene_index=0, content="Content with BGM")],
            bgm_path=mock_bgm,
            bgm_volume=0.10,
        )

        result = engine.render_plan(source_folder=SAMPLES_DIR, plan=plan)
        self.assertEqual(result.metadata.get("bgm_path"), str(mock_bgm))
        self.assertEqual(result.metadata.get("bgm_name"), "sample_bgm.wav")
        self.assertEqual(result.metadata.get("bgm_volume"), 0.10)

        # Kiểm tra in-memory log
        combined_logs = "\n".join(result.logs)
        self.assertIn("Nhạc nền BGM: 'sample_bgm.wav' (Âm lượng: 10%", combined_logs)


if __name__ == "__main__":
    unittest.main()

