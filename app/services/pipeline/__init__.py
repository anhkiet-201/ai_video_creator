"""Video Creation Pipeline Package.

Cung cấp orchestrator điều phối luồng 6 bước:
1. Nhận Content & Video Source Path
2. Trích xuất thông tin
3. Lên kịch bản thô
4. Render overlay, audio
5. Lên kịch bản chi tiết (có overlay path, audio path)
6. Render video
"""

from app.services.pipeline.coordinator import VideoCreationPipeline
from app.services.pipeline.exceptions import (
    PipelineError,
    StepAssetRenderError,
    StepContentExtractionError,
    StepDetailedPlanError,
    StepPlanCreationError,
    StepValidationError,
    StepVideoRenderError,
)
from app.services.pipeline.models import (
    PipelineInput,
    PipelineResult,
    ProgressCallback,
    RoughScene,
    RoughScript,
)

__all__ = [
    "VideoCreationPipeline",
    "PipelineInput",
    "PipelineResult",
    "RoughScript",
    "RoughScene",
    "ProgressCallback",
    "PipelineError",
    "StepValidationError",
    "StepContentExtractionError",
    "StepPlanCreationError",
    "StepAssetRenderError",
    "StepDetailedPlanError",
    "StepVideoRenderError",
]
