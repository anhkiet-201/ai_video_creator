"""Interface trừu tượng BaseLLMProvider định nghĩa hành vi chung cho các dịch vụ LLM."""

from abc import ABC, abstractmethod
import json
import logging
import re
from typing import Any, Dict, Optional, Union

from app.services.llm.exceptions import LLMResponseParsingError

logger = logging.getLogger(__name__)


class BaseLLMProvider(ABC):
    """Lớp cơ sở trừu tượng cho tất cả các LLM Providers (Gemini, LM Studio, v.v.)."""

    def __init__(self, model_name: str = "", **kwargs: Any) -> None:
        self.model_name = model_name

    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> str:
        """Sinh phản hồi dạng văn bản thuần từ LLM."""
        pass

    @abstractmethod
    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        json_schema: Optional[Union[Dict[str, Any], str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Sinh phản hồi và phân tích cú pháp thành Dictionary/JSON an toàn từ LLM."""
        pass

    def clean_and_parse_json(self, raw_text: str) -> Dict[str, Any]:
        """Làm sạch markdown code fences và trích xuất khối JSON an toàn từ phản hồi LLM."""
        if not raw_text or not raw_text.strip():
            raise LLMResponseParsingError("Phản hồi thô từ LLM rỗng, không thể phân tích cú pháp JSON.")

        text = raw_text.strip()

        # 1. Loại bỏ markdown code fences (```json ... ``` hoặc ``` ... ```)
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # 2. Tìm kiếm khối JSON hợp lệ nằm giữa cặp ngoặc nhọn ngoài cùng
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

        # 3. Loại bỏ các comment //, /* ... */, và # (Python-style)
        text = re.sub(r"//.*", "", text)
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        text = re.sub(r"^\s*#.*", "", text, flags=re.MULTILINE)

        # 4. Chuẩn hóa dấu nháy cong thông minh (Smart / Curly quotes)
        text = text.replace("“", '"').replace("”", '"')
        text = text.replace("‘", "'").replace("’", "'")

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # 5. Chuẩn hóa các khiếm khuyết cú pháp phổ biến sang chuẩn JSON RFC 8259:
            # a) Khóa dùng nháy đơn: 'key': -> "key":
            cleaned_text = re.sub(r"([{,]\s*)'([a-zA-Z_][a-zA-Z0-9_]*)'\s*:", r'\1"\2":', text)
            # b) Khóa không dùng nháy: key: -> "key":
            cleaned_text = re.sub(r"([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1"\2":', cleaned_text)
            # c) Giá trị chuỗi dùng nháy đơn: : 'value' -> : "value"
            cleaned_text = re.sub(r":\s*'([^'\n\r]*)'", r': "\1"', cleaned_text)
            # d) Dấu phẩy thừa trước ngoặc đóng: , } hoặc , ]
            cleaned_text = re.sub(r",\s*([\]\}])", r"\1", cleaned_text)
            # e) Dấu phẩy lặp: ,, -> ,
            cleaned_text = re.sub(r",\s*,", ",", cleaned_text)

            try:
                parsed = json.loads(cleaned_text)
            except Exception as e:
                line_num = getattr(e, "lineno", None)
                col_num = getattr(e, "colno", None)
                pos = getattr(e, "pos", None)
                context_snippet = ""
                if pos is not None and isinstance(pos, int):
                    start = max(0, pos - 80)
                    end = min(len(cleaned_text), pos + 80)
                    context_snippet = f"\nNgữ cảnh lỗi (pos {pos}): ...{cleaned_text[start:end]}..."
                logger.error(
                    f"Không thể phân tích cú pháp JSON từ phản hồi LLM: Dòng {line_num}, Cột {col_num}. Lỗi: {e}{context_snippet}"
                )
                raise LLMResponseParsingError(
                    f"Phản hồi từ LLM không đúng định dạng JSON hợp lệ: {e} (Dòng {line_num}, Cột {col_num}){context_snippet}"
                ) from e

        if not isinstance(parsed, dict):
            raise LLMResponseParsingError(
                f"Kết quả phân tích JSON không phải dạng đối tượng (dict): {type(parsed).__name__}"
            )
        return parsed
