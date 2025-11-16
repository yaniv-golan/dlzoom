"""
Configuration management for dlzoom
"""

import json
import os
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv
from platformdirs import user_config_dir

from dlzoom.exceptions import ConfigError

# Check YAML availability at module level
try:
    from importlib.util import find_spec

    YAML_AVAILABLE = find_spec("yaml") is not None
except ImportError:
    YAML_AVAILABLE = False


class Config:
    """Configuration loader and validator with multi-source support"""

    # Schema for validation
    REQUIRED_FIELDS = ["zoom_account_id", "zoom_client_id", "zoom_client_secret"]
    OPTIONAL_FIELDS = {
        "output_dir": ".",
        "log_level": "INFO",
        "zoom_api_base_url": "https://api.zoom.us/v2",
        "zoom_oauth_token_url": None,
        "zoom_s2s_default_user": None,
        # End-user auth via hosted OAuth broker (open source, auditable code in zoom-broker/)
        # Users can override with DLZOOM_AUTH_URL env var or --auth-url flag, or self-host
        "auth_url": "https://zoom-broker.dlzoom.workers.dev",
        # Token storage path (resolved at runtime using platformdirs)
        "tokens_path": None,
    }

    def __init__(self, env_file: str | None = None):
        # Configuration priority:
        # 1. Config file (JSON/YAML)
        # 2. Environment variables
        # 3. .env file
        # 4. Defaults

        self.config_dir = Path(user_config_dir("dlzoom"))
        config_data = {}

        # Load from config file if provided
        if env_file is not None:
            config_data = self._load_config_file(env_file)
        else:
            default_config = self._find_default_config()
            if default_config:
                config_data = self._load_config_file(str(default_config))
            # Do not implicitly load .env here to allow tests and callers
            # to control configuration via environment variables explicitly.
            # If a .env-style file path is passed explicitly to env_file or
            # via CLI, _load_config_file() will handle load_dotenv(config_path).

        prefer_env_over_file = env_file is None

        def _resolve_s2s_field(config_key: str, env_key: str) -> str | None:
            config_value = config_data.get(config_key)
            env_value = os.getenv(env_key)
            if prefer_env_over_file:
                return env_value if env_value is not None else config_value
            return config_value if config_value is not None else env_value

        # Required Zoom credentials (prioritize per source order)
        # Store in private variables to prevent accidental exposure in logs/tracebacks
        self._zoom_account_id = _resolve_s2s_field("zoom_account_id", "ZOOM_ACCOUNT_ID")
        self._zoom_client_id = _resolve_s2s_field("zoom_client_id", "ZOOM_CLIENT_ID")
        self._zoom_client_secret = _resolve_s2s_field("zoom_client_secret", "ZOOM_CLIENT_SECRET")

        # Optional settings
        output_dir_val = config_data.get("output_dir") or os.getenv("OUTPUT_DIR", ".")
        self.output_dir = Path(str(output_dir_val))
        self.log_level = config_data.get("log_level") or os.getenv("LOG_LEVEL", "INFO")
        api_base = config_data.get("zoom_api_base_url") or os.getenv(
            "ZOOM_API_BASE_URL", self.OPTIONAL_FIELDS["zoom_api_base_url"]
        )
        self.zoom_api_base_url = str(api_base).rstrip("/")
        token_override = config_data.get("zoom_oauth_token_url") or os.getenv(
            "ZOOM_OAUTH_TOKEN_URL"
        )
        self.zoom_oauth_token_url = (
            str(token_override).strip()
            if token_override
            else _derive_token_url(self.zoom_api_base_url)
        )

        # Hosted auth service URL (flag/env/config/default precedence handled in CLI commands)
        raw_auth_url = (
            config_data.get("auth_url")
            or os.getenv("DLZOOM_AUTH_URL")
            or self.OPTIONAL_FIELDS["auth_url"]
        )
        self.auth_url = str(raw_auth_url).strip()

        # Token file path: default under platform-specific user config directory
        configured_tokens_path = config_data.get("tokens_path") or os.getenv("DLZOOM_TOKENS_PATH")
        if configured_tokens_path:
            self.tokens_path = Path(str(configured_tokens_path))
        else:
            self.tokens_path = self.config_dir / "tokens.json"

        # Optional default user for S2S --scope=user fallback
        raw_config_default = config_data.get("zoom_s2s_default_user")
        s2s_default_source: str
        if raw_config_default is not None:
            s2s_default_source = str(raw_config_default)
        else:
            env_default = os.getenv("ZOOM_S2S_DEFAULT_USER")
            s2s_default_source = env_default if env_default is not None else ""
        cleaned_default = s2s_default_source.strip()
        self.s2s_default_user = cleaned_default or None

    @property
    def zoom_account_id(self) -> str | None:
        """Zoom account ID (read-only property)"""
        return self._zoom_account_id

    @property
    def zoom_client_id(self) -> str | None:
        """Zoom client ID (read-only property)"""
        return self._zoom_client_id

    @property
    def zoom_client_secret(self) -> str | None:
        """Zoom client secret (read-only property)"""
        return self._zoom_client_secret

    def __repr__(self) -> str:
        """
        String representation that excludes credentials

        Prevents accidental credential exposure in logs, tracebacks, and debugging
        """
        # Check all three credentials for S2S auth
        s2s_configured = bool(
            self._zoom_account_id and self._zoom_client_id and self._zoom_client_secret
        )
        return (
            f"Config("
            f"output_dir={self.output_dir!r}, "
            f"log_level={self.log_level!r}, "
            f"zoom_api_base_url={self.zoom_api_base_url!r}, "
            f"credentials={'configured' if s2s_configured else 'missing'}"
            f")"
        )

    def clear_credentials(self) -> None:
        """
        Clear sensitive credentials from memory.

        Note: Due to Python's memory management and string immutability,
        this provides best-effort cleanup but cannot guarantee complete
        memory erasure. Credentials may remain in memory until garbage
        collection or process termination.
        """
        self._zoom_account_id = None
        self._zoom_client_id = None
        self._zoom_client_secret = None

    def __del__(self) -> None:
        """Attempt to clear credentials when object is destroyed (best-effort only)"""
        try:
            self.clear_credentials()
        except Exception:
            pass  # Ignore errors during finalization

    @staticmethod
    def _is_null_device(path_str: str) -> bool:
        """Return True when the provided path represents the OS null device."""
        normalized = path_str.strip().lower()
        normalized = normalized.replace("\\", "/")

        null_candidates = {"/dev/null", "nul", "nul:"}
        try:
            null_candidates.add(os.devnull.lower())
            null_candidates.add(Path(os.devnull).as_posix().lower())
        except Exception:
            pass

        return normalized in null_candidates

    def _load_config_file(self, config_path: str) -> dict[str, Any]:
        """
        Load configuration from JSON or YAML file

        Args:
            config_path: Path to config file (.json or .yaml/.yml)

        Returns:
            Configuration dictionary

        Raises:
            ConfigError: If file cannot be loaded or parsed
        """
        if self._is_null_device(config_path):
            # Allow callers/tests to opt-out from config file loading
            # via special null-device paths such as /dev/null or nul.
            return {}

        path = Path(config_path)

        if not path.exists():
            raise ConfigError(
                f"Config file '{config_path}' does not exist. "
                "Provide an existing JSON/YAML/.env file or remove the --config flag."
            )

        # Check YAML availability early if trying to load YAML file
        if path.suffix.lower() in [".yaml", ".yml"] and not YAML_AVAILABLE:
            raise ConfigError(
                f"Cannot load YAML config file '{path.name}': PyYAML not installed. "
                "Install with: pip install pyyaml"
            )

        try:
            with open(path) as f:
                if path.suffix.lower() == ".json":
                    data = json.load(f)
                elif path.suffix.lower() in [".yaml", ".yml"]:
                    data = self._load_yaml(f)
                else:
                    # Assume .env file
                    load_dotenv(config_path)
                    return {}

            # Validate schema
            self._validate_schema(data, path)
            return dict(data)

        except json.JSONDecodeError as e:
            raise ConfigError(f"Invalid JSON in config file {config_path}: {e}")
        except Exception as e:
            raise ConfigError(f"Failed to load config file {config_path}: {e}")

    def _load_yaml(self, file_obj: Any) -> dict[str, Any]:
        """
        Load YAML configuration

        Args:
            file_obj: Open file object

        Returns:
            Configuration dictionary

        Raises:
            ConfigError: If YAML cannot be parsed or PyYAML not installed
        """
        try:
            import yaml

            result = yaml.safe_load(file_obj)
            return dict(result) if result else {}
        except ImportError:
            raise ConfigError("PyYAML not installed. Install with: pip install pyyaml")
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML: {e}")

    def _find_default_config(self) -> Path | None:
        """
        Locate the default config file in the user config directory.

        Returns:
            Path to the discovered config file or None if not present.
        """
        for filename in ("config.json", "config.yaml", "config.yml"):
            candidate = self.config_dir / filename
            if candidate.exists():
                return candidate
        return None

    def _validate_schema(self, data: dict[str, Any], path: Path) -> None:
        """
        Validate configuration schema

        Args:
            data: Configuration data to validate
            path: Path to config file (for error messages)

        Raises:
            ConfigError: If schema validation fails
        """
        if not isinstance(data, dict):
            raise ConfigError(f"Config file {path} must contain a JSON/YAML object")

        # Check for unknown keys
        known_keys = set(self.REQUIRED_FIELDS) | set(self.OPTIONAL_FIELDS.keys())
        unknown_keys = set(data.keys()) - known_keys

        if unknown_keys:
            raise ConfigError(
                f"Unknown keys in config file {path}: {', '.join(unknown_keys)}\n"
                f"Valid keys: {', '.join(sorted(known_keys))}"
            )

        # Type validation
        if "output_dir" in data and not isinstance(data["output_dir"], str):
            raise ConfigError(f"output_dir must be a string in {path}")

        if "log_level" in data:
            valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            if data["log_level"].upper() not in valid_levels:
                raise ConfigError(f"log_level must be one of {valid_levels} in {path}")

        if "zoom_api_base_url" in data and not isinstance(data["zoom_api_base_url"], str):
            raise ConfigError(f"zoom_api_base_url must be a string in {path}")
        if "auth_url" in data and not isinstance(data["auth_url"], str):
            raise ConfigError(f"auth_url must be a string in {path}")
        if "tokens_path" in data and not isinstance(data["tokens_path"], str):
            raise ConfigError(f"tokens_path must be a string in {path}")

    def validate(self) -> None:
        """Validate required configuration"""
        missing = []

        if not self.zoom_account_id:
            missing.append("ZOOM_ACCOUNT_ID")
        if not self.zoom_client_id:
            missing.append("ZOOM_CLIENT_ID")
        if not self.zoom_client_secret:
            missing.append("ZOOM_CLIENT_SECRET")

        if missing:
            raise ConfigError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                "Please set them in .env file or environment"
            )

    def is_valid(self) -> bool:
        """Check if configuration is valid"""
        try:
            self.validate()
            return True
        except ConfigError:
            return False

    def get_auth_mode(self) -> Literal["s2s", "oauth", "none"]:
        """Return the active authentication mode based on available credentials."""
        if self.zoom_account_id and self.zoom_client_id and self.zoom_client_secret:
            return "s2s"
        try:
            if self.tokens_path.exists():
                return "oauth"
        except Exception:
            # If tokens_path points to inaccessible location, treat as none.
            pass
        return "none"


def _derive_token_url(api_base_url: str) -> str:
    """Infer the OAuth token URL from the API base host (Zoom vs ZoomGov, etc.)."""
    parsed = urlsplit(api_base_url)
    host = parsed.netloc
    if host.startswith("api."):
        host = host[4:]
    scheme = parsed.scheme or "https"
    return urlunsplit((scheme, host, "/oauth/token", "", ""))
