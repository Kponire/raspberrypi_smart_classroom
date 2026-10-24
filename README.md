# Raspberry Pi — Classroom TV Interface

Zero-touch Tkinter kiosk that mirrors the web **Live Classroom** on the classroom TV.

- **Nothing is manual for the student.** Pi polls the backend and switches between `IDLE ↔ LIVE` itself. Power + internet are always on, so the Pi just stays running.
- Shows the same live state the lecturer controls: course, Jitsi room, elapsed time, attendees, recording badge, and the last **pushed material** (slides/pdf) as a bottom banner.
- USB **camera + mic** plugged into the Pi: their health is reflected in the right rail via `device.cameraHealth / micHealth`; telemetry (CPU, mem, disk, uptime) is posted to `POST /api/devices/:id/telemetry`.
- When the lecturer presses **Start lecture**, the Pi optionally auto-opens the Jitsi room in Chromium kiosk on the TV.

## What it looks like

```
┌─────────────────────────────────────────────────────────────────┐
│ SMART CLASSROOM   Classroom A · Block B 101   ● ON AIR  12:34  02:31 PM  Thu 22 Oct │
├──────────────────────────────────────────┬──────────────────────┤
│  CSC 301 · Data Structures    sc-csc301-…  ● REC                 │ Device status        │
│  ┌────────────────────────────────────┐  │ Camera      OK       │
│  │  Lecture is live / Waiting…       │  │ Microphone  OK       │
│  │  (TV kiosk — Jitsi opens in       │  │ Speaker     FAULT    │
│  │   Chromium when live)             │  │ Pi heartbeat OK       │
│  └────────────────────────────────────┘  │                      │
│  ▸  Week 4 — Binary Trees  [PDF]         │ Smart TV  Paired     │
│                                          │ Attendees  18        │
│                                          │ Session facts …      │
└──────────────────────────────────────────┴──────────────────────┘
Esc exits fullscreen, F11 toggles.
```

## Quick start (dev on Windows)

```powershell
cd raspbarrypi_interface
copy .env.example .env   # edit API_URL if backend isn't on localhost:3000
py -3 -m pip install -r requirements.txt
py -3 main.py
```

## Pi setup (Raspberry Pi OS, TV via HDMI)

```bash
chmod +x pi-setup.sh
./pi-setup.sh            # installs chromium, hides cursor, enables autostart
cp .env.example .env
nano .env                # set API_URL to backend LAN IP, e.g. http://192.168.1.50:3000
# optional: pin CLASSROOM_ID / DEVICE_ID from Admin → Classrooms
python3 main.py          # test once; then reboot — it autostarts
```

### `.env` keys

| key | default | notes |
|---|---|---|
| `API_URL` | `http://localhost:3000` | Backend base (no `/api`). On the Pi use the LAN IP. |
| `CLASSROOM_ID` / `DEVICE_ID` | auto-picks first | Pin to one room if you have multiple classrooms. |
| `PI_USERNAME` / `PI_PASSWORD` | — | Pi credentials for `POST /devices/:id/telemetry` — must match the device's `piUsername`/`piPassword` set in Admin → Devices. Sent as `x-pi-username` / `x-pi-password` headers. |
| `POLL_SESSION_S` | `5` | How often to check for a live session. |
| `POLL_TELEMETRY_S` | `30` | How often to push telemetry. |
| `AUTO_OPEN_JITSI` | `true` | Auto-launch Chromium kiosk on `status=live`. |
| `JITSI_BROWSER_CMD` | auto-detect | Override kiosk command. |
| `FULLSCREEN` | `true` | `false` for windowed dev. |

`API_URL` also falls back to `VITE_API_URL` / `Backend/.env` if present.

## How it works

- Polls `GET /api/sessions`, `/api/classrooms`, `/api/devices`, `/api/courses`, `/api/materials?courseId=…` — same public endpoints the web `LiveClassroomPage` uses. No student login.
- Live = any `LectureSession` with `status === "live"` (prefers one matching the pinned classroom). Elapsed timer is from `startsAt`. Recording badge shows when `recordingId` is set. Material banner shows the newest `pushedToTv === true`.
- Jitsi URL is built the same way as the web app: `https://meet.jit.si/<room>?config.prejoinPageEnabled=false&userInfo.displayName=Classroom TV`.
- Telemetry via `POST /api/devices/:id/telemetry` with `psutil` when installed; otherwise just uptime. The right rail mirrors `Device.cameraHealth / micHealth / speakerHealth / status`.

## Hardware

- Raspberry Pi 4/5, HDMI to TV, USB camera + USB mic (UVC / USB-audio — no config needed; health is backend-driven).
- Full power + internet are assumed always on — no sleep, no manual wake.

## Files

- `main.py` — Tkinter kiosk (fully automated, no buttons students need to press).
- `api_client.py` — tiny stdlib HTTP client (no `requests` needed at runtime; `requirements.txt` is optional).
- `config.py` — env loader + defaults.
- `pi-setup.sh` — one-shot Pi OS setup (chromium, autostart, systemd user service).
