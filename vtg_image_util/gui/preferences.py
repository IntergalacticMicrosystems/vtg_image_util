"""
User preferences management for the disk image utility GUI.

Stores and retrieves user preferences including recent files,
window positions, and other settings.
"""

import json
import os
from pathlib import Path
from typing import Any


# Default preferences
DEFAULT_PREFS = {
    'recent_files': [],
    'max_recent_files': 10,
    'window_width': 800,
    'window_height': 600,
    'window_x': -1,  # -1 means center
    'window_y': -1,
    'confirm_delete': True,
    'confirm_overwrite': True,
    'last_open_dir': '',
    'last_save_dir': '',
}


def get_config_path() -> Path:
    """Get the path to the configuration file."""
    # Use AppData on Windows, ~/.config on Linux/Mac
    if os.name == 'nt':
        app_data = os.environ.get('APPDATA', os.path.expanduser('~'))
        config_dir = Path(app_data) / 'vtg_image_util'
    else:
        config_dir = Path.home() / '.config' / 'vtg_image_util'

    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / 'preferences.json'


class Preferences:
    """Manages user preferences with automatic persistence."""

    def __init__(self):
        self._prefs: dict[str, Any] = DEFAULT_PREFS.copy()
        self._config_path = get_config_path()
        self._load()

    def _load(self):
        """Load preferences from file."""
        try:
            if self._config_path.exists():
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # Merge with defaults (in case new prefs were added)
                    for key, value in loaded.items():
                        if key in DEFAULT_PREFS:
                            self._prefs[key] = value
        except (json.JSONDecodeError, OSError):
            # Ignore corrupt or unreadable config
            pass

    def _save(self):
        """Save preferences to file."""
        try:
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(self._prefs, f, indent=2)
        except OSError:
            # Ignore save failures
            pass

    def get(self, key: str, default: Any = None) -> Any:
        """Get a preference value."""
        return self._prefs.get(key, default)

    def set(self, key: str, value: Any):
        """Set a preference value and save."""
        self._prefs[key] = value
        self._save()

    # Recent files management
    def get_recent_files(self) -> list[str]:
        """Get list of recent files."""
        # Filter out files that no longer exist
        recent = self._prefs.get('recent_files', [])
        return [f for f in recent if os.path.exists(f)]

    def add_recent_file(self, path: str):
        """Add a file to the recent files list."""
        path = os.path.abspath(path)
        recent = self._prefs.get('recent_files', [])

        # Remove if already in list
        if path in recent:
            recent.remove(path)

        # Add to beginning
        recent.insert(0, path)

        # Trim to max
        max_recent = self._prefs.get('max_recent_files', 10)
        recent = recent[:max_recent]

        self._prefs['recent_files'] = recent
        self._save()

    def clear_recent_files(self):
        """Clear the recent files list."""
        self._prefs['recent_files'] = []
        self._save()

    # Window position management
    def get_window_position(self) -> tuple[int, int, int, int]:
        """Get saved window position (x, y, width, height)."""
        return (
            self._prefs.get('window_x', -1),
            self._prefs.get('window_y', -1),
            self._prefs.get('window_width', 800),
            self._prefs.get('window_height', 600)
        )

    def save_window_position(self, x: int, y: int, width: int, height: int):
        """Save current window position."""
        self._prefs['window_x'] = x
        self._prefs['window_y'] = y
        self._prefs['window_width'] = width
        self._prefs['window_height'] = height
        self._save()


# Global preferences instance
_prefs: Preferences | None = None


def get_preferences() -> Preferences:
    """Get the global preferences instance."""
    global _prefs
    if _prefs is None:
        _prefs = Preferences()
    return _prefs
