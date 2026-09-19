import json
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator


class PlanCreatorConfig(BaseModel):
    """Mô hình cấu hình cho Plan Creator Engine."""

    model_name: str = Field(
        default="gemini-2.5-flash",
        description="Tên mô hình Gemini AI sử dụng để lên kịch bản video"
    )
    api_keys: List[str] = Field(
        ...,
        description="Danh sách các API keys khả dụng để xoay vòng"
    )
    system_prompt: str = Field(
        ...,
        description="Chỉ dẫn hệ thống (System Prompt) cho AI về vai trò biên kịch, tone giọng, đối tượng mục tiêu"
    )
    json_structure: Union[Dict[str, Any], str] = Field(
        ...,
        description="Cấu trúc JSON đầu ra mong muốn cho kịch bản (dưới dạng Dict hoặc JSON string/schema)"
    )
    user_prompt_template: Optional[str] = Field(
        default=None,
        description="Mẫu nội dung yêu cầu gửi cho AI. Nếu để None sẽ dùng DEFAULT_USER_PROMPT_TEMPLATE từ constants."
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Nhiệt độ sáng tạo của AI (mặc định 0.7 để tạo các kịch bản phong phú, hấp dẫn)"
    )
    sound_effects_dir: Optional[Any] = Field(
        default=None,
        description="Thư mục chứa hiệu ứng âm thanh (mặc định: EFFECT_SOUNDS_DIR)"
    )

    @field_validator("api_keys")
    @classmethod
    def validate_api_keys(cls, v: List[str]) -> List[str]:
        cleaned = [k.strip() for k in v if isinstance(k, str) and k.strip()]
        if not cleaned:
            raise ValueError("Danh sách api_keys không được để trống!")
        return cleaned

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

    @field_validator("user_prompt_template")
    @classmethod
    def validate_user_prompt_template(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                return None
            return stripped
        return None

    def get_user_prompt_template(self) -> str:
        """Lấy user prompt template đã cấu hình hoặc lấy mặc định từ constants."""
        if self.user_prompt_template and self.user_prompt_template.strip():
            return self.user_prompt_template.strip()
        from app.services.plan_creator.prompts import DEFAULT_USER_PROMPT_TEMPLATE
        return DEFAULT_USER_PROMPT_TEMPLATE


    def get_json_structure_str(self) -> str:
        """Chuyển đổi json_structure thành chuỗi JSON có định dạng đẹp mắt."""
        if isinstance(self.json_structure, dict):
            return json.dumps(self.json_structure, ensure_ascii=False, indent=2)
        return str(self.json_structure)
