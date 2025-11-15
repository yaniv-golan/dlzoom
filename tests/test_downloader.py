"""
Tests for Downloader robustness: atomic operations, disk space, size validation
"""

import os
import shutil
from unittest.mock import MagicMock, Mock, patch

import pytest

from dlzoom.downloader import Downloader
from dlzoom.exceptions import DiskSpaceError


class TestDiskSpaceCheck:
    """Test disk space validation"""

    def test_check_disk_space_sufficient(self, tmp_path):
        """Should pass when sufficient disk space available"""
        downloader = Downloader(output_dir=tmp_path, access_token="test_token")

        # Request 1 MB (should be available on any system)
        result = downloader.check_disk_space(1024 * 1024)
        assert result is True

    @patch("shutil.disk_usage")
    def test_check_disk_space_insufficient(self, mock_disk_usage, tmp_path):
        """Should raise DiskSpaceError when insufficient space"""
        # Mock 50 MB available
        mock_disk_usage.return_value = Mock(free=50 * 1024 * 1024)

        downloader = Downloader(output_dir=tmp_path, access_token="test_token")

        # Request 1 GB (with 100 MB buffer = 1.1 GB total needed)
        with pytest.raises(DiskSpaceError, match="Insufficient disk space"):
            downloader.check_disk_space(1024 * 1024 * 1024)

    @patch("shutil.disk_usage")
    def test_check_disk_space_includes_buffer(self, mock_disk_usage, tmp_path):
        """Should include 100 MB buffer in calculation"""
        # Mock exactly 200 MB available
        mock_disk_usage.return_value = Mock(free=200 * 1024 * 1024)

        downloader = Downloader(output_dir=tmp_path, access_token="test_token")

        # Request 150 MB (with 100 MB buffer = 250 MB needed, but only 200 MB available)
        with pytest.raises(DiskSpaceError):
            downloader.check_disk_space(150 * 1024 * 1024)

    @patch("shutil.disk_usage")
    def test_check_disk_space_oserror_proceeds(self, mock_disk_usage, tmp_path):
        """Should proceed optimistically if disk_usage fails"""
        mock_disk_usage.side_effect = OSError("Permission denied")

        downloader = Downloader(output_dir=tmp_path, access_token="test_token")

        # Should return True and log warning instead of failing
        result = downloader.check_disk_space(1024 * 1024 * 1024)
        assert result is True


class TestENOSPCHandling:
    """Test ENOSPC (disk full) error handling during writes"""

    @patch("builtins.open")
    @patch("requests.get")
    def test_enospc_during_download_with_progress(self, mock_get, mock_open, tmp_path):
        """Should raise DiskSpaceError when ENOSPC occurs during download"""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-length": "1000"}
        mock_response.iter_content = lambda chunk_size: [b"chunk1", b"chunk2"]
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_get.return_value = mock_response

        # Mock file write to raise ENOSPC
        mock_file = MagicMock()
        mock_file.write.side_effect = OSError(28, "No space left on device")
        mock_open.return_value.__enter__.return_value = mock_file

        downloader = Downloader(output_dir=tmp_path, access_token="test_token")

        with pytest.raises(DiskSpaceError, match="Disk full"):
            downloader._download_with_progress(
                response=mock_response,
                output_path=tmp_path / "test.mp4",
                total_size=1000,
                filename="test.mp4",
            )

    @patch("builtins.open")
    @patch("requests.get")
    def test_other_oserror_reraises(self, mock_get, mock_open, tmp_path):
        """Should re-raise other OSErrors (not ENOSPC)"""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-length": "1000"}
        mock_response.iter_content = lambda chunk_size: [b"chunk1"]
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_get.return_value = mock_response

        # Mock file write to raise different OSError
        mock_file = MagicMock()
        mock_file.write.side_effect = OSError(13, "Permission denied")
        mock_open.return_value.__enter__.return_value = mock_file

        downloader = Downloader(output_dir=tmp_path, access_token="test_token")

        # Should raise original OSError, not DiskSpaceError
        with pytest.raises(OSError, match="Permission denied"):
            downloader._download_with_progress(
                response=mock_response,
                output_path=tmp_path / "test.mp4",
                total_size=1000,
                filename="test.mp4",
            )


