import json
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


class ContentExtractorConfig(BaseModel):
    """Mô hình cấu hình cho Content Extractor Engine."""

    provider: str = Field(
        default="gemini",
        description="Loại LLM Provider sử dụng ('gemini' hoặc 'lm_studio')"
    )
    base_url: Optional[str] = Field(
        default=None,
        description="Địa chỉ API cho LM Studio (mặc định: http://localhost:1234/v1)"
    )
    model_name: str = Field(
        default="gemini-2.5-flash",
        description="Tên mô hình LLM sử dụng để bóc tách nội dung"
    )
    api_keys: List[str] = Field(
        default_factory=list,
        description="Danh sách các API keys khả dụng (bắt buộc khi dùng provider='gemini')"
    )
    system_prompt: str = Field(
        ...,
        description="Chỉ dẫn hệ thống (System Prompt) cho AI, do người dùng/caller cung cấp"
    )
    json_structure: Union[Dict[str, Any], str] = Field(
        ...,
        description="Cấu trúc JSON đầu ra mong muốn (dưới dạng Dict hoặc JSON string/schema)"
    )
    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Nhiệt độ sáng tạo của AI (mặc định 0.2 để trích xuất chính xác)"
    )

    @field_validator("api_keys", mode="before")
    @classmethod
    def validate_api_keys_raw(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v.strip()] if v.strip() else []
        if isinstance(v, (list, tuple, set)):
            return [str(k).strip() for k in v if str(k).strip()]
        return v

    @model_validator(mode="after")
    def validate_provider_keys(self) -> "ContentExtractorConfig":
        if (self.provider or "").lower().strip() == "gemini" and not self.api_keys:
            raise ValueError("Danh sách api_keys không được để trống!")
        return self

    @field_validator("system_prompt")
    @classmethod
    def validate_system_prompt(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("system_prompt không được để trống!")
        return v.strip()

    @field_validator("json_structure")
    @classmethod
    def validate_json_structure(cls, v: Union[Dict[str, Any], str]) -> Union[Dict[str, Any], str]:
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                raise ValueError("json_structure không được để trống!")
            return stripped
        if isinstance(v, dict):
            if not v:
                raise ValueError("json_structure dict không được rỗng!")
            return v
        raise ValueError("json_structure phải là dict hoặc chuỗi định dạng JSON!")

    def get_json_structure_str(self) -> str:
        """Chuyển đổi json_structure thành chuỗi JSON có định dạng đẹp mắt."""
        if isinstance(self.json_structure, dict):
            return json.dumps(self.json_structure, ensure_ascii=False, indent=2)
        return str(self.json_structure)
