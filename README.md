# Proxy Busters

A college attendance platform built to make proxy attendance — forwarded QR screenshots, shared
accounts, session sharing — meaningfully harder, without resorting to GPS/geofencing or facial
recognition. It combines ordinary attendance management (subjects, divisions, lectures, history,
analytics) with security mechanisms enforced entirely server-side: a QR code that rotates every
10 seconds and is signed with a short-lived HMAC token, one active session per account, a 60-minute
server-side cooldown after a voluntary logout, an audited manual-override path for professors, and
a rule-based (with an optional ML fallback) anomaly-scoring system that flags patterns for human
review rather than making accusations.

The UI is a faithful implementation of an existing Google Stitch design (`design/`) — the visual
design was not altered; this build wires it to a real backend and database.

## Architecture

```
Next.js (App Router, TS)  ──REST──▶  FastAPI  ──SQLAlchemy──▶  PostgreSQL
        │                              │
        └──────────WebSocket──────────┘   (live QR rotation + live attendance feed,
                                            one room per attendance session)
```

- **Frontend**: Next.js App Router, client-rendered pages behind a JWT-aware auth context; camera
  QR scanning (`html5-qrcode`) and QR rendering (`qrcode`) happen entirely in the browser.
- **Backend**: FastAPI, SQLAlchemy 2.0 models, Alembic migrations, Pydantic v2 schemas, JWT auth
  (`python-jose`), bcrypt hashing (`passlib`), `slowapi` for rate limiting, `scikit-learn` for the
  optional ML anomaly path.
- **Realtime**: a single in-process WebSocket connection manager (`app/services/realtime.py`)
  keyed by attendance-session id, plus an `asyncio` background task per active session that mints
  and broadcasts a new signed QR token every `QR_TOKEN_TTL_SECONDS` (default 10s).
- **Database**: PostgreSQL (developed against Supabase Postgres).

## Tech stack

**Backend** (`backend/requirements.txt`): FastAPI 0.115, Uvicorn 0.32, SQLAlchemy 2.0.36, Alembic
1.14, psycopg2-binary 2.9, Pydantic 2.10 / pydantic-settings 2.6, python-jose 3.3, passlib+bcrypt,
slowapi 0.1.9, scikit-learn 1.5.2 / numpy 2.1.3, pytest 8.3 / pytest-asyncio / httpx for testing.

**Frontend** (`frontend/package.json`): Next.js 16.3.4 (App Router, Turbopack), React 19.2,
Tailwind CSS v4 (token-based `@theme` — no `tailwind.config.ts` in v4), `qrcode` 1.5, `html5-qrcode`
2.3.8, TypeScript 5, ESLint 9.

## Folder structure

```
backend/app/
  api/          auth.py, attendance.py, ws.py, students.py, professor.py
  core/         config.py, db.py, security.py, deps.py, time.py, types.py
  models/       user.py, academic.py, attendance.py, security.py
  schemas/      auth.py, attendance.py, student.py, professor.py
  services/     auth_service.py, cooldown_service.py, attendance_service.py,
                realtime.py, analytics_service.py, professor_service.py,
                anomaly_service.py
  ml/           isolation_forest.py
backend/alembic/         migration environment + versions/
backend/tests/           pytest suite (see Testing)
backend/seed.py          development seed data

frontend/app/
  student/      dashboard, attendance, scan, cooldown
  professor/    dashboard, session/[id], attendance-sheet, students, students/[id], cooldowns
  login/, register/
frontend/components/
  layout/       SideNavBar, TopNavBar/DesktopTopBar, BottomMobileNav
  ui/           StatusBadge, Card/GlassCard
  student/, professor/   screen-specific modals/widgets
frontend/lib/    api.ts (typed client), auth-context.tsx

design/          Stitch-exported screens (code.html + screen.png) — the UI source of truth
```

## Database schema

