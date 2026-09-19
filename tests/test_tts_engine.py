"""
Kiểm thử tự động cho TTSEngine (OmniVoice).
Chạy kiểm thử:
    pytest tests/test_tts_engine.py -v -s
hoặc:
    python tests/test_tts_engine.py
"""

import sys
from pathlib import Path

# Đảm bảo đường dẫn gốc của dự án nằm trong sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import TEMP_DIR
from app.services.tts_engine import TTSEngine


def test_tts_engine_basic_synthesis():
    print("\n=== 1. KIỂM THỬ TỔNG HỢP GIỌNG NÓI CƠ BẢN (VOICE DESIGN) ===")
    engine = TTSEngine()
    out_file = TEMP_DIR / "test_unit_basic.mp3"

    text = "Xin chào, đây là bài kiểm tra tự động cho dịch vụ TTS Engine."
    res_path = engine.synthesize(
        text=text,
        speed=1.1,
        voice="female",
        pitch="+0Hz",
        output_path=out_file
    )

    assert res_path.exists(), f"File {res_path} không tồn tại sau khi tổng hợp."
    assert res_path.stat().st_size > 1000, f"File {res_path} quá nhỏ: {res_path.stat().st_size} bytes."
    dur = engine.get_duration(res_path)
    assert dur > 1.0, f"Thời lượng âm thanh không hợp lệ: {dur}s."
    print(f"-> PASS: Đã sinh thành công {res_path.name} ({dur:.2f}s, {res_path.stat().st_size} bytes)")


def test_tts_engine_speed_and_pitch_normalization():
    print("\n=== 2. KIỂM THỬ CHUẨN HÓA TỐC ĐỘ VÀ CAO ĐỘ (SPEED & PITCH) ===")
    engine = TTSEngine()

    # Kiểm tra chuẩn hóa tốc độ
    assert engine._normalize_speed(1.2) == 1.2
    assert engine._normalize_speed("+20%") == 1.2
    assert engine._normalize_speed("-10%") == 0.9

    # Kiểm tra chuẩn hóa cao độ
    assert engine._normalize_pitch("+0Hz") == "moderate pitch"
    assert engine._normalize_pitch("+5Hz") == "very high pitch"
    assert engine._normalize_pitch("-2Hz") == "low pitch"
    assert engine._normalize_pitch("high pitch") == "high pitch"

    out_file = TEMP_DIR / "test_unit_fast_high.mp3"
    res_path = engine.synthesize(
        text="Tốc độ nhanh và cao độ tươi vui cho video ngắn.",
        speed="+25%",
        voice="female",
        pitch="+5Hz",
        output_path=out_file
    )
    assert res_path.exists() and res_path.stat().st_size > 1000
    print(f"-> PASS: Chuẩn hóa speed và pitch thành công, file tạo ra: {res_path.name}")


def test_tts_engine_voice_clone():
    print("\n=== 3. KIỂM THỬ NHÂN BẢN GIỌNG NÓI (VOICE CLONING) ===")
    engine = TTSEngine()
    sample_ref = TEMP_DIR / "test_unit_basic.mp3"
    assert sample_ref.exists(), "Cần có file mẫu từ test 1."

    out_clone = TEMP_DIR / "test_unit_cloned.mp3"
    res_path = engine.synthesize(
        text="Nội dung đọc với chất giọng được sao chép từ mẫu.",
        speed=1.0,
        voice_clone_path=sample_ref,
        ref_text="Xin chào, đây là bài kiểm tra tự động cho dịch vụ TTS Engine.",
        output_path=out_clone
    )
    assert res_path.exists() and res_path.stat().st_size > 1000
    dur = engine.get_duration(res_path)
    assert dur > 1.0
    print(f"-> PASS: Nhân bản giọng nói thành công ({dur:.2f}s)")


def test_tts_engine_validation_error():
    print("\n=== 4. KIỂM THỬ XỬ LÝ LỖI VALIDATION ===")
    engine = TTSEngine()
    try:
        engine.synthesize(text="   ")
        assert False, "Phải ném ValueError khi text rỗng."
    except ValueError as err:
        print(f"-> PASS: Đã chặn text rỗng thành công ({err})")


