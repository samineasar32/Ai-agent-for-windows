"""FastAPI routes for the remote Security & Privacy dashboard.

Registered with ONE call from dashboard/server.py _build_app. Everything is
additive: if the security package is missing the existing dashboard is
completely unaffected. All endpoints sit behind the dashboard's existing
bearer-token auth. Destructive security changes additionally require the
backup PIN once one is set — a paired phone alone cannot disarm protection.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from security import get_manager
from security import storage

_HTML_PATH = Path(__file__).resolve().parent.parent / "dashboard" / "static" / "security.html"


def _weakens(action: str, body: dict) -> bool:
    if action == "set_mode":
        return body.get("mode") == "open"
    if action == "drive_protection":
        return not body.get("enabled")
    if action == "update_settings":
        f = body.get("fields") or {}
        return any(v is False for k, v in f.items()
                   if k in ("camera_permission", "face_tracking_enabled",
                            "face_recognition_enabled", "voice_verification_enabled"))
    if action == "drive_permission":
        perms = body.get("perms") or {}
        return perms.get("access") is False or any(v is False for v in perms.values())
    return False


def register_security_routes(app, auth, broadcast) -> None:
    mgr = get_manager()
    try:
        _loop = asyncio.get_running_loop()
    except RuntimeError:
        _loop = None

    def _push_threadsafe(msg: dict) -> None:
        try:
            if _loop is not None:
                _loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(broadcast(msg)))
        except Exception:
            pass

    mgr.add_listener(lambda ev: _push_threadsafe({"type": "security", **ev}))

    @app.get("/security", response_class=HTMLResponse)
    async def security_page():
        try:
            return HTMLResponse(_HTML_PATH.read_text(encoding="utf-8"))
        except Exception:
            return HTMLResponse("<h3>security.html missing</h3>", status_code=500)

    @app.get("/api/security")
    async def security_status(req: Request):
        if not auth(req):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return JSONResponse(await asyncio.to_thread(mgr.status))

    @app.get("/api/security/frame")
    async def security_frame(req: Request):
        if not auth(req):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        jpeg = mgr.camera_frame_jpeg()
        if not jpeg:
            return JSONResponse({"error": "camera inactive"}, status_code=404)
        return Response(jpeg, media_type="image/jpeg",
                        headers={"Cache-Control": "no-store"})

    @app.post("/api/security")
    async def security_action(req: Request):
        if not auth(req):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        try:
            body = await req.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "bad json"}, status_code=400)
        action = str(body.get("action") or "")

        # Grants AND revocations of drive rights are explicit decisions.
        needs_pin = (action in ("delete_identity", "drive_permission")
                     or _weakens(action, body))
        if needs_pin and storage.has_pin():
            if not storage.verify_pin(str(body.get("pin") or "")):
                return JSONResponse(
                    {"ok": False, "error": "Backup PIN required for this change."},
                    status_code=403)

        def _run() -> tuple[bool, str]:
            if action == "status":
                return True, "ok"
            if action == "set_mode":
                return mgr.set_privacy_mode(str(body.get("mode") or ""))
            if action == "update_settings":
                return mgr.update_settings(body.get("fields") or {})
            if action == "set_pin":
                return mgr.set_pin(str(body.get("new_pin") or ""))
            if action == "unlock_pin":
                return mgr.unlock_with_pin(str(body.get("pin") or ""))
            if action == "emergency_lock":
                return True, mgr.emergency_lock()
            if action == "delete_identity":
                return mgr.delete_identity(str(body.get("what") or ""))
            if action == "drive_protection":
                return mgr.set_drive_protection(bool(body.get("enabled")))
            if action == "drive_permission":
                return mgr.set_drive_permission(str(body.get("drive") or ""),
                                                **(body.get("perms") or {}))
            if action == "register_face":
                return mgr.register_face(
                    lambda d, t, m: _push_threadsafe(
                        {"type": "security", "kind": "register_face",
                         "done": d, "total": t, "message": m}))
            if action == "register_voice":
                return mgr.register_voice(
                    lambda d, t, m: _push_threadsafe(
                        {"type": "security", "kind": "register_voice",
                         "done": d, "total": t, "message": m}))
            return False, f"Unknown action: {action}"

        ok, msg = await asyncio.to_thread(_run)
        return JSONResponse({"ok": ok, "message": msg},
                            status_code=200 if ok else 400)