| Table | Purpose |
|---|---|
| `users` | Account identity, hashed password, role (student/professor) |
| `student_profiles` | Roll number, program, semester — 1:1 with a student `User` |
| `professor_profiles` | Department — 1:1 with a professor `User` |
| `subjects` | Course catalog entries (code, name, credits) |
| `class_divisions` | A subject taught to one division by one professor |
| `enrollments` | Student ↔ class-division membership |
| `lectures` | Scheduled class meetings for a division |
| `attendance_sessions` | One "attendance window" opened by a professor for a lecture |
| `attendance_tokens` | Each 10-second rotating signed QR token, one-time consumable |
| `attendance_records` | The actual present/late/manual mark for a student+lecture (unique per pair) |
| `manual_attendance` | Audit trail for every professor manual override |
| `device_sessions` | Login/logout/device tracking, enforces one active session per account |
| `cooldowns` | Active 60-minute post-logout lockouts |
| `security_events` | Concurrent-login, force-logout, and other security-relevant events |
| `anomaly_scores` | Stored rule-based/ML risk scores + human-readable reasons per student |

## Authentication

JWT access tokens (HS256, `python-jose`), bcrypt password hashing (`passlib`). Every token embeds a
`jti` that doubles as the `DeviceSession.session_id`; `app/core/deps.authenticate()` (shared by the
HTTP bearer dependency and the WebSocket handshake) rejects a token whose `DeviceSession` is no
longer `ACTIVE` — this is how "one active session per account" is enforced: logging in again
revokes any prior active session and logs a `concurrent_login` `SecurityEvent`. `require_student`
/ `require_professor` (built on `require_role`) gate every role-specific route; professor endpoints
additionally scope every query to that professor's own `class_divisions` so no professor can read
another's students or sessions.

## Attendance flow

1. Professor picks a lecture and calls `POST /attendance/sessions` → an `AttendanceSession` is
   created and the first `AttendanceToken` is issued immediately.
2. A background `asyncio` task (`realtime.rotate_qr_loop`) mints a new signed token every
   `QR_TOKEN_TTL_SECONDS` (10s) and broadcasts it over `WS /ws/attendance/sessions/{id}`.
3. The frontend renders the token string as a QR code (`qrcode`) and shows a live countdown to the
   next rotation.
4. A student scans it with the device camera (`html5-qrcode`) and the app calls `POST
   /attendance/scan` with the decoded payload.
5. The backend runs the full validation chain (below) and, on success, creates an
   `AttendanceRecord` and broadcasts the check-in to the professor's live view.
6. The professor calls `POST /attendance/sessions/{id}/close` when done; unmarked students are
   simply left with no record (attendance % is computed as enrolled-minus-recorded, not stored).

## Dynamic QR architecture

The QR payload is `base64(session_id.nonce.issued_at.expires_at.signature)`, where `nonce` is a
random 16-byte URL-safe token and `signature = HMAC-SHA256(QR_SIGNING_SECRET, session_id.nonce.issued_at.expires_at)`
— a secret kept separate from `JWT_SECRET`. Verifying a scan recomputes the HMAC and compares it
with `hmac.compare_digest` before ever touching the database, then looks up the `AttendanceToken`
row by `nonce` to check it exists, hasn't expired, and — critically — hasn't already been
`consumed`. A token is marked consumed only once an attendance record is actually created for it,
so a wrong/disallowed scan of a still-valid token doesn't burn it for the real student. Because
each token is valid for only ~10 seconds and single-use, a screenshot or forwarded image of the QR
is worthless to anyone who isn't in the room at that moment.

`POST /attendance/scan` validates, in order: caller is authenticated → caller is a student →
signature is valid → token hasn't expired → token belongs to an `ACTIVE` session → token hasn't
been replayed → student is enrolled in that class division → student has no active cooldown →
student has no existing record for that lecture (also enforced at the DB level via a unique
constraint as a race-condition backstop) → record created.

## Cooldown system

A 60-minute (`COOLDOWN_MINUTES`) cooldown is created **only** by a voluntary `POST /auth/logout`
(`auth_service.logout_user`) — never by token expiry, a crash, a dropped connection, or a server
restart, since none of those code paths touch the `Cooldown` table. While a cooldown row's
`expires_at` is in the future, `cooldown_service.get_active_cooldown` blocks both `POST /auth/login`
(423, with `remaining_seconds` in the body) and `POST /attendance/scan` (423) for that student.
`GET /students/me/cooldown` lets the student poll their own remaining time; `GET
/professor/cooldowns` lets a professor see who on their roster is currently locked out.

