"""Sound Effect (SFX) management and scene audio integration.

Cung cấp dịch vụ quản lý, phân tích thẻ và ghép nối hiệu ứng âm thanh (Sound Effect)
vào kịch bản và luồng dựng video tự động, tuân thủ Clean Architecture & SOLID:
- Tự động quét và định dạng danh sách âm thanh hiệu ứng từ assets/sounds/effect cho AI Prompt.
- Phân tích cú pháp regex cho thẻ sound effect dạng: [sound-effect:<tên file>].
- Đảm bảo thẻ nằm ở cuối câu và tách biệt nội dung thuần túy cho TTS đọc.
- Hợp nhất âm thanh TTS và Sound Effect ở cuối câu với tỷ lệ âm lượng chuẩn xác.
- Đồng bộ tổng thời lượng scene = audio gen thực tế + sound effect.
"""

from collections import OrderedDict
import logging
from pathlib import Path
import re
import subprocess
from typing import Dict, List, Optional, Set, Tuple, Union

import soundfile as sf

from app.config import (
    AUDIO_SAMPLE_RATE,
    DEFAULT_EFFECT_SOUND_VOLUME,
    EFFECT_SOUNDS_DIR,
    SUPPORTED_AUDIO_EXTS,
)

logger = logging.getLogger(__name__)

# Biểu thức chính quy phát hiện thẻ sound effect: [sound-effect:<tên file>]
SOUND_EFFECT_TAG_REGEX = re.compile(r"\[sound-effect:\s*([^\]]+)\]", re.IGNORECASE)


def get_available_sound_effects(
    sounds_dir: Optional[Union[str, Path]] = None,
    supported_exts: Optional[Set[str]] = None,
) -> List[Path]:
    """Quét và trả về danh sách các tệp âm thanh hiệu ứng khả dụng.

    Quy ước đặt tên tệp: <Tên sound> - <Cách sử dụng>.<ext> (.wav, .mp3)
    Ví dụ: 'Ting - Điểm nhấn quyền lợi.mp3', 'Boom - Nhấn mạnh kịch tính.wav'

    Args:
        sounds_dir: Thư mục chứa các tệp âm thanh hiệu ứng (mặc định: EFFECT_SOUNDS_DIR).
        supported_exts: Tập hợp các định dạng được hỗ trợ (.wav, .mp3...).

    Returns:
        Danh sách đường dẫn Path trỏ tới các tệp âm thanh hợp lệ (đã sắp xếp).
    """
    target_dir = Path(sounds_dir).resolve() if sounds_dir else EFFECT_SOUNDS_DIR
    valid_exts = {ext.lower() for ext in (supported_exts or SUPPORTED_AUDIO_EXTS)}

    if not target_dir.exists() or not target_dir.is_dir():
        logger.warning(f"Thư mục âm thanh effect không tồn tại: {target_dir}")
        return []

    sound_files = [
        f for f in sorted(target_dir.iterdir())
        if f.is_file() and f.suffix.lower() in valid_exts and not f.name.startswith(".")
    ]

    return sound_files


