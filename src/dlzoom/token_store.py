"""
Token storage utilities for dlzoom user OAuth.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VERSION = 1


@dataclass
class Tokens:
    token_type: str
    access_token: str
    refresh_token: str
    expires_at: int
    issued_at: int
    scope: str | None
    auth_url: str

    @property
    def is_expired(self) -> bool:
        # Treat as expired if within 120s buffer
        return int(time.time()) >= (int(self.expires_at) - 120)


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def exists(path: Path) -> bool:
    return path.exists()


def load(path: Path) -> Tokens | None:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # Minimal validation
    if data.get("version") != VERSION:
        # Allow forward compatibility if keys exist
        pass
    return Tokens(
        token_type=str(data.get("token_type", "Bearer")),
        access_token=str(data["access_token"]),
        refresh_token=str(data["refresh_token"]),
        expires_at=int(data["expires_at"]),
        issued_at=int(data.get("issued_at", int(time.time()))),
        scope=data.get("scope"),
        auth_url=str(data["auth_url"]),
    )


def save(path: Path, tokens: Tokens) -> None:
    _ensure_dir(path)
    payload: dict[str, Any] = {
        "version": VERSION,
        "token_type": tokens.token_type,
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "expires_at": int(tokens.expires_at),
        "issued_at": int(tokens.issued_at),
        "scope": tokens.scope,
        "auth_url": tokens.auth_url,
    }

    # Atomic write
    tmp_fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, text=True)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp:
            json.dump(payload, tmp, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except Exception:
            pass

    # Permissions: 0600 best effort
    try:
        os.chmod(path, 0o600)
    except Exception:
        # Ignore on platforms that don't support chmod as expected
        pass


def clear(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
