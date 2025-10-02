"""
Unit tests for config module
"""

import os
import pytest
from pathlib import Path
from dlzoom.config import Config, ConfigError


def test_config_loads_from_env(monkeypatch):
    """Test that config loads from environment variables"""
    monkeypatch.setenv("ZOOM_ACCOUNT_ID", "test_account")
    monkeypatch.setenv("ZOOM_CLIENT_ID", "test_client")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "test_secret")

    config = Config()
    assert config.zoom_account_id == "test_account"
    assert config.zoom_client_id == "test_client"
    assert config.zoom_client_secret == "test_secret"


def test_config_validation_success(monkeypatch):
    """Test that validation passes with all required vars"""
    monkeypatch.setenv("ZOOM_ACCOUNT_ID", "test_account")
    monkeypatch.setenv("ZOOM_CLIENT_ID", "test_client")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "test_secret")

    config = Config()
    config.validate()  # Should not raise


def test_config_validation_fails_missing_vars(monkeypatch):
    """Test that validation fails with missing required vars"""
    # Don't set any env vars
    for key in ["ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET"]:
        monkeypatch.delenv(key, raising=False)

    # Pass empty env_file to prevent loading from .env
    config = Config(env_file="/dev/null")
    with pytest.raises(ConfigError) as exc_info:
        config.validate()

    assert "Missing required environment variables" in str(exc_info.value)


def test_config_defaults():
    """Test that default values are set correctly"""
    config = Config()
    assert config.output_dir == Path(".")
    assert config.log_level == "INFO"
    assert config.zoom_api_base_url == "https://api.zoom.us/v2"


def test_config_custom_output_dir(monkeypatch):
    """Test that custom output dir is used"""
    monkeypatch.setenv("OUTPUT_DIR", "/tmp/custom")
    config = Config()
    assert config.output_dir == Path("/tmp/custom")


def test_config_is_valid(monkeypatch):
    """Test is_valid() method"""
    # Invalid config
    for key in ["ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET"]:
        monkeypatch.delenv(key, raising=False)

    config = Config(env_file="/dev/null")
    assert not config.is_valid()

    # Valid config
    monkeypatch.setenv("ZOOM_ACCOUNT_ID", "test_account")
    monkeypatch.setenv("ZOOM_CLIENT_ID", "test_client")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "test_secret")

    config = Config(env_file="/dev/null")
    assert config.is_valid()


def test_config_repr_excludes_credentials(monkeypatch):
    """Test that __repr__ does not expose credentials"""
    monkeypatch.setenv("ZOOM_ACCOUNT_ID", "secret_account_123")
    monkeypatch.setenv("ZOOM_CLIENT_ID", "secret_client_456")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "very_secret_password_789")

    config = Config()
    repr_str = repr(config)

    # Should not contain actual credentials
    assert "secret_account_123" not in repr_str
    assert "secret_client_456" not in repr_str
    assert "very_secret_password_789" not in repr_str

    # Should contain safe information
    assert "Config" in repr_str
    assert "output_dir" in repr_str
    assert "log_level" in repr_str
    assert "zoom_api_base_url" in repr_str

    # Should indicate credentials are configured
    assert "configured" in repr_str or "credentials" in repr_str


def test_config_repr_shows_missing_credentials(monkeypatch):
    """Test that __repr__ indicates when credentials are missing"""
    for key in ["ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET"]:
        monkeypatch.delenv(key, raising=False)

    config = Config(env_file="/dev/null")
    repr_str = repr(config)

    # Should indicate credentials are missing
    assert "missing" in repr_str


def test_config_del_zeros_credentials(monkeypatch):
    """Test that __del__ zeros out credentials"""
    monkeypatch.setenv("ZOOM_ACCOUNT_ID", "account")
    monkeypatch.setenv("ZOOM_CLIENT_ID", "client")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "secret")

    config = Config()

    # Verify credentials are set
    assert config.zoom_account_id is not None
    assert config.zoom_client_id is not None
    assert config.zoom_client_secret is not None

    # Call __del__ manually
    config.__del__()

    # Credentials should be zeroed
    assert config._zoom_account_id is None
    assert config._zoom_client_id is None
    assert config._zoom_client_secret is None


def test_yaml_dependency_check_yaml_not_available(tmp_path, monkeypatch):
    """Test that YAML file loading fails gracefully when PyYAML not installed"""
    # Create a YAML config file
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("zoom_account_id: test\nzoom_client_id: client\n")

    # Mock YAML as not available
    import dlzoom.config
    original_yaml_available = dlzoom.config.YAML_AVAILABLE
    dlzoom.config.YAML_AVAILABLE = False

    try:
        config = Config(env_file=str(yaml_file))
        # Should raise ConfigError with helpful message
        pytest.fail("Should have raised ConfigError")
    except ConfigError as e:
        assert "PyYAML not installed" in str(e)
        assert "pip install pyyaml" in str(e)
        assert yaml_file.name in str(e)
    finally:
        # Restore original state
        dlzoom.config.YAML_AVAILABLE = original_yaml_available


def test_yaml_dependency_check_json_works_without_yaml(tmp_path, monkeypatch):
    """Test that JSON config still works when PyYAML not installed"""
    # Create a JSON config file
    json_file = tmp_path / "config.json"
    json_file.write_text('{"zoom_account_id": "test", "zoom_client_id": "client", "zoom_client_secret": "secret"}')

    # Mock YAML as not available
    import dlzoom.config
    original_yaml_available = dlzoom.config.YAML_AVAILABLE
    dlzoom.config.YAML_AVAILABLE = False

    try:
        config = Config(env_file=str(json_file))
        # Should work fine with JSON
        assert config.zoom_account_id == "test"
        assert config.zoom_client_id == "client"
    finally:
        # Restore original state
        dlzoom.config.YAML_AVAILABLE = original_yaml_available
