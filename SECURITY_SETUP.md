# JARVIS — Security & Privacy Upgrade

Additive upgrade: face recognition, voice authentication, two privacy modes,
automatic privacy protection, and centralized drive permission management.
**Nothing was removed or replaced.** Six existing files received small,
additive hooks; everything else lives in the new `security/` package.

---

## 1. Installation

**No new pip dependencies.** Everything uses packages already in
`requirements.txt` (opencv-python, numpy, cryptography, pywin32, fastapi, PyQt6).

```bash
# from the project folder, with your existing environment:
pip install -r requirements.txt      # only if your env is not already set up
python main.py                       # start JARVIS exactly as before
```

Face AI models (YuNet detector ~0.3 MB + SFace recognizer ~37 MB) are
downloaded **once** from the official OpenCV model zoo the first time you
press **REGISTER FACE**, cached in `config/security_data/models/`, and used
100% offline afterwards. To pre-download manually, place these files there:

- `face_detection_yunet_2023mar.onnx`
- `face_recognition_sface_2021dec.onnx`

(from https://github.com/opencv/opencv_zoo/tree/main/models)

Settings live in a **new** file `config/security_settings.json`; your existing
`config/api_keys.json` is never touched. Biometric templates and the PIN
verifier are Fernet-encrypted in `config/security_data/`; on Windows the
encryption key is additionally wrapped with DPAPI (bound to your Windows
account — copying the folder to another machine/account yields unusable data).

## 2. First-time setup (recommended order)

Open **⚙ SETUP → 🛡 SECURITY & PRIVACY** in the HUD, or the 🛡 button in the
remote web dashboard (`/security`).

1. **SET PIN** — backup authentication (min 4 chars). Do this first.
2. **Camera permission** ON → **Face Recognition** ON → **REGISTER FACE**
   (look at the camera; 12 samples are collected).
3. **Voice Verification** ON → **REGISTER VOICE** (speak naturally; 4 segments).
4. Choose **STRICT PRIVACY MODE** (requires steps 2–3) or stay in **OPEN VOICE**.
5. Enable **Drive Protection** and grant drives/rights explicitly.

## 3. Privacy modes

| | Open Voice | Strict Privacy |
|---|---|---|
| General commands (search, weather, chat…) | anyone | anyone |
| Sensitive ops (files, messages, computer control…) | auth required **once an identity is enrolled** | face **and** fresh voice match, or PIN window |
| User leaves camera view | — | sensitive ops auto-lock (3 s grace) |
| Camera disconnects | — | sensitive ops auto-lock |
| User returns | — | face re-verified automatically; speak once to re-verify voice |

Until you enroll anything, Open mode behaves **exactly like the original
JARVIS** — installing this upgrade changes nothing by itself.

Voice verification tolerates normal variation (adaptive template update) and
is **never sufficient alone** for sensitive operations. A PIN unlock opens a
5-minute authorization window. **Emergency lock** blocks all sensitive tools
until PIN unlock or full face+voice re-verification.

The camera never runs secretly: it requires explicit permission plus a face
feature toggle, the left-panel HUD indicator shows **SEC / CAM ACTIVE** in
orange whenever it is live, and the overlay/dashboard show a red dot.

**Camera-loss shutdown (default ON):** once the security camera has been live,
turning it off — in Settings, by unplugging it, or a Windows camera-privacy
toggle — stops the conversation, engages the emergency lock and shuts the
assistant down (the PC is never touched). Restart JARVIS to resume. Disable
via the "Shut down the assistant if the camera is turned off / disconnected"
checkbox in the overlay or `/security` (`camera_loss_shutdown` in settings).

## 4. Drive Permission Management

- **ACCESS is the master gate, not a usable right.** Tick ACCESS *and* the
  rights you want (READ at minimum to open/list a drive). ACCESS alone keeps
  everything blocked — the settings panel tells you when rights are missing.
- Explicit per-drive entries are **always enforced**, even with the master
  switch OFF: a drive you denied stays denied; a drive you granted READ+ACCESS
  on is usable immediately. Drives with **no entry** follow the master switch:
  OFF (default) = original behaviour, ON = default-DENIED.
- Turning the master switch ON seeds **every detected drive as DENIED**.
  Nothing is ever granted silently. Grant per drive: ACCESS, READ, WRITE,
  CREATE, EDIT, DELETE.
- Enforcement is programmatic, at three layers:
  1. the tool gate in `main.py::_execute_tool` (every AI function call),
  2. `actions/file_controller.py` (every file operation, per-operation right),
  3. wrapped `subprocess.Popen` / `os.system` / `os.startfile` (shell commands
     cannot bypass; command verbs map to rights — `del` needs DELETE, etc.).
- "Open C drive" is refused while C: is restricted, whatever module tries it;
  with ACCESS+READ granted it opens in File Explorer (`open_app` handles drive
  roots and folder paths directly).
- Revoking any right blocks the very next operation (no cached decisions).
- Paths are canonicalized (`realpath`) before checking: `..` traversal and
  symlink/junction escapes cannot cross a drive boundary. UNC paths are denied.
- **Exemption:** JARVIS's own install folder and the Python runtime remain
  usable — drive protection governs *user data*, not the app's ability to run.
- Granting a drive also extends file access beyond the original home-folder
  restriction (D:/E: become reachable only after an explicit grant).
- Once a PIN is set, the remote dashboard requires it for any change that
  weakens protection or alters drive rights.

## 5. Voice commands (new `security_control` tool)

- "Security status" / "are we locked?"
- "Emergency lock" / "lock privacy"
- "Unlock privacy, PIN 1234"
- "Which drives can you access?"

Drive grants and mode changes are deliberately **UI/dashboard only** — the
model cannot talk its way into granting itself access.

## 6. Testing

```bash
python -m security.tests.test_security       # 27 unit tests
python -m security.tests.test_integration    # 17 end-to-end tests
```

Covered: encrypted storage, PIN + lockout, drive denial/grant/revoke/traversal/
UNC/shell/startfile, explicit policy with master off, both privacy modes,
emergency lock, dual auth, speaker embedding separation (incl. a regression
test for vocal-tract discrimination), camera-loss shutdown, drive opening via
the real `open_app`, the real `file_controller` under policy, the dashboard
API (auth + PIN gating). Camera/mic hardware paths (live registration, camera
disconnect) need your physical devices: enable camera permission, register,
then unplug the camera and watch the assistant lock and shut down.

**Updating from the first security release:** re-register your voice once
(REGISTER VOICE). The speaker embedding was fixed to actually discriminate
speakers; templates enrolled with the old math will not match.

## 7. Known limitations (honest notes)

- Speaker verification is a lightweight local embedding (log-mel + MFCC +
  pitch), not a cloud-grade neural voiceprint. It is a second factor, never a
  sole factor — by design. Thresholds are tunable in
  `config/security_settings.json` (`voice_match_threshold`,
  `face_match_threshold`).
- Shell-command vetting is heuristic for exotic command lines; the file-tool
  and tool-gate layers are exact. A determined local process running outside
  JARVIS is beyond any user-space guard.
- Face recognition quality depends on lighting; register in conditions
  similar to normal use.

## 8. Files

**Modified (additive hooks only):**
| File | Change |
|---|---|
| `main.py` | +66 lines: startup init, tool gate (executor), mic tap, camera-loss shutdown hook |
| `ui.py` | +56 lines: drawer button, overlay opener, live SEC/camera indicator |
| `dashboard/server.py` | +8 lines: register security routes |
| `dashboard/static/app.html` | +5 lines: 🛡 header button |
| `actions/file_controller.py` | +25/−1 lines: drive layer in path guard + dispatcher check |
| `actions/screen_processor.py` | +10 lines: reuse face-monitor frame (webcam can't open twice) |
| `actions/open_app.py` | +29 lines: drive roots / folder paths open in File Explorer (drive-guard enforced) |

**New:** `security/` (`__init__`, `config`, `storage`, `drive_guard`, `face`,
`voice`, `privacy`, `manager`, `ui_overlay`, `dashboard_routes`, `tests/`),
`actions/security_control.py`, `dashboard/static/security.html`, this document.

**Removed:** nothing.