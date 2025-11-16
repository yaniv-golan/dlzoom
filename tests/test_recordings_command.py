import json

from click.testing import CliRunner

from dlzoom.cli import cli as dlzoom_cli


def _prep_user_tokens(monkeypatch, tmp_path):
    tokens_file = tmp_path / "tokens.json"
    tokens_file.write_text("{}")
    monkeypatch.setenv("DLZOOM_TOKENS_PATH", str(tokens_file))


class FakeUserClient:
    def __init__(self, tokens, tokens_path):
        pass

    def get_user_recordings(
        self,
        user_id: str = "me",
        from_date: str | None = None,
        to_date: str | None = None,
        page_size: int = 300,
        next_page_token: str | None = None,
    ):
        # Simulate two pages when no token, then stop
        if next_page_token is None:
            return {
                "meetings": [
                    {
                        "id": "123456789",
                        "uuid": "AAA+BBB/CCC==",
                        "topic": "Weekly Standup",
                        "start_time": "2025-01-15T10:00:00Z",
                        "duration": 30,
                        "recording_files": [{"recording_type": "MP4"}],
                    }
                ],
                "next_page_token": "PAGE2",
            }
        elif next_page_token == "PAGE2":
            return {
                "meetings": [
                    {
                        "id": "123456789",
                        "uuid": "DDD+EEE/FFF==",
                        "topic": "Weekly Standup",
                        "start_time": "2025-01-22T10:00:00Z",
                        "duration": 30,
                        "recording_files": [
                            {"recording_type": "MP4"},
                            {"recording_type": "M4A"},
                        ],
                    }
                ]
            }
        return {"meetings": []}

    def get_meeting(self, meeting_id: str):
        # Simulate absence of meeting:read scope (fallback to heuristic)
        raise Exception("permission denied")


class FakeS2SClient:
    def __init__(self, account_id: str, client_id: str, client_secret: str):
        self.account_id = account_id

    def get_meeting_recordings(self, meeting_id: str):
        # Simulate a meeting with two instances
        return {
            "meetings": [
                {
                    "uuid": "X1",
                    "topic": "Demo",
                    "start_time": "2025-01-10T09:00:00Z",
                    "duration": 45,
                    "recording_files": [{"recording_type": "MP4"}],
                },
                {
                    "uuid": "X2",
                    "topic": "Demo",
                    "start_time": "2025-01-11T09:00:00Z",
                    "duration": 45,
                    "recording_files": [{"recording_type": "MP4"}, {"recording_type": "M4A"}],
                },
            ]
        }

    def get_account_recordings(
        self,
        *,
        from_date=None,
        to_date=None,
        page_size=300,
        next_page_token=None,
    ):
        return {
            "meetings": [
                {
                    "id": "999000111",
                    "uuid": "ACCT123",
                    "topic": "Account Sync",
                    "start_time": "2025-02-01T12:00:00Z",
                    "duration": 60,
                    "recording_files": [{"recording_type": "MP4"}],
                }
            ]
        }


