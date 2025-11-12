"""
Tests for ZoomClient network resilience and credential protection
"""

from unittest.mock import Mock, patch

import pytest
import requests

from dlzoom.exceptions import AuthenticationError, RateLimitedError
from dlzoom.zoom_client import ZoomAPIError, ZoomClient


class TestCredentialProtection:
    """Test credential protection in __repr__ and __del__"""

    def test_repr_excludes_credentials(self):
        """__repr__ should not expose credentials"""
        client = ZoomClient(
            account_id="secret_account", client_id="secret_client", client_secret="very_secret"
        )

        repr_str = repr(client)

        # Should not contain actual credentials
        assert "secret_account" not in repr_str
        assert "secret_client" not in repr_str
        assert "very_secret" not in repr_str

        # Should contain safe information
        assert "ZoomClient" in repr_str
        assert "base_url" in repr_str
        assert "account_id_set=True" in repr_str
        assert "client_id_set=True" in repr_str

    def test_repr_with_cached_token(self):
        """__repr__ should indicate if token is cached"""
        client = ZoomClient("acc", "cli", "sec")
        client._access_token = "cached_token"

        repr_str = repr(client)
        assert "token_cached=True" in repr_str

    def test_repr_without_cached_token(self):
        """__repr__ should indicate if token is not cached"""
        client = ZoomClient("acc", "cli", "sec")

        repr_str = repr(client)
        assert "token_cached=False" in repr_str

    def test_del_zeros_credentials(self):
        """__del__ should zero out credentials"""
        client = ZoomClient("acc", "cli", "sec")
        client._access_token = "token"

        # Call __del__ manually
        client.__del__()

        assert client.account_id == ""
        assert client.client_id == ""
        assert client.client_secret == ""
        assert client._access_token is None


class TestNetworkTimeouts:
    """Test timeout handling for OAuth and API requests"""

    @patch("requests.post")
    def test_oauth_timeout(self, mock_post):
        """OAuth request should timeout after 30 seconds"""
        mock_post.side_effect = requests.exceptions.Timeout()

        client = ZoomClient("acc", "cli", "sec")

        with pytest.raises(AuthenticationError, match="Authentication timeout"):
            client._get_access_token()

        # Verify timeout was set to 30 seconds
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["timeout"] == 30

    @patch("time.sleep")  # Mock sleep to avoid delays
    @patch("requests.post")
    @patch("requests.request")
    def test_api_request_timeout(self, mock_request, mock_post, mock_sleep):
        """API request should timeout after 30 seconds"""
        # Mock OAuth token
        mock_post.return_value = Mock(
            status_code=200, json=lambda: {"access_token": "token", "expires_in": 3600}
        )

        # Mock API timeout - will retry 3 times
        mock_request.side_effect = requests.exceptions.Timeout()

        client = ZoomClient("acc", "cli", "sec")

        with pytest.raises(ZoomAPIError, match="Network request failed"):
            client._make_request("GET", "meetings/123")

        # Verify timeout was set
        assert mock_request.call_args.kwargs["timeout"] == 30
        # Should have tried 3 times (default retry_count)
        assert mock_request.call_count == 3


