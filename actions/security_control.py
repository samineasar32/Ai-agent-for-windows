"""Voice tools for the Security & Privacy subsystem (auto-discovered).

Lets the user ask JARVIS for security status, engage the emergency privacy
lock, and unlock with the backup PIN by voice. Drive permissions and mode
changes are deliberately NOT offered here — granting access must be an
explicit UI/dashboard action, never something the model can talk itself into.
"""
from __future__ import annotations


def security_control(parameters: dict = None, player=None, **kwargs) -> str:
    params = parameters or {}
    action = str(params.get("action", "status")).lower().strip()
    try:
        from security import get_manager
        mgr = get_manager()
    except Exception as e:
        return f"Security subsystem is unavailable: {e}"

    if action == "status":
        st = mgr.quick_status()
        priv, face, voice = st["privacy"], st["face"], st["voice"]
        locked = priv.get("privacy_locked") or priv.get("emergency_locked")
        lines = [
            f"Privacy mode: {priv.get('mode', 'open').upper()}.",
            f"Privacy lock: {'LOCKED' if locked else 'unlocked'}."
            + (f" Reason: {priv.get('lock_reason')}." if locked and priv.get("lock_reason") else ""),
            f"Face: {'authorized user present' if face.get('authorized_present') else 'authorized user not detected'}; "
            f"camera {face.get('camera_status', 'off')}.",
            f"Voice: {'verified' if voice.get('verified') else 'not verified'}.",
        ]
        if face.get("unknown_present"):
            lines.append("Warning: an unknown person is in camera view.")
        from security import drive_guard
        if drive_guard.is_enabled():
            pol = drive_guard.get_policy()
            allowed = [f"{d}:" for d, p in pol.items() if p.get("access")]
            lines.append("Drive protection ON. Allowed drives: "
                         + (", ".join(allowed) if allowed else "none — all restricted."))
        else:
            lines.append("Drive protection is off.")
        return " ".join(lines)

    if action == "lock":
        return mgr.emergency_lock()

    if action == "unlock":
        pin = str(params.get("pin", "")).strip()
        if not pin:
            return ("To unlock by voice I need the backup PIN. Say: unlock privacy, "
                    "PIN <your pin>. Or unlock from the Security & Privacy panel.")
        ok, msg = mgr.unlock_with_pin(pin)
        return msg

    if action == "drives":
        from security import drive_guard
        pol = drive_guard.get_policy()
        if not drive_guard.is_enabled():
            return ("Drive protection is currently off — manage it in the "
                    "Security & Privacy panel.")
        rows = []
        for d, p in sorted(pol.items()):
            rights = ",".join(k for k in ("read", "write", "create", "edit", "delete") if p.get(k))
            rows.append(f"{d}: {'ALLOWED (' + rights + ')' if p.get('access') else 'DENIED'}")
        return "Drive permissions — " + "; ".join(rows) + \
               ". Changes can only be made in the Security & Privacy panel."

    return f"Unknown security action: '{action}'. Use status, lock, unlock or drives."


TOOL = {
    "name": "security_control",
    "description": (
        "Security & privacy status and locks. Use for: 'security status', "
        "'emergency lock' / 'lock privacy' (action=lock), 'unlock privacy with "
        "PIN 1234' (action=unlock, pin=1234), 'which drives can you access' "
        "(action=drives). Drive permissions and privacy-mode changes can ONLY "
        "be changed by the user in the Security & Privacy panel — never attempt "
        "to grant access through this tool."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "status | lock | unlock | drives",
            },
            "pin": {
                "type": "STRING",
                "description": "Backup PIN, only when the user explicitly provides it for unlock",
            },
        },
        "required": ["action"],
    },
    "handler": security_control,
}