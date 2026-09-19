"""Native macOS Video Renderer using FFmpeg, FFprobe, and VideoToolbox hardware acceleration."""

import logging
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional

from app.services.video_render_engine.renderers.ffmpeg import FFmpegBaseRenderer

logger = logging.getLogger(__name__)


class MacOSVideoRenderer(FFmpegBaseRenderer):
    """Native macOS Video Renderer using FFmpeg, FFprobe, and VideoToolbox hardware acceleration.

    Hardware acceleration attempts to use Apple Silicon h264_videotoolbox,
    falling back gracefully to libx264.
    """

    @property
    def renderer_name(self) -> str:
        return "MacOSVideoRenderer"

    def validate_environment(self) -> bool:
        """Check availability of ffmpeg, ffprobe, and VideoToolbox hardware encoder on macOS."""
        ffmpeg_bin = shutil.which("ffmpeg")
        ffprobe_bin = shutil.which("ffprobe")
        if not ffmpeg_bin or not ffprobe_bin:
            logger.error("Không tìm thấy ffmpeg hoặc ffprobe trong PATH hệ thống macOS!")
            return False

        self._ffmpeg_bin = ffmpeg_bin
        self._ffprobe_bin = ffprobe_bin

        if self.hardware_accel:
            try:
                proc = self._run_cmd(
                    [self._ffmpeg_bin, "-encoders"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if "h264_videotoolbox" in proc.stdout:
                    self._encoder = "h264_videotoolbox"
                    logger.info("Đã kích hoạt bộ mã hóa phần cứng macOS: h264_videotoolbox")
                else:
                    self._encoder = "libx264"
                    logger.warning("h264_videotoolbox không khả dụng, fallback sang libx264")
            except Exception as e:
                logger.warning(f"Lỗi kiểm tra VideoToolbox ({e}), fallback sang libx264")
                self._encoder = "libx264"
        else:
            self._encoder = "libx264"

        return True