def format_sound_effects_for_prompt(
    sounds_dir: Optional[Union[str, Path]] = None,
) -> str:
    """Định dạng danh sách các âm thanh hiệu ứng thành văn bản hướng dẫn cho Gemini AI Prompt.

    Giúp AI hiểu rõ từng tệp hiệu ứng và cách sử dụng tương ứng để quyết định chèn thẻ vào
    scene phù hợp nhất.

    Args:
        sounds_dir: Thư mục chứa hiệu ứng âm thanh (mặc định: EFFECT_SOUNDS_DIR).

    Returns:
        Chuỗi văn bản định dạng danh sách sound effects để chèn vào prompt.
    """
    effects = get_available_sound_effects(sounds_dir)
    if not effects:
        return ""

    lines = [
        "AVAILABLE SOUND EFFECTS (SFX) FOR SCENE HIGHLIGHTS:",
        "Available sound files strictly follow the naming pattern '<Sound Name> - <Usage Description>.<ext>' (.wav, .mp3):",
        "- '<Sound Name>': The auditory sound category/identifier (e.g., Ting, Boom, Whoosh, Chime).",
        "- '<Usage Description>': Explains the designated scene purpose, dramatic mood, or highlight context.",
        "List of available audio files:"
    ]

    for ef in effects:
        # ef.name có dạng: <Tên sound> - <Cách sử dụng>.<ext>
        stem = ef.stem
        if " - " in stem:
            parts = stem.split(" - ", 1)
            sound_name = parts[0].strip()
            usage = parts[1].strip()
            lines.append(f"- '{ef.name}' (Sound: '{sound_name}' | Usage: {usage}) -> Tag: [sound-effect:{ef.name}]")
        else:
            lines.append(f"- '{ef.name}' -> Tag: [sound-effect:{ef.name}]")

    lines.append(
        "\nSOUND EFFECT TAG USAGE RULES:\n"
        "1. Contextual & Non-Formulaic Selection: Inspect the '<Usage Description>' of each file. Choose an effect that authentically matches the scene's specific narrative moment (e.g., sharing a clever tip, a dramatic turning point, confirming honest facts, or a warm closing). STRICTLY FORBIDDEN to lazily default to the same sound across scripts.\n"
        "2. Optional & Dynamic Placement: Sound effects are optional highlights, NOT a mechanical requirement. When used, place the effect where the real dramatic climax occurs (Scene 1, a middle turning point, or the closing outro). Do not mechanically place it in the same scene across all scripts.\n"
        "3. Strict Frequency Limit: Maximum 1 sound effect per script. Most scenes must have NO sound effect to maintain natural human storytelling pacing.\n"
        "4. Strict Placement: When used, the tag [sound-effect:<exact filename>] must always be placed at the very end of the scene's 'srt_script'."
    )

    return "\n".join(lines)


def parse_sound_effect_tag(text: Optional[str]) -> Tuple[str, Optional[str]]:
    """Phân tích và bóc tách thẻ [sound-effect:<tên file>] ra khỏi chuỗi văn bản.

    Tách phần thẻ sound effect để xử lý âm thanh, đồng thời trả về văn bản sạch
    dành cho TTS Engine (giọng đọc AI không bị đọc dính chữ thẻ).

    Args:
        text: Chuỗi văn bản lời thoại (srt_script) có thể chứa thẻ sound-effect.

    Returns:
        Tuple[str, Optional[str]]:
        - str: Văn bản sạch đã loại bỏ thẻ [sound-effect:...].
        - Optional[str]: Tên file hiệu ứng âm thanh cần chèn (hoặc None nếu không có thẻ).
    """
    if not text:
        return "", None

    raw_text = str(text).strip()
    match = SOUND_EFFECT_TAG_REGEX.search(raw_text)
    if not match:
        return raw_text, None

    effect_filename = match.group(1).strip()
    # Loại bỏ thẻ khỏi văn bản
    cleaned = SOUND_EFFECT_TAG_REGEX.sub("", raw_text)
    # Kéo dấu câu dính sát vào từ đứng trước (nếu việc xóa thẻ để lại khoảng trắng trước dấu câu)
    cleaned = re.sub(r"\s+([,\.!\?:;\-])", r"\1", cleaned)
    # Dọn dẹp khoảng trắng thừa
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned, effect_filename


