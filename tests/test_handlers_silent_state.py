from dlzoom.handlers import _handle_check_availability
from dlzoom.output import OutputFormatter
from dlzoom.recorder_selector import RecordingSelector


class _DummyClient:
    def get_meeting_recordings(self, meeting_id: str) -> dict:
        return {
            "meetings": [
                {
                    "uuid": "uuid-123",
                    "recording_files": [
                        {
                            "status": "completed",
                            "file_extension": "M4A",
                            "file_type": "audio_only",
                        }
                    ],
                }
            ]
        }


def test_check_availability_restores_formatter_state():
    formatter = OutputFormatter()
    selector = RecordingSelector()
    client = _DummyClient()

    result = _handle_check_availability(
        client=client,
        selector=selector,
        meeting_id="123456789",
        recording_id=None,
        formatter=formatter,
        wait=None,
        json_mode=False,
        capture_result=True,
    )

    assert result is not None
    assert formatter.silent is False