class TestRetryLogic:
    """Test exponential backoff retry logic"""

    @patch("requests.post")
    @patch("requests.request")
    @patch("time.sleep")
    def test_retry_on_rate_limit_429(self, mock_sleep, mock_request, mock_post):
        """Should retry on 429 rate limit with exponential backoff"""
        # Mock OAuth
        mock_post.return_value = Mock(
            status_code=200, json=lambda: {"access_token": "token", "expires_in": 3600}
        )

        # Mock API: 429 twice, then success
        mock_request.side_effect = [
            Mock(status_code=429),
            Mock(status_code=429),
            Mock(status_code=200, json=lambda: {"data": "success"}),
        ]

        client = ZoomClient("acc", "cli", "sec")
        result = client._make_request("GET", "meetings/123")

        assert result == {"data": "success"}
        assert mock_request.call_count == 3

        # Check exponential backoff: 1.0, 2.0 seconds
        assert mock_sleep.call_count == 2
        sleep_times = [call[0][0] for call in mock_sleep.call_args_list]
        assert sleep_times[0] == 1.0  # backoff_factor * (2 ** 0)
        assert sleep_times[1] == 2.0  # backoff_factor * (2 ** 1)

    @patch("requests.post")
    @patch("requests.request")
    @patch("time.sleep")
    def test_retry_on_server_error_503(self, mock_sleep, mock_request, mock_post):
        """Should retry on 503 server error with exponential backoff"""
        # Mock OAuth
        mock_post.return_value = Mock(
            status_code=200, json=lambda: {"access_token": "token", "expires_in": 3600}
        )

        # Mock API: 503 once, then success
        mock_request.side_effect = [
            Mock(status_code=503),
            Mock(status_code=200, json=lambda: {"data": "success"}),
        ]

        client = ZoomClient("acc", "cli", "sec")
        result = client._make_request("GET", "meetings/123")

        assert result == {"data": "success"}
        assert mock_request.call_count == 2
        mock_sleep.assert_called_once_with(1.0)

    @patch("requests.post")
    @patch("requests.request")
    @patch("time.sleep")
    def test_retry_exhausted_429(self, mock_sleep, mock_request, mock_post):
        """Should raise RateLimitedError after max retries"""
        # Mock OAuth
        mock_post.return_value = Mock(
            status_code=200, json=lambda: {"access_token": "token", "expires_in": 3600}
        )

        # Mock API: always 429
        mock_request.return_value = Mock(status_code=429)

        client = ZoomClient("acc", "cli", "sec")

        with pytest.raises(RateLimitedError, match="Rate limit exceeded"):
            client._make_request("GET", "meetings/123", retry_count=3)

        # Should try 3 times (no retry after last attempt)
        assert mock_request.call_count == 3
        # Should sleep 2 times (between attempts)
        assert mock_sleep.call_count == 2

    @patch("requests.post")
    @patch("requests.request")
    @patch("time.sleep")
    def test_retry_exhausted_server_error(self, mock_sleep, mock_request, mock_post):
        """Should raise ZoomAPIError after max retries on server error"""
        # Mock OAuth
        mock_post.return_value = Mock(
            status_code=200, json=lambda: {"access_token": "token", "expires_in": 3600}
        )

        # Mock API: always 503
        mock_request.return_value = Mock(status_code=503)

        client = ZoomClient("acc", "cli", "sec")

        with pytest.raises(ZoomAPIError, match="Zoom API server error"):
            client._make_request("GET", "meetings/123", retry_count=3)

    @patch("requests.post")
    @patch("requests.request")
    @patch("time.sleep")
    def test_retry_on_network_error(self, mock_sleep, mock_request, mock_post):
        """Should retry on network errors (ConnectionError)"""
        # Mock OAuth
        mock_post.return_value = Mock(
            status_code=200, json=lambda: {"access_token": "token", "expires_in": 3600}
        )

        # Mock API: ConnectionError once, then success
        mock_request.side_effect = [
            requests.exceptions.ConnectionError("Connection failed"),
            Mock(status_code=200, json=lambda: {"data": "success"}),
        ]

        client = ZoomClient("acc", "cli", "sec")
        result = client._make_request("GET", "meetings/123")

        assert result == {"data": "success"}
        assert mock_request.call_count == 2
        mock_sleep.assert_called_once_with(1.0)

    @patch("requests.post")
    @patch("requests.request")
    @patch("time.sleep")
    def test_retry_exhausted_network_error(self, mock_sleep, mock_request, mock_post):
        """Should raise ZoomAPIError after max retries on network error"""
        # Mock OAuth
        mock_post.return_value = Mock(
            status_code=200, json=lambda: {"access_token": "token", "expires_in": 3600}
        )

        # Mock API: always ConnectionError
        mock_request.side_effect = requests.exceptions.ConnectionError("Connection failed")

        client = ZoomClient("acc", "cli", "sec")

        with pytest.raises(ZoomAPIError, match="Network request failed after retries"):
            client._make_request("GET", "meetings/123", retry_count=3)

        assert mock_request.call_count == 3


