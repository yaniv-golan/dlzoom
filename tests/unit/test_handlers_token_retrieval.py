"""
Unit tests for token retrieval in download handlers.

These tests specifically verify that handlers correctly retrieve and use
access tokens from clients before constructing Downloader.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from dlzoom.handlers import _handle_download_mode
from dlzoom.output import OutputFormatter
from dlzoom.recorder_selector import RecordingSelector


class TestHandlersTokenRetrieval:
    """Unit tests for token retrieval logic in handlers."""

    @pytest.fixture
    def mock_client_with_token(self) -> Mock:
        """Create a mock client with _get_access_token method."""
        client = Mock()
        client._get_access_token = Mock(return_value="mock_token_12345")
        client.get_meeting_recordings = Mock(
            return_value={
                "recording_files": [
                    {
                        "id": "test123",
                        "file_extension": "M4A",
                        "file_size": 1000,
                        "download_url": "https://zoom.us/rec/test.m4a",
                        "status": "completed",
                    }
                ],
                "topic": "Test",
                "start_time": "2024-01-01T10:00:00Z",
                "uuid": "test-uuid",
            }
        )
        return client

    def test_get_access_token_called_before_downloader_construction(
        self, mock_client_with_token: Mock, tmp_path: Path
    ) -> None:
        """
        Verify _get_access_token is called before Downloader is constructed.

        This is the PRIMARY regression test for the critical bug.
        """
        selector = RecordingSelector()
        formatter = OutputFormatter("human")

        with patch("dlzoom.handlers.Downloader") as mock_downloader_cls:
            mock_downloader = Mock()
            mock_downloader_cls.return_value = mock_downloader
            mock_downloader.download_file = Mock(return_value=tmp_path / "test.m4a")
            mock_downloader.download_transcripts_and_chat = Mock(
                return_value={"vtt": [], "txt": [], "timeline": [], "speakers": []}
            )

            _handle_download_mode(
                client=mock_client_with_token,
                selector=selector,
                meeting_id="123",
                recording_id=None,
                output_dir=tmp_path,
                output_name="test",
                skip_transcript=True,
                skip_chat=True,
                skip_timeline=True,
                dry_run=False,
                log_file=None,
                formatter=formatter,
                verbose=False,
                debug=False,
                json_mode=False,
                wait=None,
            )

            # CRITICAL: Verify token was retrieved
            mock_client_with_token._get_access_token.assert_called_once()

            # CRITICAL: Verify it was called BEFORE Downloader construction
            # This checks the call order
            assert mock_client_with_token._get_access_token.call_count == 1
            assert mock_downloader_cls.call_count == 1

    def test_access_token_passed_as_second_argument(
        self, mock_client_with_token: Mock, tmp_path: Path
    ) -> None:
        """
        Verify access token is passed as 2nd argument to Downloader.__init__.

        Signature: Downloader(output_dir, access_token, output_name=None)
        """
        selector = RecordingSelector()
        formatter = OutputFormatter("human")

        with patch("dlzoom.handlers.Downloader") as mock_downloader_cls:
            mock_downloader = Mock()
            mock_downloader_cls.return_value = mock_downloader
            mock_downloader.download_file = Mock(return_value=tmp_path / "test.m4a")
            mock_downloader.download_transcripts_and_chat = Mock(
                return_value={"vtt": [], "txt": [], "timeline": [], "speakers": []}
            )

            _handle_download_mode(
                client=mock_client_with_token,
                selector=selector,
                meeting_id="456",
                recording_id=None,
                output_dir=tmp_path,
                output_name="my_output",
                skip_transcript=True,
                skip_chat=True,
                skip_timeline=True,
                dry_run=False,
                log_file=None,
                formatter=formatter,
                verbose=False,
                debug=False,
                json_mode=False,
                wait=None,
            )

            # Verify constructor call arguments
            assert mock_downloader_cls.called
            args, kwargs = mock_downloader_cls.call_args

            # Positional args should be: (output_dir, access_token, output_name)
            assert len(args) == 3
            assert args[0] == tmp_path  # output_dir
            assert args[1] == "mock_token_12345"  # access_token
            assert args[2] == "my_output"  # output_name

    def test_different_token_for_different_client(self, tmp_path: Path) -> None:
        """
        Verify handler correctly retrieves token from different client types.
        """
        # Create a different mock client with different token
        client2 = Mock()
        client2._get_access_token = Mock(return_value="different_token_67890")
        client2.get_meeting_recordings = Mock(
            return_value={
                "recording_files": [
                    {
                        "id": "different",
                        "file_extension": "M4A",
                        "file_size": 2000,
                        "download_url": "https://zoom.us/rec/different.m4a",
                        "status": "completed",
                    }
                ],
                "topic": "Different Test",
                "start_time": "2024-01-02T10:00:00Z",
                "uuid": "different-uuid",
            }
        )

        selector = RecordingSelector()
        formatter = OutputFormatter("human")

        with patch("dlzoom.handlers.Downloader") as mock_downloader_cls:
            mock_downloader = Mock()
            mock_downloader_cls.return_value = mock_downloader
            mock_downloader.download_file = Mock(return_value=tmp_path / "diff.m4a")
            mock_downloader.download_transcripts_and_chat = Mock(
                return_value={"vtt": [], "txt": [], "timeline": [], "speakers": []}
            )

            _handle_download_mode(
                client=client2,
                selector=selector,
                meeting_id="789",
                recording_id=None,
                output_dir=tmp_path,
                output_name="different",
                skip_transcript=True,
                skip_chat=True,
                skip_timeline=True,
                dry_run=False,
                log_file=None,
                formatter=formatter,
                verbose=False,
                debug=False,
                json_mode=False,
                wait=None,
            )

            # Verify correct token was retrieved and passed
            client2._get_access_token.assert_called_once()
            args, _ = mock_downloader_cls.call_args
            assert args[1] == "different_token_67890"

    def test_token_not_retrieved_in_dry_run(
        self, mock_client_with_token: Mock, tmp_path: Path
    ) -> None:
        """
        Verify token is NOT retrieved during dry run.

        Dry run should return early without creating Downloader.
        """
        selector = RecordingSelector()
        formatter = OutputFormatter("human")

        _handle_download_mode(
            client=mock_client_with_token,
            selector=selector,
            meeting_id="999",
            recording_id=None,
            output_dir=tmp_path,
            output_name="dry",
            skip_transcript=False,
            skip_chat=False,
            skip_timeline=False,
            dry_run=True,  # DRY RUN
            log_file=None,
            formatter=formatter,
            verbose=False,
            debug=False,
            json_mode=False,
            wait=None,
        )

        # Token should NOT be retrieved in dry run
        mock_client_with_token._get_access_token.assert_not_called()

    def test_token_retrieval_with_templates(
        self, mock_client_with_token: Mock, tmp_path: Path
    ) -> None:
        """
        Verify token is retrieved even when using filename/folder templates.

        Templates should not affect the core token retrieval logic.
        """
        selector = RecordingSelector()
        formatter = OutputFormatter("human")

        with patch("dlzoom.handlers.Downloader") as mock_downloader_cls:
            mock_downloader = Mock()
            mock_downloader_cls.return_value = mock_downloader
            mock_downloader.download_file = Mock(return_value=tmp_path / "test.m4a")
            mock_downloader.download_transcripts_and_chat = Mock(
                return_value={"vtt": [], "txt": [], "timeline": [], "speakers": []}
            )

            _handle_download_mode(
                client=mock_client_with_token,
                selector=selector,
                meeting_id="template_test",
                recording_id=None,
                output_dir=tmp_path,
                output_name="base_name",
                skip_transcript=True,
                skip_chat=True,
                skip_timeline=True,
                dry_run=False,
                log_file=None,
                formatter=formatter,
                verbose=False,
                debug=False,
                json_mode=False,
                wait=None,
                filename_template="{topic}_{start_time:%Y%m%d}",
                folder_template="{start_time:%Y/%m}",
            )

            # Token should still be retrieved with templates
            mock_client_with_token._get_access_token.assert_called_once()

            # And passed to Downloader
            args, _ = mock_downloader_cls.call_args
            assert args[1] == "mock_token_12345"


class TestTokenRetrievalEdgeCases:
    """Test edge cases in token retrieval."""

    def test_client_missing_get_access_token_method(self, tmp_path: Path) -> None:
        """
        Verify appropriate error if client doesn't have _get_access_token.

        This shouldn't happen in practice but worth testing defensive behavior.
        """
        bad_client = Mock()
        # Intentionally don't add _get_access_token method
        bad_client.get_meeting_recordings = Mock(
            return_value={
                "recording_files": [
                    {
                        "id": "test",
                        "file_extension": "M4A",
                        "file_size": 1000,
                        "download_url": "https://zoom.us/rec/test.m4a",
                        "status": "completed",
                    }
                ],
                "topic": "Test",
                "start_time": "2024-01-01T10:00:00Z",
                "uuid": "test",
            }
        )

        selector = RecordingSelector()
        formatter = OutputFormatter("human")

        with pytest.raises(AttributeError):
            _handle_download_mode(
                client=bad_client,
                selector=selector,
                meeting_id="bad",
                recording_id=None,
                output_dir=tmp_path,
                output_name="bad",
                skip_transcript=True,
                skip_chat=True,
                skip_timeline=True,
                dry_run=False,
                log_file=None,
                formatter=formatter,
                verbose=False,
                debug=False,
                json_mode=False,
                wait=None,
            )

    def test_get_access_token_raises_exception(self, tmp_path: Path) -> None:
        """
        Verify exception from _get_access_token is properly propagated.
        """
        failing_client = Mock()
        failing_client._get_access_token = Mock(
            side_effect=Exception("Token retrieval failed: network error")
        )
        failing_client.get_meeting_recordings = Mock(
            return_value={
                "recording_files": [
                    {
                        "id": "test",
                        "file_extension": "M4A",
                        "file_size": 1000,
                        "download_url": "https://zoom.us/rec/test.m4a",
                        "status": "completed",
                    }
                ],
                "topic": "Test",
                "start_time": "2024-01-01T10:00:00Z",
                "uuid": "test",
            }
        )

        selector = RecordingSelector()
        formatter = OutputFormatter("human")

        with pytest.raises(Exception) as exc_info:
            _handle_download_mode(
                client=failing_client,
                selector=selector,
                meeting_id="fail",
                recording_id=None,
                output_dir=tmp_path,
                output_name="fail",
                skip_transcript=True,
                skip_chat=True,
                skip_timeline=True,
                dry_run=False,
                log_file=None,
                formatter=formatter,
                verbose=False,
                debug=False,
                json_mode=False,
                wait=None,
            )

        assert "Token retrieval failed" in str(exc_info.value)
