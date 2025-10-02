"""
Unit tests for recorder selector module
"""

import pytest

from dlzoom.recorder_selector import RecordingSelector


@pytest.fixture
def selector():
    return RecordingSelector()


@pytest.fixture
def sample_recording_files():
    return [
        {"file_type": "audio_only", "file_extension": "M4A"},
        {"file_type": "MP4", "file_extension": "MP4"},
        {"file_type": "chat_file", "file_extension": "TXT"},
    ]


@pytest.fixture
def sample_instances():
    return [
        {"uuid": "abc123", "start_time": "2025-01-01T10:00:00Z"},
        {"uuid": "def456", "start_time": "2025-01-02T10:00:00Z"},
        {"uuid": "ghi789", "start_time": "2025-01-03T10:00:00Z"},
    ]


def test_select_best_audio_m4a_audio_only(selector, sample_recording_files):
    """Test that audio_only M4A is prioritized"""
    result = selector.select_best_audio(sample_recording_files)
    assert result["file_type"] == "audio_only"
    assert result["file_extension"] == "M4A"


def test_select_best_audio_m4a_fallback(selector):
    """Test that other M4A files are selected if no audio_only"""
    files = [
        {"file_type": "MP4", "file_extension": "MP4"},
        {"file_type": "recording", "file_extension": "M4A"},
    ]
    result = selector.select_best_audio(files)
    assert result["file_extension"] == "M4A"


def test_select_best_audio_mp4_fallback(selector):
    """Test that MP4 is used as last resort"""
    files = [
        {"file_type": "MP4", "file_extension": "MP4"},
        {"file_type": "chat_file", "file_extension": "TXT"},
    ]
    result = selector.select_best_audio(files)
    assert result["file_extension"] == "MP4"


def test_select_best_audio_none(selector):
    """Test that None is returned when no suitable files"""
    files = [
        {"file_type": "chat_file", "file_extension": "TXT"},
    ]
    result = selector.select_best_audio(files)
    assert result is None


def test_select_most_recent_instance(selector, sample_instances):
    """Test that most recent instance is selected"""
    result = selector.select_most_recent_instance(sample_instances)
    assert result["uuid"] == "ghi789"  # 2025-01-03


def test_select_most_recent_instance_empty(selector):
    """Test that None is returned for empty list"""
    result = selector.select_most_recent_instance([])
    assert result is None


def test_filter_by_uuid(selector, sample_instances):
    """Test filtering by UUID"""
    result = selector.filter_by_uuid(sample_instances, "def456")
    assert result["uuid"] == "def456"


def test_filter_by_uuid_not_found(selector, sample_instances):
    """Test that None is returned when UUID not found"""
    result = selector.filter_by_uuid(sample_instances, "notfound")
    assert result is None


def test_detect_multiple_instances(selector):
    """Test detection of multiple instances"""
    recordings = {"meetings": [{"id": 1}, {"id": 2}]}
    assert selector.detect_multiple_instances(recordings) is True

    recordings = {"meetings": [{"id": 1}]}
    assert selector.detect_multiple_instances(recordings) is False

    recordings = {"meetings": []}
    assert selector.detect_multiple_instances(recordings) is False
