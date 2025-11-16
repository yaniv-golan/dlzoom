"""
Zoom API Client using user OAuth tokens obtained via the hosted auth service.
Handles proactive refresh via the auth service before expiry and reactive refresh on 401.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, cast

import requests

from dlzoom.token_store import Tokens
from dlzoom.token_store import save as save_tokens


class ZoomUserClient:
    def __init__(
        self,
        tokens: Tokens,
        tokens_path: str | None = None,
        *,
        base_url: str = "https://api.zoom.us/v2",
    ):
        self.base_url = base_url.rstrip("/")
        self._tokens: Tokens = tokens
        self._tokens_path: str | None = tokens_path
        # In-process simple lock for refresh single-flight
        from threading import Lock

        self._refresh_lock = Lock()

    def _maybe_refresh(self) -> None:
        if not self._tokens.is_expired:
            return
        # Ensure only one refresh at a time
        with self._refresh_lock:
            if not self._tokens.is_expired:
                return
            self._refresh_tokens()

    def _get_access_token(self) -> str:
        """Provide current access token (refresh if needed) for downloader compatibility."""
        self._maybe_refresh()
        return str(self._tokens.access_token)

    def _refresh_tokens(self) -> None:
        url = f"{self._tokens.auth_url.rstrip('/')}/zoom/token/refresh"
        try:
            r = requests.post(
                url,
                json={"refresh_token": self._tokens.refresh_token},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            raise ZoomUserAPIError(f"Failed to refresh token: {e}") from e

        # Zoom may rotate refresh tokens
        new_access = str(data.get("access_token"))
        new_refresh = str(data.get("refresh_token", self._tokens.refresh_token))
        token_type = str(data.get("token_type", self._tokens.token_type))
        expires_in = int(data.get("expires_in", 3600))
        now = int(time.time())

        self._tokens = Tokens(
            token_type=token_type,
            access_token=new_access,
            refresh_token=new_refresh,
            expires_at=now + expires_in,
            issued_at=now,
            scope=data.get("scope"),
            auth_url=self._tokens.auth_url,
        )
        # Persist if path known
        try:
            if self._tokens_path:
                save_tokens(Path(self._tokens_path), self._tokens)
        except Exception as e:
            # Non-fatal, but log warning
            import logging

            logging.warning(
                f"Failed to persist refreshed tokens to {self._tokens_path}: {e}. "
                "You may need to re-authenticate sooner than expected."
            )

    def _auth_headers(self, include_content_type: bool = False) -> dict[str, str]:
        """
        Build authentication headers.

        Args:
            include_content_type: Only set Content-Type for methods with body (POST, PUT, PATCH)
        """
        from dlzoom import __version__

        headers = {
            "Authorization": f"Bearer {self._tokens.access_token}",
            "User-Agent": f"dlzoom/{__version__} (https://github.com/yaniv-golan/dlzoom)",
            "Accept": "application/json",
        }
        if include_content_type:
            headers["Content-Type"] = "application/json"
        return headers

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        retry_on_401: bool = True,
        retry_count: int = 3,
        backoff_factor: float = 1.0,
    ) -> dict[str, Any]:
        self._maybe_refresh()
        url = f"{self.base_url}/{endpoint}"
        logging.debug(
            "Zoom API request: %s %s params=%s",
            method,
            url,
            {k: v for k, v in (params or {}).items()},
        )
        # Only include Content-Type for methods with body
        include_content_type = method.upper() in ("POST", "PUT", "PATCH")

        for attempt in range(retry_count):
            try:
                resp = requests.request(
                    method,
                    url,
                    headers=self._auth_headers(include_content_type=include_content_type),
                    params=params,
                    timeout=30,
                )
                logging.debug("Zoom API response: HTTP %s", resp.status_code)

                # Handle rate limiting and server errors with exponential backoff
                if resp.status_code in (429, 500, 502, 503, 504):
                    if attempt < retry_count - 1:
                        wait_time = backoff_factor * (2**attempt)
                        status_name = "Rate limit" if resp.status_code == 429 else "Server error"
                        logging.warning(
                            f"{status_name} (HTTP {resp.status_code}), retrying in {wait_time}s "
                            f"(attempt {attempt + 1}/{retry_count})"
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        if resp.status_code == 429:
                            raise ZoomUserAPIError("Rate limit exceeded")
                        raise ZoomUserAPIError(
                            f"Server error (HTTP {resp.status_code}) after {retry_count} retries"
                        )

                if resp.status_code == 401 and retry_on_401:
                    logging.info("Access token expired, attempting refresh...")
                    self._refresh_tokens()
                    resp = requests.request(
                        method,
                        url,
                        headers=self._auth_headers(include_content_type=include_content_type),
                        params=params,
                        timeout=30,
                    )
                    logging.debug("Zoom API response after refresh: HTTP %s", resp.status_code)
                resp.raise_for_status()
                data = cast(dict[str, Any], resp.json())
                logging.debug(
                    "Zoom API ok: keys=%s",
                    (list(data.keys()) if isinstance(data, dict) else type(data).__name__),
                )
                return data
            except requests.exceptions.HTTPError as e:
                raise ZoomUserAPIError(f"Zoom API error: {e}") from e
            except Exception as e:
                # Network errors: try again with backoff if attempts remain
                if attempt < retry_count - 1:
                    wait_time = backoff_factor * (2**attempt)
                    logging.warning(
                        f"Network error ({type(e).__name__}), retrying in {wait_time}s "
                        f"(attempt {attempt + 1}/{retry_count})"
                    )
                    time.sleep(wait_time)
                    continue
                raise ZoomUserAPIError(f"Network error: {e}") from e
        raise ZoomUserAPIError("Max retries exceeded")

    # Public API (mirror subset used by CLI)
    @staticmethod
    def encode_uuid(uuid: str) -> str:
        import urllib.parse

        return urllib.parse.quote(urllib.parse.quote(uuid, safe=""), safe="")

    def get_meeting_recordings(self, meeting_id: str) -> dict[str, Any]:
        if not str(meeting_id).isdigit():
            encoded_id = self.encode_uuid(meeting_id)
            endpoint = f"meetings/{encoded_id}/recordings"
        else:
            endpoint = f"meetings/{meeting_id}/recordings"
        return self._request("GET", endpoint)

    def get_user_recordings(
        self,
        user_id: str = "me",
        from_date: str | None = None,
        to_date: str | None = None,
        page_size: int = 300,
        next_page_token: str | None = None,
    ) -> dict[str, Any]:
        endpoint = f"users/{user_id}/recordings"
        params: dict[str, Any] = {"page_size": page_size}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        if next_page_token:
            params["next_page_token"] = next_page_token
        return self._request("GET", endpoint, params=params)

    def get_current_user(self) -> dict[str, Any]:
        """Get the current Zoom user using user OAuth tokens."""
        endpoint = "users/me"
        return self._request("GET", endpoint)

    def get_past_meeting(self, uuid: str) -> dict[str, Any]:
        encoded_uuid = self.encode_uuid(uuid)
        endpoint = f"past_meetings/{encoded_uuid}"
        return self._request("GET", endpoint)

    def get_past_meeting_participants(
        self, uuid: str, page_size: int = 300, next_page_token: str | None = None
    ) -> dict[str, Any]:
        encoded_uuid = self.encode_uuid(uuid)
        endpoint = f"past_meetings/{encoded_uuid}/participants"
        params: dict[str, Any] = {"page_size": page_size}
        if next_page_token:
            params["next_page_token"] = next_page_token
        return self._request("GET", endpoint, params=params)

    def get_meeting(self, meeting_id: str) -> dict[str, Any]:
        """Get meeting details (requires meeting:read scope)."""
        endpoint = f"meetings/{meeting_id}"
        return self._request("GET", endpoint)


class ZoomUserAPIError(Exception):
    pass
