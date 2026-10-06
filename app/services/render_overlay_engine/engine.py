import copy
import logging
import os
import shutil
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from app.config import CHROME_BINARY_PATH, TEMP_DIR, VIDEO_HEIGHT, VIDEO_WIDTH
from app.services.render_overlay_engine.fonts import resolve_font
from app.services.render_overlay_engine.palettes import ColorPalette, resolve_palette
from app.services.render_overlay_engine.styles import BaseOverlayStyle, BubbleCloudStyle

logger = logging.getLogger(__name__)

# Nhận diện môi trường Windows để áp dụng các cờ tối ưu hóa kernel và tiến trình
IS_WINDOWS = os.name == "nt"

# Flags triệt tiêu overhead phân bổ console window và GUI context switching trên Windows
WIN_CREATIONFLAGS = 0x08000000 if IS_WINDOWS else 0  # CREATE_NO_WINDOW

# Tập cờ dòng lệnh tối ưu hóa hiệu năng cao nhất cho Google Chrome Headless
# - Loại bỏ triệt để các module không cần thiết (Crashpad, Audio, Extensions, Sync, V8 WASM)
# - Ngăn chặn tính năng tiết kiệm điện / Eco Mode của Windows 10/11 tự động dìm xung CPU của tiến trình con
OPTIMIZED_CHROME_FLAGS = [
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--hide-scrollbars",
    "--default-background-color=00000000",
    "--disable-extensions",
    "--disable-default-apps",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-breakpad",  # Không spawn tiến trình crashpad_handler.exe trên Windows
    "--disable-component-update",
    "--disable-domain-reliability",
    "--disable-sync",
    "--disable-translate",
    "--disable-features=AudioServiceOutOfProcess,IsolateOrigins,site-per-process,TranslateUI,BackForwardCache,AcceptCHFrame,MediaRouter,OptimizationHints,CertificateTransparencyComponentUpdater,AutofillServerCommunication",
    "--no-first-run",
    "--no-default-browser-check",
    "--mute-audio",
    "--run-all-compositor-stages-before-draw",  # Render hoàn tất ngay không cần chờ frame idle
    "--disable-web-security",
    "--allow-file-access-from-files",
    "--disable-site-isolation-trials",
    "--disable-software-rasterizer",
    "--force-device-scale-factor=1",
    "--js-flags=--no-expose-wasm",
]


