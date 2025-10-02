"""
Configuration management for dlzoom
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from dlzoom.exceptions import ConfigError

# Check YAML availability at module level
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class Config:
    """Configuration loader and validator with multi-source support"""

    # Schema for validation
    REQUIRED_FIELDS = ["zoom_account_id", "zoom_client_id", "zoom_client_secret"]
    OPTIONAL_FIELDS = {
        "output_dir": ".",
        "log_level": "INFO",
        "zoom_api_base_url": "https://api.zoom.us/v2"
    }

    def __init__(self, env_file: Optional[str] = None):
        # Configuration priority:
        # 1. Config file (JSON/YAML)
        # 2. Environment variables
        # 3. .env file
        # 4. Defaults

        config_data = {}

        # Load from config file if provided
        if env_file is not None:
            config_data = self._load_config_file(env_file)
        else:
            # Only load .env file if no config file was specified
            load_dotenv()

        # Required Zoom credentials (prioritize config file, fall back to env)
        # Store in private variables to prevent accidental exposure in logs/tracebacks
        self._zoom_account_id = config_data.get("zoom_account_id") or os.getenv("ZOOM_ACCOUNT_ID")
        self._zoom_client_id = config_data.get("zoom_client_id") or os.getenv("ZOOM_CLIENT_ID")
        self._zoom_client_secret = config_data.get("zoom_client_secret") or os.getenv("ZOOM_CLIENT_SECRET")

        # Optional settings
        self.output_dir = Path(
            config_data.get("output_dir") or os.getenv("OUTPUT_DIR", ".")
        )
        self.log_level = config_data.get("log_level") or os.getenv("LOG_LEVEL", "INFO")
        self.zoom_api_base_url = (
            config_data.get("zoom_api_base_url") or
            os.getenv("ZOOM_API_BASE_URL", "https://api.zoom.us/v2")
        )

    @property
    def zoom_account_id(self) -> Optional[str]:
        """Zoom account ID (read-only property)"""
        return self._zoom_account_id

    @property
    def zoom_client_id(self) -> Optional[str]:
        """Zoom client ID (read-only property)"""
        return self._zoom_client_id

    @property
    def zoom_client_secret(self) -> Optional[str]:
        """Zoom client secret (read-only property)"""
        return self._zoom_client_secret

    def __repr__(self) -> str:
        """
        String representation that excludes credentials

        Prevents accidental credential exposure in logs, tracebacks, and debugging
        """
        return (
            f"Config("
            f"output_dir={self.output_dir!r}, "
            f"log_level={self.log_level!r}, "
            f"zoom_api_base_url={self.zoom_api_base_url!r}, "
            f"credentials={'configured' if self._zoom_account_id else 'missing'}"
            f")"
        )

    def __del__(self):
        """Zero out credentials when object is destroyed"""
        if hasattr(self, '_zoom_account_id'):
            self._zoom_account_id = None
        if hasattr(self, '_zoom_client_id'):
            self._zoom_client_id = None
        if hasattr(self, '_zoom_client_secret'):
            self._zoom_client_secret = None

    def _load_config_file(self, config_path: str) -> Dict[str, Any]:
        """
        Load configuration from JSON or YAML file

        Args:
            config_path: Path to config file (.json or .yaml/.yml)

        Returns:
            Configuration dictionary

        Raises:
            ConfigError: If file cannot be loaded or parsed
        """
        path = Path(config_path)

        if not path.exists():
            # If file doesn't exist, assume it's a .env file path
            load_dotenv(config_path)
            return {}

        # Check YAML availability early if trying to load YAML file
        if path.suffix.lower() in [".yaml", ".yml"] and not YAML_AVAILABLE:
            raise ConfigError(
                f"Cannot load YAML config file '{path.name}': PyYAML not installed. "
                "Install with: pip install pyyaml"
            )

        try:
            with open(path, "r") as f:
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
            return data

        except json.JSONDecodeError as e:
            raise ConfigError(f"Invalid JSON in config file {config_path}: {e}")
        except Exception as e:
            raise ConfigError(f"Failed to load config file {config_path}: {e}")

    def _load_yaml(self, file_obj) -> Dict[str, Any]:
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
            return yaml.safe_load(file_obj)
        except ImportError:
            raise ConfigError(
                "PyYAML not installed. Install with: pip install pyyaml"
            )
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML: {e}")

    def _validate_schema(self, data: Dict[str, Any], path: Path) -> None:
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
                raise ConfigError(
                    f"log_level must be one of {valid_levels} in {path}"
                )

        if "zoom_api_base_url" in data and not isinstance(data["zoom_api_base_url"], str):
            raise ConfigError(f"zoom_api_base_url must be a string in {path}")

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
