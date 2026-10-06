"""FFmpeg-based Video Renderer implementing the core rendering pipeline."""

import logging
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from app.config import AUDIO_SAMPLE_RATE, TRANSITION_DURATION
from app.services.plan_creator.constants import FFMPEG_TRANSITIONS
from app.services.video_render_engine.renderers.base import (
    BaseVideoRenderer,
    SUPPORTED_VIDEO_EXTENSIONS,
)
from app.services.video_render_engine.core.config import VideoRenderConfig
from app.services.video_render_engine.core.exceptions import (
    RenderExecutionError,
    SourceFolderNotFoundError,
)
from app.services.video_render_engine.core.logger import TaskLogger
from app.services.video_render_engine.core.models import (
    AntiReupProfile,
    RenderResult,
    VideoRenderPlan,
)
from app.services.video_render_engine.processors.output_namer import (
    allocate_next_output_path,
)
from app.services.video_render_engine.processors.segment import (
    SegmentCutPlan,
    VideoSegmentAllocator,
)
from app.services.video_render_engine.audio.transition_sound import (
    TransitionSoundSelector,
)

logger = logging.getLogger(__name__)


def _get_subprocess_extra_kwargs() -> Dict[str, Any]:
    """Return platform-specific subprocess execution flags."""
    kwargs: Dict[str, Any] = {}
    if sys.platform == 'win32':
        # 0x08000000 = subprocess.CREATE_NO_WINDOW
        kwargs['creationflags'] = 0x08000000
    return kwargs


