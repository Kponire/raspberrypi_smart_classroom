"""
Smart Classroom — Raspberry Pi TV Interface
Fully automated Tkinter kiosk for the classroom TV.

- No student interaction required: polls the backend and switches
  between IDLE and LIVE automatically.
- Shows Live Classroom on the big screen: Jitsi room + course info.
- USB camera + mic are reported via device telemetry (if configured).
- Optionally auto-opens Jitsi in Chromium kiosk when a lecture goes live.

Run on the Pi:  python3 main.py
Dev on Windows: py -3 main.py
"""
from __future__ import annotations

import subprocess
import sys
import time
import threading
import urllib.parse
from datetime import datetime, timezone
from typing import Optional

try:
    import tkinter as tk
    from tkinter import font as tkfont
except ImportError as e:
    print("tkinter not available:", e)
    sys.exit(1)

import config
from api_client import ApiClient


# ── design tokens (mirrors Frontend/src/styles/tokens.css) ──
DEEP   = "#03045e"
FRENCH = "#023e8a"
BRIGHT = "#0077b6"
TEAL   = "#00b4d8"
FROST  = "#90e0ef"
FROST2 = "#ade8f4"
CYAN   = "#caf0f8"
CANVAS = "#f1f7fb"
SURFACE= "#ffffff"
MUTED  = "#4d6577"
SUBTLE = "#6f8698"
BORDER = "#b9d5e6"
DANGER = "#b3261e"
SUCCESS= "#1a7f4b"

def _jitsi_base() -> str:
    if config.JITSI_HOST:
        return config.JITSI_HOST.rstrip("/")
    if config.JAAS_APP_ID:
        return f"https://{config.JITSI_DOMAIN or '8x8.vc'}"
    return "https://meet.jit.si"


def jitsi_url(room: str, jwt: Optional[str] = None,
              display_name: str = "Classroom TV") -> str:
    app_id = config.JAAS_APP_ID
    path = (f"{app_id}/{urllib.parse.quote(room)}" if app_id
            else urllib.parse.quote(room))
    # Jitsi JSON-parses hash values, so string values must be quoted.
    q = urllib.parse.urlencode({
        "config.prejoinPageEnabled": "false",
        "config.disableDeepLinking": "true",
        "userInfo.displayName": f'"{display_name}"',
    })
    query = f"?jwt={urllib.parse.quote(jwt, safe='')}" if jwt else ""
    return f"{_jitsi_base()}/{path}{query}#{q}"


def fmt_clock(dt: Optional[datetime] = None) -> str:
    d = dt or datetime.now()
    return d.strftime("%I:%M %p").lstrip("0")

def fmt_date(dt: Optional[datetime] = None) -> str:
    d = dt or datetime.now()
    return d.strftime("%a, %d %b %Y")

def fmt_duration(sec: int) -> str:
    sec = max(0, int(sec))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def parse_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        # backend sends ISO; may end with Z
        s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None


