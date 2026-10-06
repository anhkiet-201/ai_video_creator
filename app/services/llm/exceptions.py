"""Các ngoại lệ chuẩn hóa cho tầng LLM Provider."""


class LLMProviderError(Exception):
    """Ngoại lệ cơ sở cho toàn bộ các lỗi liên quan đến LLM Provider."""
    pass


class LLMConnectionError(LLMProviderError):
    """Lỗi khi không thể kết nối tới máy chủ LLM (ví dụ LM Studio server chưa bật, timeout)."""
    pass


class LLMQuotaExhaustedError(LLMProviderError):
    """Lỗi khi toàn bộ API Keys đã hết hạn mức hoặc bị lỗi quota (429 Too Many Requests)."""
    pass


class LLMResponseParsingError(LLMProviderError):
    """Lỗi khi phản hồi từ mô hình LLM không thể phân tích cú pháp thành JSON hợp lệ."""
    pass


class LLMEmptyResponseError(LLMProviderError):
    """Lỗi khi phản hồi trả về từ mô hình LLM rỗng."""
    pass
