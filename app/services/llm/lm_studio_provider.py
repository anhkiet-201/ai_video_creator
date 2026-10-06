"""LM Studio LLM Provider triển khai BaseLLMProvider giao tiếp qua OpenAI-compatible API bằng httpx."""

import logging
from typing import Any, Dict, List, Optional, Union
import httpx

from app.services.llm.base import BaseLLMProvider
from app.services.llm.exceptions import (
    LLMConnectionError,
    LLMEmptyResponseError,
    LLMProviderError,
    LLMResponseParsingError,
)

logger = logging.getLogger(__name__)

DEFAULT_LM_STUDIO_URL = "http://localhost:1234/v1"


class LMStudioLLMProvider(BaseLLMProvider):
    """Triển khai LLM Provider cho LM Studio (hoặc các OpenAI-compatible local servers)."""

    def __init__(
        self,
        base_url: str = DEFAULT_LM_STUDIO_URL,
        model_name: str = "local-model",
        api_key: str = "lm-studio",
        timeout: float = 90.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(model_name=model_name or "local-model", **kwargs)
        raw_url = (base_url or DEFAULT_LM_STUDIO_URL).rstrip("/")
        if not raw_url.endswith("/v1"):
            raw_url = f"{raw_url}/v1"
        self.base_url = raw_url
        self.api_key = api_key or "lm-studio"
        self.timeout = float(timeout)

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> str:
        """Sinh phản hồi văn bản thuần từ LM Studio qua Chat Completions endpoint."""
        return self._send_chat_completion(
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
        """Sinh phản hồi và phân tích cú pháp thành JSON an toàn từ LM Studio."""
        raw_text = self._send_chat_completion(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            is_json=True,
            **kwargs,
        )
        return self.clean_and_parse_json(raw_text)

    def _send_chat_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        is_json: bool = False,
        **kwargs: Any,
    ) -> str:
        """Gửi request HTTP POST tới /v1/chat/completions."""
        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        messages: List[Dict[str, str]] = []
        if system_prompt and system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt.strip()})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
        }

        if is_json:
            payload["response_format"] = {"type": "json_object"}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(endpoint, json=payload, headers=headers)

                # Nếu server báo lỗi 400 do không hỗ trợ response_format, thử lại không kèm response_format
                if is_json and response.status_code == 400 and "response_format" in response.text:
                    logger.warning("LM Studio server không hỗ trợ 'response_format'. Thử lại mà không kèm format flag.")
                    payload.pop("response_format", None)
                    response = client.post(endpoint, json=payload, headers=headers)

                if response.status_code != 200:
                    raise LLMProviderError(
                        f"LM Studio trả về mã lỗi HTTP {response.status_code}: {response.text}"
                    )

                data = response.json()
                choices = data.get("choices", [])
                if not choices:
                    raise LLMEmptyResponseError("LM Studio trả về phản hồi không có trường 'choices'.")

                message = choices[0].get("message", {})
                content = message.get("content", "")

                if not content or not content.strip():
                    raise LLMEmptyResponseError("Phản hồi văn bản từ LM Studio rỗng.")

                return content.strip()

        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            logger.error(f"Lỗi kết nối tới LM Studio tại {self.base_url}: {e}")
            raise LLMConnectionError(
                f"Không thể kết nối đến máy chủ LM Studio tại '{self.base_url}'. "
                f"Vui lòng đảm bảo phần mềm LM Studio đang mở và đã bật 'Local Server' (cổng 1234). "
                f"Chi tiết: {e}"
            ) from e

        except httpx.ReadTimeout as e:
            logger.error(f"Timeout khi chờ phản hồi từ LM Studio ({self.timeout}s): {e}")
            raise LLMConnectionError(
                f"Hết thời gian chờ phản hồi ({self.timeout}s) từ máy chủ LM Studio tại '{self.base_url}'. "
                f"Mô hình cục bộ có thể đang quá tải hoặc cấu hình timeout quá ngắn."
            ) from e

        except httpx.HTTPError as e:
            logger.error(f"Lỗi giao thức HTTP khi gọi LM Studio: {e}")
            raise LLMProviderError(f"Lỗi HTTP khi gọi LM Studio: {e}") from e
