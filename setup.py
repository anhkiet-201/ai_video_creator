#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
 AI VIDEO CREATOR - ALL-IN-ONE AUTOMATED SETUP & DIAGNOSTIC SCRIPT (WINDOWS)
==============================================================================
Tự động cài đặt và kiểm tra toàn diện:
 1. Kiểm tra môi trường hệ thống (Windows, Python, GPU NVIDIA / CUDA)
 2. Nâng cấp bộ công cụ pip, setuptools, wheel
 3. Tự động cài đặt PyTorch tương thích (CUDA cho GPU NVIDIA hoặc CPU)
 4. Cài đặt toàn bộ thư viện cần thiết từ requirements.txt
 5. Tự động tìm kiếm / cài đặt FFmpeg (thông qua WinGet) & cấu hình PATH
 6. Kiểm tra Google Chrome / Edge Headless cho đồ họa Overlay
 7. Cấu hình biến môi trường thực thi cho lệnh aiv (aiv.bat)
 8. Khởi tạo cấu trúc thư mục lưu trữ và tài nguyên
 9. Chạy bộ tự chẩn đoán (Self-Test Suite) nghiệm thu hệ thống
==============================================================================
"""

import os
import sys
import platform
import subprocess
import shutil
import tempfile
from pathlib import Path

# Đảm bảo mã hóa UTF-8 cho console trên Windows
if sys.platform == "win32":
    os.environ["PYTHONUTF8"] = "1"
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Định nghĩa màu sắc hiển thị Console
class UI:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BLUE = "\033[94m"
    GRAY = "\033[90m"

    @classmethod
    def header(cls, title: str):
        print(f"\n{cls.CYAN}{cls.BOLD}{'=' * 75}{cls.RESET}")
        print(f"{cls.CYAN}{cls.BOLD}  {title.center(71)}{cls.RESET}")
        print(f"{cls.CYAN}{cls.BOLD}{'=' * 75}{cls.RESET}\n")

    @classmethod
    def step(cls, step_num: int, total_steps: int, title: str):
        print(f"\n{cls.BLUE}{cls.BOLD}[Bước {step_num}/{total_steps}] ⚙️  {title}{cls.RESET}")
        print(f"{cls.GRAY}{'-' * 75}{cls.RESET}")

    @classmethod
    def ok(cls, msg: str):
        print(f" {cls.GREEN}[✓] {msg}{cls.RESET}")

    @classmethod
    def warn(cls, msg: str):
        print(f" {cls.YELLOW}[⚠️] {msg}{cls.RESET}")

    @classmethod
    def err(cls, msg: str):
        print(f" {cls.RED}[✗] {msg}{cls.RESET}")

    @classmethod
    def info(cls, msg: str):
        print(f" {cls.GRAY}[i] {msg}{cls.RESET}")


BASE_DIR = Path(__file__).resolve().parent


def run_cmd(cmd, desc: str = "", check: bool = True, capture: bool = False, env: dict = None) -> subprocess.CompletedProcess:
    """Thực thi lệnh shell và xử lý hiển thị log."""
    if desc:
        UI.info(f"{desc}...")
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    run_env["PYTHONUTF8"] = "1"

    res = subprocess.run(
        cmd,
        shell=isinstance(cmd, str),
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=run_env
    )
    if check and res.returncode != 0:
        err_msg = res.stderr if capture else f"Exit code {res.returncode}"
        UI.err(f"Lệnh thất bại: {cmd}\n{err_msg}")
        raise RuntimeError(f"Command failed: {cmd}")
    return res


# ==============================================================================
# BƯỚC 1: KIỂM TRA MÔI TRƯỜNG HỆ THỐNG
# ==============================================================================
def check_system() -> dict:
    UI.step(1, 9, "Kiểm tra tương thích phần cứng và hệ điều hành")
    info = {"os": platform.system(), "python": sys.version_split() if hasattr(sys, 'version_split') else sys.version, "has_nvidia": False}

    # 1. Hệ điều hành
    if sys.platform != "win32":
        UI.warn(f"Bạn đang chạy trên {platform.system()}. Script tối ưu nhất cho Windows 10/11.")
    else:
        UI.ok(f"Hệ điều hành: Windows {platform.release()} ({platform.machine()})")

    # 2. Phiên bản Python
    py_ver = sys.version_info
    UI.info(f"Python hiện tại: {py_ver.major}.{py_ver.minor}.{py_ver.micro} ({sys.executable})")
    if py_ver < (3, 10):
        UI.err("Yêu cầu Python >= 3.10 để tương thích với các thư viện AI hiện đại!")
        sys.exit(1)
    else:
        UI.ok("Phiên bản Python đạt chuẩn yêu cầu.")

    # 3. Kiểm tra GPU NVIDIA
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            res = subprocess.run([nvidia_smi, "--query-gpu=name,driver_version", "--format=csv,noheader"], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                gpu_name = res.stdout.strip().split(",")[0]
                UI.ok(f"Phát hiện GPU NVIDIA: {gpu_name} (Hỗ trợ tăng tốc phần cứng CUDA)")
                info["has_nvidia"] = True
        except Exception:
            pass

    if not info["has_nvidia"]:
        UI.info("Không phát hiện GPU NVIDIA rời hoặc nvidia-smi. Sẽ sử dụng cấu hình tối ưu cho CPU.")

    return info


# ==============================================================================
# BƯỚC 2: NÂNG CẤP BỘ CÔNG CỤ PIP & BUILD TOOLS
# ==============================================================================
def upgrade_pip():
    UI.step(2, 9, "Nâng cấp bộ công cụ pip, setuptools và wheel")
    try:
        run_cmd(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
            desc="Đang nâng cấp pip, setuptools, wheel",
            check=False
        )
        UI.ok("Bộ công cụ pip và build tools đã sẵn sàng.")
    except Exception as e:
        UI.warn(f"Nâng cấp pip không bắt buộc: {e}")


# ==============================================================================
# BƯỚC 3: CÀI ĐẶT PYTORCH (CUDA HOẶC CPU)
# ==============================================================================
def install_pytorch(has_nvidia: bool):
    UI.step(3, 9, "Cài đặt PyTorch phù hợp với phần cứng")

    # Kiểm tra torch đã cài đặt chưa
    try:
        import torch
        import torchvision
        import torchaudio
        cuda_avail = torch.cuda.is_available()
        UI.ok(f"PyTorch đã được cài đặt: phiên bản {torch.__version__} (CUDA: {cuda_avail})")
        if has_nvidia and not cuda_avail:
            UI.info("Máy có GPU NVIDIA nhưng PyTorch hiện tại là bản CPU. Đang nâng cấp lên bản CUDA...")
        else:
            return
    except ImportError:
        UI.info("Chưa tìm thấy PyTorch/torchvision/torchaudio đầy đủ. Đang chuẩn bị cài đặt...")

    cmd = [
        sys.executable, "-m", "pip", "install", "torch", "torchvision", "torchaudio"
    ]
    desc = "Đang cài đặt PyTorch (pip install torch torchvision torchaudio)"

    run_cmd(cmd, desc=desc, check=True)
    UI.ok("Cài đặt PyTorch thành công.")


# ==============================================================================
# BƯỚC 4: CÀI ĐẶT CÁC THƯ VIỆN TỪ REQUIREMENTS.TXT
# ==============================================================================
def install_requirements():
    UI.step(4, 9, "Cài đặt các thư viện Python (requirements.txt)")
    req_file = BASE_DIR / "requirements.txt"
    if not req_file.exists():
        UI.err(f"Không tìm thấy file {req_file}")
        sys.exit(1)

    cmd = [sys.executable, "-m", "pip", "install", "-r", str(req_file)]
    run_cmd(cmd, desc="Đang cài đặt các thư viện phụ thuộc", check=True)
    UI.ok("Tất cả thư viện trong requirements.txt đã được cài đặt thành công.")


# ==============================================================================
# BƯỚC 5: TÌM KIẾM / CÀI ĐẶT FFMPEG QUA WINGET & CẤU HÌNH PATH
# ==============================================================================
def setup_ffmpeg():
    UI.step(5, 9, "Kiểm tra và thiết lập FFmpeg / FFprobe trên Windows")

    # Kiểm tra các vị trí tiềm năng trên Windows
    possible_ffmpeg_dirs = [
        os.path.expandvars(r"%LocalAppData%\Microsoft\WinGet\Links"),
        r"C:\ffmpeg\bin",
        r"C:\Program Files\ffmpeg\bin",
    ]
    # Tìm kiếm trong thư mục Packages của WinGet
    winget_pkg_dir = Path(os.path.expandvars(r"%LocalAppData%\Microsoft\WinGet\Packages"))
    if winget_pkg_dir.exists():
        for p in winget_pkg_dir.glob("*FFmpeg*/**/bin"):
            if (p / "ffmpeg.exe").exists():
                possible_ffmpeg_dirs.insert(0, str(p))
                break

    ffmpeg_found = shutil.which("ffmpeg")
    ffmpeg_dir_to_add = None

    if ffmpeg_found:
        UI.ok(f"Tìm thấy FFmpeg trên PATH: {ffmpeg_found}")
    else:
        for d in possible_ffmpeg_dirs:
            p_dir = Path(d)
            if p_dir.is_dir() and (p_dir / "ffmpeg.exe").exists():
                ffmpeg_dir_to_add = str(p_dir)
                break

        if ffmpeg_dir_to_add:
            UI.ok(f"Đã phát hiện FFmpeg tại: {ffmpeg_dir_to_add}")
            os.environ["PATH"] = f"{ffmpeg_dir_to_add}{os.pathsep}{os.environ.get('PATH', '')}"
        else:
            # Thử tự động cài đặt qua winget
            winget = shutil.which("winget")
            if winget:
                UI.info("Chưa có FFmpeg. Đang tự động cài đặt Gyan.FFmpeg thông qua WinGet...")
                try:
                    run_cmd(
                        ["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--silent",
                         "--accept-source-agreements", "--accept-package-agreements"],
                        desc="WinGet đang cài đặt FFmpeg",
                        check=False
                    )
                    # Quét lại sau khi cài
                    for d in possible_ffmpeg_dirs:
                        if Path(d).is_dir() and (Path(d) / "ffmpeg.exe").exists():
                            ffmpeg_dir_to_add = str(d)
                            os.environ["PATH"] = f"{ffmpeg_dir_to_add}{os.pathsep}{os.environ.get('PATH', '')}"
                            UI.ok(f"Cài đặt FFmpeg thành công tại: {ffmpeg_dir_to_add}")
                            break
                except Exception as e:
                    UI.warn(f"Lỗi khi cài qua winget: {e}")

    # Bổ sung vào User PATH Registry vĩnh viễn nếu trên Windows
    if ffmpeg_dir_to_add and sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
                current_user_path, _ = winreg.QueryValueEx(key, "Path")
                if ffmpeg_dir_to_add.lower() not in current_user_path.lower():
                    new_path = f"{current_user_path};{ffmpeg_dir_to_add}"
                    winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
                    UI.ok(f"Đã ghi nhận vĩnh viễn FFmpeg vào User PATH: {ffmpeg_dir_to_add}")
        except Exception:
            pass


# ==============================================================================
# BƯỚC 6: KIỂM TRA GOOGLE CHROME / EDGE HEADLESS
# ==============================================================================
def check_chrome():
    UI.step(6, 9, "Kiểm tra trình duyệt Chrome / Edge (cho Overlay Engine)")
    chrome_candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        shutil.which("chrome"),
        shutil.which("google-chrome"),
        shutil.which("msedge")
    ]
    found_browser = None
    for c in chrome_candidates:
        if c and os.path.exists(c):
            found_browser = c
            break

    if found_browser:
        UI.ok(f"Tìm thấy trình duyệt Headless: {found_browser}")
    else:
        UI.warn("Không tìm thấy Google Chrome hoặc Microsoft Edge.")
        UI.info("Gợi ý: Cài đặt Chrome qua lệnh: winget install Google.Chrome")


# ==============================================================================
# BƯỚC 7: CẤU HÌNH BIẾN MÔI TRƯỜNG THỰC THI CHO LỆNH AIV (AIV.BAT)
# ==============================================================================
def setup_aiv_cli():
    UI.step(7, 9, "Cấu hình biến môi trường thực thi cho lệnh aiv (aiv.bat)")
    aiv_bat = BASE_DIR / "aiv.bat"
    if not aiv_bat.exists():
        UI.warn(f"Không tìm thấy file {aiv_bat}. Đang tạo mới...")
        bat_content = (
            "@echo off\r\n"
            "setlocal\r\n\r\n"
            "REM 1. Neu khong co tham so: mac dinh chay setup.py\r\n"
            "if \"%~1\"==\"\" (\r\n"
            "    python \"%~dp0setup.py\"\r\n"
            "    exit /b %ERRORLEVEL%\r\n"
            ")\r\n\r\n"
            "REM 2. Neu tham so dau tien la update: chay git pull\r\n"
            "if /i \"%~1\"==\"update\" (\r\n"
            "    echo [i] Dang cap nhat AI Video Creator tu Git (git pull)...\r\n"
            "    git -C \"%~dp0\" pull\r\n"
            "    exit /b %ERRORLEVEL%\r\n"
            ")\r\n\r\n"
            "set \"HAS_SOURCE=0\"\r\n"
            "for %%A in (%*) do (\r\n"
            "    if /i \"%%~A\"==\"--source-folder\" set \"HAS_SOURCE=1\"\r\n"
            ")\r\n\r\n"
            "if \"%HAS_SOURCE%\"==\"1\" (\r\n"
            "    python \"%~dp0cli.py\" %*\r\n"
            ") else (\r\n"
            "    python \"%~dp0cli.py\" --source-folder \"%CD%\" %*\r\n"
            ")\r\n\r\n"
            "endlocal\r\n"
        )
        aiv_bat.write_text(bat_content, encoding="utf-8")
        UI.ok("Đã khởi tạo file thực thi: aiv.bat")
    else:
        UI.ok("Đã xác nhận file thực thi: aiv.bat")

    base_dir_str = str(BASE_DIR.resolve())

    # Cập nhật PATH cho phiên làm việc hiện tại của script
    current_path_list = [p.strip() for p in os.environ.get("PATH", "").split(os.pathsep) if p.strip()]
    if base_dir_str.lower() not in [p.lower() for p in current_path_list]:
        os.environ["PATH"] = f"{base_dir_str}{os.pathsep}{os.environ.get('PATH', '')}"

    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
                try:
                    user_path, val_type = winreg.QueryValueEx(key, "Path")
                except FileNotFoundError:
                    user_path, val_type = "", winreg.REG_EXPAND_SZ

                parts = [p.strip() for p in user_path.split(";") if p.strip()]
                normalized_parts = [os.path.normpath(p).lower() for p in parts]
                norm_base = os.path.normpath(base_dir_str).lower()

                if norm_base not in normalized_parts:
                    parts.append(base_dir_str)
                    new_user_path = ";".join(parts)
                    save_type = val_type if val_type in (winreg.REG_EXPAND_SZ, winreg.REG_SZ) else winreg.REG_EXPAND_SZ
                    winreg.SetValueEx(key, "Path", 0, save_type, new_user_path)
                    UI.ok(f"Đã đăng ký vĩnh viễn thư mục dự án vào User PATH: {base_dir_str}")
                else:
                    UI.ok(f"User PATH đã có sẵn thư mục dự án: {base_dir_str}")

            # Phát tín hiệu WM_SETTINGCHANGE tới hệ thống Windows để Explorer và Terminal mới nhận diện ngay
            try:
                import ctypes
                HWND_BROADCAST = 0xFFFF
                WM_SETTINGCHANGE = 0x001A
                SMTO_ABORTIFHUNG = 0x0002
                result = ctypes.c_long()
                ctypes.windll.user32.SendMessageTimeoutW(
                    HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",
                    SMTO_ABORTIFHUNG, 5000, ctypes.byref(result)
                )
                UI.info("Đã phát tín hiệu cập nhật biến môi trường tới Windows (WM_SETTINGCHANGE).")
            except Exception:
                pass

        except Exception as e:
            UI.warn(f"Không thể tự động ghi vào User Registry: {e}")
            UI.info(f"Vui lòng thêm thủ công đường dẫn sau vào biến môi trường PATH: {base_dir_str}")
    else:
        # Hỗ trợ macOS/Linux
        aiv_sh = BASE_DIR / "aiv"
        if not aiv_sh.exists():
            sh_content = (
                "#!/usr/bin/env bash\n"
                'BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n\n'
                "# 1. Khi khong co tham so: mac dinh chay setup.py\n"
                "if [ $# -eq 0 ]; then\n"
                '    python3 "$BASE_DIR/setup.py"\n'
                "    exit $?\n"
                "fi\n\n"
                "# 2. Khi tham so dau tien la update: thuc hien git pull\n"
                'if [ "$1" = "update" ]; then\n'
                '    echo "🔄 Đang cập nhật AI Video Creator (git pull)..."\n'
                '    git -C "$BASE_DIR" pull\n'
                "    exit $?\n"
                "fi\n\n"
                "HAS_SOURCE=0\n"
                'for arg in "$@"; do\n'
                '    if [ "$arg" = "--source-folder" ]; then\n'
                "        HAS_SOURCE=1\n"
                "        break\n"
                "    fi\n"
                "done\n\n"
                'if [ "$HAS_SOURCE" -eq 1 ]; then\n'
                '    python3 "$BASE_DIR/cli.py" "$@"\n'
                "else\n"
                '    python3 "$BASE_DIR/cli.py" --source-folder "$(pwd)" "$@"\n'
                "fi\n"
            )
            aiv_sh.write_text(sh_content, encoding="utf-8")
            try:
                aiv_sh.chmod(0o755)
            except Exception:
                pass
            UI.ok("Đã khởi tạo script thực thi cho Unix/macOS: ./aiv")
        UI.info(f"Gợi ý: Thêm export PATH=\"$PATH:{base_dir_str}\" vào ~/.zshrc hoặc ~/.bashrc để gọi lệnh 'aiv' từ mọi nơi.")


# ==============================================================================
# BƯỚC 8: KHỞI TẠO CẤU TRÚC THƯ MỤC & FILE CẤU HÌNH
# ==============================================================================
def scaffold_directories():
    UI.step(8, 9, "Khởi tạo cây thư mục lưu trữ và tài nguyên")
    dirs = [
        BASE_DIR / "storage" / "uploads",
        BASE_DIR / "storage" / "outputs",
        BASE_DIR / "storage" / "temp",
        BASE_DIR / "assets" / "voices",
        BASE_DIR / "assets" / "fonts",
        BASE_DIR / "assets" / "music",
        BASE_DIR / "assets" / "sounds" / "bgm",
        BASE_DIR / "assets" / "sounds" / "transition",
        BASE_DIR / "assets" / "sounds" / "effect",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    UI.ok("Cấu trúc thư mục storage và assets đã được đảm bảo đầy đủ.")

    # Kiểm tra file content.txt
    content_file = BASE_DIR / "content.txt"
    if not content_file.exists():
        default_content = (
            "Hook vào lần đầu tiên: TUYỂN DỤNG CÔNG NHÂN NAM/NỮ ĐI LÀM NGAY!\n\n"
            "💰 Thu nhập hấp dẫn 9-13 triệu/tháng\n"
            "🏭 Công ty hỗ trợ cơm trưa và phụ cấp chuyên cần\n"
            "📄 Thủ tục đơn giản: Chỉ cần CCCD gốc hoặc photo\n"
        )
        content_file.write_text(default_content, encoding="utf-8")
        UI.ok("Đã khởi tạo file mẫu: content.txt")
    else:
        UI.ok(f"File nội dung content.txt đã sẵn sàng ({len(content_file.read_text(encoding='utf-8'))} ký tự).")


# ==============================================================================
# BƯỚC 9: BỘ TỰ CHẨN ĐOÁN NGHIỆM THU (SELF-TEST SUITE)
# ==============================================================================
def run_diagnostics():
    UI.step(9, 9, "Bộ tự chẩn đoán nghiệm thu hệ thống (Self-Test Suite)")
    results = {}

    # 1. Test PyTorch
    try:
        import torch
        results["PyTorch"] = (True, f"v{torch.__version__} (CUDA: {torch.cuda.is_available()})")
    except Exception as e:
        results["PyTorch"] = (False, str(e))

    # 2. Test VieNeu-TTS & Transformers
    try:
        import transformers
        from vieneu import Vieneu
        results["VieNeu-TTS & Transformers"] = (True, f"Transformers v{transformers.__version__}")
    except Exception as e:
        results["VieNeu-TTS & Transformers"] = (False, str(e))

    # 3. Test FFmpeg & FFprobe
    from app.config import CHROME_BINARY_PATH
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        try:
            res = subprocess.run([ffmpeg_bin, "-version"], capture_output=True, text=True)
            ver_line = res.stdout.splitlines()[0] if res.stdout else "Available"
            results["FFmpeg"] = (True, ver_line[:40])
        except Exception as e:
            results["FFmpeg"] = (False, str(e))
    else:
        results["FFmpeg"] = (False, "Chưa tìm thấy trên PATH")

    # 4. Test Lệnh thực thi CLI (aiv / aiv.bat)
    aiv_cmd = shutil.which("aiv") or shutil.which("aiv.bat") or shutil.which("aiv.exe")
    if aiv_cmd:
        results["Lệnh thực thi CLI (aiv)"] = (True, f"Sẵn sàng ({aiv_cmd})")
    elif (BASE_DIR / "aiv.bat").exists() or (BASE_DIR / "aiv").exists():
        if str(BASE_DIR.resolve()).lower() in os.environ.get("PATH", "").lower():
            results["Lệnh thực thi CLI (aiv)"] = (True, f"Đã nạp vào PATH ({BASE_DIR.name})")
        else:
            results["Lệnh thực thi CLI (aiv)"] = (True, f"Đã cấu hình tại {BASE_DIR} (Mở terminal mới để nhận)")
    else:
        results["Lệnh thực thi CLI (aiv)"] = (False, "Chưa tìm thấy file thực thi aiv.bat hoặc aiv")

    # 5. Test Chrome Headless Screenshot
    if CHROME_BINARY_PATH and os.path.exists(CHROME_BINARY_PATH):
        try:
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
                f.write("<h1 style='color:red;'>Test</h1>")
                temp_html = f.name
            temp_png = Path(tempfile.gettempdir()) / "test_chrome_shot.png"

            cmd = [
                CHROME_BINARY_PATH,
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                f"--screenshot={temp_png}",
                temp_html
            ]
            subprocess.run(cmd, capture_output=True, timeout=10)
            if temp_png.exists() and temp_png.stat().st_size > 0:
                results["Chrome Headless Overlay"] = (True, "Chụp ảnh PNG thành công")
                temp_png.unlink(missing_ok=True)
            else:
                results["Chrome Headless Overlay"] = (False, "Không thể sinh ảnh screenshot")
            Path(temp_html).unlink(missing_ok=True)
        except Exception as e:
            results["Chrome Headless Overlay"] = (False, str(e))
    else:
        results["Chrome Headless Overlay"] = (False, f"Không tìm thấy: {CHROME_BINARY_PATH}")

    # 6. Kiểm tra API Key Gemini
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        results["Gemini API Key"] = (True, f"{gemini_key[:8]}... (Đã cấu hình)")
    else:
        results["Gemini API Key"] = (True, "Sử dụng key truyền qua CLI / script")

    # In bảng tổng kết
    print(f"\n{UI.BOLD}📊 BẢNG TỔNG KẾT TRẠNG THÁI HỆ THỐNG:{UI.RESET}")
    all_ok = True
    for component, (status, detail) in results.items():
        if status:
            print(f"  {UI.GREEN}[✓] {component:<28}: {detail}{UI.RESET}")
        else:
            all_ok = False
            print(f"  {UI.RED}[✗] {component:<28}: {detail}{UI.RESET}")

    return all_ok


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================
def main():
    UI.header("AI VIDEO CREATOR - TRÌNH THIẾT LẬP TỰ ĐỘNG WINDOWS")
    print(" Bắt đầu quy trình tự động cài đặt môi trường, thư viện và công cụ...\n")

    sys_info = check_system()
    upgrade_pip()
    install_pytorch(has_nvidia=sys_info["has_nvidia"])
    install_requirements()
    setup_ffmpeg()
    check_chrome()
    setup_aiv_cli()
    scaffold_directories()
    all_ok = run_diagnostics()

    if all_ok:
        UI.header("🎉 THIẾT LẬP HOÀN TẤT THÀNH CÔNG!")
        print(f"{UI.GREEN}{UI.BOLD}Hệ thống đã sẵn sàng 100% để sản xuất video TikTok tự động!{UI.RESET}\n")
        print("▶ Cách khởi chạy nhanh pipeline sản xuất video:")
        print(f"  {UI.CYAN}1. Cách 1 - Lệnh toàn cục (Khuyên dùng): Mở terminal tại bất kỳ thư mục media nào và gõ:{UI.RESET}")
        print(f"     {UI.BOLD}aiv{UI.RESET}  (hoặc tùy biến: {UI.BOLD}aiv --num-videos 10 --speed 1.2{UI.RESET})")
        print(f"  {UI.CYAN}2. Cách 2 - Soạn nội dung tuyển dụng và chạy script PowerShell:{UI.RESET}")
        print(f"     {UI.BOLD}.\\ff.ps1{UI.RESET}\n")
    else:
        UI.header("⚠️ THIẾT LẬP CÓ CẢNH BÁO")
        print(f"{UI.YELLOW}Một số thành phần cần bạn kiểm tra lại chi tiết phía trên.{UI.RESET}\n")


if __name__ == "__main__":
    main()

