from __future__ import annotations
import json
import urllib.request
import urllib.error
import urllib.parse
import time
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

    # ---- auth ----
    def login(self) -> bool:
        if not config.PI_EMAIL or not config.PI_PASSWORD:
            return False
        try:
            data = self._request("/auth/login", method="POST",
                                 body={"email": config.PI_EMAIL.strip().lower(),
                                       "password": config.PI_PASSWORD}, auth=False)
            tok = data.get("token") if isinstance(data, dict) else None
            if tok:
                self.token = str(tok)
                return True
        except Exception:
            pass
        return False

    # ---- low level ----
    def _request(self, path: str, method: str = "GET",
                 body: Any = None, query: dict | None = None, auth: bool = True) -> Any:
        qs = ""
        if query:
            q = {k: str(v) for k, v in query.items() if v is not None and str(v) != ""}
            if q:
                qs = "?" + urllib.parse.urlencode(q)
        url = f"{self.base}{path}{qs}"
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
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

    # ---- high level (mirrors Frontend lib/api.ts) ----
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

    def post_telemetry(self, device_id: str, payload: dict) -> bool:
        try:
            self._request(f"/devices/{urllib.parse.quote(device_id)}/telemetry",
                          method="POST", body=payload, auth=bool(self.token))
            return True
        except ApiError:
            # retry once with login
            if self.token is None and config.PI_EMAIL:
                if self.login():
                    try:
                        self._request(f"/devices/{urllib.parse.quote(device_id)}/telemetry",
                                      method="POST", body=payload, auth=True)
                        return True
                    except ApiError:
                        return False
            return False

    def health(self) -> bool:
        try:
            # lightweight check — sessions endpoint is public
            self._request("/sessions", query={"status": "live"}, auth=False)
            return True
        except ApiError as e:
            return e.status != 0
        except Exception:
            return False