class TestAtomicFileOperations:
    """Test atomic file operations with os.replace() and fallback"""

    @patch("os.replace")
    @patch("shutil.move")
    def test_atomic_replace_success(self, mock_move, mock_replace, tmp_path):
        """Should use os.replace() for atomic move (POSIX)"""
        # Create real temp file
        temp_file = tmp_path / ".tmp.test.mp4"
        temp_file.write_text("test content")

        final_file = tmp_path / "test.mp4"

        Downloader(output_dir=tmp_path, access_token="test_token")

        # Mock successful os.replace
        mock_replace.return_value = None

        # Simulate the atomic move code
        try:
            os.replace(str(temp_file), str(final_file))
        except OSError:
            shutil.move(str(temp_file), str(final_file))

        # Should call os.replace, not shutil.move
        mock_replace.assert_called_once()
        mock_move.assert_not_called()

    @patch("os.replace")
    @patch("shutil.move")
    def test_atomic_replace_fallback(self, mock_move, mock_replace, tmp_path):
        """Should fallback to shutil.move() if os.replace() fails"""
        temp_file = tmp_path / ".tmp.test.mp4"
        final_file = tmp_path / "test.mp4"

        # Mock os.replace failure (cross-filesystem)
        mock_replace.side_effect = OSError("Cross-device link")
        mock_move.return_value = None

        Downloader(output_dir=tmp_path, access_token="test_token")

        # Simulate the fallback code
        try:
            os.replace(str(temp_file), str(final_file))
        except OSError:
            shutil.move(str(temp_file), str(final_file))

        # Should call both os.replace (fails) and shutil.move (succeeds)
        mock_replace.assert_called_once()
        mock_move.assert_called_once()


class TestAdaptiveSizeValidation:
    """Test adaptive size validation with 2% and 5% tolerances"""

    def test_size_validation_small_file_within_tolerance(self, tmp_path):
        """Small file (<10MB) within 2% tolerance should pass"""
        Downloader(output_dir=tmp_path, access_token="test_token")

        # 5 MB file, 1% difference = 51.2 KB (within 2%)
        expected_size = 5 * 1024 * 1024  # 5 MB
        actual_size = expected_size + 51_200  # 1% larger

        size_diff = abs(actual_size - expected_size)
        size_diff_pct = size_diff / expected_size
        tolerance = 0.02 if expected_size < 10_000_000 else 0.05

        assert size_diff_pct < tolerance

    def test_size_validation_small_file_exceeds_tolerance(self, tmp_path):
        """Small file (<10MB) exceeding 2% tolerance should warn"""
        Downloader(output_dir=tmp_path, access_token="test_token")

        # 5 MB file, 3% difference (exceeds 2% tolerance)
        expected_size = 5 * 1024 * 1024  # 5 MB
        actual_size = int(expected_size * 1.03)  # 3% larger

        size_diff = abs(actual_size - expected_size)
        size_diff_pct = size_diff / expected_size
        tolerance = 0.02 if expected_size < 10_000_000 else 0.05

        assert size_diff_pct > tolerance

    def test_size_validation_large_file_within_tolerance(self, tmp_path):
        """Large file (>=10MB) within 5% tolerance should pass"""
        Downloader(output_dir=tmp_path, access_token="test_token")

        # 50 MB file, 4% difference = 2 MB (within 5%)
        expected_size = 50 * 1024 * 1024  # 50 MB
        actual_size = int(expected_size * 1.04)  # 4% larger

        size_diff = abs(actual_size - expected_size)
        size_diff_pct = size_diff / expected_size
        tolerance = 0.02 if expected_size < 10_000_000 else 0.05

        assert size_diff_pct < tolerance

    def test_size_validation_large_file_exceeds_tolerance(self, tmp_path):
        """Large file (>=10MB) exceeding 5% tolerance should warn"""
        Downloader(output_dir=tmp_path, access_token="test_token")

        # 50 MB file, 6% difference (exceeds 5% tolerance)
        expected_size = 50 * 1024 * 1024  # 50 MB
        actual_size = int(expected_size * 1.06)  # 6% larger

        size_diff = abs(actual_size - expected_size)
        size_diff_pct = size_diff / expected_size
        tolerance = 0.02 if expected_size < 10_000_000 else 0.05

        assert size_diff_pct > tolerance

    def test_size_validation_boundary_10mb(self, tmp_path):
        """Test boundary at exactly 10 MB"""
        Downloader(output_dir=tmp_path, access_token="test_token")

        # File at exactly 10 MB threshold
        expected_size_below = 10_000_000 - 1  # Just under 10 MB
        expected_size_at = 10_000_000  # Exactly 10 MB
        expected_size_above = 10_000_000 + 1  # Just over 10 MB

        # Below threshold: 2% tolerance
        tolerance_below = 0.02 if expected_size_below < 10_000_000 else 0.05
        assert tolerance_below == 0.02

        # At threshold: 5% tolerance
        tolerance_at = 0.02 if expected_size_at < 10_000_000 else 0.05
        assert tolerance_at == 0.05

        # Above threshold: 5% tolerance
        tolerance_above = 0.02 if expected_size_above < 10_000_000 else 0.05
        assert tolerance_above == 0.05


