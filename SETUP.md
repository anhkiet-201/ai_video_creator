# 🛠️ Hướng Dẫn Cài Đặt - AI Video Creator (Windows)

> Hướng dẫn cài đặt từng bước để chạy **AI Video Creator** trên **Windows 10/11** (native hoặc WSL2).

---

## 📋 Mục Lục

1. [Yêu Cầu Tiên Quyết](#-yêu-cầu-tiên-quyết)
2. [Cài Đặt Python](#-cài-đặt-python)
3. [Cài Đặt Tự Động (setup.py)](#-cài-đặt-tự-động-khuyến-nghị)
4. [Cài Đặt Thư Viện Python (Thủ Công)](#-cài-đặt-thư-viện-python-thủ-công)
5. [Cài Đặt VieNeu-TTS](#-cài-đặt-vieneu-tts)
6. [Cài Đặt FFmpeg](#-cài-đặt-ffmpeg)
7. [Cài Đặt Google Chrome](#-cài-đặt-google-chrome)
8. [Cấu Hình Đường Dẫn Chrome](#-cấu-hình-đường-dẫn-chrome-windows)
9. [Cấu Hình API Key Gemini](#-cấu-hình-api-key-gemini)
10. [Chuẩn Bị Assets](#-chuẩn-bị-assets)
11. [Kiểm Tra Cài Đặt](#-kiểm-tra-cài-đặt)
12. [Chạy Thử Lần Đầu](#-chạy-thử-lần-đầu)
13. [Xử Lý Lỗi Thường Gặp](#-xử-lý-lỗi-thường-gặp)

---

## ✅ Yêu Cầu Tiên Quyết

| Thành Phần | Phiên Bản | Bắt Buộc |
|---|---|:---:|
| Windows | 10 / 11 (64-bit) | ✅ |
| Python | `3.10` — `3.12` | ✅ |
| FFmpeg | `5.0+` | ✅ |
| Google Chrome | Bất kỳ | ✅ |
| Gemini API Key | — | ✅ |
| NVIDIA GPU + CUDA | `11.8+` (tùy chọn) | ⬜ |

> ⚠️ **Python 3.13 chưa tương thích** với một số thư viện AI. Dùng Python **3.10 – 3.12**.

---

## 🐍 Cài Đặt Python

### 1. Tải Python từ trang chính thức

Truy cập [python.org/downloads](https://www.python.org/downloads/windows/) → Tải bản **Python 3.12.x (64-bit)**.

### 2. Cài đặt — quan trọng: tick "Add to PATH"

Khi chạy installer, **bắt buộc tick chọn**:

```
☑ Add Python 3.12 to PATH
☑ Install for all users (khuyến nghị)
```

Chọn **"Customize installation"** → tick đủ: `pip`, `tcl/tk`, `py launcher`.

### 3. Kiểm tra sau khi cài

Mở **Command Prompt** (cmd) hoặc **PowerShell**:

```cmd
python --version
pip --version
```

Kết quả mong đợi:
```
Python 3.12.x
pip 24.x.x from ...
```

---

## 🚀 Cài Đặt Tự Động (Khuyến Nghị)

Dự án đã tích hợp sẵn script cài đặt và kiểm tra môi trường toàn diện tự động `setup.py`. Bạn chỉ cần mở **PowerShell** hoặc **Command Prompt** tại thư mục project và chạy:

```powershell
python setup.py
```

> **Script sẽ tự động thực hiện toàn bộ:**
> 1. Kiểm tra phần cứng và phát hiện GPU NVIDIA RTX/GTX.
> 2. Tự động nâng cấp `pip`, `setuptools`, `wheel`.
> 3. Tự động cài đặt PyTorch phiên bản CUDA phù hợp (hoặc CPU nếu không có GPU rời).
> 4. Cài đặt toàn bộ thư viện cần thiết từ `requirements.txt`.
> 5. Tự động tìm kiếm / cài đặt FFmpeg và cấu hình vĩnh viễn vào biến môi trường `PATH`.
> 6. Kiểm tra trình duyệt Chrome / Edge Headless cho đồ họa Overlay.
> 7. Khởi tạo cấu trúc thư mục `storage/` và `assets/`.
> 8. Chạy bộ tự chẩn đoán (Self-Test Suite) nghiệm thu hệ thống.

---

## 📦 Cài Đặt Thư Viện Python (Thủ Công)

### Bước 1: Cài từ requirements.txt

```cmd
pip install -r requirements.txt
```

### Bước 2: Cài thư viện bổ sung (bắt buộc)

Các thư viện sau được dùng trực tiếp trong source code nhưng **không có trong requirements.txt**:

```cmd
pip install numpy soundfile
```

### Bước 3: Cài PyTorch

Chọn **một trong hai** lệnh sau tuỳ theo máy:

**Máy không có GPU NVIDIA (CPU-only):**
```cmd
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

**Máy có GPU NVIDIA (CUDA 12.1):**
```cmd
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

> Kiểm tra phiên bản CUDA của GPU: `nvidia-smi` trong cmd.

### Kiểm tra PyTorch

```cmd
python -c "import torch; print('PyTorch:', torch.__version__)"
```

---

## 🎙️ Cài Đặt VieNeu-TTS

VieNeu-TTS là engine tổng hợp giọng nói tiếng Việt (48 kHz, v3 Turbo) — thành phần **cốt lõi** của pipeline audio.

### Cài đặt

```cmd
pip install vieneu
```

### Kiểm tra

```cmd
python -c "from vieneu import Vieneu; print('VieNeu-TTS: OK')"
```

> ⏳ **Lần đầu chạy pipeline**, VieNeu sẽ tự động tải model weights (~500 MB – 1 GB) từ internet. Quá trình này chỉ xảy ra **một lần duy nhất** rồi được cache lại.

---

## 🎞️ Cài Đặt FFmpeg

FFmpeg xử lý toàn bộ khâu encode, ghép nối, hiệu ứng chuyển cảnh và xuất video MP4.

### Cách 1: Cài qua winget (Windows 10/11 tích hợp sẵn)

Mở **Command Prompt với quyền Admin**:

```cmd
winget install Gyan.FFmpeg
```

### Cách 2: Tải thủ công

1. Vào [ffmpeg.org/download.html](https://ffmpeg.org/download.html) → **Windows builds by BtbN**
2. Tải file `ffmpeg-master-latest-win64-gpl.zip`
3. Giải nén vào `C:\ffmpeg\`
4. Thêm `C:\ffmpeg\bin` vào **PATH hệ thống**:
   - Tìm kiếm: **"Edit the system environment variables"**
   - `Environment Variables` → `Path` → `New` → nhập `C:\ffmpeg\bin`

### Kiểm tra FFmpeg

**Mở cmd mới** (quan trọng: phải mở cmd mới sau khi chỉnh PATH):

```cmd
ffmpeg -version
```

Kết quả mong đợi:
```
ffmpeg version 7.x Copyright (c) 2000-2024 the FFmpeg developers ...
```

Kiểm tra codec bắt buộc:
```cmd
ffmpeg -codecs | findstr /i "libx264"
ffmpeg -codecs | findstr /i "aac"
```

---

## 🌐 Cài Đặt Google Chrome

Chrome được dùng ở chế độ **Headless** để render đồ họa Overlay HTML5/CSS3 thành ảnh PNG trong suốt (RGBA 32-bit).

> Nếu máy đã cài Chrome thì **bỏ qua bước này**.

Tải và cài đặt tại: [google.com/chrome](https://www.google.com/chrome/)

Đường dẫn mặc định sau khi cài trên Windows:
```
C:\Program Files\Google\Chrome\Application\chrome.exe
```

---

## ⚙️ Cấu Hình Đường Dẫn Chrome (Windows)

Mở file [`app/config.py`](file:///Volumes/aki/workspace/AI_Video_Creator/app/config.py) và **thêm đường dẫn Windows** vào hàm `find_chrome_binary()`:

```python
def find_chrome_binary() -> str:
    possible_paths = [
        # Windows (thêm các dòng này)
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Users\{}\AppData\Local\Google\Chrome\Application\chrome.exe".format(
            os.environ.get("USERNAME", "")
        ),
        # macOS / Linux (giữ nguyên)
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "google-chrome",
        "chromium",
    ]
    for p in possible_paths:
        if os.path.exists(p) and os.access(p, os.X_OK):
            return p
    # Fallback Windows
    return r"C:\Program Files\Google\Chrome\Application\chrome.exe"
```

### Kiểm tra Chrome hoạt động

```cmd
"C:\Program Files\Google\Chrome\Application\chrome.exe" --version
```

---

## 🔑 Cấu Hình API Key Gemini

### Lấy API Key

1. Truy cập [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Đăng nhập tài khoản Google → Click **"Create API Key"**
3. Copy key (dạng `AIzaSy...`)

### Thiết lập biến môi trường (Khuyến nghị)

**Cách A – Tạm thời trong session (cmd):**
```cmd
set GEMINI_API_KEY=AIzaSyYourKeyHere
```

**Cách B – Vĩnh viễn (System Environment Variable):**
```cmd
:: Mở cmd với quyền Admin
setx GEMINI_API_KEY "AIzaSyYourKeyHere" /M
```

Hoặc thêm thủ công qua:
- **Settings** → System → **About** → **Advanced system settings**
- Nhấn `Environment Variables...` → `New...` (System variables)
- Variable name: `GEMINI_API_KEY` | Value: `AIzaSy...`

**Mở cmd mới** để biến môi trường có hiệu lực.

### Cách C – Truyền trực tiếp qua CLI (không cần cài biến môi trường)

```cmd
python cli.py --api-keys AIzaSyKey1 AIzaSyKey2 ...
```

### Kiểm tra

```cmd
python -c "import os; k=os.environ.get('GEMINI_API_KEY','CHUA_CAI'); print(k[:20]+'...' if k!='CHUA_CAI' else 'CANH BAO: Chua cai GEMINI_API_KEY')"
```

---

## 📁 Chuẩn Bị Assets

### Cấu trúc thư mục cần có

```
AI_Video_Creator\
├── assets\
│   ├── voices\          ← Audio mẫu Voice Cloning (.wav, .mp3)
│   ├── sounds\
│   │   └── bgm\         ← Nhạc nền BGM (.mp3, .wav)
│   └── samples\
│       ├── sample_job.txt         ← Văn bản mẫu
│       └── company_media\         ← Video / ảnh B-roll
└── ...
```

Hệ thống tự tạo thư mục khi khởi động. Bạn cần tự cung cấp file media.

### Chuẩn bị B-Roll

```cmd
mkdir assets\samples\company_media

:: Copy video/ảnh B-roll vào đây
:: Hỗ trợ: .mp4, .mov, .jpg, .jpeg, .png
```

### Chuẩn bị Voice Clone (tuỳ chọn)

```cmd
mkdir assets\voices

:: Copy file audio mẫu vào đây (chỉ cần 3-5 giây)
:: Hỗ trợ: .wav, .mp3, .m4a
```

### Chuẩn bị nhạc nền BGM (tuỳ chọn)

```cmd
mkdir assets\sounds\bgm

:: Copy file nhạc nền vào đây
:: Hỗ trợ: .mp3, .wav
```

### Tạo file văn bản mẫu

```cmd
echo Tuyển 5 nhân viên đóng gói bánh kẹo tại Tân Bình > assets\samples\sample_job.txt
echo Lương 8.5 triệu/tháng, bao ăn trưa >> assets\samples\sample_job.txt
```

---

## 🔍 Kiểm Tra Cài Đặt

Chạy lệnh kiểm tra tổng hợp:

```cmd
python -c "
import sys
print(f'Python: {sys.version}')
assert sys.version_info >= (3, 10), 'Can Python 3.10+'

try:
    import pydantic; print(f'pydantic: {pydantic.__version__} OK')
except: print('pydantic: THIEU')

try:
    import google.genai; print('google-genai: OK')
except: print('google-genai: THIEU - pip install google-genai')

try:
    import numpy; print(f'numpy: {numpy.__version__} OK')
except: print('numpy: THIEU - pip install numpy')

try:
    import soundfile; print(f'soundfile: {soundfile.__version__} OK')
except: print('soundfile: THIEU - pip install soundfile')

try:
    import torch; print(f'torch: {torch.__version__} OK')
except: print('torch: THIEU - pip install torch')

try:
    from vieneu import Vieneu; print('vieneu: OK')
except: print('vieneu: THIEU - pip install vieneu')

import shutil, subprocess
if shutil.which('ffmpeg'):
    r = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
    print('ffmpeg: ' + r.stdout.split(chr(10))[0] + ' OK')
else:
    print('ffmpeg: THIEU - cai theo huong dan SETUP.md')

import os
chrome = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
print(f'chrome: {\"OK\" if os.path.exists(chrome) else \"THIEU - cai Google Chrome\"}')

print()
print('=== Kiem tra xong! ===')
"
```

---

## 🚀 Chạy Thử Lần Đầu

### Test nhanh với văn bản trực tiếp

```cmd
python cli.py ^
  --content "Tuyen 5 ban nhan vien dong goi tai Tan Binh, luong 8.5 trieu, bao an trua" ^
  --source-folder assets\samples\company_media ^
  --api-keys AIzaSyYourKeyHere ^
  --num-videos 1
```

> 💡 Windows dùng `^` thay cho `\` để xuống dòng trong cmd.

### Test từ file văn bản mẫu

```cmd
python cli.py ^
  --content-file assets\samples\sample_job.txt ^
  --source-folder assets\samples\company_media ^
  --num-videos 1 ^
  --verbose
```

### Kết quả mong đợi

Video thành phẩm lưu tại:
```
storage\outputs\video_YYYYMMDD_HHMMSS.mp4
```

---

## 🐛 Xử Lý Lỗi Thường Gặp

### `python` không nhận dạng được

→ Python chưa vào PATH. Cài lại và tick **"Add Python to PATH"**.

```cmd
:: Kiểm tra
where python
```

### `ModuleNotFoundError: No module named 'torch'`

```cmd
:: CPU-only
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

### `ModuleNotFoundError: No module named 'soundfile'`

```cmd
pip install soundfile
```

### `ModuleNotFoundError: No module named 'vieneu'`

```cmd
pip install vieneu
```

### `ModuleNotFoundError: No module named 'numpy'`

```cmd
pip install numpy
```

### `ffmpeg` không tìm thấy

```cmd
:: Kiểm tra
where ffmpeg

:: Nếu không thấy → cài lại qua winget
winget install Gyan.FFmpeg
:: Sau đó mở CMD mới
```

### Chrome không tìm thấy (lỗi render overlay)

Kiểm tra đường dẫn Chrome:
```cmd
dir "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

Nếu không có, tìm:
```cmd
where chrome
```

Sau đó cập nhật `app\config.py` → hàm `find_chrome_binary()` với đường dẫn đúng.

### `HTTP 429 - Resource Exhausted` (Gemini)

Cung cấp nhiều API Key để xoay vòng:
```cmd
python cli.py --api-keys key1 key2 key3 ...
```

### PowerShell: `Activate.ps1 cannot be loaded`

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### VieNeu model tải chậm / bị ngắt

- Kiểm tra kết nối mạng
- Chạy lại lệnh — model được cache sau khi tải xong
- Nếu dùng proxy: `set HTTPS_PROXY=http://your-proxy:port`

---

## 📌 Thư Viện Thực Sự Được Dùng

Bảng dưới liệt kê chính xác các thư viện được **import trong source code**:

| Thư Viện | Lệnh Cài | Dùng Ở Đâu |
|---|---|---|
| `pydantic` | có trong `requirements.txt` | Models, validation |
| `google-genai` | có trong `requirements.txt` | Gemini AI (trích xuất, biên kịch) |
| `numpy` | `pip install numpy` | TTS engine, audio processing |
| `soundfile` | `pip install soundfile` | Đọc/ghi file audio WAV |
| `torch` | `pip install torch` | VieNeu-TTS model inference |
| `vieneu` | `pip install vieneu` | Engine TTS tiếng Việt |
| `vieneu_utils` | cài kèm `vieneu` | Chuẩn hóa văn bản Vietnamese |

> ⚠️ Các thư viện trong `requirements.txt` như `fastapi`, `uvicorn`, `edge-tts`, `pillow`, `jinja2`, `aiofiles`, `httpx`, `python-multipart` hiện **chưa được dùng** trong pipeline chính. Cài để tránh lỗi nếu mở rộng sau này.

---

## 🔗 Tham Khảo Thêm

- [`README.md`](./README.md) — Tài liệu kỹ thuật và tham số CLI đầy đủ
- [`cli.py`](./cli.py) — Điểm nhập CLI chính
- [`app/config.py`](./app/config.py) — Cấu hình Chrome, FFmpeg, video specs
- [Google AI Studio](https://aistudio.google.com/apikey) — Lấy Gemini API Key
- [PyTorch Windows](https://pytorch.org/get-started/locally/) — Chọn đúng phiên bản CUDA
- [FFmpeg Windows Builds](https://github.com/BtbN/FFmpeg-Builds/releases) — Tải FFmpeg binary