def test_recordings_user_wide_json(monkeypatch, tmp_path):
    # Disable .env autoload for test isolation
    monkeypatch.setenv("DLZOOM_NO_DOTENV", "1")
    # Ensure S2S is not used
    monkeypatch.delenv("ZOOM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_SECRET", raising=False)

    monkeypatch.setattr("dlzoom.config.user_config_dir", lambda _: str(tmp_path))
    _prep_user_tokens(monkeypatch, tmp_path)
    # Patch token loader to pretend we have user tokens
    monkeypatch.setattr("dlzoom.cli.load_tokens", lambda path: object())
    # Patch client to use fake
    monkeypatch.setattr("dlzoom.cli.ZoomUserClient", FakeUserClient)

    runner = CliRunner()
    result = runner.invoke(dlzoom_cli, ["recordings", "--range", "today", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["status"] == "success"
    assert data["command"] == "recordings"
    assert data["scope"] == "user"
    assert data["user_id"] == "me"
    assert data["total_meetings"] == 2
    assert all(r.get("recurring") is True for r in data["meetings"])


def test_recordings_account_scope_json(monkeypatch):
    monkeypatch.setenv("DLZOOM_NO_DOTENV", "1")
    monkeypatch.setenv("ZOOM_ACCOUNT_ID", "acct")
    monkeypatch.setenv("ZOOM_CLIENT_ID", "cid")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "sec")
    monkeypatch.setattr("dlzoom.cli.ZoomClient", FakeS2SClient)

    runner = CliRunner()
    result = runner.invoke(
        dlzoom_cli, ["recordings", "--from-date", "2025-02-01", "--to-date", "2025-02-02", "--json"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["scope"] == "account"
    assert data["account_id"] == "acct"
    assert data["total_meetings"] == 1
    assert data["meetings"][0]["topic"] == "Account Sync"


def test_recordings_meeting_scoped_json(monkeypatch):
    # Disable .env autoload for test isolation
    monkeypatch.setenv("DLZOOM_NO_DOTENV", "1")
    # Make S2S present via env so CLI chooses S2S
    monkeypatch.setenv("ZOOM_ACCOUNT_ID", "acct")
    monkeypatch.setenv("ZOOM_CLIENT_ID", "cid")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "sec")

    monkeypatch.setattr("dlzoom.cli.ZoomClient", FakeS2SClient)

    runner = CliRunner()
    result = runner.invoke(dlzoom_cli, ["recordings", "--meeting-id", "123456789", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["status"] == "success"
    assert data["command"] == "recordings-instances"
    assert data["meeting_id"] == "123456789"
    assert data["total_instances"] == 2


def test_recordings_mutual_exclusivity_error(monkeypatch, tmp_path):
    # Disable .env autoload for test isolation
    monkeypatch.setenv("DLZOOM_NO_DOTENV", "1")
    # Tokens to avoid auth error
    monkeypatch.delenv("ZOOM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_SECRET", raising=False)
    monkeypatch.setattr("dlzoom.config.user_config_dir", lambda _: str(tmp_path))
    _prep_user_tokens(monkeypatch, tmp_path)
    monkeypatch.setattr("dlzoom.cli.load_tokens", lambda path: object())
    monkeypatch.setattr("dlzoom.cli.ZoomUserClient", FakeUserClient)

    runner = CliRunner()
    result = runner.invoke(
        dlzoom_cli,
        ["recordings", "--meeting-id", "123456789", "--range", "today"],
    )
    assert result.exit_code != 0
    assert "cannot be used with" in result.output


def test_recordings_invalid_date_rejected(monkeypatch, tmp_path):
    # Disable .env autoload for test isolation
    monkeypatch.setenv("DLZOOM_NO_DOTENV", "1")
    monkeypatch.delenv("ZOOM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_SECRET", raising=False)
    monkeypatch.setattr("dlzoom.config.user_config_dir", lambda _: str(tmp_path))
    _prep_user_tokens(monkeypatch, tmp_path)
    monkeypatch.setattr("dlzoom.cli.load_tokens", lambda path: object())
    monkeypatch.setattr("dlzoom.cli.ZoomUserClient", FakeUserClient)

    runner = CliRunner()
    result = runner.invoke(
        dlzoom_cli, ["recordings", "--from-date", "2025-13-01", "--to-date", "2025-01-02"]
    )
    assert result.exit_code != 0
    assert "YYYY-MM-DD" in result.output or "Invalid date" in result.output


def test_recordings_from_gt_to_error(monkeypatch):
    # Disable .env autoload for test isolation
    monkeypatch.setenv("DLZOOM_NO_DOTENV", "1")
    monkeypatch.delenv("ZOOM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_SECRET", raising=False)
    monkeypatch.setattr("dlzoom.cli.load_tokens", lambda path: object())
    monkeypatch.setattr("dlzoom.cli.ZoomUserClient", FakeUserClient)

    runner = CliRunner()
    result = runner.invoke(
        dlzoom_cli, ["recordings", "--from-date", "2025-01-03", "--to-date", "2025-01-01"]
    )
    assert result.exit_code != 0
    assert "before or equal" in result.output


def test_recordings_limit_zero_fetches_all(monkeypatch, tmp_path):
    # Disable .env autoload for test isolation
    monkeypatch.setenv("DLZOOM_NO_DOTENV", "1")
    monkeypatch.delenv("ZOOM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_SECRET", raising=False)
    _prep_user_tokens(monkeypatch, tmp_path)
    monkeypatch.setattr("dlzoom.config.user_config_dir", lambda _: str(tmp_path))
    monkeypatch.setattr("dlzoom.cli.load_tokens", lambda path: object())
    monkeypatch.setattr("dlzoom.cli.ZoomUserClient", FakeUserClient)

    runner = CliRunner()
    result = runner.invoke(dlzoom_cli, ["recordings", "--range", "today", "--limit", "0", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["total_meetings"] == 2


def test_recordings_empty_results(monkeypatch, tmp_path):
    class EmptyClient(FakeUserClient):
        def get_user_recordings(self, *a, **k):
            return {"meetings": []}

    # Disable .env autoload for test isolation
    monkeypatch.setenv("DLZOOM_NO_DOTENV", "1")
    monkeypatch.delenv("ZOOM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_SECRET", raising=False)
    monkeypatch.setattr("dlzoom.config.user_config_dir", lambda _: str(tmp_path))
    _prep_user_tokens(monkeypatch, tmp_path)
    monkeypatch.setattr("dlzoom.cli.load_tokens", lambda path: object())
    monkeypatch.setattr("dlzoom.cli.ZoomUserClient", EmptyClient)

    runner = CliRunner()
    result = runner.invoke(dlzoom_cli, ["recordings", "--range", "today", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["total_meetings"] == 0
