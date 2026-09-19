import logging
from typing import List, Optional, Set

logger = logging.getLogger(__name__)


class KeyRotator:
    """Quản lý danh sách API Key với cơ chế Failover & Xoay Vòng tự động khi gặp lỗi 429 hoặc lỗi hạn mức"""

    def __init__(self, api_keys: Optional[List[str]] = None):
        self._keys: List[str] = []
        self._failed_keys: Set[str] = set()
        self._current_index: int = 0

        if api_keys:
            self.set_keys(api_keys)

    def set_keys(self, api_keys: List[str]) -> None:
        """Cập nhật danh sách API key, tự động bóc tách các chuỗi chứa dấu phẩy, chấm phẩy, khoảng trắng."""
        cleaned_keys: List[str] = []
        raw_items = api_keys if isinstance(api_keys, (list, tuple, set)) else [api_keys]
        for item in raw_items:
            if not isinstance(item, str):
                continue
            norm = item.replace(";", ",").replace("\n", ",").replace("\t", ",")
            for part in norm.split(","):
                for sub in part.strip().split():
                    cleaned = sub.strip(" \"'\t\r\n")
                    if cleaned and cleaned not in cleaned_keys:
                        cleaned_keys.append(cleaned)

        self._keys = cleaned_keys
        self._failed_keys.clear()
        self._current_index = 0
        logger.info(f"KeyRotator initialized with {len(self._keys)} unique keys.")

    def get_current_key(self) -> Optional[str]:
        """Lấy key khả dụng hiện tại. Nếu key hiện tại đã bị đánh dấu hỏng, tự động nhảy sang key kế tiếp."""
        if not self._keys:
            return None

        # Tìm key đầu tiên chưa bị đánh dấu lỗi bắt đầu từ _current_index
        for offset in range(len(self._keys)):
            idx = (self._current_index + offset) % len(self._keys)
            key = self._keys[idx]
            if key not in self._failed_keys:
                self._current_index = idx
                return key

        # Toàn bộ key đã bị đánh dấu lỗi
        return None

    def mark_key_failed(self, key: str, reason: str = "") -> Optional[str]:
        """Đánh dấu key bị lỗi (quota, 429, invalid) và chuyển sang key kế tiếp khả dụng"""
        logger.warning(f"API Key ...{key[-6:] if len(key) >= 6 else key} bị đánh dấu lỗi: {reason}")
        self._failed_keys.add(key)
        
        # Chuyển ngay sang key kế tiếp
        next_key = self.get_current_key()
        if next_key:
            logger.info(f"Đã tự động chuyển sang API key tiếp theo: ...{next_key[-6:] if len(next_key) >= 6 else next_key}")
        else:
            logger.error("Tất cả API keys trong danh sách đã bị đánh dấu lỗi hoặc hết hạn mức!")
        return next_key

    def has_available_keys(self) -> bool:
        """Kiểm tra xem còn key nào hoạt động được không"""
        return self.get_current_key() is not None

    def total_keys_count(self) -> int:
        return len(self._keys)

    def available_keys_count(self) -> int:
        return len([k for k in self._keys if k not in self._failed_keys])

    def reset_failed_keys(self) -> None:
        """Đặt lại trạng thái của tất cả các key (cho các lượt chạy mới)"""
        self._failed_keys.clear()
        self._current_index = 0
