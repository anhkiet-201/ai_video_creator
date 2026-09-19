"""
TTSEngine: Service chuyển văn bản thành giọng nói tiếng Việt chất lượng cao
sử dụng mô hình VieNeu-TTS (v3 Turbo, 48 kHz).

Tuân thủ kiến trúc Clean Architecture & SOLID:
- Single Responsibility: Chỉ đảm nhận nhiệm vụ chuyển đổi văn bản sang file âm thanh.
- Tự động chuẩn hóa văn bản tiếng Việt viết hoa, số tiền và từ viết tắt qua VieNeu normalize_to_chunks_v3.
- Hỗ trợ 14 giọng đọc tiếng Việt 3 miền Bắc - Trung - Nam thông qua VieNeuVoice Enum.
- Hỗ trợ Voice Cloning chỉ từ 3 - 5 giây âm thanh mẫu.

Fix tone instability:
- `encode_ref_audio_once()` encodes speaker embedding + ref codes một lần duy nhất
  per (ref_audio_path, session_dir) và cache lại dưới dạng voice dict.
  Mọi scene trong cùng video sẽ share cùng speaker representation,
  loại bỏ nguồn gây drift do denoise/preclean chạy lại nhiều lần.
"""

import logging
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import warnings

import numpy as np
import soundfile as sf
try:
    import torch
except ImportError:
    torch = None


from app.config import TEMP_DIR
from app.services.tts_engine.constants import (
    DEFAULT_BASE_TARGET_WPS,
    DEFAULT_CROSSFADE_P,
    DEFAULT_LEADING_SILENCE_DURATION,
    DEFAULT_MODEL_MODE,
    DEFAULT_REPETITION_PENALTY,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_SILENCE_P,
    DEFAULT_SPEED,
    DEFAULT_SYNC_VOICE_SPEED,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DEFAULT_TRIM_MARGIN_SEC,
    DEFAULT_TRIM_SILENCE_THRESHOLD_DB,
    DEFAULT_VOICE,
    MAX_SAFE_SPEED_FACTOR,
    MIN_SAFE_SPEED_FACTOR,
    VieNeuVoice,
    VoiceGender,
    VoiceRegion,
    estimate_syllables,
    format_emotion_cues,
    get_preset_voice_for_clone,
    parse_voice_filename,
    resolve_voice,
    trim_silence_edges,
    compress_internal_silence,
)

logger = logging.getLogger(__name__)