## Security model

- **One active session per account**, enforced via `DeviceSession` + `authenticate()` (see
  Authentication above); a new login revokes the old session and logs a `concurrent_login` event.
- **Force logout**: a professor can revoke a specific student's active session
  (`POST /professor/students/{id}/force-logout`) — this does **not** start a cooldown, since
  cooldown is reserved for voluntary logout.
- **WebSocket authorization**: `WS /ws/attendance/sessions/{id}` re-validates the JWT and then
  calls the same `authorize_session_access` used by the REST `GET /sessions/{id}` endpoint before
  accepting the connection, so a student can't subscribe to another class's live feed.
- **Rate limiting**: `slowapi`'s `Limiter` (`app/core/rate_limit.py`) is enforced per client IP on
  the endpoints most worth protecting from brute-force/spam: `POST /auth/login` (10/minute),
  `POST /auth/register` (5/minute), and `POST /attendance/scan` (20/minute). Verified by
  `tests/test_rate_limit.py`.
- **Audit trail**: every manual attendance action creates a `ManualAttendance` row recording the
  professor, reason, previous status, and new status — attendance is never silently rewritten.

## Proxy / anomaly detection

`app/services/anomaly_service.py` implements rule-based scoring (0–100, capped), returning
human-readable reasons, not accusations:

- Frequent device/session changes in the last 30 days (+15)
- Repeated logout/login pattern in the last 7 days (+15)
- Multiple `concurrent_login` security events in the last 30 days (+10 each, capped +30)
- The student's most recent scan timing deviating > 2 standard deviations from their own
  historical scan-timing pattern (+20)
- Participation in a detected synchronized-attendance pair (+25)

**Synchronized-attendance detection** (`find_synchronized_pairs`) clusters each lecture's
`AttendanceRecord`s by `marked_at` (records within 5 seconds of each other), then counts, across
all lectures, how often each pair of students lands in the same cluster; pairs with ≥3 occurrences
are surfaced (≥6 = "high" risk, else "medium") as plain-text reasons like *"Synchronized attendance
with 22BCP045 (6 sessions, high risk)"* — there's no separate graph-visualization UI, since none of
the Stitch screens include one.

**ML fallback** (`app/ml/isolation_forest.py`) only runs `sklearn.ensemble.IsolationForest` when at
least 30 students each have at least 5 historical attendance records; below that threshold it
returns an empty list and the system relies on rule-based scoring only — this build never fabricates
an ML confidence score from insufficient data. When it does run, scores are min-max normalized to
the same 0–100 scale as the rule-based score.

## Local setup

