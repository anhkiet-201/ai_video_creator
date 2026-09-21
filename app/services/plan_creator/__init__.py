"""Plan Creator Service - Tự động lên kịch bản video từ dữ liệu JSON bằng Gemini AI."""

from app.services.plan_creator.engine import PlanCreatorEngine, sanitize_script_tags
from app.services.plan_creator.exceptions import (
    EmptyContentError,
    InvalidNumScriptsError,
    JSONParsingError,
    MissingJsonStructureError,
    MissingSystemPromptError,
    NoValidApiKeyError,
    PlanCreatorError,
)
from app.services.plan_creator.constants import (
    FFMPEG_TRANSITIONS,
    VALID_EMOTION_TAGS,
)
from app.services.plan_creator.models import PlanCreatorConfig
from app.services.plan_creator.prompts import (
    DEFAULT_JSON_STRUCTURE,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_USER_PROMPT_TEMPLATE,
)
from app.services.plan_creator.sensitive_rules import (
    SENSITIVE_REPLACEMENTS,
    clean_sensitive_text,
)


__all__ = [
    "PlanCreatorEngine",
    "PlanCreatorConfig",
    "sanitize_script_tags",
    "clean_sensitive_text",
    "SENSITIVE_REPLACEMENTS",
    "VALID_EMOTION_TAGS",
    "DEFAULT_SYSTEM_PROMPT",
    "DEFAULT_USER_PROMPT_TEMPLATE",
    "DEFAULT_JSON_STRUCTURE",
    "FFMPEG_TRANSITIONS",

    "PlanCreatorError",
    "EmptyContentError",
    "InvalidNumScriptsError",
    "MissingSystemPromptError",
    "MissingJsonStructureError",
    "NoValidApiKeyError",
    "JSONParsingError",
]
