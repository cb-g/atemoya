"""
Centralized configuration management for atemoya pricing models.

Provides a unified way to load configuration from:
1. JSON config files (default values)
2. Environment variables (overrides)
3. Command-line arguments (highest priority)

Usage:
    from lib.python.config import load_config

    config = load_config('pricing/options', 'config.json')
    rate = config.get('risk_free_rate', 0.05)
"""

import json
import os
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar('T')


class Config:
    """Configuration container with hierarchical lookup."""

    def __init__(self, data: dict[str, Any], prefix: str = ""):
        self._data = data
        self._prefix = prefix

    def get(self, key: str, default: T = None) -> T:
        """
        Get a configuration value.

        Lookup order:
        1. Environment variable: {PREFIX}_{KEY} (uppercase)
        2. Config file value
        3. Default value

        Args:
            key: Configuration key
            default: Default value if not found

        Returns:
            Configuration value
        """
        # Try environment variable first
        env_key = f"{self._prefix}_{key}".upper().replace(".", "_")
        env_val = os.environ.get(env_key)
        if env_val is not None:
            return self._convert_type(env_val, default)

        # Try config file
        val = self._data.get(key)
        if val is not None:
            return val

        return default

    def _convert_type(self, val: str, default: T) -> T:
        """Convert string value to type of default."""
        if default is None:
            return val
        if isinstance(default, bool):
            return val.lower() in ('true', '1', 'yes')
        if isinstance(default, int):
            return int(val)
        if isinstance(default, float):
            return float(val)
        return val

    def section(self, name: str) -> 'Config':
        """Get a configuration section."""
        section_data = self._data.get(name, {})
        return Config(section_data, f"{self._prefix}_{name}" if self._prefix else name)


def load_config(module_path: str, config_file: str = "config.json") -> Config:
    """
    Load configuration for a module.

    Args:
        module_path: Path to module (e.g., 'pricing/options')
        config_file: Config file name

    Returns:
        Config object
    """
    # Try multiple locations
    locations = [
        Path(module_path) / config_file,
        Path(module_path) / "data" / config_file,
        Path(__file__).parent.parent.parent / module_path / config_file,
    ]

    for path in locations:
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            prefix = module_path.replace("/", "_").upper()
            return Config(data, prefix)

    # Return empty config if no file found
    return Config({}, module_path.replace("/", "_").upper())


# Default configurations for common parameters
DEFAULTS = {
    "risk_free_rate": 0.05,
    "dividend_yield": 0.0,
    "min_expiry_days": 7,
    "max_expiry_days": 365,
    "max_bid_ask_spread": 0.5,
    "min_volume": 1,
    "iv_bounds": {"lower": 0.01, "upper": 5.0},
    "newton_raphson": {
        "tolerance": 1e-5,
        "max_iterations": 50,
    },
    "svi": {
        "a_bounds": [0.0, 1.0],
        "b_bounds": [0.0, 1.0],
        "rho_bounds": [-1.0, 1.0],
        "m_bounds": [-0.5, 0.5],
        "sigma_bounds": [0.01, 1.0],
    },
}


def get_default(key: str, subkey: str = None) -> Any:
    """Get a default configuration value."""
    val = DEFAULTS.get(key)
    if subkey and isinstance(val, dict):
        return val.get(subkey)
    return val
