import json
from pathlib import Path

from dlzoom.handlers import _handle_batch_download
from dlzoom.recorder_selector import RecordingSelector
from dlzoom.zoom_client import ZoomClient


def test_batch_download_account_scope_includes_metadata(monkeypatch, tmp_path, capsys):
    fake_items = [{"id": "123", "topic": "All Hands", "start_time": "2024-01-10T10:00:00Z"}]

    iter_calls = []

    def fake_iter_account(*args, **kwargs):
        iter_calls.append(kwargs)
        return iter(fake_items)

    downloaded = []

    def fake_download_mode(**kwargs):
        downloaded.append(kwargs["meeting_id"])

    monkeypatch.setattr("dlzoom.handlers._iterate_account_recordings", fake_iter_account)
    monkeypatch.setattr("dlzoom.handlers._handle_download_mode", fake_download_mode)

    client = ZoomClient("acct", "cid", "sec")
    selector = RecordingSelector()

    _handle_batch_download(
        client=client,
        selector=selector,
        from_date="2024-01-01",
        to_date="2024-01-31",
        scope="account",
        user_id=None,
        page_size=300,
        account_id="acct",
        output_dir=Path(tmp_path),
        skip_transcript=False,
        skip_chat=False,
        skip_timeline=False,
        formatter=None,  # not used when json_mode=True
        verbose=False,
        debug=False,
        json_mode=True,
        filename_template=None,
        folder_template=None,
        skip_speakers=None,
        speakers_mode="first",
        stj_min_segment_sec=1.0,
        stj_merge_gap_sec=1.5,
        include_unknown=False,
    )

    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data["scope"] == "account"
    assert data["account_id"] == "acct"
    assert downloaded == ["123"]
    assert data["results"][0]["scope"] == "account"
    assert iter_calls  # ensure account iterator path taken


def test_batch_download_user_scope_sets_user_id(monkeypatch, tmp_path, capsys):
    fake_items = [{"id": "555", "topic": "One-on-one", "start_time": "2024-02-02T09:00:00Z"}]

    def fake_iter_user(*args, **kwargs):
        return iter(fake_items)

    monkeypatch.setattr("dlzoom.handlers._iterate_user_recordings", fake_iter_user)
    monkeypatch.setattr("dlzoom.handlers._handle_download_mode", lambda **kwargs: None)

    class DumbClient:
        pass

    selector = RecordingSelector()

    _handle_batch_download(
        client=DumbClient(),
        selector=selector,
        from_date="2024-02-01",
        to_date="2024-02-10",
        scope="user",
        user_id="user@example.com",
        page_size=100,
        account_id=None,
        output_dir=Path(tmp_path),
        skip_transcript=True,
        skip_chat=True,
        skip_timeline=True,
        formatter=None,
        verbose=False,
        debug=False,
        json_mode=True,
        filename_template=None,
        folder_template=None,
        skip_speakers=None,
        speakers_mode="first",
        stj_min_segment_sec=1.0,
        stj_merge_gap_sec=1.5,
        include_unknown=False,
    )

    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data["scope"] == "user"
    assert data["user_id"] == "user@example.com"
    assert data["results"][0]["user_id"] == "user@example.com"
