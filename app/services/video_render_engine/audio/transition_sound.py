"""Transition sound effect (SFX) management and waveform peak alignment.

Cung cấp dịch vụ quản lý, tuyển chọn ngẫu nhiên và phân tích dạng sóng (Waveform Peak Detection)
cho các tệp âm thanh hiệu ứng chuyển cảnh (whoosh, swish, swoosh...) từ thư mục assets:
- Tự động quét và phân bổ âm thanh đa dạng (Cyclic-Shuffle) tránh trùng lặp giữa các cảnh liên tiếp.
- Phân tích năng lượng dạng sóng (Sliding-window Energy Envelope) để xác định chính xác đỉnh âm lượng (Peak).
- Căn đỉnh âm lượng khớp 100% với khoảnh khắc chuyển cảnh giữa 2 scenes.
- Tích hợp bộ nhớ đệm (In-memory Peak Cache) để tối ưu hóa hiệu năng tối đa.
"""

import logging
from pathlib import Path
import random
import struct
import subprocess
from typing import Dict, List, Optional, Set, Tuple, Union

from app.config import DEFAULT_TRANSITION_SOUND_VOLUME, SUPPORTED_AUDIO_EXTS, TRANSITION_SOUNDS_DIR

logger = logging.getLogger(__name__)

# Bộ nhớ đệm toàn cục lưu trữ vị trí đỉnh âm lượng của từng file SFX
_GLOBAL_PEAK_CACHE: Dict[str, float] = {}


def get_available_transition_sounds(
    sounds_dir: Optional[Union[str, Path]] = None,
    supported_exts: Optional[Set[str]] = None,
) -> List[Path]:
    """Quét và trả về danh sách các tệp âm thanh chuyển cảnh khả dụng.

    Args:
        sounds_dir: Thư mục chứa các tệp âm thanh (mặc định: TRANSITION_SOUNDS_DIR).
        supported_exts: Tập hợp các phần mở rộng được hỗ trợ (.mp3, .wav, .aac...).

    Returns:
        Danh sách đường dẫn Path trỏ tới các tệp âm thanh hợp lệ (đã sắp xếp).
    """
    target_dir = Path(sounds_dir).resolve() if sounds_dir else TRANSITION_SOUNDS_DIR
    valid_exts = {ext.lower() for ext in (supported_exts or SUPPORTED_AUDIO_EXTS)}

    if not target_dir.exists() or not target_dir.is_dir():
        logger.warning(f"Thư mục âm thanh transition không tồn tại: {target_dir}")
        return []

    sound_files = [
        f for f in sorted(target_dir.iterdir())
        if f.is_file() and f.suffix.lower() in valid_exts and not f.name.startswith(".")
    ]

    return sound_files


