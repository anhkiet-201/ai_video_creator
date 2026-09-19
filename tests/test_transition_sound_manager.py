"""Unit tests for TransitionSoundManager and Waveform Peak Detection."""

from pathlib import Path
import shutil
import subprocess
import unittest

from app.services.video_render_engine.transition_sound_manager import (
    TransitionSoundSelector,
    allocate_transition_sounds,
    detect_audio_peak_timestamp,
    get_available_transition_sounds,
    pick_random_transition_sound,
)

TEST_DIR = Path("storage/temp/test_transition_sound_manager")


class TestTransitionSoundManager(unittest.TestCase):
    """Test suite cho module quản lý âm thanh chuyển cảnh và căn đỉnh waveform."""

    @classmethod
    def setUpClass(cls):
        TEST_DIR.mkdir(parents=True, exist_ok=True)

        # Tạo 3 file audio test giả lập âm thanh whoosh với vị trí peak khác nhau
        # File 1: peak ở 0.3s
        cls.sound_1 = TEST_DIR / "whoosh_01.wav"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "sine=frequency=300:duration=0.8",
                "-af", "volume=enable='between(t,0.25,0.35)':volume=5",
                "-c:a", "pcm_s16le", str(cls.sound_1),
            ],
            capture_output=True,
            check=True,
        )

        # File 2: peak ở 0.6s
        cls.sound_2 = TEST_DIR / "whoosh_02.mp3"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "sine=frequency=500:duration=1.0",
                "-af", "volume=enable='between(t,0.55,0.65)':volume=5",
                "-c:a", "libmp3lame", str(cls.sound_2),
            ],
            capture_output=True,
            check=True,
        )

        # File 3: file phụ
        cls.sound_3 = TEST_DIR / "whoosh_03.wav"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "sine=frequency=700:duration=0.6",
                "-c:a", "pcm_s16le", str(cls.sound_3),
            ],
            capture_output=True,
            check=True,
        )

        # File không hợp lệ và file ẩn để kiểm tra bộ lọc
        cls.invalid_file = TEST_DIR / "notes.txt"
        cls.invalid_file.write_text("not an audio file", encoding="utf-8")

        cls.hidden_file = TEST_DIR / ".hidden_sound.wav"
        cls.hidden_file.write_text("hidden", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEST_DIR, ignore_errors=True)

    def test_01_get_available_transition_sounds(self):
        """Kiểm tra quét đúng danh sách file âm thanh hợp lệ và loại bỏ file rác/file ẩn."""
        sounds = get_available_transition_sounds(TEST_DIR)
        sound_names = [s.name for s in sounds]

        self.assertIn("whoosh_01.wav", sound_names)
        self.assertIn("whoosh_02.mp3", sound_names)
        self.assertIn("whoosh_03.wav", sound_names)
        self.assertNotIn("notes.txt", sound_names)
        self.assertNotIn(".hidden_sound.wav", sound_names)

    def test_02_get_available_sounds_empty_or_nonexistent_dir(self):
        """Kiểm tra xử lý an toàn khi thư mục không tồn tại."""
        sounds = get_available_transition_sounds(TEST_DIR / "nonexistent_dir")
        self.assertEqual(sounds, [])

    def test_03_detect_audio_peak_timestamp(self):
        """Kiểm tra thuật toán tìm đỉnh Waveform Envelope cho kết quả chính xác."""
        cache = {}
        # sound_1 được kích hoạt volume lớn ở [0.25, 0.35], đỉnh phải rơi vào ~0.3s
        peak_1 = detect_audio_peak_timestamp(self.sound_1, cache=cache)
        self.assertAlmostEqual(peak_1, 0.3, delta=0.08)
        self.assertIn(str(self.sound_1.resolve()), cache)

        # Lần gọi tiếp theo phải lấy từ cache
        cached_val = detect_audio_peak_timestamp(self.sound_1, cache=cache)
        self.assertEqual(peak_1, cached_val)

        # sound_2 được kích hoạt volume lớn ở [0.55, 0.65], đỉnh phải rơi vào ~0.6s
        peak_2 = detect_audio_peak_timestamp(self.sound_2, cache=cache)
        self.assertAlmostEqual(peak_2, 0.6, delta=0.08)

    def test_04_detect_peak_nonexistent_file(self):
        """Kiểm tra fallback an toàn về 0.0s khi file âm thanh không tồn tại."""
        peak = detect_audio_peak_timestamp(TEST_DIR / "ghost_sound.wav")
        self.assertEqual(peak, 0.0)

    def test_05_pick_random_transition_sound(self):
        """Kiểm tra chọn ngẫu nhiên có tái lập bằng seed."""
        sound_a = pick_random_transition_sound(TEST_DIR, seed=42)
        sound_b = pick_random_transition_sound(TEST_DIR, seed=42)
        self.assertIsNotNone(sound_a)
        self.assertEqual(sound_a, sound_b)

        empty_dir = TEST_DIR / "empty_dir"
        empty_dir.mkdir(exist_ok=True)
        self.assertIsNone(pick_random_transition_sound(empty_dir))

    def test_06_allocate_transition_sounds(self):
        """Kiểm tra phân bổ cyclic-shuffle tránh lặp 2 âm thanh liền kề."""
        allocated = allocate_transition_sounds(transition_count=6, sounds_dir=TEST_DIR, seed=123)
        self.assertEqual(len(allocated), 6)

        # Kiểm tra không có 2 âm thanh liên tiếp bị trùng nhau (vì có 3 file khả dụng)
        for i in range(len(allocated) - 1):
            self.assertNotEqual(allocated[i], allocated[i + 1])

    def test_07_allocate_fallback_when_empty(self):
        """Kiểm tra fallback an toàn trả về danh sách None khi thư mục rỗng."""
        empty_dir = TEST_DIR / "empty_dir_2"
        empty_dir.mkdir(exist_ok=True)
        allocated = allocate_transition_sounds(transition_count=3, sounds_dir=empty_dir)
        self.assertEqual(allocated, [None, None, None])

    def test_08_transition_sound_selector_class(self):
        """Kiểm tra lớp đối tượng TransitionSoundSelector hoạt động đồng bộ."""
        selector = TransitionSoundSelector(sounds_dir=TEST_DIR)
        self.assertGreaterEqual(len(selector.available_sounds), 3)

        allocated_with_peaks = selector.allocate(transition_count=4, seed=99)
        self.assertEqual(len(allocated_with_peaks), 4)

        for path, peak in allocated_with_peaks:
            self.assertIsNotNone(path)
            self.assertGreater(peak, 0.0)


if __name__ == "__main__":
    unittest.main()