def find_sound_effect_file(
    sound_identifier: str,
    sounds_dir: Optional[Union[str, Path]] = None,
) -> Optional[Path]:
    """Tìm kiếm file âm thanh hiệu ứng trong thư mục theo tên hoặc tên rút gọn.

    Hỗ trợ tìm kiếm thông minh:
    1. Khớp chính xác tên tệp đầy đủ (ví dụ: 'Ting - Điểm nhấn.mp3').
    2. Khớp không phân biệt hoa thường.
    3. Khớp phần tên gốc không có đuôi (stem match) nếu AI chỉ sinh 'Ting - Điểm nhấn'.
    4. Khớp theo tên sound đầu tiên (trước dấu gạch ngang) nếu AI viết vắn tắt.

    Args:
        sound_identifier: Tên tệp hoặc định danh do AI trả về trong thẻ.
        sounds_dir: Thư mục chứa hiệu ứng âm thanh (mặc định: EFFECT_SOUNDS_DIR).

    Returns:
        Path tới file âm thanh nếu tìm thấy, ngược lại trả về None.
    """
    if not sound_identifier:
        return None

    clean_id = sound_identifier.strip()
    available_files = get_available_sound_effects(sounds_dir)
    if not available_files:
        return None

    # 1. Khớp chính xác tên tệp
    for f in available_files:
        if f.name == clean_id:
            return f

    # 2. Khớp không phân biệt hoa thường
    lower_id = clean_id.lower()
    for f in available_files:
        if f.name.lower() == lower_id:
            return f

    # 3. Khớp theo stem (không đuôi mở rộng)
    id_stem = Path(clean_id).stem.lower()
    for f in available_files:
        if f.stem.lower() == id_stem:
            return f

    # 4. Khớp theo tiền tố sound name (trước dấu ' - ')
    for f in available_files:
        f_prefix = f.stem.split(" - ")[0].strip().lower()
        if f_prefix == id_stem or f_prefix == lower_id:
            return f

    logger.warning(
        f"Không tìm thấy file sound effect khớp với '{sound_identifier}' "
        f"trong thư mục {sounds_dir or EFFECT_SOUNDS_DIR}"
    )
    return None


def get_audio_duration(audio_path: Union[str, Path]) -> float:
    """Lấy thời lượng chuẩn xác của file âm thanh bằng soundfile hoặc ffprobe."""
    p = Path(audio_path).resolve()
    if not p.exists():
        return 0.0

    try:
        info = sf.info(str(p))
        return float(info.duration)
    except Exception:
        pass

    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            str(p),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8", errors="replace")
        dur_str = res.stdout.strip()
        if dur_str:
            return float(dur_str)
    except Exception as e:
        logger.warning(f"Không thể đo thời lượng audio {p} qua ffprobe: {e}")

    return 0.0


def concatenate_tts_and_effect_audio(
    tts_audio_path: Union[str, Path],
    effect_audio_path: Union[str, Path],
    output_path: Union[str, Path],
    effect_volume: float = DEFAULT_EFFECT_SOUND_VOLUME,
    pause_duration: float = 0.0,
) -> Tuple[Path, float]:
    """Hợp nhất file âm thanh giọng đọc TTS và file âm thanh Sound Effect ở cuối câu.

    Quy trình xử lý âm thanh chuẩn FFmpeg:
    1. Đầu vào 0: Âm thanh giọng đọc TTS (thời lượng T_tts).
    2. Đầu vào 1: Âm thanh hiệu ứng Sound Effect (thời lượng T_sfx, chỉnh âm lượng theo effect_volume).
    3. Ghép nối tuần tự: TTS đọc xong -> Sound effect vang lên ở cuối câu -> (Pause duration nếu có).
    4. Thời lượng tổng thể của scene = T_tts + T_sfx (+ pause_duration).

    Args:
        tts_audio_path: Đường dẫn file audio TTS đã tạo.
        effect_audio_path: Đường dẫn file hiệu ứng âm thanh.
        output_path: Đường dẫn lưu file audio hợp nhất.
        effect_volume: Tỷ lệ âm lượng của hiệu ứng (mặc định: 0.6 = 60%).
        pause_duration: Khoảng nghỉ tĩnh đệm thêm ở đuôi scene (giây).

    Returns:
        Tuple[Path, float]: (Đường dẫn file kết quả, Tổng thời lượng thực tế của scene).
    """
    tts_p = Path(tts_audio_path).resolve()
    sfx_p = Path(effect_audio_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    if not tts_p.exists():
        raise FileNotFoundError(f"Không tìm thấy file TTS audio: {tts_p}")
    if not sfx_p.exists():
        raise FileNotFoundError(f"Không tìm thấy file Sound Effect audio: {sfx_p}")

    # Xác định sample rate đồng bộ: ưu tiên đọc trực tiếp từ file TTS để khớp 100% (thường 48000 Hz)
    target_sample_rate = AUDIO_SAMPLE_RATE
    try:
        info = sf.info(str(tts_p))
        if info.samplerate > 0:
            target_sample_rate = int(info.samplerate)
    except Exception as e:
        logger.warning(
            f"Không thể đọc sample rate từ '{tts_p.name}' ({e}), dùng AUDIO_SAMPLE_RATE={target_sample_rate}Hz"
        )

    # Xây dựng filter_complex ghép nối bằng FFmpeg đảm bảo sample rate và kênh âm đồng nhất
    # [0:a]resample target_sample_rate stereo -> [a0]
    # [1:a]volume=vol, resample target_sample_rate stereo -> [a1]
    # [a0][a1]concat=n=2:v=0:a=1[outa]
    vol_clamped = max(0.0, min(2.0, float(effect_volume)))

    if pause_duration > 0.0:
        # Nếu có khoảng nghỉ ở đuôi scene, chèn thêm khoảng tĩnh
        filter_str = (
            f"[0:a]aformat=sample_rates={target_sample_rate}:channel_layouts=stereo[a0];"
            f"[1:a]volume={vol_clamped:.2f},aformat=sample_rates={target_sample_rate}:channel_layouts=stereo[a1];"
            f"aevalsrc=0:d={pause_duration:.3f}:s={target_sample_rate}:c=stereo[apad];"
            f"[a0][a1][apad]concat=n=3:v=0:a=1[outa]"
        )
    else:
        filter_str = (
            f"[0:a]aformat=sample_rates={target_sample_rate}:channel_layouts=stereo[a0];"
            f"[1:a]volume={vol_clamped:.2f},aformat=sample_rates={target_sample_rate}:channel_layouts=stereo[a1];"
            f"[a0][a1]concat=n=2:v=0:a=1[outa]"
        )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(tts_p),
        "-i", str(sfx_p),
        "-filter_complex", filter_str,
        "-map", "[outa]",
        "-c:a", "pcm_s16le",
        "-ar", str(target_sample_rate),
        str(out_p),
    ]

    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        logger.error(f"Lỗi khi ghép nối TTS và Sound Effect qua FFmpeg: {res.stderr}")
        raise RuntimeError(f"FFmpeg ghép nối âm thanh thất bại: {res.stderr[-300:]}")

    measured_duration = get_audio_duration(out_p)
    logger.info(
        f"Ghép nối Sound Effect thành công: '{sfx_p.name}' vào '{tts_p.name}' -> "
        f"'{out_p.name}', tổng thời lượng scene: {measured_duration:.2f}s"
    )

    return out_p, measured_duration


