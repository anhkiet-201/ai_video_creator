"""Output directory and filename formatting manager for Video Render Engine.

Formats outputs according to the structured pattern:
    outputs/{company_name}-{DD-MM-YYYY}/tik_final_{seq:02d}.mp4

Provides robust Unicode/Vietnamese slugification, thread-safe sequence
allocation, and collision-free file naming.
"""

import re
import unicodedata
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional

# Regex pattern to match existing output files: e.g. tik_final_01.mp4, tik_final_2.mp4
TIK_FINAL_PATTERN = re.compile(r"^tik_final_(\d+)\.mp4$", re.IGNORECASE)

# Thread lock to guarantee safe sequence allocation during parallel multi-threaded rendering
_ALLOCATION_LOCK = Lock()

# Vietnamese specific character map for accurate ASCII conversion (especially đ/Đ)
VIETNAMESE_MAP = {
    "à": "a", "á": "a", "ả": "a", "ã": "a", "ạ": "a",
    "ă": "a", "ằ": "a", "ắ": "a", "ẳ": "a", "ẵ": "a", "ặ": "a",
    "â": "a", "ầ": "a", "ấ": "a", "ẩ": "a", "ẫ": "a", "ậ": "a",
    "đ": "d",
    "è": "e", "é": "e", "ẻ": "e", "ẽ": "e", "ẹ": "e",
    "ê": "e", "ề": "e", "ế": "e", "ể": "e", "ễ": "e", "ệ": "e",
    "ì": "i", "í": "i", "ỉ": "i", "ĩ": "i", "ị": "i",
    "ò": "o", "ó": "o", "ỏ": "o", "õ": "o", "ọ": "o",
    "ô": "o", "ồ": "o", "ố": "o", "ổ": "o", "ỗ": "o", "ộ": "o",
    "ơ": "o", "ờ": "o", "ớ": "o", "ở": "o", "ỡ": "o", "ợ": "o",
    "ù": "u", "ú": "u", "ủ": "u", "ũ": "u", "ụ": "u",
    "ư": "u", "ừ": "u", "ứ": "u", "ử": "u", "ữ": "u", "ự": "u",
    "ỳ": "y", "ý": "y", "ỷ": "y", "ỹ": "y", "ỵ": "y",
    "À": "a", "Á": "a", "Ả": "a", "Ã": "a", "Ạ": "a",
    "Ă": "a", "Ằ": "a", "Ắ": "a", "Ẳ": "a", "Ẵ": "a", "Ặ": "a",
    "Â": "a", "Ầ": "a", "Ấ": "a", "Ẩ": "a", "Ẫ": "a", "Ậ": "a",
    "Đ": "d",
    "È": "e", "É": "e", "Ẻ": "e", "Ẽ": "e", "Ẹ": "e",
    "Ê": "e", "Ề": "e", "Ế": "e", "Ể": "e", "Ễ": "e", "Ệ": "e",
    "Ì": "i", "Í": "i", "Ỉ": "i", "Ĩ": "i", "Ị": "i",
    "Ò": "o", "Ó": "o", "Ỏ": "o", "Õ": "o", "Ọ": "o",
    "Ô": "o", "Ồ": "o", "Ố": "o", "Ổ": "o", "Ỗ": "o", "Ộ": "o",
    "Ơ": "o", "Ờ": "o", "Ớ": "o", "Ở": "o", "Ỡ": "o", "Ợ": "o",
    "Ù": "u", "Ú": "u", "Ủ": "u", "Ũ": "u", "Ụ": "u",
    "Ư": "u", "Ừ": "u", "Ứ": "u", "Ử": "u", "Ữ": "u", "Ự": "u",
    "Ỳ": "y", "Ý": "y", "Ỷ": "y", "Ỹ": "y", "Ỵ": "y",
}


