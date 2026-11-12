"""Centralized drive permission enforcement.

Every JARVIS-initiated file operation must pass `check()` before it runs.
Enforcement layers:
  1. check(path, op)          — called by file_controller and the tool gate.
  2. subprocess / os.startfile wrappers — shell commands cannot bypass (1).

Design rules:
  * Master switch `drive_protection_enabled`.  OFF (default) = legacy JARVIS
    behaviour, untouched.  ON = every drive defaults to DENIED until the user
    explicitly grants it in the dashboard.  Permissions are never granted
    implicitly or silently.
  * Revoking access or any single right takes effect on the very next check
    (policy is read live, no caching of decisions).
  * Paths are canonicalized with os.path.realpath (resolves symlinks/junctions
    and ".." traversal) BEFORE the drive is extracted, so neither
    "D:\\..\\C:\\x" style tricks nor symlink escapes can cross a boundary.
  * UNC / network paths are denied while protection is on (no drive policy
    can describe them).
  * The application's own install directory and the Python runtime are exempt:
    drive protection governs USER DATA access, not JARVIS's ability to run.
"""
from __future__ import annotations

import ctypes
import os
import re
import string
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import config

_LOCK = threading.RLock()
_denial_listeners: list = []

_APP_ROOTS: list[str] = []


def _app_roots() -> list[str]:
    global _APP_ROOTS
    if not _APP_ROOTS:
        roots = {str(config._BASE_DIR), sys.prefix, sys.base_prefix}
        _APP_ROOTS = [os.path.normcase(os.path.realpath(r)) for r in roots if r]
    return _APP_ROOTS


def on_denial(callback) -> None:
    """Register fn(drive, op, path, source) for UI / dashboard alerts."""
    with _LOCK:
        _denial_listeners.append(callback)


def _notify_denial(drive: str, op: str, path: str, source: str) -> None:
    for cb in list(_denial_listeners):
        try:
            cb(drive, op, path, source)
        except Exception:
            pass


# ── Drive discovery ──────────────────────────────────────────────────────────

def detect_drives() -> list[dict]:
    """Available drives with label/type. Windows-first, psutil fallback."""
    drives: list[dict] = []
    if os.name == "nt":
        try:
            mask = ctypes.windll.kernel32.GetLogicalDrives()
            for i, letter in enumerate(string.ascii_uppercase):
                if not mask & (1 << i):
                    continue
                root = f"{letter}:\\"
                dtype = ctypes.windll.kernel32.GetDriveTypeW(root)
                kind = {2: "Removable", 3: "Fixed", 4: "Network",
                        5: "CD-ROM", 6: "RAM disk"}.get(dtype, "Unknown")
                label = ""
                try:
                    buf = ctypes.create_unicode_buffer(261)
                    ctypes.windll.kernel32.GetVolumeInformationW(
                        root, buf, 260, None, None, None, None, 0)
                    label = buf.value
                except Exception:
                    pass
                free = total = 0
                try:
                    import shutil
                    total, _used, free = shutil.disk_usage(root)
                except Exception:
                    pass
                drives.append({"drive": letter, "root": root, "type": kind,
                               "label": label, "total": total, "free": free})
            return drives
        except Exception:
            pass
    try:
        import psutil
        seen = set()
        for p in psutil.disk_partitions(all=False):
            letter = os.path.splitdrive(p.mountpoint)[0].rstrip(":").upper()
            if letter and letter not in seen:
                seen.add(letter)
                drives.append({"drive": letter, "root": p.mountpoint,
                               "type": p.fstype, "label": "",
                               "total": 0, "free": 0})
    except Exception:
        pass
    return drives


# ── Policy ───────────────────────────────────────────────────────────────────

def is_enabled() -> bool:
    return bool(config.get("drive_protection_enabled"))


def set_enabled(enabled: bool) -> None:
    """Master switch. Turning ON seeds every detected drive as DENIED."""
    with _LOCK:
        settings = config.load_settings()
        policy = dict(settings.get("drives") or {})
        if enabled:
            for d in detect_drives():
                policy.setdefault(d["drive"], _denied_policy())
        config.save_settings(drive_protection_enabled=bool(enabled), drives=policy)


def _denied_policy() -> dict:
    return {op: False for op in config.DRIVE_OPS}


