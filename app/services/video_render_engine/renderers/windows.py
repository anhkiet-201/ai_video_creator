"""Native Windows Video Renderer using FFmpeg, FFprobe, and NVIDIA NVENC hardware acceleration."""

import logging
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, List, Optional

from app.services.video_render_engine.renderers.ffmpeg import FFmpegBaseRenderer
from app.services.video_render_engine.processors.segment import VideoSegmentAllocator
from app.services.video_render_engine.audio.transition_sound import TransitionSoundSelector

logger = logging.getLogger(__name__)


class WindowsVideoRenderer(FFmpegBaseRenderer):
    """Native Windows Video Renderer using FFmpeg, FFprobe, and NVIDIA NVENC hardware acceleration.

    Features:
    - Smart Binary Discovery: Automatically resolves ffmpeg.exe and ffprobe.exe via PATH,
      user environment variables, and standard WinGet locations (%LOCALAPPDATA%/Microsoft/WinGet/Links).
    - Hardware Acceleration: Detects and tests NVIDIA GPU h264_nvenc, falling back gracefully to libx264.
    - Zero-Window execution: Suppresses console popup window during background rendering.
    - Windows path safety: Enforces POSIX slash formatting for FFmpeg concat demuxers.
    """

    def __init__(
        self,
        hardware_accel: bool = True,
        default_fit_mode: str = "crop",
        segment_allocator: Optional[VideoSegmentAllocator] = None,
        transition_sound_selector: Optional[TransitionSoundSelector] = None,
        ffmpeg_path: Optional[str] = None,
        ffprobe_path: Optional[str] = None,
    ) -> None:
        super().__init__(
            hardware_accel=hardware_accel,
            default_fit_mode=default_fit_mode,
            segment_allocator=segment_allocator,
            transition_sound_selector=transition_sound_selector,
        )
        self._custom_ffmpeg = ffmpeg_path
        self._custom_ffprobe = ffprobe_path

    @property
    def renderer_name(self) -> str:
        return "WindowsVideoRenderer"

    def _find_binary(self, binary_name: str, custom_path: Optional[str] = None) -> Optional[str]:
        """Find executable binary on Windows across multiple sources."""
        # 1. Custom path explicitly passed
        if custom_path:
            p = Path(custom_path)
            if p.exists():
                return str(p.resolve())

        # 2. Environment variables FFMPEG_PATH / FFPROBE_PATH
        env_key = f"{binary_name.upper()}_PATH"
        env_val = os.environ.get(env_key)
        if env_val:
            p = Path(env_val)
            if p.exists():
                return str(p.resolve())

        # 3. System and current process PATH
        which_found = shutil.which(binary_name) or shutil.which(f"{binary_name}.exe")
        if which_found:
            return which_found

        # 4. Standard WinGet Links directory (%LOCALAPPDATA%/Microsoft/WinGet/Links)
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            winget_bin = Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / f"{binary_name}.exe"
            if winget_bin.exists():
                return str(winget_bin.resolve())

        user_profile = os.environ.get("USERPROFILE")
        if user_profile:
            winget_bin = Path(user_profile) / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links" / f"{binary_name}.exe"
            if winget_bin.exists():
                return str(winget_bin.resolve())

        # 5. Windows Registry User Environment PATH
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                val, _ = winreg.QueryValueEx(key, "Path")
                for part in val.split(";"):
                    clean_part = part.strip()
                    if clean_part:
                        cand = Path(clean_part) / f"{binary_name}.exe"
                        if cand.exists():
                            return str(cand.resolve())
        except Exception:
            pass

        # 6. Common Windows installation directories
        common_candidates = [
            Path("C:/ffmpeg/bin") / f"{binary_name}.exe",
            Path("C:/Program Files/ffmpeg/bin") / f"{binary_name}.exe",
            Path("C:/ProgramData/chocolatey/bin") / f"{binary_name}.exe",
        ]
        if user_profile:
            common_candidates.extend([
                Path(user_profile) / "scoop" / "shims" / f"{binary_name}.exe",
                Path(user_profile) / "scoop" / "apps" / "ffmpeg" / "current" / "bin" / f"{binary_name}.exe",
            ])
        for cand in common_candidates:
            if cand.exists():
                return str(cand.resolve())

        return None

    def _detect_nvidia_encoder(self) -> str:
        """Check if NVIDIA NVENC (h264_nvenc) is available and functional."""
        try:
            # 1. Kiểm tra h264_nvenc có trong danh sách encoders của FFmpeg
            proc = self._run_cmd(
                [self._ffmpeg_bin, "-encoders"],
                capture_output=True,
                text=True,
                check=False,
            )
            if "h264_nvenc" not in proc.stdout:
                logger.warning("FFmpeg hiện tại không hỗ trợ h264_nvenc, fallback sang libx264")
                return "libx264"

            # 2. Thử nghiệm encode thực tế trên GPU NVIDIA với 1 frame dummy (NVENC yêu cầu tối thiểu ~144x144)
            test_cmd = [
                self._ffmpeg_bin,
                "-v", "error",
                "-f", "lavfi",
                "-i", "testsrc=duration=0.1:size=320x240:rate=30",
                "-c:v", "h264_nvenc",
                "-f", "null",
                "-",
            ]
            self._run_cmd(test_cmd, capture_output=True, text=True, check=True, timeout=10)
            logger.info("Đã kích hoạt bộ mã hóa phần cứng NVIDIA GPU: h264_nvenc")
            return "h264_nvenc"
        except Exception as e:
            logger.warning(f"Không thể kích hoạt NVIDIA NVENC ({e}), fallback sang libx264")
            return "libx264"

    def validate_environment(self) -> bool:
        """Check availability of ffmpeg, ffprobe, and NVIDIA NVENC hardware encoder on Windows."""
        ffmpeg_bin = self._find_binary("ffmpeg", self._custom_ffmpeg)
        ffprobe_bin = self._find_binary("ffprobe", self._custom_ffprobe)

        if not ffmpeg_bin or not ffprobe_bin:
            logger.error(
                "Không tìm thấy ffmpeg hoặc ffprobe trên hệ thống Windows!\n"
                "Vui lòng cài đặt FFmpeg bằng lệnh: winget install Gyan.FFmpeg\n"
                "hoặc tải từ https://www.gyan.dev/ffmpeg/builds/ và thêm vào PATH."
            )
            return False

        self._ffmpeg_bin = ffmpeg_bin
        self._ffprobe_bin = ffprobe_bin

        # Bổ sung thư mục chứa binary vào PATH tiến trình nếu chưa có
        bin_dir = str(Path(ffmpeg_bin).parent.resolve())
        curr_path = os.environ.get("PATH", "")
        if bin_dir not in curr_path:
            os.environ["PATH"] = f"{bin_dir};{curr_path}"

        if self.hardware_accel:
            self._encoder = self._detect_nvidia_encoder()
        else:
            self._encoder = "libx264"

        return True