def detect_audio_peak_timestamp(
    audio_path: Union[str, Path],
    window_ms: float = 50.0,
    sample_rate: int = 8000,
    cache: Optional[Dict[str, float]] = None,
) -> float:
    """Phân tích dạng sóng âm thanh để tìm thời điểm đạt đỉnh năng lượng (Peak Waveform).

    Sử dụng FFmpeg giải mã nhanh raw PCM (mono s16le ở tần số mẫu thấp 8000Hz)
    kết hợp thuật toán cửa sổ trượt (Sliding-window Energy Envelope) để xác định
    chính xác thời điểm âm thanh bùng nổ mạnh nhất (ví dụ: đỉnh tiếng whoosh).

    Args:
        audio_path: Đường dẫn tới file âm thanh.
        window_ms: Kích thước cửa sổ trượt tính bằng mili-giây (mặc định: 50ms).
        sample_rate: Tần số lấy mẫu phân tích (mặc định: 8000Hz, đủ chính xác và siêu nhanh).
        cache: Từ điển cache tùy chọn để tra cứu kết quả đã tính toán.

    Returns:
        Thời điểm đạt đỉnh âm lượng (tính bằng giây, dạng float).
    """
    path_obj = Path(audio_path).resolve()
    path_key = str(path_obj)

    peak_cache = cache if cache is not None else _GLOBAL_PEAK_CACHE
    if path_key in peak_cache:
        return peak_cache[path_key]

    if not path_obj.exists():
        logger.warning(f"File âm thanh không tồn tại khi phân tích peak: {path_obj}")
        return 0.0

    try:
        cmd = [
            "ffmpeg",
            "-v", "error",
            "-i", str(path_obj),
            "-f", "s16le",
            "-ac", "1",
            "-ar", str(sample_rate),
            "-",
        ]
        proc = subprocess.run(cmd, capture_output=True, check=True, timeout=10)
        raw_data = proc.stdout

        total_samples = len(raw_data) // 2
        if total_samples == 0:
            peak_cache[path_key] = 0.0
            return 0.0

        samples = struct.unpack(f"<{total_samples}h", raw_data)
        window_size = max(1, int(sample_rate * (window_ms / 1000.0)))

        if len(samples) <= window_size:
            peak_time = round(len(samples) / 2.0 / sample_rate, 3)
            peak_cache[path_key] = peak_time
            return peak_time

        # Thuật toán cửa sổ trượt tính tổng năng lượng (Sliding-window Envelope)
        current_energy = sum(abs(s) for s in samples[:window_size])
        max_energy = current_energy
        max_win_idx = 0

        for i in range(1, len(samples) - window_size + 1):
            current_energy += abs(samples[i + window_size - 1]) - abs(samples[i - 1])
            if current_energy > max_energy:
                max_energy = current_energy
                max_win_idx = i

        peak_time = round((max_win_idx + window_size // 2) / float(sample_rate), 3)
        peak_cache[path_key] = peak_time
        logger.debug(f"Đã phát hiện đỉnh waveform cho '{path_obj.name}': {peak_time:.3f}s")
        return peak_time

    except Exception as err:
        logger.warning(f"Không thể phân tích đỉnh waveform cho '{path_obj.name}' ({err}), fallback về 0.0s")
        peak_cache[path_key] = 0.0
        return 0.0


def pick_random_transition_sound(
    sounds_dir: Optional[Union[str, Path]] = None,
    seed: Optional[int] = None,
) -> Optional[Path]:
    """Chọn ngẫu nhiên 1 tệp âm thanh từ thư mục transition sounds.

    Args:
        sounds_dir: Thư mục chứa âm thanh chuyển cảnh.
        seed: Hạt giống ngẫu nhiên tùy chọn để tái lập kết quả.

    Returns:
        Path tới file âm thanh được chọn, hoặc None nếu thư mục rỗng.
    """
    sounds = get_available_transition_sounds(sounds_dir)
    if not sounds:
        logger.warning("Không tìm thấy tệp âm thanh chuyển cảnh nào trong thư mục.")
        return None

    rng = random.Random(seed) if seed is not None else random
    chosen = rng.choice(sounds)
    logger.debug(f"Đã chọn ngẫu nhiên âm thanh transition: '{chosen.name}'")
    return chosen


def allocate_transition_sounds(
    transition_count: int,
    sounds_dir: Optional[Union[str, Path]] = None,
    seed: Optional[int] = None,
) -> List[Optional[Path]]:
    """Phân bổ âm thanh chuyển cảnh cho K điểm giao thoa giữa các scenes bằng cyclic-shuffle.

    Đảm bảo:
    - Nếu không có file âm thanh: trả về danh sách toàn None (fallback an toàn).
    - Nếu chỉ có 1 file: áp dụng file đó cho tất cả các điểm chuyển cảnh.
    - Nếu có từ 2 file trở lên: phân phối đều và tránh lặp 2 file giống nhau ở 2 chuyển cảnh liên tiếp.

    Args:
        transition_count: Số lượng điểm chuyển cảnh cần phân bổ.
        sounds_dir: Thư mục chứa âm thanh chuyển cảnh.
        seed: Hạt giống ngẫu nhiên tùy chọn.

    Returns:
        Danh sách gồm transition_count phần tử là Path (hoặc None).
    """
    if transition_count <= 0:
        return []

    sounds = get_available_transition_sounds(sounds_dir)
    if not sounds:
        logger.warning(
            "Không có file âm thanh chuyển cảnh nào trong thư mục, "
            "video sẽ render mà không có hiệu ứng âm thanh transition."
        )
        return [None] * transition_count

    if len(sounds) == 1:
        return [sounds[0]] * transition_count

    rng = random.Random(seed) if seed is not None else random
    allocated: List[Optional[Path]] = []

    while len(allocated) < transition_count:
        shuffled = list(sounds)
        rng.shuffle(shuffled)
        # Tránh phần tử đầu của chu kỳ mới trùng với phần tử cuối của chu kỳ cũ
        if allocated and len(shuffled) > 1 and shuffled[0] == allocated[-1]:
            shuffled[0], shuffled[-1] = shuffled[-1], shuffled[0]
        allocated.extend(shuffled)

    return allocated[:transition_count]


class TransitionSoundSelector:
    """Enterprise service quản lý, phân bổ và căn đỉnh Waveform cho Transition SFX."""

    def __init__(self, sounds_dir: Optional[Union[str, Path]] = None):
        self.sounds_dir = Path(sounds_dir).resolve() if sounds_dir else TRANSITION_SOUNDS_DIR
        self._peak_cache: Dict[str, float] = {}

    @property
    def available_sounds(self) -> List[Path]:
        """Danh sách các tệp âm thanh transition khả dụng."""
        return get_available_transition_sounds(self.sounds_dir)

    def get_peak_timestamp(self, audio_path: Path) -> float:
        """Lấy thời điểm đỉnh waveform của file âm thanh (sử dụng cache)."""
        return detect_audio_peak_timestamp(audio_path, cache=self._peak_cache)

    def pick_random(self, seed: Optional[int] = None) -> Optional[Path]:
        """Chọn ngẫu nhiên 1 âm thanh transition."""
        return pick_random_transition_sound(self.sounds_dir, seed=seed)

    def allocate(
        self,
        transition_count: int,
        seed: Optional[int] = None,
    ) -> List[Tuple[Optional[Path], float]]:
        """Phân bổ danh sách các tệp âm thanh kèm thời điểm đỉnh waveform tương ứng.

        Args:
            transition_count: Số lượng điểm chuyển cảnh.
            seed: Hạt giống ngẫu nhiên.

        Returns:
            Danh sách gồm các tuple: (sound_path, peak_timestamp_in_seconds).
        """
        allocated_paths = allocate_transition_sounds(
            transition_count=transition_count,
            sounds_dir=self.sounds_dir,
            seed=seed,
        )

        result: List[Tuple[Optional[Path], float]] = []
        for path in allocated_paths:
            if path is not None:
                peak_ts = self.get_peak_timestamp(path)
                result.append((path, peak_ts))
            else:
                result.append((None, 0.0))

        return result
