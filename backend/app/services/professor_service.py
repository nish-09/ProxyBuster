import uuid
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.time import ensure_utc, utcnow
from app.models.academic import ClassDivision, Enrollment, Lecture, Subject
from app.models.attendance import AttendanceRecord, AttendanceSession, SessionStatus
from app.models.security import AnomalyScore, Cooldown, DeviceSession, DeviceSessionStatus, SecurityEvent, SecurityEventSeverity, SecurityEventStatus
from app.models.user import ProfessorProfile, StudentProfile, User
from app.schemas.professor import (
    ActiveSubjectOut,
    ActivityFeedItem,
    AttendanceSheetCell,
    AttendanceSheetOut,
    AttendanceSheetRow,
    CooldownListItem,
    ProfessorDashboardOut,
    SecurityEventOut,
    StudentDetailOut,
    StudentListItem,
    StudentListOut,
    UpcomingSessionOut,
)
from app.schemas.student import CooldownStatusOut, DeviceSessionOut
from app.services import analytics_service
from app.services.cooldown_service import get_active_cooldown

REQUIRED_PCT_DEFAULT = 75.0
SUSPICIOUS_SCORE_THRESHOLD = 60.0


def owned_class_division_ids(db: Session, professor_profile: ProfessorProfile) -> list[uuid.UUID]:
    return _owned_class_division_ids(db, professor_profile)


