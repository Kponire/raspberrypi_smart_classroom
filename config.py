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
# Pi credentials — must match the piUsername/piPassword you set when registering
# the device in Admin → Devices. The Pi sends these as headers on telemetry.
PI_USERNAME    = _env("PI_USERNAME", _env("PI_USER", ""))
PI_PASSWORD    = _env("PI_PASSWORD", "")
# Legacy fallback (ignored if PI_USERNAME is set):
PI_EMAIL       = _env("PI_EMAIL", "")
# Poll intervals (seconds)
POLL_SESSION_S  = int(_env("POLL_SESSION_S", "5") or 5)
POLL_MATERIAL_S = int(_env("POLL_MATERIAL_S", "10") or 10)
POLL_TELEMETRY_S = int(_env("POLL_TELEMETRY_S", "30") or 30)
# TV kiosk: auto-open Jitsi in Chromium when session goes live
AUTO_OPEN_JITSI = _env("AUTO_OPEN_JITSI", "true").lower() not in ("0", "false", "no")
JITSI_BROWSER_CMD = _env("JITSI_BROWSER_CMD", "")
FULLSCREEN     = _env("FULLSCREEN", "true").lower() not in ("0", "false", "no")

# Jitsi / JaaS. When JAAS_APP_ID is set the Pi targets the 8x8.vc tenant and
# mints a device token from the backend — JaaS shows an 8x8 login prompt to
# anyone joining without one. Falls back to public meet.jit.si when unset.
JAAS_APP_ID    = _env("JAAS_APP_ID", _env("VITE_JAAS_APP_ID", ""))
JITSI_DOMAIN   = _env("JITSI_DOMAIN", "")   # default 8x8.vc when an App ID is set
JITSI_HOST     = _env("JITSI_HOST", "")     # full override, e.g. https://meet.jit.si