# ── telemetry helpers (best-effort, no hard deps) ──
def collect_telemetry() -> dict:
    payload: dict = {}
    try:
        import psutil  # type: ignore
        payload["cpuPercent"] = int(psutil.cpu_percent(interval=None))
        payload["memoryPercent"] = int(psutil.virtual_memory().percent)
        try:
            temps = psutil.sensors_temperatures()  # type: ignore
            if temps:
                vals = [v.current for vs in temps.values() for v in vs if hasattr(v, "current")]
                if vals:
                    payload["temperatureC"] = int(max(vals))
        except Exception:
            pass
        du = psutil.disk_usage("/")
        payload["storageUsedGb"] = round(du.used / (1024**3), 2)
        payload["storageTotalGb"] = round(du.total / (1024**3), 2)
        payload["uptimeHours"] = int(time.monotonic() // 3600)
    except ImportError:
        # no psutil on dev machine — heartbeat only
        payload["uptimeHours"] = int(time.monotonic() // 3600)
    except Exception:
        pass
    return payload


class PiApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Smart Classroom")
        self.configure(bg=CANVAS)
        try:
            self.attributes("-fullscreen", bool(config.FULLSCREEN))
        except Exception:
            pass
        self.bind("<Escape>", lambda _e: self.attributes("-fullscreen", False))
        self.bind("<F11>", lambda _e: self.attributes("-fullscreen", not bool(self.attributes("-fullscreen"))))
        # Make window large on desktop dev
        if not bool(config.FULLSCREEN):
            self.geometry("1280x720")

        self.api = ApiClient()

        # state
        self.classroom: Optional[dict] = None
        self.device: Optional[dict] = None
        self.course: Optional[dict] = None
        self.session: Optional[dict] = None
        self.materials: list[dict] = []
        self.live_started_at: Optional[float] = None
        self._jitsi_proc: Optional[subprocess.Popen] = None
        self._last_jitsi_room: Optional[str] = None

        self._build_ui()
        self._tick_clock()
        self.after(800, self._poll)
        self.after(int(config.POLL_TELEMETRY_S * 1000), self._push_telemetry)
        # close jitsi browser on exit
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI ──
    def _build_ui(self):
        # ── top bar ──
        top = tk.Frame(self, bg=DEEP, height=64)
        top.pack(fill="x", side="top")
        top.pack_propagate(False)

        left = tk.Frame(top, bg=DEEP)
        left.pack(side="left", fill="y", padx=(18, 8), pady=8)
        tk.Label(left, text="SMART CLASSROOM", bg=DEEP, fg=FROST2,
                 font=("Segoe UI", 10, "bold"), anchor="w").pack(anchor="w")
        self.lbl_classroom = tk.Label(left, text="Loading classroom…", bg=DEEP, fg="white",
                                      font=("Segoe UI", 13, "bold"), anchor="w")
        self.lbl_classroom.pack(anchor="w")

        center = tk.Frame(top, bg=DEEP)
        center.pack(side="left", expand=True, fill="both")
        self.pill = tk.Label(center, text="●  OFF AIR", bg="#1a1a2e", fg="#ffb3b3",
                             font=("Segoe UI", 9, "bold"), padx=12, pady=4)
        self.pill.pack(side="left", padx=12, pady=14)
        # live timer
        self.lbl_elapsed = tk.Label(center, text="", bg=DEEP, fg=FROST,
                                    font=("Consolas", 11, "bold"))
        self.lbl_elapsed.pack(side="left", padx=6)

        right = tk.Frame(top, bg=DEEP)
        right.pack(side="right", padx=18, pady=8)
        self.lbl_clock = tk.Label(right, text="--:--", bg=DEEP, fg=FROST2,
                                  font=("Consolas", 18, "bold"), anchor="e")
        self.lbl_clock.pack(anchor="e")
        self.lbl_date = tk.Label(right, text="", bg=DEEP, fg=FROST,
                                 font=("Segoe UI", 9), anchor="e")
        self.lbl_date.pack(anchor="e")
        self.lbl_conn = tk.Label(right, text="", bg=DEEP, fg=FROST,
                                 font=("Segoe UI", 8), anchor="e")
        self.lbl_conn.pack(anchor="e")

        # ── main body ──
        body = tk.Frame(self, bg=CANVAS)
        body.pack(fill="both", expand=True, padx=16, pady=14)

        # Stage (left)
        self.stage = tk.Frame(body, bg=DEEP, highlightthickness=0, bd=0)
        self.stage.pack(side="left", fill="both", expand=True, padx=(0, 12))

        # stage header bar
        bar = tk.Frame(self.stage, bg="white", height=56)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)
        self.lbl_stage_title = tk.Label(bar, text="Waiting for lecture", bg="white", fg=DEEP,
                                        font=("Segoe UI", 14, "bold"), anchor="w")
        self.lbl_stage_title.pack(side="left", padx=14, pady=8)
        self.lbl_stage_sub = tk.Label(bar, text="", bg="white", fg=MUTED,
                                      font=("Segoe UI", 10), anchor="w")
        self.lbl_stage_sub.pack(side="left", padx=6, pady=10)
        # REC badge (hidden until recording)
        self.rec_badge = tk.Label(bar, text="  ● REC  ", bg=DANGER, fg="white",
                                  font=("Segoe UI", 9, "bold"))
        # not packed until recording

        # video / placeholder area
        self.frame = tk.Frame(self.stage, bg="#06072e")
        self.frame.pack(fill="both", expand=True)

        # placeholder widgets (centered)
        self.ph_icon = tk.Label(self.frame, text="◫", bg="#06072e", fg=TEAL,
                                font=("Segoe UI", 56))
        self.ph_icon.place(relx=0.5, rely=0.38, anchor="center")

        self.ph_title = tk.Label(self.frame, text="No lecture in progress",
                                 bg="#06072e", fg="white",
                                 font=("Segoe UI", 18, "bold"))
        self.ph_title.place(relx=0.5, rely=0.52, anchor="center")

        self.ph_text = tk.Label(self.frame,
            text="Your lecturer will start the session — this screen joins automatically.\nPlease stay seated. Camera & microphone are ready.",
            bg="#06072e", fg=FROST, font=("Segoe UI", 11), justify="center")
        self.ph_text.place(relx=0.5, rely=0.62, anchor="center")

        self.lbl_jitsi = tk.Label(self.frame, text="", bg="#06072e", fg=FROST2,
                                  font=("Consolas", 9), justify="center", wraplength=640)
        self.lbl_jitsi.place(relx=0.5, rely=0.78, anchor="center")

        # pushed material banner (bottom of stage)
        self.material_banner = tk.Frame(self.stage, bg=FRENCH, height=44)
        self.lbl_material = tk.Label(self.material_banner,
            text="", bg=FRENCH, fg="white", font=("Segoe UI", 11, "bold"), anchor="w")
        self.lbl_material.pack(side="left", padx=14, pady=8, fill="x", expand=True)
        self.lbl_material_sub = tk.Label(self.material_banner, text="", bg=FRENCH, fg=CYAN,
                                         font=("Segoe UI", 9), anchor="w")
        self.lbl_material_sub.pack(side="left", padx=8)

        # Rail (right) — fixed width
        rail = tk.Frame(body, bg=CANVAS, width=340)
        rail.pack(side="right", fill="y")
        rail.pack_propagate(False)

        # helper to make rail cards
        def card(title: str):
            c = tk.Frame(rail, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
            c.pack(fill="x", pady=(0, 10))
            h = tk.Frame(c, bg=SURFACE)
            h.pack(fill="x", padx=12, pady=(10, 6))
            tk.Label(h, text=title.upper(), bg=SURFACE, fg=SUBTLE,
                     font=("Segoe UI", 8, "bold")).pack(side="left")
            body_f = tk.Frame(c, bg=SURFACE)
            body_f.pack(fill="x", padx=12, pady=(0, 10))
            return body_f

        # Device status
        dev_body = card("Device status")
        self.dev_rows: dict[str, tk.Label] = {}
        for label in ("Camera", "Microphone", "Speaker", "Pi heartbeat"):
            row = tk.Frame(dev_body, bg=SURFACE)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label, bg=SURFACE, fg=DEEP,
                     font=("Segoe UI", 10), anchor="w").pack(side="left")
            pill = tk.Label(row, text="—", bg=CANVAS, fg=SUBTLE,
                            font=("Segoe UI", 8, "bold"), padx=8, pady=2)
            pill.pack(side="right")
            self.dev_rows[label] = pill
        self.lbl_device_id = tk.Label(dev_body, text="", bg=SURFACE, fg=SUBTLE,
                                      font=("Consolas", 8), anchor="w")
        self.lbl_device_id.pack(fill="x", pady=(6, 0))

        # Smart TV
        tv_body = card("Smart TV")
        r1 = tk.Frame(tv_body, bg=SURFACE); r1.pack(fill="x", pady=2)
        tk.Label(r1, text="Display", bg=SURFACE, fg=DEEP, font=("Segoe UI", 10)).pack(side="left")
        self.lbl_tv = tk.Label(r1, text="Not paired", bg=SURFACE, fg=SUBTLE, font=("Segoe UI", 9))
        self.lbl_tv.pack(side="right")
        r2 = tk.Frame(tv_body, bg=SURFACE); r2.pack(fill="x", pady=2)
        tk.Label(r2, text="Attendees", bg=SURFACE, fg=DEEP, font=("Segoe UI", 10)).pack(side="left")
        self.lbl_attendees = tk.Label(r2, text="0 connected", bg=SURFACE, fg=SUBTLE, font=("Segoe UI", 9))
        self.lbl_attendees.pack(side="right")

        # Session facts
        facts_body = card("Session facts")
        self.fact_labels: dict[str, tk.Label] = {}
        for k in ("Course", "Classroom", "Starts", "Ends", "Co-lecturers"):
            row = tk.Frame(facts_body, bg=SURFACE); row.pack(fill="x", pady=2)
            tk.Label(row, text=k, bg=SURFACE, fg=SUBTLE, font=("Segoe UI", 9)).pack(side="left")
            v = tk.Label(row, text="—", bg=SURFACE, fg=DEEP, font=("Segoe UI", 10, "bold"))
            v.pack(side="right")
            self.fact_labels[k] = v

        # footer hint (no interaction needed)
        tk.Label(rail, text="Fully automated — no action needed.",
                 bg=CANVAS, fg=SUBTLE, font=("Segoe UI", 8)).pack(pady=(2, 0))
        tk.Label(rail, text="Camera & mic are on only during live lectures.",
                 bg=CANVAS, fg=SUBTLE, font=("Segoe UI", 8)).pack()

    # ── clock ──
    def _tick_clock(self):
        self.lbl_clock.config(text=fmt_clock())
        self.lbl_date.config(text=fmt_date())
        # elapsed when live
        if self.session and self.session.get("status") == "live" and self.live_started_at:
            self.lbl_elapsed.config(text=fmt_duration(time.time() - self.live_started_at))
        else:
            self.lbl_elapsed.config(text="")
        self.after(1000, self._tick_clock)

    # ── polling ──
    def _poll(self):
        def work():
            classroom, device, course, session, materials = self._resolve_context()
            self.after(0, lambda: self._apply_context(classroom, device, course, session, materials))
        threading.Thread(target=work, daemon=True).start()
        self.after(int(config.POLL_SESSION_S * 1000), self._poll)

    def _resolve_context(self):
        # fetch in parallel-ish (sequential but short; urllib is fast on LAN)
        sessions = self.api.get_sessions()
        classrooms = self.api.get_classrooms()
        devices = self.api.get_devices()
        courses = self.api.get_courses()

        # pick classroom
        classroom = None
        if config.CLASSROOM_ID:
            classroom = next((c for c in classrooms if c.get("id") == config.CLASSROOM_ID), None)
        if not classroom and classrooms:
            classroom = classrooms[0]

        # pick device for that classroom
        device = None
        if config.DEVICE_ID:
            device = next((d for d in devices if d.get("id") == config.DEVICE_ID), None)
        if not device and classroom and classroom.get("deviceId"):
            device = next((d for d in devices if d.get("id") == classroom["deviceId"]), None)
        if not device and devices:
            device = devices[0]

        # pick session: prefer live for this classroom, else scheduled
        live = [s for s in sessions if s.get("status") == "live"]
        # filter to this classroom if we have one
        if classroom:
            prefer = [s for s in live if s.get("classroomId") == classroom["id"]]
            if prefer:
                live = prefer
        session = live[0] if live else None
        if not session:
            # show next scheduled as context (so stage title still says course)
            sched = [s for s in sessions if s.get("status") == "scheduled"]
            if classroom:
                sched = [s for s in sched if s.get("classroomId") == classroom["id"]] or sched
            session = sched[0] if sched else (sessions[0] if sessions else None)
            # if we are showing a non-live as idle, treat as no active session
            if session and session.get("status") != "live":
                # keep it for course lookup but mark idle rendering
                pass

        course = None
        if session and session.get("courseId"):
            course = next((c for c in courses if c.get("id") == session["courseId"]), None)
        if not course and courses:
            # fallback to first course of that classroom
            if classroom:
                course = next((c for c in courses if c.get("classroomId") == classroom["id"]), None)
            course = course or courses[0]

        # materials for that course
        mats: list[dict] = []
        if course and course.get("id"):
            mats = self.api.get_materials(course["id"])
        # prioritize pushed ones on top
        mats = sorted(mats, key=lambda m: (not bool(m.get("pushedToTv")), str(m.get("uploadedAt") or "" )), )

        return classroom, device, course, session, mats

    def _apply_context(self, classroom, device, course, session, materials):
        self.classroom = classroom
        self.device = device
        self.course = course
        self.materials = materials or []

        # decide if we are truly live
        is_live = bool(session and session.get("status") == "live")
        was_live = bool(self.session and self.session.get("status") == "live")
        self.session = session

        # header classroom
        if classroom:
            self.lbl_classroom.config(text=f"{classroom.get('name','Classroom')}  ·  {classroom.get('building','')} {classroom.get('room','')}")
        elif course:
            self.lbl_classroom.config(text=course.get("title","Smart Classroom"))
        else:
            self.lbl_classroom.config(text="Smart Classroom — TV")

        # pill
        if is_live:
            self.pill.config(text="  ●  ON AIR  ", bg=DANGER, fg="white")
            # start timer base
            starts = parse_dt(session.get("startsAt") or "")
            if starts:
                # use server startsAt as elapsed base
                try:
                    self.live_started_at = starts.replace(tzinfo=timezone.utc).timestamp() if starts.tzinfo else starts.timestamp()
                    # if that is in the future (clock skew), clamp to now
                    if self.live_started_at > time.time() + 2:
                        self.live_started_at = time.time()
                except Exception:
                    self.live_started_at = time.time()
            else:
                self.live_started_at = time.time()
            # auto-open Jitsi once per room
            room = session.get("jitsiRoom")
            if room and room != self._last_jitsi_room and config.AUTO_OPEN_JITSI:
                self._last_jitsi_room = str(room)
                self._open_jitsi(str(room))
        else:
            self.pill.config(text="  ●  OFF AIR  ", bg="#1a1a2e", fg="#ffb3b3")
            self.live_started_at = None
            if was_live:
                # lecture ended — close kiosk browser
                self._close_jitsi()
                self._last_jitsi_room = None

        # stage header
        if is_live:
            title = course.get("title") if course else (session.get("topic") or "Live lecture")
            self.lbl_stage_title.config(text=title)
            code = course.get("code") if course else ""
            room = session.get("jitsiRoom") or "room pending"
            self.lbl_stage_sub.config(text=f"{code}  ·  {room}" if code else room)
            # REC badge if recordingId present
            if session.get("recordingId"):
                self.rec_badge.pack(side="right", padx=10, pady=10)
            else:
                self.rec_badge.pack_forget()
        else:
            if session and session.get("topic"):
                self.lbl_stage_title.config(text=session.get("topic"))
                starts = session.get("startsAt")
                try:
                    dt = parse_dt(starts) if starts else None
                    sub = dt.strftime("%a %d %b · %I:%M %p") if dt else ""
                except Exception:
                    sub = ""
                self.lbl_stage_sub.config(text=sub)
            else:
                self.lbl_stage_title.config(text="Waiting for lecture")
                self.lbl_stage_sub.config(text="")
            self.rec_badge.pack_forget()

        # placeholder vs live copy
        if is_live:
            self.ph_icon.config(text="⬢")
            self.ph_title.config(text="Lecture is live")
            self.ph_text.config(text="You are watching on the classroom TV.\nPlease stay seated — attendance is automatic.")
            jurl = jitsi_url(session.get("jitsiRoom") or "") if session.get("jitsiRoom") else ""
            if config.AUTO_OPEN_JITSI and session.get("jitsiRoom"):
                self.lbl_jitsi.config(text=f"Live video opened in kiosk browser\n{jurl}")
            elif jurl:
                self.lbl_jitsi.config(text=jurl)
            else:
                self.lbl_jitsi.config(text="Room provisioning…")
        else:
            self.ph_icon.config(text="◫")
            if session and session.get("status") == "scheduled":
                self.ph_title.config(text="Session is not live yet")
                self.ph_text.config(text="Your lecturer will press Start — this screen joins automatically.\nNo action needed from students.")
            else:
                self.ph_title.config(text="No lecture in progress")
                self.ph_text.config(text="Your lecturer will start the session — this screen joins automatically.\nPlease stay seated. Camera & microphone are ready.")
            self.lbl_jitsi.config(text="")

        # material banner — show most recent pushed material
        pushed = next((m for m in self.materials if m.get("pushedToTv")), None)
        if pushed:
            self.material_banner.pack(fill="x", side="bottom")
            kind = str(pushed.get("kind","")).upper() or "MATERIAL"
            self.lbl_material.config(text=f"▸  {pushed.get('title','Material')}")
            self.lbl_material_sub.config(text=f"{kind}  ·  Week {pushed.get('week','—')}  ·  {pushed.get('topic','')}")
        else:
            self.material_banner.pack_forget()

        # rail — device
        cam_ok = (device or {}).get("cameraHealth") == "ok"
        mic_ok = (device or {}).get("micHealth") == "ok"
        spk_ok = (device or {}).get("speakerHealth") == "ok"
        online = (device or {}).get("status") == "online"
        def pill(lbl: str, ok: bool):
            w = self.dev_rows[lbl]
            w.config(text="  OK  " if ok else " FAULT ", bg="#e7f5ed" if ok else "#fdeceb",
                     fg=SUCCESS if ok else DANGER)
        pill("Camera", cam_ok)
        pill("Microphone", mic_ok)
        pill("Speaker", spk_ok)
        pill("Pi heartbeat", online)
        did = (device or {}).get("id") or (classroom or {}).get("deviceId") or "—"
        fw  = (device or {}).get("firmware") or ""
        self.lbl_device_id.config(text=f"Device {did}  {('·  v'+fw) if fw else ''}")

        # TV
        tv_paired = bool((classroom or {}).get("tvPaired") or device)
        self.lbl_tv.config(text="Paired — ready for slides" if tv_paired else "Not paired",
                           fg=SUCCESS if tv_paired else SUBTLE)
        attendees = session.get("attendees") if session else 0
        try:
            attendees = int(attendees or 0)
        except Exception:
            attendees = 0
        self.lbl_attendees.config(text=f"{attendees} connected")

        # facts
        def set_fact(k: str, v: str):
            self.fact_labels[k].config(text=v)
        set_fact("Course", (course or {}).get("code") or "—")
        set_fact("Classroom", (classroom or {}).get("name") or (session or {}).get("classroomId") or "—")
        def clock_of(key: str):
            s = (session or {}).get(key) or ""
            dt = parse_dt(s) if s else None
            return dt.strftime("%I:%M %p").lstrip("0") if dt else "—"
        set_fact("Starts", clock_of("startsAt"))
        set_fact("Ends", clock_of("endsAt"))
        co = session.get("coLecturerIds") if session else None
        set_fact("Co-lecturers", str(len(co)) if isinstance(co, list) and co else "None")

        # connection dot
        ok = self.api.health()
        self.lbl_conn.config(text="●  Backend online" if ok else "○  Reconnecting…",
                             fg=SUCCESS if ok else "#ffb3b3")

    # ── jitsi kiosk ──
    def _open_jitsi(self, room: str):
        # already open this room
        if self._jitsi_proc and self._jitsi_proc.poll() is None:
            return
        # minting the device token is a network call — keep it off the Tk thread
        threading.Thread(target=self._launch_jitsi, args=(room,), daemon=True).start()

    def _device_id(self) -> str:
        return str(config.DEVICE_ID or (self.device or {}).get("id")
                   or (self.classroom or {}).get("deviceId") or "")

    def _launch_jitsi(self, room: str):
        jwt = None
        if config.JAAS_APP_ID:
            sid = str((self.session or {}).get("id") or "")
            did = self._device_id()
            if sid and did:
                res = self.api.get_pi_jitsi_token(sid, did) or {}
                jwt = res.get("token")
            if not jwt:
                print("jitsi: no device token from backend — "
                      "the TV may be asked to log in to 8x8")
        url = jitsi_url(room, jwt)
        cmd = config.JITSI_BROWSER_CMD.strip()
        try:
            if cmd:
                # split naively — allow quoted args
                import shlex
                parts = shlex.split(cmd) + [url]
                self._jitsi_proc = subprocess.Popen(parts)
            else:
                # try chromium then chrome then xdg-open
                for exe in ("chromium-browser", "chromium", "google-chrome", "chrome"):
                    try:
                        self._jitsi_proc = subprocess.Popen(
                            [exe, "--kiosk", "--no-sandbox", "--disable-dev-shm-usage",
                             "--noerrdialogs", "--disable-infobars",
                             "--autoplay-policy=no-user-gesture-required", url]
                        )
                        break
                    except FileNotFoundError:
                        continue
                else:
                    import webbrowser
                    webbrowser.open(url)
        except Exception as e:
            print("open jitsi failed:", e)

    def _close_jitsi(self):
        if self._jitsi_proc and self._jitsi_proc.poll() is None:
            try:
                self._jitsi_proc.terminate()
                try:
                    self._jitsi_proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._jitsi_proc.kill()
            except Exception:
                pass
        self._jitsi_proc = None

    def _push_telemetry(self):
        # fire and forget; re-schedule
        def work():
            # resolve device id if not pinned
            did = config.DEVICE_ID or (self.device or {}).get("id") or (self.classroom or {}).get("deviceId") or ""
            if not did:
                return
            payload = collect_telemetry()
            if payload:
                self.api.post_telemetry(str(did), payload)
        threading.Thread(target=work, daemon=True).start()
        self.after(int(config.POLL_TELEMETRY_S * 1000), self._push_telemetry)

    def _on_close(self):
        self._close_jitsi()
        self.destroy()


if __name__ == "__main__":
    # Windows HiDPI
    try:
        from ctypes import windll  # type: ignore
        windll.shcore.SetProcessDpiAwareness(1)  # type: ignore
    except Exception:
        pass
    app = PiApp()
    app.mainloop()
