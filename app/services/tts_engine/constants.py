"""
Constants and configurations for VieNeu-TTS Engine (v3 Turbo).
"""

from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple, Union

import numpy as np



class VieNeuVoice(str, Enum):
    """Danh mục 14 giọng đọc chính thức của VieNeu-TTS v3 Turbo đại diện cho 3 miền Bắc - Trung - Nam."""

    # --- MIỀN BẮC ---
    MINH_DUC = "Minh Đức"       # Nam · Bắc · Phong cách tin tức (Mặc định)
    PHAM_TUYEN = "Phạm Tuyên"   # Nam · Bắc · Phong cách tự nhiên
    THANH_BINH = "Thanh Bình"   # Nam · Bắc · Phong cách kể chuyện
    MAI_ANH = "Mai Anh"         # Nữ · Bắc · Phong cách tin tức
    TRUC_LY = "Trúc Ly"         # Nữ · Bắc · Phong cách tự nhiên
    NGOC_LINH = "Ngọc Linh"     # Nữ · Bắc · Phong cách kể chuyện
    DOAN_TRANG = "Đoan Trang"   # Nữ · Bắc · Phong cách tự nhiên

    # --- MIỀN NAM ---
    THAI_SON = "Thái Sơn"       # Nam · Nam · Phong cách kể chuyện
    XUAN_VINH = "Xuân Vĩnh"     # Nam · Nam · Phong cách tự nhiên
    MINH_TRIET = "Minh Triết"   # Nam · Nam · Phong cách tin tức
    THUY_DUNG = "Thùy Dung"     # Nữ · Nam · Phong cách tin tức
    THUC_DOAN = "Thục Đoan"     # Nữ · Nam · Phong cách kể chuyện

    # --- MIỀN TRUNG ---
    QUANG_SON = "Quang Sơn"     # Nam · Trung · Phong cách tự nhiên
    NGOC_TRAN = "Ngọc Trân"     # Nữ · Trung · Phong cách tự nhiên


# Mode mặc định của VieNeu (v3 Turbo chạy cực nhanh, 48 kHz)
DEFAULT_MODEL_MODE = "v3turbo"

# Ngôn ngữ mặc định
DEFAULT_LANGUAGE = "vi"

# Tốc độ đọc mặc định (1.0x)
DEFAULT_SPEED = 1.0

# Giọng đọc mặc định
DEFAULT_VOICE = VieNeuVoice.MINH_DUC.value

# Tần số lấy mẫu mặc định của VieNeu-TTS (48 kHz chất lượng phòng thu)
DEFAULT_SAMPLE_RATE = 48000

# Tốc độ đọc cơ sở mục tiêu (Words/Syllables Per Second): 3.15 từ/giây (~189 WPM)
# Tỷ lệ chuẩn vàng cho video ngắn: sôi động, cuốn hút, giàu cảm xúc nhưng phát âm tròn trịa, không nuốt chữ
DEFAULT_BASE_TARGET_WPS = 4.15

# Mặc định bật cơ chế tự động đồng bộ tốc độ âm thanh giữa các giọng clone
DEFAULT_SYNC_VOICE_SPEED = True

# Giới hạn co giãn an toàn của thuật toán time-stretch để bảo toàn chất lượng âm thanh tự nhiên
MIN_SAFE_SPEED_FACTOR = 0.75 
MAX_SAFE_SPEED_FACTOR = 1.85

# Các tham số lấy mẫu (Sampling Parameters) tối ưu chất lượng cao cho VieNeu-TTS v3 Turbo:
# - DEFAULT_TEMPERATURE: 0.45 (cân bằng hoàn hảo giữa cảm xúc biểu cảm và tính chuẩn xác, triệt tiêu lỗi vấp tiếng)
# - DEFAULT_TOP_P: 0.90 (loại bỏ các token nhiễu ở đuôi phân phối xác suất)
# - DEFAULT_REPETITION_PENALTY: 1.25 (chống lặp phụ âm đầu và nói lắp khi diễn cảm xúc)
# - DEFAULT_SILENCE_P: 0.18 (khoảng nghỉ tự nhiên để người đọc lấy hơi giữa các vế câu)
# - DEFAULT_CROSSFADE_P: 0.05 (chuyển tiếp mượt mà giữa các chunk, không bị gãy tiếng)
DEFAULT_TEMPERATURE = 0.45
DEFAULT_TOP_P = 0.90
DEFAULT_REPETITION_PENALTY = 1.25
DEFAULT_SILENCE_P = 0.18
DEFAULT_CROSSFADE_P = 0.05
# Thời lượng đệm tĩnh ở đầu audio (giây) để bảo vệ phụ âm đầu câu, chống nuốt từ đầu
DEFAULT_LEADING_SILENCE_DURATION = 0.15