class TestTokenCaching:
    """Test OAuth token caching"""

    @patch("requests.post")
    def test_token_cached(self, mock_post):
        """Token should be cached and reused"""
        mock_post.return_value = Mock(
            status_code=200, json=lambda: {"access_token": "token123", "expires_in": 3600}
        )

        client = ZoomClient("acc", "cli", "sec")

        # First call - should request token
        token1 = client._get_access_token()
        assert token1 == "token123"
        assert mock_post.call_count == 1

        # Second call - should use cached token
        token2 = client._get_access_token()
        assert token2 == "token123"
        assert mock_post.call_count == 1  # No additional request

    @patch("requests.post")
    @patch("time.time")
    def test_token_refresh_when_expired(self, mock_time, mock_post):
        """Token should be refreshed when expired"""
        # Different tokens for each request
        mock_post.side_effect = [
            Mock(status_code=200, json=lambda: {"access_token": "token1", "expires_in": 3600}),
            Mock(status_code=200, json=lambda: {"access_token": "token2", "expires_in": 3600}),
        ]

        # Mock time progression
        mock_time.side_effect = [
            1000.0,  # First _get_access_token() call - current time
            5000.0,  # Second _get_access_token() call - expired (5000 > 4600-60=4540)
        ]

        client = ZoomClient("acc", "cli", "sec")

        # First call - gets token1
        token1 = client._get_access_token()
        assert token1 == "token1"

        # Second call (expired) - should refresh and get token2
        token2 = client._get_access_token()
        assert token2 == "token2"

        # Should have called OAuth twice
        assert mock_post.call_count == 2


class TestUUIDEncoding:
    """Test UUID double encoding"""

    def test_encode_uuid_simple(self):
        """Simple UUID should be double encoded"""
        result = ZoomClient.encode_uuid("abc123")
        # First encode: abc123 -> abc123 (no special chars)
        # Second encode: abc123 -> abc123
        assert result == "abc123"

    def test_encode_uuid_with_special_chars(self):
        """UUID with special characters should be double encoded"""
        result = ZoomClient.encode_uuid("abc+123/xyz=")
        # First encode: + -> %2B, / -> %2F, = -> %3D
        # Second encode: % -> %25
        assert "%252B" in result or "%2B" in result  # Depends on safe parameter


class TestGetMeetingRecordingsEndpointEncoding:
    @patch.object(ZoomClient, "_make_request")
    def test_numeric_meeting_id_not_encoded(self, mock_make_request):
        client = ZoomClient("acc", "cli", "sec")
        mock_make_request.return_value = {"ok": True}

        client.get_meeting_recordings("88290609309")

        # Ensure endpoint not encoded for numeric IDs
        args, kwargs = mock_make_request.call_args
        assert args[0] == "GET"
        assert args[1].endswith("meetings/88290609309/recordings")

    @patch.object(ZoomClient, "_make_request")
    def test_uuid_meeting_id_is_double_encoded(self, mock_make_request):
        client = ZoomClient("acc", "cli", "sec")
        mock_make_request.return_value = {"ok": True}

        uuid = "/abc+123/xyz="
        client.get_meeting_recordings(uuid)

        args, kwargs = mock_make_request.call_args
        endpoint = args[1]
        # Expect double-encoded within the ID segment: "/" -> %252F, "+" -> %252B, "=" -> %253D
        assert endpoint.startswith("meetings/") and endpoint.endswith("/recordings")
        encoded_id = endpoint[len("meetings/") : -len("/recordings")]
        # No raw slashes inside the encoded ID segment
        assert "/" not in encoded_id
        assert "%252F" in encoded_id
        assert "%252B" in encoded_id
        assert "%253D" in encoded_id
