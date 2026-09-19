"""Các ngoại lệ tùy chỉnh cho PlanCreatorEngine."""


class PlanCreatorError(Exception):
    """Ngoại lệ cơ sở cho toàn bộ lỗi trong service plan_creator."""
    pass


class EmptyContentError(PlanCreatorError):
    """Ném ra khi nội dung JSON đầu vào rỗng hoặc không hợp lệ."""
    pass


class InvalidNumScriptsError(PlanCreatorError):
    """Ném ra khi số lượng kịch bản num_scripts không hợp lệ (nhỏ hơn hoặc bằng 0)."""
    pass


class MissingSystemPromptError(PlanCreatorError):
    """Ném ra khi thiếu system_prompt trong cấu hình."""
    pass


class MissingJsonStructureError(PlanCreatorError):
    """Ném ra khi thiếu json_structure trong cấu hình."""
    pass


class NoValidApiKeyError(PlanCreatorError):
    """Ném ra khi không tìm thấy API Key hợp lệ hoặc toàn bộ API Keys đã bị lỗi/hạn mức."""
    pass


class JSONParsingError(PlanCreatorError):
    """Ném ra khi phản hồi từ AI không thể phân tích cú pháp thành JSON hợp lệ."""
    pass
