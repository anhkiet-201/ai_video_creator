class ContentExtractorError(Exception):
    """Lớp ngoại lệ cơ sở cho toàn bộ lỗi trong Content Extractor Engine."""
    pass


class EmptyContentError(ContentExtractorError):
    """Ném ra khi nội dung tin tuyển dụng đầu vào bị trống hoặc chỉ chứa khoảng trắng."""
    pass


class MissingSystemPromptError(ContentExtractorError):
    """Ném ra khi system_prompt bị thiếu hoặc rỗng trong cấu hình."""
    pass


class MissingJsonStructureError(ContentExtractorError):
    """Ném ra khi cấu trúc JSON (json_structure) bị thiếu hoặc rỗng."""
    pass


class NoValidApiKeyError(ContentExtractorError):
    """Ném ra khi danh sách api_keys rỗng hoặc toàn bộ key đã bị lỗi quota / hết hạn mức."""
    pass


class JSONParsingError(ContentExtractorError):
    """Ném ra khi phản hồi từ AI không thể phân tích cú pháp thành JSON hợp lệ."""
    pass
