"""
Custom exception classes with error codes
"""


class DlzoomError(Exception):
    """Base exception for dlzoom errors"""

    def __init__(self, message: str, code: str, details: str = ""):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for JSON output"""
        return {"code": self.code, "message": self.message, "details": self.details}


class AuthenticationError(DlzoomError):
    """Authentication failed"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, "AUTH_FAILED", details)


class MeetingNotFoundError(DlzoomError):
    """Meeting ID does not exist"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, "MEETING_NOT_FOUND", details)


class RecordingNotFoundError(DlzoomError):
    """No recording available"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, "RECORDING_NOT_FOUND", details)


class RecordingNotProcessedError(DlzoomError):
    """Recording exists but not processed"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, "RECORDING_NOT_PROCESSED", details)


class NoAudioAvailableError(DlzoomError):
    """No audio file available"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, "NO_AUDIO_AVAILABLE", details)


class DownloadFailedError(DlzoomError):
    """File download failed"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, "DOWNLOAD_FAILED", details)


class FFmpegNotFoundError(DlzoomError):
    """ffmpeg binary not found"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, "FFMPEG_NOT_FOUND", details)


class PermissionDeniedError(DlzoomError):
    """Insufficient permissions"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, "PERMISSION_DENIED", details)


class InvalidMeetingIDError(DlzoomError):
    """Meeting ID format invalid"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, "INVALID_MEETING_ID", details)


class RateLimitedError(DlzoomError):
    """API rate limit exceeded"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, "RATE_LIMITED", details)


class OperationTimeoutError(DlzoomError):
    """Operation timed out"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, "TIMEOUT", details)


class DiskSpaceError(DlzoomError):
    """Insufficient disk space"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, "DISK_SPACE_ERROR", details)


class AudioExtractionError(DlzoomError):
    """FFmpeg failed to extract audio from video"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, "AUDIO_EXTRACTION_FAILED", details)


class FileWriteError(DlzoomError):
    """Cannot write to output directory (permission or I/O error)"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, "FILE_WRITE_ERROR", details)


class NetworkError(DlzoomError):
    """Network connection issue"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, "NETWORK_ERROR", details)


class InvalidScopeError(DlzoomError):
    """OAuth scopes insufficient or incorrect"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, "INVALID_SCOPE", details)


class ConfigError(DlzoomError):
    """Missing or invalid configuration"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, "INVALID_CONFIG", details)


class InvalidRecordingIDError(DlzoomError):
    """Specified recording UUID not found"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, "INVALID_RECORDING_ID", details)


class PasswordProtectedError(DlzoomError):
    """Recording download failed - password-protected recording issue"""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message, "PASSWORD_PROTECTED_ERROR", details)
