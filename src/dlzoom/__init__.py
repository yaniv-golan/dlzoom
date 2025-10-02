"""
dlzoom - Download Zoom cloud recordings via API
"""

__version__ = "0.1.0"
__author__ = "dlzoom"
__description__ = "CLI tool to download Zoom cloud recordings and extract audio for transcription"

from .audio_extractor import AudioExtractionError, AudioExtractor
from .config import Config, ConfigError
from .downloader import Downloader, DownloadError
from .logger import setup_logging
from .output import OutputFormatter
from .recorder_selector import RecordingSelector
from .zoom_client import ZoomAPIError, ZoomClient

__all__ = [
    "ZoomClient",
    "ZoomAPIError",
    "Config",
    "ConfigError",
    "RecordingSelector",
    "AudioExtractor",
    "AudioExtractionError",
    "Downloader",
    "DownloadError",
    "OutputFormatter",
    "setup_logging",
    "__version__",
]