# Ngưỡng nhận diện khoảng lặng (dBFS) để cắt tỉa khoảng tĩnh thừa ở đầu và đuôi audio do model AI sinh ra
DEFAULT_TRIM_SILENCE_THRESHOLD_DB = -45.0
# Khoảng đệm an toàn (giây) giữ lại ở đầu và đuôi sau khi cắt tỉa để bảo toàn phụ âm gió và âm thanh nhẹ
DEFAULT_TRIM_MARGIN_SEC = 0.05
# Ngưỡng thời lượng tối đa cho phép của khoảng lặng bên trong câu nói (giây). Nếu vượt quá ngưỡng này, được coi là khoảng lặng chết rác do model AI kẹt token
DEFAULT_MAX_INTERNAL_SILENCE_SEC = 0.40
# Thời lượng đích sau khi nén khoảng lặng chết bên trong câu nói (giây) để tạo nhịp lấy hơi tự nhiên
DEFAULT_TARGET_INTERNAL_SILENCE_SEC = 0.25


def trim_silence_edges(
    waveform: np.ndarray,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    threshold_db: float = DEFAULT_TRIM_SILENCE_THRESHOLD_DB,
    margin_sec: float = DEFAULT_TRIM_MARGIN_SEC,
    frame_ms: float = 15.0,
) -> np.ndarray:
    """Cắt tỉa khoảng lặng tĩnh thừa ở đầu và đuôi mảng waveform dựa trên năng lượng RMS.
    
    Giúp loại bỏ triệt để khoảng lặng chết (trailing silence) do mô hình AI để lại,
    đảm bảo việc tính toán tốc độ đọc (sync_speed) và thời lượng phân cảnh chính xác 100%.

    Args:
        waveform: Mảng âm thanh 1D float32.
        sample_rate: Tần số lấy mẫu (mặc định 48000 Hz).
        threshold_db: Ngưỡng năng lượng nhận diện âm thanh tĩnh (dBFS, mặc định -45 dBFS).
        margin_sec: Khoảng đệm an toàn giữ lại ở 2 đầu (mặc định 0.05s).
        frame_ms: Độ dài cửa sổ tính RMS (mili-giây, mặc định 15ms).

    Returns:
        Mảng waveform đã được cắt sạch phần tĩnh thừa ở đầu và đuôi.
    """
    if waveform is None or len(waveform) == 0:
        return waveform

    # Chuyển đổi dBFS sang biên độ tuyến tính (Linear Amplitude)
    threshold_linear = 10.0 ** (threshold_db / 20.0)
    frame_size = max(1, int(sample_rate * frame_ms / 1000.0))

    num_frames = len(waveform) // frame_size
    if num_frames == 0:
        return waveform

    reshaped = waveform[:num_frames * frame_size].reshape(num_frames, frame_size)
    frame_rms = np.sqrt(np.mean(reshaped ** 2, axis=1))

    active_frames = np.where(frame_rms >= threshold_linear)[0]
    if len(active_frames) == 0:
        if np.max(np.abs(waveform)) >= threshold_linear:
            return waveform
        return waveform[:0]

    first_frame = int(active_frames[0])
    last_frame = int(active_frames[-1]) + 1

    margin_samples = int(margin_sec * sample_rate)
    start_sample = max(0, first_frame * frame_size - margin_samples)
    end_sample = min(len(waveform), last_frame * frame_size + margin_samples)

    return waveform[start_sample:end_sample]


