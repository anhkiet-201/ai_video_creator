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

logger = logging.getLogger(__name__)


class ContentExtractorEngine:
    """Engine chuyên trích xuất thông tin có cấu trúc từ tin tuyển dụng bằng Gemini AI.

    Đặc điểm kiến trúc:
    - Nhận danh sách api_keys và tự động xoay vòng key khi gặp lỗi quota (429).
    - Nhận system_prompt do caller cấu hình, không ép buộc prompt mặc định.
    - Nhận cấu trúc JSON (json_structure) linh hoạt theo yêu cầu nghiệp vụ.
    """

    def __init__(
        self,
        config: Optional[ContentExtractorConfig] = None,
        key_rotator: Optional[KeyRotator] = None,
    ):
        self.config = config
        if key_rotator is not None:
            self.key_rotator = key_rotator
        elif config and config.api_keys:
            self.key_rotator = KeyRotator(config.api_keys)
        else:
            self.key_rotator = KeyRotator([])

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
        if override_config and override_config.api_keys:
            self.key_rotator.set_keys(override_config.api_keys)

        if not self.key_rotator.has_available_keys():
            raise NoValidApiKeyError(
                "Không tìm thấy Gemini API Key khả dụng hoặc danh sách api_keys rỗng. "
                "Vui lòng cung cấp ít nhất một API Key hợp lệ."
            )

        # 4. Xây dựng prompt & gọi Gemini AI có cơ chế xoay vòng key
        prompt_content = self._build_prompt_content(active_config, content.strip())
        return self._execute_with_rotation(active_config, prompt_content)

    def _build_prompt_content(self, config: ContentExtractorConfig, content: str) -> str:
        """Xây dựng phần user contents gửi cho Gemini AI kèm cấu trúc JSON yêu cầu."""
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
        """Thực hiện gọi API qua Google GenAI SDK với cơ chế xoay vòng key và bắt lỗi."""
        last_error_reason: str = ""

        while self.key_rotator.has_available_keys():
            current_key = self.key_rotator.get_current_key()
            if not current_key:
                break

            masked_key = f"...{current_key[-6:]}" if len(current_key) >= 6 else current_key

            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=current_key)
                response = client.models.generate_content(
                    model=config.model_name,
                    contents=prompt_content,
                    config=types.GenerateContentConfig(
                        system_instruction=config.system_prompt,
                        response_mime_type="application/json",
                        temperature=config.temperature,
                    ),
                )

                if response and response.text:
                    return self._clean_and_parse_json(response.text)

                last_error_reason = "Phản hồi từ Gemini API rỗng (response.text is empty)."
                logger.warning(f"Phản hồi rỗng khi gọi model {config.model_name} với key {masked_key}")

            except JSONParsingError:
                # Lỗi định dạng JSON do AI sinh sai cú pháp
                raise
            except Exception as e:
                err_msg = str(e)
                last_error_reason = err_msg
                logger.warning(f"Lỗi khi bóc tách nội dung với key {masked_key}: {err_msg}")
                self.key_rotator.mark_key_failed(current_key, reason=err_msg)

        raise NoValidApiKeyError(
            f"Không thể bóc tách nội dung tin tuyển dụng bằng AI: Toàn bộ API Key trong danh sách đã bị lỗi quota hoặc hết hạn mức. "
            f"Lỗi gần nhất: {last_error_reason}"
        )

    def _clean_and_parse_json(self, raw_text: str) -> Dict[str, Any]:
        """Làm sạch văn bản markdown và phân tích cú pháp chuỗi JSON an toàn."""
        text = raw_text.strip()

        # Loại bỏ markdown code fences nếu AI vô tình sinh ra (```json ... ```)
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # Tìm kiếm khối JSON hợp lệ nằm giữa cặp ngoặc nhọn ngoài cùng
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

        try:
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise JSONParsingError(
                    f"Dữ liệu JSON trả về phải là một Object (dict), nhận được: {type(parsed).__name__}"
                )
            return parsed
        except (json.JSONDecodeError, JSONParsingError) as e:
            logger.error(f"Không thể parse JSON từ AI output: {text[:200]}... Lỗi: {e}")
            raise JSONParsingError(f"Phản hồi từ AI không đúng định dạng JSON hợp lệ: {e}") from e
