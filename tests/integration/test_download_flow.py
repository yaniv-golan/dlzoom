"""
Integration tests for the complete download flow.

These tests verify the critical path: client -> token retrieval -> Downloader -> download.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from dlzoom.downloader import Downloader
from dlzoom.handlers import _handle_download_mode
from dlzoom.output import OutputFormatter
from dlzoom.recorder_selector import RecordingSelector
from dlzoom.zoom_client import ZoomClient
from dlzoom.zoom_user_client import ZoomUserClient


class TestDownloadFlowIntegration:
    """Test the complete download flow from client to file on disk."""

    @pytest.fixture
    def mock_zoom_client(self) -> Mock:
        """Create a mock ZoomClient with _get_access_token method."""
        client = Mock(spec=ZoomClient)
        client._get_access_token = Mock(return_value="test_access_token_s2s")

        # Mock API responses
        client.get_meeting_recordings = Mock(
            return_value={
                "recording_files": [
                    {
                        "id": "audio123",
                        "recording_type": "audio_only",
                        "file_type": "M4A",
                        "file_extension": "M4A",
                        "file_size": 1024000,
                        "download_url": "https://zoom.us/rec/download/test.m4a",
                        "status": "completed",
                    },
                    {
                        "id": "transcript456",
                        "recording_type": "transcript",
                        "file_type": "TRANSCRIPT",
                        "file_extension": "VTT",
                        "file_size": 5000,
                        "download_url": "https://zoom.us/rec/download/test.vtt",
                        "status": "completed",
                    },
                ],
                "topic": "Test Meeting",
                "start_time": "2024-01-01T10:00:00Z",
                "uuid": "test-uuid-123",
                "duration": 60,
            }
        )
        # Mock get_all_participants to return empty list (not a Mock object)
        client.get_all_participants = Mock(return_value=[])
        return client

    @pytest.fixture
    def mock_zoom_user_client(self) -> Mock:
        """Create a mock ZoomUserClient with _get_access_token method."""
        client = Mock(spec=ZoomUserClient)
        client._get_access_token = Mock(return_value="test_access_token_user")

        # Mock API responses (same structure as S2S)
        client.get_meeting_recordings = Mock(
            return_value={
                "recording_files": [
                    {
                        "id": "audio789",
                        "recording_type": "audio_only",
                        "file_type": "M4A",
                        "file_extension": "M4A",
                        "file_size": 2048000,
                        "download_url": "https://zoom.us/rec/download/user_test.m4a",
                        "status": "completed",
                    }
                ],
                "topic": "User Test Meeting",
                "start_time": "2024-01-02T14:00:00Z",
                "uuid": "user-test-uuid-456",
            }
        )
        return client

    def test_downloader_receives_correct_access_token_s2s(
        self, mock_zoom_client: Mock, tmp_path: Path
    ) -> None:
        """
        CRITICAL BUG REGRESSION TEST:
        Verify Downloader is constructed with access token from ZoomClient.

        This test would have caught the bug where Downloader(output_dir, output_name)
        was called without the access_token parameter.
        """
        selector = RecordingSelector()
        formatter = OutputFormatter("human")

        with patch("dlzoom.handlers.Downloader") as mock_downloader_cls:
            mock_downloader_instance = Mock()
            mock_downloader_cls.return_value = mock_downloader_instance

            # Mock download_file to return a path
            mock_downloader_instance.download_file = Mock(return_value=tmp_path / "test.m4a")
            mock_downloader_instance.download_transcripts_and_chat = Mock(
                return_value={"vtt": [], "txt": [], "timeline": [], "speakers": []}
            )

            # Execute the handler
            _handle_download_mode(
                client=mock_zoom_client,
                selector=selector,
                meeting_id="123456789",
                recording_id=None,
                output_dir=tmp_path,
                output_name="test_meeting",
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
                filename_template=None,
                folder_template=None,
            )

            # CRITICAL ASSERTION: Verify _get_access_token was called
            mock_zoom_client._get_access_token.assert_called_once()

            # CRITICAL ASSERTION: Verify Downloader was constructed with correct args
            mock_downloader_cls.assert_called_once()
            call_args = mock_downloader_cls.call_args

            # Should be: Downloader(output_dir, access_token, output_name)
            assert call_args[0][0] == tmp_path  # output_dir
            assert call_args[0][1] == "test_access_token_s2s"  # access_token
            assert call_args[0][2] == "test_meeting"  # output_name

    def test_downloader_receives_correct_access_token_user_oauth(
        self, mock_zoom_user_client: Mock, tmp_path: Path
    ) -> None:
        """
        Verify Downloader receives access token from ZoomUserClient.

        Tests both S2S and User OAuth paths to ensure token retrieval works
        correctly for both authentication modes.
        """
        selector = RecordingSelector()
        formatter = OutputFormatter("human")

        with patch("dlzoom.handlers.Downloader") as mock_downloader_cls:
            mock_downloader_instance = Mock()
            mock_downloader_cls.return_value = mock_downloader_instance

            mock_downloader_instance.download_file = Mock(return_value=tmp_path / "user_test.m4a")
            mock_downloader_instance.download_transcripts_and_chat = Mock(
                return_value={"vtt": [], "txt": [], "timeline": [], "speakers": []}
            )

            _handle_download_mode(
                client=mock_zoom_user_client,
                selector=selector,
                meeting_id="987654321",
                recording_id=None,
                output_dir=tmp_path,
                output_name="user_meeting",
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
                filename_template=None,
                folder_template=None,
            )

            # Verify token was retrieved from user client
            mock_zoom_user_client._get_access_token.assert_called_once()

            # Verify Downloader got the correct token
            mock_downloader_cls.assert_called_once()
            call_args = mock_downloader_cls.call_args
            assert call_args[0][1] == "test_access_token_user"

    def test_download_with_real_downloader_constructor(
        self, mock_zoom_client: Mock, tmp_path: Path
    ) -> None:
        """
        Test with real Downloader instantiation (not mocked).

        This verifies the constructor signature is correct and no TypeError
        is raised when passing the access token.
        """
        selector = RecordingSelector()
        formatter = OutputFormatter("human")

        # Mock only the actual download, not the constructor
        with patch("dlzoom.handlers.Downloader.download_file") as mock_download:
            with patch(
                "dlzoom.handlers.Downloader.download_transcripts_and_chat"
            ) as mock_transcripts:
                mock_download.return_value = tmp_path / "real_test.m4a"
                mock_transcripts.return_value = {
                    "vtt": [],
                    "txt": [],
                    "timeline": [],
                    "speakers": [],
                }

                # This should NOT raise TypeError about wrong number of arguments
                try:
                    _handle_download_mode(
                        client=mock_zoom_client,
                        selector=selector,
                        meeting_id="111222333",
                        recording_id=None,
                        output_dir=tmp_path,
                        output_name="real_test",
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
                        filename_template=None,
                        folder_template=None,
                    )
                except TypeError as e:
                    if "takes 2 positional arguments but 3 were given" in str(e):
                        pytest.fail(
                            f"Downloader constructor signature mismatch: {e}\n"
                            "This indicates the old bug where "
                            "output_name was passed as access_token"
                        )
                    raise

    def test_access_token_passed_to_download_file(
        self, mock_zoom_client: Mock, tmp_path: Path
    ) -> None:
        """
        Verify the access token is actually used in download_file calls.

        The Downloader should append the access_token to download URLs.
        """
        selector = RecordingSelector()
        formatter = OutputFormatter("human")

        # Create a real Downloader instance but mock requests
        with patch("dlzoom.downloader.requests") as mock_requests:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {"content-length": "1024000"}
            mock_response.iter_content = Mock(return_value=[b"test_data"])
            mock_requests.get = Mock(return_value=mock_response)

            # Execute download
            _handle_download_mode(
                client=mock_zoom_client,
                selector=selector,
                meeting_id="555666777",
                recording_id=None,
                output_dir=tmp_path,
                output_name="token_test",
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
                filename_template=None,
                folder_template=None,
            )

            # Verify requests.get was called with token in URL
            assert mock_requests.get.called
            call_args = mock_requests.get.call_args
            url_used = call_args[0][0] if call_args[0] else call_args[1].get("url", "")

            # The URL should contain the access token as a query parameter
            assert "access_token=test_access_token_s2s" in url_used

    def test_dry_run_does_not_call_get_access_token(
        self, mock_zoom_client: Mock, tmp_path: Path
    ) -> None:
        """
        Verify dry run mode doesn't retrieve access token or create Downloader.

        This is an optimization - dry run should only fetch metadata.
        """
        selector = RecordingSelector()
        formatter = OutputFormatter("human")

        _handle_download_mode(
            client=mock_zoom_client,
            selector=selector,
            meeting_id="999888777",
            recording_id=None,
            output_dir=tmp_path,
            output_name="dry_run_test",
            skip_transcript=False,
            skip_chat=False,
            skip_timeline=False,
            dry_run=True,  # DRY RUN MODE
            log_file=None,
            formatter=formatter,
            verbose=False,
            debug=False,
            json_mode=False,
            wait=None,
            filename_template=None,
            folder_template=None,
        )

        # Token should NOT be retrieved in dry run mode
        # (returns early before downloader construction)
        mock_zoom_client._get_access_token.assert_not_called()


class TestDownloaderConstructorSignature:
    """Direct tests of Downloader constructor to verify signature."""

    def test_downloader_requires_access_token(self, tmp_path: Path) -> None:
        """
        Verify Downloader constructor requires access_token as 2nd parameter.

        This is a unit test but placed in integration suite because it's
        testing the integration contract between handlers and downloader.
        """
        # Correct usage
        downloader = Downloader(output_dir=tmp_path, access_token="test_token", output_name="test")
        assert downloader.access_token == "test_token"
        assert downloader.output_name == "test"

    def test_downloader_old_bug_pattern(self, tmp_path: Path) -> None:
        """
        Document the old bug pattern: Downloader(output_dir, output_name).

        When called with Downloader(output_dir, output_name), the output_name
        becomes the access_token (wrong!). This test verifies the fix.
        """
        # The OLD BUG PATTERN was: Downloader(output_dir, output_name)
        # This would treat output_name as the access_token

        # Now with the fix, we must pass 3 args: (output_dir, access_token, output_name)
        # Let's verify the correct pattern works
        downloader = Downloader(tmp_path, "correct_token", "correct_output_name")
        assert downloader.access_token == "correct_token"
        assert downloader.output_name == "correct_output_name"

        # And verify the old buggy pattern would give wrong results
        buggy_downloader = Downloader(tmp_path, "filename.m4a")  # Missing 3rd arg
        # In the buggy version, "filename.m4a" becomes the token!
        assert buggy_downloader.access_token == "filename.m4a"  # This was the bug
        assert buggy_downloader.output_name is None  # output_name was never set
