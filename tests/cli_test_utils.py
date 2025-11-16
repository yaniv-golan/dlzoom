import re
from pathlib import Path


class DummyConfig:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.zoom_account_id = None
        self.zoom_client_id = None
        self.zoom_client_secret = None
        self.tokens_path = output_dir / "tokens.json"
        self.zoom_api_base_url = "https://api.zoom.us/v2"
        self.zoom_oauth_token_url = None
        self.s2s_default_user = None
        self.auth_url = ""


class DummyUserClient:
    def __init__(self, tokens, tokens_path):
        self.base_url = None


def setup_user_cli(monkeypatch, tmp_path: Path) -> None:
    """Prepare CLI environment to use stubbed user client/config."""
    monkeypatch.setenv("DLZOOM_NO_DOTENV", "1")
    monkeypatch.delenv("ZOOM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_SECRET", raising=False)

    monkeypatch.setattr("dlzoom.cli.load_tokens", lambda path: object())
    monkeypatch.setattr("dlzoom.cli.ZoomUserClient", DummyUserClient)
    monkeypatch.setattr("dlzoom.cli.Config", lambda *args, **kwargs: DummyConfig(tmp_path))


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    """Utility for tests to assert on CLI output irrespective of color codes."""
    return _ANSI_RE.sub("", text)
