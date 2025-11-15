import json
from pathlib import Path

import pytest

from dlzoom.exceptions import DownloadFailedError, RecordingNotFoundError
from dlzoom.handlers import (
    _handle_batch_check_availability,
    _handle_batch_download,
    _handle_download_mode,
)
from dlzoom.output import OutputFormatter
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

    log_path = tmp_path / "batch.log"

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
        log_file=log_path,
    )

    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data["scope"] == "account"
    assert data["account_id"] == "acct"
    assert data["log_file"] == str(log_path.absolute())
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


def test_batch_download_preserves_user_output_name(monkeypatch, tmp_path):
    fake_items = [
        {"id": "777", "topic": "Weekly Sync", "start_time": "2024-03-01T12:00:00Z"},
        {"id": "888", "topic": "Weekly Sync", "start_time": "2024-03-08T12:00:00Z"},
    ]

    monkeypatch.setattr(
        "dlzoom.handlers._iterate_account_recordings", lambda *args, **kwargs: iter(fake_items)
    )

    recorded_output_names: list[str] = []

    def fake_download_mode(**kwargs):
        recorded_output_names.append(kwargs["output_name"])

    monkeypatch.setattr("dlzoom.handlers._handle_download_mode", fake_download_mode)

    client = ZoomClient("acct", "cid", "sec")
    selector = RecordingSelector()

    _handle_batch_download(
        client=client,
        selector=selector,
        from_date="2024-03-01",
        to_date="2024-03-09",
        scope="account",
        user_id=None,
        page_size=300,
        account_id="acct",
        output_dir=Path(tmp_path),
        skip_transcript=False,
        skip_chat=False,
        skip_timeline=False,
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
        base_output_name="custom_name",
        user_supplied_output_name=True,
    )

    assert recorded_output_names == ["custom_name", "custom_name"]


def test_batch_download_generates_timestamped_names(monkeypatch, tmp_path):
    fake_items = [
        {"id": "999", "topic": "Recurring", "start_time": "2024-04-10T09:00:00Z"},
        {"id": "999", "topic": "Recurring", "start_time": "2024-04-11T09:05:00Z"},
    ]

    monkeypatch.setattr(
        "dlzoom.handlers._iterate_account_recordings", lambda *args, **kwargs: iter(fake_items)
    )

    recorded_output_names: list[str] = []

    def fake_download_mode(**kwargs):
        recorded_output_names.append(kwargs["output_name"])

    monkeypatch.setattr("dlzoom.handlers._handle_download_mode", fake_download_mode)

    client = ZoomClient("acct", "cid", "sec")
    selector = RecordingSelector()

    _handle_batch_download(
        client=client,
        selector=selector,
        from_date="2024-04-01",
        to_date="2024-04-30",
        scope="account",
        user_id=None,
        page_size=300,
        account_id="acct",
        output_dir=Path(tmp_path),
        skip_transcript=False,
        skip_chat=False,
        skip_timeline=False,
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
        base_output_name="999",
        user_supplied_output_name=False,
    )

    assert recorded_output_names == ["999_20240411-090500", "999_20240410-090000"]


def test_batch_download_falls_back_to_uuid_when_no_start(monkeypatch, tmp_path):
    fake_items = [
        {"id": "321", "topic": "Ad-hoc", "uuid": "abc/def", "start_time": None},
    ]

    monkeypatch.setattr(
        "dlzoom.handlers._iterate_account_recordings", lambda *args, **kwargs: iter(fake_items)
    )

    recorded_output_names: list[str] = []

    def fake_download_mode(**kwargs):
        recorded_output_names.append(kwargs["output_name"])

    monkeypatch.setattr("dlzoom.handlers._handle_download_mode", fake_download_mode)

    client = ZoomClient("acct", "cid", "sec")
    selector = RecordingSelector()

    _handle_batch_download(
        client=client,
        selector=selector,
        from_date="2024-05-01",
        to_date="2024-05-02",
        scope="account",
        user_id=None,
        page_size=300,
        account_id="acct",
        output_dir=Path(tmp_path),
        skip_transcript=False,
        skip_chat=False,
        skip_timeline=False,
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
        base_output_name="321",
        user_supplied_output_name=False,
    )

    assert recorded_output_names == ["321_abc_def"]


def test_batch_download_respects_dry_run(monkeypatch, tmp_path):
    fake_items = [
        {"id": "1010", "topic": "Preview", "start_time": "2024-06-01T08:00:00Z"},
    ]

    monkeypatch.setattr(
        "dlzoom.handlers._iterate_account_recordings", lambda *args, **kwargs: iter(fake_items)
    )

    called: list[bool] = []

    def fake_download_mode(**kwargs):
        called.append(kwargs["dry_run"])

    monkeypatch.setattr("dlzoom.handlers._handle_download_mode", fake_download_mode)

    client = ZoomClient("acct", "cid", "sec")
    selector = RecordingSelector()

    _handle_batch_download(
        client=client,
        selector=selector,
        from_date="2024-06-01",
        to_date="2024-06-02",
        scope="account",
        user_id=None,
        page_size=300,
        account_id="acct",
        output_dir=Path(tmp_path),
        skip_transcript=False,
        skip_chat=False,
        skip_timeline=False,
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
        base_output_name="1010",
        user_supplied_output_name=False,
        dry_run=True,
    )

    assert called == [True]


