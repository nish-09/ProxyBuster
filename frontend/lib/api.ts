/**
 * Typed API client for the Proxy Busters FastAPI backend.
 * Field names/shapes mirror backend/app/schemas/*.py exactly — check there before changing types.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

let inMemoryToken: string | null = null;

export function setToken(token: string | null) {
  inMemoryToken = token;
  if (typeof window !== "undefined") {
    if (token) window.localStorage.setItem("pb_token", token);
    else window.localStorage.removeItem("pb_token");
  }
}

export function getToken(): string | null {
  if (inMemoryToken) return inMemoryToken;
  if (typeof window !== "undefined") {
    inMemoryToken = window.localStorage.getItem("pb_token");
  }
  return inMemoryToken;
}

/** Shape of FastAPI's default error body, and the cooldown-specific 423 body from auth_service.login_user. */
export interface ApiErrorDetail {
  message?: string;
  remaining_seconds?: number;
}

export class ApiError extends Error {
  status: number;
  detail: string | ApiErrorDetail;
  remainingSeconds?: number;

  constructor(status: number, detail: string | ApiErrorDetail) {
    const message = typeof detail === "string" ? detail : detail.message ?? "Request failed";
    super(message);
    this.status = status;
    this.detail = detail;
    if (typeof detail === "object" && typeof detail.remaining_seconds === "number") {
      this.remainingSeconds = detail.remaining_seconds;
    }
  }
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; auth?: boolean; query?: Record<string, string | number | boolean | undefined> } = {}
): Promise<T> {
  const { method = "GET", body, auth = true, query } = options;

  let url = `${API_BASE}/api${path}`;
  if (query) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
    }
    const qs = params.toString();
    if (qs) url += `?${qs}`;
  }

  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 204) return undefined as T;

  let payload: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!res.ok) {
    if (res.status === 401) setToken(null);
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload as { detail: string | ApiErrorDetail }).detail
        : typeof payload === "string"
          ? payload
          : "Request failed";
    throw new ApiError(res.status, detail);
  }

  return payload as T;
}

// ---------- Auth ----------

export type UserRole = "student" | "professor";

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
  role: UserRole;
  roll_number?: string;
  program?: string;
  semester?: number;
  department?: string;
}

export interface MeResponse {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  role: UserRole;
  user_id: string;
}