def compress_internal_silence(
    waveform: np.ndarray,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    max_silence_sec: float = DEFAULT_MAX_INTERNAL_SILENCE_SEC,
    target_silence_sec: float = DEFAULT_TARGET_INTERNAL_SILENCE_SEC,
    threshold_db: float = DEFAULT_TRIM_SILENCE_THRESHOLD_DB,
    frame_ms: float = 20.0,
) -> np.ndarray:
    """Nén các khoảng lặng chết rác (dead silence gaps) kéo dài bất thường ở giữa câu nói.

    Khi mô hình AI chia chunk hoặc gặp thẻ cảm xúc, nó có thể sinh ra các đoạn im lặng kéo dài
    nhiều giây ở giữa câu. Hàm này quét năng lượng RMS và nén bất kỳ khoảng lặng nội bộ nào
    dài hơn `max_silence_sec` về mức `target_silence_sec`, giúp câu thoại luôn dồn dập, tự nhiên,
    không bao giờ bị mất âm hay chết tiếng.

    Args:
        waveform: Mảng âm thanh 1D float32.
        sample_rate: Tần số lấy mẫu (mặc định 48000 Hz).
        max_silence_sec: Thời lượng im lặng tối đa cho phép ở giữa câu (mặc định 0.40s).
        target_silence_sec: Thời lượng nén về (mặc định 0.25s).
        threshold_db: Ngưỡng năng lượng nhận diện âm thanh tĩnh (dBFS, mặc định -45 dBFS).
        frame_ms: Độ dài frame tính RMS (mili-giây, mặc định 20ms).

    Returns:
        Mảng waveform đã được nén sạch các khoảng lặng chết rác ở giữa.
    """
    if waveform is None or len(waveform) == 0:
        return waveform

    threshold_linear = 10.0 ** (threshold_db / 20.0)
    frame_size = max(1, int(sample_rate * frame_ms / 1000.0))
    num_frames = len(waveform) // frame_size
    if num_frames == 0:
        return waveform

    reshaped = waveform[:num_frames * frame_size].reshape(num_frames, frame_size)
    frame_rms = np.sqrt(np.mean(reshaped ** 2, axis=1))
    is_silent = frame_rms < threshold_linear

    max_silence_frames = max(1, int(max_silence_sec * 1000.0 / frame_ms))
    target_silence_samples = max(0, int(target_silence_sec * sample_rate))

    pieces: List[np.ndarray] = []
    cursor = 0
    in_silence = False
    silence_start_frame = 0

    for f_idx in range(num_frames):
        if is_silent[f_idx]:
            if not in_silence:
                in_silence = True
                silence_start_frame = f_idx
        else:
            if in_silence:
                in_silence = False
                silence_frames = f_idx - silence_start_frame
                if silence_frames > max_silence_frames:
                    speech_end_sample = silence_start_frame * frame_size
                    if speech_end_sample > cursor:
                        pieces.append(waveform[cursor:speech_end_sample])
                    if target_silence_samples > 0:
                        pieces.append(np.zeros(target_silence_samples, dtype=waveform.dtype))
                    cursor = f_idx * frame_size

    if cursor < len(waveform):
        if in_silence and (num_frames - silence_start_frame) > max_silence_frames:
            speech_end_sample = silence_start_frame * frame_size
            if speech_end_sample > cursor:
                pieces.append(waveform[cursor:speech_end_sample])
        else:
            pieces.append(waveform[cursor:])

    if not pieces:
        return waveform

    return np.concatenate(pieces)




