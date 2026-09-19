"""Unit tests for SoundEffectManager and Audio Integration."""

from pathlib import Path
import shutil
import subprocess
import sys
import unittest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.services.video_render_engine.sound_effect_manager import (
    SoundEffectManager,
    concatenate_tts_and_effect_audio,
    find_sound_effect_file,
    format_sound_effects_for_prompt,
    get_audio_duration,
    get_available_sound_effects,
    parse_sound_effect_tag,
)

TEST_DIR = Path("storage/temp/test_sound_effect_manager")
SFX_DIR = TEST_DIR / "sfx"
WORK_DIR = TEST_DIR / "work"


class TestSoundEffectManager(unittest.TestCase):
    """Test suite cho module quản lý hiệu ứng âm thanh và tích hợp scene audio."""

    @classmethod
    def setUpClass(cls):
        SFX_DIR.mkdir(parents=True, exist_ok=True)
        WORK_DIR.mkdir(parents=True, exist_ok=True)

        # Tạo file audio hiệu ứng 1: Ting - Quyền lợi hấp dẫn.mp3 (0.3s)
        cls.sfx_1 = SFX_DIR / "Ting - Quyền lợi hấp dẫn.mp3"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "sine=frequency=1000:duration=0.3",
                "-c:a", "libmp3lame", str(cls.sfx_1),
            ],
            capture_output=True,
            check=True,
        )

        # Tạo file audio hiệu ứng 2: Boom - Nhấn mạnh kịch tính.wav (0.4s)
        cls.sfx_2 = SFX_DIR / "Boom - Nhấn mạnh kịch tính.wav"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "sine=frequency=200:duration=0.4",
                "-c:a", "pcm_s16le", str(cls.sfx_2),
            ],
            capture_output=True,
            check=True,
        )

        # Tạo file audio TTS giả lập: speech.wav (0.8s) trong WORK_DIR
        cls.tts_speech = WORK_DIR / "tts_speech.wav"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "sine=frequency=440:duration=0.8",
                "-c:a", "pcm_s16le", str(cls.tts_speech),
            ],
            capture_output=True,
            check=True,
        )

        # File không hợp lệ và file ẩn để kiểm tra bộ lọc
        cls.invalid_file = SFX_DIR / "readme.txt"
        cls.invalid_file.write_text("not an audio file", encoding="utf-8")

        cls.hidden_file = SFX_DIR / ".hidden_sfx.wav"
        cls.hidden_file.write_text("hidden", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEST_DIR, ignore_errors=True)

    def test_01_get_available_sound_effects(self):
        """Kiểm tra quét đúng danh sách file âm thanh hiệu ứng hợp lệ và loại bỏ file rác."""
        effects = get_available_sound_effects(SFX_DIR)
        effect_names = [e.name for e in effects]

        self.assertEqual(len(effects), 2)
        self.assertIn("Ting - Quyền lợi hấp dẫn.mp3", effect_names)
        self.assertIn("Boom - Nhấn mạnh kịch tính.wav", effect_names)
        self.assertNotIn("readme.txt", effect_names)
        self.assertNotIn(".hidden_sfx.wav", effect_names)

    def test_02_format_sound_effects_for_prompt(self):
        """Kiểm tra định dạng danh sách sound effect thành prompt rõ ràng cho AI."""
        prompt_text = format_sound_effects_for_prompt(SFX_DIR)
        self.assertIn("AVAILABLE SOUND EFFECTS", prompt_text)
        self.assertIn("Ting - Quyền lợi hấp dẫn.mp3", prompt_text)
        self.assertIn("Boom - Nhấn mạnh kịch tính.wav", prompt_text)
        self.assertIn("[sound-effect:Ting - Quyền lợi hấp dẫn.mp3]", prompt_text)
        self.assertIn("CUỐI CÂU", prompt_text)

        # Kiểm tra thư mục rỗng trả về chuỗi rỗng
        empty_dir = WORK_DIR / "empty_dir"
        empty_dir.mkdir(parents=True, exist_ok=True)
        self.assertEqual(format_sound_effects_for_prompt(empty_dir), "")

    def test_03_parse_sound_effect_tag(self):
        """Kiểm tra phân tích cú pháp regex bóc tách thẻ [sound-effect:<tên file>] ở cuối câu."""
        # Trường hợp 1: Có thẻ chuẩn ở cuối câu
        text_1 = "Đãi ngộ bao ăn ở máy lạnh cực đã nha mấy bà! [sound-effect:Ting - Quyền lợi hấp dẫn.mp3]"
        clean_1, tag_1 = parse_sound_effect_tag(text_1)
        self.assertEqual(clean_1, "Đãi ngộ bao ăn ở máy lạnh cực đã nha mấy bà!")
        self.assertEqual(tag_1, "Ting - Quyền lợi hấp dẫn.mp3")

        # Trường hợp 2: Có khoảng trắng bên trong thẻ
        text_2 = "Coi chừng bị lừa tiền cọc nha! [sound-effect:   Boom - Nhấn mạnh kịch tính.wav   ]"
        clean_2, tag_2 = parse_sound_effect_tag(text_2)
        self.assertEqual(clean_2, "Coi chừng bị lừa tiền cọc nha!")
        self.assertEqual(tag_2, "Boom - Nhấn mạnh kịch tính.wav")

        # Trường hợp 3: Không có thẻ sound effect (văn bản bình thường hoặc chỉ có emotion tag)
        text_3 = "Ớ chịu không nổi rồi [chuckle], việc nhàn lương cao [cười]!"
        clean_3, tag_3 = parse_sound_effect_tag(text_3)
        self.assertEqual(clean_3, text_3)
        self.assertIsNone(tag_3)

        # Trường hợp 4: Thẻ đứng trước dấu câu (dấu câu không bị cách khoảng trắng)
        text_4 = "Nhanh tay đăng ký nha mấy bà [sound-effect:Ding.mp3]!"
        clean_4, tag_4 = parse_sound_effect_tag(text_4)
        self.assertEqual(clean_4, "Nhanh tay đăng ký nha mấy bà!")
        self.assertEqual(tag_4, "Ding.mp3")

        # Trường hợp 5: Thẻ nằm giữa câu trước dấu phẩy
        text_5 = "Lương 10 củ [sound-effect:Ding.mp3], bao cơm nước nha."
        clean_5, tag_5 = parse_sound_effect_tag(text_5)
        self.assertEqual(clean_5, "Lương 10 củ, bao cơm nước nha.")
        self.assertEqual(tag_5, "Ding.mp3")

        # Trường hợp 6: Nhiều khoảng trắng thừa xung quanh thẻ
        text_6 = "Việc làm máy lạnh    [sound-effect:Ding.mp3]    cực mát."
        clean_6, tag_6 = parse_sound_effect_tag(text_6)
        self.assertEqual(clean_6, "Việc làm máy lạnh cực mát.")
        self.assertEqual(tag_6, "Ding.mp3")

        # Trường hợp 7: Chuỗi rỗng hoặc None
        self.assertEqual(parse_sound_effect_tag(""), ("", None))
        self.assertEqual(parse_sound_effect_tag(None), ("", None))

    def test_04_find_sound_effect_file(self):
        """Kiểm tra tìm file sound effect thông minh (chính xác, case-insensitive, không đuôi)."""
        # 1. Khớp chính xác tên đầy đủ
        found_1 = find_sound_effect_file("Ting - Quyền lợi hấp dẫn.mp3", SFX_DIR)
        self.assertIsNotNone(found_1)
        self.assertEqual(found_1.name, "Ting - Quyền lợi hấp dẫn.mp3")

        # 2. Khớp case-insensitive
        found_2 = find_sound_effect_file("boom - nhấn mạnh kịch tính.wav", SFX_DIR)
        self.assertIsNotNone(found_2)
        self.assertEqual(found_2.name, "Boom - Nhấn mạnh kịch tính.wav")

        # 3. Khớp stem không đuôi mở rộng
        found_3 = find_sound_effect_file("Ting - Quyền lợi hấp dẫn", SFX_DIR)
        self.assertIsNotNone(found_3)
        self.assertEqual(found_3.name, "Ting - Quyền lợi hấp dẫn.mp3")

        # 4. Khớp theo prefix sound name
        found_4 = find_sound_effect_file("Boom", SFX_DIR)
        self.assertIsNotNone(found_4)
        self.assertEqual(found_4.name, "Boom - Nhấn mạnh kịch tính.wav")

        # 5. File không tồn tại trả về None
        self.assertIsNone(find_sound_effect_file("Non_Existent.wav", SFX_DIR))
        self.assertIsNone(find_sound_effect_file("", SFX_DIR))

    def test_05_concatenate_tts_and_effect_audio(self):
        """Kiểm tra ghép nối file TTS và Sound Effect ở cuối câu với thời lượng chính xác."""
        out_audio = WORK_DIR / "combined_scene.wav"
        out_path, total_dur = concatenate_tts_and_effect_audio(
            tts_audio_path=self.tts_speech,
            effect_audio_path=self.sfx_1,
            output_path=out_audio,
            effect_volume=0.8,
            pause_duration=0.0,
        )

        self.assertTrue(out_path.exists())
        # tts_speech (0.8s) + sfx_1 (0.3s) = ~1.1s
        measured = get_audio_duration(out_path)
        self.assertAlmostEqual(measured, 1.1, delta=0.08)
        self.assertAlmostEqual(total_dur, 1.1, delta=0.08)

        # Kiểm tra khi có thêm pause_duration = 0.2s -> ~1.3s
        out_audio_pause = WORK_DIR / "combined_scene_pause.wav"
        _, total_dur_pause = concatenate_tts_and_effect_audio(
            tts_audio_path=self.tts_speech,
            effect_audio_path=self.sfx_2,  # 0.4s
            output_path=out_audio_pause,
            effect_volume=0.6,
            pause_duration=0.2,
        )
        measured_pause = get_audio_duration(out_audio_pause)
        # 0.8s + 0.4s + 0.2s = ~1.4s
        self.assertAlmostEqual(measured_pause, 1.4, delta=0.08)
        self.assertAlmostEqual(total_dur_pause, 1.4, delta=0.08)

    def test_06_sound_effect_manager_class(self):
        """Kiểm tra giao diện SoundEffectManager class theo chuẩn Clean Architecture."""
        manager = SoundEffectManager(sounds_dir=SFX_DIR, default_volume=0.5)

        effects = manager.get_available_effects()
        self.assertEqual(len(effects), 2)

        prompt_str = manager.format_for_prompt()
        self.assertIn("AVAILABLE SOUND EFFECTS", prompt_str)

        clean_text, tag = manager.parse_tag("Đăng ký ngay nha! [sound-effect:Boom - Nhấn mạnh kịch tính.wav]")
        self.assertEqual(clean_text, "Đăng ký ngay nha!")
        self.assertEqual(tag, "Boom - Nhấn mạnh kịch tính.wav")

        found = manager.find_effect(tag)
        self.assertIsNotNone(found)

        out_path = WORK_DIR / "manager_out.wav"
        res_path, dur = manager.concatenate_audio(
            tts_audio_path=self.tts_speech,
            effect_audio_path=found,
            output_path=out_path,
        )
        self.assertTrue(res_path.exists())
        self.assertGreater(dur, 1.0)


if __name__ == "__main__":
    unittest.main()