def enrolled_student_ids(db: Session, class_division_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    return _enrolled_student_ids(db, class_division_ids)


def _owned_class_division_ids(db: Session, professor_profile: ProfessorProfile) -> list[uuid.UUID]:
    return [
        row[0]
        for row in db.query(ClassDivision.id).filter(ClassDivision.professor_id == professor_profile.id).all()
    ]


def _enrolled_student_ids(db: Session, class_division_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    if not class_division_ids:
        return []
    return list(
        {
            row[0]
            for row in db.query(Enrollment.student_id)
            .filter(Enrollment.class_division_id.in_(class_division_ids))
            .all()
        }
    )


def _security_events_query(db: Session, student_ids: list[uuid.UUID]):
    if not student_ids:
        return db.query(SecurityEvent).filter(False)
    user_ids = [row[0] for row in db.query(StudentProfile.user_id).filter(StudentProfile.id.in_(student_ids)).all()]
    return db.query(SecurityEvent).filter(SecurityEvent.user_id.in_(user_ids))


def _student_display_name(db: Session, student_profile: StudentProfile) -> str:
    user = db.get(User, student_profile.user_id)
    return user.full_name if user else "Unknown"


def dashboard(db: Session, professor_profile: ProfessorProfile) -> ProfessorDashboardOut:
    owned_ids = _owned_class_division_ids(db, professor_profile)
    now = utcnow()
    day_start = datetime.combine(now.date(), time.min, tzinfo=now.tzinfo)
    day_end = day_start + timedelta(days=1)

    today_lectures = (
        db.query(Lecture)
        .filter(Lecture.class_division_id.in_(owned_ids), Lecture.scheduled_start >= day_start, Lecture.scheduled_start < day_end)
        .all()
        if owned_ids
        else []
    )

    student_ids = _enrolled_student_ids(db, owned_ids)
    total_students = len(student_ids)

    percentages = []
    below_threshold_students: set[uuid.UUID] = set()
    active_subjects: list[ActiveSubjectOut] = []
    for cd_id in owned_ids:
        class_division = db.get(ClassDivision, cd_id)
        subject = db.get(Subject, class_division.subject_id)
        cd_student_ids = [
            row[0] for row in db.query(Enrollment.student_id).filter(Enrollment.class_division_id == cd_id).all()
        ]
        cd_stats = analytics_service.batch_subject_stats(db, cd_student_ids, cd_id, REQUIRED_PCT_DEFAULT)
        cd_pcts = []
        for sid in cd_student_ids:
            pct = cd_stats[sid]["percentage"]
            cd_pcts.append(pct)
            if pct < REQUIRED_PCT_DEFAULT:
                below_threshold_students.add(sid)
        avg_pct = round(sum(cd_pcts) / len(cd_pcts), 2) if cd_pcts else 0.0
        percentages.append(avg_pct)

        has_active = (
            db.query(AttendanceSession)
            .join(Lecture, AttendanceSession.lecture_id == Lecture.id)
            .filter(Lecture.class_division_id == cd_id, AttendanceSession.status == SessionStatus.ACTIVE)
            .first()
            is not None
        )
        active_subjects.append(
            ActiveSubjectOut(
                class_division_id=cd_id,
                subject_code=subject.code,
                subject_name=subject.name,
                division_name=class_division.name,
                avg_pct=avg_pct,
                has_active_session=has_active,
            )
        )

    avg_attendance_pct = round(sum(percentages) / len(percentages), 2) if percentages else 0.0

    upcoming_lectures = (
        db.query(Lecture)
        .filter(Lecture.class_division_id.in_(owned_ids), Lecture.scheduled_start >= now)
        .order_by(Lecture.scheduled_start.asc())
        .limit(5)
        .all()
        if owned_ids
        else []
    )
    upcoming_sessions = []
    for lecture in upcoming_lectures:
        class_division = db.get(ClassDivision, lecture.class_division_id)
        subject = db.get(Subject, class_division.subject_id)
        has_active = (
            db.query(AttendanceSession)
            .filter(AttendanceSession.lecture_id == lecture.id, AttendanceSession.status == SessionStatus.ACTIVE)
            .first()
            is not None
        )
        upcoming_sessions.append(
            UpcomingSessionOut(
                lecture_id=lecture.id,
                class_division_id=class_division.id,
                subject_name=subject.name,
                division_name=class_division.name,
                room=lecture.room,
                scheduled_start=lecture.scheduled_start,
                scheduled_end=lecture.scheduled_end,
                has_active_session=has_active,
            )
        )

    events_q = _security_events_query(db, student_ids).filter(
        SecurityEvent.status == SecurityEventStatus.OPEN,
        SecurityEvent.severity.in_([SecurityEventSeverity.MEDIUM, SecurityEventSeverity.HIGH]),
    )
    suspicious_events_count = events_q.count()

    feed_events = (
        _security_events_query(db, student_ids).order_by(SecurityEvent.created_at.desc()).limit(10).all()
    )
    activity_feed = [
        ActivityFeedItem(
            id=e.id,
            type=e.event_type,
            severity=e.severity.value,
            description=e.description,
            created_at=e.created_at,
            status=e.status.value,
        )
        for e in feed_events
    ]

    return ProfessorDashboardOut(
        today_classes_count=len(today_lectures),
        total_students=total_students,
        avg_attendance_pct=avg_attendance_pct,
        suspicious_events_count=suspicious_events_count,
        students_below_threshold_count=len(below_threshold_students),
        active_subjects=active_subjects,
        upcoming_sessions=upcoming_sessions,
        activity_feed=activity_feed,
    )


def list_students(
    db: Session,
    professor_profile: ProfessorProfile,
    q: str | None = None,
    class_division_id: uuid.UUID | None = None,
    min_pct: float | None = None,
    max_pct: float | None = None,
    sort: str | None = None,
) -> StudentListOut:
    owned_ids = _owned_class_division_ids(db, professor_profile)
    scope_ids = [class_division_id] if class_division_id else owned_ids
    if class_division_id and class_division_id not in owned_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not teach this class")

    student_ids = _enrolled_student_ids(db, scope_ids)
    overall_by_student = analytics_service.batch_overall_stats(db, student_ids, scope_ids, REQUIRED_PCT_DEFAULT)
    items: list[StudentListItem] = []
    for sid in student_ids:
        student_profile = db.get(StudentProfile, sid)
        user = db.get(User, student_profile.user_id)
        if q:
            needle = q.lower()
            if needle not in user.full_name.lower() and needle not in student_profile.roll_number.lower():
                continue
        overall = overall_by_student[sid]
        pct = overall["percentage"]
        if min_pct is not None and pct < min_pct:
            continue
        if max_pct is not None and pct > max_pct:
            continue
        items.append(
            StudentListItem(
                student_id=sid,
                user_id=user.id,
                full_name=user.full_name,
                roll_number=student_profile.roll_number,
                program=student_profile.program,
                semester=student_profile.semester,
                overall_percentage=pct,
                standing="good" if pct >= REQUIRED_PCT_DEFAULT else "warning",
            )
        )

    reverse = bool(sort and sort.startswith("-"))
    key = (sort or "name").lstrip("-")
    key_fn = {
        "name": lambda i: i.full_name.lower(),
        "roll": lambda i: i.roll_number,
        "percentage": lambda i: i.overall_percentage,
    }.get(key, lambda i: i.full_name.lower())
    items.sort(key=key_fn, reverse=reverse)

    return StudentListOut(items=items, total=len(items))


def _verify_student_in_scope(db: Session, professor_profile: ProfessorProfile, student_id: uuid.UUID) -> StudentProfile:
    owned_ids = _owned_class_division_ids(db, professor_profile)
    enrolled = (
        db.query(Enrollment)
        .filter(Enrollment.student_id == student_id, Enrollment.class_division_id.in_(owned_ids))
        .first()
        if owned_ids
        else None
    )
    if enrolled is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found in your classes")
    student_profile = db.get(StudentProfile, student_id)
    if student_profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")
    return student_profile


def student_detail(db: Session, professor_profile: ProfessorProfile, student_id: uuid.UUID) -> StudentDetailOut:
    student_profile = _verify_student_in_scope(db, professor_profile, student_id)
    user = db.get(User, student_profile.user_id)
    owned_ids = _owned_class_division_ids(db, professor_profile)
    overall = analytics_service.student_overall_stats(db, student_id, REQUIRED_PCT_DEFAULT, owned_ids)

    active_device_row = (
        db.query(DeviceSession)
        .filter(DeviceSession.user_id == user.id, DeviceSession.status == DeviceSessionStatus.ACTIVE)
        .order_by(DeviceSession.login_at.desc())
        .first()
    )
    active_device = (
        DeviceSessionOut(
            device_id=active_device_row.device_id,
            ip_address=active_device_row.ip_address,
            user_agent=active_device_row.user_agent,
            login_at=active_device_row.login_at,
            logout_at=active_device_row.logout_at,
            status=active_device_row.status.value,
        )
        if active_device_row
        else None
    )

    cooldown = get_active_cooldown(db, student_id)
    cooldown_out = (
        CooldownStatusOut(
            active=True,
            remaining_seconds=max(int((ensure_utc(cooldown.expires_at) - utcnow()).total_seconds()), 0),
            expires_at=cooldown.expires_at,
        )
        if cooldown
        else CooldownStatusOut(active=False, remaining_seconds=0, expires_at=None)
    )

    recent_events = (
        db.query(SecurityEvent).filter(SecurityEvent.user_id == user.id).order_by(SecurityEvent.created_at.desc()).limit(5).all()
    )
    events_out = [
        SecurityEventOut(
            id=e.id,
            user_id=e.user_id,
            student_name=user.full_name,
            event_type=e.event_type,
            description=e.description,
            severity=e.severity.value,
            status=e.status.value,
            created_at=e.created_at,
            event_metadata=e.event_metadata or {},
        )
        for e in recent_events
    ]

    return StudentDetailOut(
        student_id=student_id,
        full_name=user.full_name,
        email=user.email,
        roll_number=student_profile.roll_number,
        program=student_profile.program,
        semester=student_profile.semester,
        overall_percentage=overall["percentage"],
        standing="good" if overall["percentage"] >= REQUIRED_PCT_DEFAULT else "warning",
        active_device=active_device,
        cooldown=cooldown_out,
        recent_security_events=events_out,
    )


def force_logout(db: Session, professor_profile: ProfessorProfile, student_id: uuid.UUID) -> None:
    student_profile = _verify_student_in_scope(db, professor_profile, student_id)
    user = db.get(User, student_profile.user_id)

    active_sessions = (
        db.query(DeviceSession).filter(DeviceSession.user_id == user.id, DeviceSession.status == DeviceSessionStatus.ACTIVE).all()
    )
    now = utcnow()
    for s in active_sessions:
        s.status = DeviceSessionStatus.REVOKED
        s.logout_at = now

    # Deliberately no cooldown here: cooldown is a consequence of the student's own
    # voluntary logout (see auth_service.logout_user), not of a professor-initiated action.
    db.add(
        SecurityEvent(
            user_id=user.id,
            event_type="professor_force_logout",
            description=f"Session force-disconnected by professor {professor_profile.id}",
            severity=SecurityEventSeverity.MEDIUM,
            event_metadata={"professor_id": str(professor_profile.id)},
        )
    )
    db.commit()


def attendance_sheet(
    db: Session, professor_profile: ProfessorProfile, class_division_id: uuid.UUID, date_from: date, date_to: date
) -> AttendanceSheetOut:
    class_division = db.get(ClassDivision, class_division_id)
    if class_division is None or class_division.professor_id != professor_profile.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not teach this class")

    start_dt = datetime.combine(date_from, time.min)
    end_dt = datetime.combine(date_to, time.max)
    lectures = (
        db.query(Lecture)
        .filter(Lecture.class_division_id == class_division_id, Lecture.scheduled_start >= start_dt, Lecture.scheduled_start <= end_dt)
        .order_by(Lecture.scheduled_start.asc())
        .all()
    )
    lecture_dates = [ensure_utc(l.scheduled_start).date().isoformat() for l in lectures]
    date_counts: dict[str, int] = {}
    for d in lecture_dates:
        date_counts[d] = date_counts.get(d, 0) + 1
    columns = []
    for lecture, iso_date in zip(lectures, lecture_dates):
        if date_counts[iso_date] > 1:
            label = ensure_utc(lecture.scheduled_start).strftime("%b %d %I:%M %p")
        else:
            label = iso_date
        columns.append({"lecture_id": lecture.id, "date": iso_date, "label": label})

    enrollments = db.query(Enrollment).filter(Enrollment.class_division_id == class_division_id).all()
    student_ids = [e.student_id for e in enrollments]

    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.lecture_id.in_([l.id for l in lectures]), AttendanceRecord.student_id.in_(student_ids))
        .all()
        if lectures and student_ids
        else []
    )
    records_by_student: dict[uuid.UUID, dict[uuid.UUID, AttendanceRecord]] = {}
    for r in records:
        records_by_student.setdefault(r.student_id, {})[r.lecture_id] = r

    stats_by_student = analytics_service.batch_subject_stats(db, student_ids, class_division_id, REQUIRED_PCT_DEFAULT)

    rows: list[AttendanceSheetRow] = []
    for sid in student_ids:
        student_profile = db.get(StudentProfile, sid)
        user = db.get(User, student_profile.user_id)
        cells: dict[str, AttendanceSheetCell] = {}
        for lecture in lectures:
            record = records_by_student.get(sid, {}).get(lecture.id)
            cells[str(lecture.id)] = (
                AttendanceSheetCell(status=record.status.value, method=record.method.value)
                if record
                else AttendanceSheetCell(status=None, method=None)
            )

        stats = stats_by_student[sid]

        latest_anomaly = (
            db.query(AnomalyScore).filter(AnomalyScore.student_id == sid).order_by(AnomalyScore.computed_at.desc()).first()
        )
        suspicious = bool(latest_anomaly and float(latest_anomaly.score) >= SUSPICIOUS_SCORE_THRESHOLD)
        suspicious_reason = (latest_anomaly.reasons[0] if suspicious and latest_anomaly.reasons else None)

        rows.append(
            AttendanceSheetRow(
                student_id=sid,
                full_name=user.full_name,
                roll_number=student_profile.roll_number,
                cells=cells,
                avg_pct=stats["percentage"],
                suspicious=suspicious,
                suspicious_reason=suspicious_reason,
            )
        )

    return AttendanceSheetOut(columns=columns, rows=rows)