def test_resolve_voice_fallback_and_none_handling():
    print("\n=== 4.1 KIỂM THỬ PHÂN GIẢI GIỌNG ĐỌC VÀ FALLBACK VOICE=NONE ===")
    from app.services.tts_engine.constants import DEFAULT_VOICE, resolve_voice

    # Kiểm tra các trường hợp None / rỗng / từ khóa fallback
    assert resolve_voice(None) == DEFAULT_VOICE
    assert resolve_voice("None") == DEFAULT_VOICE
    assert resolve_voice("null") == DEFAULT_VOICE
    assert resolve_voice("default") == DEFAULT_VOICE
    assert resolve_voice("") == DEFAULT_VOICE
    assert resolve_voice("   ") == DEFAULT_VOICE

    # Kiểm tra alias giới tính
    assert resolve_voice("female") == "Mai Anh"
    assert resolve_voice("male") == "Minh Đức"
    assert resolve_voice("nữ") == "Mai Anh"
    assert resolve_voice("nam") == "Minh Đức"

    # Kiểm tra giọng hợp lệ
    assert resolve_voice("Minh Đức") == "Minh Đức"
    assert resolve_voice("Mai Anh") == "Mai Anh"

    # Kiểm tra giọng không tồn tại phải ném ValueError
    try:
        resolve_voice("giong_khong_ton_tai_123")
        assert False, "Phải ném ValueError với tên giọng không tồn tại."
    except ValueError:
        pass

    print("-> PASS: resolve_voice xử lý an toàn tuyệt đối các trường hợp None, null, alias và ném lỗi đúng quy định!")


def test_parse_voice_filename_and_regional_preset():
    print("\n=== 5. KIỂM THỬ NHẬN DIỆN VÙNG MIỀN & GIỚI TÍNH TỪ TÊN FILE ===")
    from app.services.tts_engine import (
        VoiceGender,
        VoiceRegion,
        get_preset_voice_for_clone,
        parse_voice_filename,
    )

    # Test chuẩn 3 phần: <Tên>-<vùng miền>-<giới tính>.<ext>
    r, g = parse_voice_filename("phuonghang-nam-nu.wav")
    assert r == VoiceRegion.NAM and g == VoiceGender.NU
    assert get_preset_voice_for_clone(r, g) == "Thùy Dung"

    r, g = parse_voice_filename("chiphien-nam-nam.wav")
    assert r == VoiceRegion.NAM and g == VoiceGender.NAM
    assert get_preset_voice_for_clone(r, g) == "Thái Sơn"

    r, g = parse_voice_filename("tuanduong-bac-nam.wav")
    assert r == VoiceRegion.BAC and g == VoiceGender.NAM
    assert get_preset_voice_for_clone(r, g) == "Minh Đức"

    r, g = parse_voice_filename("ngockem-bac-nu.wav")
    assert r == VoiceRegion.BAC and g == VoiceGender.NU
    assert get_preset_voice_for_clone(r, g) == "Mai Anh"

    r, g = parse_voice_filename("vohalinh-trung-nu.wav")
    assert r == VoiceRegion.TRUNG and g == VoiceGender.NU
    assert get_preset_voice_for_clone(r, g) == "Ngọc Trân"

    # Test file không theo chuẩn
    r_unknown, g_unknown = parse_voice_filename("unknown_voice.wav")
    assert r_unknown is None and g_unknown is None

    print("-> PASS: Nhận diện vùng miền và giới tính từ tên file thành công 100%!")


def test_estimate_syllables():
    print("\n=== 6. KIỂM THỬ ĐẾM ÂM TIẾT CHUẨN HÓA TIẾNG VIỆT ===")
    from app.services.tts_engine.constants import estimate_syllables

    # Văn bản thông thường
    assert estimate_syllables("Xin chào các bạn") == 4

    # Văn bản có số và ký hiệu tiền tệ / thời gian (phải bung chữ ra trước khi đếm)
    c1 = estimate_syllables("Lương: 240.000 VNĐ")
    # "lương, hai trăm bốn mươi nghìn việt nam đồng" -> ~9 từ
    assert c1 >= 7, f"Số âm tiết bung ra phải >= 7, thực tế: {c1}"

    c2 = estimate_syllables("08:00 – 20:00")
    # "tám giờ không phút, hai mươi giờ không phút" -> ~8 từ
    assert c2 >= 6, f"Số âm tiết bung ra phải >= 6, thực tế: {c2}"

    # Thẻ sound-effect không được làm phình số âm tiết
    c_pure = estimate_syllables("Đăng ký ngay nha mấy bà!")
    c_with_sfx = estimate_syllables("Đăng ký ngay nha mấy bà [sound-effect:Ding - Highlight Key Benefit.mp3]!")
    assert c_pure == c_with_sfx, f"Số âm tiết khi có sound effect ({c_with_sfx}) phải bằng khi không có ({c_pure})"

    print(f"-> PASS: Đếm âm tiết chuẩn hóa số, chữ và miễn nhiễm thẻ sound-effect thành công (Lương 240k VNĐ: {c1} âm tiết, 08:00-20:00: {c2} âm tiết)")


