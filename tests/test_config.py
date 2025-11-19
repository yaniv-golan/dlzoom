"""
Unit tests for config module
"""

import os
from pathlib import Path

import pytest

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
    config = Config(env_file=os.devnull)
    with pytest.raises(ConfigError) as exc_info:
        config.validate()

    assert "Missing required environment variables" in str(exc_info.value)


def test_config_defaults():
    """Test that default values are set correctly"""
    config = Config()
    assert config.output_dir == Path(".")
    assert config.log_level == "INFO"
    assert config.zoom_api_base_url == "https://api.zoom.us/v2"


def test_missing_config_file_raises_error(tmp_path):
    """Explicit config path must exist instead of silently loading .env"""
    missing = tmp_path / "missing.json"
    with pytest.raises(ConfigError) as exc_info:
        Config(env_file=str(missing))
    assert "does not exist" in str(exc_info.value)


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

    config = Config(env_file=os.devnull)
    assert not config.is_valid()

    # Valid config
    monkeypatch.setenv("ZOOM_ACCOUNT_ID", "test_account")
    monkeypatch.setenv("ZOOM_CLIENT_ID", "test_client")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "test_secret")

    config = Config(env_file=os.devnull)
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
        Config(env_file=str(yaml_file))
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
    json_file.write_text(
        '{"zoom_account_id": "test", "zoom_client_id": "client", "zoom_client_secret": "secret"}'
    )

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


def test_config_discovers_user_config_json(tmp_path, monkeypatch):
    """Config should load credentials from default user config directory."""
    config_dir = tmp_path / "dlzoom"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text(
        '{"zoom_account_id": "file_account", "zoom_client_id": "file_client", '
        '"zoom_client_secret": "file_secret"}'
    )

    monkeypatch.setattr("dlzoom.config.user_config_dir", lambda _: str(config_dir))
    for key in ["ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET"]:
        monkeypatch.delenv(key, raising=False)

    cfg = Config()
    assert cfg.zoom_account_id == "file_account"
    assert cfg.zoom_client_id == "file_client"
    assert cfg.zoom_client_secret == "file_secret"


def test_env_vars_override_user_config(tmp_path, monkeypatch):
    """Environment variables should override values from user config file."""
    config_dir = tmp_path / "dlzoom"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        '{"zoom_account_id": "file_account", "zoom_client_id": "file_client", '
        '"zoom_client_secret": "file_secret"}'
    )

    monkeypatch.setattr("dlzoom.config.user_config_dir", lambda _: str(config_dir))
    monkeypatch.setenv("ZOOM_ACCOUNT_ID", "env_account")
    monkeypatch.setenv("ZOOM_CLIENT_ID", "env_client")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "env_secret")

    cfg = Config()
    assert cfg.zoom_account_id == "env_account"
    assert cfg.zoom_client_id == "env_client"
    assert cfg.zoom_client_secret == "env_secret"


def test_config_discovers_user_config_yaml(tmp_path, monkeypatch):
    """YAML config files in user config dir should be discovered."""
    pytest.importorskip("yaml")
    config_dir = tmp_path / "dlzoom"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "zoom_account_id: yaml_account\n"
        "zoom_client_id: yaml_client\n"
        "zoom_client_secret: yaml_secret\n"
    )

    monkeypatch.setattr("dlzoom.config.user_config_dir", lambda _: str(config_dir))
    for key in ["ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET"]:
        monkeypatch.delenv(key, raising=False)

    cfg = Config()
    assert cfg.zoom_account_id == "yaml_account"
    assert cfg.zoom_client_id == "yaml_client"
    assert cfg.zoom_client_secret == "yaml_secret"


def test_config_discovers_user_config_yml(tmp_path, monkeypatch):
    """config.yml should also be detected when higher-priority files absent."""
    pytest.importorskip("yaml")
    config_dir = tmp_path / "dlzoom"
    config_dir.mkdir()
    (config_dir / "config.yml").write_text(
        "zoom_account_id: yml_account\n"
        "zoom_client_id: yml_client\n"
        "zoom_client_secret: yml_secret\n"
    )

    monkeypatch.setattr("dlzoom.config.user_config_dir", lambda _: str(config_dir))
    for key in ["ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET"]:
        monkeypatch.delenv(key, raising=False)

    cfg = Config()
    assert cfg.zoom_account_id == "yml_account"
    assert cfg.zoom_client_id == "yml_client"
    assert cfg.zoom_client_secret == "yml_secret"


def test_explicit_config_overrides_user_config(tmp_path, monkeypatch):
    """Explicit --config path should take precedence over discovered config."""
    default_dir = tmp_path / "dlzoom_default"
    default_dir.mkdir()
    default_file = default_dir / "config.json"
    default_file.write_text(
        '{"zoom_account_id": "default_account", "zoom_client_id": "default_client", '
        '"zoom_client_secret": "default_secret"}'
    )

    explicit_file = tmp_path / "explicit.json"
    explicit_file.write_text(
        '{"zoom_account_id": "explicit_account", "zoom_client_id": "explicit_client", '
        '"zoom_client_secret": "explicit_secret"}'
    )

    monkeypatch.setattr("dlzoom.config.user_config_dir", lambda _: str(default_dir))

    cfg = Config(env_file=str(explicit_file))
    assert cfg.zoom_account_id == "explicit_account"
    assert cfg.zoom_client_id == "explicit_client"
    assert cfg.zoom_client_secret == "explicit_secret"


def test_get_auth_mode(tmp_path, monkeypatch):
    """get_auth_mode should reflect configured credentials."""
    config_dir = tmp_path / "dlzoom"
    config_dir.mkdir()
    monkeypatch.setattr("dlzoom.config.user_config_dir", lambda _: str(config_dir))

    # No credentials defaults to "none"
    cfg = Config(env_file=os.devnull)
    assert cfg.get_auth_mode() == "none"

    # Tokens path present should return oauth
    tokens_file = cfg.tokens_path
    tokens_file.parent.mkdir(parents=True, exist_ok=True)
    tokens_file.write_text("{}")
    assert cfg.get_auth_mode() == "oauth"

    # S2S credentials should take precedence
    monkeypatch.setenv("ZOOM_ACCOUNT_ID", "acct")
    monkeypatch.setenv("ZOOM_CLIENT_ID", "client")
    monkeypatch.setenv("ZOOM_CLIENT_SECRET", "secret")
    cfg_with_s2s = Config(env_file=os.devnull)
    assert cfg_with_s2s.get_auth_mode() == "s2s"