class TTSEngine:
    """
    Engine chuyển văn bản thành giọng nói chất lượng cao sử dụng VieNeu-TTS (v3 Turbo).
    
    Hỗ trợ 2 chế độ chính:
    1. Preset Voice Mode: Chọn từ danh mục 14 giọng đọc Bắc - Trung - Nam qua VieNeuVoice.
    2. Voice Cloning Mode: Sử dụng file audio mẫu (voice_clone_path) để sao chép giọng nói.
    """

    # Biến cấp lớp (Class-level singleton) lưu model đã tải để tránh tải lại nhiều lần
    _cached_model: Optional[Any] = None
    _cached_mode: Optional[str] = None

    # Cache registered voice name: key = ref_audio path string, value = registered name trong VieNeu
    # Dùng add_voice() để đăng ký voice một lần, sau đó dùng name string trong infer(voice=name).
    # Đây là con đường duy nhất đảm bảo đúng internal normalization pathway của VieNeu.
    # voice=dict bypass normalization → amplitude scale khác ~20% → tai nghe là "khác tone".
    _registered_voice_cache: Dict[str, str] = {}

    def __init__(
        self,
        mode: str = DEFAULT_MODEL_MODE,
        precision: str = "fp32",
    ):
        self.mode = mode
        self.precision = precision

    def _get_or_load_model(self) -> Any:
        """Lazy-load nạp mô hình VieNeu-TTS vào bộ nhớ (chỉ nạp duy nhất một lần)"""
        if TTSEngine._cached_model is not None and TTSEngine._cached_mode == self.mode:
            return TTSEngine._cached_model

        # Tắt các cảnh báo runtime ma trận không quan trọng của ONNX Runtime
        warnings.filterwarnings("ignore", category=RuntimeWarning)

        from vieneu import Vieneu

        logger.info(f"Đang nạp mô hình VieNeu-TTS mode='{self.mode}', precision='{self.precision}'...")
        model = Vieneu(mode=self.mode, precision=self.precision)

        TTSEngine._cached_model = model
        TTSEngine._cached_mode = self.mode
        logger.info(f"Nạp thành công mô hình VieNeu-TTS ({self.mode})")
        return model

    def register_ref_voice_once(
        self,
        ref_audio_path: Union[str, Path],
        *,
        clear_cache: bool = False,
    ) -> str:
        """
        Đăng ký ref_audio vào VieNeu bằng add_voice() và cache lại tên.

        Đây là cách chính xác duy nhất: infer(voice=name_string) dùng đúng
        internal normalization pathway của VieNeu (giống preset voice),
        đảm bảo amplitude/tone nhất quán xuyên suốt tất cả scene.

        voice=dict pathway bị bỏ qua normalization → amplitude khác ~20%
        → tai nghe là "khác tone" — đã xác nhận bằng thực nghiệm.

        Args:
            ref_audio_path: Đường dẫn file âm thanh mẫu.
            clear_cache: Nếu True, xóa cache cũ và re-register.

        Returns:
            Tên voice đã đăng ký trong VieNeu model (dùng làm voice param cho infer()).
        """
        cache_key = str(Path(ref_audio_path).resolve())

        if not clear_cache and cache_key in TTSEngine._registered_voice_cache:
            registered_name = TTSEngine._registered_voice_cache[cache_key]
            logger.debug(f"[TTSEngine] Cache hit: voice '{registered_name}' cho '{Path(ref_audio_path).name}'")
            return registered_name

        model = self._get_or_load_model()
        clone_file = Path(ref_audio_path).resolve()
        if not clone_file.exists():
            raise FileNotFoundError(f"Không tìm thấy file mẫu voice clone: {clone_file}")

        # Trích xuất vùng miền và giới tính từ tên file ref audio (theo chuẩn <Tên>-<vùng miền>-<giới tính>)
        region, gender = parse_voice_filename(clone_file)
        gender_str = "male" if gender == VoiceGender.NAM else ("female" if gender == VoiceGender.NU else "")
        desc_parts = [f"Clone {clone_file.stem}"]
        if region:
            desc_parts.append(f"Miền {region.value.upper()}")
        if gender:
            desc_parts.append(f"Giới tính {gender.value}")
        voice_desc = " · ".join(desc_parts)

        # Tên voice đăng ký: unique per file path để tránh xung đột
        registered_name = f"__clone_{clone_file.stem}_{abs(hash(cache_key)) % 99999}__"

        logger.info(
            f"[TTSEngine] Đăng ký voice clone '{clone_file.name}' vào VieNeu "
            f"với tên '{registered_name}' (lần đầu tiên) [{voice_desc}]..."
        )
        model.add_voice(
            registered_name,
            str(clone_file),
            denoise=True,
            use_ref_codes=True,
            description=voice_desc,
            gender=gender_str,
            save=False,
        )
        TTSEngine._registered_voice_cache[cache_key] = registered_name
        logger.info(
            f"[TTSEngine] Đã đăng ký voice clone '{clone_file.name}' thành công."
        )
        return registered_name


    # ------------------------------------------------------------------ #
    #  Bảo tương thích ngược: giữ encode_ref_audio_once nhưng delegate sang register
    # ------------------------------------------------------------------ #
    def encode_ref_audio_once(
        self,
        ref_audio_path: Union[str, Path],
        *,
        clear_cache: bool = False,
    ) -> str:
        """Alias của register_ref_voice_once() — giữ cho backward compatibility."""
        return self.register_ref_voice_once(ref_audio_path, clear_cache=clear_cache)

    @classmethod
    def clear_ref_audio_cache(cls) -> None:
        """Xóa toàn bộ cache registered voice name (dùng khi bắt đầu session mới)."""
        cls._registered_voice_cache.clear()
        logger.info("[TTSEngine] Đã xóa toàn bộ ref_audio voice cache.")

    def synthesize(
        self,
        text: str,
        speed: Union[float, str] = DEFAULT_SPEED,
        voice: Optional[Union[str, VieNeuVoice]] = DEFAULT_VOICE,
        pitch: float = 0.0,
        voice_clone_path: Optional[Union[str, Path]] = None,
        output_path: Optional[Union[str, Path]] = None,
        seed: Optional[int] = None,
        pause_duration: float = 0.0,
        leading_silence_duration: float = DEFAULT_LEADING_SILENCE_DURATION,
        max_chars: int = 512,
        sync_speed: bool = DEFAULT_SYNC_VOICE_SPEED,
        target_wps: Optional[float] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        repetition_penalty: float = DEFAULT_REPETITION_PENALTY,
        silence_p: float = DEFAULT_SILENCE_P,
        crossfade_p: float = DEFAULT_CROSSFADE_P,
        trim_silence: bool = True,
        trim_threshold_db: float = DEFAULT_TRIM_SILENCE_THRESHOLD_DB,
        trim_margin_sec: float = DEFAULT_TRIM_MARGIN_SEC,
        **kwargs: Any,
    ) -> Path:
        """
        Chuyển đổi văn bản thành file âm thanh giọng nói tiếng Việt tự nhiên.

        Args:
            text: Nội dung văn bản cần đọc (bắt buộc, hỗ trợ cả viết hoa, số, từ viết tắt và thẻ cảm xúc [cười], [thở dài]...).
            speed: Tốc độ đọc (số thực hoặc chuỗi phần trăm, ví dụ: 1.0, "+15%").
            voice: Giọng đọc thuộc VieNeuVoice Enum hoặc tên giọng hợp lệ ("Minh Đức", "Mai Anh", ...).
            pitch: Cao độ giọng nói (hiện chưa được VieNeu v3 Turbo hỗ trợ natively, giữ lại để tương thích API).
            voice_clone_path: Đường dẫn file âm thanh mẫu (.wav, .mp3) để clone giọng (Optional).
                              Khi truyền vào, speaker embedding sẽ được encode và cache lần đầu,
                              các scene kế tiếp dùng lại cache để đảm bảo đồng nhất tone giọng.
            output_path: Đường dẫn file đầu ra mong muốn. Nếu None, tự động sinh trong TEMP_DIR.
            seed: Hạt giống ngẫu nhiên cố định (đảm bảo đồng nhất chất giọng trong cùng video).
            pause_duration: Khoảng nghỉ tĩnh (silence) được đệm thêm vào cuối audio (giây).
            leading_silence_duration: Khoảng đệm tĩnh ở đầu audio (giây, mặc định 0.15s) để bảo vệ phụ âm đầu câu, chống nuốt từ đầu.
            max_chars: Số ký tự tối đa mỗi chunk VieNeu xử lý (default 512).
            sync_speed: Tự động đồng bộ hóa và chuẩn hóa tốc độ đọc (Target Speaking Rate Normalization).
            target_wps: Tốc độ đọc mục tiêu cơ sở (Words/Syllables Per Second). Mặc định None (dùng 3.15 WPS).
            temperature: Độ ngẫu nhiên lấy mẫu token âm thanh (mặc định 0.45: ổn định cao, không vấp, giàu cảm xúc).
            top_p: Ngưỡng lọc token xác suất (mặc định 0.90: lọc token nhiễu).
            repetition_penalty: Phạt lặp lại token âm thanh (mặc định 1.25: chống nói lắp/lặp âm).
            silence_p: Khoảng nghỉ tự nhiên giữa các chunk/mệnh đề để lấy hơi (mặc định 0.18s).
            crossfade_p: Chuyển tiếp mượt giữa các chunk (mặc định 0.05s).
            trim_silence: Tự động cắt tỉa khoảng lặng tĩnh thừa ở đầu và đuôi do AI model sinh ra (mặc định True).
            trim_threshold_db: Ngưỡng nhận diện âm thanh tĩnh (dBFS, mặc định -45 dBFS).
            trim_margin_sec: Khoảng đệm an toàn 2 đầu sau khi cắt tỉa (mặc định 0.05s).

        Returns:
            Path: Đường dẫn trỏ tới file âm thanh đã được tạo thành công.
        """
        # Chuẩn hóa khoảng đệm quanh thẻ cảm xúc ([cười], [thở dài]...) để giữ trọn cảm xúc
        # mà không làm vấp hay dính chữ khi mô hình chuyển tiếp giữa lời thoại và âm thanh cảm xúc
        clean_text = format_emotion_cues(text or "")
        if not clean_text:
            raise ValueError("Tham số 'text' không được để trống khi tổng hợp giọng nói.")

        # 1. Xác định đường dẫn file đầu ra
        target_path = self._resolve_output_path(output_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # 2. Chuẩn hóa tốc độ đọc (speed factor)
        speed_factor = self._normalize_speed(speed)

        # 4. Lấy model đã nạp sẵn trong bộ nhớ
        model = self._get_or_load_model()
        sampling_rate = getattr(model, "sample_rate", DEFAULT_SAMPLE_RATE)

        # 5. Cố định Random Seed cho ONNX Runtime (sử dụng numpy RNG, không phải torch)
        # VieNeu v3 Turbo ONNX dùng np.random.choice() để sample token âm thanh.
        # torch.manual_seed() không có tác dụng với ONNX backend.
        #
        # QUY TẮc: caller (coordinator) chịu trách nhiệm set np.random.seed() MỘT LẦN
        # trước chuỗi scene, KHAI THÁC liên tục mà không reset giữa các scene.
        # Reset seed per-scene khiến mỗi scene bắt đầu từ cùng RNG state → drift do
        # text length khác nhau khiến số token sample khác nhau mỗi call.
        #
        # synthesize() không tự reset — chỉ seed khi seed được cung cấp lần đầu
        # (thường là scene 1), sau đó các scene kế tiếp kế thừa RNG state.
        if seed is not None:
            import numpy as _np
            _np.random.seed(seed % (2**31))  # numpy seed phải trong [0, 2^31-1]
            logger.debug(f"[TTS] np.random.seed({seed % (2**31)}) — chỉ set lần đầu cho scene này")

        # 6. Dọn dẹp cache bộ nhớ GPU trước khi sinh
        if hasattr(torch, "mps") and torch.backends.mps.is_available():
            torch.mps.empty_cache()

        # 7. Thực thi sinh âm thanh qua VieNeu-TTS
        try:
            infer_kwargs: dict = {
                "text": clean_text,
                "apply_watermark": False,
                "temperature": temperature,
                "top_p": top_p,
                "repetition_penalty": repetition_penalty,
                "silence_p": silence_p,
                "crossfade_p": crossfade_p,
            }

            if voice_clone_path is not None:
                clone_file = Path(voice_clone_path).resolve()
                if not clone_file.exists():
                    raise FileNotFoundError(f"Không tìm thấy file mẫu voice clone tại: {clone_file}")

                # Nhận diện vùng miền và giới tính từ tên file ref audio
                region, gender = parse_voice_filename(clone_file)
                base_preset = get_preset_voice_for_clone(region, gender)

                # Dùng add_voice() + infer(voice=name) — đây là con đường duy nhất đảm bảo
                # amplitude/tone nhất quán. voice=dict bỏ qua normalization → khác ~20%.
                # add_voice() cũng chỉ chạy 1 lần nhờ _registered_voice_cache.
                registered_voice_name = self.register_ref_voice_once(clone_file)
                logger.info(
                    f"Đang sinh âm thanh Voice Clone cho '{clean_text[:30]}...' "
                    f"với giọng '{registered_voice_name}' "
                    f"[Vùng miền: {region.value if region else 'Chưa xác định'}, "
                    f"Giới tính: {gender.value if gender else 'Chưa xác định'}, "
                    f"Base Preset: {base_preset}]"
                )
                infer_kwargs["voice"] = registered_voice_name
            else:
                resolved_voice = resolve_voice(voice)
                logger.info(f"Đang sinh âm thanh VieNeu-TTS cho '{clean_text[:30]}...' với giọng: '{resolved_voice}'")
                infer_kwargs["voice"] = resolved_voice


            # max_chars: giới hạn độ dài mỗi chunk để tránh split thành quá nhiều chunk nhỏ.
            # Mặc định 512 (gấp đôi default của VieNeu=256) — giảm số chunk, giảm tone drift
            # ở các scene dài (CTA), đặc biệt ở scene cuối.
            infer_kwargs["max_chars"] = max_chars

            # Sinh waveform âm thanh (float32 numpy array)
            waveform = model.infer(**infer_kwargs)

            if waveform is None or len(waveform) == 0:
                raise RuntimeError("VieNeu-TTS không trả về bất kỳ dữ liệu âm thanh nào.")

            # Log stats waveform để diagnostic tone drift nếu cần
            logger.debug(
                f"[TTS waveform stats] text='{clean_text[:40]}' | "
                f"len={len(waveform)} samples | "
                f"std={float(np.std(waveform)):.4f} | "
                f"max={float(np.max(np.abs(waveform))):.4f}"
            )

            # Đảm bảo waveform là mảng 1D float32
            waveform = np.asarray(waveform, dtype=np.float32)

            # 7b. Cắt tỉa khoảng lặng tĩnh thừa ở đầu và đuôi (Smart Silence Trim)
            # Loại bỏ triệt để trailing/leading silence rác do VieNeu-TTS để lại
            # để đảm bảo việc đo raw_duration và tính sync_speed phản ánh 100% tiếng nói thực tế.
            if trim_silence and len(waveform) > 0:
                before_samples = len(waveform)
                trimmed_w = trim_silence_edges(
                    waveform=waveform,
                    sample_rate=sampling_rate,
                    threshold_db=trim_threshold_db,
                    margin_sec=trim_margin_sec,
                )
                if len(trimmed_w) > 0:
                    trimmed_samples = before_samples - len(trimmed_w)
                    if trimmed_samples > 0:
                        trimmed_sec = trimmed_samples / float(sampling_rate) if sampling_rate > 0 else 0.0
                        logger.info(
                            f"[TTSEngine] Smart Silence Trim: đã cắt tỉa {trimmed_sec:.2f}s khoảng lặng thừa ở 2 đầu "
                            f"(speech thực tế: {len(trimmed_w)/sampling_rate:.2f}s)"
                        )
                    
                    # Nén các khoảng lặng chết rác (internal silence gaps > 0.40s) ở giữa câu
                    compressed_w = compress_internal_silence(
                        waveform=trimmed_w,
                        sample_rate=sampling_rate,
                        threshold_db=trim_threshold_db,
                    )
                    if len(compressed_w) > 0:
                        compressed_samples = len(trimmed_w) - len(compressed_w)
                        if compressed_samples > 0:
                            compressed_sec = compressed_samples / float(sampling_rate) if sampling_rate > 0 else 0.0
                            logger.info(
                                f"[TTSEngine] Internal Silence Compression: đã nén {compressed_sec:.2f}s khoảng lặng chết rác giữa câu "
                                f"(thời lượng sau nén: {len(compressed_w)/sampling_rate:.2f}s)"
                            )
                        waveform = compressed_w
                    else:
                        waveform = trimmed_w

            # 8. Đồng bộ hóa và chuẩn hóa tốc độ đọc (Smart Speaking Rate Synchronization)
            # Nếu sync_speed=True: Tự động đo lường số âm tiết thực tế của văn bản và chuẩn hóa nhịp đọc
            # về tốc độ mục tiêu (Target WPS), loại bỏ hoàn toàn hiện tượng giọng clone nhanh/chậm bất thường.
            if sync_speed:
                raw_samples = len(waveform)
                raw_duration = raw_samples / float(sampling_rate) if sampling_rate > 0 else 0.0

                syllable_count = estimate_syllables(clean_text)
                base_wps = target_wps if target_wps is not None and target_wps > 0 else DEFAULT_BASE_TARGET_WPS
                # Tốc độ đọc mục tiêu có tính đến hệ số speed của người dùng (ví dụ: 2.85 * 1.15 = 3.28 wps)
                effective_target_wps = base_wps * speed_factor

                if raw_duration > 0.1 and syllable_count > 0:
                    measured_wps = syllable_count / raw_duration
                    target_duration = syllable_count / effective_target_wps
                    # Hệ số cần co giãn: ratio = raw_duration / target_duration
                    needed_speed_factor = raw_duration / target_duration

                    # Giới hạn an toàn (Safe Clamping) tránh méo tiếng
                    clamped_factor = min(max(needed_speed_factor, MIN_SAFE_SPEED_FACTOR), MAX_SAFE_SPEED_FACTOR)

                    logger.info(
                        f"[TTSEngine] Đồng bộ tốc độ (Sync Speed): "
                        f"âm tiết={syllable_count}, raw={raw_duration:.2f}s ({measured_wps:.2f} wps) "
                        f"→ target={target_duration:.2f}s ({effective_target_wps:.2f} wps) "
                        f"| Áp dụng hệ số time-stretch={clamped_factor:.3f}"
                    )

                    if abs(clamped_factor - 1.0) > 0.02:
                        waveform = self._adjust_speed(waveform, sampling_rate, clamped_factor)
                elif abs(speed_factor - 1.0) > 0.01:
                    waveform = self._adjust_speed(waveform, sampling_rate, speed_factor)
            else:
                # Chế độ co giãn tuyến tính thuần (Legacy / manual)
                if abs(speed_factor - 1.0) > 0.01:
                    waveform = self._adjust_speed(waveform, sampling_rate, speed_factor)

            # 9. Đệm micro-silence ở đầu và khoảng nghỉ tĩnh (silence padding) vào đuôi audio
            silence_chunks: List[np.ndarray] = []
            if leading_silence_duration > 0.0:
                lead_samples = int(leading_silence_duration * sampling_rate)
                if lead_samples > 0:
                    silence_chunks.append(np.zeros((lead_samples,), dtype=np.float32))

            silence_chunks.append(waveform)

            if pause_duration > 0.0:
                trail_samples = int(pause_duration * sampling_rate)
                if trail_samples > 0:
                    silence_chunks.append(np.zeros((trail_samples,), dtype=np.float32))

            if len(silence_chunks) > 1:
                waveform = np.concatenate(silence_chunks)
                logger.debug(
                    f"Đã đệm leading={leading_silence_duration:.2f}s, "
                    f"pause={pause_duration:.2f}s vào waveform."
                )

            # 10. Chống rè và vỡ tiếng: Soft Peak Limiter (-0.5 dBFS ~ 0.95 biên độ tối đa)
            max_amp = float(np.max(np.abs(waveform))) if len(waveform) > 0 else 0.0
            if max_amp > 0.95:
                waveform = waveform * (0.95 / max_amp)
                logger.debug(f"[PeakLimiter] Đã chuẩn hóa đỉnh biên độ từ {max_amp:.3f} về 0.950 (-0.5 dBFS)")

            # 11. Ghi dữ liệu âm thanh ra file đích (.wav hoặc .mp3)
            self._save_audio(waveform=waveform, sample_rate=sampling_rate, output_path=target_path)
            logger.info(f"Đã tạo file âm thanh thành công: {target_path} (kích thước: {target_path.stat().st_size} bytes)")
            return target_path

        except Exception as err:
            logger.error(f"Lỗi khi tổng hợp giọng nói bằng VieNeu-TTS cho '{clean_text[:30]}...': {err}")
            raise

    @staticmethod
    def _adjust_speed(waveform: np.ndarray, sample_rate: int, speed: float) -> np.ndarray:
        """
        Điều chỉnh tốc độ đọc của waveform mà không làm thay đổi cao độ.

        Ưu tiên sử dụng ffmpeg `atempo` filter (chất lượng cao hơn librosa cho speech).
        Fallback sang librosa nếu ffmpeg không hoạt động.

        Lý do không dùng librosa làm primary:
        - librosa.effects.time_stretch dùng Phase Vocoder (STFT) → gây phase smearing,
          transient blur, và "metallic/phasiness" artifact đặc biệt nặng với tiếng Việt
          (nhiều phụ âm cuối, thanh điệu sắc nét).
        - ffmpeg atempo dùng WSOLA (Waveform Similarity Overlap-Add) → âm thanh tự nhiên hơn,
          không bị giật hay dính âm.

        ffmpeg atempo chỉ nhận speed trong [0.5, 2.0]. Nếu speed ngoài range này,
        chuỗi nhiều atempo filter được nối tiếp nhau.
        """
        # Thử ffmpeg atempo trước (chất lượng tốt hơn cho speech)
        result = TTSEngine._adjust_speed_ffmpeg(waveform, sample_rate, speed)
        if result is not None:
            return result

        # Fallback: librosa time_stretch
        try:
            import librosa
            logger.warning(
                f"[_adjust_speed] Fallback sang librosa time_stretch (rate={speed:.3f}). "
                "Chất lượng audio có thể bị ảnh hưởng."
            )
            return librosa.effects.time_stretch(waveform, rate=speed)
        except Exception as e:
            logger.warning(f"Không thể time-stretch qua librosa ({e}), giữ nguyên tốc độ gốc")
            return waveform

    @staticmethod
    def _adjust_speed_ffmpeg(
        waveform: np.ndarray,
        sample_rate: int,
        speed: float,
    ) -> Optional[np.ndarray]:
        """
        Dùng ffmpeg `atempo` filter để time-stretch waveform không thay đổi pitch.
        Trả về None nếu thất bại (caller sẽ fallback sang librosa).

        Dùng temp file thay vì pipe (pipe có thể gây buffer artifact / rè với waveform lớn).
        """
        try:
            atempo_chain = TTSEngine._build_atempo_chain(speed)
            filter_str = ",".join(f"atempo={v:.6f}" for v in atempo_chain)

            temp_in = TEMP_DIR / f"atempo_in_{uuid.uuid4().hex[:8]}.wav"
            temp_out = TEMP_DIR / f"atempo_out_{uuid.uuid4().hex[:8]}.wav"
            TEMP_DIR.mkdir(parents=True, exist_ok=True)

            # Đảm bảo waveform 1D float32 trước khi ghi
            wav_flat = np.asarray(waveform, dtype=np.float32).flatten()
            import soundfile as sf
            sf.write(str(temp_in), wav_flat, sample_rate)

            cmd = [
                "ffmpeg", "-y",
                "-i", str(temp_in),
                "-af", filter_str,
                str(temp_out),
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=60)

            if result.returncode != 0:
                logger.debug(f"[atempo] ffmpeg failed: {result.stderr[:200]}")
                return None

            stretched, _ = sf.read(str(temp_out), dtype='float32')
            # Đảm bảo output là 1D
            if stretched.ndim > 1:
                stretched = stretched[:, 0]

            logger.debug(
                f"[atempo] speed={speed:.3f} | chain={atempo_chain} | "
                f"in={len(wav_flat)} → out={len(stretched)} samples"
            )
            return stretched

        except Exception as e:
            logger.debug(f"[atempo] Exception: {e}")
            return None
        finally:
            for p in [temp_in, temp_out]:
                try:
                    if 'p' in dir() and p.exists():
                        p.unlink(missing_ok=True)
                except Exception:
                    pass

    @staticmethod
    def _build_atempo_chain(speed: float) -> List[float]:
        """
        Phân rã speed thành chuỗi atempo factors, mỗi factor trong [0.5, 2.0].

        Ví dụ:
            speed=1.15  → [1.15]         (trong range, dùng trực tiếp)
            speed=0.25  → [0.5, 0.5]     (2 bước × 0.5 = 0.25)
            speed=2.5   → [2.0, 1.25]    (2.0 × 1.25 = 2.5)
            speed=4.0   → [2.0, 2.0]     (2.0 × 2.0 = 4.0)
        """
        MIN_ATEMPO = 0.5
        MAX_ATEMPO = 2.0

        if MIN_ATEMPO <= speed <= MAX_ATEMPO:
            return [speed]

        chain: List[float] = []
        remaining = speed
        while remaining > MAX_ATEMPO:
            chain.append(MAX_ATEMPO)
            remaining /= MAX_ATEMPO
        while remaining < MIN_ATEMPO:
            chain.append(MIN_ATEMPO)
            remaining /= MIN_ATEMPO
        chain.append(round(remaining, 6))
        return chain

    @staticmethod
    def _resolve_output_path(output_path: Optional[Union[str, Path]]) -> Path:
        """Xác định đường dẫn file đầu ra hợp lệ"""
        if output_path is not None:
            p = Path(output_path)
            if not p.suffix:
                return p.with_suffix(".wav")
            return p
        return TEMP_DIR / f"tts_{uuid.uuid4().hex[:12]}.wav"

    @staticmethod
    def _normalize_speed(speed: Union[float, str]) -> float:
        """
        Chuẩn hóa tốc độ đọc sang hệ số nhân float (ví dụ 1.25).
        Chấp nhận các định dạng: 1.2, "+20%", "+22%", "-10%".
        """
        if isinstance(speed, (int, float)):
            return float(speed)

        speed_str = str(speed).strip()
        if speed_str.endswith("%"):
            try:
                percent_val = float(speed_str.rstrip("%"))
                return round(1.0 + (percent_val / 100.0), 3)
            except ValueError:
                pass

        try:
            return float(speed_str)
        except ValueError:
            logger.warning(f"Không thể phân giải tốc độ đọc '{speed}', sử dụng mặc định 1.0")
            return DEFAULT_SPEED

    @staticmethod
    def _normalize_pitch(pitch: Union[float, str]) -> str:
        """Tương thích ngược API OmniVoice: chuẩn hóa pitch thành chuỗi mô tả."""
        pitch_str = str(pitch).strip().lower()
        if "+5" in pitch_str or "very high" in pitch_str:
            return "very high pitch"
        if "-2" in pitch_str or "low" in pitch_str:
            return "low pitch"
        if "high" in pitch_str:
            return "high pitch"
        return "moderate pitch"

    @staticmethod
    def _save_audio(waveform: np.ndarray, sample_rate: int, output_path: Path) -> None:

        """
        Ghi mảng numpy waveform ra file âm thanh (.wav hoặc chuyển mã sang .mp3 qua ffmpeg).
        """
        suffix = output_path.suffix.lower()

        if suffix == ".wav":
            sf.write(str(output_path), waveform, sample_rate)
            return

        # Nếu là .mp3 hoặc định dạng khác, ghi ra file wav tạm thời rồi chuyển mã qua ffmpeg
        temp_wav = output_path.parent / f"temp_{uuid.uuid4().hex[:8]}.wav"
        try:
            sf.write(str(temp_wav), waveform, sample_rate)
            cmd = [
                "ffmpeg", "-y",
                "-i", str(temp_wav),
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                "-ar", "44100",
                str(output_path)
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"Lỗi khi chuyển mã audio sang mp3: {res.stderr[:300]}")
        finally:
            if temp_wav.exists():
                temp_wav.unlink(missing_ok=True)

    @staticmethod
    def get_duration(audio_path: Path) -> float:
        """Lấy độ dài thời lượng chính xác của file âm thanh bằng soundfile hoặc ffprobe"""
        if not audio_path.exists():
            return 0.0
        try:
            info = sf.info(str(audio_path))
            return float(info.duration)
        except Exception:
            pass

        try:
            import json
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                str(audio_path)
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                return float(data.get("format", {}).get("duration", 0.0))
        except Exception as e:
            logger.warning(f"Lỗi đọc độ dài file âm thanh {audio_path}: {e}")
        return 0.0
