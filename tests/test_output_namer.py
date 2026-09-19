"""Unit tests for OutputNamer module in Video Render Engine."""

from datetime import datetime
from pathlib import Path
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest

from app.services.video_render_engine.output_namer import (
    allocate_next_output_path,
    build_company_dir_name,
    format_date_suffix,
    get_existing_max_index,
    sanitize_company_slug,
)


class TestOutputNamer(unittest.TestCase):
    """Test suite for output directory naming and file allocation."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_output_namer_"))

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_sanitize_company_slug_standard(self):
        self.assertEqual(sanitize_company_slug("TechNova"), "technova")
        self.assertEqual(sanitize_company_slug("FPT Telecom"), "fpt-telecom")
        self.assertEqual(sanitize_company_slug("Google LLC"), "google-llc")

    def test_02_sanitize_company_slug_vietnamese_accents(self):
        # Kiểm tra chuẩn hóa đầy đủ dấu tiếng Việt
        self.assertEqual(
            sanitize_company_slug("Kho Vận Thực Phẩm Hoàng Gia"),
            "kho-van-thuc-pham-hoang-gia",
        )
        # Kiểm tra chữ Đ / đ
        self.assertEqual(
            sanitize_company_slug("Điện Máy Đỏ & Đồng Nai"),
            "dien-may-do-dong-nai",
        )
        # Ký tự có dấu hỏi, ngã, nặng
        self.assertEqual(
            sanitize_company_slug("Cửa Hàng Sữa Mẹ & Bé"),
            "cua-hang-sua-me-be",
        )

    def test_03_sanitize_company_slug_special_characters(self):
        # Ký tự cấm trên OS: \ / : * ? " < > |
        raw = "Công Ty TNHH /\\:*?\"<>| & TM @2026!"
        slug = sanitize_company_slug(raw)
        self.assertEqual(slug, "cong-ty-tnhh-tm-2026")

    def test_04_sanitize_company_slug_fallback_when_empty(self):
        self.assertEqual(sanitize_company_slug(""), "company")
        self.assertEqual(sanitize_company_slug("   "), "company")
        self.assertEqual(sanitize_company_slug(None), "company")
        self.assertEqual(sanitize_company_slug("!@#$%", default_fallback="brand"), "brand")

    def test_05_format_date_suffix(self):
        fixed_date = datetime(2026, 9, 18, 14, 30)
        self.assertEqual(format_date_suffix(fixed_date), "18-09-2026")

    def test_06_build_company_dir_name(self):
        fixed_date = datetime(2026, 9, 18)
        dir_name = build_company_dir_name("TechNova", target_date=fixed_date)
        self.assertEqual(dir_name, "technova-18-09-2026")

        dir_vn = build_company_dir_name("Công Ty Hoàng Gia", target_date=fixed_date)
        self.assertEqual(dir_vn, "cong-ty-hoang-gia-18-09-2026")

    def test_07_allocate_next_output_path_sequential(self):
        fixed_date = datetime(2026, 9, 18)
        p1 = allocate_next_output_path(
            base_output_dir=self.temp_dir,
            company_name="TechNova",
            sequence_hint=1,
            target_date=fixed_date,
        )
        # Verify thư mục và tên file dạng 2 chữ số
        self.assertEqual(p1.parent.name, "technova-18-09-2026")
        self.assertEqual(p1.name, "tik_final_01.mp4")

        # Tạo file giả lập trên đĩa
        p1.touch()

        p2 = allocate_next_output_path(
            base_output_dir=self.temp_dir,
            company_name="TechNova",
            sequence_hint=2,
            target_date=fixed_date,
        )
        self.assertEqual(p2.name, "tik_final_02.mp4")
        p2.touch()

        p3 = allocate_next_output_path(
            base_output_dir=self.temp_dir,
            company_name="TechNova",
            sequence_hint=3,
            target_date=fixed_date,
        )
        self.assertEqual(p3.name, "tik_final_03.mp4")

    def test_08_allocate_next_output_path_collision_avoidance(self):
        """Nếu thư mục đã có sẵn tik_final_01.mp4 và tik_final_02.mp4 từ đợt trước,

        lần sau chạy dù sequence_hint=1 vẫn tự động tăng lên tik_final_03.mp4.
        """
        fixed_date = datetime(2026, 9, 18)
        target_dir = self.temp_dir / "fpt-telecom-18-09-2026"
        target_dir.mkdir(parents=True, exist_ok=True)

        (target_dir / "tik_final_01.mp4").touch()
        (target_dir / "tik_final_02.mp4").touch()

        # Đợt render mới, truyền hint = 1
        p_next = allocate_next_output_path(
            base_output_dir=self.temp_dir,
            company_name="FPT Telecom",
            sequence_hint=1,
            target_date=fixed_date,
        )
        self.assertEqual(p_next.name, "tik_final_03.mp4")
        p_next.touch()

        p_after = allocate_next_output_path(
            base_output_dir=self.temp_dir,
            company_name="FPT Telecom",
            sequence_hint=None,
            target_date=fixed_date,
        )
        self.assertEqual(p_after.name, "tik_final_04.mp4")

    def test_09_multithreaded_allocation_safe(self):
        """Kiểm tra an toàn tuyệt đối khi nhiều thread cùng xin cấp phát file."""
        fixed_date = datetime(2026, 9, 18)
        allocated_paths = []

        def _allocate_and_create(idx: int):
            path = allocate_next_output_path(
                base_output_dir=self.temp_dir,
                company_name="ConcurrentCorp",
                sequence_hint=None,
                target_date=fixed_date,
            )
            # Tạo file ngay lập tức để mô phỏng render xong
            path.touch()
            return path.name

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(_allocate_and_create, i) for i in range(10)]
            for f in futures:
                allocated_paths.append(f.result())

        # 10 file phải duy nhất không trùng lặp
        self.assertEqual(len(set(allocated_paths)), 10)
        expected = [f"tik_final_{i:02d}.mp4" for i in range(1, 11)]
        self.assertEqual(sorted(allocated_paths), sorted(expected))


if __name__ == "__main__":
    unittest.main()
