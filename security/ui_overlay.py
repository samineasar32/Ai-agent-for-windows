"""Security & Privacy overlay for the JARVIS HUD.

Purely additive: opened from the SETUP drawer, styled with the existing
palette (ui.C) and overlay base (ui._HudOverlay). Nothing here alters the
existing panels. All heavy work happens in the security package threads;
this file only renders status and forwards user intent to the manager.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QScrollArea, QVBoxLayout, QWidget,
)

from ui import C, _HudOverlay
from security import get_manager
from security import config as sec_config


def _font(size=8, bold=False):
    return QFont("Courier New", size,
                 QFont.Weight.Bold if bold else QFont.Weight.Normal)


class SecurityOverlay(_HudOverlay):
    _reg_msg = pyqtSignal(str)
    _OW = 620
    _OH = 640

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mgr = get_manager()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SecurityOverlay {{
                background: rgba(0, 6, 10, 250);
                border: 1px solid {C.PRI_DIM};
                border-radius: 6px;
            }}
            QLabel {{ background: transparent; border: none; color: {C.TEXT}; }}
            QCheckBox, QRadioButton {{ color: {C.TEXT_MED}; background: transparent;
                font-family: 'Courier New'; font-size: 11px; spacing: 6px; }}
            QCheckBox::indicator, QRadioButton::indicator {{
                width: 13px; height: 13px;
                border: 1px solid {C.BORDER_B}; border-radius: 2px;
                background: {C.BG};
            }}
            QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
                background: {C.GREEN}; border-color: {C.GREEN};
            }}
            QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
                border-color: {C.BORDER}; background: {C.PANEL};
            }}
            QLineEdit {{ background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px;
                font-family: 'Courier New'; }}
            QScrollArea {{ background: transparent; border: none; }}
        """)
        self.setFixedSize(self._OW, self._OH)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        hdr = QHBoxLayout()
        title = QLabel("◈ SECURITY && PRIVACY")
        title.setFont(_font(11, True))
        title.setStyleSheet(f"color: {C.PRI};")
        hdr.addWidget(title)
        hdr.addStretch()
        close = QPushButton("✕")
        close.setFixedSize(24, 24)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(f"QPushButton {{ color: {C.TEXT_MED}; background: transparent;"
                            f" border: 1px solid {C.BORDER}; border-radius: 3px; }}"
                            f"QPushButton:hover {{ color: {C.RED}; border-color: {C.RED}; }}")
        close.clicked.connect(self.hide)
        hdr.addWidget(close)
        root.addLayout(hdr)

        self._status_lbl = QLabel("…")
        self._status_lbl.setFont(_font(8, True))
        root.addWidget(self._status_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        self._body = QVBoxLayout(body)
        self._body.setContentsMargins(0, 0, 8, 0)
        self._body.setSpacing(8)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        self._build_mode_section()
        self._build_camera_section()
        self._build_face_section()
        self._build_voice_section()
        self._build_pin_section()
        self._build_drive_section()
        self._build_notifications()
        self._body.addStretch()

        self._msg = QLabel("")
        self._msg.setWordWrap(True)
        self._msg.setFont(_font(8))
        self._msg.setStyleSheet(f"color: {C.ACC2};")
        root.addWidget(self._msg)
        self._reg_msg.connect(self._msg.setText)

        self._drive_snapshot = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(1200)
        self._refresh()

    # ── section helpers ──────────────────────────────────────────────────────

    def _section(self, title: str) -> QVBoxLayout:
        frame = QFrame()
        frame.setStyleSheet(f"QFrame {{ background: {C.PANEL2};"
                            f" border: 1px solid {C.BORDER}; border-radius: 4px; }}")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(5)
        lbl = QLabel(title)
        lbl.setFont(_font(8, True))
        lbl.setStyleSheet(f"color: {C.PRI_DIM}; border-bottom: 1px solid {C.BORDER};"
                          " padding-bottom: 3px;")
        lay.addWidget(lbl)
        self._body.addWidget(frame)
        return lay

    def _btn(self, text, danger=False) -> QPushButton:
        col = C.RED if danger else C.PRI
        b = QPushButton(text)
        b.setFixedHeight(26)
        b.setFont(_font(8, True))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {col};
                border: 1px solid {col}; border-radius: 3px; padding: 0 10px; }}
            QPushButton:hover {{ background: rgba(0, 212, 255, 25); }}
        """)
        return b

    def _say(self, ok: bool, text: str):
        self._msg.setStyleSheet(f"color: {C.GREEN if ok else C.RED};")
        self._msg.setText(text)

    # ── privacy mode ─────────────────────────────────────────────────────────

    def _build_mode_section(self):
        lay = self._section("PRIVACY MODE")
        row = QHBoxLayout()
        self._mode_open = QRadioButton("OPEN VOICE — anyone may talk; sensitive ops need auth")
        self._mode_strict = QRadioButton("STRICT — face + voice required; auto-lock on leave")
        s = sec_config.load_settings()
        (self._mode_strict if s.get("privacy_mode") == "strict"
         else self._mode_open).setChecked(True)
        self._mode_open.toggled.connect(lambda on: on and self._set_mode("open"))
        self._mode_strict.toggled.connect(lambda on: on and self._set_mode("strict"))
        row.addWidget(self._mode_open)
        row.addWidget(self._mode_strict)
        lay.addLayout(row)

    def _set_mode(self, mode):
        ok, msg = self.mgr.set_privacy_mode(mode)
        self._say(ok, msg)
        if not ok:
            other = self._mode_open if mode == "strict" else self._mode_strict
            other.blockSignals(True)
            other.setChecked(True)
            other.blockSignals(False)

    # ── camera ───────────────────────────────────────────────────────────────

    def _build_camera_section(self):
        lay = self._section("CAMERA")
        row = QHBoxLayout()
        self._cam_perm = QCheckBox("Camera permission (camera NEVER runs without this)")
        self._cam_perm.setChecked(bool(sec_config.get("camera_permission")))
        self._cam_perm.toggled.connect(self._on_cam_perm)
        row.addWidget(self._cam_perm)
        row.addStretch()
        self._cam_dot = QLabel("●")
        self._cam_dot.setFont(_font(12, True))
        row.addWidget(self._cam_dot)
        self._cam_status = QLabel("OFF")
        self._cam_status.setFont(_font(8, True))
        row.addWidget(self._cam_status)
        lay.addLayout(row)
        self._cam_loss = QCheckBox("Shut down the assistant if the camera is turned off / disconnected")
        self._cam_loss.setChecked(bool(sec_config.get("camera_loss_shutdown")))
        self._cam_loss.toggled.connect(
            lambda on: self._say(*self.mgr.update_settings({"camera_loss_shutdown": bool(on)})))
        lay.addWidget(self._cam_loss)

    def _on_cam_perm(self, on):
        ok, msg = self.mgr.update_settings({"camera_permission": bool(on)})
        self._say(ok, msg)

    # ── face ─────────────────────────────────────────────────────────────────

    def _build_face_section(self):
        lay = self._section("FACE SECURITY  (local processing — no frame leaves this PC)")
        row = QHBoxLayout()
        self._face_track = QCheckBox("Face Tracking")
        self._face_recog = QCheckBox("Face Recognition")
        s = sec_config.load_settings()
        self._face_track.setChecked(bool(s.get("face_tracking_enabled")))
        self._face_recog.setChecked(bool(s.get("face_recognition_enabled")))
        self._face_track.toggled.connect(
            lambda on: self._face_setting("face_tracking_enabled", on))
        self._face_recog.toggled.connect(
            lambda on: self._face_setting("face_recognition_enabled", on))
        row.addWidget(self._face_track)
        row.addWidget(self._face_recog)
        row.addStretch()
        lay.addLayout(row)

        self._face_status = QLabel("Authorized user: —   Presence: —")
        self._face_status.setFont(_font(8))
        lay.addWidget(self._face_status)
        self._face_motion = QLabel("Head: —   Movement: —")
        self._face_motion.setFont(_font(8))
        self._face_motion.setStyleSheet(f"color: {C.TEXT_MED};")
        lay.addWidget(self._face_motion)

        row2 = QHBoxLayout()
        reg = self._btn("▸ REGISTER FACE")
        reg.clicked.connect(self._register_face)
        row2.addWidget(reg)
        dele = self._btn("DELETE FACE DATA", danger=True)
        dele.clicked.connect(lambda: self._delete_id("face"))
        row2.addWidget(dele)
        row2.addStretch()
        lay.addLayout(row2)

    def _face_setting(self, key, on):
        ok, msg = self.mgr.update_settings({key: bool(on)})
        self._say(ok, msg)
        if not ok:
            w = self._face_track if key == "face_tracking_enabled" else self._face_recog
            w.blockSignals(True)
            w.setChecked(not on)
            w.blockSignals(False)

    def _register_face(self):
        ok, msg = self.mgr.register_face(
            lambda d, t, m: self._reg_msg.emit(f"FACE {d}/{t}  {m}"))
        self._say(ok, msg)

    def _delete_id(self, what):
        ok, msg = self.mgr.delete_identity(what)
        self._say(ok, msg)

    # ── voice ────────────────────────────────────────────────────────────────

    def _build_voice_section(self):
        lay = self._section("VOICE SECURITY  (speaker identity — separate from speech recognition)")
        row = QHBoxLayout()
        self._voice_on = QCheckBox("Voice Verification")
        self._voice_on.setChecked(bool(sec_config.get("voice_verification_enabled")))
        self._voice_on.toggled.connect(self._on_voice_toggle)
        row.addWidget(self._voice_on)
        row.addStretch()
        self._voice_status = QLabel("NOT VERIFIED")
        self._voice_status.setFont(_font(8, True))
        row.addWidget(self._voice_status)
        lay.addLayout(row)
        note = QLabel("Voice alone never unlocks sensitive operations — face or PIN is also required.")
        note.setFont(_font(7))
        note.setStyleSheet(f"color: {C.TEXT_DIM};")
        note.setWordWrap(True)
        lay.addWidget(note)
        row2 = QHBoxLayout()
        reg = self._btn("▸ REGISTER VOICE")
        reg.clicked.connect(self._register_voice)
        row2.addWidget(reg)
        dele = self._btn("DELETE VOICE DATA", danger=True)
        dele.clicked.connect(lambda: self._delete_id("voice"))
        row2.addWidget(dele)
        row2.addStretch()
        lay.addLayout(row2)

    def _on_voice_toggle(self, on):
        ok, msg = self.mgr.update_settings({"voice_verification_enabled": bool(on)})
        self._say(ok, msg)

    def _register_voice(self):
        ok, msg = self.mgr.register_voice(
            lambda d, t, m: self._reg_msg.emit(f"VOICE {d}/{t}  {m}"))
        self._say(ok, msg)

    # ── PIN / emergency ──────────────────────────────────────────────────────

    def _build_pin_section(self):
        lay = self._section("BACKUP PIN & EMERGENCY LOCK")
        row = QHBoxLayout()
        self._pin_edit = QLineEdit()
        self._pin_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pin_edit.setPlaceholderText("PIN / password (min 4 chars)")
        self._pin_edit.setFixedWidth(220)
        row.addWidget(self._pin_edit)
        setb = self._btn("SET PIN")
        setb.clicked.connect(self._set_pin)
        row.addWidget(setb)
        unlock = self._btn("UNLOCK WITH PIN")
        unlock.clicked.connect(self._unlock_pin)
        row.addWidget(unlock)
        row.addStretch()
        lock = self._btn("⚠ EMERGENCY LOCK", danger=True)
        lock.clicked.connect(lambda: self._say(True, self.mgr.emergency_lock()))
        row.addWidget(lock)
        lay.addLayout(row)
        self._pin_status = QLabel("")
        self._pin_status.setFont(_font(7))
        self._pin_status.setStyleSheet(f"color: {C.TEXT_DIM};")
        lay.addWidget(self._pin_status)

    def _set_pin(self):
        ok, msg = self.mgr.set_pin(self._pin_edit.text())
        self._say(ok, msg)
        if ok:
            self._pin_edit.clear()

    def _unlock_pin(self):
        ok, msg = self.mgr.unlock_with_pin(self._pin_edit.text())
        self._say(ok, msg)
        if ok:
            self._pin_edit.clear()

    # ── drives ───────────────────────────────────────────────────────────────

    def _build_drive_section(self):
        lay = self._section("DRIVE PERMISSION MANAGEMENT")
        self._drive_prot = QCheckBox(
            "Drive Protection (ON = every drive DENIED until explicitly granted)")
        self._drive_prot.setChecked(bool(sec_config.get("drive_protection_enabled")))
        self._drive_prot.toggled.connect(self._on_drive_prot)
        lay.addWidget(self._drive_prot)
        self._drive_grid_host = QVBoxLayout()
        lay.addLayout(self._drive_grid_host)
        self._drive_widgets = {}

    def _on_drive_prot(self, on):
        ok, msg = self.mgr.set_drive_protection(bool(on))
        self._say(ok, msg)
        self._drive_snapshot = None
        self._rebuild_drives()

    def _rebuild_drives(self):
        from security import drive_guard
        detected = drive_guard.detect_drives()
        policy = drive_guard.get_policy()
        snap = ([(d["drive"], d["label"], d["type"]) for d in detected],
                tuple(sorted((k, tuple(sorted(v.items()))) for k, v in policy.items())))
        if snap == self._drive_snapshot:
            return
        self._drive_snapshot = snap
        while self._drive_grid_host.count():
            item = self._drive_grid_host.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._drive_widgets = {}

        # One grid for header AND rows so the columns line up and the whole
        # table fits the overlay width (per-row grids made it 1176 px wide
        # and pushed DELETE behind a horizontal scrollbar).
        table = QWidget()
        gl = QGridLayout(table)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setHorizontalSpacing(6)
        gl.setVerticalSpacing(3)
        center = Qt.AlignmentFlag.AlignHCenter
        for c, t in enumerate(["DRIVE", "ACCESS", "READ", "WRITE", "CREATE", "EDIT", "DELETE"]):
            lbl = QLabel(t)
            lbl.setFont(_font(7, True))
            lbl.setStyleSheet(f"color: {C.PRI_DIM};")
            gl.addWidget(lbl, 0, c, center if c else Qt.AlignmentFlag.AlignLeft)
        gl.setColumnStretch(0, 1)

        ops = ("read", "write", "create", "edit", "delete")
        for r, d in enumerate(detected, start=1):
            letter = d["drive"]
            p = policy.get(letter, {})
            name = QLabel(f"{letter}:  {d['label'] or d['type']}")
            name.setFont(_font(8, True))
            name.setStyleSheet(f"color: {C.TEXT};")
            gl.addWidget(name, r, 0)
            access = QCheckBox("ALLOWED" if p.get("access") else "DENIED")
            access.setChecked(bool(p.get("access")))
            access.setStyleSheet(
                f"color: {C.GREEN if p.get('access') else C.RED}; font-weight: bold;")
            access.toggled.connect(
                lambda on, L=letter: self._set_drive(L, access=on))
            gl.addWidget(access, r, 1)
            checks = {}
            for i, op in enumerate(ops):
                cb = QCheckBox()
                cb.setChecked(bool(p.get(op)))
                cb.setEnabled(bool(p.get("access")))
                cb.setToolTip(f"Drive {letter}: {op.upper()} permission")
                cb.toggled.connect(
                    lambda on, L=letter, O=op: self._set_drive(L, **{O: on}))
                gl.addWidget(cb, r, 2 + i, center)
                checks[op] = cb
            self._drive_widgets[letter] = (access, checks)
        self._drive_grid_host.addWidget(table)
        hint = QLabel("ACCESS is the master gate — tick READ (and any other right) to use a drive.")
        hint.setFont(_font(7))
        hint.setStyleSheet(f"color: {C.TEXT_DIM};")
        hint.setWordWrap(True)
        self._drive_grid_host.addWidget(hint)

    def _set_drive(self, letter, **perms):
        ok, msg = self.mgr.set_drive_permission(letter, **perms)
        self._say(ok, msg)
        self._drive_snapshot = None
        self._rebuild_drives()

    # ── notifications ────────────────────────────────────────────────────────

    def _build_notifications(self):
        lay = self._section("SECURITY LOG")
        self._notif_lbl = QLabel("No events.")
        self._notif_lbl.setFont(_font(7))
        self._notif_lbl.setStyleSheet(f"color: {C.TEXT_MED};")
        self._notif_lbl.setWordWrap(True)
        lay.addWidget(self._notif_lbl)

    # ── live refresh ─────────────────────────────────────────────────────────

    def _refresh(self):
        if not self.isVisible():
            return
        try:
            st = self.mgr.status()
        except Exception:
            return
        priv, face, voice, cam = (st["privacy"], st["face"], st["voice"], st["camera"])

        auth = "VERIFIED" if (face.get("authorized_present") and voice.get("verified")) \
            else ("PIN" if priv.get("pin_active") else "NOT VERIFIED")
        lock = "LOCKED" if (priv.get("privacy_locked") or priv.get("emergency_locked")) \
            else "UNLOCKED"
        col = C.RED if lock == "LOCKED" else C.GREEN
        self._status_lbl.setText(
            f"AUTH: {auth}    PRIVACY: {lock}    MODE: {priv.get('mode', 'open').upper()}")
        self._status_lbl.setStyleSheet(f"color: {col};")

        active = cam.get("active")
        self._cam_dot.setStyleSheet(f"color: {C.RED if active else C.TEXT_DIM};")
        self._cam_status.setText(str(cam.get("status", "off")).upper())
        self._cam_status.setStyleSheet(
            f"color: {C.RED if active else C.TEXT_MED};")

        reg = "REGISTERED" if face.get("registered") else "NOT REGISTERED"
        pres = "DETECTED" if face.get("authorized_present") else "NOT DETECTED"
        unknown = "  ⚠ UNKNOWN PERSON" if face.get("unknown_present") else ""
        self._face_status.setText(
            f"Authorized user: {reg}   Presence: {pres}{unknown}")
        self._face_status.setStyleSheet(
            f"color: {C.RED if face.get('unknown_present') else C.TEXT};")
        self._face_motion.setText(
            f"Head: {face.get('head_direction', '—')}   Movement: {face.get('movement', '—')}")

        vs = "VERIFIED" if voice.get("verified") else "NOT VERIFIED"
        self._voice_status.setText(vs)
        self._voice_status.setStyleSheet(
            f"color: {C.GREEN if voice.get('verified') else C.ACC};")

        self._pin_status.setText(
            ("PIN is set." if priv.get("pin_set") else "No PIN set — recommended backup.")
            + ("  PIN window ACTIVE." if priv.get("pin_active") else ""))

        self._rebuild_drives()

        notes = st.get("notifications") or []
        if notes:
            import time as _t
            lines = [f"[{_t.strftime('%H:%M:%S', _t.localtime(n['time']))}] {n['message']}"
                     for n in notes[-5:]]
            self._notif_lbl.setText("\n".join(lines))

    def hideEvent(self, e):
        self._refresh_timer.stop()
        super().hideEvent(e)

    def showEvent(self, e):
        self._refresh_timer.start(1200)
        super().showEvent(e)