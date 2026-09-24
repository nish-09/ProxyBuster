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

/** Shape of the structured error bodies the backend returns (see attendance_service.api_error). */
export interface ApiErrorDetail {
  code?: string;
  message?: string;
  remaining_seconds?: number;
  valid_until?: string;
}

/** One entry of FastAPI's 422 validation error list. */
interface ValidationDetail {
  loc?: (string | number)[];
  msg?: string;
}

export const AUTH_EXPIRED_EVENT = "pb:auth-expired";

const GENERIC_SERVER_ERROR = "Something went wrong on our side. Please try again.";
const NETWORK_ERROR = "Can't reach the server. Check your connection and try again.";
const REQUEST_TIMEOUT_MS = 20_000;

function messageFromDetail(status: number, detail: unknown): string {
  if (status >= 500) return GENERIC_SERVER_ERROR;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0] as ValidationDetail | undefined;
    const field = first?.loc?.filter((p) => p !== "body").slice(-1)[0];
    return first?.msg ? `${field ? `${String(field)}: ` : ""}${first.msg}` : "Some of the information you entered is invalid.";
  }
  if (detail && typeof detail === "object" && "message" in detail && typeof (detail as ApiErrorDetail).message === "string") {
    return (detail as ApiErrorDetail).message as string;
  }
  return "Request failed";
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  code?: string;
  remainingSeconds?: number;
  validUntil?: string;

  constructor(status: number, detail: unknown, messageOverride?: string) {
    super(messageOverride ?? messageFromDetail(status, detail));
    this.status = status;
    this.detail = detail;
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      const d = detail as ApiErrorDetail;
      if (typeof d.code === "string") this.code = d.code;
      if (typeof d.remaining_seconds === "number") this.remainingSeconds = d.remaining_seconds;
      if (typeof d.valid_until === "string") this.validUntil = d.valid_until;
    }
  }

  /** True only for a genuine authentication failure (expired/invalid/revoked token). */
  get isAuthFailure(): boolean {
    return this.status === 401;
  }
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; auth?: boolean; query?: Record<string, string | number | boolean | undefined>; signal?: AbortSignal } = {}
): Promise<T> {
  const { method = "GET", body, auth = true, query, signal } = options;

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
  let sentToken: string | null = null;
  if (auth) {
    sentToken = getToken();
    if (sentToken) headers["Authorization"] = `Bearer ${sentToken}`;
  }

  // Every request has a deadline so no screen can spin forever on a hung connection, and a
  // caller-supplied signal (e.g. leaving the scanner) cancels it early.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const onCallerAbort = () => controller.abort();
  signal?.addEventListener("abort", onCallerAbort);

  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (err) {
    if (signal?.aborted) throw err; // the caller cancelled: let it see a normal AbortError
    throw new ApiError(0, null, controller.signal.aborted ? "The server took too long to respond. Please try again." : NETWORK_ERROR);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onCallerAbort);
  }

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
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload as { detail: unknown }).detail
        : typeof payload === "string"
          ? payload
          : "Request failed";
    // Only a 401 on a request that actually carried OUR current token means the session is
    // over. A 500, a 4xx business error, a timeout or a dropped connection must never log
    // anyone out (that used to happen for any failure of /auth/me).
    if (res.status === 401 && sentToken && getToken() === sentToken) {
      setToken(null);
      if (typeof window !== "undefined") window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    }
    throw new ApiError(res.status, detail);
  }

  return payload as T;
}

/**
 * Same auth/timeout/error-handling contract as request(), for multipart bodies (image
 * uploads). Never sets Content-Type manually — the browser fills in the multipart boundary.
 */
