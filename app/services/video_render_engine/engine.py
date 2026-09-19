"""Core Video Render Engine coordinating input validation, anti-reup generation,

in-memory thread logging, and concurrent execution via pluggable BaseVideoRenderer.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from pathlib import Path
import time
from typing import Callable, List, Optional

from app.services.video_render_engine.processors.anti_reup import AntiReupEngine
from app.services.video_render_engine.renderers.base import BaseVideoRenderer
from app.services.video_render_engine.core.config import VideoRenderConfig
from app.services.video_render_engine.core.exceptions import (
    InvalidPlanError,
    RendererNotProvidedError,
    RenderExecutionError,
    SourceFolderNotFoundError,
)
from app.services.video_render_engine.core.logger import TaskLogger
from app.services.video_render_engine.core.models import (
    RenderBatchResult,
    RenderResult,
    VideoRenderPlan,
)

logger = logging.getLogger(__name__)


class VideoRenderEngine:
    """Enterprise-grade, platform-agnostic Video Render Engine.

    Features:
    - Pluggable Architecture: Any custom renderer can be injected via BaseVideoRenderer.
    - Zero Hardcoded Dependencies: Does not assume FFmpeg, Mac, Windows, or any specific tool.
    - Multi-Threading Concurrency: Parallel render of multiple videos using ThreadPoolExecutor.
    - In-Memory Isolated Logging: Separate, non-colliding log buffers per thread (NO disk I/O).
    - Automated Anti-Reup parameter generation.
    """

    def __init__(
        self,
        renderer: Optional[BaseVideoRenderer] = None,
        config: Optional[VideoRenderConfig] = None,
        anti_reup_engine: Optional[AntiReupEngine] = None,
    ):
        self.renderer = renderer
        self.config = config or VideoRenderConfig()
        self.anti_reup_engine = anti_reup_engine or AntiReupEngine()

    def set_renderer(self, renderer: BaseVideoRenderer) -> None:
        """Set or replace the active renderer implementation."""
        self.renderer = renderer

    def render_plan(
        self,
        source_folder: Path,
        plan: VideoRenderPlan,
        on_log: Optional[Callable[[str, str, str], None]] = None,
    ) -> RenderResult:
        """Render a single video plan using the injected custom renderer.

        Accumulates execution logs purely in memory without creating files on disk.

        Args:
            source_folder: Path to folder containing video/image assets.
            plan: Blueprint containing scenes, texts, audio, and durations.
            on_log: Optional callback(plan_id, level, message) for real-time log event streaming.

        Returns:
            RenderResult containing output path, duration, file size, and thread logs.
        """
        self._validate_inputs(source_folder=source_folder, plan=plan)

        start_time = time.time()
        task_logger = TaskLogger(plan_id=plan.plan_id, on_log=on_log)

        task_logger.info(f"Bắt đầu render video: '{plan.title}' ({len(plan.scenes)} scenes)")
        task_logger.info(f"Sử dụng renderer: {self.renderer.renderer_name}")
        task_logger.info(f"Thư mục tư liệu nguồn: {source_folder}")
        if plan.voice_clone_path:
            task_logger.info(f"Giọng đọc Voice Clone: '{plan.voice_clone_path.name}' ({plan.voice_clone_path})")
        if plan.bgm_path:
            vol_pct = int(round(plan.bgm_volume * 100)) if getattr(plan, "bgm_volume", None) is not None else 10
            task_logger.info(f"Nhạc nền BGM: '{plan.bgm_path.name}' (Âm lượng: {vol_pct}%, đường dẫn: {plan.bgm_path})")

        # 1. Check environment readiness
        if not self.renderer.validate_environment():
            err_msg = f"Renderer '{self.renderer.renderer_name}' báo cáo môi trường chưa sẵn sàng để render!"
            task_logger.error(err_msg)
            raise RenderExecutionError(err_msg)

        # 2. Generate anti-reup profile
        profile = self.anti_reup_engine.generate_profile(level=self.config.anti_reup_level)
        task_logger.info(f"Sinh AntiReupProfile thành công: UUID={profile.metadata_uuid[:8]}, Level={self.config.anti_reup_level}")

        # 3. Invoke hooks and delegate execution to user-defined renderer
        try:
            self.renderer.on_render_start(
                plan=plan,
                task_logger=task_logger,
                source_folder=source_folder,
                config=self.config,
            )
        except TypeError:
            self.renderer.on_render_start(plan=plan, task_logger=task_logger)

        result: Optional[RenderResult] = None
        try:
            result = self.renderer.render_plan(
                plan=plan,
                source_folder=source_folder,
                config=self.config,
                profile=profile,
                task_logger=task_logger,
            )

            # 4. Attach execution stats, profile, voice clone, and in-memory logs
            elapsed = round(time.time() - start_time, 2)
            result.render_time_seconds = elapsed
            result.anti_reup_profile = profile
            if plan.voice_clone_path:
                result.metadata["voice_clone_path"] = str(plan.voice_clone_path)
                result.metadata["voice_clone_name"] = plan.voice_clone_path.name
            if plan.bgm_path:
                result.metadata["bgm_path"] = str(plan.bgm_path)
                result.metadata["bgm_name"] = plan.bgm_path.name
                result.metadata["bgm_volume"] = plan.bgm_volume
            result.logs = task_logger.get_logs()

            task_logger.info(f"Hoàn thành render plan '{plan.plan_id}' trong {elapsed}s -> {result.output_path}")
            result.logs = task_logger.get_logs()
            return result
        except Exception as e:
            task_logger.error(f"Renderer gặp sự cố khi xử lý plan '{plan.plan_id}': {e}")
            raise RenderExecutionError(f"Render plan '{plan.plan_id}' thất bại: {e}") from e
        finally:
            try:
                self.renderer.on_render_end(
                    result=result,
                    task_logger=task_logger,
                    plan=plan,
                    config=self.config,
                )
            except TypeError:
                if result is not None:
                    self.renderer.on_render_end(result=result, task_logger=task_logger)

    def render_batch(
        self,
        source_folder: Path,
        plans: List[VideoRenderPlan],
        max_workers: Optional[int] = None,
        on_progress: Optional[Callable[[RenderResult], None]] = None,
        on_log: Optional[Callable[[str, str, str], None]] = None,
    ) -> RenderBatchResult:
        """Render multiple video plans concurrently using ThreadPoolExecutor.

        Each concurrent thread maintains its own independent in-memory log buffer.
        Errors in one plan do not terminate other parallel render tasks.

        Args:
            source_folder: Path to directory containing media clips.
            plans: List of VideoRenderPlan blueprints to render.
            max_workers: Number of parallel workers (defaults to config.max_concurrent_tasks).
            on_progress: Optional thread-safe callback invoked upon each video completion.
            on_log: Optional thread-safe callback for streaming log events from all threads.

        Returns:
            RenderBatchResult aggregating all successful and failed renders.
        """
        if not plans:
            raise InvalidPlanError("Danh sách plans không được để trống!")

        self._validate_inputs(source_folder=source_folder)

        workers = max_workers or self.config.max_concurrent_tasks
        workers = max(1, min(workers, len(plans)))

        logger.info(f"Khởi chạy render batch: {len(plans)} videos trên {workers} luồng song song...")
        batch_start = time.time()

        results: List[RenderResult] = []
        errors: List[dict] = []

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="VideoRenderWorker") as executor:
            future_to_plan = {
                executor.submit(self.render_plan, source_folder, plan, on_log): plan
                for plan in plans
            }

            for future in as_completed(future_to_plan):
                current_plan = future_to_plan[future]
                try:
                    res = future.result()
                    results.append(res)
                    if on_progress:
                        try:
                            on_progress(res)
                        except Exception as cb_err:
                            logger.warning(f"Lỗi trong progress callback: {cb_err}")
                except Exception as exc:
                    logger.error(f"Render plan '{current_plan.plan_id}' thất bại: {exc}")
                    errors.append({
                        "plan_id": current_plan.plan_id,
                        "title": current_plan.title,
                        "error": str(exc),
                    })

        total_time = round(time.time() - batch_start, 2)
        logger.info(
            f"Kết thúc render batch ({len(plans)} videos): "
            f"{len(results)} thành công, {len(errors)} thất bại trong {total_time}s"
        )

        return RenderBatchResult(
            total_plans=len(plans),
            successful_renders=len(results),
            failed_renders=len(errors),
            results=results,
            errors=errors,
            total_time_seconds=total_time,
        )

    def _validate_inputs(
        self,
        source_folder: Path,
        plan: Optional[VideoRenderPlan] = None,
    ) -> None:
        """Verify inputs and configuration."""
        if not self.renderer:
            raise RendererNotProvidedError(
                "Chưa cung cấp implementation của BaseVideoRenderer cho VideoRenderEngine! "
                "Vui lòng truyền renderer vào constructor hoặc gọi set_renderer(renderer)."
            )

        if not source_folder.exists() or not source_folder.is_dir():
            raise SourceFolderNotFoundError(f"Thư mục nguồn không tồn tại hoặc không phải thư mục: {source_folder}")

        if plan is not None:
            if not plan.scenes:
                raise InvalidPlanError(f"Plan '{plan.plan_id}' không chứa bất kỳ phân cảnh (scene) nào!")
