"""Encrypted biometric storage.

Face/voice templates and the PIN verifier are stored as Fernet-encrypted
blobs under config/security_data/.  On Windows the Fernet key itself is
wrapped with DPAPI (bound to the Windows user account) so copying the folder
to another machine or account yields unusable ciphertext.  A plain keyfile
fallback exists for non-Windows platforms.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time

from cryptography.fernet import Fernet, InvalidToken

from . import config

_LOCK = threading.RLock()
_fernet: Fernet | None = None

# PIN brute-force protection: escalating lockout, process-lifetime counter.
_pin_failures = 0
_pin_locked_until = 0.0


def _load_or_create_key() -> bytes:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    dpapi_file = config.DATA_DIR / "key.dpapi"
    plain_file = config.DATA_DIR / "key.bin"
    if os.name == "nt":
        try:
            import win32crypt  # pywin32 — already a project dependency
            if dpapi_file.exists():
                blob = dpapi_file.read_bytes()
                return win32crypt.CryptUnprotectData(blob, None, None, None, 0)[1]
            key = secrets.token_bytes(32)
            blob = win32crypt.CryptProtectData(key, "JARVIS security key",
                                               None, None, None, 0)
            dpapi_file.write_bytes(blob)
            return key
        except Exception:
            pass  # fall through to keyfile (logged by caller-facing status)
    if plain_file.exists():
        return plain_file.read_bytes()
    key = secrets.token_bytes(32)
    plain_file.write_bytes(key)
    try:
        os.chmod(plain_file, 0o600)
    except Exception:
        pass
    return key


def _get_fernet() -> Fernet:
    global _fernet
    with _LOCK:
        if _fernet is None:
            key = base64.urlsafe_b64encode(_load_or_create_key())
            _fernet = Fernet(key)
        return _fernet


def save_blob(name: str, data: dict) -> None:
    if not name.replace("_", "").isalnum():
        raise ValueError("invalid blob name")
    with _LOCK:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        token = _get_fernet().encrypt(json.dumps(data).encode("utf-8"))
        path = config.DATA_DIR / f"{name}.enc"
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(token)
        tmp.replace(path)


def load_blob(name: str) -> dict | None:
    path = config.DATA_DIR / f"{name}.enc"
    if not path.exists():
        return None
    try:
        with _LOCK:
            raw = _get_fernet().decrypt(path.read_bytes())
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def delete_blob(name: str) -> None:
    path = config.DATA_DIR / f"{name}.enc"
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def has_blob(name: str) -> bool:
    return (config.DATA_DIR / f"{name}.enc").exists()


# ── PIN backup authentication ────────────────────────────────────────────────

def set_pin(pin: str) -> None:
    pin = str(pin).strip()
    if len(pin) < 4:
        raise ValueError("PIN must be at least 4 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 200_000)
    save_blob("pin", {"salt": salt.hex(), "hash": digest.hex()})


def has_pin() -> bool:
    return has_blob("pin")


def verify_pin(pin: str) -> bool:
    global _pin_failures, _pin_locked_until
    with _LOCK:
        now = time.time()
        if now < _pin_locked_until:
            return False
        data = load_blob("pin")
        if not data:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", str(pin).encode("utf-8"),
            bytes.fromhex(data["salt"]), 200_000)
        ok = hmac.compare_digest(digest.hex(), data["hash"])
        if ok:
            _pin_failures = 0
        else:
            _pin_failures += 1
            if _pin_failures >= 5:
                _pin_locked_until = now + min(300, 15 * (2 ** (_pin_failures - 5)))
        return ok


def pin_lockout_remaining() -> float:
    return max(0.0, _pin_locked_until - time.time())