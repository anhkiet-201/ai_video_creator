"""Voice clone management and randomized voice selector for Video Render Engine."""

import logging
from pathlib import Path
import random
from typing import List, Optional, Set, Union

from app.config import SUPPORTED_VOICE_EXTS, VOICES_DIR

logger = logging.getLogger(__name__)


def get_available_voices(
    voices_dir: Optional[Union[str, Path]] = None,
    supported_exts: Optional[Set[str]] = None,
) -> List[Path]:
    """Quét và trả về danh sách các tệp âm thanh giọng mẫu khả dụng.

    Args:
        voices_dir: Thư mục chứa các tệp âm thanh mẫu (mặc định: VOICES_DIR).
        supported_exts: Tập hợp các phần mở rộng được hỗ trợ (.wav, .mp3...).

    Returns:
        Danh sách các đường dẫn Path trỏ tới các tệp âm thanh hợp lệ (đã sắp xếp).
    """
    target_dir = Path(voices_dir).resolve() if voices_dir else VOICES_DIR
    valid_exts = {ext.lower() for ext in (supported_exts or SUPPORTED_VOICE_EXTS)}

    if not target_dir.exists() or not target_dir.is_dir():
        logger.warning(f"Thư mục voices không tồn tại hoặc không phải thư mục: {target_dir}")
        return []

    voice_files = [
        f for f in sorted(target_dir.iterdir())
        if f.is_file() and f.suffix.lower() in valid_exts and not f.name.startswith(".")
    ]

    return voice_files


def pick_random_voice(
    voices_dir: Optional[Union[str, Path]] = None,
    seed: Optional[int] = None,
) -> Optional[Path]:
    """Chọn ngẫu nhiên 1 tệp âm thanh mẫu từ thư mục voices.

    Args:
        voices_dir: Thư mục chứa voice (mặc định: VOICES_DIR).
        seed: Hạt giống ngẫu nhiên tùy chọn để tái lập kết quả.

    Returns:
        Path tới file âm thanh được chọn, hoặc None nếu thư mục rỗng.
    """
    voices = get_available_voices(voices_dir)
    if not voices:
        logger.warning("Không tìm thấy tệp âm thanh mẫu nào trong thư mục voices.")
        return None

    rng = random.Random(seed) if seed is not None else random
    chosen = rng.choice(voices)
    logger.info(f"Đã chọn ngẫu nhiên voice mẫu: '{chosen.name}' từ {len(voices)} files khả dụng.")
    return chosen


def allocate_voices_for_plans(
    plan_count: int,
    voices_dir: Optional[Union[str, Path]] = None,
    seed: Optional[int] = None,
) -> List[Optional[Path]]:
    """Phân bổ voice clone cho danh sách N kịch bản (plans) bằng thuật toán cyclic-shuffle.

    Đảm bảo:
    - Nếu chỉ có 1 voice: tất cả N plan sử dụng voice đó.
    - Nếu có nhiều voice: phân bổ đa dạng, tránh lặp lại cùng 1 voice cho các video liên tiếp.
    - Nếu không có voice nào: trả về danh sách toàn None (để fallback về preset voice).

    Args:
        plan_count: Số lượng kịch bản/plan cần phân bổ.
        voices_dir: Thư mục chứa voice mẫu.
        seed: Hạt giống ngẫu nhiên tùy chọn.

    Returns:
        Danh sách gồm plan_count phần tử là Path tới file voice (hoặc None).
    """
    if plan_count <= 0:
        return []

    voices = get_available_voices(voices_dir)
    if not voices:
        logger.warning("Không có file voice nào để clone, toàn bộ plans sẽ fallback về preset voice.")
        return [None] * plan_count

    if len(voices) == 1:
        logger.info(f"Chỉ có 1 voice mẫu '{voices[0].name}', áp dụng cho toàn bộ {plan_count} plans.")
        return [voices[0]] * plan_count

    rng = random.Random(seed) if seed is not None else random
    allocated: List[Optional[Path]] = []

    while len(allocated) < plan_count:
        shuffled = list(voices)
        rng.shuffle(shuffled)
        # Tránh phần tử đầu của vòng mới trùng với phần tử cuối của vòng cũ
        if allocated and len(shuffled) > 1 and shuffled[0] == allocated[-1]:
            shuffled[0], shuffled[-1] = shuffled[-1], shuffled[0]
        allocated.extend(shuffled)

    return allocated[:plan_count]


class VoiceCloneSelector:
    """Enterprise service quản lý và tuyển chọn Voice Clone cho Video Render Plans."""

    def __init__(self, voices_dir: Optional[Union[str, Path]] = None):
        self.voices_dir = Path(voices_dir).resolve() if voices_dir else VOICES_DIR

    @property
    def available_voices(self) -> List[Path]:
        return get_available_voices(self.voices_dir)

    def pick_random(self, seed: Optional[int] = None) -> Optional[Path]:
        return pick_random_voice(self.voices_dir, seed=seed)

    def allocate(self, plan_count: int, seed: Optional[int] = None) -> List[Optional[Path]]:
        return allocate_voices_for_plans(plan_count, self.voices_dir, seed=seed)