def test_tts_engine_speed_synchronization():
    print("\n=== 7. KIỂM THỬ ĐỒNG BỘ TỐC ĐỘ GIỌNG CLONE (SYNC SPEED) ===")
    engine = TTSEngine()
    text = "Lương 3 ngày thanh toán một lần, môi trường làm việc máy lạnh cực kỳ thoải mái tại công ty Taixin."

    v1 = BASE_DIR / "assets" / "voices" / "tuanduong-bac-nam.wav"
    v2 = BASE_DIR / "assets" / "voices" / "thanhphuong-bac-nu.wav"

    if not v1.exists() or not v2.exists():
        print("-> SKIP: Không tìm thấy đủ 2 file voice mẫu để kiểm thử đồng bộ.")
        return

    out1 = TEMP_DIR / "test_sync_v1.wav"
    out2 = TEMP_DIR / "test_sync_v2.wav"

    p1 = engine.synthesize(text=text, voice_clone_path=v1, output_path=out1, sync_speed=True, target_wps=3.8)
    p2 = engine.synthesize(text=text, voice_clone_path=v2, output_path=out2, sync_speed=True, target_wps=3.8)

    d1 = engine.get_duration(p1)
    d2 = engine.get_duration(p2)
    diff = abs(d1 - d2)

    assert diff <= 0.45, f"Độ lệch thời lượng giữa 2 voice clone quá lớn: {diff:.2f}s (d1={d1:.2f}s, d2={d2:.2f}s)"
    print(f"-> PASS: Tốc độ giữa các giọng clone khác nhau đã được đồng bộ chuẩn xác (độ lệch chỉ {diff:.2f}s)!")


def test_format_emotion_cues_and_expressive_synthesis():
    print("\n=== 8. KIỂM THỬ ĐỊNH DẠNG CẢM XÚC & TỔNG HỢP GIÀU CẢM XÚC (EXPRESSIVE TTS) ===")
    from app.services.tts_engine.constants import format_emotion_cues

    # Test định dạng thẻ cảm xúc
    raw_1 = "Ủa thật không mấy bà ơi [cười] ghê chưa"
    fmt_1 = format_emotion_cues(raw_1)
    assert fmt_1 == "Ủa thật không mấy bà ơi, [cười] ghê chưa", f"Format lỗi: {fmt_1}"

    raw_2 = "Vui quá nè![cười] đúng không?"
    fmt_2 = format_emotion_cues(raw_2)
    assert fmt_2 == "Vui quá nè! [cười] đúng không?", f"Format lỗi: {fmt_2}"

    # Test tự động bóc tách thẻ sound-effect và chuẩn hóa khoảng trắng/dấu câu
    raw_3 = "Đăng ký ngay nha mấy bà [sound-effect:Ding - Highlight Key Benefit.mp3]!"
    fmt_3 = format_emotion_cues(raw_3)
    assert fmt_3 == "Đăng ký ngay nha mấy bà!", f"Chuẩn hóa sfx lỗi: {fmt_3}"

    raw_4 = "Vui ghê [cười] bấm nút liền [sound-effect:Boom.wav], nha!"
    fmt_4 = format_emotion_cues(raw_4)
    assert fmt_4 == "Vui ghê, [cười] bấm nút liền, nha!", f"Chuẩn hóa hỗn hợp lỗi: {fmt_4}"

    print(f"-> PASS: Định dạng thẻ cảm xúc và làm sạch thẻ sound-effect thành công: '{fmt_3}'")

    # Test tổng hợp âm thanh có thẻ cảm xúc
    engine = TTSEngine()
    out_file = TEMP_DIR / "test_emotion_synthesis.wav"
    text = "Ủa thật không mấy bà ơi [cười] ghê chưa! [thở dài] Lương thanh toán đều đặn nha."

    res_path = engine.synthesize(
        text=text,
        voice="Minh Đức",
        speed=1.0,
        output_path=out_file
    )
    assert res_path.exists() and res_path.stat().st_size > 1000
    dur = engine.get_duration(res_path)
    print(f"-> PASS: Tổng hợp âm thanh giàu cảm xúc thành công ({dur:.2f}s, file: {res_path.name})")


