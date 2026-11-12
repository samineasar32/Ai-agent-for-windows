"""End-to-end integration tests: existing JARVIS components + security layer.

Run from the project root:  python -m security.tests.test_integration
Uses a temp security config; the only real files touched are test files this
script creates (and removes) inside the user's temp directory.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from security import config, storage, drive_guard
import security


class _TempSecurityConfig(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self._old = (config.SETTINGS_FILE, config.DATA_DIR, storage._fernet)
        config.SETTINGS_FILE = base / "security_settings.json"
        config.DATA_DIR = base / "data"
        storage._fernet = None
        drive_guard._APP_ROOTS = []
        security._manager = None            # fresh manager per test

    def tearDown(self):
        config.SETTINGS_FILE, config.DATA_DIR, storage._fernet = self._old
        drive_guard._APP_ROOTS = []
        security._manager = None
        self._tmp.cleanup()


class TestFileControllerIntegration(_TempSecurityConfig):
    """The REAL actions/file_controller.py, gated by the REAL drive policy."""

    def setUp(self):
        super().setUp()
        from actions.file_controller import file_controller
        self.fc = file_controller
        # test file lives under home (temp dir), like normal JARVIS targets
        self.f = Path(tempfile.gettempdir()) / "jarvis_sec_itest.txt"
        self.f.write_text("hello security", encoding="utf-8")
        self.addCleanup(lambda: self.f.unlink(missing_ok=True))
        self.home_drive = os.path.splitdrive(str(self.f))[0].rstrip(":").upper()

    def _grant(self, **perms):
        drive_guard.set_permission(self.home_drive, **perms)

    def test_legacy_when_disabled(self):
        out = self.fc({"action": "read", "path": str(self.f)})
        self.assertIn("hello security", out)

    def test_denied_drive_blocks_read(self):
        drive_guard.set_enabled(True)
        out = self.fc({"action": "read", "path": str(self.f)})
        self.assertIn("refused", out.lower())
        self.assertNotIn("hello security", out)

    def test_grant_read_only(self):
        drive_guard.set_enabled(True)
        self._grant(access=True, read=True)
        out = self.fc({"action": "read", "path": str(self.f)})
        self.assertIn("hello security", out)
        out = self.fc({"action": "write", "path": str(self.f), "content": "x"})
        self.assertIn("refused", out.lower())
        out = self.fc({"action": "delete", "path": str(self.f)})
        self.assertIn("refused", out.lower())
        self.assertTrue(self.f.exists())

    def test_grant_write_create_delete(self):
        drive_guard.set_enabled(True)
        self._grant(access=True, read=True, write=True, create=True, delete=True)
        out = self.fc({"action": "write", "path": str(self.f), "content": "updated"})
        self.assertNotIn("refused", out.lower())
        self.assertIn("updated", self.f.read_text(encoding="utf-8"))
        newf = self.f.parent / "jarvis_sec_itest_new.txt"
        out = self.fc({"action": "create_file", "path": str(newf), "content": "n"})
        self.addCleanup(lambda: newf.unlink(missing_ok=True))
        self.assertTrue(newf.exists(), out)
        out = self.fc({"action": "delete", "path": str(newf)})
        self.assertNotIn("refused", out.lower())

    def test_revoke_blocks_immediately(self):
        drive_guard.set_enabled(True)
        self._grant(access=True, read=True)
        self.assertIn("hello security", self.fc({"action": "read", "path": str(self.f)}))
        self._grant(access=False)
        out = self.fc({"action": "read", "path": str(self.f)})
        self.assertIn("refused", out.lower())

    def test_open_c_drive_command_refused(self):
        """'Open C drive' arrives as file_controller list or open_app path."""
        drive_guard.set_enabled(True)
        out = self.fc({"action": "list", "path": f"{self.home_drive}:\\"})
        self.assertIn("refused", out.lower())
        mgr = security.get_manager()
        denial = mgr.authorize_tool("open_app", {"app_name": "explorer",
                                                 "path": f"{self.home_drive}:\\"})
        self.assertIsNotNone(denial)


class TestShellGuards(_TempSecurityConfig):
    def test_subprocess_blocked_and_allowed(self):
        drive_guard.install_process_guards()
        drive_guard.set_enabled(True)
        f = Path(tempfile.gettempdir()) / "jarvis_sec_shell.txt"
        f.write_text("data", encoding="utf-8")
        self.addCleanup(lambda: f.unlink(missing_ok=True))
        drive_letter = os.path.splitdrive(str(f))[0].rstrip(":").upper()
        with self.assertRaises(PermissionError):
            subprocess.run(f'cmd /c type "{f}"', shell=True, capture_output=True)
        drive_guard.set_permission(drive_letter, access=True, read=True)
        r = subprocess.run(f'cmd /c type "{f}"', shell=True, capture_output=True)
        self.assertIn(b"data", r.stdout)
        # delete on a read-only drive must still be blocked
        with self.assertRaises(PermissionError):
            subprocess.run(f'cmd /c del "{f}"', shell=True, capture_output=True)
        self.assertTrue(f.exists())

    def test_startfile_blocked(self):
        if not hasattr(os, "startfile"):
            self.skipTest("not Windows")
        drive_guard.install_process_guards()
        drive_guard.set_enabled(True)
        with self.assertRaises(PermissionError):
            os.startfile("C:\\Windows\\win.ini")

    def test_guards_inert_when_disabled(self):
        drive_guard.install_process_guards()
        drive_guard.set_enabled(False)
        r = subprocess.run("cmd /c echo legacy-ok", shell=True, capture_output=True)
        self.assertIn(b"legacy-ok", r.stdout)


class TestToolGate(_TempSecurityConfig):
    def test_general_tools_unaffected(self):
        mgr = security.get_manager()
        drive_guard.set_enabled(True)
        self.assertIsNone(mgr.authorize_tool("web_search", {"query": "weather"}))
        self.assertIsNone(mgr.authorize_tool("weather_report", {}))

    def test_emergency_lock_blocks_sensitive(self):
        mgr = security.get_manager()
        mgr.start()
        self.assertIsNone(mgr.authorize_tool("file_controller",
                                             {"action": "list", "path": "desktop"}))
        mgr.emergency_lock()
        denial = mgr.authorize_tool("file_controller",
                                    {"action": "list", "path": "desktop"})
        self.assertIsNotNone(denial)
        self.assertIn("Emergency", denial)
        # general commands still work under emergency lock
        self.assertIsNone(mgr.authorize_tool("web_search", {"query": "news"}))
        # security tool itself always reachable
        self.assertIsNone(mgr.authorize_tool("security_control", {"action": "status"}))
        storage.set_pin("7777")
        ok, _ = mgr.unlock_with_pin("7777")
        self.assertTrue(ok)


class TestCameraLossShutdown(_TempSecurityConfig):
    def _mgr(self):
        mgr = security.get_manager()
        config.save_settings(camera_permission=True, face_tracking_enabled=True)
        return mgr

    def test_camera_loss_shuts_down_agent(self):
        mgr = self._mgr()
        calls = []
        mgr.set_shutdown_hook(lambda reason: calls.append(reason))
        mgr._on_event("camera_active", {})
        mgr._on_event("camera_disconnected", {})
        self.assertEqual(len(calls), 1)
        self.assertTrue(mgr.privacy.emergency_locked)
        # a second event must not fire the hook again
        mgr._on_event("camera_disconnected", {})
        self.assertEqual(len(calls), 1)

    def test_no_shutdown_before_camera_was_active(self):
        mgr = self._mgr()
        calls = []
        mgr.set_shutdown_hook(lambda reason: calls.append(reason))
        mgr._on_event("camera_disconnected", {})   # e.g. no camera at boot
        self.assertEqual(calls, [])
        self.assertFalse(mgr.privacy.emergency_locked)

    def test_setting_disables_shutdown(self):
        mgr = self._mgr()
        config.save_settings(camera_loss_shutdown=False)
        calls = []
        mgr.set_shutdown_hook(lambda reason: calls.append(reason))
        mgr._on_event("camera_active", {})
        mgr._on_event("camera_disconnected", {})
        self.assertEqual(calls, [])

    def test_turning_camera_off_in_settings_shuts_down(self):
        mgr = self._mgr()
        calls = []
        mgr.set_shutdown_hook(lambda reason: calls.append(reason))
        mgr._on_event("camera_active", {})
        mgr.update_settings({"camera_permission": False})
        self.assertEqual(len(calls), 1)


class TestOpenAppDrive(_TempSecurityConfig):
    def test_gate_and_handler(self):
        drive_guard.install_process_guards()
        mgr = security.get_manager()
        from actions import open_app as oa
        # ACCESS alone is the master gate — READ is still required
        drive_guard.set_permission("C", access=True, read=False)
        self.assertIsNotNone(mgr.authorize_tool("open_app", {"app_name": "C:\\"}))
        out = oa.open_app({"app_name": "C:\\"})
        self.assertIn("status=failed", out)
        self.assertIn("read", out)
        # explicit grant works even with the master switch OFF
        drive_guard.set_enabled(False)
        drive_guard.set_permission("C", access=True, read=True)
        self.assertIsNone(mgr.authorize_tool("open_app", {"app_name": "C:\\"}))
        opened = []
        orig = os.startfile
        os.startfile = lambda p, *a, **k: opened.append(p)
        try:
            out = oa.open_app({"app_name": "C:"})
        finally:
            os.startfile = orig
        self.assertEqual(opened, ["C:" + os.sep])
        self.assertIn("status=done", out)


class TestDashboardAPI(_TempSecurityConfig):
    def test_routes(self):
        from fastapi.testclient import TestClient
        from dashboard.server import DashboardServer
        srv = DashboardServer()
        import time as _t
        srv._tokens["test-token"] = _t.time()
        client = TestClient(srv._build_app())
        # unauthenticated is rejected
        self.assertEqual(client.get("/api/security").status_code, 401)
        H = {"Authorization": "Bearer test-token"}
        r = client.get("/api/security", headers=H)
        self.assertEqual(r.status_code, 200)
        self.assertIn("drives", r.json())
        # security page serves
        self.assertEqual(client.get("/security").status_code, 200)
        # enable protection via API → all denied
        r = client.post("/api/security", headers=H,
                        json={"action": "drive_protection", "enabled": True})
        self.assertTrue(r.json()["ok"])
        pol = client.get("/api/security", headers=H).json()["drives"]["policy"]
        self.assertTrue(all(not any(p.values()) for p in pol.values()))
        # grant D- style drive explicitly (use first detected drive)
        letter = next(iter(pol))
        r = client.post("/api/security", headers=H,
                        json={"action": "drive_permission", "drive": letter,
                              "perms": {"access": True, "read": True}})
        self.assertTrue(r.json()["ok"])
        pol = client.get("/api/security", headers=H).json()["drives"]["policy"]
        self.assertTrue(pol[letter]["read"])
        self.assertFalse(pol[letter]["delete"])
        # once a PIN exists, weakening changes need it
        client.post("/api/security", headers=H,
                    json={"action": "set_pin", "new_pin": "5555"})
        r = client.post("/api/security", headers=H,
                        json={"action": "drive_protection", "enabled": False})
        self.assertEqual(r.status_code, 403)
        r = client.post("/api/security", headers=H,
                        json={"action": "drive_protection", "enabled": False,
                              "pin": "5555"})
        self.assertTrue(r.json()["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)