def get_policy() -> dict:
    """Live policy for every detected drive; unlisted drives are DENIED."""
    with _LOCK:
        stored = config.load_settings().get("drives") or {}
        out = {}
        letters = {d["drive"] for d in detect_drives()} | set(stored.keys())
        for letter in sorted(letters):
            p = _denied_policy()
            p.update({k: bool(v) for k, v in (stored.get(letter) or {}).items()
                      if k in config.DRIVE_OPS})
            out[letter] = p
        return out


def set_permission(drive: str, **perms) -> dict:
    """Explicit grant/revoke from the UI/dashboard only.

    Granting any right requires access=True in the same call or already
    stored. Revoking access zeroes every right immediately.
    """
    drive = str(drive).upper().rstrip(":\\/")
    if len(drive) != 1 or drive not in string.ascii_uppercase:
        raise ValueError(f"Invalid drive: {drive}")
    unknown = set(perms) - set(config.DRIVE_OPS)
    if unknown:
        raise ValueError(f"Unknown permission: {unknown}")
    with _LOCK:
        policy = config.load_settings().get("drives") or {}
        cur = _denied_policy()
        cur.update(policy.get(drive) or {})
        for k, v in perms.items():
            cur[k] = bool(v)
        if not cur["access"]:
            cur = _denied_policy()
        elif any(cur[op] for op in config.DRIVE_OPS if op != "access"):
            cur["access"] = True
        policy[drive] = cur
        config.save_settings(drives=policy)
        return dict(cur)


# ── Path checking ────────────────────────────────────────────────────────────

_DRIVE_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]):[\\/]")


def _canonical(path: str) -> str:
    p = os.path.expanduser(str(path).strip().strip('"').strip("'"))
    if not os.path.isabs(p):
        p = os.path.join(os.getcwd(), p)
    return os.path.normcase(os.path.realpath(p))


def _is_app_path(canon: str) -> bool:
    return any(canon == r or canon.startswith(r + os.sep) for r in _app_roots())


def check(path, op: str = "read", source: str = "tool") -> tuple[bool, str]:
    """Central permission check. Returns (allowed, reason).

    `op` is one of read/write/create/edit/delete. Fail-closed: anything we
    cannot understand is denied while protection is enabled.

    Semantics:
      * A drive with an EXPLICIT policy entry is always enforced (access +
        the requested right), whether or not the master switch is on — a
        grant or restriction the user typed must mean something immediately.
      * A drive with NO entry: master ON = denied (default-deny), master
        OFF = legacy JARVIS behaviour (allowed).
    """
    if op not in config.DRIVE_OPS or op == "access":
        op = "read"
    try:
        raw = str(path)
        if raw.startswith("\\\\") or raw.startswith("//"):
            if is_enabled():
                _notify_denial("UNC", op, raw, source)
                return False, "Network/UNC paths are not permitted by drive policy."
            return True, "drive protection off"
        canon = _canonical(raw)
        if _is_app_path(canon):
            return True, "application path"
        drive = os.path.splitdrive(canon)[0].rstrip(":").upper()
        if not drive:
            _notify_denial("?", op, raw, source)
            return False, "Path has no identifiable drive — denied."
        stored = config.load_settings().get("drives") or {}
        entry = stored.get(drive)
        if entry is None:
            if not is_enabled():
                return True, "no drive policy (legacy behaviour)"
            policy = _denied_policy()
        else:
            policy = _denied_policy()
            policy.update({k: bool(v) for k, v in entry.items()
                           if k in config.DRIVE_OPS})
        if not policy["access"]:
            _notify_denial(drive, op, raw, source)
            return False, f"Drive {drive}: is restricted (ACCESS DENIED)."
        if not policy.get(op, False):
            _notify_denial(drive, op, raw, source)
            return False, (f"Drive {drive}: '{op}' permission is not granted. "
                           "Tick the matching right in Drive Permission Management.")
        return True, f"{drive}: {op} allowed"
    except Exception as e:
        _notify_denial("?", op, str(path), source)
        return False, f"Path could not be validated ({e}) — denied."


def require(path, op: str = "read", source: str = "tool") -> None:
    ok, reason = check(path, op, source)
    if not ok:
        raise PermissionError(f"[DriveGuard] {reason}")


def is_granted_target(path) -> bool:
    """True when the path lies on a drive the user explicitly granted.

    Used by file_controller to EXTEND its safe roots beyond the home folder
    (D:/E: become reachable only after an explicit grant). Explicit grants
    count even when the master protection switch is off.
    """
    try:
        canon = _canonical(str(path))
        drive = os.path.splitdrive(canon)[0].rstrip(":").upper()
        entry = (config.load_settings().get("drives") or {}).get(drive) or {}
        return bool(entry.get("access") and entry.get("read"))
    except Exception:
        return False


