# AI Agent for Windows

A desktop AI assistant project with voice interaction, a graphical interface, computer automation, browser tools, memory, and an optional remote dashboard.

> **Project note:** The supplied source package identifies the application as **MARK LVI** and credits its original project author, **FatihMakes**. This repository is a packaged copy of that project; retain the original notices and license when redistributing or modifying it.

## Features

- Voice-based interaction and configurable AI providers
- Desktop interface with an animated assistant avatar
- Computer and application control
- Browser automation and web search
- Local memory and reminders
- File and document utilities
- Optional remote dashboard
- Extensible actions and plugins

## Requirements

- Python **3.11–3.13** (the project setup script documents the tested range)
- Windows, macOS, or Linux support as described by the upstream project
- Internet connection for online AI providers and browser automation
- API credentials for whichever cloud provider you choose

## Quick start

1. Download or clone this repository.
2. Open a terminal in the project folder.
3. Run the setup script:

   ```bash
   python setup.py
   ```

4. Start the application using the entry point documented in the included user manual.
5. Add your own provider credentials locally when prompted or through the application's settings.

See [USER_MANUAL.md](USER_MANUAL.md), [User Manual.pdf](User%20Manual.pdf), and [SECURITY_SETUP.md](SECURITY_SETUP.md) for detailed guidance.

## Security

**Never commit API keys, OAuth tokens, personal memory databases, certificates, or biometric/security data.** Keep local configuration files out of Git and use the included `.gitignore` as a starting point. If a credential has ever been shared in an archive or repository, revoke it and generate a replacement.

## Repository contents

- `actions/` — assistant actions and automation features
- `core/` — application engine and shared runtime
- `dashboard/` — optional dashboard
- `memory/` — memory components
- `plugins/` — optional integrations
- `providers/` — model, speech, and voice providers
- `security/` — security and privacy components
- `main.py`, `ui.py` — application entry points and interface

## Credits and license

Please consult the included [LICENSE](LICENSE) and upstream attribution before using or redistributing this project. Preserve copyright and license notices.

---

**Status:** Personal project repository. Documentation and packaging may be refined as the project is reviewed.