def test_batch_download_passes_wait(monkeypatch, tmp_path):
    fake_items = [{"id": "2020", "topic": "Processing", "start_time": "2024-07-01T08:00:00Z"}]

    monkeypatch.setattr(
        "dlzoom.handlers._iterate_account_recordings", lambda *args, **kwargs: iter(fake_items)
    )

    received_wait: list[int | None] = []

    def fake_download_mode(**kwargs):
        received_wait.append(kwargs["wait"])

    monkeypatch.setattr("dlzoom.handlers._handle_download_mode", fake_download_mode)

    client = ZoomClient("acct", "cid", "sec")
    selector = RecordingSelector()

    _handle_batch_download(
        client=client,
        selector=selector,
        from_date="2024-07-01",
        to_date="2024-07-02",
        scope="account",
        user_id=None,
        page_size=300,
        account_id="acct",
        output_dir=Path(tmp_path),
        skip_transcript=False,
        skip_chat=False,
        skip_timeline=False,
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
        base_output_name="2020",
        user_supplied_output_name=False,
        dry_run=False,
        wait=45,
    )

    assert received_wait == [45]


def test_batch_download_writes_log_file(monkeypatch, tmp_path):
    fake_items = [{"id": "3030", "topic": "Audit", "start_time": "2024-08-01T08:00:00Z"}]

    monkeypatch.setattr(
        "dlzoom.handlers._iterate_account_recordings", lambda *args, **kwargs: iter(fake_items)
    )

    emissions: list[Path | None] = []

    def fake_download_mode(**kwargs):
        emissions.append(kwargs["log_file"])

    monkeypatch.setattr("dlzoom.handlers._handle_download_mode", fake_download_mode)

    client = ZoomClient("acct", "cid", "sec")
    selector = RecordingSelector()
    log_path = tmp_path / "logs.jsonl"

    _handle_batch_download(
        client=client,
        selector=selector,
        from_date="2024-08-01",
        to_date="2024-08-02",
        scope="account",
        user_id=None,
        page_size=300,
        account_id="acct",
        output_dir=Path(tmp_path),
        skip_transcript=False,
        skip_chat=False,
        skip_timeline=False,
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
        base_output_name="3030",
        user_supplied_output_name=False,
        dry_run=False,
        wait=None,
        log_file=log_path,
    )

    assert emissions == [log_path]


def test_batch_download_empty_json_includes_log_path(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        "dlzoom.handlers._iterate_account_recordings", lambda *args, **kwargs: iter([])
    )
    client = ZoomClient("acct", "cid", "sec")
    selector = RecordingSelector()
    log_path = tmp_path / "empty.jsonl"

    _handle_batch_download(
        client=client,
        selector=selector,
        from_date="2024-08-05",
        to_date="2024-08-06",
        scope="account",
        user_id=None,
        page_size=300,
        account_id="acct",
        output_dir=Path(tmp_path),
        skip_transcript=False,
        skip_chat=False,
        skip_timeline=False,
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
        log_file=log_path,
    )

    data = json.loads(capsys.readouterr().out)
    assert data["total_meetings"] == 0
    assert data["log_file"] == str(log_path.absolute())


def test_batch_check_availability_json(monkeypatch, capsys):
    fake_items = [
        {"id": "1001", "topic": "Ready", "start_time": "2024-09-01T10:00:00Z"},
        {"id": "1002", "topic": "Processing", "start_time": "2024-09-02T10:00:00Z"},
    ]

    monkeypatch.setattr(
        "dlzoom.handlers._iterate_account_recordings", lambda *args, **kwargs: iter(fake_items)
    )

    def fake_check_availability(
        client,
        selector,
        meeting_id,
        recording_id,
        formatter,
        wait,
        json_mode,
        capture_result=False,
    ):
        assert capture_result is True
        if meeting_id == "1001":
            return {
                "status": "success",
                "command": "check_availability",
                "meeting_id": meeting_id,
                "available": True,
                "recording_status": "completed",
            }
        return {
            "status": "success",
            "command": "check_availability",
            "meeting_id": meeting_id,
            "available": False,
            "recording_status": "processing",
        }

    monkeypatch.setattr("dlzoom.handlers._handle_check_availability", fake_check_availability)

    client = ZoomClient("acct", "cid", "sec")
    selector = RecordingSelector()
    formatter = OutputFormatter("json")

    _handle_batch_check_availability(
        client=client,
        selector=selector,
        from_date="2024-09-01",
        to_date="2024-09-03",
        scope="account",
        user_id=None,
        page_size=300,
        account_id="acct",
        formatter=formatter,
        verbose=False,
        debug=False,
        json_mode=True,
        wait=None,
    )

    data = json.loads(capsys.readouterr().out)
    assert data["command"] == "batch-check-availability"
    assert data["total_meetings"] == 2
    assert data["ready"] == 1
    assert data["processing"] == 1
    assert len(data["results"]) == 2
    assert {res["meeting_id"] for res in data["results"]} == {"1001", "1002"}


