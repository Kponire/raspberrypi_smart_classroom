import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / "Backend" / ".env", override=False)

def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()

API_URL        = _env("API_URL", _env("VITE_API_URL", "http://10.160.124.214:3000")).rstrip("/")
API_PREFIX     = "/api"
CLASSROOM_ID   = _env("CLASSROOM_ID", "example-classroom-id")
DEVICE_ID      = _env("DEVICE_ID", "example-device-id")
DEVICE_NAME    = _env("DEVICE_NAME", "Classroom Pi")
# Optional service account — Pi logs in to send telemetry; if blank, telemetry is best-effort anonymous.
PI_EMAIL       = _env("PI_EMAIL", "")
PI_PASSWORD    = _env("PI_PASSWORD", "")
# Poll intervals (seconds)
POLL_SESSION_S  = int(_env("POLL_SESSION_S", "5") or 5)
POLL_MATERIAL_S = int(_env("POLL_MATERIAL_S", "10") or 10)
POLL_TELEMETRY_S = int(_env("POLL_TELEMETRY_S", "30") or 30)
# TV kiosk: auto-open Jitsi in Chromium when session goes live
AUTO_OPEN_JITSI = _env("AUTO_OPEN_JITSI", "true").lower() not in ("0", "false", "no")
JITSI_BROWSER_CMD = _env("JITSI_BROWSER_CMD", "")  # e.g. "chromium-browser --kiosk --noerrdialogs --disable-infobars"
FULLSCREEN     = _env("FULLSCREEN", "true").lower() not in ("0", "false", "no")