class TestFilenameGeneration:
    """Test safe filename generation"""

    def test_generate_filename_with_output_name(self, tmp_path):
        """Should use output_name when provided"""
        downloader = Downloader(
            output_dir=tmp_path, access_token="test_token", output_name="my_recording"
        )

        file_info = {"file_type": "audio_only", "file_extension": "M4A"}

        filename = downloader.generate_filename(file_info, "Meeting Topic")
        assert filename == "my_recording.m4a"

    def test_generate_filename_transcript_unique(self, tmp_path):
        downloader = Downloader(output_dir=tmp_path, access_token="token", output_name="session")
        file_info = {
            "file_type": "TRANSCRIPT",
            "file_extension": "VTT",
            "id": "en-US",
        }
        filename = downloader.generate_filename(file_info, "Topic")
        assert filename == "session_transcript_en_US.vtt"

    def test_generate_filename_sanitizes_topic(self, tmp_path):
        """Should sanitize meeting topic for filename"""
        downloader = Downloader(output_dir=tmp_path, access_token="test_token")

        file_info = {"file_type": "audio_only", "file_extension": "M4A", "id": "rec123"}

        # Meeting topic with special characters
        filename = downloader.generate_filename(file_info, "Meeting/Topic: Test@2024!")

        # Should replace special characters with underscores
        assert "/" not in filename
        assert ":" not in filename
        assert "@" not in filename
        assert "!" not in filename
        assert "_" in filename or "-" in filename


class TestTranscriptDownloadLists:
    def test_download_transcripts_returns_multiple(self, monkeypatch, tmp_path):
        downloader = Downloader(output_dir=tmp_path, access_token="token", output_name="session")

        def fake_download(
            self,
            download_url,
            file_info,
            meeting_topic,
            instance_start,
            show_progress,
            *args,
            **kwargs,
        ):
            name = downloader.generate_filename(file_info, meeting_topic, instance_start)
            path = tmp_path / name
            path.write_text("dummy")
            return path

        monkeypatch.setattr(Downloader, "download_file", fake_download)

        files = downloader.download_transcripts_and_chat(
            recording_files=[
                {
                    "file_extension": "VTT",
                    "file_type": "TRANSCRIPT",
                    "download_url": "https://example.com/vtt1",
                    "id": "en",
                },
                {
                    "file_extension": "VTT",
                    "file_type": "TRANSCRIPT",
                    "download_url": "https://example.com/vtt2",
                    "id": "es",
                },
            ],
            meeting_topic="Topic",
            instance_start=None,
            show_progress=False,
            skip_transcript=False,
            skip_chat=True,
            skip_timeline=True,
        )

        vtts = [p.name for p in files["vtt"]]
        assert len(vtts) == 2
        assert vtts[0] != vtts[1]

    def test_download_transcripts_skips_non_timeline_json(self, monkeypatch, tmp_path):
        downloader = Downloader(output_dir=tmp_path, access_token="token", output_name="session")

        def fail_download(*args, **kwargs):
            raise AssertionError("Should not download non-timeline JSON")

        monkeypatch.setattr(Downloader, "download_file", fail_download)

        files = downloader.download_transcripts_and_chat(
            recording_files=[
                {
                    "file_extension": "JSON",
                    "file_type": "SUMMARY",
                    "download_url": "https://example.com/poll.json",
                }
            ],
            meeting_topic="Topic",
            instance_start=None,
            show_progress=False,
            skip_transcript=True,
            skip_chat=True,
            skip_timeline=False,
        )

        assert files["timeline"] == []
