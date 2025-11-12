import json
from click.testing import CliRunner

from dlzoom.cli import cli as dlzoom_cli


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
        pass

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


def test_recordings_user_wide_json(monkeypatch):
    # Ensure S2S is not used
    monkeypatch.delenv("ZOOM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_SECRET", raising=False)

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
    # Two meetings across two pages; recurring should be true by heuristic
    assert data["total_count"] == 2
    assert all(r.get("recurring") is True for r in data["recordings"])


def test_recordings_meeting_scoped_json(monkeypatch):
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


def test_recordings_mutual_exclusivity_error(monkeypatch):
    # Tokens to avoid auth error
    monkeypatch.delenv("ZOOM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_SECRET", raising=False)
    monkeypatch.setattr("dlzoom.cli.load_tokens", lambda path: object())
    monkeypatch.setattr("dlzoom.cli.ZoomUserClient", FakeUserClient)

    runner = CliRunner()
    result = runner.invoke(
        dlzoom_cli,
        ["recordings", "--meeting-id", "123456789", "--range", "today"],
    )
    assert result.exit_code != 0
    assert "cannot be used with" in result.output


def test_recordings_invalid_date_rejected(monkeypatch):
    monkeypatch.delenv("ZOOM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_SECRET", raising=False)
    monkeypatch.setattr("dlzoom.cli.load_tokens", lambda path: object())
    monkeypatch.setattr("dlzoom.cli.ZoomUserClient", FakeUserClient)

    runner = CliRunner()
    result = runner.invoke(
        dlzoom_cli, ["recordings", "--from-date", "2025-13-01", "--to-date", "2025-01-02"]
    )
    assert result.exit_code != 0
    assert "YYYY-MM-DD" in result.output or "Invalid date" in result.output


def test_recordings_from_gt_to_error(monkeypatch):
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


def test_recordings_limit_zero_fetches_all(monkeypatch):
    monkeypatch.delenv("ZOOM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_SECRET", raising=False)
    monkeypatch.setattr("dlzoom.cli.load_tokens", lambda path: object())
    monkeypatch.setattr("dlzoom.cli.ZoomUserClient", FakeUserClient)

    runner = CliRunner()
    result = runner.invoke(dlzoom_cli, ["recordings", "--range", "today", "--limit", "0", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["total_count"] == 2


def test_recordings_empty_results(monkeypatch):
    class EmptyClient(FakeUserClient):
        def get_user_recordings(self, *a, **k):
            return {"meetings": []}

    monkeypatch.delenv("ZOOM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_ID", raising=False)
    monkeypatch.delenv("ZOOM_CLIENT_SECRET", raising=False)
    monkeypatch.setattr("dlzoom.cli.load_tokens", lambda path: object())
    monkeypatch.setattr("dlzoom.cli.ZoomUserClient", EmptyClient)

    runner = CliRunner()
    result = runner.invoke(dlzoom_cli, ["recordings", "--range", "today", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["total_count"] == 0