class RenderOverlayEngine:
    """
    Engine tạo đồ họa chữ đè (Overlay Graphics & Titles) dạng ảnh PNG trong suốt 32-bit (RGBA)
    bằng Google Chrome Headless và HTML5/CSS3.
    
    Được tối ưu hóa chuyên sâu cho Windows:
    - Loại bỏ overhead phân bổ console window và GUI switching (CREATE_NO_WINDOW, SW_HIDE).
    - Áp dụng các cờ Chrome Headless tinh gọn nhất để rút ngắn thời gian khởi động ~45-50%.
    - Bộ nhớ đệm (disk cache) cho Google Fonts giúp triệt tiêu độ trễ mạng cho các frame tiếp theo.
    - Phân bổ profile độc lập theo worker/thread nhằm tránh file lock / profile collision khi chạy song song.
    
    Tuân thủ nguyên lý Đa hình (Polymorphism) & Đóng Mở (Open-Closed Principle):
    Engine chỉ nhận BaseOverlayStyle mà không phụ thuộc vào bất kỳ Style cụ thể nào.
    Khi bổ sung style mới, chỉ cần khai báo thêm class style mà không cần sửa đổi Engine.
    """

    def __init__(self, chrome_path: Optional[str] = None):
        self.chrome_path = chrome_path or CHROME_BINARY_PATH
        if not os.path.exists(self.chrome_path) and not self._is_executable_in_path(self.chrome_path):
            logger.warning(f"Google Chrome không tìm thấy tại: {self.chrome_path}")

        # Thư mục cache dùng chung cho Chrome (lưu font Google Fonts và CSS, tăng tốc các lần render tiếp theo)
        self.disk_cache_dir = TEMP_DIR / "chrome_cache"
        self.disk_cache_dir.mkdir(parents=True, exist_ok=True)

        # Thư mục profile cho từng worker/thread để tránh profile collision / file lock trên Windows
        self.profiles_dir = TEMP_DIR / "chrome_profiles"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

        # Thư mục file HTML tạm thời
        self.temp_html_dir = TEMP_DIR / "chrome_html"
        self.temp_html_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _is_executable_in_path(cmd: str) -> bool:
        """Kiểm tra lệnh có tồn tại trong PATH hệ thống hay không"""
        from shutil import which
        return which(cmd) is not None

    def _get_worker_profile_dir(self, worker_id: Optional[Union[int, str]] = None) -> Path:
        """
        Trả về thư mục profile độc lập cho mỗi lần chụp ảnh.
        Trên Windows, Chrome sẽ lock profile (SingletonLock / lockfile).
        Sử dụng định danh duy nhất (UUID) cho mỗi lần chụp đảm bảo 100% không bị lockfile conflict,
        kể cả khi các luồng hoặc tiến trình chạy song song hay liên tiếp với tần suất cao.
        Trong khi đó, toàn bộ font chữ và CSS tải về vẫn được lưu trữ và dùng chung từ disk_cache_dir.
        """
        unique_token = uuid.uuid4().hex[:8]
        if worker_id is not None:
            profile_dir = self.profiles_dir / f"w_{worker_id}_{unique_token}"
        else:
            profile_dir = self.profiles_dir / f"t_{threading.get_ident()}_{unique_token}"
        profile_dir.mkdir(parents=True, exist_ok=True)
        return profile_dir

    def _get_subprocess_kwargs(self) -> Dict[str, Any]:
        """Cấu hình tối ưu hóa subprocess trên Windows"""
        kwargs: Dict[str, Any] = {}
        if IS_WINDOWS:
            kwargs["creationflags"] = WIN_CREATIONFLAGS
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            kwargs["startupinfo"] = startupinfo
        return kwargs

    def render(
        self,
        content: str,
        subcontent: Optional[str] = None,
        style: Optional[BaseOverlayStyle] = None,
        font: Optional[str] = None,
        palette: Optional[Union[str, ColorPalette, List[str], Tuple[str, ...]]] = None,
        palette_tag: Optional[str] = None,
        output_path: Optional[Union[str, Path]] = None,
        width: int = VIDEO_WIDTH,
        height: int = VIDEO_HEIGHT,
        timeout: float = 15.0,
        worker_id: Optional[Union[int, str]] = None
    ) -> Path:
        """
        Render tiêu đề overlay thành 1 file ảnh PNG trong suốt.
        
        Args:
            content: Nội dung chính (Tiêu đề / Headline).
            subcontent: Nội dung phụ (Điểm nhấn / Subtitle / Quyền lợi), có thể để trống hoặc None.
            style: Đối tượng kế thừa BaseOverlayStyle định nghĩa phong cách đồ họa.
            font: Tên font chữ (VD: 'Cherry Bomb One', 'Roboto'). Nếu None, tự động random từ danh mục font.
            palette: Bảng màu Color Hunt (ID, ColorPalette, hoặc 4 mã hex). Nếu None, tự động random từ 50+ bảng màu Color Hunt.
            palette_tag: Tag lọc bảng màu khi random (VD: 'pastel', 'retro', 'neon', 'warm', 'cold', 'candy').
            output_path: Đường dẫn lưu file PNG (tự sinh file tạm nếu None).
            width: Chiều rộng canvas (mặc định 1080).
            height: Chiều cao canvas (mặc định 1920).
            timeout: Thời gian chờ tối đa cho tiến trình Chrome Headless (giây).
            worker_id: Mã định danh luồng/worker tùy chọn để cô lập Chrome profile khi chạy song song.
            
        Returns:
            Path trỏ đến file ảnh PNG đã tạo thành công.
        """
        clean_content = (content or "").strip()
        if not clean_content:
            raise ValueError("Tham số 'content' không được để trống khi render overlay.")

        # Nếu không truyền style, sử dụng BubbleCloudStyle làm mặc định (dùng deepcopy để bảo đảm thread-safe)
        resolved_style = copy.deepcopy(style) if style is not None else BubbleCloudStyle()

        # Xác định font chữ: nếu None thì tự động random 1 font từ danh mục định nghĩa sẵn
        effective_font = font or getattr(resolved_style, "font", None)
        selected_font = resolve_font(effective_font)
        resolved_style.apply_font(selected_font)

        # Xác định bảng màu: nếu None thì tự động random 1 bảng màu từ 50+ bảng màu Color Hunt
        effective_palette = palette or getattr(resolved_style, "palette", None)
        selected_palette = resolve_palette(effective_palette, tag=palette_tag)
        resolved_style.apply_palette(selected_palette)

        # Đồng bộ ngược lại font và palette vào instance style gốc (nếu được truyền vào và chưa có font/palette)
        # Giúp các lời gọi tiếp theo tái sử dụng cùng style instance sẽ giữ nguyên font & palette nhất quán
        if style is not None:
            if getattr(style, "font", None) is None:
                style.apply_font(selected_font)
            if getattr(style, "palette", None) is None:
                style.apply_palette(selected_palette)

        logger.info(
            f"Render overlay với font: '{selected_font}' | "
            f"Palette: '{selected_palette.name}' ({selected_palette.id}) | "
            f"Style: {resolved_style.__class__.__name__}"
        )

        # Xác định đường dẫn file PNG đầu ra
        if output_path is None:
            resolved_output = TEMP_DIR / f"overlay_{uuid.uuid4().hex[:12]}.png"
        else:
            resolved_output = Path(output_path)
            
        resolved_output.parent.mkdir(parents=True, exist_ok=True)

        # 1. Sinh mã HTML hoàn chỉnh thông qua phương thức render_html của style class
        html_code = resolved_style.render_html(
            content=clean_content,
            subcontent=subcontent,
            width=width,
            height=height
        )

        # 2. Tạo file HTML tạm thời để Chrome Headless đọc
        temp_html = self.temp_html_dir / f"temp_{uuid.uuid4().hex[:8]}.html"
        temp_html.write_text(html_code, encoding="utf-8")

        try:
            # 3. Chạy Chrome Headless chụp ảnh màn hình PNG với nền trong suốt
            self._capture_screenshot(
                html_path=temp_html,
                output_png_path=resolved_output,
                width=width,
                height=height,
                timeout=timeout,
                worker_id=worker_id
            )
        finally:
            # Dọn dẹp file tạm ngay lập tức
            if temp_html.exists():
                try:
                    temp_html.unlink()
                except OSError as err:
                    logger.debug(f"Không thể xóa file tạm {temp_html}: {err}")

        return resolved_output

    def _capture_screenshot(
        self,
        html_path: Path,
        output_png_path: Path,
        width: int,
        height: int,
        timeout: float,
        worker_id: Optional[Union[int, str]] = None
    ) -> None:
        """Thực thi Chrome Headless CLI chụp ảnh PNG trong suốt được tối ưu tốc độ tối đa trên Windows"""
        profile_dir = self._get_worker_profile_dir(worker_id)

        cmd = [
            self.chrome_path,
            *OPTIMIZED_CHROME_FLAGS,
            f"--window-size={width},{height}",
            f"--disk-cache-dir={self.disk_cache_dir.resolve()}",
            f"--user-data-dir={profile_dir.resolve()}",
            f"--screenshot={output_png_path.resolve()}",
            str(html_path.resolve())
        ]

        sp_kwargs = self._get_subprocess_kwargs()

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                **sp_kwargs
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"Chrome Headless render quá thời gian {timeout}s: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"Lỗi khi thực thi Chrome Headless tại {self.chrome_path}: {exc}") from exc
        finally:
            if profile_dir.exists():
                try:
                    shutil.rmtree(profile_dir, ignore_errors=True)
                except Exception:
                    pass

        if res.returncode != 0 or not output_png_path.exists() or output_png_path.stat().st_size == 0:
            stderr_msg = res.stderr.decode("utf-8", errors="ignore").strip()
            raise RuntimeError(
                f"Chrome Headless thất bại với mã lỗi {res.returncode}. "
                f"Đường dẫn file: {output_png_path}. Chi tiết lỗi: {stderr_msg}"
            )

    def render_batch(
        self,
        items: List[Dict[str, Any]],
        output_dir: Path,
        default_font: Optional[str] = None,
        default_palette: Optional[Union[str, ColorPalette, List[str], Tuple[str, ...]]] = None,
        default_palette_tag: Optional[str] = None,
        max_workers: int = 4
    ) -> List[Path]:
        """
        Render song song nhiều overlay items bằng ThreadPoolExecutor.
        Được tối ưu để phân bổ worker slot độc lập cho mỗi thread, đảm bảo tối đa hiệu năng đa nhân CPU.
        
        Mỗi item trong list là một dict gồm:
            - 'content': str (bắt buộc)
            - 'subcontent': Optional[str] (tùy chọn)
            - 'style': Optional[BaseOverlayStyle] (tùy chọn)
            - 'font': Optional[str] (tùy chọn, nếu None sẽ dùng default_font hoặc batch_font)
            - 'palette': Optional[Union[str, ColorPalette]] (tùy chọn, nếu None sẽ dùng default_palette hoặc batch_palette)
            - 'palette_tag': Optional[str] (tùy chọn, ví dụ 'pastel', 'retro')
            - 'filename': Optional[str] (tùy chọn tên file, ví dụ 'scene_1.png')
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Cố định font & palette đồng nhất cho toàn bộ items trong batch (nếu chưa truyền)
        batch_font = resolve_font(default_font) if default_font is not None else resolve_font(None)
        batch_palette = (
            resolve_palette(default_palette, tag=default_palette_tag)
            if default_palette is not None
            else resolve_palette(None, tag=default_palette_tag)
        )

        results: List[Optional[Path]] = [None] * len(items)

        def _worker(index: int, item_data: Dict[str, Any]) -> tuple[int, Path]:
            content = item_data.get("content", "")
            subcontent = item_data.get("subcontent")
            item_style = item_data.get("style")
            item_font = item_data.get("font") or batch_font
            item_palette = item_data.get("palette") or batch_palette
            item_palette_tag = item_data.get("palette_tag") or default_palette_tag
            filename = item_data.get("filename") or f"overlay_{index:03d}.png"
            target_path = output_dir / filename
            worker_slot = index % max_workers

            rendered_path = self.render(
                content=content,
                subcontent=subcontent,
                style=item_style,
                font=item_font,
                palette=item_palette,
                palette_tag=item_palette_tag,
                output_path=target_path,
                worker_id=worker_slot
            )
            return index, rendered_path

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(_worker, idx, item): idx
                for idx, item in enumerate(items)
            }
            for future in as_completed(future_to_idx):
                idx, path = future.result()
                results[idx] = path

        return [p for p in results if p is not None]

    def render_for_scene(
        self,
        scene: Any,
        output_path: Path,
        style: Optional[BaseOverlayStyle] = None,
        font: Optional[str] = None,
        palette: Optional[Union[str, ColorPalette, List[str], Tuple[str, ...]]] = None,
        worker_id: Optional[Union[int, str]] = None
    ) -> Path:
        """
        Adapter method hỗ trợ tương thích ngược với entity ScriptScene.
        Trích xuất overlay_title và overlay_highlight từ scene và thực hiện render.
        """
        content = getattr(scene, "overlay_title", "")
        subcontent = getattr(scene, "overlay_highlight", "")
        scene_font = font or getattr(scene, "font", None) or getattr(style, "font", None)
        scene_palette = palette or getattr(scene, "palette", None) or getattr(style, "palette", None)
        return self.render(
            content=content,
            subcontent=subcontent,
            style=style,
            font=scene_font,
            palette=scene_palette,
            output_path=output_path,
            worker_id=worker_id
        )

    def warm_up(self, fonts: Optional[List[str]] = None) -> None:
        """
        Khởi động trước tiến trình Chrome và làm ấm (warm-up) disk cache font.
        Có thể gọi trước khi bắt đầu pipeline để đảm bảo frame đầu tiên không bị độ trễ cold-start.
        """
        try:
            sample_style = BubbleCloudStyle()
            dummy_target = self.temp_html_dir / "warmup.png"
            self.render(
                content="WARMUP",
                subcontent="OK",
                style=sample_style,
                font=fonts[0] if fonts else "Nunito",
                output_path=dummy_target
            )
            if dummy_target.exists():
                dummy_target.unlink()
            logger.info("Chrome Overlay Engine warm-up completed successfully.")
        except Exception as exc:
            logger.debug(f"Chrome warm-up ignored error: {exc}")

    def clear_cache(self) -> None:
        """Dọn dẹp thư mục disk cache và profiles tạm thời khi cần thiết"""
        for d in [self.disk_cache_dir, self.profiles_dir, self.temp_html_dir]:
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
                d.mkdir(parents=True, exist_ok=True)