**Backend** (Windows shown; adjust activation for macOS/Linux):

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy ..\.env.example ..\.env    # then fill in a real DATABASE_URL and secrets
.venv\Scripts\alembic upgrade head
.venv\Scripts\python seed.py
.venv\Scripts\uvicorn app.main:app --reload
```

**Frontend**:

```bash
cd frontend
npm install
copy .env.local.example .env.local   # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
```

**Seeded demo logins** (password for every seeded account: `Password123!`):
- Professor: `meera.nair@college.edu`
- Student: `arjun.mehta@college.edu`

(Two seeded students — Nikhil Jain / Pooja Nayak — are deliberately left in an active cooldown by
the seed script, to exercise that flow out of the box.)

## Environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string (`postgresql+psycopg2://...`) |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | Only relevant if the frontend ever talks to Supabase directly; the backend does not use Supabase Auth |
| `JWT_SECRET` | Signing secret for access tokens |
| `JWT_ALGORITHM` | JWT algorithm, default `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime, default 480 |
| `QR_SIGNING_SECRET` | HMAC secret for QR tokens — kept separate from `JWT_SECRET` |
| `QR_TOKEN_TTL_SECONDS` | QR rotation interval, default 10 |
| `COOLDOWN_MINUTES` | Post-logout lockout duration, default 60 |
| `FRONTEND_ORIGIN` | Allowed CORS origin for the backend |
| `NEXT_PUBLIC_API_BASE_URL` | Backend base URL the frontend calls (build-time inlined, see Docker) |

## Migrations

```bash
cd backend
.venv\Scripts\alembic revision --autogenerate -m "message"
.venv\Scripts\alembic upgrade head
```

**Caveat**: the initial migration in `backend/alembic/versions/` was **hand-written**, not
autogenerated — the target Supabase Postgres instance was DNS-unreachable from the environment
this project was built in. It was validated end-to-end (`upgrade`/`downgrade`) against a throwaway
SQLite database and mirrors every model exactly, but it has **not** been run against the real
target. Run `alembic upgrade head` against your real database and sanity-check the result before
relying on it in anything beyond local development.

## Seed data

`backend/seed.py` creates 3 professors, 20 students, 5 subjects/divisions, enrollments, ~15 days of
lectures with realistic attendance history, a handful of `SecurityEvent`s, two active `Cooldown`
rows, and a deliberate synchronized-attendance pattern between two students (so anomaly detection
has something real to surface immediately). It's idempotent — it skips if seed data already exists.
Like the migration above, it was dry-run against a throwaway SQLite database in this build
environment (same DNS-reachability issue) and has **not** yet been run against the real target
database — run `python seed.py` once connectivity is confirmed.

## Testing

```bash
cd backend
.venv\Scripts\pytest tests/ -v
```

Current status: **49 passed, 0 failed**.

| File | Covers |
|---|---|
| `test_auth.py` | Register/login/logout, wrong password |
| `test_rbac.py` | Role gating (student vs. professor endpoints), unauthenticated access |
| `test_qr.py` | Token issuance, expiry, replay, tampered signature, wrong-session token |
| `test_attendance.py` | Full scan happy path, late-marking, unenrolled rejection, duplicate rejection, non-owner close |
| `test_cooldown.py` | Login blocked during cooldown, scan blocked during cooldown, cooldown not created by expiry/crash |
| `test_manual_attendance.py` | Manual mark creates the record + audit row with correct previous/new status |
| `test_analytics.py` | Attendance-percentage and projection formulas against hand-computed values |
| `test_anomaly.py` | Rule-based scoring signals, synchronized-pair detection |

## Docker

```bash
docker compose up --build
```

Brings up `postgres` (16-alpine, healthchecked), `backend` (runs `alembic upgrade head` then
`uvicorn`, port 8000), and `frontend` (Next.js production build, port 3000). `NEXT_PUBLIC_API_BASE_URL`
is a **build-time** value in Next.js — it gets inlined into the client JS bundle, so it's passed as
a Docker build `ARG` (see `frontend/Dockerfile` and the `frontend.build.args` block in
`docker-compose.yml`) and must be the URL the **browser** can reach (`http://localhost:8000`), not
the in-network service name. All default secrets in `docker-compose.yml` are dev-only placeholders
— override them for anything beyond local use.

*This compose file was validated for syntax only in the environment this project was built in
(Docker itself wasn't available there) — run `docker compose up --build` end-to-end on a machine
with Docker before relying on it.*

## Known limitations / follow-ups

- **DB connectivity unverified**: migrations and seed data haven't been run against the real
  Supabase instance from this build environment (DNS-unreachable) — do this first on a real machine.
- **Rate limiting is IP-based only**: `/auth/login`, `/auth/register`, and `/attendance/scan` are
  rate-limited per client IP via `slowapi`. This is a reasonable first layer but not per-account —
  a determined attacker distributed across IPs isn't slowed by it; a production deployment behind a
  shared campus NAT should also consider per-account throttling.
- **Single-process realtime**: the WebSocket `ConnectionManager` and QR-rotation tasks are
  in-process only; running more than one backend instance would need Redis pub/sub to keep sessions
  in sync (the spec calls Redis optional infra — not implemented here).
- **ML anomaly scoring** only activates once ≥30 students each have ≥5 historical records — a
  freshly seeded database will only ever show rule-based scores, by design.
- **"Extend Timer"** on the live session screen is intentionally inert: sessions have no
  auto-expiry to extend (they stay `ACTIVE` until explicitly closed), so there's nothing to wire it
  to without fabricating a feature.
- **Account Settings card** (password reset / biometric toggle / notification preferences) from the
  `student_profile` Stitch screen has no backend feature in this build and was omitted rather than
  faked with a non-functional control.
