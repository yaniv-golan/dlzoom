"""
Zoom API Client with Server-to-Server OAuth authentication
"""

import base64
import logging
import time
import urllib.parse
from typing import Any

import requests

from dlzoom.exceptions import (
    AuthenticationError,
    MeetingNotFoundError,
    PermissionDeniedError,
    RateLimitedError,
    RecordingNotFoundError,
)


class ZoomClient:
    """Client for Zoom API with Server-to-Server OAuth and token caching"""

    def __init__(self, account_id: str, client_id: str, client_secret: str):
        self.account_id = account_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://api.zoom.us/v2"
        self.token_url = "https://zoom.us/oauth/token"

        # Token caching (in memory during execution)
        self._access_token: str | None = None
        self._token_expires_at: float = 0

    def __repr__(self) -> str:
        """
        String representation that excludes credentials

        Prevents accidental credential exposure in logs, tracebacks, and debugging
        """
        return (
            f"ZoomClient("
            f"base_url={self.base_url!r}, "
            f"account_id_set={bool(self.account_id)}, "
            f"client_id_set={bool(self.client_id)}, "
            f"token_cached={bool(self._access_token)}"
            f")"
        )

    def __del__(self) -> None:
        """Zero out sensitive credentials when object is destroyed"""
        if hasattr(self, "account_id"):
            self.account_id = ""
        if hasattr(self, "client_id"):
            self.client_id = ""
        if hasattr(self, "client_secret"):
            self.client_secret = ""
        if hasattr(self, "_access_token"):
            self._access_token = None

    def _get_access_token(self) -> str:
        """Get access token with caching (refresh only when expired)"""
        current_time = time.time()

        # Return cached token if still valid (with 60s buffer)
        if self._access_token and current_time < (self._token_expires_at - 60):
            return self._access_token

        # Request new token
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        data = {"grant_type": "account_credentials", "account_id": self.account_id}

        try:
            response = requests.post(
                self.token_url,
                headers=headers,
                data=data,
                timeout=30,  # 30 second timeout
            )
            response.raise_for_status()
        except requests.exceptions.Timeout:
            from dlzoom.exceptions import AuthenticationError

            raise AuthenticationError(
                "Authentication timeout",
                details="Zoom OAuth server did not respond within 30 seconds",
            )

        token_data = response.json()
        self._access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        self._token_expires_at = current_time + expires_in

        return str(self._access_token)

    @staticmethod
    def encode_uuid(uuid: str) -> str:
        """Double URL-encode UUID for past_meetings endpoints"""
        return urllib.parse.quote(urllib.parse.quote(uuid, safe=""), safe="")

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        retry_count: int = 3,
        backoff_factor: float = 1.0,
    ) -> dict[str, Any]:
        """Make authenticated API request with retry logic"""
        url = f"{self.base_url}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
        }

        for attempt in range(retry_count):
            try:
                response = requests.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    timeout=30,  # 30 second timeout
                )

                # Handle rate limiting and server errors with exponential backoff
                if response.status_code in (429, 500, 502, 503, 504):
                    if attempt < retry_count - 1:
                        wait_time = backoff_factor * (2**attempt)
                        status_name = (
                            "Rate limit" if response.status_code == 429 else "Server error"
                        )
                        logging.warning(
                            f"{status_name} (HTTP {response.status_code}), "
                            f"retrying in {wait_time}s (attempt {attempt + 1}/{retry_count})"
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        # Max retries exceeded
                        if response.status_code == 429:
                            raise RateLimitedError(
                                "Rate limit exceeded",
                                details=(
                                    "Too many requests to Zoom API. Please retry after some time."
                                ),
                            )
                        else:
                            raise ZoomAPIError(
                                f"Zoom API server error (HTTP {response.status_code}): "
                                f"Server returned {response.status_code} after "
                                f"{retry_count} retries"
                            )

                response.raise_for_status()
                result: dict[str, Any] = response.json()
                return result

            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.ChunkedEncodingError,
            ) as e:
                # Network errors should be retried with exponential backoff
                if attempt < retry_count - 1:
                    wait_time = backoff_factor * (2**attempt)
                    logging.warning(
                        f"Network error ({type(e).__name__}), "
                        f"retrying in {wait_time}s (attempt {attempt + 1}/{retry_count}): {e}"
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    raise ZoomAPIError(
                        f"Network request failed after retries: {type(e).__name__}: {e}"
                    ) from e

            except requests.exceptions.HTTPError as e:
                # Capture Zoom error codes
                error_data = {}
                try:
                    error_data = e.response.json()
                except Exception:
                    pass

                zoom_code = error_data.get("code")
                zoom_message = error_data.get("message", str(e))
                status_code = e.response.status_code

                # Raise specific exceptions based on status code
                if status_code == 401:
                    raise AuthenticationError(
                        "Authentication failed",
                        details="Check ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, and ZOOM_CLIENT_SECRET",
                    )
                elif status_code == 403:
                    raise PermissionDeniedError(
                        "Permission denied", details="Check OAuth scopes for your Zoom app"
                    )
                elif status_code == 404:
                    # Determine if it's a meeting or recording not found based on endpoint
                    if "meeting" in endpoint and "recording" not in endpoint:
                        raise MeetingNotFoundError(
                            "Meeting not found",
                            details=f"Meeting ID or UUID may be incorrect: {zoom_message}",
                        )
                    else:
                        raise RecordingNotFoundError(
                            "Recording not found",
                            details=f"The meeting may not have been recorded: {zoom_message}",
                        )
                elif status_code == 429:
                    # Should be caught above, but handle here as fallback
                    raise RateLimitedError("Rate limit exceeded", details=zoom_message)
                else:
                    # For other errors, use generic ZoomAPIError
                    raise ZoomAPIError(
                        f"Zoom API error: {zoom_message}",
                        status_code=status_code,
                        zoom_code=zoom_code,
                        details=error_data,
                    )

        raise ZoomAPIError("Max retries exceeded")

    def get_meeting_recordings(self, meeting_id: str) -> dict[str, Any]:
        """Get recording info for a meeting (handles both ID and UUID)"""
        # Try as meeting ID first, then as UUID if needed
        endpoint = f"meetings/{meeting_id}/recordings"
        return self._make_request("GET", endpoint)

    def get_past_meeting(self, uuid: str) -> dict[str, Any]:
        """Get past meeting details (requires double-encoded UUID)"""
        encoded_uuid = self.encode_uuid(uuid)
        endpoint = f"past_meetings/{encoded_uuid}"
        return self._make_request("GET", endpoint)

    def get_past_meeting_participants(
        self, uuid: str, page_size: int = 300, next_page_token: str | None = None
    ) -> dict[str, Any]:
        """Get participants for past meeting with pagination"""
        encoded_uuid = self.encode_uuid(uuid)
        endpoint = f"past_meetings/{encoded_uuid}/participants"

        params: dict[str, Any] = {"page_size": page_size}
        if next_page_token:
            params["next_page_token"] = next_page_token

        return self._make_request("GET", endpoint, params=params)

    def get_all_participants(self, uuid: str) -> list[dict[str, Any]]:
        """Get all participants with automatic pagination"""
        all_participants = []
        next_token = None
        first_page = True

        while True:
            response = self.get_past_meeting_participants(
                uuid, page_size=300, next_page_token=next_token
            )
            participants = response.get("participants", [])
            all_participants.extend(participants)

            # Pagination bug detection
            if first_page and len(participants) == 30 and not response.get("next_page_token"):
                import logging

                logging.warning(
                    "Possible Zoom pagination bug detected: "
                    f"Only 30 results returned with page_size=300 and no next_page_token. "
                    "Participant count may be incomplete. "
                    "This is a known Zoom API bug. "
                    "Consider using page_size=30 explicitly or implementing fallback pagination. "
                    f"Current participant count: {len(participants)}"
                )

            first_page = False
            next_token = response.get("next_page_token")
            if not next_token:
                break

        return all_participants

    def get_user_recordings(
        self,
        user_id: str = "me",
        from_date: str | None = None,
        to_date: str | None = None,
        page_size: int = 300,
        next_page_token: str | None = None,
    ) -> dict[str, Any]:
        """Get user recordings with date filtering"""
        endpoint = f"users/{user_id}/recordings"

        params: dict[str, Any] = {"page_size": page_size}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        if next_page_token:
            params["next_page_token"] = next_page_token

        return self._make_request("GET", endpoint, params=params)


class ZoomAPIError(Exception):
    """Custom exception for Zoom API errors"""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        zoom_code: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.zoom_code = zoom_code
        self.details = details or {}
