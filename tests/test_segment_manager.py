"""Unit tests for VideoSegmentAllocator and SegmentCutPlan."""

from pathlib import Path
import unittest

from app.services.video_render_engine.segment_manager import (
    SegmentCutPlan,
    VideoSegmentAllocator,
)


class TestVideoSegmentAllocator(unittest.TestCase):
    """Test suite for VideoSegmentAllocator logic & temporal diversity."""

    def setUp(self):
        self.allocator = VideoSegmentAllocator(seed=42)

    def test_01_merge_intervals(self):
        """Kiểm tra thuật toán gộp các khoảng thời gian bị giao nhau."""
        intervals = [(10.0, 15.0), (5.0, 8.0), (7.0, 12.0), (20.0, 25.0)]
        merged = VideoSegmentAllocator.merge_intervals(intervals)
        # (5.0, 8.0) và (7.0, 12.0) và (10.0, 15.0) gộp thành (5.0, 15.0)
        expected = [(5.0, 15.0), (20.0, 25.0)]
        self.assertEqual(merged, expected)

    def test_02_find_free_intervals(self):
        """Kiểm tra tìm các khoảng thời gian trống chưa bị cắt của video."""
        video_dur = 60.0
        used = [(10.0, 20.0), (35.0, 45.0)]
        free = VideoSegmentAllocator.find_free_intervals(video_dur, used)
        expected = [(0.0, 10.0), (20.0, 35.0), (45.0, 60.0)]
        self.assertEqual(free, expected)

    def test_03_calculate_overlap_duration(self):
        """Kiểm tra tính toán thời lượng giao thoa giữa khoảng mới và các khoảng cũ."""
        used = [(10.0, 20.0), (30.0, 40.0)]
        # Đoạn (15.0, 25.0) bị giao 5s với (10, 20)
        overlap = VideoSegmentAllocator.calculate_overlap_duration(15.0, 25.0, used)
        self.assertAlmostEqual(overlap, 5.0, places=2)

        # Đoạn (22.0, 28.0) hoàn toàn tự do
        overlap_free = VideoSegmentAllocator.calculate_overlap_duration(22.0, 28.0, used)
        self.assertAlmostEqual(overlap_free, 0.0, places=2)

    def test_04_pick_start_time_guarantees_zero_overlap(self):
        """Kiểm tra chọn start_time khi video còn khoảng trống đủ lớn: đảm bảo 0% overlap."""
        video_dur = 30.0
        used = [(0.0, 10.0), (15.0, 25.0)]  # Trống: [10.0, 15.0] (5s) và [25.0, 30.0] (5s)
        target_dur = 4.0

        start_time, loop_needed, overlap_ratio = self.allocator.pick_start_time(
            video_duration=video_dur,
            target_duration=target_dur,
            used_intervals=used,
        )

        self.assertFalse(loop_needed)
        self.assertEqual(overlap_ratio, 0.0)
        # Vị trí cắt phải nằm trong [10, 11] hoặc [25, 26]
        in_first_gap = 10.0 <= start_time <= 11.0
        in_second_gap = 25.0 <= start_time <= 26.0
        self.assertTrue(in_first_gap or in_second_gap)

    def test_05_pick_start_time_shorter_video(self):
        """Video ngắn hơn thời lượng scene thì phải kích hoạt loop_needed."""
        video_dur = 2.5
        target_dur = 5.0

        start_time, loop_needed, overlap_ratio = self.allocator.pick_start_time(
            video_duration=video_dur,
            target_duration=target_dur,
            used_intervals=[],
        )
        self.assertEqual(start_time, 0.0)
        self.assertTrue(loop_needed)

    def test_06_adjacent_anti_collision(self):
        """RÀNG BUỘC CỐT LÕI: Không bao giờ có 2 cảnh kề nhau dùng chung 1 video nguồn."""
        video_sources = {
            Path("vid_A.mp4"): 20.0,
            Path("vid_B.mp4"): 20.0,
            Path("vid_C.mp4"): 20.0,
        }
        # Kịch bản 10 cảnh
        scene_durations = [3.0] * 10
        plans = self.allocator.allocate(scene_durations, video_sources, seed=123)

        self.assertEqual(len(plans), 10)
        for i in range(1, len(plans)):
            prev_video = plans[i - 1].video_path
            curr_video = plans[i].video_path
            self.assertNotEqual(
                prev_video,
                curr_video,
                f"Phát hiện 2 cảnh kề nhau ({i-1} và {i}) dùng chung video: '{curr_video.name}'",
            )

    def test_07_all_unique_videos_when_sufficient(self):
        """Khi số lượng video >= số scene: Mỗi cảnh dùng 1 video hoàn toàn độc lập (100% unique)."""
        video_sources = {
            Path(f"vid_{i}.mp4"): 15.0
            for i in range(1, 10)
        }
        # 6 cảnh với 9 video
        scene_durations = [3.0] * 6
        plans = self.allocator.allocate(scene_durations, video_sources, seed=999)

        chosen_videos = [p.video_path for p in plans]
        unique_videos = set(chosen_videos)
        self.assertEqual(
            len(chosen_videos),
            len(unique_videos),
            "Số video được chọn phải là duy nhất 100% khi kho footage có đủ video.",
        )

    def test_08_non_overlapping_segments_on_single_long_video(self):
        """Khi chỉ có 1 video dài: Các cảnh phải cắt ở các dải thời gian khác nhau (0% overlap)."""
        video_sources = {
            Path("single_long_video.mp4"): 60.0,
        }
        # 5 cảnh, mỗi cảnh 4s -> tổng 20s < 60s
        scene_durations = [4.0] * 5
        plans = self.allocator.allocate(scene_durations, video_sources, seed=777)

        # Kiểm tra không có 2 segment nào bị overlap
        intervals = [(p.start_time, p.start_time + p.duration) for p in plans]
        for i in range(len(intervals)):
            s_i, e_i = intervals[i]
            for j in range(i + 1, len(intervals)):
                s_j, e_j = intervals[j]
                overlap = max(0.0, min(e_i, e_j) - max(s_i, s_j))
                self.assertAlmostEqual(
                    overlap,
                    0.0,
                    places=2,
                    msg=f"Segment {i} ({s_i}-{e_i}) bị đè lên Segment {j} ({s_j}-{e_j})!",
                )
            self.assertEqual(plans[i].overlap_ratio, 0.0)

    def test_09_reproducibility_with_seed(self):
        """Cùng seed phải cho ra kết quả phân bổ giống hệt nhau."""
        video_sources = {
            Path("v1.mp4"): 30.0,
            Path("v2.mp4"): 25.0,
            Path("v3.mp4"): 20.0,
        }
        durations = [3.5, 4.0, 3.0, 5.0, 4.5]

        plans_run1 = self.allocator.allocate(durations, video_sources, seed=100)
        plans_run2 = self.allocator.allocate(durations, video_sources, seed=100)

        for p1, p2 in zip(plans_run1, plans_run2):
            self.assertEqual(p1.video_path, p2.video_path)
            self.assertEqual(p1.start_time, p2.start_time)
            self.assertEqual(p1.duration, p2.duration)

    def test_10_empty_sources_raises_error(self):
        """Ném lỗi rõ ràng khi không có video nguồn nào."""
        with self.assertRaises(ValueError):
            self.allocator.allocate([3.0, 4.0], {})


if __name__ == "__main__":
    unittest.main()
