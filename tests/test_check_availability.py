import pytest

from dlzoom.exceptions import RecordingNotFoundError
from dlzoom.handlers import _handle_check_availability
from dlzoom.output import OutputFormatter
from dlzoom.recorder_selector import RecordingSelector


class DummyClient:
    def __init__(self, payload):
        self.payload = payload

    def get_meeting_recordings(self, meeting_id):
        return self.payload


def test_check_availability_raises_for_missing_meeting():
    client = DummyClient({})
    selector = RecordingSelector()
    formatter = OutputFormatter("human")

    with pytest.raises(RecordingNotFoundError):
        _handle_check_availability(
            client,
            selector,
            meeting_id="123456789",
            recording_id=None,
            formatter=formatter,
            wait=None,
            json_mode=False,
        )
