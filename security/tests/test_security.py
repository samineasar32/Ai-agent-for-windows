"""Unit tests for the JARVIS security subsystem.

Run from the project root:  python -m security.tests.test_security
All state is redirected to a temp directory — real config is never touched.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from security import config, storage, drive_guard, privacy


class _TempConfig(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self._old = (config.SETTINGS_FILE, config.DATA_DIR, storage._fernet)
        config.SETTINGS_FILE = base / "security_settings.json"
        config.DATA_DIR = base / "data"
        storage._fernet = None
        drive_guard._APP_ROOTS = []

    def tearDown(self):
        config.SETTINGS_FILE, config.DATA_DIR, storage._fernet = self._old
        drive_guard._APP_ROOTS = []
        self._tmp.cleanup()


class TestStorage(_TempConfig):
    def test_blob_roundtrip_encrypted(self):
        storage.save_blob("face", {"templates": [[0.1, 0.2]]})
        raw = (config.DATA_DIR / "face.enc").read_bytes()
        self.assertNotIn(b"templates", raw)
        self.assertEqual(storage.load_blob("face")["templates"], [[0.1, 0.2]])

    def test_pin(self):
        storage.set_pin("12345")
        self.assertTrue(storage.has_pin())
        self.assertTrue(storage.verify_pin("12345"))
        self.assertFalse(storage.verify_pin("00000"))

    def test_pin_min_length(self):
        with self.assertRaises(ValueError):
            storage.set_pin("1")


class TestDriveGuard(_TempConfig):
    def setUp(self):
        super().setUp()
        # deterministic policy: C denied, D read+write, E read-only
        config.save_settings(drive_protection_enabled=True, drives={
            "C": {op: False for op in config.DRIVE_OPS},
            "D": {"access": True, "read": True, "write": True,
                  "create": False, "edit": False, "delete": False},
            "E": {"access": True, "read": True, "write": False,
                  "create": False, "edit": False, "delete": False},
        })

    def test_denied_drive(self):
        ok, reason = drive_guard.check("C:\\Users\\me\\secret.txt", "read")
        self.assertFalse(ok)
        self.assertIn("restricted", reason)

    def test_default_deny_unknown_drive(self):
        ok, _ = drive_guard.check("E:\\file.txt", "write")
        self.assertFalse(ok)
        ok, _ = drive_guard.check("Z:\\anything", "read")
        self.assertFalse(ok)

    def test_granted_ops(self):
        self.assertTrue(drive_guard.check("D:\\docs\\a.txt", "read")[0])
        self.assertTrue(drive_guard.check("D:\\docs\\a.txt", "write")[0])
        self.assertFalse(drive_guard.check("D:\\docs\\a.txt", "delete")[0])
        self.assertTrue(drive_guard.check("E:\\a.txt", "read")[0])
        self.assertFalse(drive_guard.check("E:\\a.txt", "write")[0])

    def test_traversal_cannot_escape_granted_drive(self):
        ok, _ = drive_guard.check("D:\\docs\\..\\..\\Windows\\system32", "read")
        # D:\..\Windows stays on D: (Windows does not cross drives via ..),
        # but a traversal that lands on the granted drive root is still D:.
        # The real escape vector is a crafted absolute reference:
        ok2, _ = drive_guard.check("D:\\docs\\../../C:/Windows/win.ini", "read")
        self.assertFalse(ok2)

    def test_symlink_escape_blocked(self):
        base = Path(self._tmp.name)
        target = base / "restricted"
        target.mkdir()
        link_dir = base / "granted"
        link_dir.mkdir()
        link = link_dir / "escape"
        try:
            os.symlink(target, link, target_is_directory=True)
        except OSError:
            self.skipTest("symlink privilege not available")
        # map both dirs onto drives via policy: fake by checking canonicalization
        canon = drive_guard._canonical(str(link))
        self.assertEqual(canon, drive_guard._canonical(str(target)))

    def test_unc_denied(self):
        self.assertFalse(drive_guard.check("\\\\server\\share\\x", "read")[0])

    def test_revoke_immediate(self):
        self.assertTrue(drive_guard.check("D:\\a.txt", "read")[0])
        drive_guard.set_permission("D", access=False)
        self.assertFalse(drive_guard.check("D:\\a.txt", "read")[0])

    def test_revoke_single_right_immediate(self):
        self.assertTrue(drive_guard.check("D:\\a.txt", "write")[0])
        drive_guard.set_permission("D", write=False)
        self.assertFalse(drive_guard.check("D:\\a.txt", "write")[0])
        self.assertTrue(drive_guard.check("D:\\a.txt", "read")[0])

    def test_disabled_means_legacy_for_unlisted_drives(self):
        drive_guard.set_enabled(False)
        # Z: has no policy entry -> legacy allow when the master switch is off
        self.assertTrue(drive_guard.check("Z:\\anything", "delete")[0])

    def test_explicit_policy_enforced_with_master_off(self):
        drive_guard.set_enabled(False)
        # C: is explicitly DENIED in setUp — that must hold even with the
        # master switch off, otherwise a grant/deny means nothing.
        self.assertFalse(drive_guard.check("C:\\anything", "delete")[0])
        self.assertFalse(drive_guard.check("C:\\anything", "read")[0])
        # D: explicitly granted read+write — usable with the master off too
        self.assertTrue(drive_guard.check("D:\\a.txt", "read")[0])
        self.assertFalse(drive_guard.check("D:\\a.txt", "delete")[0])
        with self.assertRaises(PermissionError):
            drive_guard._vet_command('type C:\\secret.txt')

    def test_access_without_rights_is_denied(self):
        drive_guard.set_permission("E", access=True, read=False)
        ok, reason = drive_guard.check("E:\\file.txt", "read")
        self.assertFalse(ok)
        self.assertIn("read", reason)

    def test_enable_defaults_all_denied(self):
        drive_guard.set_enabled(False)
        config.save_settings(drives={})
        drive_guard.set_enabled(True)
        for letter, p in drive_guard.get_policy().items():
            self.assertFalse(any(p.values()), f"{letter} silently granted")

    def test_shell_vetting(self):
        drive_guard._vet_command('notepad D:\\ok.txt')          # allowed
        with self.assertRaises(PermissionError):
            drive_guard._vet_command('type C:\\secret.txt')
        with self.assertRaises(PermissionError):
            drive_guard._vet_command(['cmd', '/c', 'del', 'E:\\file.txt'])
        with self.assertRaises(PermissionError):
            drive_guard._vet_command('dir', cwd='C:\\Users')

    def test_executable_on_denied_drive_allowed(self):
        # running a program ≠ reading user data
        drive_guard._vet_command('"C:\\Program Files\\App\\app.exe"')


class TestVoiceMath(unittest.TestCase):
    def test_embedding_shape_and_similarity(self):
        import numpy as np
        from security.voice import speaker_embedding, similarity
        rng = np.random.default_rng(7)
        t = np.arange(16000 * 2) / 16000.0
        # two "speakers": different harmonic structures
        a = (0.4 * np.sin(2 * np.pi * 140 * t) + 0.2 * np.sin(2 * np.pi * 420 * t)
             + 0.02 * rng.standard_normal(t.size)).astype(np.float32)
        b = (0.4 * np.sin(2 * np.pi * 230 * t) + 0.2 * np.sin(2 * np.pi * 900 * t)
             + 0.02 * rng.standard_normal(t.size)).astype(np.float32)
        a2 = a * 0.8 + 0.01 * rng.standard_normal(t.size).astype(np.float32)
        ea, eb, ea2 = (speaker_embedding(x) for x in (a, b, a2))
        self.assertIsNotNone(ea)
        self.assertAlmostEqual(float(np.linalg.norm(ea)), 1.0, places=5)
        self.assertGreater(similarity(ea, ea2), similarity(ea, eb))

    def test_silence_rejected(self):
        import numpy as np
        from security.voice import speaker_embedding
        self.assertIsNone(speaker_embedding(np.zeros(32000, dtype=np.float32)))

    def test_different_vocal_tract_rejected(self):
        """Regression: time-CMN alone erased the formant envelope and every
        speaker scored ~0.99 against every other. The spectral-shape block
        must keep different vocal tracts below the unauthorized threshold."""
        import numpy as np
        from security.voice import speaker_embedding, similarity

        def speech(f0, formants, seed=7):
            r = np.random.default_rng(seed)
            n = int(16000 * 1.6)
            t = np.arange(n) / 16000.0
            x = np.zeros(n)
            for k in range(1, 40):
                f = f0 * k
                if f > 7800:
                    break
                g = sum(np.exp(-((f - fc) / 120.0) ** 2) for fc in formants) + 0.05
                x += (g / k ** 0.7) * np.sin(2 * np.pi * f * t + 0.05 * k)
            return (0.3 * x / np.max(np.abs(x))
                    + 0.01 * r.standard_normal(n)).astype(np.float32)

        a = speaker_embedding(speech(140, [500, 1500, 2500]))
        a2 = speaker_embedding(speech(140, [500, 1500, 2500], seed=9))
        b = speaker_embedding(speech(140, [700, 1100, 2900]))
        self.assertGreater(similarity(a, a2), 0.9)
        self.assertLess(similarity(a, b), 0.55)


class TestPrivacy(_TempConfig):
    def _controller(self, face, voice):
        events = []
        p = privacy.PrivacyController(lambda: face, lambda: voice,
                                      lambda k, d: events.append((k, d)))
        return p, events

    def test_open_unconfigured_legacy(self):
        p, _ = self._controller({}, {})
        ok, _ = p.authorize_sensitive()
        self.assertTrue(ok)

    def test_open_configured_requires_auth(self):
        storage.set_pin("9999")
        p, _ = self._controller({}, {})
        ok, reason = p.authorize_sensitive()
        self.assertFalse(ok)
        ok, _ = p.unlock_with_pin("9999")
        self.assertTrue(ok)
        self.assertTrue(p.authorize_sensitive()[0])

    def test_strict_requires_enrollment(self):
        config.set_value("privacy_mode", "strict")
        p, _ = self._controller({"authorized_present": True}, {"verified": True})
        ok, reason = p.authorize_sensitive()
        self.assertFalse(ok)
        self.assertIn("registered face AND voice", reason)

    def test_strict_dual_auth(self):
        storage.save_blob("face", {"templates": [[1.0]]})
        storage.save_blob("voice", {"templates": [[1.0]]})
        config.set_value("privacy_mode", "strict")
        face = {"authorized_present": True, "camera_status": "active"}
        voice = {"verified": True}
        p, events = self._controller(face, voice)
        self.assertTrue(p.authorize_sensitive()[0])
        face["authorized_present"] = False
        self.assertFalse(p.authorize_sensitive()[0])
        face["authorized_present"] = True
        voice["verified"] = False
        self.assertFalse(p.authorize_sensitive()[0])

    def test_camera_disconnect_locks_strict(self):
        storage.save_blob("face", {"templates": [[1.0]]})
        storage.save_blob("voice", {"templates": [[1.0]]})
        config.set_value("privacy_mode", "strict")
        face = {"authorized_present": True, "camera_status": "active"}
        p, events = self._controller(face, {"verified": True})
        p.notify("camera_disconnected", {})
        self.assertTrue(p.status()["privacy_locked"])
        self.assertIn("privacy_locked", [k for k, _ in events])

    def test_emergency_lock_and_pin(self):
        storage.set_pin("4321")
        p, _ = self._controller({}, {})
        p.emergency_lock()
        self.assertFalse(p.authorize_sensitive()[0])
        self.assertTrue(p.unlock_with_pin("4321")[0])
        self.assertTrue(p.authorize_sensitive()[0])

    def test_emergency_lock_even_unconfigured(self):
        p, _ = self._controller({}, {})
        self.assertTrue(p.authorize_sensitive()[0])   # legacy open mode
        p.emergency_lock()
        self.assertFalse(p.authorize_sensitive()[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)