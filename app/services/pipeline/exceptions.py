"""Custom exceptions for the 6-step Video Creation Pipeline."""


class PipelineError(Exception):
    """Ngoại lệ cơ sở cho toàn bộ Pipeline."""
    pass


class StepValidationError(PipelineError):
    """Lỗi thẩm định dữ liệu đầu vào ở Bước 1."""
    pass


class StepContentExtractionError(PipelineError):
    """Lỗi bóc tách nội dung ở Bước 2."""
    pass


class StepPlanCreationError(PipelineError):
    """Lỗi tạo kịch bản thô ở Bước 3."""
    pass


class StepAssetRenderError(PipelineError):
    """Lỗi render overlay hoặc audio ở Bước 4."""
    pass


class StepDetailedPlanError(PipelineError):
    """Lỗi tổng hợp kịch bản chi tiết ở Bước 5."""
    pass


class StepVideoRenderError(PipelineError):
    """Lỗi dựng video thành phẩm ở Bước 6."""
    pass
