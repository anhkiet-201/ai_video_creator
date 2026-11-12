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
        self.session_usage_counts: Dict[Path, int] = defaultdict(int)
        self.session_used_intervals: Dict[Path, List[Tuple[float, float]]] = defaultdict(list)

    def reset_session(self) -> None:
        """Xóa sạch bộ nhớ phiên cũ để sẵn sàng cho phiên render batch mới."""
        self.session_usage_counts.clear()
        self.session_used_intervals.clear()

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
                span = max_start - chosen_start
                # Dynamic Sector Jumping: Chia khoảng thời gian thành các phân khu (Early, Mid, Late)
                # để nhảy pha phi tuyến tính, tránh việc cắt dồn ở đầu clip (0.0s) khi clip đủ dài.
                if span >= 2.0:
                    sectors = [
                        (chosen_start + span * 0.08, chosen_start + span * 0.38),
                        (chosen_start + span * 0.38, chosen_start + span * 0.70),
                        (chosen_start + span * 0.70, chosen_start + span * 0.96),
                    ]
                    sec_start, sec_end = random_gen.choice(sectors)
                    start_time = random_gen.uniform(sec_start, sec_end)
                else:
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
        plan_index: Optional[int] = None,
        session_aware: Optional[bool] = None,
    ) -> List[SegmentCutPlan]:
        """Phân bổ tối ưu toàn bộ các cảnh vào kho video nguồn.

        Hỗ trợ phân bổ phi tuyến tính (Non-linear Shuffled Allocation) và
        luân chuyển tư liệu toàn phiên (Cross-Plan Session Tracking):
        1. Xáo trộn ngẫu nhiên toàn bộ ứng viên bằng Fisher-Yates shuffle.
        2. Chống lặp nội bộ: Không trùng video trong cùng một plan khi kho footage đủ lớn.
        3. Phủ tối đa: Khai thác hết toàn bộ video trong session trước khi tái sử dụng.
        4. Cắt nhảy pha: Dynamic Sector Jumping tránh cắt tuyến tính từ đầu file.

        Args:
            scene_durations: Danh sách thời lượng (giây) của từng scene theo thứ tự kịch bản.
            source_videos_info: Dict ánh xạ Path video nguồn -> duration (giây).
            seed: Seed ngẫu nhiên tùy chọn để tái lập kết quả.
            plan_index: Chỉ số kịch bản trong batch (1, 2, 3...) giúp sinh seed phi tuyến tính.
            session_aware: Nếu True, lưu vết và ưu tiên video chưa dùng trong toàn session.
                           Mặc định tự động bật khi plan_index được cung cấp.

        Returns:
            Danh sách SegmentCutPlan cho từng scene.
        """
        if not source_videos_info:
            raise ValueError("Không có video nguồn nào được cung cấp để phân bổ!")
        if not scene_durations:
            return []

        is_session_aware = session_aware if session_aware is not None else (plan_index is not None)

        # Khởi tạo bộ sinh số ngẫu nhiên với entropy phi tuyến tính
        if seed is not None:
            effective_seed = seed + (plan_index * 10007 if plan_index is not None else 0)
            rng = random.Random(effective_seed)
        elif self.seed is not None:
            effective_seed = self.seed + (plan_index * 10007 if plan_index is not None else 0)
            rng = random.Random(effective_seed)
        else:
            rng = random.Random()

        # Xáo trộn sâu danh sách video nguồn bằng Fisher-Yates để triệt tiêu thứ tự hệ thống tập tin
        all_videos = list(source_videos_info.keys())
        rng.shuffle(all_videos)

        plan_used_intervals: Dict[Path, List[Tuple[float, float]]] = defaultdict(list)
        plan_usage_counts: Dict[Path, int] = {p: 0 for p in all_videos}
        last_chosen_video: Optional[Path] = None

        plans: List[SegmentCutPlan] = []

        for scene_idx, audio_dur in enumerate(scene_durations):
            target_dur = max(0.5, float(audio_dur))

            # 1. Lọc video ứng viên: Loại trừ video liền kề trước đó nếu có > 1 video
            if len(all_videos) > 1 and last_chosen_video is not None:
                candidate_videos = [v for v in all_videos if v != last_chosen_video]
            else:
                candidate_videos = list(all_videos)

            # 2. Ràng buộc chống lặp nội bộ kịch bản:
            # Nếu còn video chưa dùng trong plan hiện tại, bắt buộc chỉ chọn trong nhóm chưa dùng
            fresh_in_plan = [v for v in candidate_videos if plan_usage_counts[v] == 0]
            search_pool = fresh_in_plan if fresh_in_plan else candidate_videos

            # 3. Phân loại ưu tiên đa tầng (Multi-Tier Priority)
            # Tier 1: Video CHƯA TỪNG ĐƯỢC SỬ DỤNG TRONG TOÀN BỘ PHIÊN (Session-wide fresh)
            if is_session_aware:
                tier_1_session_fresh = [
                    v for v in search_pool
                    if self.session_usage_counts[v] == 0
                    and plan_usage_counts[v] == 0
                    and source_videos_info[v] >= target_dur
                ]
            else:
                tier_1_session_fresh = []

            # Tier 2: Video CHƯA DÙNG TRONG PLAN NÀY và đủ độ dài >= target_dur
            tier_2_plan_fresh = [
                v for v in search_pool
                if plan_usage_counts[v] == 0 and source_videos_info[v] >= target_dur
            ]

            # Tier 3: Video có khoảng trống tự do (free gap) >= target_dur
            tier_3_has_gap: List[Path] = []
            for v in search_pool:
                v_dur = source_videos_info[v]
                if v_dur >= target_dur:
                    combined_history = list(plan_used_intervals[v])
                    if is_session_aware and self.session_used_intervals[v]:
                        combined_history.extend(self.session_used_intervals[v])
                    free_gaps = self.find_free_intervals(v_dur, combined_history)
                    if any((f_end - f_start) >= target_dur for f_start, f_end in free_gaps):
                        tier_3_has_gap.append(v)

            # Tier 4: Video có độ dài >= target_dur
            tier_4_long_enough = [
                v for v in search_pool
                if source_videos_info[v] >= target_dur
            ]

            # Tier 5: Video ngắn hơn target_dur (buộc phải stream_loop)
            tier_5_short = [
                v for v in search_pool
                if source_videos_info[v] < target_dur
            ]

            # 4. Lựa chọn video tốt nhất theo mức ưu tiên
            chosen_video: Path
            if tier_1_session_fresh:
                chosen_video = rng.choice(tier_1_session_fresh)
            elif tier_2_plan_fresh:
                # Ưu tiên các video có số lần sử dụng thấp nhất trong toàn bộ session
                min_sess_usage = min(self.session_usage_counts[v] for v in tier_2_plan_fresh)
                sub_pool = [v for v in tier_2_plan_fresh if self.session_usage_counts[v] == min_sess_usage]
                chosen_video = rng.choice(sub_pool)
            elif tier_3_has_gap:
                min_usage_val = min(
                    (self.session_usage_counts[v] if is_session_aware else plan_usage_counts[v])
                    for v in tier_3_has_gap
                )
                sub_pool = [
                    v for v in tier_3_has_gap
                    if (self.session_usage_counts[v] if is_session_aware else plan_usage_counts[v]) == min_usage_val
                ]
                chosen_video = rng.choice(sub_pool)
            elif tier_4_long_enough:
                min_usage = min(plan_usage_counts[v] for v in tier_4_long_enough)
                sub_pool = [v for v in tier_4_long_enough if plan_usage_counts[v] == min_usage]
                chosen_video = rng.choice(sub_pool)
            else:
                min_usage = min(plan_usage_counts[v] for v in tier_5_short)
                sub_pool = [v for v in tier_5_short if plan_usage_counts[v] == min_usage]
                chosen_video = rng.choice(sub_pool)

            # 5. Xác định start_time phi tuyến tính kết hợp lịch sử cắt
            v_dur = source_videos_info[chosen_video]
            history_intervals = list(plan_used_intervals[chosen_video])
            if is_session_aware and self.session_used_intervals[chosen_video]:
                history_intervals.extend(self.session_used_intervals[chosen_video])

            start_time, loop_needed, overlap_ratio = self.pick_start_time(
                video_duration=v_dur,
                target_duration=target_dur,
                used_intervals=history_intervals,
                rng=rng,
            )

            # 6. Cập nhật trạng thái cho cả plan và session
            cut_end = min(v_dur, round(start_time + target_dur, 3))
            plan_used_intervals[chosen_video].append((start_time, cut_end))
            plan_usage_counts[chosen_video] += 1

            if is_session_aware:
                self.session_used_intervals[chosen_video].append((start_time, cut_end))
                self.session_usage_counts[chosen_video] += 1

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
