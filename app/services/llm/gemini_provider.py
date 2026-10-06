"""Gemini LLM Provider triển khai giao thức BaseLLMProvider với SDK google-genai và cơ chế xoay vòng key."""

import logging
from typing import Any, Dict, List, Optional, Union

from app.services.key_rotator import KeyRotator
from app.services.llm.base import BaseLLMProvider
from app.services.llm.exceptions import (
    LLMEmptyResponseError,
    LLMProviderError,
    LLMQuotaExhaustedError,
    LLMResponseParsingError,
)

logger = logging.getLogger(__name__)


class GeminiLLMProvider(BaseLLMProvider):
    """Triển khai LLM Provider cho Google Gemini AI với cơ chế xoay vòng API Keys."""

    def __init__(
        self,
        api_keys: Optional[Union[List[str], str]] = None,
        model_name: str = "gemini-2.5-flash",
        key_rotator: Optional[KeyRotator] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model_name=model_name or "gemini-2.5-flash", **kwargs)

        if key_rotator is not None:
            self.key_rotator = key_rotator
        else:
            initial_keys = []
            if api_keys:
                initial_keys = api_keys if isinstance(api_keys, list) else [api_keys]
            self.key_rotator = KeyRotator(initial_keys)

    def set_keys(self, api_keys: Union[List[str], str]) -> None:
        """Cập nhật danh sách API Keys mới cho KeyRotator."""
        keys_list = api_keys if isinstance(api_keys, list) else [api_keys]
        self.key_rotator.set_keys(keys_list)

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> str:
        """Sinh phản hồi văn bản từ Gemini AI kèm cơ chế xoay vòng API Keys."""
        return self._execute_request(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            is_json=False,
            **kwargs,
        )

    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        json_schema: Optional[Union[Dict[str, Any], str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Sinh phản hồi và phân tích cú pháp thành JSON từ Gemini AI."""
        raw_text = self._execute_request(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            is_json=True,
            **kwargs,
        )
        return self.clean_and_parse_json(raw_text)

    def _execute_request(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        is_json: bool = False,
        **kwargs: Any,
    ) -> str:
        """Thực thi request tới Google GenAI SDK với cơ chế xoay vòng API Key."""
        last_error_reason: str = ""

        if not self.key_rotator.has_available_keys():
            raise LLMQuotaExhaustedError(
                "Không tìm thấy Gemini API Key khả dụng hoặc danh sách api_keys rỗng. "
                "Vui lòng cung cấp ít nhất một API Key hợp lệ."
            )

        while self.key_rotator.has_available_keys():
            current_key = self.key_rotator.get_current_key()
            if not current_key:
                break

            masked_key = f"...{current_key[-6:]}" if len(current_key) >= 6 else current_key

            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=current_key)
                config_params: Dict[str, Any] = {
                    "temperature": temperature,
                }
                if system_prompt:
                    config_params["system_instruction"] = system_prompt
                if is_json:
                    config_params["response_mime_type"] = "application/json"

                response = client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_params),
                )

                if response and response.text:
                    return response.text

                last_error_reason = "Phản hồi từ Gemini API rỗng (response.text is empty)."
                logger.warning(f"Phản hồi rỗng khi gọi Gemini model {self.model_name} với key {masked_key}")

            except (LLMResponseParsingError, LLMEmptyResponseError):
                raise
            except Exception as e:
                err_msg = str(e)
                last_error_reason = err_msg
                logger.warning(f"Lỗi khi gọi Gemini API với key {masked_key}: {err_msg}")
                self.key_rotator.mark_key_failed(current_key, reason=err_msg)

        raise LLMQuotaExhaustedError(
            f"Không thể thực thi yêu cầu qua Gemini AI: Toàn bộ API Key trong danh sách đã bị lỗi quota hoặc hết hạn mức. "
            f"Lỗi gần nhất: {last_error_reason}"
        )
