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

        # 3. Loại bỏ các comment // và /* ... */
        text = re.sub(r"//.*", "", text)
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # 4. Fallback làm sạch unquoted keys và trailing commas
            cleaned_text = re.sub(r"([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1"\2":', text)
            cleaned_text = re.sub(r",\s*([\]\}])", r"\1", cleaned_text)
            try:
                parsed = json.loads(cleaned_text)
            except Exception as e:
                logger.error(f"Không thể phân tích cú pháp JSON từ phản hồi LLM: {text[:200]}... Lỗi: {e}")
                raise LLMResponseParsingError(
                    f"Phản hồi từ LLM không đúng định dạng JSON hợp lệ: {e}\nNội dung thô: {text[:200]}..."
                ) from e

        if not isinstance(parsed, dict):
            raise LLMResponseParsingError(
                f"Kết quả phân tích JSON không phải dạng đối tượng (dict): {type(parsed).__name__}"
            )
        return parsed
