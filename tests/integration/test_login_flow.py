"""
Integration tests for login flow error handling.

Tests the complete login flow including broker error responses.
"""

import json
from unittest.mock import Mock, patch

import pytest

from dlzoom.login import main as login_main


class TestLoginErrorHandling:
    """Test login command handles broker errors correctly."""

    @patch("dlzoom.login.webbrowser.open")
    @patch("dlzoom.login.requests.post")
    @patch("dlzoom.login.requests.get")
    @patch("dlzoom.login.save_tokens")
    def test_login_handles_500_error_from_broker(
        self,
        mock_save: Mock,
        mock_get: Mock,
        mock_post: Mock,
        mock_browser: Mock,
    ) -> None:
        """
        CRITICAL BUG REGRESSION TEST:
        Verify login command handles HTTP 500 from broker and displays error.

        Previously, 500 errors were ignored and CLI would poll until timeout.
        """
        # Mock start auth response
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "auth_url": "https://zoom.us/oauth/authorize?...",
                "session_id": "test-session-123",
            },
        )

        # Mock poll response with 500 error
        error_response = Mock()
        error_response.status_code = 500
        error_response.json = lambda: {
            "status": "error",
            "http_status": 400,
            "body": "invalid_grant: Authorization code is invalid or expired",
        }
        error_response.text = json.dumps(
            {
                "status": "error",
                "http_status": 400,
                "body": "invalid_grant: Authorization code is invalid or expired",
            }
        )
        mock_get.return_value = error_response

        # Execute login and expect SystemExit
        with pytest.raises(SystemExit) as exc_info:
            with patch("dlzoom.login.console") as mock_console:
                login_main.callback(auth_url=None)

        # Verify it exited with error code
        assert exc_info.value.code == 1

        # Verify error was displayed (not ignored)
        # The 500 handler should print the error message
        assert mock_console.print.called

    @patch("dlzoom.login.webbrowser.open")
    @patch("dlzoom.login.requests.post")
    @patch("dlzoom.login.requests.get")
    def test_login_handles_410_expired_session(
        self,
        mock_get: Mock,
        mock_post: Mock,
        mock_browser: Mock,
    ) -> None:
        """
        Verify login command handles HTTP 410 (expired session) correctly.
        """
        # Mock start auth response
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "auth_url": "https://zoom.us/oauth/authorize?...",
                "session_id": "expired-session",
            },
        )

        # Mock poll response with 410 (expired)
        expired_response = Mock()
        expired_response.status_code = 410
        expired_response.json = lambda: {"status": "expired"}
        mock_get.return_value = expired_response

        # Execute and expect SystemExit
        with pytest.raises(SystemExit) as exc_info:
            with patch("dlzoom.login.console"):
                login_main.callback(auth_url=None)

        assert exc_info.value.code == 1

    @patch("dlzoom.login.webbrowser.open")
    @patch("dlzoom.login.requests.post")
    @patch("dlzoom.login.requests.get")
    @patch("dlzoom.login.save_tokens")
    @patch("dlzoom.login.time.time")
    def test_login_timeout_after_10_minutes(
        self,
        mock_time: Mock,
        mock_save: Mock,
        mock_get: Mock,
        mock_post: Mock,
        mock_browser: Mock,
    ) -> None:
        """
        Verify login command times out after 10 minutes of polling.
        """
        # Mock start auth response
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "auth_url": "https://zoom.us/oauth/authorize?...",
                "session_id": "timeout-test",
            },
        )

        # Mock time to simulate timeout
        # Start at 0, then jump to 601 seconds (> 10 minutes)
        mock_time.side_effect = [0, 0, 601]

        # Mock poll response as pending
        pending_response = Mock()
        pending_response.status_code = 200
        pending_response.json = lambda: {"status": "pending"}
        mock_get.return_value = pending_response

        # Execute and expect SystemExit
        with pytest.raises(SystemExit) as exc_info:
            with patch("dlzoom.login.console"):
                with patch("dlzoom.login.time.sleep"):  # Skip actual sleep
                    login_main.callback(auth_url=None)

        assert exc_info.value.code == 1

    @patch("dlzoom.login.webbrowser.open")
    @patch("dlzoom.login.requests.post")
    @patch("dlzoom.login.requests.get")
    @patch("dlzoom.login.save_tokens")
    def test_login_success_saves_tokens(
        self,
        mock_save: Mock,
        mock_get: Mock,
        mock_post: Mock,
        mock_browser: Mock,
    ) -> None:
        """
        Verify successful login saves tokens correctly.
        """
        # Mock start auth response
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "auth_url": "https://zoom.us/oauth/authorize?...",
                "session_id": "success-test",
            },
        )

        # Mock poll response with tokens
        success_response = Mock()
        success_response.status_code = 200
        success_response.json = lambda: {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "recording:read",
        }
        mock_get.return_value = success_response

        # Execute login
        with patch("dlzoom.login.console"):
            with patch("dlzoom.login.Config") as mock_config:
                mock_config.return_value.tokens_path = "/tmp/tokens.json"
                login_main.callback(auth_url=None)

        # Verify save_tokens was called
        assert mock_save.called

        # Verify tokens have correct structure
        call_args = mock_save.call_args
        tokens = call_args[0][1]
        assert tokens.access_token == "test_access_token"
        assert tokens.refresh_token == "test_refresh_token"