def test_trim_silence_edges():
    print("\n=== 9. KIỂM THỬ CẮT TỈA KHOẢNG LẶNG THỪA (SMART SILENCE TRIM) ===")
    import numpy as np
    from app.services.tts_engine.constants import trim_silence_edges

    sr = 48000
    # Tạo waveform nhân tạo: 1.5s silence + 1.0s tone 440Hz biên độ 0.3 + 2.5s silence
    tone = 0.3 * np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, sr, dtype=np.float32))
    lead = np.zeros(int(1.5 * sr), dtype=np.float32)
    trail = np.zeros(int(2.5 * sr), dtype=np.float32)
    raw_w = np.concatenate([lead, tone, trail])
    total_raw_dur = len(raw_w) / sr
    assert abs(total_raw_dur - 5.0) < 0.01

    trimmed_w = trim_silence_edges(raw_w, sample_rate=sr, margin_sec=0.05)
    trimmed_dur = len(trimmed_w) / sr

    # Thời lượng sau khi trim phải xấp xỉ 1.0s tone + 2 * 0.05s margin = 1.10s
    assert abs(trimmed_dur - 1.10) < 0.05, f"Thời lượng sau trim không chuẩn: {trimmed_dur:.2f}s"
    print(f"-> PASS: Đã cắt tỉa từ {total_raw_dur:.2f}s xuống {trimmed_dur:.2f}s chuẩn xác!")

    # Test edge case: mảng rỗng
    empty_w = np.array([], dtype=np.float32)
    assert len(trim_silence_edges(empty_w, sr)) == 0
    print("-> PASS: Xử lý mảng rỗng an toàn.")

    # Test edge case: mảng toàn silence
    all_silence = np.zeros(sr, dtype=np.float32)
    assert len(trim_silence_edges(all_silence, sr)) == 0
    print("-> PASS: Xử lý mảng toàn silence an toàn.")


def test_compress_internal_silence():
    print("\n=== 10. KIỂM THỬ NÉN KHOẢNG LẶNG CHẾT GIỮA CÂU (INTERNAL SILENCE COMPRESSION) ===")
    from app.services.tts_engine import compress_internal_silence
    import numpy as np

    sr = 48000
    t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
    tone1 = 0.5 * np.sin(2 * np.pi * 440 * t)
    # Khoảng lặng chết rác kéo dài 4.0s ở giữa (tương tự lỗi mô hình kẹt token)
    dead_silence = np.zeros(int(4.0 * sr), dtype=np.float32)
    tone2 = 0.5 * np.sin(2 * np.pi * 554 * t)

    raw_w = np.concatenate([tone1, dead_silence, tone2])
    raw_dur = len(raw_w) / sr
    assert abs(raw_dur - 6.0) < 0.01

    # Nén khoảng lặng chết 4.0s về 0.25s
    compressed_w = compress_internal_silence(
        raw_w, sample_rate=sr, max_silence_sec=0.40, target_silence_sec=0.25
    )
    compressed_dur = len(compressed_w) / sr
    expected_dur = 1.0 + 0.25 + 1.0  # 2.25s
    assert abs(compressed_dur - expected_dur) < 0.05, f"Thời lượng sau nén không chuẩn: {compressed_dur:.2f}s (kỳ vọng ~{expected_dur:.2f}s)"
    print(f"-> PASS: Đã nén thành công từ {raw_dur:.2f}s xuống {compressed_dur:.2f}s (xóa sạch 3.75s im lặng rác)!")

    # Test trường hợp khoảng nghỉ lấy hơi tự nhiên ngắn (0.2s <= 0.40s): không được nén
    natural_silence = np.zeros(int(0.2 * sr), dtype=np.float32)
    natural_w = np.concatenate([tone1, natural_silence, tone2])
    kept_w = compress_internal_silence(natural_w, sample_rate=sr, max_silence_sec=0.40, target_silence_sec=0.25)
    assert len(kept_w) == len(natural_w), "Khoảng nghỉ tự nhiên ngắn không được phép bị nén!"
    print("-> PASS: Bảo toàn trọn vẹn khoảng nghỉ nhịp tự nhiên ngắn (0.2s).")

    # Test edge case mảng rỗng
    empty_w = np.array([], dtype=np.float32)
    assert len(compress_internal_silence(empty_w, sr)) == 0
    print("-> PASS: Xử lý mảng rỗng an toàn.")


if __name__ == "__main__":
    test_trim_silence_edges()
    test_compress_internal_silence()
    test_parse_voice_filename_and_regional_preset()
    test_estimate_syllables()
    test_format_emotion_cues_and_expressive_synthesis()
    test_tts_engine_basic_synthesis()
    test_tts_engine_speed_and_pitch_normalization()
    test_tts_engine_voice_clone()
    test_tts_engine_speed_synchronization()
    test_tts_engine_validation_error()
    test_resolve_voice_fallback_and_none_handling()
    print("\n=================================================")
    print("  TẤT CẢ CÁC BÀI TEST TTS ENGINE ĐỀU THÀNH CÔNG! ")
    print("=================================================")