# ── Shell / startfile enforcement ────────────────────────────────────────────

_guards_installed = False


def _command_text(args) -> str:
    if isinstance(args, (list, tuple)):
        return " ".join(str(a) for a in args)
    return str(args)


def _exec_prefix(cmd: str) -> str:
    """The executable portion of a shell string (first token, quote-aware)."""
    s = cmd.lstrip()
    if s.startswith('"'):
        end = s.find('"', 1)
        return s[1:end] if end > 0 else s
    return s.split(" ", 1)[0] if s else ""


_DELETE_VERBS = {"del", "erase", "rm", "rmdir", "rd", "remove-item", "unlink"}
_EDIT_VERBS = {"ren", "rename", "move", "mv", "set-content", "add-content",
               "replace", "rename-item", "move-item"}
_CREATE_VERBS = {"mkdir", "md", "new-item", "copy", "cp", "xcopy", "robocopy",
                 "copy-item", "out-file", "ni"}


def _command_op(cmd: str) -> str:
    """Best-effort operation class for a shell command (fail towards strict)."""
    s = cmd.strip().strip('"').lower()
    # skip interpreter prefixes: cmd /c ..., powershell -command ...
    tokens = re.split(r"[\s\"']+", s)
    verb = ""
    for t in tokens:
        if t in ("cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "bash", "sh"):
            continue
        if t in ("/c", "/k", "-command", "-c", "-encodedcommand"):
            continue
        verb = t
        break
    verb = os.path.basename(verb)
    if verb.endswith(".exe"):
        verb = verb[:-4]
    if verb in _DELETE_VERBS:
        return "delete"
    if verb in _EDIT_VERBS:
        return "edit"
    if verb in _CREATE_VERBS:
        return "create"
    if ">" in cmd:
        return "write"
    return "read"


def _vet_command(args, cwd=None, source="shell") -> None:
    """Raise PermissionError when a command touches a restricted drive.

    The executable itself may live on a restricted drive (running a program
    is not reading user data); every OTHER drive reference — arguments,
    redirection targets, the working directory — is checked. Explicit drive
    policies are enforced even when the master switch is off; with no policy
    and the switch off, check() allows everything (legacy behaviour).
    """
    if cwd:
        require(cwd, "read", source)
    cmd = _command_text(args)
    op = _command_op(cmd)
    exe = os.path.normcase(os.path.realpath(_exec_prefix(cmd))) if cmd else ""
    for m in _DRIVE_RE.finditer(cmd):
        # Reconstruct the full path token containing this drive reference.
        start = m.start()
        # include a leading quote if present
        tok_start = start
        while tok_start > 0 and cmd[tok_start - 1] not in ' \t"\'':
            tok_start -= 1
        tok_end = start + 3
        while tok_end < len(cmd) and cmd[tok_end] not in '"\'|&;<>\r\n':
            tok_end += 1
        token = cmd[tok_start:tok_end].strip().strip('"').strip("'")
        if not token:
            token = cmd[start:tok_end]
        canon = _canonical(token)
        if exe and (canon == exe or exe.startswith(canon)):
            continue  # the program being executed, not a data path
        if _is_app_path(canon):
            continue
        require(token, op, source)
        if op in ("create", "edit", "delete", "write"):
            require(token, "read", source)


def install_process_guards() -> None:
    """Wrap subprocess.Popen / os.startfile / os.system once.

    Follows the existing main.py precedent of patching Popen globally.  The
    wrapper chains whatever patch is already in place (CREATE_NO_WINDOW),
    it does not replace it.
    """
    global _guards_installed
    with _LOCK:
        if _guards_installed:
            return
        _guards_installed = True

        _OrigPopen = subprocess.Popen

        class _GuardedPopen(_OrigPopen):
            def __init__(self, args, *a, **kw):
                _vet_command(args, kw.get("cwd"), source="subprocess")
                super().__init__(args, *a, **kw)

        subprocess.Popen = _GuardedPopen

        if hasattr(os, "startfile"):
            _orig_startfile = os.startfile

            def _guarded_startfile(path, *a, **kw):
                require(path, "read", "os.startfile")
                return _orig_startfile(path, *a, **kw)

            os.startfile = _guarded_startfile

        _orig_system = os.system

        def _guarded_system(cmd):
            _vet_command(cmd, source="os.system")
            return _orig_system(cmd)

        os.system = _guarded_system