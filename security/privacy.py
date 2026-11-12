"""Privacy modes and the lock state machine.

Strict Privacy Mode:
  sensitive operations need face presence AND a fresh voice match (dual auth),
  or an active PIN window. Leaving the camera view / camera disconnect locks
  sensitive operations automatically; returning re-verifies (voice match must
  be fresh — the user simply speaks again).

Open Voice Mode:
  anyone may talk to JARVIS; general commands are untouched. Sensitive
  operations require authorization ONLY once the user has enrolled an
  identity (face, voice or PIN) — before that, legacy behaviour is preserved
  so installing this update changes nothing.

Emergency lock: everything sensitive is locked until a PIN unlock or a full
dual-auth re-verification plus explicit unlock.
"""
from __future__ import annotations

import threading
import time

from . import config, storage


class PrivacyController:
    def __init__(self, face_status_fn, voice_status_fn, event_cb=None):
        self._face_status = face_status_fn     # callable -> dict (may be {})
        self._voice_status = voice_status_fn   # callable -> dict (may be {})
        self.event_cb = event_cb or (lambda kind, data: None)
        self._lock = threading.RLock()
        self.emergency_locked = False
        self.pin_until = 0.0
        self.last_lock_reason = ""
        self._sensitive_locked = False

    # ── identity configuration ───────────────────────────────────────────────

    @staticmethod
    def identity_configured() -> bool:
        return (storage.has_blob("face") or storage.has_blob("voice")
                or storage.has_pin())

    @staticmethod
    def mode() -> str:
        m = str(config.get("privacy_mode"))
        return m if m in ("open", "strict") else "open"

    # ── events from monitors ─────────────────────────────────────────────────

    def notify(self, kind: str, data: dict) -> None:
        with self._lock:
            if self.mode() != "strict":
                return
            if kind in ("camera_disconnected", "face_error"):
                self._lock_sensitive("camera disconnected")
            elif kind == "authorized_absent":
                grace = float(config.get("presence_grace_seconds"))
                t = threading.Timer(grace, self._recheck_absence)
                t.daemon = True
                t.start()
            elif kind == "authorized_present":
                if self._sensitive_locked and not self.emergency_locked:
                    # face re-verified; sensitive ops still need fresh voice
                    self.event_cb("privacy_reverify", {
                        "message": "Authorized user returned — speak to re-verify voice."})

    def _recheck_absence(self) -> None:
        with self._lock:
            if self.mode() != "strict":
                return
            face = self._face_status()
            if not face.get("authorized_present") and not self._pin_active():
                self._lock_sensitive("authorized user left camera view")

    def _lock_sensitive(self, reason: str) -> None:
        if not self._sensitive_locked:
            self._sensitive_locked = True
            self.last_lock_reason = reason
            self.pin_until = 0.0
            self.event_cb("privacy_locked", {"reason": reason})

    # ── lock / unlock ────────────────────────────────────────────────────────

    def emergency_lock(self) -> None:
        with self._lock:
            self.emergency_locked = True
            self.pin_until = 0.0
            self._sensitive_locked = True
            self.last_lock_reason = "emergency lock engaged"
            self.event_cb("privacy_locked", {"reason": self.last_lock_reason})

    def unlock_with_pin(self, pin: str) -> tuple[bool, str]:
        if storage.pin_lockout_remaining() > 0:
            return False, (f"PIN locked for {int(storage.pin_lockout_remaining()) + 1}s "
                           "after repeated failures.")
        if not storage.verify_pin(pin):
            return False, "Incorrect PIN."
        with self._lock:
            self.pin_until = time.time() + float(config.get("pin_auth_window_seconds"))
            self.emergency_locked = False
            self._sensitive_locked = False
            self.last_lock_reason = ""
            self.event_cb("privacy_unlocked", {"method": "pin"})
        return True, "PIN accepted — sensitive operations unlocked."

    def unlock_explicit(self) -> tuple[bool, str]:
        """UI/voice unlock without PIN: only works with full dual auth live."""
        face = self._face_status()
        voice = self._voice_status()
        if face.get("authorized_present") and voice.get("verified"):
            with self._lock:
                self.emergency_locked = False
                self._sensitive_locked = False
                self.last_lock_reason = ""
                self.event_cb("privacy_unlocked", {"method": "dual"})
            return True, "Face and voice verified — unlocked."
        return False, "Unlock requires the authorized face in view and a fresh voice match (or PIN)."

    # ── the gate ─────────────────────────────────────────────────────────────

    def _pin_active(self) -> bool:
        return time.time() < self.pin_until

    def _dual_auth(self) -> bool:
        face = self._face_status()
        voice = self._voice_status()
        return bool(face.get("authorized_present")) and bool(voice.get("verified"))

    def authorize_sensitive(self) -> tuple[bool, str]:
        """May a sensitive/personal operation run right now?"""
        with self._lock:
            mode = self.mode()
            if self.emergency_locked:
                if self._dual_auth():
                    self.emergency_locked = False
                    self._sensitive_locked = False
                    self.event_cb("privacy_unlocked", {"method": "dual-auto"})
                    return True, "dual authentication restored"
                return False, "Emergency privacy lock is engaged. Unlock with PIN or face + voice."
            if self._pin_active():
                return True, "PIN authorization window"
            if mode == "open" and not self.identity_configured():
                return True, "security not configured — legacy behaviour"
            if mode == "strict":
                face = self._face_status()
                voice = self._voice_status()
                if not storage.has_blob("face") or not storage.has_blob("voice"):
                    return False, ("Strict Privacy Mode requires registered face AND voice. "
                                   "Enroll them in Security & Privacy settings.")
                if not face.get("authorized_present"):
                    if face.get("camera_status") in ("disconnected", "error", "off"):
                        self._lock_sensitive("camera unavailable in strict mode")
                        return False, "Camera is not active — sensitive operations are locked."
                    self._lock_sensitive("authorized user not in camera view")
                    return False, "Authorized user not detected — sensitive operations are locked."
                if not voice.get("verified"):
                    return False, ("Face detected, but voice is not verified. "
                                   "Speak a command so I can verify your voice.")
                self._sensitive_locked = False
                return True, "dual authentication (face + voice)"
            # open mode with an enrolled identity
            if self._dual_auth():
                self._sensitive_locked = False
                return True, "face + voice verified"
            face = self._face_status()
            voice = self._voice_status()
            if storage.has_blob("face") and face.get("authorized_present"):
                return False, "Face recognized — speak so I can verify your voice, or use PIN."
            if storage.has_blob("voice") and voice.get("verified") and not storage.has_blob("face"):
                return True, "voice verified (no face enrolled)"
            return False, ("Sensitive operation: authorization required "
                           "(face + voice, or PIN in Security & Privacy).")

    def status(self) -> dict:
        with self._lock:
            face = self._face_status()
            strict = self.mode() == "strict"
            locked = self.emergency_locked or (strict and self._sensitive_locked)
            if strict and not locked:
                ok, _ = True, None
                if not self._pin_active():
                    ok = self._dual_auth()
                locked = not ok and self.identity_configured()
            return {
                "mode": self.mode(),
                "identity_configured": self.identity_configured(),
                "privacy_locked": bool(locked),
                "emergency_locked": self.emergency_locked,
                "pin_active": self._pin_active(),
                "pin_set": storage.has_pin(),
                "lock_reason": self.last_lock_reason,
            }