def test_batch_check_availability_human(monkeypatch, capsys):
    fake_items = [
        {"id": "2001", "topic": "Ready", "start_time": "2024-09-10T12:00:00Z"},
        {"id": "2002", "topic": "Error", "start_time": "2024-09-11T12:00:00Z"},
    ]

    monkeypatch.setattr(
        "dlzoom.handlers._iterate_account_recordings", lambda *args, **kwargs: iter(fake_items)
    )

    def fake_check_availability(
        client,
        selector,
        meeting_id,
        recording_id,
        formatter,
        wait,
        json_mode,
        capture_result=False,
    ):
        assert capture_result is True
        if meeting_id == "2001":
            return {
                "status": "success",
                "command": "check_availability",
                "meeting_id": meeting_id,
                "available": True,
                "recording_status": "completed",
            }
        return {
            "status": "error",
            "command": "check_availability",
            "meeting_id": meeting_id,
            "error": {"code": "ZOOM_API_ERROR", "message": "boom"},
        }

    monkeypatch.setattr("dlzoom.handlers._handle_check_availability", fake_check_availability)

    client = ZoomClient("acct", "cid", "sec")
    selector = RecordingSelector()
    formatter = OutputFormatter("human")

    _handle_batch_check_availability(
        client=client,
        selector=selector,
        from_date="2024-09-10",
        to_date="2024-09-12",
        scope="account",
        user_id=None,
        page_size=300,
        account_id="acct",
        formatter=formatter,
        verbose=False,
        debug=False,
        json_mode=False,
        wait=None,
    )

    stdout = capsys.readouterr().out
    assert "[2001] status: ready" in stdout
    assert "[2002] boom" in stdout
    assert "Availability check complete" in stdout


def test_download_mode_aborts_when_wait_times_out(monkeypatch, tmp_path):
    called = {}

    def fake_check_availability(
        client,
        selector,
        meeting_id,
        recording_id,
        formatter,
        wait,
        json_mode,
        capture_result=False,
    ):
        called["capture_result"] = capture_result
        return {
            "status": "success",
            "command": "check_availability",
            "meeting_id": meeting_id,
            "available": False,
            "recording_status": "processing",
        }

    monkeypatch.setattr("dlzoom.handlers._handle_check_availability", fake_check_availability)

    class DummyClient:
        def get_meeting_recordings(self, meeting_id):
            raise AssertionError("should not fetch recordings when availability fails")

        def _get_access_token(self):
            return "token"

    formatter = OutputFormatter("human")
    selector = RecordingSelector()

    with pytest.raises(RecordingNotFoundError):
        _handle_download_mode(
            client=DummyClient(),
            selector=selector,
            meeting_id="123456789",
            recording_id=None,
            output_dir=tmp_path,
            output_name="custom",
            skip_transcript=False,
            skip_chat=False,
            skip_timeline=False,
            dry_run=False,
            log_file=None,
            formatter=formatter,
            verbose=False,
            debug=False,
            json_mode=False,
            wait=5,
        )

    assert called.get("capture_result") is True


def test_batch_download_raises_when_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "dlzoom.handlers._iterate_account_recordings",
        lambda *args, **kwargs: iter(
            [
                {"id": "111", "topic": "One", "start_time": "2024-01-01T10:00:00Z"},
                {"id": "222", "topic": "Two", "start_time": "2024-01-02T10:00:00Z"},
            ]
        ),
    )

    call_count = {"count": 0}

    def fake_download_mode(**kwargs):
        call_count["count"] += 1
        if call_count["count"] == 1:
            raise RecordingNotFoundError("missing")

    monkeypatch.setattr("dlzoom.handlers._handle_download_mode", fake_download_mode)

    client = ZoomClient("acct", "id", "secret")
    selector = RecordingSelector()
    formatter = OutputFormatter("human")

    with pytest.raises(DownloadFailedError):
        _handle_batch_download(
            client=client,
            selector=selector,
            from_date="2024-01-01",
            to_date="2024-01-03",
            scope="account",
            user_id=None,
            page_size=300,
            account_id="acct",
            output_dir=tmp_path,
            skip_transcript=False,
            skip_chat=False,
            skip_timeline=False,
            formatter=formatter,
            verbose=False,
            debug=False,
            json_mode=False,
            filename_template=None,
            folder_template=None,
            skip_speakers=None,
            speakers_mode="first",
            stj_min_segment_sec=1.0,
            stj_merge_gap_sec=1.5,
            include_unknown=False,
            base_output_name="base",
            user_supplied_output_name=False,
            dry_run=False,
            wait=None,
            log_file=None,
        )
