"""Video segment allocation and footage diversity management.

Cung cấp thuật toán phân bổ và cắt video segment thông minh (Smart Segment Allocation)
nhằm triệt tiêu trùng lặp giữa các cảnh (scenes), tuân thủ Clean Architecture & SOLID:
- Không bao giờ trùng video giữa 2 cảnh liên tiếp (Adjacent Anti-Collision).
- Phân phối đều toàn bộ tư liệu nguồn (Cyclic Shuffled Distribution).
- Theo dõi lịch sử dải thời gian cắt để đảm bảo không cắt đè (Free Interval Tracking).
- Tìm vị trí cắt có độ chồng chéo tối thiểu (Minimum Overlap) khi kho tư liệu cạn khoảng trống.
"""

from collections import defaultdict
from dataclasses import dataclass
import logging
from pathlib import Path
import random
from typing import Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


@dataclass
class SegmentCutPlan:
    """Kế hoạch cắt phân đoạn video cho một cảnh (scene)."""

    scene_index: int
    video_path: Path
    start_time: float
    duration: float
    loop_needed: bool = False
    overlap_ratio: float = 0.0  # 0.0 = hoàn toàn mới lạ (0% trùng), 1.0 = trùng toàn bộ


class VideoSegmentAllocator:
    """Enterprise-grade Video Segment Allocator.

    Đảm bảo tính đa dạng tuyệt đối của hình ảnh nền giữa các phân cảnh trong video:
    1. Tránh lặp video kề nhau (Adjacent Anti-Collision).
    2. Phân bổ đồng đều và xáo trộn nguồn tài nguyên (Fair & Cyclic Shuffled Allocation).
    3. Quản lý dải thời gian độc lập trên từng video (Non-overlapping Free Interval Search).
    4. Tối thiểu hóa độ chồng chéo khi bắt buộc tái sử dụng video trong điều kiện kho footage hạn hẹp.
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        """Khởi tạo allocator với seed ngẫu nhiên tùy chọn."""
        self.seed = seed

    @staticmethod
    def merge_intervals(intervals: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Gộp các khoảng thời gian bị đè hoặc chạm nhau thành danh sách khoảng rời rạc."""
        if not intervals:
            return []

        sorted_intervals = sorted(intervals, key=lambda x: x[0])
        merged: List[Tuple[float, float]] = []

        curr_start, curr_end = sorted_intervals[0]
        for start, end in sorted_intervals[1:]:
            if start <= curr_end:
                curr_end = max(curr_end, end)
            else:
                merged.append((round(curr_start, 3), round(curr_end, 3)))
                curr_start, curr_end = start, end

        merged.append((round(curr_start, 3), round(curr_end, 3)))
        return merged

    @classmethod
    def find_free_intervals(
        cls,
        video_duration: float,
        used_intervals: Sequence[Tuple[float, float]],
    ) -> List[Tuple[float, float]]:
        """Tìm các khoảng trống thời gian khả dụng (chưa bị cắt) của một video."""
        if video_duration <= 0.0:
            return []

        merged_used = cls.merge_intervals(used_intervals)
        if not merged_used:
            return [(0.0, round(video_duration, 3))]

        free: List[Tuple[float, float]] = []
        current_pos = 0.0

        for start, end in merged_used:
            if start > current_pos + 0.05:  # Khoảng trống tối thiểu 50ms
                free.append((round(current_pos, 3), round(min(start, video_duration), 3)))
            current_pos = max(current_pos, end)
            if current_pos >= video_duration:
                break

        if current_pos + 0.05 < video_duration:
            free.append((round(current_pos, 3), round(video_duration, 3)))

        return free

    @staticmethod
    def calculate_overlap_duration(
        start: float,
        end: float,
        used_intervals: Sequence[Tuple[float, float]],
    ) -> float:
        """Tính tổng thời lượng (giây) bị giao cắt giữa [start, end] và các khoảng đã dùng."""
        total_overlap = 0.0
        for u_start, u_end in used_intervals:
            intersect_start = max(start, u_start)
            intersect_end = min(end, u_end)
            if intersect_end > intersect_start:
                total_overlap += intersect_end - intersect_start
        return round(total_overlap, 3)

    def pick_start_time(
        self,
        video_duration: float,
        target_duration: float,
        used_intervals: Sequence[Tuple[float, float]],
        rng: Optional[random.Random] = None,
    ) -> Tuple[float, bool, float]:
        """Xác định vị trí bắt đầu cắt (start_time) tối ưu nhất từ video.

        Returns:
            Tuple gồm:
            - start_time: Thời điểm bắt đầu cắt (giây)
            - loop_needed: True nếu video ngắn hơn thời lượng cần cắt
            - overlap_ratio: Tỷ lệ trùng lặp với các đoạn đã cắt trước đó (0.0 -> 1.0)
        """
        random_gen = rng or random.Random(self.seed)

        # 1. Trường hợp video ngắn hơn thời lượng yêu cầu: Bắt buộc lặp lại từ đầu
        if video_duration <= target_duration:
            overlap = 1.0 if used_intervals else 0.0
            return 0.0, True, overlap

        free_intervals = self.find_free_intervals(video_duration, used_intervals)

        # 2. Tìm các khoảng trống có độ dài đủ để cắt trọn vẹn (0% overlap)
        valid_free_intervals = [
            (f_start, f_end)
            for f_start, f_end in free_intervals
            if (f_end - f_start) >= target_duration
        ]

        if valid_free_intervals:
            # Chọn ngẫu nhiên 1 khoảng trống (ưu tiên khoảng dài hơn thông qua phân phối ngẫu nhiên)
            chosen_start, chosen_end = random_gen.choice(valid_free_intervals)
            max_start = chosen_end - target_duration
            if max_start > chosen_start:
                start_time = random_gen.uniform(chosen_start, max_start)
            else:
                start_time = chosen_start
            return round(start_time, 3), False, 0.0

        # 3. Khi không còn khoảng trống nào >= target_duration:
        # Tìm vị trí cắt có độ giao cắt (overlap) tối thiểu nhất với các đoạn cũ
        merged_used = self.merge_intervals(used_intervals)
        max_possible_start = video_duration - target_duration

        # Thu thập các điểm ứng viên tiềm năng (biên các khoảng trống và các mốc lưới thời gian)
        candidate_points = {0.0, max_possible_start}
        for f_start, _ in free_intervals:
            if f_start <= max_possible_start:
                candidate_points.add(f_start)
        for _, u_end in merged_used:
            if u_end <= max_possible_start:
                candidate_points.add(u_end)

        # Thêm các điểm lưới mẫu với bước nhảy 0.5s để bao quát toàn bộ video
        step = max(0.5, (max_possible_start) / 40.0) if max_possible_start > 0 else 1.0
        curr = 0.0
        while curr <= max_possible_start:
            candidate_points.add(round(curr, 3))
            curr += step

        best_points: List[float] = []
        min_overlap = float("inf")

        for pt in candidate_points:
            pt = max(0.0, min(pt, max_possible_start))
            overlap_dur = self.calculate_overlap_duration(pt, pt + target_duration, merged_used)
            if overlap_dur < min_overlap - 0.01:
                min_overlap = overlap_dur
                best_points = [pt]
            elif abs(overlap_dur - min_overlap) <= 0.01:
                best_points.append(pt)

        chosen_point = random_gen.choice(best_points) if best_points else 0.0
        overlap_ratio = round(min(1.0, min_overlap / target_duration), 3)

        return round(chosen_point, 3), False, overlap_ratio

    def allocate(
        self,
        scene_durations: Sequence[float],
        source_videos_info: Dict[Path, float],
        seed: Optional[int] = None,
    ) -> List[SegmentCutPlan]:
        """Phân bổ tối ưu toàn bộ các cảnh vào kho video nguồn.

        Args:
            scene_durations: Danh sách thời lượng (giây) của từng scene theo thứ tự kịch bản.
            source_videos_info: Dict ánh xạ Path video nguồn -> duration (giây).
            seed: Seed ngẫu nhiên tùy chọn để tái lập kết quả.

        Returns:
            Danh sách SegmentCutPlan cho từng scene.
        """
        if not source_videos_info:
            raise ValueError("Không có video nguồn nào được cung cấp để phân bổ!")
        if not scene_durations:
            return []

        rng = random.Random(seed if seed is not None else self.seed)
        all_videos = list(source_videos_info.keys())

        used_intervals: Dict[Path, List[Tuple[float, float]]] = defaultdict(list)
        usage_counts: Dict[Path, int] = {p: 0 for p in all_videos}
        last_chosen_video: Optional[Path] = None

        plans: List[SegmentCutPlan] = []

        for scene_idx, audio_dur in enumerate(scene_durations):
            target_dur = max(0.5, float(audio_dur))

            # 1. Lọc video ứng viên: Loại trừ video liền kề trước đó nếu có > 1 video
            if len(all_videos) > 1 and last_chosen_video is not None:
                candidate_videos = [v for v in all_videos if v != last_chosen_video]
            else:
                candidate_videos = list(all_videos)

            # 2. Phân loại mức độ ưu tiên của các video ứng viên
            # Nhóm 1: Video CHƯA TỪNG ĐƯỢC SỬ DỤNG và có độ dài >= target_dur
            tier_1_fresh = [
                v for v in candidate_videos
                if usage_counts[v] == 0 and source_videos_info[v] >= target_dur
            ]

            # Nhóm 2: Video CÒN KHOẢNG TRỐNG TỰ DO (Free interval) >= target_dur
            tier_2_has_gap: List[Path] = []
            if not tier_1_fresh:
                for v in candidate_videos:
                    v_dur = source_videos_info[v]
                    if v_dur >= target_dur:
                        free_gaps = self.find_free_intervals(v_dur, used_intervals[v])
                        if any((f_end - f_start) >= target_dur for f_start, f_end in free_gaps):
                            tier_2_has_gap.append(v)

            # Nhóm 3: Video có độ dài >= target_dur nhưng đã hết khoảng trống hoàn toàn độc lập
            tier_3_long_enough = [
                v for v in candidate_videos
                if source_videos_info[v] >= target_dur
            ]

            # Nhóm 4: Video ngắn hơn target_dur (phải stream_loop)
            tier_4_short = [
                v for v in candidate_videos
                if source_videos_info[v] < target_dur
            ]

            # 3. Lựa chọn video tốt nhất theo mức ưu tiên
            chosen_video: Path
            if tier_1_fresh:
                chosen_video = rng.choice(tier_1_fresh)
            elif tier_2_has_gap:
                # Ưu tiên các video có số lần sử dụng thấp nhất trong nhóm 2
                min_usage = min(usage_counts[v] for v in tier_2_has_gap)
                sub_pool = [v for v in tier_2_has_gap if usage_counts[v] == min_usage]
                chosen_video = rng.choice(sub_pool)
            elif tier_3_long_enough:
                # Ưu tiên các video có số lần dùng ít nhất
                min_usage = min(usage_counts[v] for v in tier_3_long_enough)
                sub_pool = [v for v in tier_3_long_enough if usage_counts[v] == min_usage]
                chosen_video = rng.choice(sub_pool)
            else:
                # Fallback sang nhóm video ngắn
                min_usage = min(usage_counts[v] for v in tier_4_short)
                sub_pool = [v for v in tier_4_short if usage_counts[v] == min_usage]
                chosen_video = rng.choice(sub_pool)

            # 4. Xác định start_time và độ đè overlap
            v_dur = source_videos_info[chosen_video]
            start_time, loop_needed, overlap_ratio = self.pick_start_time(
                video_duration=v_dur,
                target_duration=target_dur,
                used_intervals=used_intervals[chosen_video],
                rng=rng,
            )

            # 5. Cập nhật trạng thái
            cut_end = min(v_dur, round(start_time + target_dur, 3))
            used_intervals[chosen_video].append((start_time, cut_end))
            usage_counts[chosen_video] += 1
            last_chosen_video = chosen_video

            plans.append(
                SegmentCutPlan(
                    scene_index=scene_idx,
                    video_path=chosen_video,
                    start_time=start_time,
                    duration=target_dur,
                    loop_needed=loop_needed,
                    overlap_ratio=overlap_ratio,
                )
            )

        return plans
