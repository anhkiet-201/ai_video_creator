"""Factory tạo instance BaseLLMProvider dựa trên loại provider cấu hình."""

import logging
from typing import Any, List, Optional, Union

from app.services.key_rotator import KeyRotator
from app.services.llm.base import BaseLLMProvider
from app.services.llm.gemini_provider import GeminiLLMProvider
from app.services.llm.lm_studio_provider import DEFAULT_LM_STUDIO_URL, LMStudioLLMProvider

logger = logging.getLogger(__name__)


def create_llm_provider(
    provider_type: str = "gemini",
    model_name: Optional[str] = None,
    api_keys: Optional[Union[List[str], str]] = None,
    base_url: Optional[str] = None,
    key_rotator: Optional[KeyRotator] = None,
    timeout: float = 90.0,
    **kwargs: Any,
) -> BaseLLMProvider:
    """Khởi tạo LLM Provider thích hợp dựa trên provider_type.

    Args:
        provider_type: "gemini" hoặc "lm_studio" (hỗ trợ alias: "lmstudio", "local", "google").
        model_name: Tên mô hình (ví dụ: "gemini-2.5-flash" hoặc "qwen2.5-7b-instruct").
        api_keys: Danh sách API Keys (dành cho Gemini).
        base_url: Địa chỉ máy chủ (dành cho LM Studio, mặc định: http://localhost:1234/v1).
        key_rotator: Instance KeyRotator có sẵn (nếu muốn tái sử dụng).
        timeout: Thời gian timeout (giây).
        **kwargs: Tham số bổ sung truyền cho provider.

    Returns:
        Instance kế thừa BaseLLMProvider.
    """
    normalized_type = (provider_type or "gemini").lower().strip()

    if normalized_type in {"gemini", "google"}:
        target_model = model_name or "gemini-2.5-flash"
        return GeminiLLMProvider(
            api_keys=api_keys,
            model_name=target_model,
            key_rotator=key_rotator,
            **kwargs,
        )

    if normalized_type in {"lm_studio", "lmstudio", "local"}:
        target_url = base_url or DEFAULT_LM_STUDIO_URL
        target_model = model_name or "local-model"
        return LMStudioLLMProvider(
            base_url=target_url,
            model_name=target_model,
            timeout=timeout,
            **kwargs,
        )

    raise ValueError(
        f"Không hỗ trợ LLM Provider: '{provider_type}'. "
        f"Các provider được hỗ trợ bao gồm: 'gemini', 'lm_studio'."
    )