async function requestForm<T>(path: string, formData: FormData, options: { method?: string; signal?: AbortSignal } = {}): Promise<T> {
  const { method = "POST", signal } = options;
  const url = `${API_BASE}/api${path}`;

  const headers: Record<string, string> = {};
  const sentToken = getToken();
  if (sentToken) headers["Authorization"] = `Bearer ${sentToken}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const onCallerAbort = () => controller.abort();
  signal?.addEventListener("abort", onCallerAbort);

  let res: Response;
  try {
    res = await fetch(url, { method, headers, body: formData, signal: controller.signal });
  } catch (err) {
    if (signal?.aborted) throw err;
    throw new ApiError(0, null, controller.signal.aborted ? "The server took too long to respond. Please try again." : NETWORK_ERROR);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onCallerAbort);
  }

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
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload as { detail: unknown }).detail
        : typeof payload === "string"
          ? payload
          : "Request failed";
    if (res.status === 401 && sentToken && getToken() === sentToken) {
      setToken(null);
      if (typeof window !== "undefined") window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    }
    throw new ApiError(res.status, detail);
  }

  return payload as T;
}

// ---------- Auth ----------

export type UserRole = "student" | "professor" | "admin";

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
  role: UserRole;
  roll_number?: string;
  program?: string;
  semester?: number;
  department?: string;
  invite_code?: string;
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
  reason: string | null;
}

export interface RestrictionStatusOut {
  active: boolean;
  valid_until: string | null;
  reason: string | null;
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
  restriction: () => request<RestrictionStatusOut>("/students/me/restriction"),
  lastScan: () => request<LastScanOut>("/students/me/last-scan"),
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
  active_session_id: string | null;
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
  active_session_id: string | null;
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

export interface AttendanceSheetColumn {
  lecture_id: string;
  date: string;
  label: string;
  /** false for a lecture that hasn't started yet (a blank cell is then not an absence). */
  started: boolean;
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
  columns: AttendanceSheetColumn[];
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

export type SessionStatus = "active" | "closed" | "expired";
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
  session_expires_at: string | null;
  qr_payload: string | null;
  qr_ttl_seconds: number;
  /** Authoritative server clock, used to correct countdowns for a wrong device clock. */
  server_time: string;
  lecture_id: string;
  class_division_id: string;
  subject_code: string;
  subject_name: string;
  division_name: string;
  room: string | null;
  topic: string | null;
  feed: LiveFeedEntry[];
}

export interface ScanResult {
  status: "marked" | "rejected";
  attendance_status: string | null;
  message: string;
  subject_code: string | null;
  subject_name: string | null;
  division_name: string | null;
  session_topic: string | null;
  marked_at: string | null;
  cooldown_seconds: number | null;
  cooldown_expires_at: string | null;
  server_time: string | null;
}

export interface LastScanOut {
  attendance_status: string;
  subject_code: string;
  subject_name: string;
  division_name: string;
  session_topic: string | null;
  marked_at: string;
  server_time: string;
  cooldown_active: boolean;
  cooldown_remaining_seconds: number;
  cooldown_expires_at: string | null;
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
  createAdhocSession: (payload: { class_division_id: string; duration_minutes: number; topic?: string }) =>
    request<AttendanceSessionOut>("/attendance/sessions/adhoc", { method: "POST", body: payload }),
  getSession: (sessionId: string) => request<AttendanceSessionOut>(`/attendance/sessions/${sessionId}`),
  closeSession: (sessionId: string) => request<AttendanceSessionOut>(`/attendance/sessions/${sessionId}/close`, { method: "POST" }),
  liveSession: (sessionId: string) => request<LiveSessionState>(`/attendance/sessions/${sessionId}/live`),
  scan: (token: string, signal?: AbortSignal) => request<ScanResult>("/attendance/scan", { method: "POST", body: { token }, signal }),
  manual: (payload: { student_id: string; lecture_id: string; status: "present" | "absent" | "late"; reason: string }) =>
    request<ManualAttendanceOut>("/attendance/manual", { method: "POST", body: payload }),
};

// ---------- Classroom AI verification ----------

export type VerificationStatusValue = "processing" | "completed" | "failed";
export type DetectionStatusValue = "confirmed" | "high_confidence" | "uncertain" | "not_detected";
export type DiscrepancyTypeValue = "attended_and_detected" | "attended_not_detected" | "detected_not_attended" | "none";
export type DecisionActionValue = "confirmed_present" | "asked_to_scan" | "dismissed" | "violation";
export type ViolationReasonValue = "proxy_attendance" | "not_physically_present" | "unauthorized_attendance" | "other";
export type RestrictionDurationValue = "one_lecture" | "one_day" | "three_days" | "seven_days" | "custom";

export interface ClassroomVerificationOut {
  id: string;
  session_id: string;
  lecture_id: string;
  status: VerificationStatusValue;
  image_count: number;
  provider: string;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface VerificationResultOut {
  id: string;
  student_id: string;
  full_name: string;
  roll_number: string;
  qr_present: boolean;
  ai_status: DetectionStatusValue;
  confidence: number;
  discrepancy_type: DiscrepancyTypeValue;
  decision_action: DecisionActionValue | null;
  decision_notes: string | null;
  decided_at: string | null;
}

export interface ClassroomVerificationDetailOut {
  verification: ClassroomVerificationOut;
  total_enrolled: number;
  students_excluded_no_reference_photo: number;
  present_count: number;
  confirmed_count: number;
  discrepancy_count: number;
  results: VerificationResultOut[];
}

export interface VerificationDecisionRequest {
  action: DecisionActionValue;
  notes?: string;
  reason?: ViolationReasonValue;
  restriction_duration?: RestrictionDurationValue;
  custom_restriction_end?: string;
}

export interface VerificationDecisionOut {
  result_id: string;
  action: string;
  notes: string | null;
  created_at: string;
  violation_id: string | null;
  restriction_end: string | null;
}

export interface ViolationOut {
  id: string;
  student_id: string;
  full_name: string;
  roll_number: string;
  lecture_id: string;
  professor_id: string;
  reason: string;
  notes: string | null;
  status: "active" | "revoked";
  created_at: string;
  restriction_start: string;
  restriction_end: string;
  revoked_at: string | null;
  revocation_reason: string | null;
}

export const verificationApi = {
  start: (sessionId: string, images: File[]) => {
    const form = new FormData();
    for (const image of images) form.append("images", image);
    return requestForm<ClassroomVerificationOut>(`/verification/sessions/${sessionId}/verify`, form);
  },
  get: (verificationId: string) => request<ClassroomVerificationDetailOut>(`/verification/${verificationId}`),
  decide: (resultId: string, payload: VerificationDecisionRequest) =>
    request<VerificationDecisionOut>(`/verification/results/${resultId}/decision`, { method: "POST", body: payload }),
  myViolations: (classDivisionId?: string) =>
    request<ViolationOut[]>("/verification/violations/mine", { query: { class_division_id: classDivisionId } }),
  revokeViolation: (violationId: string, revocation_reason: string) =>
    request<ViolationOut>(`/verification/violations/${violationId}/revoke`, { method: "POST", body: { revocation_reason } }),
};

// ---------- Admin ----------

export interface AdminStudentOut {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  roll_number: string;
  program: string;
  semester: number;
  created_at: string;
  has_reference_photo: boolean;
}

export interface AdminReferencePhotoOut {
  student_id: string;
  has_reference_photo: boolean;
  content_type: string | null;
  uploaded_at: string | null;
}

export interface DeviceBindingResetOut {
  student_id: string;
  revoked_count: number;
}

export interface AdminCreateStudentRequest {
  email: string;
  password: string;
  full_name: string;
  roll_number: string;
  program: string;
  semester: number;
}

export interface AdminUpdateStudentRequest {
  password?: string;
  full_name?: string;
  program?: string;
  semester?: number;
  is_active?: boolean;
}

export interface AdminProfessorOut {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  department: string;
  created_at: string;
}

export interface AdminCreateProfessorRequest {
  email: string;
  password: string;
  full_name: string;
  department: string;
}

export interface AdminUpdateProfessorRequest {
  password?: string;
  full_name?: string;
  department?: string;
  is_active?: boolean;
}

export interface AdminSubjectOut {
  id: string;
  code: string;
  name: string;
  credits: number;
}

export interface AdminCreateSubjectRequest {
  code: string;
  name: string;
  credits: number;
}

export interface AdminUpdateSubjectRequest {
  name?: string;
  credits?: number;
}

export interface AdminDivisionOut {
  id: string;
  subject_id: string;
  subject_code: string;
  subject_name: string;
  professor_id: string;
  professor_name: string;
  name: string;
  semester: number;
  room: string | null;
  enrolled_count: number;
}

export interface AdminCreateDivisionRequest {
  subject_id: string;
  professor_id: string;
  name: string;
  semester: number;
  room?: string;
}

export interface AdminUpdateDivisionRequest {
  professor_id?: string;
  name?: string;
  semester?: number;
  room?: string;
}

export interface AdminEnrollmentOut {
  id: string;
  student_id: string;
  student_name: string;
  roll_number: string;
  class_division_id: string;
  created_at: string;
}

export interface AdminBulkEnrollResult {
  enrolled: string[];
  already_enrolled: string[];
  not_found: string[];
}

export interface AdminLectureOut {
  id: string;
  class_division_id: string;
  subject_name: string;
  division_name: string;
  topic: string | null;
  scheduled_start: string;
  scheduled_end: string;
  room: string | null;
}

export interface AdminCreateLectureRequest {
  class_division_id: string;
  topic?: string;
  scheduled_start: string;
  scheduled_end: string;
  room?: string;
}

export interface AdminSummaryOut {
  students: number;
  professors: number;
  subjects: number;
  divisions: number;
  lectures: number;
  enrollments: number;
}

export function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

export const adminApi = {
  summary: () => request<AdminSummaryOut>("/admin/summary"),
  students: (q?: string) => request<AdminStudentOut[]>("/admin/students", { query: { q, limit: 500 } }),
  createStudent: (payload: AdminCreateStudentRequest) =>
    request<AdminStudentOut>("/admin/students", { method: "POST", body: payload }),
  updateStudent: (id: string, payload: AdminUpdateStudentRequest) =>
    request<AdminStudentOut>(`/admin/students/${id}`, { method: "PATCH", body: payload }),
  uploadReferencePhoto: (studentId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return requestForm<AdminReferencePhotoOut>(`/admin/students/${studentId}/reference-photo`, form);
  },
  deleteReferencePhoto: (studentId: string) =>
    request<void>(`/admin/students/${studentId}/reference-photo`, { method: "DELETE" }),
  resetDeviceBinding: (studentId: string, reason?: string) =>
    request<DeviceBindingResetOut>(`/admin/students/${studentId}/device-binding/reset`, { method: "POST", body: { reason } }),

  professors: (q?: string) => request<AdminProfessorOut[]>("/admin/professors", { query: { q, limit: 500 } }),
  createProfessor: (payload: AdminCreateProfessorRequest) =>
    request<AdminProfessorOut>("/admin/professors", { method: "POST", body: payload }),
  updateProfessor: (id: string, payload: AdminUpdateProfessorRequest) =>
    request<AdminProfessorOut>(`/admin/professors/${id}`, { method: "PATCH", body: payload }),

  subjects: () => request<AdminSubjectOut[]>("/admin/subjects"),
  createSubject: (payload: AdminCreateSubjectRequest) =>
    request<AdminSubjectOut>("/admin/subjects", { method: "POST", body: payload }),
  updateSubject: (id: string, payload: AdminUpdateSubjectRequest) =>
    request<AdminSubjectOut>(`/admin/subjects/${id}`, { method: "PATCH", body: payload }),
  deleteSubject: (id: string) => request<void>(`/admin/subjects/${id}`, { method: "DELETE" }),

  divisions: () => request<AdminDivisionOut[]>("/admin/divisions"),
  createDivision: (payload: AdminCreateDivisionRequest) =>
    request<AdminDivisionOut>("/admin/divisions", { method: "POST", body: payload }),
  updateDivision: (id: string, payload: AdminUpdateDivisionRequest) =>
    request<AdminDivisionOut>(`/admin/divisions/${id}`, { method: "PATCH", body: payload }),

  enrollments: (classDivisionId: string) =>
    request<AdminEnrollmentOut[]>("/admin/enrollments", { query: { class_division_id: classDivisionId } }),
  createEnrollment: (student_id: string, class_division_id: string) =>
    request<AdminEnrollmentOut>("/admin/enrollments", { method: "POST", body: { student_id, class_division_id } }),
  deleteEnrollment: (id: string) => request<void>(`/admin/enrollments/${id}`, { method: "DELETE" }),
  bulkEnroll: (student_ids: string[], class_division_id: string) =>
    request<AdminBulkEnrollResult>("/admin/enrollments/bulk", { method: "POST", body: { student_ids, class_division_id } }),

  lectures: (classDivisionId?: string) =>
    request<AdminLectureOut[]>("/admin/lectures", { query: { class_division_id: classDivisionId } }),
  createLecture: (payload: AdminCreateLectureRequest) =>
    request<AdminLectureOut>("/admin/lectures", { method: "POST", body: payload }),
  deleteLecture: (id: string) => request<void>(`/admin/lectures/${id}`, { method: "DELETE" }),

  violations: () => request<ViolationOut[]>("/admin/violations"),
  revokeViolation: (violationId: string, revocation_reason: string) =>
    request<ViolationOut>(`/admin/violations/${violationId}/revoke`, { method: "POST", body: { revocation_reason } }),
};

/**
 * WebSocket URL for a session's live feed. The JWT is deliberately NOT in the URL (URLs end up
 * in proxy/server access logs); the client sends it as the first message instead — see
 * attendanceSocketAuthMessage().
 */
export function attendanceSocketUrl(sessionId: string): string {
  const wsBase = API_BASE.replace(/^http/, "ws");
  return `${wsBase}/api/ws/attendance/sessions/${sessionId}`;
}

export function attendanceSocketAuthMessage(): string {
  return JSON.stringify({ type: "auth", token: getToken() ?? "" });
}
