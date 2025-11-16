import pytest

from dlzoom.exceptions import ConfigError
from dlzoom.handlers import _raise_account_scope_error
from dlzoom.zoom_client import ZoomAPIError


def test_account_scope_error_includes_troubleshooting():
    exc = ZoomAPIError("Forbidden", status_code=403, zoom_code=4711)
    with pytest.raises(ConfigError) as err:
        _raise_account_scope_error(exc)

    assert "account:read:admin" in err.value.message
    assert "cloud_recording:read:list_account_recordings" in err.value.message
    assert "General app" in err.value.details
