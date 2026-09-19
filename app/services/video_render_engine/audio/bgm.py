"""Background music (BGM) management and randomized selector for Video Render Engine."""

import logging
from pathlib import Path
import random
from typing import List, Optional, Set, Union

from app.config import BGM_SOUNDS_DIR, SUPPORTED_AUDIO_EXTS

logger = logging.getLogger(__name__)


def get_available_bgm(
    bgm_dir: Optional[Union[str, Path]] = None,
    supported_exts: Optional[Set[str]] = None,
) -> List[Path]:
    """Quét và trả về danh sách các tệp nhạc nền BGM khả dụng.

    Args:
        bgm_dir: Thư mục chứa các tệp nhạc nền (mặc định: BGM_SOUNDS_DIR / assets/sounds/bgm).
        supported_exts: Tập hợp các phần mở rộng được hỗ trợ (.wav, .mp3, .m4a...).

    Returns:
        Danh sách các đường dẫn Path trỏ tới các tệp âm thanh hợp lệ (đã sắp xếp).
    """
    target_dir = Path(bgm_dir).resolve() if bgm_dir else BGM_SOUNDS_DIR
    valid_exts = {ext.lower() for ext in (supported_exts or SUPPORTED_AUDIO_EXTS)}

    if not target_dir.exists() or not target_dir.is_dir():
        logger.warning(f"Thư mục BGM không tồn tại hoặc không phải thư mục: {target_dir}")
        return []

    bgm_files = [
        f for f in sorted(target_dir.iterdir())
        if f.is_file() and f.suffix.lower() in valid_exts and not f.name.startswith(".")
    ]

    return bgm_files


def pick_random_bgm(
    bgm_dir: Optional[Union[str, Path]] = None,
    seed: Optional[int] = None,
) -> Optional[Path]:
    """Chọn ngẫu nhiên 1 tệp nhạc nền BGM từ thư mục bgm.

    Args:
        bgm_dir: Thư mục chứa BGM (mặc định: BGM_SOUNDS_DIR).
        seed: Hạt giống ngẫu nhiên tùy chọn để tái lập kết quả.

    Returns:
        Path tới file BGM được chọn, hoặc None nếu thư mục rỗng.
    """
    bgm_files = get_available_bgm(bgm_dir)
    if not bgm_files:
        logger.warning("Không tìm thấy tệp nhạc nền nào trong thư mục BGM.")
        return None

    rng = random.Random(seed) if seed is not None else random
    chosen = rng.choice(bgm_files)
    logger.info(f"Đã chọn ngẫu nhiên BGM: '{chosen.name}' từ {len(bgm_files)} files khả dụng.")
    return chosen


def allocate_bgm_for_plans(
    plan_count: int,
    bgm_dir: Optional[Union[str, Path]] = None,
    seed: Optional[int] = None,
) -> List[Optional[Path]]:
    """Phân bổ nhạc nền BGM cho danh sách N kịch bản (plans) bằng thuật toán cyclic-shuffle.

    Đảm bảo:
    - Nếu chỉ có 1 bài BGM: tất cả N plan sử dụng bài đó.
    - Nếu có nhiều bài BGM: phân bổ đa dạng, tránh lặp lại cùng 1 bài cho các video liên tiếp.
    - Nếu không có bài BGM nào: trả về danh sách toàn None.

    Args:
        plan_count: Số lượng kịch bản/plan cần phân bổ.
        bgm_dir: Thư mục chứa các tệp BGM.
        seed: Hạt giống ngẫu nhiên tùy chọn.

    Returns:
        Danh sách gồm plan_count phần tử là Path tới file BGM (hoặc None).
    """
    if plan_count <= 0:
        return []

    bgm_files = get_available_bgm(bgm_dir)
    if not bgm_files:
        logger.warning("Không có file BGM nào trong thư mục, toàn bộ plans sẽ không có BGM.")
        return [None] * plan_count

    if len(bgm_files) == 1:
        logger.info(f"Chỉ có 1 file BGM '{bgm_files[0].name}', áp dụng cho toàn bộ {plan_count} plans.")
        return [bgm_files[0]] * plan_count

    rng = random.Random(seed) if seed is not None else random
    allocated: List[Optional[Path]] = []

    while len(allocated) < plan_count:
        shuffled = list(bgm_files)
        rng.shuffle(shuffled)
        # Tránh phần tử đầu của vòng mới trùng với phần tử cuối của vòng cũ
        if allocated and len(shuffled) > 1 and shuffled[0] == allocated[-1]:
            shuffled[0], shuffled[-1] = shuffled[-1], shuffled[0]
        allocated.extend(shuffled)

    return allocated[:plan_count]


class BGMSelector:
    """Enterprise service quản lý và tuyển chọn Background Music (BGM) cho Video Render Plans."""

    def __init__(self, bgm_dir: Optional[Union[str, Path]] = None):
        self.bgm_dir = Path(bgm_dir).resolve() if bgm_dir else BGM_SOUNDS_DIR

    @property
    def available_bgm(self) -> List[Path]:
        return get_available_bgm(self.bgm_dir)

    def pick_random(self, seed: Optional[int] = None) -> Optional[Path]:
        return pick_random_bgm(self.bgm_dir, seed=seed)

    def allocate(self, plan_count: int, seed: Optional[int] = None) -> List[Optional[Path]]:
        return allocate_bgm_for_plans(plan_count=plan_count, bgm_dir=self.bgm_dir, seed=seed)
