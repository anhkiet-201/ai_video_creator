import json
import logging
import re
from typing import Any, Dict, Optional

from app.services.content_extractor.exceptions import (
    ContentExtractorError,
    EmptyContentError,
    JSONParsingError,
    MissingJsonStructureError,
    MissingSystemPromptError,
    NoValidApiKeyError,
)
from app.services.content_extractor.models import ContentExtractorConfig
from app.services.key_rotator import KeyRotator
from app.services.llm import (
    BaseLLMProvider,
    LLMProviderError,
    LLMQuotaExhaustedError,
    LLMResponseParsingError,
    create_llm_provider,
)

logger = logging.getLogger(__name__)


class ContentExtractorEngine:
    """Engine chuyên trích xuất thông tin có cấu trúc từ tin tuyển dụng bằng LLM Provider.

    Đặc điểm kiến trúc:
    - Nhận danh sách api_keys và tự động xoay vòng key khi gặp lỗi quota (429) với Gemini.
    - Hỗ trợ LM Studio và các mô hình cục bộ khác qua interface BaseLLMProvider.
    - Nhận system_prompt do caller cấu hình, không ép buộc prompt mặc định.
    - Nhận cấu trúc JSON (json_structure) linh hoạt theo yêu cầu nghiệp vụ.
    """

    def __init__(
        self,
        config: Optional[ContentExtractorConfig] = None,
        key_rotator: Optional[KeyRotator] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
    ):
        self.config = config
        self._custom_llm_provider = llm_provider
        self.llm_provider = llm_provider

        if key_rotator is not None:
            self.key_rotator = key_rotator
        elif config and config.api_keys:
            self.key_rotator = KeyRotator(config.api_keys)
        else:
            self.key_rotator = KeyRotator([])

        if self.llm_provider is None:
            provider_type = config.provider if config else "gemini"
            model_name = config.model_name if config else "gemini-2.5-flash"
            base_url = config.base_url if config else None
            self.llm_provider = create_llm_provider(
                provider_type=provider_type,
                model_name=model_name,
                api_keys=config.api_keys if config else None,
                base_url=base_url,
                key_rotator=self.key_rotator,
            )

    def _resolve_llm_provider(
        self,
        active_config: ContentExtractorConfig,
        override_config: Optional[ContentExtractorConfig] = None,
    ) -> BaseLLMProvider:
        """Lấy provider thích hợp dựa trên active_config và self.llm_provider."""
        if override_config and override_config.api_keys and hasattr(self, "key_rotator"):
            if override_config.api_keys != self.key_rotator._keys:
                self.key_rotator.set_keys(override_config.api_keys)

        # 1. Nếu caller truyền custom provider (ví dụ mock trong unit tests), ưu tiên sử dụng
        if self._custom_llm_provider is not None:
            if hasattr(self._custom_llm_provider, "key_rotator"):
                self._custom_llm_provider.key_rotator = self.key_rotator
            if active_config.model_name:
                self._custom_llm_provider.model_name = active_config.model_name
            return self._custom_llm_provider

        # 2. Kiểm tra nếu provider hiện tại đã đúng loại provider và cấu hình tương ứng
        target_provider = (active_config.provider or "gemini").lower().strip()
        current_provider = getattr(self.llm_provider, "provider_name", None)

        if self.llm_provider is not None and current_provider == target_provider:
            if target_provider == "lm_studio":
                curr_base = getattr(self.llm_provider, "base_url", None)
                target_base = active_config.base_url
                if target_base and curr_base and target_base.rstrip("/").rstrip("/v1") != curr_base.rstrip("/").rstrip("/v1"):
                    pass
                else:
                    if active_config.model_name:
                        self.llm_provider.model_name = active_config.model_name
                    return self.llm_provider
            else:
                if hasattr(self.llm_provider, "key_rotator"):
                    self.llm_provider.key_rotator = self.key_rotator
                if active_config.model_name:
                    self.llm_provider.model_name = active_config.model_name
                return self.llm_provider

        # 3. Tạo mới provider theo đúng active_config
        new_provider = create_llm_provider(
            provider_type=target_provider,
            model_name=active_config.model_name,
            api_keys=active_config.api_keys,
            base_url=active_config.base_url,
            key_rotator=self.key_rotator,
        )
        self.llm_provider = new_provider
        return new_provider

    def extract(
        self,
        content: str,
        override_config: Optional[ContentExtractorConfig] = None,
    ) -> Dict[str, Any]:
        """Bóc tách thông tin từ văn bản tin tuyển dụng sang định dạng JSON.

        Args:
            content: Văn bản thô của tin tuyển dụng cần bóc tách.
            override_config: Cấu hình ghi đè nếu muốn thay đổi config lúc gọi hàm.

        Returns:
            Dict[str, Any]: Dữ liệu đã trích xuất theo đúng cấu trúc JSON yêu cầu.

        Raises:
            EmptyContentError: Nếu nội dung tuyển dụng rỗng.
            MissingSystemPromptError: Nếu thiếu system_prompt.
            MissingJsonStructureError: Nếu thiếu cấu trúc json_structure.
            NoValidApiKeyError: Nếu không có API key hợp lệ hoặc toàn bộ key hết hạn mức.
            JSONParsingError: Nếu AI trả về kết quả không parse được sang JSON.
            ContentExtractorError: Các lỗi hệ thống khác.
        """
        # 1. Guard Clause: Kiểm tra tính hợp lệ của content
        if not content or not content.strip():
            raise EmptyContentError("Nội dung tin tuyển dụng không được để trống!")

        # 2. Xác định config áp dụng
        active_config = override_config or self.config
        if not active_config:
            raise ContentExtractorError(
                "Chưa cung cấp cấu hình ContentExtractorConfig cho ContentExtractorEngine!"
            )

        if not active_config.system_prompt or not active_config.system_prompt.strip():
            raise MissingSystemPromptError("system_prompt không được để trống trong cấu hình!")

        if not active_config.json_structure:
            raise MissingJsonStructureError("json_structure không được để trống trong cấu hình!")

        # 3. Đồng bộ danh sách API Keys vào KeyRotator nếu có override
        provider = self._resolve_llm_provider(active_config, override_config=override_config)

        if (active_config.provider or "").lower().strip() == "gemini":
            rotator = getattr(provider, "key_rotator", self.key_rotator)
            if not rotator or not rotator.has_available_keys():
                raise NoValidApiKeyError(
                    "Không tìm thấy Gemini API Key khả dụng hoặc danh sách api_keys rỗng. "
                    "Vui lòng cung cấp ít nhất một API Key hợp lệ."
                )

        # 4. Xây dựng prompt & gọi LLM Provider
        prompt_content = self._build_prompt_content(active_config, content.strip())
        return self._execute_with_rotation(active_config, prompt_content)

    def _build_prompt_content(self, config: ContentExtractorConfig, content: str) -> str:
        """Xây dựng phần user contents gửi cho AI kèm cấu trúc JSON yêu cầu."""
        schema_repr = config.get_json_structure_str()
        return (
            f"NỘI DUNG TIN TUYỂN DỤNG CẦN PHÂN TÍCH VÀ BÓC TÁCH:\n"
            f'"""\n{content}\n"""\n\n'
            f"HÃY BÓC TÁCH THÔNG TIN VÀ TRẢ VỀ CHÍNH XÁC THEO CẤU TRÚC JSON DƯỚI ĐÂY:\n"
            f"{schema_repr}\n\n"
            f"Quy tắc quan trọng:\n"
            f"1. Chỉ trả về đúng một khối JSON hợp lệ, không kèm văn bản giải thích hay markdown code fence.\n"
            f"2. Bám sát dữ liệu trong tin tuyển dụng, không bịa đặt thông tin không có cơ sở."
        )

    def _execute_with_rotation(
        self,
        config: ContentExtractorConfig,
        prompt_content: str,
    ) -> Dict[str, Any]:
        """Thực hiện gọi API qua LLM Provider với cơ chế xoay vòng key và bắt lỗi chuẩn hóa."""
        provider = self._resolve_llm_provider(config)

        if (config.provider or "").lower().strip() == "gemini":
            rotator = getattr(provider, "key_rotator", self.key_rotator)
            if not rotator or not rotator.has_available_keys():
                raise NoValidApiKeyError(
                    "Không tìm thấy Gemini API Key khả dụng hoặc danh sách api_keys rỗng. "
                    "Vui lòng cung cấp ít nhất một API Key hợp lệ."
                )

        try:
            return provider.generate_json(
                prompt=prompt_content,
                system_prompt=config.system_prompt,
                temperature=config.temperature,
            )
        except LLMQuotaExhaustedError as e:
            raise NoValidApiKeyError(str(e)) from e
        except LLMResponseParsingError as e:
            raise JSONParsingError(str(e)) from e
        except LLMProviderError as e:
            raise ContentExtractorError(str(e)) from e

    def _clean_and_parse_json(self, raw_text: str) -> Dict[str, Any]:
        """Làm sạch văn bản markdown và phân tích cú pháp chuỗi JSON an toàn."""
        try:
            if self.llm_provider:
                return self.llm_provider.clean_and_parse_json(raw_text)
            from app.services.llm.base import BaseLLMProvider
            return BaseLLMProvider.clean_and_parse_json(self.llm_provider, raw_text)
        except (LLMResponseParsingError, Exception) as e:
            if isinstance(e, JSONParsingError):
                raise
            raise JSONParsingError(f"Phản hồi từ AI không đúng định dạng JSON hợp lệ: {e}") from e
