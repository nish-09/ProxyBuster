# Proxy Busters — Workflow Guide

A short, practical guide to what this project is and how to actually use it day-to-day.
For deep architecture/API/schema details, see [`README.md`](./README.md).

## What it is

A college attendance system with QR-based check-in that's hard to proxy/cheat:
- QR code **rotates every 10 seconds** and is single-use (screenshots go stale fast).
- All rules (enrollment, cooldown, duplicates, session expiry) are enforced **server-side** —
  the frontend never decides who gets marked present.
- Three roles: **Admin** (sets up the academic structure), **Professor** (runs attendance),
  **Student** (scans to check in).

## Stack at a glance

```
frontend/   Next.js (App Router, TS) — talks to the backend over REST + one WebSocket per live session
backend/    FastAPI + SQLAlchemy + PostgreSQL — all business logic and validation lives here
design/     Stitch-exported screens — the visual source of truth for the UI
```

## Running it locally

```bash
# Backend
cd backend
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
copy ..\.env.example ..\.env      # fill in DATABASE_URL + secrets
.venv\Scripts\alembic upgrade head
.venv\Scripts\python seed.py      # optional demo data
.venv\Scripts\uvicorn app.main:app --reload

# Frontend (new terminal)
cd frontend
npm install
copy .env.local.example .env.local   # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
```

Or `docker compose up --build` to bring up Postgres + backend + frontend together.

Seeded logins (password `Password123!`): professor `meera.nair@college.edu`,
student `arjun.mehta@college.edu`.

## End-to-end usage flow

### 1. Admin — set up the academic structure (once)

Admin dashboard → in order:

1. **Professors** — add each professor (name, email, department).
2. **Subjects** — add each course (code, name, credits).
3. **Divisions** — link a subject + professor + division name (e.g. "CS301 • Div A").
4. **Students** — add each student (roll number, program, semester).
5. **Enrollments** — enroll students into a division (bulk-enroll supported).
6. **Lectures** *(optional)* — schedule lectures in advance if you want professors to start
   attendance against a fixed timetable. Not required — see the ad-hoc option below.

### 2. Professor — run attendance

Professor dashboard → **Start Attendance**:

- **Scheduled Lecture** tab — pick one of today's admin-scheduled lectures and start it.
- **Ad-hoc Session** tab — no lecture needed: pick a subject/division you teach + a
  duration (15–240 min), and a session starts immediately. Use this for pop quizzes,
  makeup classes, or whenever nothing was pre-scheduled.

Either way you land on the **live session screen**: a rotating QR code, a live present/total
count, and a check-in feed, all updated over WebSocket (falls back to polling if the socket
drops). From there you can:
- **Manual Entry** — mark a student present/late/absent by hand (reason required, fully
  audited).
- **Stop Session** — closes it; scans against it are rejected after that.
- A session also auto-expires once its time window passes (scheduled `scheduled_end`, or
  `now + duration` for ad-hoc) — no need to remember to stop it.

Afterwards, **Attendance Sheet** shows every lecture/session as its own column (even multiple
sessions on the same day stay separate — they never overwrite each other), with per-student
Present/Absent/Late/Manual marks and CSV export.

### 3. Student — check in

Student dashboard → **Scan Attendance** → point the camera at the professor's QR.

On success you get a dedicated confirmation screen (subject, date, time, status) —
**you stay logged in**, nothing resets. After marking, a short **server-enforced cooldown**
starts (visible as a live countdown); scanning again before it expires is rejected by the
backend regardless of what the client does, and refreshing the page shows the real remaining
time (never resets to zero client-side).

Rejections you might see, all with a specific reason: not enrolled, already marked for this
lecture, session expired/closed, or cooldown active.

## Where the rules actually live (backend)

| Concern | Enforced in |
|---|---|
| QR rotation, signing, replay/expiry | `backend/app/services/attendance_service.py` |
| Enrollment / duplicate / cooldown checks | `attendance_service.scan()` |
| Session lifecycle (active → expired/closed) | `attendance_service._close_if_expired`, checked on scan/live/WS rotation |
| Ad-hoc session creation | `attendance_service.create_adhoc_session()` → `POST /attendance/sessions/adhoc` |
| Attendance sheet (per-lecture columns) | `backend/app/services/professor_service.py::attendance_sheet` |
| Post-scan cooldown duration | `settings.scan_cooldown_seconds` (`.env`) |
| Post-logout cooldown duration | `settings.cooldown_minutes` (`.env`) |

If attendance data ever looks wrong, `attendance_records` in Postgres is the single source of
truth — the professor dashboard's live count and the attendance sheet both read from it by
`lecture_id`, nothing is cached or computed only in the frontend.

## Tests

```bash
cd backend
.venv\Scripts\pytest -q
```

```bash
cd frontend
npm run lint
npm run build
```
