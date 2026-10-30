from __future__ import annotations
import json
import urllib.request
import urllib.error
import urllib.parse
from typing import Any, Optional

import config


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class ApiClient:
    def __init__(self):
        self.token: Optional[str] = None
        self.base = f"{config.API_URL}{config.API_PREFIX}"

    def _pi_headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if config.PI_USERNAME:
            h["x-pi-username"] = config.PI_USERNAME
            h["x-device-username"] = config.PI_USERNAME
        if config.PI_PASSWORD:
            h["x-pi-password"] = config.PI_PASSWORD
            h["x-device-password"] = config.PI_PASSWORD
        return h

    def _request(self, path: str, method: str = "GET",
                 body: Any = None, query: dict | None = None,
                 auth: bool = True, extra_headers: dict | None = None) -> Any:
        qs = ""
        if query:
            q = {k: str(v) for k, v in query.items() if v is not None and str(v) != ""}
            if q:
                qs = "?" + urllib.parse.urlencode(q)
        url = f"{self.base}{path}{qs}"
        headers: dict[str, str] = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if extra_headers:
            headers.update(extra_headers)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                if not raw:
                    return None
                parsed = json.loads(raw)
                if isinstance(parsed, dict) and "data" in parsed:
                    return parsed["data"]
                if isinstance(parsed, dict) and "error" in parsed:
                    msg = parsed["error"].get("message", "request failed")
                    raise ApiError(resp.status, str(msg))
                return parsed
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="ignore") if e.fp else ""
            try:
                parsed = json.loads(body_text) if body_text else {}
                msg = parsed.get("error", {}).get("message") if isinstance(parsed, dict) else None
                raise ApiError(e.code, str(msg or f"HTTP {e.code}"))
            except ApiError:
                raise
            except Exception:
                raise ApiError(e.code, body_text[:400] or f"HTTP {e.code}")
        except urllib.error.URLError as e:
            raise ApiError(0, str(e.reason) if hasattr(e, "reason") else str(e))

    def get_sessions(self, status: str | None = None) -> list[dict]:
        q: dict = {}
        if status:
            q["status"] = status
        try:
            data = self._request("/sessions", query=q or None, auth=False)
            return data if isinstance(data, list) else []
        except ApiError:
            return []

    def get_session(self, sid: str) -> Optional[dict]:
        try:
            data = self._request(f"/sessions/{urllib.parse.quote(sid)}", auth=False)
            return data if isinstance(data, dict) else None
        except ApiError:
            return None

    def get_classrooms(self) -> list[dict]:
        try:
            data = self._request("/classrooms", auth=False)
            return data if isinstance(data, list) else []
        except ApiError:
            return []

    def get_devices(self) -> list[dict]:
        try:
            data = self._request("/devices", auth=False)
            return data if isinstance(data, list) else []
        except ApiError:
            return []

    def get_courses(self) -> list[dict]:
        try:
            data = self._request("/courses", auth=False)
            return data if isinstance(data, list) else []
        except ApiError:
            return []

    def get_materials(self, course_id: str | None = None) -> list[dict]:
        try:
            q = {"courseId": course_id} if course_id else None
            data = self._request("/materials", query=q, auth=False)
            return data if isinstance(data, list) else []
        except ApiError:
            return []

    def get_pi_jitsi_token(self, session_id: str, device_id: str) -> Optional[dict]:
        # Non-moderator JaaS token for the TV. JaaS shows an 8x8 login prompt to
        # anonymous joiners, so the Pi authenticates with its device credentials.
        try:
            return self._request(
                f"/sessions/{urllib.parse.quote(session_id)}/pi-jitsi-token",
                auth=False,
                extra_headers={**self._pi_headers(), "x-device-id": device_id},
            )
        except ApiError:
            return None

    def post_telemetry(self, device_id: str, payload: dict) -> bool:
        # Pi authenticates with x-pi-username / x-pi-password when the device
        # was registered with piUsername/piPassword in Admin → Devices.
        try:
            self._request(f"/devices/{urllib.parse.quote(device_id)}/telemetry",
                          method="POST", body=payload, auth=False,
                          extra_headers=self._pi_headers())
            return True
        except ApiError:
            return False

    def health(self) -> bool:
        try:
            self._request("/sessions", query={"status": "live"}, auth=False)
            return True
        except ApiError as e:
            return e.status != 0
        except Exception:
            return False