export const authApi = {
  register: (payload: RegisterRequest) => request<MeResponse>("/auth/register", { method: "POST", body: payload, auth: false }),
  login: (email: string, password: string, device_id?: string) =>
    request<TokenResponse>("/auth/login", { method: "POST", body: { email, password, device_id }, auth: false }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  me: () => request<MeResponse>("/auth/me"),
};

// ---------- Student ----------

export interface StudentMeResponse {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  roll_number: string;
  program: string;
  semester: number;
}

export type Standing = "good" | "warning";

export interface SubjectAttendanceOut {
  class_division_id: string;
  subject_code: string;
  subject_name: string;
  division_name: string;
  present: number;
  late: number;
  manual: number;
  absent: number;
  total: number;
  percentage: number;
  classes_can_miss: number;
  classes_needed_to_recover: number;
  next_class_at: string | null;
}

export interface TodayScheduleItem {
  class_division_id: string;
  subject_name: string;
  room: string | null;
  scheduled_start: string;
  scheduled_end: string;
  state: "past" | "current" | "upcoming";
}

export interface StudentDashboardOut {
  full_name: string;
  roll_number: string;
  program: string;
  semester: number;
  overall_percentage: number;
  total_classes: number;
  attended_classes: number;
  standing: Standing;
  subjects: SubjectAttendanceOut[];
  today_schedule: TodayScheduleItem[];
}

export interface AttendanceHistoryEntry {
  id: string;
  lecture_id: string;
  subject_name: string;
  professor_name: string;
  status: string;
  method: string;
  marked_at: string | null;
  scheduled_start: string;
}

export interface AttendanceHistoryOut {
  entries: AttendanceHistoryEntry[];
  present: number;
  absent: number;
  late: number;
  manual: number;
  total: number;
  percentage: number;
}

export interface CooldownStatusOut {
  active: boolean;
  remaining_seconds: number;
  expires_at: string | null;
}

export interface DeviceSessionOut {
  device_id: string | null;
  ip_address: string | null;
  user_agent: string | null;
  login_at: string;
  logout_at: string | null;
  status: string;
}

export interface BunkCalculatorOut {
  current_percentage: number;
  classes_can_miss: number;
  classes_needed_to_recover: number;
  projected_after_attending_1: number;
  projected_after_missing_1: number;
}

export const studentApi = {
  me: () => request<StudentMeResponse>("/students/me"),
  dashboard: () => request<StudentDashboardOut>("/students/me/dashboard"),
  attendance: (params?: { subject_id?: string; from_date?: string; to_date?: string; limit?: number; offset?: number }) =>
    request<AttendanceHistoryOut>("/students/me/attendance", { query: params }),
  subjectAttendance: (subjectId: string) => request<SubjectAttendanceOut>(`/students/me/attendance/${subjectId}`),
  cooldown: () => request<CooldownStatusOut>("/students/me/cooldown"),
  sessions: () => request<DeviceSessionOut[]>("/students/me/sessions"),
  bunkCalculator: (class_division_id: string, required_pct = 75.0) =>
    request<BunkCalculatorOut>("/students/me/bunk-calculator", { method: "POST", body: { class_division_id, required_pct } }),
};

// ---------- Professor ----------

export interface ActiveSubjectOut {
  class_division_id: string;
  subject_code: string;
  subject_name: string;
  division_name: string;
  avg_pct: number;
  has_active_session: boolean;
}

export interface UpcomingSessionOut {
  lecture_id: string;
  class_division_id: string;
  subject_name: string;
  division_name: string;
  room: string | null;
  scheduled_start: string;
  scheduled_end: string;
  has_active_session: boolean;
}

export interface ActivityFeedItem {
  id: string;
  type: string;
  severity: string;
  description: string;
  created_at: string;
  status: string;
}

export interface ProfessorDashboardOut {
  today_classes_count: number;
  total_students: number;
  avg_attendance_pct: number;
  suspicious_events_count: number;
  students_below_threshold_count: number;
  active_subjects: ActiveSubjectOut[];
  upcoming_sessions: UpcomingSessionOut[];
  activity_feed: ActivityFeedItem[];
}

export interface StudentListItem {
  student_id: string;
  user_id: string;
  full_name: string;
  roll_number: string;
  program: string;
  semester: number;
  overall_percentage: number;
  standing: Standing;
}

export interface StudentListOut {
  items: StudentListItem[];
  total: number;
}

export interface SecurityEventOut {
  id: string;
  user_id: string | null;
  student_name: string | null;
  event_type: string;
  description: string;
  severity: string;
  status: string;
  created_at: string;
  event_metadata: Record<string, unknown>;
}

export interface StudentDetailOut {
  student_id: string;
  full_name: string;
  email: string;
  roll_number: string;
  program: string;
  semester: number;
  overall_percentage: number;
  standing: Standing;
  active_device: DeviceSessionOut | null;
  cooldown: CooldownStatusOut;
  recent_security_events: SecurityEventOut[];
}

export interface AttendanceSheetCell {
  status: string | null;
  method: string | null;
}

export interface AttendanceSheetRow {
  student_id: string;
  full_name: string;
  roll_number: string;
  cells: Record<string, AttendanceSheetCell>;
  avg_pct: number;
  suspicious: boolean;
  suspicious_reason: string | null;
}

export interface AttendanceSheetOut {
  dates: string[];
  rows: AttendanceSheetRow[];
}

export interface AnomalyScoreOut {
  student_id: string;
  full_name: string;
  roll_number: string;
  score: number;
  reasons: string[];
  method: string;
  computed_at: string;
}

export interface CooldownListItem {
  student_id: string;
  full_name: string;
  roll_number: string;
  expires_at: string;
  remaining_seconds: number;
  reason: string;
}

export const professorApi = {
  dashboard: () => request<ProfessorDashboardOut>("/professor/dashboard"),
  analytics: () => request<ProfessorDashboardOut>("/professor/analytics"),
  students: (params?: { q?: string; class_division_id?: string; min_pct?: number; max_pct?: number; sort?: string }) =>
    request<StudentListOut>("/professor/students", { query: params }),
  student: (studentId: string) => request<StudentDetailOut>(`/professor/students/${studentId}`),
  forceLogout: (studentId: string) => request<void>(`/professor/students/${studentId}/force-logout`, { method: "POST" }),
  attendanceSheet: (params: { class_division_id: string; date_from: string; date_to: string }) =>
    request<AttendanceSheetOut>("/professor/attendance-sheet", { query: params }),
  security: (params?: { status?: string; severity?: string; limit?: number }) =>
    request<SecurityEventOut[]>("/professor/security", { query: params }),
  flagEvent: (eventId: string) => request<void>(`/professor/security/${eventId}/flag`, { method: "POST" }),
  dismissEvent: (eventId: string) => request<void>(`/professor/security/${eventId}/dismiss`, { method: "POST" }),
  cooldowns: () => request<CooldownListItem[]>("/professor/cooldowns"),
  anomalyScores: (classDivisionId?: string) =>
    request<AnomalyScoreOut[]>("/professor/anomaly-scores", { query: { class_division_id: classDivisionId } }),
};

// ---------- Attendance / QR ----------

export type SessionStatus = "active" | "closed";
export type AttendanceStatusValue = "present" | "absent" | "late" | "manual" | "suspicious";

export interface AttendanceSessionOut {
  id: string;
  lecture_id: string;
  professor_id: string;
  status: SessionStatus;
  started_at: string;
  ended_at: string | null;
}

export interface LiveFeedEntry {
  id: string;
  student_name: string;
  roll_number: string;
  status: AttendanceStatusValue;
  marked_at: string;
}

export interface LiveSessionState {
  session_id: string;
  status: SessionStatus;
  present_count: number;
  total_enrolled: number;
  current_token_expires_at: string | null;
  qr_payload: string | null;
  feed: LiveFeedEntry[];
}

export interface ScanResult {
  status: "marked" | "rejected";
  attendance_status: string | null;
  message: string;
}

export interface ManualAttendanceOut {
  id: string;
  attendance_record_id: string;
  professor_id: string;
  reason: string;
  previous_status: string | null;
  new_status: string;
  created_at: string;
}

export const attendanceApi = {
  createSession: (lecture_id: string) =>
    request<AttendanceSessionOut>("/attendance/sessions", { method: "POST", body: { lecture_id } }),
  getSession: (sessionId: string) => request<AttendanceSessionOut>(`/attendance/sessions/${sessionId}`),
  closeSession: (sessionId: string) => request<AttendanceSessionOut>(`/attendance/sessions/${sessionId}/close`, { method: "POST" }),
  liveSession: (sessionId: string) => request<LiveSessionState>(`/attendance/sessions/${sessionId}/live`),
  scan: (token: string) => request<ScanResult>("/attendance/scan", { method: "POST", body: { token } }),
  manual: (payload: { student_id: string; lecture_id: string; status: "present" | "absent" | "late"; reason: string }) =>
    request<ManualAttendanceOut>("/attendance/manual", { method: "POST", body: payload }),
};

/** Builds the WebSocket URL for a session's live feed; token is passed as a query param (browsers can't set WS headers). */
export function attendanceSocketUrl(sessionId: string): string {
  const token = getToken();
  const wsBase = API_BASE.replace(/^http/, "ws");
  return `${wsBase}/api/ws/attendance/sessions/${sessionId}?token=${encodeURIComponent(token ?? "")}`;
}
