from collections import deque

from dlzoom.handlers import _iterate_account_recordings, _iterate_user_recordings


class StubAccountClient:
    def __init__(self, responses):
        self.responses = deque(responses)
        self.calls = []

    def get_account_recordings(
        self,
        *,
        from_date=None,
        to_date=None,
        page_size=300,
        next_page_token=None,
    ):
        self.calls.append(
            {
                "from": from_date,
                "to": to_date,
                "page_size": page_size,
                "next_page_token": next_page_token,
            }
        )
        return self.responses.popleft()


class StubUserClient:
    def __init__(self, responses):
        self.responses = deque(responses)
        self.calls = []

    def get_user_recordings(
        self,
        *,
        user_id,
        from_date=None,
        to_date=None,
        page_size=300,
        next_page_token=None,
    ):
        self.calls.append(
            {
                "user_id": user_id,
                "from": from_date,
                "to": to_date,
                "page_size": page_size,
                "next_page_token": next_page_token,
            }
        )
        return self.responses.popleft()


def test_account_iteration_handles_pagination():
    responses = [
        {"meetings": [{"uuid": "A"}], "next_page_token": "NEXT"},
        {"meetings": [{"uuid": "B"}]},
    ]
    client = StubAccountClient(responses)

    meetings = list(
        _iterate_account_recordings(
            client,
            from_date="2024-01-01",
            to_date="2024-01-10",
            page_size=200,
            debug=False,
        )
    )

    assert [m["uuid"] for m in meetings] == ["A", "B"]
    assert client.calls[0]["next_page_token"] is None
    assert client.calls[1]["next_page_token"] == "NEXT"


def test_account_iteration_chunks_months():
    responses = [
        {"meetings": [{"uuid": "JAN"}]},
        {"meetings": [{"uuid": "FEB"}]},
    ]
    client = StubAccountClient(responses)

    meetings = list(
        _iterate_account_recordings(
            client,
            from_date="2024-01-30",
            to_date="2024-02-02",
            page_size=300,
        )
    )

    assert [m["uuid"] for m in meetings] == ["JAN", "FEB"]
    assert client.calls[0]["from"] == "2024-01-30"
    assert client.calls[0]["to"] == "2024-01-31"
    assert client.calls[1]["from"] == "2024-02-01"
    assert client.calls[1]["to"] == "2024-02-02"


def test_account_iteration_resets_tokens_per_chunk():
    responses = [
        {"meetings": [{"uuid": "JAN-1"}], "next_page_token": "JAN-TOKEN"},
        {"meetings": [{"uuid": "JAN-2"}]},
        {"meetings": [{"uuid": "FEB-1"}]},
    ]
    client = StubAccountClient(responses)

    meetings = list(
        _iterate_account_recordings(
            client,
            from_date="2024-01-30",
            to_date="2024-02-02",
            page_size=100,
        )
    )

    assert [m["uuid"] for m in meetings] == ["JAN-1", "JAN-2", "FEB-1"]
    assert client.calls[0]["next_page_token"] is None
    assert client.calls[1]["next_page_token"] == "JAN-TOKEN"
    assert client.calls[2]["next_page_token"] is None  # new chunk resets pagination


def test_user_iteration_passes_user_id():
    responses = [
        {"meetings": [{"uuid": "U1"}]},
    ]
    client = StubUserClient(responses)

    meetings = list(
        _iterate_user_recordings(
            client,
            user_id="user@example.com",
            from_date="2024-03-01",
            to_date="2024-03-05",
            page_size=150,
        )
    )

    assert meetings[0]["uuid"] == "U1"
    assert client.calls[0]["user_id"] == "user@example.com"
    assert client.calls[0]["page_size"] == 150
