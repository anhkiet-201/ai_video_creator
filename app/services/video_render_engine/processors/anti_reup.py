"""Anti-Reup Engine - Bộ sinh ngẫu nhiên các thông số vi mô tùy biến (Dynamic Parameter Randomizer)."""

from datetime import datetime, timedelta
import logging
import random
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import uuid

from app.services.video_render_engine.core.models import AntiReupProfile

logger = logging.getLogger(__name__)

# Gợi ý quy tắc ngẫu nhiên mẫu (người dùng có thể định nghĩa bất kỳ thông số nào tùy theo renderer)
DEFAULT_RANDOM_RULES: Dict[str, Any] = {
    "speed": (0.985, 1.015),             # Tốc độ phát (min, max)
    "zoom": (1.01, 1.035),               # Tỷ lệ phóng to (min, max)
    "brightness": (-0.03, 0.03),         # Độ sáng vi mô (min, max)
    "contrast": (0.97, 1.03),            # Độ tương phản (min, max)
    "saturation": (0.97, 1.03),          # Độ bão hòa màu (min, max)
    "flip_horizontal": [False],          # Mặc định không lật ngang để giữ chữ overlay luôn chuẩn
}


class AntiReupEngine:
    """Động cơ sinh ngẫu nhiên các thông số chống nhận diện trùng lặp (Anti-Reup Parameter Randomizer).

    Bản chất của Anti-Reup là cơ chế random các thông số kỹ thuật/thuộc tính video theo
    dải giá trị (ranges/choices/distributions) do người dùng hoặc renderer cấu hình.
    Hoàn toàn không hardcode danh sách thông số cố định.
    """

    def __init__(self, rules: Optional[Dict[str, Any]] = None):
        """Khởi tạo engine với tập quy tắc random tùy chỉnh hoặc mẫu gợi ý."""
        self._rules: Dict[str, Any] = dict(rules if rules is not None else DEFAULT_RANDOM_RULES)

    # --- Các hàm tiện ích sinh ngẫu nhiên toán học thuần túy ---

    @staticmethod
    def random_range(min_val: float, max_val: float, precision: int = 4, seed: Optional[int] = None) -> float:
        """Sinh một số thực ngẫu nhiên trong khoảng [min_val, max_val] với độ chính xác chỉ định."""
        rng = random.Random(seed)
        return round(rng.uniform(float(min_val), float(max_val)), precision)

    @staticmethod
    def random_int(min_val: int, max_val: int, seed: Optional[int] = None) -> int:
        """Sinh một số nguyên ngẫu nhiên trong khoảng [min_val, max_val]."""
        rng = random.Random(seed)
        return rng.randint(int(min_val), int(max_val))

    @staticmethod
    def random_choice(choices: List[Any], seed: Optional[int] = None) -> Any:
        """Chọn ngẫu nhiên một phần tử từ danh sách."""
        if not choices:
            return None
        rng = random.Random(seed)
        return rng.choice(choices)

    @staticmethod
    def random_jitter(base_value: float, percent_range: Tuple[float, float], precision: int = 4, seed: Optional[int] = None) -> float:
        """Dao động ngẫu nhiên một giá trị gốc theo tỷ lệ phần trăm (ví dụ: base=30fps, range=(-0.02, 0.02))."""
        rng = random.Random(seed)
        delta_pct = rng.uniform(float(percent_range[0]), float(percent_range[1]))
        return round(base_value * (1.0 + delta_pct), precision)

    # --- Quản lý các quy tắc tham số động ---

    def set_rule(self, param_name: str, rule: Union[Tuple[Any, Any], list, Callable, Any]) -> None:
        """Thêm hoặc ghi đè một quy tắc sinh ngẫu nhiên cho một thông số cụ thể."""
        self._rules[param_name] = rule

    def remove_rule(self, param_name: str) -> None:
        """Xóa bỏ một quy tắc thông số."""
        self._rules.pop(param_name, None)

    def set_rules(self, rules: Dict[str, Any]) -> None:
        """Thiết lập toàn bộ tập quy tắc sinh ngẫu nhiên mới."""
        self._rules = dict(rules)

    def get_rules(self) -> Dict[str, Any]:
        """Lấy danh sách các quy tắc sinh ngẫu nhiên hiện tại."""
        return dict(self._rules)

    def randomize(
        self,
        custom_rules: Optional[Dict[str, Any]] = None,
        seed: Optional[int] = None,
    ) -> AntiReupProfile:
        """Thực hiện ngẫu nhiên hóa toàn bộ các thông số theo tập quy tắc đã định nghĩa.

        Hỗ trợ các kiểu định dạng quy tắc:
        - Tuple (min, max) số thực: sinh random float uniform.
        - Tuple (min, max) số nguyên: sinh random int.
        - List [a, b, c]: chọn random phần tử.
        - Callable(rng): hàm tùy biến trả về giá trị ngẫu nhiên.
        - Giá trị tĩnh: giữ nguyên.

        Returns:
            AntiReupProfile chứa từ điển params đã được random.
        """
        rng = random.Random(seed)
        active_rules = dict(self._rules)
        if custom_rules:
            active_rules.update(custom_rules)

        generated_params: Dict[str, Any] = {}

        for param_name, rule in active_rules.items():
            val = self._evaluate_rule(rule, rng)
            generated_params[param_name] = val

        # Tự động gắn thêm UUID ngẫu nhiên và metadata thời gian nếu người dùng chưa tự định nghĩa
        if "metadata_uuid" not in generated_params:
            generated_params["metadata_uuid"] = str(uuid.uuid4())

        if "metadata_date" not in generated_params:
            fake_days = rng.randint(1, 7)
            fake_hours = rng.randint(1, 23)
            fake_time = datetime.now() - timedelta(days=fake_days, hours=fake_hours)
            generated_params["metadata_date"] = fake_time.strftime("%Y-%m-%dT%H:%M:%S")

        logger.debug(f"AntiReupEngine đã sinh ngẫu nhiên {len(generated_params)} thông số")
        return AntiReupProfile(params=generated_params)

    def generate_profile(
        self,
        level: Optional[str] = None,
        custom_rules: Optional[Dict[str, Any]] = None,
        seed: Optional[int] = None,
    ) -> AntiReupProfile:
        """Hàm alias tương thích ngược, thực hiện ngẫu nhiên hóa thông số."""
        return self.randomize(custom_rules=custom_rules, seed=seed)

    @staticmethod
    def _evaluate_rule(rule: Any, rng: random.Random) -> Any:
        """Xử lý sinh giá trị ngẫu nhiên cho một quy tắc cụ thể."""
        if callable(rule):
            return rule(rng)

        if isinstance(rule, tuple) and len(rule) == 2:
            low, high = rule
            if isinstance(low, int) and isinstance(high, int):
                return rng.randint(low, high)
            if isinstance(low, (int, float)) and isinstance(high, (int, float)):
                return round(rng.uniform(float(low), float(high)), 4)

        if isinstance(rule, list) and len(rule) > 0:
            return rng.choice(rule)

        return rule
