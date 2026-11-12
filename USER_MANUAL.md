# JARVIS (Mark LVI) — Complete User Manual

**The ultimate cross-platform personal AI assistant — with the Security & Privacy upgrade.**

This manual guides a brand-new user from an empty folder to a fully configured,
secured JARVIS. Read Part 1 to get running, then use the rest as a reference.
If you only read one section, read **[11. Security & Privacy](#11-security--privacy--the-complete-guide)**.

- Based on: Mark LVI by FatihMakes + the Security & Privacy upgrade
- Platforms: Windows 10/11 · macOS · Linux
- Python: 3.11 – 3.13
- License: CC BY-NC 4.0 (non-commercial)

---

## Table of contents

1. [What is JARVIS?](#1-what-is-jarvis)
2. [What you need](#2-what-you-need)
3. [Installation — step by step](#3-installation--step-by-step)
4. [First launch — the Gemini API key](#4-first-launch--the-gemini-api-key)
5. [Screen tour — the HUD and its drawers](#5-screen-tour--the-hud-and-its-drawers)
6. [Talking to JARVIS](#6-talking-to-jarvis)
7. [What you can ask — feature reference](#7-what-you-can-ask--feature-reference)
8. [Built-in safety — confirmation, undo, honest answers](#8-built-in-safety--confirmation-undo-honest-answers)
9. [Memory](#9-memory)
10. [Engines & Providers — local and third-party models](#10-engines--providers--local-and-third-party-models)
11. [Security & Privacy — the complete guide](#11-security--privacy--the-complete-guide)
12. [Phone dashboard — remote control](#12-phone-dashboard--remote-control)
13. [Settings and data files](#13-settings-and-data-files)
14. [Extending JARVIS — plugins, providers, actions](#14-extending-jarvis--plugins-providers-actions)
15. [Troubleshooting](#15-troubleshooting)
16. [Keyboard shortcuts](#16-keyboard-shortcuts)
17. [Running the security tests](#17-running-the-security-tests)
18. [Reset and uninstall](#18-reset-and-uninstall)
19. [Project structure](#19-project-structure)
20. [Credits and license](#20-credits-and-license)

---

## 1. What is JARVIS?

JARVIS is a real-time voice AI that can **hear, see, speak, and control your
computer**. It lives in a holographic HUD with an animated avatar that lip-syncs
to its own voice, and it can:

- hold a natural voice conversation in any language (Gemini Live, or your own
  local STT + LLM + TTS stack),
- open apps and drives, manage files, control volume/brightness/WiFi/power,
- search the web, play YouTube/videos on the HUD, send messages, set reminders,
- see your screen and webcam, remember you across sessions, and undo what it did.

The **Security & Privacy upgrade** adds:

- **Face security** — local detection, tracking, authorized-user recognition,
  presence and head-movement sensing, unknown-person alerts. No frame ever
  leaves your PC.
- **Voice security** — speaker verification (who is talking), separate from
  speech recognition (what was said).
- **Two privacy modes** — *Open Voice* and *Strict* (face + voice, auto-lock).
- **Automatic protection** — auto lock/unlock, emergency lock, backup PIN,
  camera activity indicator, camera-loss shutdown, encrypted biometric storage.
- **Drive permission management** — per-drive ACCESS / READ / WRITE / CREATE /
  EDIT / DELETE, default-deny for unapproved drives, enforced in code on every
  file operation and shell command — not just in the UI.

Everything is optional and off by default. A plain install behaves exactly like
the original Mark LVI until you switch something on.

---

## 2. What you need

| Item | Requirement |
|---|---|
| OS | Windows 10/11, macOS, or Linux |
| Python | **3.11, 3.12 or 3.13** (check with `python --version`) |
| Microphone | Any working input device |
| Speakers | Any working output device |
| Internet | Needed for Gemini mode and first-time model downloads |
| Gemini API key | Free from Google AI Studio (see §4) — not needed if you run a fully local engine |
| Camera | Optional — only for face security. Never runs without your explicit permission |
| Disk | ~1–2 GB for dependencies; face models are a few MB; local speech models ~60–500 MB if you choose them |

No paid subscription is required. Local speech (Whisper/Piper) and local models
(Ollama etc.) are optional one-click installs from inside the app.

---

## 3. Installation — step by step

### 3.1 Get the project folder

Extract the zip (e.g. `Mark-LVI-main-SECURITY-upgraded.zip`) to a permanent
location, for example:

```
C:\Users\<you>\Documents\Mark-LVI-main
```

> Avoid running it from inside the zip or from a temporary folder — JARVIS
> stores its config, memory and biometric data next to `main.py`.

### 3.2 Install (the easy way)

Open a terminal **in the project folder** and run:

```bash
python setup.py
```

`setup.py` checks your Python version (3.11–3.13), installs everything in
`requirements.txt`, and downloads the Playwright browsers used for browser
control. On Windows it picks the Windows-only automation packages automatically.

### 3.3 Install (manual way, if you prefer)

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

### 3.4 Using VS Code (step by step)

1. **File → Open Folder…** → select the `Mark-LVI-main` folder.
2. Install the **Python** extension if VS Code asks.
3. Pick the interpreter: `Ctrl+Shift+P` → *Python: Select Interpreter* → choose
   your Python 3.11–3.13 install.
4. Open a terminal: **Terminal → New Terminal** (it starts in the project folder).
5. Run `python setup.py` once.
6. Run `python main.py` to start JARVIS.

### 3.5 Optional components (installed later, from inside the app)

These are deliberately **not** in `requirements.txt` — a fresh clone that only
uses Gemini should not download hundreds of megabytes it will never open:

| Component | What it does | How to install |
|---|---|---|
| Wake word ("Hey Jarvis") | Local always-listening trigger | Controls drawer → WAKE WORD button (one click) |
| `faster-whisper` | Local speech recognition (CPU) | ⚙ → ENGINE & PROVIDERS → Hearing → install |
| `piper-tts` | Local neural voice, ~50 languages | ⚙ → ENGINE & PROVIDERS → Speaking → install |

---

## 4. First launch — the Gemini API key

Start JARVIS:

```bash
python main.py
```

On the very first run you will see the **◈ INITIALISATION REQUIRED** overlay:

1. **GEMINI API KEY** — paste your key (it starts with `AIza…`).
   Get one free at **https://aistudio.google.com/apikey** (sign in with a Google
   account → *Create API key*).
2. **OPERATING SYSTEM** — auto-detected; confirm or change it.
3. Confirm. The key is saved to `config/api_keys.json` and JARVIS connects.

Notes:

- The key file is **plain text** on disk — treat the folder as private
  (see §13).
- If the key is ever rejected, JARVIS stops hammering the API and asks you to
  re-enter it.
- No key? You can still run fully locally later via ENGINE & PROVIDERS (§10),
  but the default conversation engine is Gemini Live.

---

## 5. Screen tour — the HUD and its drawers

The main window is the **HUD**, laid out as a dashboard:

- **Header bar** — your assistant's brand + version on the left, four navigation
  pills (**Home**, **System**, **Tools**, **Settings**), the assistant name and
  tagline in the centre, and on the right a live **Online / Ready-to-assist**
  status plus a **clock** showing the time, date and region you select
  (default **Dhaka, Bangladesh** — see *Clock region* below).
- **Left column — SYS MONITOR card** — live CPU / MEM / NET / GPU / TMP bars,
  uptime, process count and OS, with the AI CORE / SEC / PROTOCOL lamps below.
- **Avatar** — an animated human head, lit and drawn in software. It lip-syncs
  to the audio (~50 mouth shapes/second), blinks, nods, looks away while
  thinking, and meets your eyes while listening.
- **Waveform** — pulses to real audio: your mic while listening, JARVIS while
  speaking.
- **Right column — three cards**: **ACTIVITY LOG** (running log of what
  happened), **FILE UPLOAD** (drop or browse a file to attach), and
  **COMMAND INPUT** (type instead of speaking) with the **INTERRUPT [ESC]**
  and **MICROPHONE ACTIVE** buttons.
- **Content panel** — scrollable layer beneath the HUD for web results, news,
  files and search data. Videos (YouTube/local/URL) play *where the avatar
  sits*, starting muted; ask for sound.

**Clock region.** Settings drawer → **CLOCK REGION** picks the zone the header
clock displays (Dhaka, Kolkata, Dubai, Istanbul, London, Berlin, Tokyo,
Shanghai, Singapore, Sydney, New York, Chicago, Los Angeles, UTC, or your
system's local time). The choice is saved to `config/api_keys.json`
(`clock_timezone`) and survives restarts. It only changes the displayed clock —
logs, reminders and the assistant's own sense of "now" still use system time.

Drawers (the **Settings** and **System** pills in the header):

| Drawer | What's inside |
|---|---|
| ⚙ **Settings** | Clock region, remote control, desktop shortcut, auto-start, assistant name, your name, voice, theme colour (hue wheel/hex — the avatar retints), audio device pickers with TEST meters, and the panels below |
| 🔌 **ENGINE & PROVIDERS** | Choose Gemini Live or your own STT + LLM + TTS stack (§10) |
| 🛡 **SECURITY && PRIVACY** | The full security panel (§11) |
| 🖥 **System** | Everyday switches: fullscreen, morning brief, wake word, sleep/wake, push-to-talk status, HUD style |
| **Memory panel** | Every stored fact, when it was learned, one-click delete (§9) |

The **camera activity indicator** (a dot + status in the Security panel, and a
HUD indicator while the camera runs) is always visible whenever the camera is
active — the camera can never run secretly.

---

## 6. Talking to JARVIS

Three ways to hold the conversation — mix them freely:

### 6.1 Normal voice mode

Just talk. JARVIS hears you through the selected microphone, answers in your
language, and its avatar lip-syncs. The **self-echo guard** recognises the tail
of its own voice and drops it, so it never answers itself.

### 6.2 Push-to-talk — `Ctrl+Space`

Hold **Ctrl+Space** and the mic opens; release and it closes. The mic is closed
the rest of the time. Truly global on Windows; window-scoped on macOS/Linux.

### 6.3 Wake word — "Hey Jarvis" (opt-in)

Enable it in the CONTROLS drawer (one-click install on first use). JARVIS sleeps
until called, **never streams audio while asleep**, and auto-sleeps after 2
minutes of silence. A manual sleep/wake button is next to it.

### 6.4 Typing

Use the text input for anything you can say. Voice and keyboard switch
seamlessly mid-conversation.

### Other behaviour worth knowing

- **Instant acknowledgment** — longer tasks get a short spoken "on it" in your
  language immediately, so you are never left in silence.
- **Session continuity** — a dropped connection, voice change or device change
  no longer wipes the conversation.
- **Unlimited sessions** — sliding-window context compression lets one
  conversation run for hours.
- **Language** — JARVIS detects and remembers your spoken language; in local
  mode the *voice itself* follows the language you spoke (§10).

---

## 7. What you can ask — feature reference

Everything below is a real, auto-discovered tool. Example phrases are starting
points, not a fixed grammar.

### Apps, windows and desktop

| Say something like | Tool | Notes |
|---|---|---|
| "Open WhatsApp" / "Open Notepad" | `open_app` | Already running? It raises the existing window instead of starting a second copy. Closing asks the app politely so unsaved work survives, and JARVIS's own processes are never a target |
| **"Open C drive"** / "Open D:\Movies" | `open_app` | Opens the drive/folder in File Explorer — **only if the drive is granted ACCESS + READ** (§11.9) |
| "Show the desktop" / "Switch window" / taskbar ops | `desktop` | Window management and desktop-level operations |
| "Take a screenshot" / mouse & keyboard control | `computer_control` | Platform-honest: on Wayland or a macOS without permissions it tells you what it *cannot* do instead of narrating a fake click |

### System settings and power

| Say | Tool | Notes |
|---|---|---|
| "Set volume to 40%" / "Increase brightness" | `computer_settings` | Volume belongs to the speaker you picked, not the system default |
| "Turn off WiFi" / "Shutdown" / "Restart" | `computer_settings` | **Irreversible actions wait for a button YOU press** — the model cannot confirm them itself (§8) |
| "How is my CPU / RAM / temperature?" | `system_monitor` | Continuous telemetry with localized voice alerts |

### Files

| Say | Tool | Notes |
|---|---|---|
| "Move this file to…" / "Rename…" / "Create a folder…" | `file_controller` | Every change is undoable (§8) and drive-guarded (§11.9) |
| "Read / summarise this document" / "What does this file say?" | `file_processor` | Content reaches the model wrapped as untrusted data — instructions inside a file are reported, not obeyed |

### Web and browser

| Say | Tool | Notes |
|---|---|---|
| "Search for…" / "Latest news on…" / "Compare prices of…" | `web_search` | Modes: `news` / `research` / `price` / `compare` / `search`. Gemini Grounded first, DuckDuckGo fallback |
| "Open this website" / "Click the first link" / "Next tab" | `browser_control` | Opens in your own browser; clicks/typing happen in your open window (§ below) |
| "Find flights from X to Y" | `flight_finder` | Search helper |

**How browser control works now.** Opening a site or running a web search is
handed to your real browser (your profile, your sign-ins) and then **confirmed
by looking at the screen** — JARVIS tells you what actually appeared, not just
what it asked for. Clicking, typing, scrolling and reading happen **in the
browser window you already have open**: JARVIS brings it forward, finds the
element you named by vision (say it plainly: *"the YouTube search bar at the
top"*), clicks it and types like a person — no second window is created. If
the element is not on screen, or another app steals focus mid-action (browser
lockers, installers, UAC prompts), it stops and tells you instead of typing
blind. Only when no browser window is open at all does it fall back to a
controlled Playwright window for multi-step page automation.

### Media

| Say | Tool | Notes |
|---|---|---|
| "Play … on YouTube" | `youtube_video` | Plays on the HUD, starts muted |
| "Play this video file / URL" | `video_player` | Same HUD player |

### Communication and life

| Say | Tool | Notes |
|---|---|---|
| "Send a message to … on WhatsApp/Telegram" | `send_message` | Compose and send through the web apps |
| "What's the weather in …?" | `weather_report` | Live data, personalised from memory |
| "Remind me to … at …" | `reminder` | OS-native scheduled notifications (Task Scheduler / LaunchAgent / systemd) |
| Morning briefing | automatic | First boot: greeting, time, yesterday's recap, live news |
| Proactive check-ins | automatic | Time- and context-aware; session summaries mentioned next morning, never repeated |
| "Watch for news about …" | `background_monitor` | Checks once a day, alerts naturally — only topics you configure |

### Developer tools

| Say | Tool | Notes |
|---|---|---|
| "Write / explain / fix this code" | `code_helper` | Code assistance |
| "Build me a …" (multi-step goal) | `dev_agent` | Agent-mode planning for complex tasks |
| "Update my games" | `game_updater` | Game-library helper |

### Vision

| Say | Tool | Notes |
|---|---|---|
| "What's on my screen?" | `screen_process` | Screen capture piped into the session, labelled by source |
| Webcam vision | on request | Same pipeline, labelled as webcam |

### Security (voice commands)

| Say | Effect |
|---|---|
| "Security status" | Reports privacy state, camera, face, voice, drives |
| "Emergency lock" / "Lock privacy" | Immediate emergency lock |
| "Unlock privacy with PIN 1234" | Unlocks via your backup PIN — only when *you* say the PIN |
| "Which drives can you access?" | Lists effective drive permissions |

> Drive permissions and privacy-mode changes can **only** be changed by you in
> the Security & Privacy panel. The assistant can never grant itself access.

---

## 8. Built-in safety — confirmation, undo, honest answers

These are properties of the base assistant that the security upgrade preserves:

- **Real confirmation gate** — shutdown, restart and WiFi wait for a button
  *you* press. The model cannot confirm its own irreversible actions.
- **Undo** — take back files JARVIS moved, renamed, created or wrote, and
  settings it changed. Say "undo".
- **It says what it checked** — every app-driving tool answers
  `done` / `unverified` / `failed`. `done` means verified (e.g. the process
  table was watched); `unverified` means the request went out but could not be
  confirmed — and JARVIS says exactly that instead of rounding it to "done".
- **Untrusted content boundary** — web pages and documents reach the model
  wrapped as data. An instruction hidden inside one is reported, not obeyed.
- **Tool-loop brakes** — a repeated identical tool call is answered from the
  previous result (no double-launching apps); long wandering chains are capped.

---

## 9. Memory

- JARVIS remembers projects, preferences and personal context across sessions
  (`memory/long_term.json`).
- **No size limit, nothing silently forgotten** — the prompt carries what fits;
  the rest is looked up on demand from a local search.
- **Memory panel** — see every fact, when it was learned, and delete any of it
  in one click.
- `save_memory` / `recall_memory` are *sensitive tools* under the security
  system (§11) — in Strict mode they need your verified identity.

---

## 10. Engines & Providers — local and third-party models

Open ⚙ → **🔌 ENGINE & PROVIDERS**. One panel, four decisions:

1. **Who holds the conversation** — Gemini Live (default), or your own stack:
   - **① Hearing** — Whisper on this machine (CPU), or a transcription API.
   - **② Thinking** — anything serving `/v1/chat/completions`: Ollama, LM
     Studio, llama.cpp, vLLM (local) or OpenAI, Groq, DeepSeek, Mistral, xAI,
     OpenRouter, Together (hosted). One setting, because they share a protocol.
   - **③ Speaking** — Piper (neural, ~50 languages, fully offline), your
     system's own voices, or ElevenLabs.
2. **Side calls** — the assistant's own background requests (reading documents,
   screen understanding, code, page parsing) can fall back to another model via
   one dropdown, without touching the conversation or the voice. Useful when
   Gemini's *text* quota empties before the voice quota.

Every part has a **TEST** button that connects, measures and reports in a
sentence ("Answered in 0.36s", "Nothing answered at that address — is the
server running?").

Good to know:

- **Nothing is installed or imported until you use it.** On a default install
  the `providers/` folder is never loaded.
- **Piper voices**: 176 voices, 52 languages; ~63 MB download once per voice;
  synthesis measured ~15× faster than real time on CPU. The voice **follows the
  language you spoke** (Whisper reports it) and switches mid-conversation. Only
  voices already on disk are considered mid-sentence.
- **Reasoning stays private** — `<think>…</think>` blocks from qwen3 /
  deepseek-r1 style models are filtered from speech, logs and history.
- **Tool budget** — small local models get a core-first subset of tools (by
  count *and* payload size) automatically for loopback/private endpoints.
  Gemini always gets every tool.
- **Model ladder** — nine Gemini models in a measured order; a quota, timeout
  or outage steps to the next rung instead of failing.
- `localhost` is resolved to IPv4 explicitly on Windows (Ollama binds IPv4).

---

## 11. Security & Privacy — the complete guide

### 11.1 The guarantees

These are enforced in code, not promises in the UI:

1. **The camera never operates secretly.** It only runs after you tick
   *Camera permission*, and an activity indicator is shown while it runs.
2. **Permissions are never silently granted.** Only you can tick a permission,
   in the panel. The assistant cannot grant itself access through any tool.
3. **Enforcement is programmatic.** Every file operation, app/drive open and
   shell command passes the drive guard — including `os.startfile`,
   `subprocess` and `os.system` paths.
4. **Unapproved drives default to DENIED** when drive protection is on.
5. **Path traversal and symlink bypasses are blocked** — paths are canonicalised
   (realpath) before checking, so `D:\..\C:\secret` or a symlink pointing into
   a denied drive cannot sneak through.
6. **Voice alone never unlocks highly sensitive operations** — face or PIN is
   also required.
7. **All biometric data stays local and encrypted** (§11.11).

### 11.2 Opening the panel

⚙ Settings drawer → **🛡 SECURITY && PRIVACY**.

The panel has sections: **Privacy Mode · Camera · Face Security · Voice
Security · Backup PIN & Emergency Lock · Drive Permissions · Status &
Notifications**. Changes apply immediately — no restart needed.

### 11.3 Recommended setup order (10-minute checklist)

Do these in order; each step works on its own:

1. **Set a backup PIN** (§11.4) — do this *first*, so you can always get back in.
2. **Grant drive permissions** (§11.9) — tick ACCESS **and** READ (plus any
   other rights you want) for each drive you use.
3. **Turn on Camera permission** (§11.5) and register your **face** (§11.6).
4. **Register your voice** (§11.7) and enable Voice Verification.
5. Choose a **privacy mode** (§11.8) — start with Open Voice, move to Strict
   once face + voice are registered.
6. Ask JARVIS: *"security status"* — confirm everything reads the way you expect.

> **Upgraded from an older build?** Voice templates from before the upgrade
> are incompatible with the improved speaker embedding. Press **DELETE VOICE
> DATA**, then **REGISTER VOICE** again. Face data and PIN are unaffected.

### 11.4 Backup PIN & emergency lock

- **SET PIN** — type a PIN/password (minimum 4 characters) and press SET PIN.
  It is stored only as a PBKDF2 hash (200,000 iterations) inside the encrypted
  vault — never in plain text.
- **⚠ EMERGENCY LOCK** — one press (or say *"emergency lock"*): everything
  sensitive locks immediately, regardless of mode.
- **UNLOCK WITH PIN** — type the PIN and press it (or say *"unlock privacy with
  PIN 1234"*). A successful PIN unlock opens a **5-minute window** for
  sensitive operations, then expires.
- If the camera dies or you leave in Strict mode, the PIN is your way back in
  without the camera.

### 11.5 Camera — permission, indicator, camera-loss shutdown

- **Camera permission (camera NEVER runs without this)** — the master consent
  checkbox. Off = the camera code never opens a device.
- While the camera runs, the panel shows a live **● indicator + status**
  (ACTIVE / OFF / DISCONNECTED), and the HUD shows camera activity.
- **Camera index** — default 0; change it in `config/security_settings.json`
  (`camera_index`) if you have several cameras.
- **"Shut down the assistant if the camera is turned off / disconnected"** —
  **ON by default.** When the security camera was active and then is turned off
  in settings, unplugged, or fails:
  1. the privacy state goes to **emergency lock**,
  2. the conversation stops,
  3. **only the JARVIS process exits** — your PC is never shut down.

  It fires once, and only if the camera had actually been active (turning the
  camera off before it ever ran does not kill the app). Untick the box (or set
  `"camera_loss_shutdown": false`) if you prefer lock-without-exit behaviour.

### 11.6 Face security (100% local)

Two independent switches:

- **Face Tracking** — detection, tracking, presence, head position/movement.
- **Face Recognition** — *who* it is: authorized user vs unknown person.

Registration:

1. Camera permission must be ON.
2. Press **▸ REGISTER FACE** and look at the camera. It collects **12 samples**
   (progress shows `FACE n/12`). Vary your angle slightly as prompted.
3. On first use it downloads two small ONNX models (YuNet detector + SFace
   recogniser) into `config/security_data/models/`. If the download fails
   (e.g. DNS error `[Errno 11001]`), check your connection and press again —
   see §15.

What you get:

- **Authorized user present/absent** status, updated live.
- **Unknown person** alert when a face that is not yours appears.
- **Head movement** readout (position/motion) in the panel.
- **Presence grace** — an absence shorter than ~3 seconds does not lock.
- In **Strict mode**: leaving locks the assistant; returning re-verifies you
  automatically; a camera disconnect triggers the camera-loss behaviour (§11.5).
- **DELETE FACE DATA** removes the stored template at any time.

Processing is local OpenCV + ONNX at ~8 frames/second by design (low CPU).
**No frame ever leaves this PC.**

### 11.7 Voice security (speaker identity)

**Voice Verification** is separate from speech recognition: recognition hears
*what* you said; verification checks *who* said it.

Registration:

1. Press **▸ REGISTER VOICE** and **speak naturally** — it records **4 segments**
   (~1.6 s each, progress shows `VOICE n/4`). Normal sentences are perfect.
2. The panel then shows VERIFIED / NOT VERIFIED live.

Behaviour:

- Verification runs on short (~0.8 s) windows of your mic audio; a match stays
  valid for **90 seconds** and refreshes as you keep talking.
- A clearly different speaker (similarity below the alert threshold) raises an
  **unauthorized-voice** notification.
- The template adapts slowly to your voice over time (robust to volume and
  intonation changes; measured to reject a different vocal tract).
- **Voice alone never unlocks sensitive operations.** Sensitive tools need
  voice **plus** face (Strict) or your PIN/authorization — exactly as the panel
  note says.
- **DELETE VOICE DATA** removes the template. After deleting, Strict mode
  falls back to Open until you register again.

### 11.8 Privacy modes

| | **OPEN VOICE** (default) | **STRICT** |
|---|---|---|
| Who may talk | Anyone | Only the verified user (face + voice) |
| Sensitive operations | Need authorization once an identity is set up | Need face + voice verified |
| You leave the camera | Nothing locks | **Auto-lock** (after the grace period) |
| You return | — | **Auto re-verify / unlock** |
| Camera disconnect | Camera-loss shutdown if enabled (§11.5) | Emergency lock + camera-loss shutdown |
| Unknown person | Alert | Alert + treated as unauthorized |
| Requirements | None | Face **and** voice registered |

Switching to Strict without both registrations is refused (the radio button
snaps back) — register first. **Emergency lock** and the **PIN window** work
identically in both modes.

Sensitive tools (the ones gated): `file_controller`, `file_processor`,
`computer_control`, `computer_settings`, `send_message`, `browser_control`,
`dev_agent`, `code_helper`, `desktop`, `open_app`, `game_updater`,
`video_player`, `save_memory`, `recall_memory`, `undo`, `screen_process`.
(The list lives in `config/security_settings.json` → `sensitive_tools`.)

### 11.9 Drive permissions — the part most people get wrong

**The table.** Every detected drive gets a row with six checkboxes:

```
DRIVE   ACCESS   READ   WRITE   CREATE   EDIT   DELETE
C:      [ ]      [ ]    [ ]     [ ]      [ ]    [ ]
D:      [ ]      [ ]    [ ]     [ ]      [ ]    [ ]
...
```

**ACCESS is the master gate.** Ticking ACCESS alone grants *nothing usable* —
you must also tick **READ** to open or browse the drive, and WRITE / CREATE /
EDIT / DELETE for those operations. The panel shows a hint reminding you of
this. Example — to let JARVIS open and read C: but never change it:

```
C:   ACCESS ✔   READ ✔   WRITE ✘   CREATE ✘   EDIT ✘   DELETE ✘
```

Then *"Open C drive"* opens `C:\` in File Explorer. With ACCESS only, the same
request is refused with a message telling you READ is missing.

**The rules, exactly:**

1. **Master switch — "Drive Protection".**
   - **ON:** any drive *without* an explicit entry is **DENIED everything**
     (default-deny).
   - **OFF:** unlisted drives keep legacy (unrestricted) behaviour — **but
     explicit per-drive entries are still enforced**. A drive you configured
     is governed by its checkboxes even with the master switch off.
2. **Per-operation checks.** Opening/browsing needs ACCESS + READ; saving needs
   WRITE; creating needs CREATE; modifying needs EDIT; removing needs DELETE.
3. **Enforced everywhere, in code.** The guard wraps the file tools,
   `open_app`, `os.startfile`, `subprocess` and `os.system`. Shell commands are
   parsed: the verb decides the operation (e.g. `del` → delete, `copy` →
   read+create) and every path argument is checked.
4. **No traversal / symlink tricks.** Paths are canonicalised with realpath
   before checking; `..` segments and symlinks resolve to their true target
   drive first.
5. **Immediate revocation.** Untick a box and the very next operation is
   denied — no restart, no cache to wait out.
6. **The assistant cannot change any of this.** `security_control` can *report*
   drive status; granting is panel-only, by you.
7. The project's own folder is exempt for its internal files, so JARVIS keeps
   working no matter what you deny.

**Refusals are spoken honestly** — e.g. *"C: read denied — grant READ in the
Security & Privacy panel"* — never rounded to "done".

### 11.10 Status, notifications and logs

- The panel's **status section** refreshes live: privacy state
  (VERIFIED / PIN / NOT VERIFIED / EMERGENCY), camera status, face
  presence + head movement, voice verification, PIN state.
- **Notifications** list security events (unknown person, unauthorized voice,
  camera lost, lock/unlock, shutdown) with timestamps; the same events appear
  in the HUD log prefixed `SEC:`.
- Voice: *"security status"* gives you the spoken summary at any time.

### 11.11 Where biometric data lives — and how it is protected

```
config/security_data/
├── face.enc      ← encrypted face templates
├── voice.enc     ← encrypted voice templates
├── pin.enc       ← encrypted vault incl. the PBKDF2 PIN hash
└── models/       ← YuNet + SFace ONNX models (public, not personal)
```

- Blobs are encrypted with **Fernet**; on Windows the key is additionally
  wrapped with **DPAPI** (bound to your user account).
- Settings (switches, drive table) live separately in
  `config/security_settings.json` — plain JSON, no biometric content.
- Nothing is uploaded. Face frames, mic audio for verification, and templates
  never leave the machine.
- Deleting a `.enc` file (or using the DELETE buttons) removes that identity
  permanently.

### 11.12 Security on the phone dashboard

The paired phone dashboard has a **🛡 Security page** (`/security`): live
privacy/camera/face/voice status, the drive table, and the camera-loss toggle —
the same controls, behind the dashboard's pairing key (§12).

---

## 12. Phone dashboard — remote control

JARVIS serves a dashboard on your local network:

1. The HUD shows a **QR code** (and a manual address like `192.168.x.x:8000`).
2. Scan it with your phone, enter the **pairing key** shown on the HUD.
3. You get: live status, text commands, wake/sleep, file upload, phone-audio
   input, and the **Security page** (§11.12).

Transport and access:

- **Default: plain HTTP on port 8000.** The pairing key, rate limits and token
  expiry still gate access; commands travel the LAN unencrypted (the page says
  so on its own badge).
- **Optional HTTPS:** add `"dashboard_https": true` to `config/api_keys.json`
  and restart. A self-signed certificate is generated into `config/certs/`;
  the dashboard moves to **https://…:8001** (port 8000 redirects), and each
  phone must trust the certificate once. This also enables the AES-GCM layer
  for commands.
- The firewall is opened for the dashboard ports automatically (one Windows
  UAC prompt, best-effort on other OSes).
- **Revoke devices** — the dashboard can revoke all paired devices at once.

---

## 13. Settings and data files

| Path | Contents | Sensitive? |
|---|---|---|
| `config/api_keys.json` | Gemini API key, `dashboard_https` flag, `clock_timezone` (header clock region) | **Yes — plain text.** Keep the folder private |
| `config/security_settings.json` | Security switches, drive table, thresholds | No biometrics; safe to inspect |
| `config/security_data/*.enc` | Face / voice / PIN vault | Encrypted (Fernet + DPAPI on Windows) |
| `config/security_data/models/` | Public ONNX face models | No |
| `config/certs/` | Dashboard TLS key/cert (only if HTTPS enabled) | Yes — private key |
| `memory/long_term.json` | Everything JARVIS remembers about you | Personal data |
| `plugins/` | Your add-on skills | — |
| `providers/` | Engine provider declarations | — |

Useful keys in `security_settings.json` (all editable in the panel except
`camera_index`): `privacy_mode`, `camera_permission`, `camera_index`,
`camera_loss_shutdown`, `face_tracking_enabled`, `face_recognition_enabled`,
`voice_verification_enabled`, `drive_protection_enabled`, `drives`,
`sensitive_tools`, plus tuning thresholds (`face_match_threshold`,
`voice_match_threshold`, `voice_verify_ttl_seconds`, `presence_grace_seconds`,
`pin_auth_window_seconds`).

---

## 14. Extending JARVIS — plugins, providers, actions

- **Plugin** — drop a single `.py` file into `plugins/`; JARVIS learns the new
  skill on next launch.
- **Action/skill** — every bundled skill declares its own `TOOL` dict + handler
  in `actions/` and is auto-discovered. Adding one is a single file.
- **Provider** — a new STT/LLM/TTS service is one file in `providers/`; the
  ENGINE & PROVIDERS form is generated from the provider's own declaration.
- The assistant's **runtime self-knowledge** regenerates each session: rename
  it or add a plugin and it knows its new abilities (and limits).

---

## 15. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| **Face model download fails — `[Errno 11001]` / DNS error** | No internet or DNS blocked at that moment. Reconnect and press REGISTER FACE again; the download resumes into `config/security_data/models/`. Corporate DNS may need the models fetched on another network |
| **"Open C drive" is refused** | The drive needs **ACCESS *and* READ** ticked (§11.9). ACCESS alone is only the master gate — the refusal message says which right is missing |
| **A configured drive is blocked even though Drive Protection is OFF** | Expected: explicit per-drive entries are always enforced. Adjust that drive's checkboxes |
| **An unlisted drive suddenly stopped working** | Drive Protection was turned ON → unlisted drives default to DENIED. Add an entry for it, or turn the master switch off |
| **JARVIS exits when I turn the camera off / unplug it** | By design: *camera-loss shutdown* (ON by default) emergency-locks and closes **only the assistant**. Untick "Shut down the assistant if the camera is turned off / disconnected" to keep it running locked instead |
| **Voice shows NOT VERIFIED after upgrading** | Old voice templates are incompatible with the improved embedding. DELETE VOICE DATA → REGISTER VOICE again (§11.3) |
| **Sensitive commands refused in Open mode** | Once an identity is registered, sensitive ops need authorization: keep talking so voice stays fresh (90 s window), be in view of the camera, or use your PIN (5-minute window) |
| **Strict mode radio button snaps back** | Face and voice must both be registered before Strict is allowed |
| **Locked out (camera gone, no face)** | Use **UNLOCK WITH PIN** in the panel, or say "unlock privacy with PIN …". No PIN set? Delete `config/security_data/face.enc` / `voice.enc` to reset identities (§18) |
| **Camera never starts** | Camera permission is OFF (it never runs without it), another app holds the camera, or wrong `camera_index` |
| **Microphone seems dead** | ⚙ Settings → audio device picker → press **TEST** and watch the live meter; pick the device that actually moves. Also check push-to-talk isn't expected (Ctrl+Space) and the wake word isn't asleep |
| **API key invalid** | JARVIS stops retrying and asks for a new key — re-enter it (create a fresh one at Google AI Studio if needed) |
| **Phone can't reach the dashboard** | Same Wi-Fi? Use the manual address `IP:8000`. Windows firewall: allow the app (setup opens the ports, one UAC prompt). With HTTPS on, accept the certificate warning once |
| **Wake word button does nothing** | First click installs `openwakeword` — wait for the install to finish; it is deliberately not in requirements.txt |
| **Local voice silent for some languages** | System voices only speak installed languages; a script they lack used to return silence. Use **Piper** (ENGINE & PROVIDERS) — it covers ~50 languages and errors now name the cause instead of returning silent success |
| **High CPU with camera on** | Face monitoring is capped at ~8 fps by design; if you changed `face_monitor_fps`, lower it back |
| **Checkboxes in the drive table look invisible** | You are on an old build — this build styles indicators explicitly (border + fill, green when ticked). Update to the current files |
| **"Type in the search bar" opens a second browser / says browser closed** | You are on an old build. Current `browser_control` types and clicks **in your already-open window** by looking at the screen (§7 Web and browser); it only falls back to a controlled window when no browser is open. Update and restart |
| **Browser typing stops with "another window took focus"** | Something stole focus mid-action (browser-locker app, installer, UAC prompt, or you alt-tabbed). Nothing was typed. Close the locker / finish the prompt and ask again |

---

## 16. Keyboard shortcuts

| Shortcut | Action |
|---|---|
| **Ctrl+Space** (hold) | Push-to-talk — mic open while held (global on Windows, window-scoped elsewhere) |
| Text input + Enter | Type a command instead of speaking |

---

## 17. Running the security tests

The upgrade ships with **44 tests** (27 unit + 17 integration), all using
temporary directories — your real config is never touched. From the project
root:

```bash
python -m security.tests.test_security
python -m security.tests.test_integration
```

They cover: encrypted storage round-trips, PIN hashing, drive default-deny and
explicit-policy enforcement (including master-off), path traversal/symlink
defence, shell-command vetting, voice discrimination (same speaker vs different
vocal tract), privacy state machine, camera-loss shutdown (fires once, only
after the camera was active, respects the setting), and the open-app drive path
end-to-end.

---

## 18. Reset and uninstall

- **Reset one identity** — panel buttons DELETE FACE DATA / DELETE VOICE DATA,
  or delete the matching `.enc` file in `config/security_data/`.
- **Reset all security** — delete `config/security_settings.json` and the
  `config/security_data/` folder. Everything returns to off-by-default.
- **Reset everything** — also delete `config/api_keys.json`, `config/certs/`
  and `memory/`.
- **Uninstall** — delete the project folder. Optional OS-level leftovers:
  scheduled reminders (Task Scheduler / LaunchAgent / systemd), the auto-start
  entry if you enabled it, and the dashboard firewall rules — remove them from
  the OS if you want a fully clean slate. Python packages remain in your
  environment; `pip uninstall -r requirements.txt` removes them.

---

## 19. Project structure

```
Mark-LVI-main/
├── main.py                  # conversation engines, tool gate, startup
├── ui.py                    # HUD, avatar, drawers, first-run overlay
├── setup.py                 # one-command installer
├── requirements.txt
├── readme.md                # Mark LVI feature documentation
├── SECURITY_SETUP.md        # security upgrade technical notes
├── USER_MANUAL.md           # this manual
├── actions/                 # auto-discovered skills (open_app, web_search, …)
├── core/                    # action loader, wake word, engines, helpers
├── security/                # the upgrade
│   ├── manager.py           #   orchestration, tool authorization, camera-loss
│   ├── face.py              #   YuNet + SFace monitor (local)
│   ├── voice.py             #   speaker verification (numpy-only)
│   ├── privacy.py           #   modes, emergency lock, PIN window
│   ├── drive_guard.py       #   per-drive enforcement + shell vetting
│   ├── storage.py           #   Fernet + DPAPI encrypted vault
│   ├── config.py            #   settings + defaults
│   ├── ui_overlay.py        #   the Security & Privacy panel
│   ├── dashboard_routes.py  #   phone /security page + API
│   └── tests/               #   44 tests
├── dashboard/               # FastAPI phone dashboard (static pages + server)
├── providers/               # engine provider declarations (lazy-loaded)
├── plugins/                 # your drop-in skills
├── memory/                  # long-term memory store
└── config/                  # api_keys.json, security_settings.json,
                             # security_data/ (encrypted), certs/
```

---

## 20. Credits and license
- **Created By Samin Easar** — A young tech enthusiast passionate about AI, programming, cybersecurity, and robotics, always eager to learn, innovate, and build the future.
- **Security & Privacy upgrade** — face/voice security, privacy modes, drive
  permission management and automatic protection, added without removing or
  changing any existing feature.

*Enjoy your assistant — and remember: the camera only runs when you say so,
and every drive stays denied until you tick the boxes yourself.*
