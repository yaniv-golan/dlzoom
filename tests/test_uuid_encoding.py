from dlzoom.zoom_client import ZoomClient
from dlzoom.zoom_user_client import ZoomUserClient


def test_zoom_user_client_double_encoding_matches_zoom_client():
    uuid = "abc/def+ghi="
    user_encoded = ZoomUserClient.encode_uuid(uuid)
    server_encoded = ZoomClient.encode_uuid(uuid)
    assert user_encoded == server_encoded
    assert "%252F" in user_encoded  # double-encoded slash


def test_zoom_user_client_encode_uuid_no_special_chars():
    uuid = "plainUUID"
    assert ZoomUserClient.encode_uuid(uuid) == "plainUUID"
