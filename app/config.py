import os
import shutil
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
ASSETS_DIR = BASE_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
MUSIC_DIR = ASSETS_DIR / "music"
VOICES_DIR = ASSETS_DIR / "voices"
TRANSITION_SOUNDS_DIR = ASSETS_DIR / "sounds" / "transition"
EFFECT_SOUNDS_DIR = ASSETS_DIR / "sounds" / "effect"
BGM_SOUNDS_DIR = ASSETS_DIR / "sounds" / "bgm"
STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
OUTPUTS_DIR = STORAGE_DIR / "outputs"
TEMP_DIR = STORAGE_DIR / "temp"

# Ensure all critical directories exist
for path in [UPLOADS_DIR, OUTPUTS_DIR, TEMP_DIR, FONTS_DIR, MUSIC_DIR, VOICES_DIR, TRANSITION_SOUNDS_DIR, EFFECT_SOUNDS_DIR, BGM_SOUNDS_DIR]:
    path.mkdir(parents=True, exist_ok=True)

# Ensure FFmpeg is available in PATH (especially for Windows WinGet installs)
if not shutil.which("ffmpeg"):
    _possible_ffmpeg_dirs = [
        os.path.expandvars(r"%LocalAppData%\Microsoft\WinGet\Links"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.1-full_build\bin"),
        r"C:\ffmpeg\bin",
        r"C:\Program Files\ffmpeg\bin",
    ]
    for _d in _possible_ffmpeg_dirs:
        if os.path.isdir(_d) and (os.path.exists(os.path.join(_d, "ffmpeg.exe")) or os.path.exists(os.path.join(_d, "ffmpeg"))):
            os.environ["PATH"] = f"{_d}{os.pathsep}{os.environ.get('PATH', '')}"
            break


# Default Video Specifications for TikTok (9:16 Vertical)
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
VIDEO_CODEC = "libx264"
FFMPEG_PRESET = "ultrafast"  # Tăng tốc độ mã hóa video lên mức cao nhất
MAX_CONCURRENT_RENDERS = 4   # Số luồng render song song các scene clips
AUDIO_CODEC = "aac"
AUDIO_SAMPLE_RATE = 48000

# Supported Media Extensions
SUPPORTED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_MEDIA_EXTS = SUPPORTED_VIDEO_EXTS | SUPPORTED_IMAGE_EXTS
SUPPORTED_VOICE_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
SUPPORTED_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"}

# TTS Configuration
DEFAULT_VOICE_FEMALE = "vi-VN-HoaiMyNeural"
DEFAULT_VOICE_MALE = "vi-VN-NamMinhNeural"
AVAILABLE_VOICES = {
    "female": {"id": DEFAULT_VOICE_FEMALE, "name": "Hoài My (Nữ miền Bắc - Ngọt ngào, truyền cảm)"},
    "male": {"id": DEFAULT_VOICE_MALE, "name": "Nam Minh (Nam miền Bắc - Trầm ấm, đĩnh đạc)"}
}

# Default Font
DEFAULT_FONT_PATH = FONTS_DIR / "default_bold.ttf"

# Anti-Reup Settings Presets
ANTI_REUP_PRESETS = {
    "low": {
        "color_jitter": 0.015,
        "zoom_range": (1.0, 1.015),
        "speed_range": (0.99, 1.01),
        "noise_amount": 0.01
    },
    "medium": {
        "color_jitter": 0.025,
        "zoom_range": (1.0, 1.025),
        "speed_range": (0.985, 1.015),
        "noise_amount": 0.02
    },
    "high": {
        "color_jitter": 0.04,
        "zoom_range": (1.0, 1.035),
        "speed_range": (0.975, 1.025),
        "noise_amount": 0.035
    }
}

# Tinh chỉnh chuyển cảnh và âm thanh siêu tốc TikTok
DEFAULT_TTS_RATE = "+22%"  # Tốc độ đọc TikTok siêu cuốn, nhanh nhẹn, giữ chân người xem
DEFAULT_TTS_PITCH = "+0Hz"
AUDIO_GAP_PADDING = 0.06   # Khoảng nghỉ micro 0.06s tự nhiên
TRANSITION_DURATION = 0.3  # Thời lượng hiệu ứng chuyển cảnh xfade mượt mà giữa các clip (giây)
AVAILABLE_TRANSITIONS = ["fade", "wipeleft", "slideleft", "smoothleft", "dissolve"]
DEFAULT_TRANSITION_SOUND_VOLUME = 0.15  # Mức âm lượng mặc định cho âm thanh chuyển cảnh (15%)
DEFAULT_EFFECT_SOUND_VOLUME = 0.6       # Mức âm lượng mặc định cho âm thanh hiệu ứng (60%)
DEFAULT_BGM_VOLUME = 0.10               # Mức âm lượng mặc định cho nhạc nền BGM (10%)

# Các mẫu tổ hợp đồ họa Overlay CapCut/TikTok chuyên nghiệp (HTML5 + CSS3)
OVERLAY_PATTERNS = {
    "torn_paper": {"name": "📰 Báo Xé Cổ Điển", "icon": "📰", "desc": "Mẩu giấy xé rách lởm chởm, nghiêng nhẹ tự nhiên"},
    "bubble_cloud": {"name": "☁️ Đám Mây Highlight", "icon": "☁️", "desc": "Vệt highlight mây bồng bềnh viền chữ đen sắc nét"},
    "pastel_multicolor": {"name": "🌸 Kẹo Ngọt Đa Sắc & Hoa", "icon": "🌸", "desc": "Từng chữ khối màu pastel kèm mini flower"},
    "paper_hearts": {"name": "❤️ Thẻ Giấy Note & Trái Tim", "icon": "❤️", "desc": "Giấy note trắng 3D kèm icon trái tim bay"},
    "neon_glow": {"name": "⚡ Neon Cyber CapCut", "icon": "⚡", "desc": "Hộp kính tối viền đôi phát sáng rực rỡ"}
}

OVERLAY_PALETTES = {
    "vintage_kraft": {"name": "Nâu Kraft Cổ Điển", "primary": "#f7f3e8", "text": "#3b2318", "border": "#8b5a2b"},
    "pink_bubblegum": {"name": "Hồng Kẹo Ngọt", "primary": "#ff7ebb", "text": "#ffffff", "border": "#ff9ecd"},
    "rainbow_candy": {"name": "Cầu Vồng Pastel", "primary": "#ffb6c1", "text": "#111827", "border": "#ffd700"},
    "pure_contrast": {"name": "Trắng Đen Đỏ Nổi Bật", "primary": "#ffffff", "text": "#000000", "border": "#ef4444"},
    "cyber_neon": {"name": "Xanh & Vàng Cyber Neon", "primary": "#ffd700", "text": "#000000", "border": "#00e5ff"}
}

OVERLAY_FONTS = {
    "cute_rounded": {"name": "Bo Tròn Dễ Thương (Nunito)", "font_family": "'Nunito', -apple-system, sans-serif"},
    "modern_bold": {"name": "Đậm Nét Hiện Đại (Montserrat)", "font_family": "'Montserrat', -apple-system, sans-serif"},
    "vintage_serif": {"name": "Cổ Điển Trang Nhã (Playfair)", "font_family": "'Playfair Display', serif"},
    "marker_hand": {"name": "Nét Bút Phóng Khoáng (Comfortaa)", "font_family": "'Comfortaa', cursive"}
}

# Tự động tìm kiếm đường dẫn Chrome Headless
def find_chrome_binary() -> str:
    possible_paths = [
        # Windows
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        # macOS
        "/Volumes/aki/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        # Linux
        "google-chrome",
        "chromium"
    ]
    for p in possible_paths:
        if os.path.isabs(p) and os.path.exists(p):
            return p
        which_p = shutil.which(p)
        if which_p and os.path.exists(which_p):
            return which_p
    return "chrome"

CHROME_BINARY_PATH = find_chrome_binary()