class TestLoginBrokerIntegration:
    """Test login command integration with broker responses."""

    @patch("dlzoom.login.webbrowser.open")
    @patch("dlzoom.login.requests.post")
    @patch("dlzoom.login.requests.get")
    def test_broker_error_json_parsing(
        self,
        mock_get: Mock,
        mock_post: Mock,
        mock_browser: Mock,
    ) -> None:
        """
        Verify login can parse JSON error from broker.

        Broker returns:
        {
          "status": "error",
          "http_status": 400,
          "body": "detailed error message from Zoom"
        }
        """
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "auth_url": "https://zoom.us/oauth/authorize?...",
                "session_id": "json-error-test",
            },
        )

        # Broker error response
        error_response = Mock()
        error_response.status_code = 500
        error_response.json = lambda: {
            "status": "error",
            "http_status": 401,
            "body": "invalid_client: The client credentials are invalid",
        }
        error_response.text = json.dumps(
            {
                "status": "error",
                "http_status": 401,
                "body": "invalid_client: The client credentials are invalid",
            }
        )
        mock_get.return_value = error_response

        with pytest.raises(SystemExit):
            with patch("dlzoom.login.console") as mock_console:
                login_main.callback(auth_url=None)

        # Verify error message was extracted and displayed
        calls = [str(call) for call in mock_console.print.call_args_list]
        error_displayed = any("invalid_client" in str(call) for call in calls)
        assert error_displayed, "Broker error message should be displayed to user"

    @patch("dlzoom.login.webbrowser.open")
    @patch("dlzoom.login.requests.post")
    @patch("dlzoom.login.requests.get")
    def test_broker_non_json_error(
        self,
        mock_get: Mock,
        mock_post: Mock,
        mock_browser: Mock,
    ) -> None:
        """
        Verify login handles non-JSON error responses from broker.

        If broker returns plain text error, should display it.
        """
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "auth_url": "https://zoom.us/oauth/authorize?...",
                "session_id": "text-error-test",
            },
        )

        # Non-JSON error response
        error_response = Mock()
        error_response.status_code = 500
        error_response.json = Mock(side_effect=json.JSONDecodeError("test", "test", 0))
        error_response.text = "Internal Server Error: Worker exception"
        mock_get.return_value = error_response

        with pytest.raises(SystemExit):
            with patch("dlzoom.login.console") as mock_console:
                login_main.callback(auth_url=None)

        # Should display the raw text
        calls = [str(call) for call in mock_console.print.call_args_list]
        error_displayed = any("Worker exception" in str(call) for call in calls)
        assert error_displayed