def security_events(
    db: Session,
    professor_profile: ProfessorProfile,
    status_filter: str | None = None,
    severity_filter: str | None = None,
    limit: int = 50,
) -> list[SecurityEventOut]:
    owned_ids = _owned_class_division_ids(db, professor_profile)
    student_ids = _enrolled_student_ids(db, owned_ids)
    query = _security_events_query(db, student_ids)
    if status_filter:
        query = query.filter(SecurityEvent.status == SecurityEventStatus(status_filter))
    if severity_filter:
        query = query.filter(SecurityEvent.severity == SecurityEventSeverity(severity_filter))
    events = query.order_by(SecurityEvent.created_at.desc()).limit(limit).all()

    results = []
    for e in events:
        student_profile = db.query(StudentProfile).filter(StudentProfile.user_id == e.user_id).first() if e.user_id else None
        user = db.get(User, e.user_id) if e.user_id else None
        results.append(
            SecurityEventOut(
                id=e.id,
                user_id=e.user_id,
                student_name=user.full_name if user else None,
                event_type=e.event_type,
                description=e.description,
                severity=e.severity.value,
                status=e.status.value,
                created_at=e.created_at,
                event_metadata=e.event_metadata or {},
            )
        )
    return results


def _event_in_scope_or_404(db: Session, professor_profile: ProfessorProfile, event_id: uuid.UUID) -> SecurityEvent:
    event = db.get(SecurityEvent, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Security event not found")
    owned_ids = _owned_class_division_ids(db, professor_profile)
    student_ids = set(_enrolled_student_ids(db, owned_ids))
    student_user_ids = {
        row[0] for row in db.query(StudentProfile.user_id).filter(StudentProfile.id.in_(student_ids)).all()
    }
    if event.user_id not in student_user_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Security event not found")
    return event


def flag_event(db: Session, professor_profile: ProfessorProfile, event_id: uuid.UUID) -> None:
    event = _event_in_scope_or_404(db, professor_profile, event_id)
    event.status = SecurityEventStatus.FLAGGED
    db.commit()


def dismiss_event(db: Session, professor_profile: ProfessorProfile, event_id: uuid.UUID) -> None:
    event = _event_in_scope_or_404(db, professor_profile, event_id)
    event.status = SecurityEventStatus.DISMISSED
    db.commit()


def cooldowns(db: Session, professor_profile: ProfessorProfile) -> list[CooldownListItem]:
    owned_ids = _owned_class_division_ids(db, professor_profile)
    student_ids = _enrolled_student_ids(db, owned_ids)
    if not student_ids:
        return []
    now = utcnow()
    active = (
        db.query(Cooldown)
        .filter(Cooldown.student_id.in_(student_ids), Cooldown.expires_at > now)
        .order_by(Cooldown.expires_at.desc())
        .all()
    )
    results = []
    for c in active:
        if ensure_utc(c.expires_at) <= now:
            continue
        student_profile = db.get(StudentProfile, c.student_id)
        user = db.get(User, student_profile.user_id)
        results.append(
            CooldownListItem(
                student_id=c.student_id,
                full_name=user.full_name,
                roll_number=student_profile.roll_number,
                expires_at=c.expires_at,
                remaining_seconds=max(int((ensure_utc(c.expires_at) - now).total_seconds()), 0),
                reason=c.reason,
            )
        )
    return results