def format_emotion_cues(text: str) -> str:
    """
    Chuẩn hóa khoảng đệm (spacing & micro-pauses) quanh các thẻ cảm xúc ([cười], [thở dài], [hắng giọng]...).
    
    Tự động bóc tách và loại bỏ thẻ [sound-effect:...] (nếu có) và chuẩn hóa khoảng trắng/dấu câu
    trước khi xử lý, giúp mô hình VieNeu-TTS chuyển tiếp nhịp nhàng giữa lời thoại và các âm thanh cảm xúc,
    ngăn chặn tình trạng vấp tiếng hoặc dính chữ.
    """
    if not text:
        return ""
    import re
    t = text.strip()
    # Loại bỏ thẻ [sound-effect:...] nếu còn sót lại và kéo dấu câu sát từ đứng trước
    t = re.sub(r'\[sound-effect:\s*[^\]]+\]', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s+([,\.!\?:;\-])', r'\1', t)
    t = re.sub(r'\s+', ' ', t).strip()

    # Nếu trước thẻ cảm xúc là dấu câu nhưng dính liền, thêm khoảng trắng
    t = re.sub(r'([,\.!\?:;\-])(\[[^\]]+\])', r'\1 \2', t)
    # Nếu trước thẻ cảm xúc là từ (không có dấu câu), thêm dấu phẩy nhẹ để ngắt nhịp mượt mà
    t = re.sub(r'([^\s,\.!\?:;\-])\s*(\[[^\]]+\])', r'\1, \2', t)
    # Đảm bảo sau thẻ cảm xúc có khoảng trắng trước từ kế tiếp
    t = re.sub(r'(\[[^\]]+\])\s*([^\s,\.!\?:;\-])', r'\1 \2', t)
    # Chuẩn hóa khoảng trắng thừa
    return re.sub(r'\s+', ' ', t).strip()


def estimate_syllables(text: str) -> int:
    """
    Ước lượng chính xác số âm tiết (syllables) của văn bản tiếng Việt.
    
    Sử dụng normalize_to_chunks_v3 của VieNeu để bung đầy đủ các số (ví dụ: '240.000 VNĐ' -> 
    'hai trăm bốn mươi nghìn việt nam đồng') và các từ viết tắt trước khi đếm từ.
    Tự động loại bỏ thẻ [sound-effect:...] để tránh đếm nhầm tên file âm thanh tiếng Anh.
    Đồng thời cộng thêm thời lượng cho các thẻ cảm xúc ([cười], [thở dài]...) để đảm bảo
    mô hình có đủ thời gian thể hiện cảm xúc mà không bị nuốt chữ.
    Fallback sang regex nếu có lỗi ngoại lệ.
    """
    clean = (text or "").strip()
    if not clean:
        return 0

    import re
    # Bóc tách thẻ [sound-effect:...] nếu có trước khi đếm âm tiết
    clean = re.sub(r'\[sound-effect:\s*[^\]]+\]', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\s+([,\.!\?:;\-])', r'\1', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    if not clean:
        return 0

    emotion_count = len(re.findall(r'\[.*?\]', clean))
    emotion_extra = emotion_count * 2  # Mỗi tiếng cười/thở dài chiếm thời lượng tương đương ~2 âm tiết

    try:
        from vieneu_utils.phonemize_text import normalize_to_chunks_v3
        chunks = normalize_to_chunks_v3(clean)
        norm_text = " ".join(chunks) if isinstance(chunks, list) else str(chunks)
        words = re.findall(r"\b\w+\b", norm_text)
        if words:
            return len(words) + emotion_extra
    except Exception:
        pass

    words = re.findall(r"\b\w+\b", clean)
    return max(len(words) + emotion_extra, 1)


def get_all_voice_names() -> List[str]:
    """Trả về danh sách tất cả các tên giọng đọc hợp lệ."""
    return [v.value for v in VieNeuVoice]


def resolve_voice(voice_input: Optional[Union[str, VieNeuVoice]] = None) -> str:
    """Xác thực và chuyển đổi giá trị đầu vào thành tên giọng đọc chuẩn VieNeuVoice.

    Chấp nhận: instance VieNeuVoice, string tên giọng ("Minh Đức"), string key ("MINH_DUC"),
    giới tính ("nam", "nữ", "female", "male").
    Nếu None, rỗng hoặc các từ khóa ("none", "null", "default"), tự động trả về DEFAULT_VOICE.
    Ném lỗi ValueError nếu giá trị chỉ định không hợp lệ.
    """
    if voice_input is None:
        return DEFAULT_VOICE

    if isinstance(voice_input, VieNeuVoice):
        return voice_input.value

    str_input = str(voice_input).strip()
    if not str_input or str_input.lower() in ("none", "null", "default"):
        return DEFAULT_VOICE

    if str_input.lower() in ("female", "nu", "nữ"):
        return VieNeuVoice.MAI_ANH.value
    if str_input.lower() in ("male", "nam"):
        return VieNeuVoice.MINH_DUC.value

    # Kiểm tra theo string value (ví dụ "Minh Đức", "Thái Sơn") hoặc string enum key (ví dụ "MINH_DUC")
    for v in VieNeuVoice:
        if str_input == v.value or str_input == v.name:
            return v.value

    valid_names = get_all_voice_names()
    raise ValueError(
        f"Giọng đọc '{voice_input}' không hợp lệ! Vui lòng chọn một trong các giọng sau: {valid_names}"
    )


class VoiceRegion(str, Enum):
    """3 vùng miền đặc trưng của giọng nói tiếng Việt."""
    BAC = "bac"
    TRUNG = "trung"
    NAM = "nam"


class VoiceGender(str, Enum):
    """Giới tính của giọng đọc."""
    NAM = "nam"
    NU = "nu"


# Ánh xạ kết hợp (vùng miền, giới tính) -> Preset Voice tương ứng của VieNeu-TTS
VOICE_REGION_GENDER_MAP = {
    (VoiceRegion.NAM, VoiceGender.NAM): VieNeuVoice.THAI_SON.value,
    (VoiceRegion.NAM, VoiceGender.NU): VieNeuVoice.THUY_DUNG.value,
    (VoiceRegion.BAC, VoiceGender.NAM): VieNeuVoice.MINH_DUC.value,
    (VoiceRegion.BAC, VoiceGender.NU): VieNeuVoice.MAI_ANH.value,
    (VoiceRegion.TRUNG, VoiceGender.NAM): VieNeuVoice.QUANG_SON.value,
    (VoiceRegion.TRUNG, VoiceGender.NU): VieNeuVoice.NGOC_TRAN.value,
}


def parse_voice_filename(
    file_path: Union[str, "Path"]
) -> tuple[Optional[VoiceRegion], Optional[VoiceGender]]:
    """
    Phân tích tên file audio ref theo chuẩn: <Tên file>-<vùng miền>-<giới tính>.<ext>.

    Ví dụ:
        phuonghang-nam-nu.wav       -> (VoiceRegion.NAM, VoiceGender.NU)
        chiphien-nam-nam.wav        -> (VoiceRegion.NAM, VoiceGender.NAM)
        tuanduong-bac-nam.wav       -> (VoiceRegion.BAC, VoiceGender.NAM)
        vohalinh-trung-nu.wav       -> (VoiceRegion.TRUNG, VoiceGender.NU)

    Returns:
        tuple (VoiceRegion hoặc None, VoiceGender hoặc None)
    """
    from pathlib import Path
    stem = Path(file_path).stem.lower().strip()
    parts = stem.split("-")

    if len(parts) < 3:
        # Tên file không theo chuẩn 3 phần, thử suy luận nếu có 2 phần
        if len(parts) == 2:
            second = parts[1].strip()
            if second in ("bac", "bắc", "north"):
                return VoiceRegion.BAC, None
            if second in ("trung", "central"):
                return VoiceRegion.TRUNG, None
            if second in ("nam", "south"):
                return VoiceRegion.NAM, None
            if second in ("nu", "nữ", "female", "f"):
                return None, VoiceGender.NU
        return None, None

    raw_region = parts[-2].strip()
    raw_gender = parts[-1].strip()

    # Chuẩn hóa vùng miền
    region: Optional[VoiceRegion] = None
    if raw_region in ("bac", "bắc", "north"):
        region = VoiceRegion.BAC
    elif raw_region in ("trung", "central"):
        region = VoiceRegion.TRUNG
    elif raw_region in ("nam", "south"):
        region = VoiceRegion.NAM

    # Chuẩn hóa giới tính
    gender: Optional[VoiceGender] = None
    if raw_gender in ("nam", "male", "m", "trai"):
        gender = VoiceGender.NAM
    elif raw_gender in ("nu", "nữ", "female", "f", "gai"):
        gender = VoiceGender.NU

    return region, gender


def get_preset_voice_for_clone(
    region: Optional[VoiceRegion] = None,
    gender: Optional[VoiceGender] = None,
) -> str:
    """Trả về preset voice chuẩn VieNeu tương ứng với cặp (region, gender), hoặc DEFAULT_VOICE nếu không khớp."""
    if region is not None and gender is not None:
        matched = VOICE_REGION_GENDER_MAP.get((region, gender))
        if matched:
            return matched

    # Nếu chỉ có region
    if region == VoiceRegion.NAM:
        return VieNeuVoice.THAI_SON.value if gender == VoiceGender.NAM else VieNeuVoice.THUY_DUNG.value
    if region == VoiceRegion.BAC:
        return VieNeuVoice.MINH_DUC.value if gender == VoiceGender.NAM else VieNeuVoice.MAI_ANH.value
    if region == VoiceRegion.TRUNG:
        return VieNeuVoice.QUANG_SON.value if gender == VoiceGender.NAM else VieNeuVoice.NGOC_TRAN.value

    return DEFAULT_VOICE

