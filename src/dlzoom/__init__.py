"""
dlzoom - Download Zoom cloud recordings via API
"""

__version__ = "0.1.0"
__author__ = "dlzoom"
__description__ = "CLI tool to download Zoom cloud recordings and extract audio for transcription"

from .zoom_client import ZoomClient, ZoomAPIError
from .config import Config, ConfigError
from .recorder_selector import RecordingSelector
from .audio_extractor import AudioExtractor, AudioExtractionError
from .downloader import Downloader, DownloadError
from .output import OutputFormatter
from .logger import setup_logging

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