class SoundEffectManager:
    """Enterprise service quản lý Sound Effects, định dạng Prompt và tích hợp âm thanh scene."""

    def __init__(
        self,
        sounds_dir: Optional[Union[str, Path]] = None,
        default_volume: float = DEFAULT_EFFECT_SOUND_VOLUME,
    ):
        self.sounds_dir = Path(sounds_dir).resolve() if sounds_dir else EFFECT_SOUNDS_DIR
        self.default_volume = default_volume

    def get_available_effects(self) -> List[Path]:
        """Lấy danh sách các file sound effect hiện có trong kho."""
        return get_available_sound_effects(self.sounds_dir)

    def format_for_prompt(self) -> str:
        """Định dạng danh sách sound effect cho AI Prompt."""
        return format_sound_effects_for_prompt(self.sounds_dir)

    def parse_tag(self, text: Optional[str]) -> Tuple[str, Optional[str]]:
        """Bóc tách thẻ [sound-effect:<tên file>] khỏi văn bản lời thoại."""
        return parse_sound_effect_tag(text)

    def find_effect(self, sound_identifier: str) -> Optional[Path]:
        """Tìm file sound effect tương ứng trong kho."""
        return find_sound_effect_file(sound_identifier, self.sounds_dir)

    def concatenate_audio(
        self,
        tts_audio_path: Union[str, Path],
        effect_audio_path: Union[str, Path],
        output_path: Union[str, Path],
        volume: Optional[float] = None,
        pause_duration: float = 0.0,
    ) -> Tuple[Path, float]:
        """Ghép nối âm thanh TTS và Sound Effect ở cuối câu."""
        eff_vol = volume if volume is not None else self.default_volume
        return concatenate_tts_and_effect_audio(
            tts_audio_path=tts_audio_path,
            effect_audio_path=effect_audio_path,
            output_path=output_path,
            effect_volume=eff_vol,
            pause_duration=pause_duration,
        )