def sanitize_company_slug(name: Optional[str], default_fallback: str = "company") -> str:
    """Convert any company name to a safe, lower-case, accent-free slug.

    Examples:
        'TechNova' -> 'technova'
        'FPT Telecom' -> 'fpt-telecom'
        'Kho Vận Thực Phẩm Hoàng Gia' -> 'kho-van-thuc-pham-hoang-gia'
        'Công Ty TNHH & TM @123!' -> 'cong-ty-tnhh-tm-123'
    """
    if not name or not name.strip():
        return default_fallback

    cleaned = name.strip()

    # 1. Map explicit Vietnamese special characters
    for k, v in VIETNAMESE_MAP.items():
        if k in cleaned:
            cleaned = cleaned.replace(k, v)

    # 2. Decompose remaining Unicode accents
    decomposed = unicodedata.normalize("NFKD", cleaned)
    ascii_chars = "".join(c for c in decomposed if not unicodedata.combining(c))

    # 3. Lowercase and replace non-alphanumeric characters with hyphens
    lowered = ascii_chars.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered)

    # 4. Remove leading/trailing hyphens and multiple consecutive hyphens
    slug = re.sub(r"-+", "-", slug).strip("-")

    return slug or default_fallback


def format_date_suffix(target_date: Optional[datetime] = None, date_format: str = "%d-%m-%Y") -> str:
    """Return date string formatted as DD-MM-YYYY (e.g. '18-09-2026')."""
    dt = target_date or datetime.now()
    return dt.strftime(date_format)


def build_company_dir_name(
    company_name: Optional[str],
    target_date: Optional[datetime] = None,
    date_format: str = "%d-%m-%Y",
    default_company: str = "company",
) -> str:
    """Build directory name: {company_slug}-{DD-MM-YYYY}."""
    slug = sanitize_company_slug(company_name, default_fallback=default_company)
    date_str = format_date_suffix(target_date=target_date, date_format=date_format)
    return f"{slug}-{date_str}"


def get_existing_max_index(target_dir: Path) -> int:
    """Scan target directory and find the highest numeric index among tik_final_*.mp4 files."""
    if not target_dir.exists() or not target_dir.is_dir():
        return 0

    max_idx = 0
    for entry in target_dir.iterdir():
        if entry.is_file():
            match = TIK_FINAL_PATTERN.match(entry.name)
            if match:
                try:
                    idx = int(match.group(1))
                    if idx > max_idx:
                        max_idx = idx
                except ValueError:
                    continue
    return max_idx


def allocate_next_output_path(
    base_output_dir: Path,
    company_name: Optional[str] = None,
    sequence_hint: Optional[int] = None,
    target_date: Optional[datetime] = None,
    date_format: str = "%d-%m-%Y",
) -> Path:
    """Allocate a collision-free output file path under the company date folder.

    Structure:
        {base_output_dir}/{company_slug}-{DD-MM-YYYY}/tik_final_{seq:02d}.mp4

    Args:
        base_output_dir: Root outputs folder (e.g. storage/outputs or outputs).
        company_name: Name of company/brand (e.g. 'TechNova').
        sequence_hint: Explicit sequence number (1, 2, ...). If file already exists,
                       the function automatically bumps to the next available index.
        target_date: Optional datetime for folder date. Defaults to current date.
        date_format: Pattern for folder date suffix. Defaults to '%d-%m-%Y'.

    Returns:
        Path to the resolved output MP4 file.
    """
    with _ALLOCATION_LOCK:
        dir_name = build_company_dir_name(
            company_name=company_name,
            target_date=target_date,
            date_format=date_format,
        )
        company_dir = base_output_dir / dir_name
        company_dir.mkdir(parents=True, exist_ok=True)

        max_existing = get_existing_max_index(company_dir)

        if sequence_hint is not None and sequence_hint > 0:
            target_index = sequence_hint
            # If the hinted sequence is already occupied on disk, advance beyond max_existing
            candidate = company_dir / f"tik_final_{target_index:02d}.mp4"
            if candidate.exists():
                target_index = max_existing + 1
        else:
            target_index = max_existing + 1

        # Double check candidate does not exist, advance if necessary
        while (company_dir / f"tik_final_{target_index:02d}.mp4").exists():
            target_index += 1

        final_path = company_dir / f"tik_final_{target_index:02d}.mp4"
        return final_path
