"""SecurityManager — single entry point used by main.py, the HUD overlay,
the remote dashboard and the security voice tool.

Integration contract (all additive):
  main.py startup      → get_manager().start()
  mic callback         → get_manager().feed_microphone(indata)   [non-blocking]
  _execute_tool top    → denial = get_manager().authorize_tool(name, args)
"""
from __future__ import annotations

import os
import re
import threading
import time
from collections import deque
from pathlib import Path

from . import config, drive_guard, privacy as privacy_mod, storage

_PATH_KEYS = ("path", "file_path", "destination", "folder", "directory",
              "output_path", "filename", "source_path", "target", "save_path")

_FC_OPS = {
    "list": "read", "find": "read", "largest": "read", "disk_usage": "read",
    "info": "read", "read": "read",
    "create_file": "create", "create_folder": "create",
    "write": "write", "delete": "delete", "rename": "edit",
    "organize_desktop": "edit",
}

_TOOL_OPS = {
    "file_processor": "write", "desktop": "write", "dev_agent": "write",
    "code_helper": "write", "game_updater": "write", "video_player": "read",
    "open_app": "read",
}

_SHORTCUTS = {
    "desktop": "Desktop", "downloads": "Downloads", "documents": "Documents",
    "pictures": "Pictures", "music": "Music", "videos": "Videos", "home": "",
}


def _resolve_for_check(raw: str) -> str:
    s = str(raw).strip().strip('"').strip("'")
    head, sep, rest = s.replace("\\", "/").partition("/")
    if head.lower() in _SHORTCUTS:
        base = Path.home() / _SHORTCUTS[head.lower()]
        return str(base / rest) if sep and rest else str(base)
    return s


class SecurityManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._started = False
        self._listeners: list = []
        self._notifications: deque = deque(maxlen=100)
        self._face_monitor = None
        self._face_engine = None
        self._voice = None
        self._camera_was_active = False
        self._shutdown_hook = None
        self._shutdown_fired = False
        self.privacy = privacy_mod.PrivacyController(
            face_status_fn=self._face_status,
            voice_status_fn=self._voice_status,
            event_cb=self._on_event,
        )

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
        drive_guard.install_process_guards()
        drive_guard.on_denial(self._on_drive_denial)
        self._sync_monitors()
        self._notify("security", "Security subsystem ready.")

    def _sync_monitors(self) -> None:
        """Start/stop background workers to match current settings."""
        s = config.load_settings()
        # voice
        if s.get("voice_verification_enabled") or storage.has_blob("voice"):
            self._ensure_voice()
            if s.get("voice_verification_enabled") and not self._voice.running:
                self._voice.start()
            if not s.get("voice_verification_enabled") and self._voice.running \
                    and not self._voice.enrolling:
                self._voice.stop()
        # face — camera ONLY with explicit permission AND a feature toggle
        cam_ok = bool(s.get("camera_permission"))
        face_on = bool(s.get("face_tracking_enabled") or s.get("face_recognition_enabled"))
        if cam_ok and face_on:
            try:
                self._ensure_face()
                if not self._face_monitor.running:
                    self._face_monitor.start()
            except Exception as e:
                self._notify("security_error", f"Face monitor unavailable: {e}")
        elif self._face_monitor is not None and self._face_monitor.running \
                and not self._face_monitor.registering:
            self._face_monitor.stop()

    def _ensure_face(self):
        if self._face_monitor is None:
            from .face import FaceEngine, FaceMonitor   # cv2 import stays lazy
            self._face_engine = FaceEngine()
            self._face_monitor = FaceMonitor(self._face_engine, self._on_event)
        return self._face_monitor

    def _ensure_voice(self):
        if self._voice is None:
            from .voice import VoiceVerifier
            self._voice = VoiceVerifier(self._on_event)
        return self._voice

    # ── taps used by main.py ─────────────────────────────────────────────────

    def feed_microphone(self, indata) -> None:
        v = self._voice
        if v is not None and v.running:
            v.feed(indata)

    def camera_frame_jpeg(self) -> bytes | None:
        """Shared frame for vision capture while the monitor holds the camera."""
        m = self._face_monitor
        if m is not None and m.running and m.camera_status == "active":
            return m.latest_jpeg()
        return None

    # ── events & notifications ───────────────────────────────────────────────

    def add_listener(self, cb) -> None:
        with self._lock:
            self._listeners.append(cb)

    def _on_event(self, kind: str, data: dict) -> None:
        if kind == "camera_active":
            self._camera_was_active = True
        elif kind in ("camera_disconnected", "face_error"):
            self._camera_loss_shutdown(kind)
        self.privacy.notify(kind, data)
        messages = {
            "unknown_person": "Unknown person detected in camera view.",
            "unauthorized_voice": "Unrecognized voice detected.",
            "camera_disconnected": "Camera disconnected — sensitive operations locked.",
            "privacy_locked": f"Privacy lock engaged: {data.get('reason', '')}",
            "privacy_unlocked": f"Privacy unlocked ({data.get('method', '')}).",
            "voice_verified": "Authorized voice verified.",
        }
        if kind in messages:
            self._notify(kind, messages[kind])
        for cb in list(self._listeners):
            try:
                cb({"type": "security_event", "kind": kind, **data})
            except Exception:
                pass

    def _notify(self, kind: str, message: str) -> None:
        item = {"time": time.time(), "kind": kind, "message": message}
        self._notifications.append(item)
        for cb in list(self._listeners):
            try:
                cb({"type": "security_event", **item})
            except Exception:
                pass

    def _on_drive_denial(self, drive: str, op: str, path: str, source: str) -> None:
        self._notify("drive_denied",
                     f"Blocked {op} on drive {drive}: ({path}) via {source}")

    # ── camera loss -> shut down the assistant (never the PC) ─────────────────

    def set_shutdown_hook(self, cb) -> None:
        """main.py registers how to stop the agent; called from a worker thread."""
        self._shutdown_hook = cb

    def _camera_loss_shutdown(self, reason: str) -> None:
        s = config.load_settings()
        if not s.get("camera_loss_shutdown", True):
            return
        # Only a camera that was actually live counts as "lost" — a machine
        # booting with no camera must not shut the agent down.
        if not self._camera_was_active or self._shutdown_fired:
            return
        self._shutdown_fired = True
        self.privacy.emergency_lock()
        self._notify("camera_loss_shutdown",
                     "Security camera lost — conversation stopped, assistant shutting down.")
        hook = self._shutdown_hook
        if hook is not None:
            try:
                hook(reason)
            except Exception as e:
                print(f"[Security] shutdown hook failed: {e}")

    def notifications(self, limit: int = 20) -> list[dict]:
        return list(self._notifications)[-limit:]

    # ── status helpers ───────────────────────────────────────────────────────

    def _face_status(self) -> dict:
        if self._face_monitor is None:
            return {"camera_status": "off", "authorized_present": False}
        return self._face_monitor.status()

    def _voice_status(self) -> dict:
        if self._voice is None:
            from .voice import VoiceVerifier
            return {"enrolled": VoiceVerifier.enrolled(), "verified": False}
        return self._voice.status()

    def quick_status(self) -> dict:
        """Cheap snapshot for the HUD indicator (no drive enumeration)."""
        s = config.load_settings()
        face = self._face_status()
        return {
            "face": face,
            "voice": self._voice_status(),
            "privacy": self.privacy.status(),
            "camera": {
                "permission": bool(s.get("camera_permission")),
                "status": face.get("camera_status", "off"),
                "active": bool(face.get("camera_active")),
            },
        }

    def status(self) -> dict:
        s = config.load_settings()
        face = self._face_status()
        voice = self._voice_status()
        priv = self.privacy.status()
        models_dir = config.DATA_DIR / "models"
        models_ready = all((models_dir / f).exists() for f in (
            "face_detection_yunet_2023mar.onnx",
            "face_recognition_sface_2021dec.onnx"))
        return {
            "face": {
                **face,
                "tracking_enabled": bool(s.get("face_tracking_enabled")),
                "recognition_enabled": bool(s.get("face_recognition_enabled")),
                "registered": storage.has_blob("face"),
                "models_ready": models_ready,
            },
            "voice": {
                **voice,
                "enabled": bool(s.get("voice_verification_enabled")),
            },
            "privacy": priv,
            "camera": {
                "permission": bool(s.get("camera_permission")),
                "status": face.get("camera_status", "off"),
                "active": bool(face.get("camera_active")),
                "index": s.get("camera_index", 0),
                "loss_shutdown": bool(s.get("camera_loss_shutdown", True)),
            },
            "drives": {
                "protection_enabled": drive_guard.is_enabled(),
                "detected": drive_guard.detect_drives(),
                "policy": drive_guard.get_policy(),
            },
            "notifications": self.notifications(),
        }

    # ── THE tool gate (called from main.py _execute_tool) ─────────────────────

    def authorize_tool(self, name: str, args: dict) -> str | None:
        """Return None to allow, or a human-readable denial reason."""
        try:
            if name == "security_control":
                return None                      # its handler enforces PIN itself
            s = config.load_settings()
            sensitive = set(s.get("sensitive_tools") or [])
            if name in sensitive:
                self._wait_for_fresh_voice()
                ok, reason = self.privacy.authorize_sensitive()
                if not ok:
                    self._notify("tool_denied", f"'{name}' blocked: {reason}")
                    return f"[Security] Operation refused. {reason}"
            denial = self._check_tool_paths(name, args or {})
            if denial:
                return denial
            return None
        except Exception as e:
            # fail closed for sensitive tools, open for general ones
            if name in set(config.get("sensitive_tools") or []):
                return f"[Security] Validation error — operation refused ({e})."
            return None

    def check_file_operation(self, params: dict) -> str | None:
        """Public drive check for actions/file_controller.py's dispatcher."""
        try:
            return self._check_tool_paths("file_controller", params or {})
        except Exception as e:
            return f"[Security] Validation error — operation refused ({e})."

    def _wait_for_fresh_voice(self) -> None:
        """The spoken command IS the freshest voice sample, but the verifier
        needs a moment to finish processing it. Without this grace, a short
        command ("open Notepad") reaches the gate before its own audio has
        been verified and every sensitive tool is refused. Bounded wait —
        never longer than 2 s, and only when voice is the deciding factor.
        Runs off the event loop (main.py calls the gate in an executor).
        """
        s = config.load_settings()
        if not s.get("voice_verification_enabled"):
            return
        if self._voice is None or not self._voice.running:
            return
        if not storage.has_blob("voice"):
            return
        if self.privacy.emergency_locked or self.privacy.status().get("pin_active"):
            return
        if storage.has_blob("face") and not self._face_status().get("authorized_present"):
            return                                 # face would block anyway
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if self._voice_status().get("verified"):
                return
            time.sleep(0.1)

    def _check_tool_paths(self, name: str, args: dict) -> str | None:
        if name == "file_controller":
            action = str(args.get("action", "")).lower().strip()
            op = _FC_OPS.get(action, "read")
            paths = []
            raw = args.get("path")
            if raw:
                p = _resolve_for_check(raw)
                if args.get("name") and action not in ("find",):
                    p = os.path.join(p, str(args["name"]))
                paths.append((p, op))
            dest = args.get("destination")
            if dest:
                dop = "create" if action in ("move", "copy") else "write"
                paths.append((_resolve_for_check(dest), dop))
                if action == "move" and paths:
                    paths.append((paths[0][0], "delete"))
            if action == "organize_desktop":
                paths.append((str(Path.home() / "Desktop"), "edit"))
            if not paths and action not in ("disk_usage",):
                return None
        elif name in _TOOL_OPS:
            op = _TOOL_OPS[name]
            paths = [(_resolve_for_check(args[k]), op)
                     for k in _PATH_KEYS if args.get(k)]
            if name == "open_app":
                # app_name is normally a program name, but "C:\\" or a folder
                # path is a drive target — check it like any other path.
                app = str(args.get("app_name") or "").strip()
                if app and (re.match(r"^[A-Za-z]:(?:[\\/]|$)", app) or os.path.isabs(app)):
                    paths.append((app, "read"))
        else:
            return None
        for p, op in paths:
            ok, reason = drive_guard.check(p, op, source=f"tool:{name}")
            if not ok:
                self._notify("tool_denied", f"'{name}' blocked: {reason}")
                return f"[Security] Operation refused. {reason}"
        return None

    # ── settings / enrollment operations (UI + dashboard + voice tool) ───────

    def set_privacy_mode(self, mode: str) -> tuple[bool, str]:
        if mode not in ("open", "strict"):
            return False, "Mode must be 'open' or 'strict'."
        if mode == "strict":
            if not storage.has_blob("face") or not storage.has_blob("voice"):
                return False, ("Strict mode needs a registered face AND voice. "
                               "Enroll both first (or stay in Open mode).")
            if not config.get("camera_permission"):
                return False, "Strict mode needs camera permission enabled."
        config.set_value("privacy_mode", mode)
        self._notify("security", f"Privacy mode set to {mode.upper()}.")
        self._sync_monitors()
        return True, f"Privacy mode: {mode}."

    def update_settings(self, fields: dict) -> tuple[bool, str]:
        """Validated settings update from UI / dashboard."""
        allowed_bool = ("face_tracking_enabled", "face_recognition_enabled",
                        "camera_permission", "voice_verification_enabled",
                        "camera_loss_shutdown")
        clean = {}
        for k, v in fields.items():
            if k in allowed_bool:
                clean[k] = bool(v)
            elif k == "camera_index":
                clean[k] = max(0, min(10, int(v)))
            elif k == "face_monitor_fps":
                clean[k] = max(1, min(30, int(v)))
            elif k in ("face_match_threshold", "voice_match_threshold"):
                clean[k] = max(0.1, min(0.99, float(v)))
        if clean.get("face_tracking_enabled") or clean.get("face_recognition_enabled"):
            merged = config.load_settings()
            merged.update(clean)
            if not merged.get("camera_permission"):
                return False, "Enable camera permission first — the camera never runs without it."
        if clean:
            config.save_settings(**clean)
        if "privacy_mode" in fields:
            return self.set_privacy_mode(str(fields["privacy_mode"]))
        self._sync_monitors()
        self._notify("security", "Security settings updated.")
        if "camera_permission" in clean and not clean["camera_permission"]:
            # Turning the security camera off is a camera loss too.
            self._camera_loss_shutdown("camera turned off in settings")
        return True, "Settings saved."

    def register_face(self, progress_cb) -> tuple[bool, str]:
        """Start face sample collection. progress_cb(done,total,message)."""
        if not config.get("camera_permission"):
            return False, "Camera permission is off."
        try:
            mon = self._ensure_face()
            from .face import ensure_models
            ensure_models(progress=lambda m: progress_cb(0, 12, m))
            if not mon.running:
                mon.start()
                time.sleep(1.0)
            if mon.camera_status != "active":
                return False, f"Camera not active ({mon.camera_status})."

            def done(d, t, templates, msg):
                if templates:
                    storage.save_blob("face", {"templates": templates,
                                               "enrolled_at": time.time()})
                    self._notify("security", "Face registered successfully.")
                    progress_cb(d, t, "Face registered.")
                else:
                    progress_cb(d, t, msg or "Look at the camera…")

            mon.begin_registration(done, samples=12)
            return True, "Registration started — look at the camera."
        except Exception as e:
            return False, str(e)

    def register_voice(self, progress_cb) -> tuple[bool, str]:
        v = self._ensure_voice()
        if not v.running:
            v.start()

        def done(d, t, templates, msg):
            if templates:
                storage.save_blob("voice", {"templates": templates,
                                            "enrolled_at": time.time()})
                self._notify("security", "Voice registered successfully.")
                progress_cb(d, t, "Voice registered.")
            else:
                progress_cb(d, t, msg or "Speak naturally…")

        v.begin_enrollment(done, segments=4)
        return True, "Voice enrollment started — speak naturally."

    def delete_identity(self, what: str) -> tuple[bool, str]:
        if what not in ("face", "voice", "pin"):
            return False, "Unknown identity item."
        if what == "pin":
            storage.delete_blob("pin")
        else:
            storage.delete_blob(what)
        if config.get("privacy_mode") == "strict":
            config.set_value("privacy_mode", "open")
            self._notify("security", "Strict mode disabled — identity incomplete.")
        self._notify("security", f"{what} identity data deleted.")
        return True, f"{what} data deleted."

    def set_pin(self, pin: str) -> tuple[bool, str]:
        try:
            storage.set_pin(pin)
            self._notify("security", "Backup PIN set.")
            return True, "PIN saved."
        except Exception as e:
            return False, str(e)

    def unlock_with_pin(self, pin: str) -> tuple[bool, str]:
        return self.privacy.unlock_with_pin(pin)

    def emergency_lock(self) -> str:
        self.privacy.emergency_lock()
        return "Emergency privacy lock engaged."

    def set_drive_protection(self, enabled: bool) -> tuple[bool, str]:
        drive_guard.set_enabled(bool(enabled))
        state = "ENABLED — all drives DENIED until granted" if enabled else "disabled"
        self._notify("security", f"Drive protection {state}.")
        return True, f"Drive protection {state}."

    def set_drive_permission(self, drive: str, **perms) -> tuple[bool, str]:
        try:
            policy = drive_guard.set_permission(drive, **perms)
            granted = [k for k, v in policy.items() if v]
            self._notify("drive_permission",
                         f"Drive {drive.upper()}: {', '.join(granted) or 'ALL DENIED'}")
            if policy.get("access") and not any(policy.get(k) for k in
                                                ("read", "write", "create", "edit", "delete")):
                return True, (f"Drive {drive.upper()} updated. ACCESS is the master gate — "
                              "nothing is usable yet. Tick READ (and any other rights "
                              "you want) for this drive in Drive Permission Management.")
            return True, f"Drive {drive.upper()} updated."
        except Exception as e:
            return False, str(e)