class FFmpegBaseRenderer(BaseVideoRenderer):
    """Shared FFmpeg-based Video Renderer implementing the core rendering pipeline.

    Workflow:
    - on_render_start: Measures exact audio durations with ffprobe, scans source_folder,
      allocates unique, non-overlapping b-roll segments via VideoSegmentAllocator and cuts them
      into tmp/video_render/{plan_id}/{scene_id}.mp4.
      Supports scaling via 'crop' (fill screen) or 'pad' (letterbox).
    - render_plan: Composes each scene with segment video + transparent overlay PNG + narration audio,
      concatenates all scenes, overlays background music with audio ducking, applies Anti-Reup
      filters (micro-zoom, speed, color adjust, metadata), and hardware/software encodes.
    - on_render_end: Safely deletes the intermediate temp folder tmp/video_render/{plan_id}/.
    """

    def __init__(
        self,
        hardware_accel: bool = True,
        default_fit_mode: str = "crop",
        segment_allocator: Optional[VideoSegmentAllocator] = None,
        transition_sound_selector: Optional[TransitionSoundSelector] = None,
    ) -> None:
        self.hardware_accel = hardware_accel
        self.default_fit_mode = default_fit_mode.lower()
        self.segment_allocator = segment_allocator or VideoSegmentAllocator()
        self.transition_sound_selector = transition_sound_selector or TransitionSoundSelector()
        self._encoder: str = "libx264"
        self._ffmpeg_bin: str = "ffmpeg"
        self._ffprobe_bin: str = "ffprobe"
        self._video_duration_cache: Dict[str, float] = {}

    @property
    def renderer_name(self) -> str:
        return self.__class__.__name__

    def _run_cmd(self, cmd: List[str], **kwargs: Any) -> subprocess.CompletedProcess:
        """Execute subprocess with platform-specific flags (e.g. CREATE_NO_WINDOW on Windows)."""
        merged_kwargs = {**_get_subprocess_extra_kwargs(), **kwargs}
        merged_kwargs.setdefault("stdin", subprocess.DEVNULL)
        if merged_kwargs.get("text"):
            merged_kwargs.setdefault("encoding", "utf-8")
            merged_kwargs.setdefault("errors", "replace")
        return subprocess.run(cmd, **merged_kwargs)

    def validate_environment(self) -> bool:
        """Generic platform check for availability of ffmpeg and ffprobe."""
        ffmpeg_bin = shutil.which("ffmpeg")
        ffprobe_bin = shutil.which("ffprobe")
        if not ffmpeg_bin or not ffprobe_bin:
            logger.error("Không tìm thấy ffmpeg hoặc ffprobe trong PATH hệ thống!")
            return False

        self._ffmpeg_bin = ffmpeg_bin
        self._ffprobe_bin = ffprobe_bin
        self._encoder = "libx264"
        return True

    def _get_media_duration(self, file_path: Path) -> float:
        """Extract exact duration in seconds of an audio or video file using ffprobe."""
        if not file_path.exists():
            return 0.0
        try:
            cmd = [
                self._ffprobe_bin,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path.resolve()),
            ]
            proc = self._run_cmd(cmd, capture_output=True, text=True, check=True, timeout=30)
            output = proc.stdout.strip()
            return round(float(output), 3) if output else 0.0
        except Exception as e:
            logger.warning(f"Không thể đo duration file {file_path}: {e}")
            return 0.0

    def _scan_source_videos(self, source_folder: Path) -> List[Path]:
        """Scan directory for valid b-roll video files."""
        if not source_folder.exists() or not source_folder.is_dir():
            raise SourceFolderNotFoundError(f"Thư mục nguồn không tồn tại: {source_folder}")

        video_files = [
            f for f in source_folder.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS and not f.name.startswith(".")
        ]
        return video_files

    def _build_scale_filter(
        self,
        width: int,
        height: int,
        fps: int,
        fit_mode: str = "crop",
    ) -> str:
        """Build FFmpeg scale/crop or scale/pad filter string."""
        if fit_mode == "pad":
            return (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,fps={fps}"
            )
        # Default: "crop" (fill canvas without letterbox)
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps={fps}"
        )

    def _get_temp_plan_dir(
        self,
        plan_id: str,
        config: Optional[VideoRenderConfig] = None,
    ) -> Path:
        """Resolve temp working directory for a given plan."""
        base_tmp = (config.temp_dir if config and config.temp_dir else Path("tmp")) / "video_render"
        return base_tmp / plan_id

    def on_render_start(
        self,
        plan: VideoRenderPlan,
        task_logger: TaskLogger,
        source_folder: Optional[Path] = None,
        config: Optional[VideoRenderConfig] = None,
    ) -> None:
        """Hook invoked before rendering:

        1. Inspect audio duration for each scene using ffprobe.
        2. Scan source_folder for b-roll video footage.
        3. Randomly select and cut video segments with matching duration.
        4. Save normalized segments to tmp/video_render/{plan_id}/{scene_id}.mp4.
        """
        task_logger.info(f"==> [on_render_start] Bắt đầu chuẩn bị tài nguyên cho plan '{plan.plan_id}'")

        if not source_folder:
            task_logger.error("source_folder không được truyền vào on_render_start!")
            raise SourceFolderNotFoundError("Chưa chỉ định thư mục nguồn video!")

        source_videos = self._scan_source_videos(source_folder)
        if not source_videos:
            err_msg = f"Thư mục nguồn '{source_folder}' không chứa bất kỳ video b-roll hợp lệ nào!"
            task_logger.error(err_msg)
            raise SourceFolderNotFoundError(err_msg)

        task_logger.info(f"Tìm thấy {len(source_videos)} video b-roll trong thư mục nguồn: '{source_folder}'")
        if plan.voice_clone_path:
            task_logger.info(f"Áp dụng Voice Clone: '{plan.voice_clone_path.name}' ({plan.voice_clone_path})")

        cfg = config or VideoRenderConfig()
        tmp_dir = self._get_temp_plan_dir(plan.plan_id, cfg)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        task_logger.info(f"Tạo thư mục làm việc tạm thời: {tmp_dir}")

        fit_mode = (
            cfg.extra_params.get("aspect_mode")
            or cfg.extra_params.get("fit_mode")
            or self.default_fit_mode
        ).lower()
        scale_vf = self._build_scale_filter(cfg.width, cfg.height, cfg.fps, fit_mode)

        # 1. Đo lường chính xác thời lượng audio của toàn bộ các scenes
        scene_durations: List[float] = []
        for scene in plan.scenes:
            audio_duration = 0.0
            if scene.audio_path and Path(scene.audio_path).exists():
                audio_duration = self._get_media_duration(Path(scene.audio_path))
                task_logger.info(
                    f"   [Scene {scene.scene_index}] Đo được thời lượng audio: {audio_duration:.2f}s "
                    f"từ '{Path(scene.audio_path).name}'"
                )
            elif plan.master_voiceover_path and Path(plan.master_voiceover_path).exists():
                master_dur = self._get_media_duration(Path(plan.master_voiceover_path))
                audio_duration = round(master_dur / max(1, len(plan.scenes)), 2)
                task_logger.info(
                    f"   [Scene {scene.scene_index}] Tính từ master audio: {audio_duration:.2f}s"
                )
            else:
                audio_duration = float(scene.metadata.get("duration", 3.0))
                task_logger.info(
                    f"   [Scene {scene.scene_index}] Không có audio file, dùng duration mặc định: {audio_duration:.2f}s"
                )

            if audio_duration <= 0.1:
                audio_duration = 3.0

            scene.metadata["measured_duration"] = audio_duration
            scene_durations.append(audio_duration)

        # 2. Đo và nạp cache thời lượng cho toàn bộ video nguồn
        source_videos_info: Dict[Path, float] = {}
        for v in source_videos:
            v_key = str(v.resolve())
            if v_key not in self._video_duration_cache:
                self._video_duration_cache[v_key] = self._get_media_duration(v)
            source_videos_info[v] = self._video_duration_cache[v_key]

        # 3. Phân bổ segment thông minh bằng VideoSegmentAllocator
        allocator_seed = cfg.extra_params.get("seed") or cfg.extra_params.get("segment_seed")
        enable_trans = getattr(cfg, "enable_transition", True) and len(plan.scenes) > 1
        trans_dur = float(getattr(cfg, "transition_duration", TRANSITION_DURATION)) if enable_trans else 0.0

        # Các scene trung gian cần cắt dài hơn trans_dur để bù trừ phần giao thoa xfade
        allocated_durations = [
            (dur + trans_dur if (enable_trans and idx < len(scene_durations) - 1) else dur)
            for idx, dur in enumerate(scene_durations)
        ]

        segment_plans = self.segment_allocator.allocate(
            scene_durations=allocated_durations,
            source_videos_info=source_videos_info,
            seed=allocator_seed,
        )

        # 4. Thực thi cắt từng segment bằng FFmpeg
        for scene, cut_plan in zip(plan.scenes, segment_plans):
            scene_id = scene.metadata.get("scene_id") or f"scene_{scene.scene_index}"
            segment_output = tmp_dir / f"{scene_id}.mp4"

            cmd = [self._ffmpeg_bin, "-y", "-nostdin"]
            if getattr(self, "hardware_accel", False) and self._encoder == "h264_nvenc":
                cmd.extend(["-hwaccel", "auto"])
            if cut_plan.loop_needed:
                cmd.extend(["-stream_loop", "-1"])
            cmd.extend([
                "-ss", f"{cut_plan.start_time:.3f}",
                "-t", f"{cut_plan.duration:.3f}",
                "-i", str(cut_plan.video_path.resolve()),
                "-vf", scale_vf,
                "-c:v", self._encoder,
            ])
            if self._encoder == "h264_nvenc":
                cmd.extend(["-preset", "p2"])
            elif self._encoder == "libx264":
                cmd.extend(["-preset", "veryfast"])
            cmd.extend([
                "-b:v", "6000k",
                "-pix_fmt", "yuv420p",
                "-an",
                str(segment_output.resolve()),
            ])

            overlap_pct = cut_plan.overlap_ratio * 100.0
            task_logger.info(
                f"   [Scene {scene.scene_index}] Cắt segment: start={cut_plan.start_time:.2f}s, "
                f"dur={cut_plan.duration:.2f}s, loop={cut_plan.loop_needed}, overlap={overlap_pct:.0f}% "
                f"từ '{cut_plan.video_path.name}' -> {segment_output.name}"
            )

            try:
                self._run_cmd(cmd, capture_output=True, text=True, check=True, timeout=300)
            except subprocess.CalledProcessError as err:
                task_logger.error(
                    f"Lỗi khi cắt video segment cho scene {scene.scene_index}: {err.stderr}"
                )
                raise RenderExecutionError(f"Cắt segment thất bại cho {scene_id}: {err.stderr}") from err

            scene.metadata["segment_path"] = str(segment_output.resolve())
            scene.metadata["chosen_video"] = str(cut_plan.video_path.resolve())
            scene.metadata["segment_start_time"] = cut_plan.start_time

        task_logger.info(f"==> [on_render_start] Đã chuẩn bị xong {len(plan.scenes)} segments tại {tmp_dir}")

    def render_plan(
        self,
        plan: VideoRenderPlan,
        source_folder: Path,
        config: VideoRenderConfig,
        profile: AntiReupProfile,
        task_logger: TaskLogger,
    ) -> RenderResult:
        """Render plan:

        1. Read prepared segments from tmp/video_render/{plan_id}/.
        2. Merge each scene: segment video + overlay image (PNG) + narration audio.
        3. Concat all scenes into a continuous stream.
        4. Apply Anti-Reup filters and background music.
        5. Output final video file.
        """
        task_logger.info(f"==> [render_plan] Bắt đầu render kịch bản: '{plan.title}' (ID: {plan.plan_id})")
        tmp_dir = self._get_temp_plan_dir(plan.plan_id, config)
        fit_mode = (
            config.extra_params.get("aspect_mode")
            or config.extra_params.get("fit_mode")
            or self.default_fit_mode
        ).lower()

        base_dest_dir = config.output_dir or Path("storage/outputs")
        if plan.company_name or not plan.output_filename:
            final_output = allocate_next_output_path(
                base_output_dir=base_dest_dir,
                company_name=plan.company_name,
                sequence_hint=plan.video_index,
            )
            dest_dir = final_output.parent
        else:
            dest_dir = base_dest_dir
            dest_dir.mkdir(parents=True, exist_ok=True)
            final_output = dest_dir / plan.output_filename

        composed_scenes: List[Path] = []
        scene_audio_files: List[Path] = []
        flip_h = bool(profile.get("flip_horizontal", False)) if profile else False

        num_scenes = len(plan.scenes)
        enable_trans = getattr(config, "enable_transition", True) and num_scenes > 1
        trans_dur = float(getattr(config, "transition_duration", TRANSITION_DURATION)) if enable_trans else 0.0

        # 1. Ghép từng scene (Video Segment + Overlay PNG) - Chỉ xử lý VIDEO, không nhồi Audio AAC trung gian
        for i, scene in enumerate(plan.scenes):
            scene_id = scene.metadata.get("scene_id") or f"scene_{scene.scene_index}"
            segment_path = Path(scene.metadata.get("segment_path") or (tmp_dir / f"{scene_id}.mp4"))

            if not segment_path.exists():
                raise RenderExecutionError(f"Không tìm thấy segment video cho scene {scene_id}: {segment_path}")

            scene_composed = tmp_dir / f"composed_{scene_id}.mp4"
            dur = float(scene.metadata.get("measured_duration", 3.0))
            clip_dur = dur + trans_dur if (enable_trans and i < num_scenes - 1) else dur

            has_overlay = scene.overlay_image_path and Path(scene.overlay_image_path).exists()
            has_audio = scene.audio_path and Path(scene.audio_path).exists()

            # Chuẩn bị audio của scene (nếu không có audio file thì tạo file silent WAV chuẩn PCM)
            if has_audio:
                scene_audio_files.append(Path(scene.audio_path).resolve())
            else:
                silent_wav = tmp_dir / f"silent_{scene_id}.wav"
                cmd_silent = [
                    self._ffmpeg_bin, "-y", "-nostdin",
                    "-f", "lavfi",
                    "-t", f"{dur:.3f}",
                    "-i", f"anullsrc=channel_layout=stereo:sample_rate={AUDIO_SAMPLE_RATE}",
                    "-c:a", "pcm_s16le",
                    str(silent_wav.resolve()),
                ]
                self._run_cmd(cmd_silent, capture_output=True, check=True)
                scene_audio_files.append(silent_wav)

            # Ghép video segment + overlay image (nếu có).
            cmd = [self._ffmpeg_bin, "-y", "-nostdin", "-i", str(segment_path.resolve())]
            if has_overlay:
                cmd.extend(["-i", str(Path(scene.overlay_image_path).resolve())])
                if flip_h:
                    filter_str = f"[0:v]hflip[bg];[bg][1:v]overlay=0:0,tpad=stop_mode=clone:stop_duration=1.5[outv]"
                else:
                    filter_str = f"[0:v][1:v]overlay=0:0,tpad=stop_mode=clone:stop_duration=1.5[outv]"
                cmd.extend([
                    "-filter_complex", filter_str,
                    "-map", "[outv]",
                ])
            else:
                vf = "hflip,tpad=stop_mode=clone:stop_duration=1.5" if flip_h else "tpad=stop_mode=clone:stop_duration=1.5"
                cmd.extend([
                    "-vf", vf,
                    "-map", "0:v",
                ])

            cmd.extend([
                "-t", f"{clip_dur:.3f}",
                "-c:v", self._encoder,
            ])
            if self._encoder == "h264_nvenc":
                cmd.extend(["-preset", "p2"])
            elif self._encoder == "libx264":
                cmd.extend(["-preset", "veryfast"])
            cmd.extend([
                "-b:v", "6000k",
                "-pix_fmt", "yuv420p",
                "-an",
                str(scene_composed.resolve()),
            ])

            task_logger.info(
                f"   [Ghép scene {scene.scene_index}] overlay={has_overlay}, audio={has_audio} (dur={clip_dur:.2f}s) "
                f"-> {scene_composed.name}"
            )

            try:
                self._run_cmd(cmd, capture_output=True, text=True, check=True, timeout=300)
            except subprocess.CalledProcessError as err:
                task_logger.error(f"Lỗi ghép scene {scene_id}: {err.stderr}")
                raise RenderExecutionError(f"Ghép scene {scene_id} thất bại: {err.stderr}") from err

            composed_scenes.append(scene_composed)

        # 2. Concat các video segment lại với nhau (Hỗ trợ FFmpeg xfade đa tầng hoặc Concat Demuxer)
        concatenated_video = tmp_dir / "concatenated.mp4"
        if enable_trans and num_scenes > 1:
            task_logger.info(
                f"Nối {num_scenes} phân cảnh với hiệu ứng FFmpeg xfade (thời lượng chuyển cảnh: {trans_dur:.2f}s)..."
            )
            inputs = []
            filter_parts = []
            prev_v = "[0:v]"
            accum_offset = 0.0

            for sc in composed_scenes:
                inputs.extend(["-i", str(sc.resolve())])

            for i in range(num_scenes - 1):
                next_v = f"[{i + 1}:v]"
                out_v = f"[v{i + 1}]" if i < num_scenes - 2 else "[outv]"
                accum_offset += float(plan.scenes[i].metadata.get("measured_duration", 3.0))

                tr_name = plan.scenes[i].transition
                if not tr_name or str(tr_name).lower() not in FFMPEG_TRANSITIONS:
                    if tr_name:
                        task_logger.warning(
                            f"   [Transition {i}->{i+1}] '{tr_name}' không thuộc whitelist 58 xfade, fallback sang 'fade'"
                        )
                    tr_name = "fade"
                else:
                    tr_name = str(tr_name).lower()

                task_logger.info(
                    f"   [Transition {i}->{i+1}] Áp dụng '{tr_name}' tại {accum_offset:.2f}s (duration={trans_dur:.2f}s)"
                )
                filter_parts.append(
                    f"{prev_v}{next_v}xfade=transition={tr_name}:duration={trans_dur:.3f}:offset={accum_offset:.3f}{out_v}"
                )
                prev_v = out_v

            cmd_xfade = (
                [self._ffmpeg_bin, "-y", "-nostdin"]
                + inputs
                + [
                    "-filter_complex", ";".join(filter_parts),
                    "-map", "[outv]",
                    "-c:v", self._encoder,
                    "-b:v", "6000k",
                    "-pix_fmt", "yuv420p",
                    "-an",
                    str(concatenated_video.resolve()),
                ]
            )
            try:
                self._run_cmd(cmd_xfade, capture_output=True, text=True, check=True, timeout=600)
            except subprocess.CalledProcessError as err:
                task_logger.error(f"Lỗi khi nối video bằng xfade: {err.stderr}")
                raise RenderExecutionError(f"Concat video xfade thất bại: {err.stderr}") from err
        else:
            # Fallback Concat Demuxer copy (Dùng POSIX path để an toàn trên cả Windows và macOS)
            concat_list_file = tmp_dir / "concat_list.txt"
            with open(concat_list_file, "w", encoding="utf-8") as f:
                for sc in composed_scenes:
                    f.write(f"file '{sc.resolve().as_posix()}'\n")

            concat_cmd = [
                self._ffmpeg_bin, "-y", "-nostdin",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list_file.resolve()),
                "-c", "copy",
                str(concatenated_video.resolve()),
            ]
            task_logger.info("Nối các phân cảnh video bằng Concat Demuxer...")
            try:
                self._run_cmd(concat_cmd, capture_output=True, text=True, check=True, timeout=300)
            except subprocess.CalledProcessError as err:
                task_logger.error(f"Lỗi khi nối các scene video: {err.stderr}")
                raise RenderExecutionError(f"Concat video thất bại: {err.stderr}") from err

        # 2b. Nối toàn bộ audio các scene thành Master Voice Audio (PCM Lossless, Zero drop packet)
        voice_master_wav = tmp_dir / "voice_master.wav"
        if len(scene_audio_files) == 1:
            cmd_audio_single = [
                self._ffmpeg_bin, "-y", "-nostdin",
                "-i", str(scene_audio_files[0].resolve()),
                "-c:a", "pcm_s16le",
                "-ar", str(AUDIO_SAMPLE_RATE),
                "-ac", "2",
                str(voice_master_wav.resolve()),
            ]
            self._run_cmd(cmd_audio_single, capture_output=True, text=True, check=True)
        else:
            audio_concat_inputs = []
            audio_filter_parts = []
            for a_idx, a_path in enumerate(scene_audio_files):
                audio_concat_inputs.extend(["-i", str(a_path.resolve())])
                audio_filter_parts.append(
                    f"[{a_idx}:a]aformat=sample_rates={AUDIO_SAMPLE_RATE}:channel_layouts=stereo[a{a_idx}]"
                )
            concat_expr = (
                "".join(f"[a{a_idx}]" for a_idx in range(len(scene_audio_files)))
                + f"concat=n={len(scene_audio_files)}:v=0:a=1[outa]"
            )
            audio_filter_parts.append(concat_expr)
            cmd_audio_concat = (
                [self._ffmpeg_bin, "-y", "-nostdin"]
                + audio_concat_inputs
                + [
                    "-filter_complex", ";".join(audio_filter_parts),
                    "-map", "[outa]",
                    "-c:a", "pcm_s16le",
                    str(voice_master_wav.resolve()),
                ]
            )
            try:
                self._run_cmd(cmd_audio_concat, capture_output=True, text=True, check=True, timeout=300)
            except subprocess.CalledProcessError as err:
                task_logger.error(f"Lỗi ghép nối Master Audio: {err.stderr}")
                raise RenderExecutionError(f"Ghép Master Audio thất bại: {err.stderr}") from err

        # 3. Áp dụng Anti-Reup profile và Background Music (BGM)
        speed = float(profile.get("speed", 1.0))
        zoom = float(profile.get("zoom", 1.0))
        brightness = float(profile.get("brightness", 0.0))
        contrast = float(profile.get("contrast", 1.0))
        saturation = float(profile.get("saturation", 1.0))

        v_filters: List[str] = []
        if abs(speed - 1.0) > 0.001:
            v_filters.append(f"setpts={1.0 / speed:.4f}*PTS")
        if zoom > 1.001:
            v_filters.append(f"scale=iw*{zoom:.4f}:ih*{zoom:.4f},crop={config.width}:{config.height}")
        if abs(brightness) > 0.001 or abs(contrast - 1.0) > 0.001 or abs(saturation - 1.0) > 0.001:
            v_filters.append(
                f"eq=brightness={brightness:.4f}:contrast={contrast:.4f}:saturation={saturation:.4f}"
            )

        vf_anti_reup = ",".join(v_filters) if v_filters else "null"

        # 3. Chuẩn bị Transition Sound Effects (SFX) căn theo đỉnh Waveform
        enable_sfx = getattr(config, "enable_transition_sound", True)
        sfx_volume = float(getattr(config, "transition_sound_volume", 0.15))
        sfx_dir = getattr(config, "transition_sound_dir", None)

        transition_entries: List[Dict[str, Any]] = []
        if enable_sfx and len(plan.scenes) > 1:
            selector = (
                TransitionSoundSelector(sounds_dir=sfx_dir)
                if sfx_dir
                else self.transition_sound_selector
            )
            allocator_seed = config.extra_params.get("seed") or config.extra_params.get("segment_seed")
            transition_count = len(plan.scenes) - 1
            allocated_sounds = selector.allocate(
                transition_count=transition_count,
                seed=allocator_seed,
            )

            accumulated_time = 0.0
            avoid_collision = getattr(config, "avoid_sfx_transition_collision", True)

            for idx in range(transition_count):
                sc = plan.scenes[idx]
                dur_sc = float(sc.metadata.get("measured_duration", 3.0))
                accumulated_time += dur_sc

                # Kiểm tra né xung đột
                scene_sfx = sc.metadata.get("sound_effect")
                if not scene_sfx and sc.metadata.get("srt_script"):
                    from app.services.video_render_engine.sound_effect_manager import parse_sound_effect_tag
                    _, scene_sfx = parse_sound_effect_tag(sc.metadata.get("srt_script"))

                if avoid_collision and scene_sfx:
                    task_logger.info(
                        f"   [Transition {idx}->{idx+1}] Bỏ qua Transition Sound vì Scene {idx} "
                        f"đã có Sound Effect: '{scene_sfx}'"
                    )
                    continue

                sound_path, peak_ts = allocated_sounds[idx]
                if sound_path and sound_path.exists():
                    t_transition = accumulated_time / speed
                    t_start = max(0.0, t_transition - peak_ts)
                    delay_ms = int(round(t_start * 1000))
                    transition_entries.append({
                        "index": idx,
                        "sound_path": sound_path,
                        "delay_ms": delay_ms,
                        "t_transition": t_transition,
                        "peak_ts": peak_ts,
                    })
                    task_logger.info(
                        f"   [Transition {idx}->{idx+1}] Gán SFX: '{sound_path.name}' tại {t_transition:.2f}s "
                        f"(peak={peak_ts:.2f}s, delay={delay_ms}ms, vol={sfx_volume:.1f})"
                    )

        final_cmd = [
            self._ffmpeg_bin, "-y", "-nostdin",
            "-i", str(concatenated_video.resolve()),
            "-i", str(voice_master_wav.resolve()),
        ]
        curr_input_idx = 2

        # 3b. Chuẩn bị Background Music (BGM)
        enable_bgm = getattr(config, "enable_bgm", True)
        bgm_path = plan.bgm_path
        if (not bgm_path or not Path(bgm_path).exists()) and enable_bgm and getattr(config, "randomize_bgm", True):
            from app.services.video_render_engine.bgm_manager import pick_random_bgm
            bgm_dir = getattr(config, "bgm_dir", None)
            bgm_seed = config.extra_params.get("seed") or config.extra_params.get("bgm_seed")
            bgm_path = pick_random_bgm(bgm_dir=bgm_dir, seed=bgm_seed)
            if bgm_path:
                task_logger.info(f"Tự động chọn ngẫu nhiên BGM cho plan: '{bgm_path.name}'")

        has_bgm = enable_bgm and bgm_path and Path(bgm_path).exists()
        bgm_vol = float(
            getattr(plan, "bgm_volume", None)
            if getattr(plan, "bgm_volume", None) is not None
            else getattr(config, "bgm_volume", 0.10)
        )
        bgm_input_idx = None
        if has_bgm:
            final_cmd.extend(["-stream_loop", "-1", "-i", str(Path(bgm_path).resolve())])
            bgm_input_idx = curr_input_idx
            curr_input_idx += 1

        sfx_inputs: List[Tuple[int, int]] = []
        for entry in transition_entries:
            final_cmd.extend(["-i", str(entry["sound_path"].resolve())])
            sfx_inputs.append((curr_input_idx, entry["delay_ms"]))
            curr_input_idx += 1

        # Xây dựng filter_complex kết hợp Video Filters và Audio Mixing (Voice Master + BGM + SFX)
        filter_parts: List[str] = [f"[0:v]{vf_anti_reup}[outv]"]
        audio_mix_inputs: List[str] = ["[a_voice]"]

        # 1:a là Master Voice Stream
        if abs(speed - 1.0) > 0.001:
            filter_parts.append(f"[1:a]atempo={speed:.4f}[a_voice]")
        else:
            filter_parts.append("[1:a]anull[a_voice]")

        if has_bgm:
            filter_parts.append(f"[{bgm_input_idx}:a]volume={bgm_vol:.2f}[a_bgm]")
            audio_mix_inputs.append("[a_bgm]")

        for s_idx, (in_idx, d_ms) in enumerate(sfx_inputs):
            sfx_label = f"[sfx_{s_idx}]"
            filter_parts.append(f"[{in_idx}:a]volume={sfx_volume:.2f},adelay={d_ms}|{d_ms}{sfx_label}")
            audio_mix_inputs.append(sfx_label)

        if len(audio_mix_inputs) > 1:
            fc_audio = (
                "".join(audio_mix_inputs)
                + f"amix=inputs={len(audio_mix_inputs)}:duration=first:dropout_transition=0:normalize=0[outa]"
            )
            filter_parts.append(fc_audio)
            final_cmd.extend([
                "-filter_complex", ";".join(filter_parts),
                "-map", "[outv]",
                "-map", "[outa]",
            ])
        else:
            final_cmd.extend([
                "-filter_complex", ";".join(filter_parts),
                "-map", "[outv]",
                "-map", "[a_voice]",
            ])

        meta_uuid = profile.get("metadata_uuid", "")
        meta_date = profile.get("metadata_date", "")
        if meta_uuid:
            final_cmd.extend(["-metadata", f"comment={meta_uuid}"])
        if meta_date:
            final_cmd.extend(["-metadata", f"creation_time={meta_date}"])

        final_cmd.extend([
            "-c:v", self._encoder,
        ])
        if self._encoder == "h264_nvenc":
            final_cmd.extend(["-preset", "p4"])
        elif self._encoder == "libx264":
            final_cmd.extend(["-preset", "medium"])
        final_cmd.extend([
            "-b:v", "6000k",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", str(AUDIO_SAMPLE_RATE),
            "-ac", "2",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(final_output.resolve()),
        ])

        bgm_log_name = Path(bgm_path).name if has_bgm else "None"
        task_logger.info(
            f"Render thành phẩm cuối cùng: BGM={has_bgm} ({bgm_log_name}, vol={bgm_vol:.2f}), "
            f"TransitionSFX={len(transition_entries)}, Encoder={self._encoder}, "
            f"Speed={speed:.3f}, Zoom={zoom:.3f} -> '{final_output.name}'"
        )

        try:
            self._run_cmd(final_cmd, capture_output=True, text=True, check=True, timeout=600)
        except subprocess.CalledProcessError as err:
            task_logger.error(f"Lỗi khi hoàn tất encode video: {err.stderr}")
            raise RenderExecutionError(f"Render video thành phẩm thất bại: {err.stderr}") from err

        final_duration = self._get_media_duration(final_output)
        file_size = final_output.stat().st_size if final_output.exists() else 0

        task_logger.info(
            f"Xuất file thành công: {final_output.name} ({file_size / (1024 * 1024):.2f} MB, {final_duration:.2f}s)"
        )

        return RenderResult(
            plan_id=plan.plan_id,
            output_path=final_output,
            duration=final_duration,
            file_size_bytes=file_size,
            scenes_count=len(plan.scenes),
            metadata={
                **dict(profile.params),
                "encoder_used": self._encoder,
                "fit_mode": fit_mode,
                "voice_clone_path": str(plan.voice_clone_path) if plan.voice_clone_path else None,
                "transition_sfx_count": len(transition_entries),
                "visual_transition_count": (num_scenes - 1) if (enable_trans and num_scenes > 1) else 0,
                "bgm_path": str(bgm_path) if has_bgm else None,
                "bgm_volume": bgm_vol if has_bgm else 0.0,
            },
        )

    def on_render_end(
        self,
        result: Optional[RenderResult],
        task_logger: TaskLogger,
        plan: Optional[VideoRenderPlan] = None,
        config: Optional[VideoRenderConfig] = None,
    ) -> None:
        """Hook invoked after rendering: clean up temp directory tmp/video_render/{plan_id}/."""
        plan_id = (result.plan_id if result else None) or (plan.plan_id if plan else None)
        if not plan_id:
            task_logger.warning("on_render_end không xác định được plan_id để dọn dẹp!")
            return

        tmp_dir = self._get_temp_plan_dir(plan_id, config)
        if tmp_dir.exists():
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                task_logger.info(f"==> [on_render_end] Đã dọn dẹp sạch sẽ thư mục tạm: {tmp_dir}")
            except Exception as e:
                task_logger.warning(f"Lỗi khi dọn dẹp thư mục tạm {tmp_dir}: {e}")


