"""Security settings — stored in config/security_settings.json.

Deliberately a SEPARATE file from config/api_keys.json so existing user
configuration is never touched by the security subsystem.
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

_BASE_DIR = (Path(sys.executable).parent if getattr(sys, "frozen", False)
             else Path(__file__).resolve().parent.parent)
CONFIG_DIR = _BASE_DIR / "config"
SETTINGS_FILE = CONFIG_DIR / "security_settings.json"
DATA_DIR = CONFIG_DIR / "security_data"

_LOCK = threading.RLock()

# Tools that touch personal data / the machine.  In Strict mode these need
# face + voice; in Open mode they need authorization once an identity is set up.
DEFAULT_SENSITIVE_TOOLS = [
    "file_controller", "file_processor", "computer_control",
    "computer_settings", "send_message", "browser_control", "dev_agent",
    "code_helper", "desktop", "open_app", "game_updater", "video_player",
    "save_memory", "recall_memory", "undo", "screen_process",
]

DEFAULTS = {
    "privacy_mode": "open",              # "open" | "strict"
    "face_tracking_enabled": False,
    "face_recognition_enabled": False,
    "camera_permission": False,          # explicit consent; camera never runs without it
    "camera_index": 0,
    "camera_loss_shutdown": True,        # security camera lost -> lock + shut down the agent
    "face_monitor_fps": 8,               # low CPU by design
    "face_match_threshold": 0.40,        # SFace cosine similarity
    "presence_grace_seconds": 3.0,       # absence shorter than this does not lock
    "voice_verification_enabled": False,
    "voice_match_threshold": 0.78,       # cosine on speaker embedding
    "voice_unauthorized_below": 0.55,    # clearly-different speaker → alert
    "voice_verify_ttl_seconds": 90.0,    # a match stays valid this long
    "pin_auth_window_seconds": 300.0,    # PIN backup unlocks sensitive ops for 5 min
    "drive_protection_enabled": False,   # master switch; all drives DENIED when on
    "drives": {},                        # "C": {"access":bool,"read":bool,...}
    "sensitive_tools": DEFAULT_SENSITIVE_TOOLS,
}

DRIVE_OPS = ("access", "read", "write", "create", "edit", "delete")


def _read_file() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def load_settings() -> dict:
    with _LOCK:
        data = dict(DEFAULTS)
        data.update(_read_file())
        return data


def save_settings(**fields) -> None:
    """Read-modify-write; never disturbs keys we do not own."""
    with _LOCK:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = _read_file()
        data.update(fields)
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=4), encoding="utf-8")
        tmp.replace(SETTINGS_FILE)


def get(key: str):
    return load_settings().get(key, DEFAULTS.get(key))


def set_value(key: str, value) -> None:
    save_settings(**{key: value})