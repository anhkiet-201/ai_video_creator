"""Custom exceptions for Video Render Engine."""


class VideoRenderEngineError(Exception):
    """Base exception for all video render engine errors."""

    pass


class RendererNotProvidedError(VideoRenderEngineError):
    """Raised when no custom BaseVideoRenderer implementation is injected into the engine."""

    pass


class SourceFolderNotFoundError(VideoRenderEngineError):
    """Raised when the specified video source folder does not exist or is not a directory."""

    pass


class InvalidPlanError(VideoRenderEngineError):
    """Raised when the provided video plan is invalid or empty."""

    pass


class RenderExecutionError(VideoRenderEngineError):
    """Raised when an error occurs during the execution of a video render plan."""

    pass
