import uuid
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_student_profile
from app.core.time import ensure_utc, utcnow
from app.models.academic import ClassDivision, Enrollment, Lecture, Subject
from app.models.security import DeviceSession
from app.models.user import ProfessorProfile, StudentProfile, User
from app.schemas.attendance import ManualAttendanceOut  # noqa: F401  (re-exported for potential client typing)
from app.schemas.student import (
    AttendanceHistoryEntry,
    AttendanceHistoryOut,
    BunkCalculatorOut,
    BunkCalculatorRequest,
    CooldownStatusOut,
    DeviceSessionOut,
    LastScanOut,
    RestrictionStatusOut,
    StudentDashboardOut,
    SubjectAttendanceOut,
    TodayScheduleItem,
)
from app.services import analytics_service, violation_service
from app.services.cooldown_service import get_active_cooldown

router = APIRouter(prefix="/students", tags=["students"])

REQUIRED_PCT_DEFAULT = 75.0


def _enrollment_or_404(db: Session, student_profile: StudentProfile, class_division_id: uuid.UUID) -> Enrollment:
    enrollment = (
        db.query(Enrollment)
        .filter(Enrollment.student_id == student_profile.id, Enrollment.class_division_id == class_division_id)
        .first()
    )
    if enrollment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not enrolled in this class")
    return enrollment


@router.get("/me")
def get_me(student_profile: StudentProfile = Depends(get_student_profile), db: Session = Depends(get_db)):
    user = db.get(User, student_profile.user_id)
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "roll_number": student_profile.roll_number,
        "program": student_profile.program,
        "semester": student_profile.semester,
    }


@router.get("/me/dashboard", response_model=StudentDashboardOut)
def dashboard(student_profile: StudentProfile = Depends(get_student_profile), db: Session = Depends(get_db)):
    user = db.get(User, student_profile.user_id)
    enrollments = db.query(Enrollment).filter(Enrollment.student_id == student_profile.id).all()
    class_division_ids = [e.class_division_id for e in enrollments]

    class_divisions_by_id = {
        cd.id: cd for cd in db.query(ClassDivision).filter(ClassDivision.id.in_(class_division_ids)).all()
    } if class_division_ids else {}
    subject_ids = [cd.subject_id for cd in class_divisions_by_id.values()]
    subjects_by_id = {s.id: s for s in db.query(Subject).filter(Subject.id.in_(subject_ids)).all()} if subject_ids else {}
    stats_by_division = (
        {
            cd_id: analytics_service.batch_subject_stats(db, [student_profile.id], cd_id, REQUIRED_PCT_DEFAULT)[
                student_profile.id
            ]
            for cd_id in class_division_ids
        }
    )
    next_lecture_by_division: dict[uuid.UUID, Lecture] = {}
    if class_division_ids:
        upcoming = (
            db.query(Lecture)
            .filter(Lecture.class_division_id.in_(class_division_ids), Lecture.scheduled_start > utcnow())
            .order_by(Lecture.scheduled_start.asc())
            .all()
        )
        for lecture in upcoming:
            next_lecture_by_division.setdefault(lecture.class_division_id, lecture)

    subjects: list[SubjectAttendanceOut] = []
    for enrollment in enrollments:
        class_division = class_divisions_by_id[enrollment.class_division_id]
        subject = subjects_by_id[class_division.subject_id]
        stats = stats_by_division[class_division.id]
        next_lecture = next_lecture_by_division.get(class_division.id)
        subjects.append(
            SubjectAttendanceOut(
                class_division_id=class_division.id,
                subject_code=subject.code,
                subject_name=subject.name,
                division_name=class_division.name,
                present=stats["present"],
                late=stats["late"],
                manual=stats["manual"],
                absent=stats["absent"],
                total=stats["total"],
                percentage=stats["percentage"],
                classes_can_miss=stats["classes_can_miss"],
                classes_needed_to_recover=stats["classes_needed_to_recover"],
                next_class_at=next_lecture.scheduled_start if next_lecture else None,
            )
        )

    # Aggregate overall stats from the per-division stats already computed for `subjects`
    # above, instead of a second independent pass (student_overall_stats would otherwise
    # re-query lectures/records per division a second time).
    overall_totals = {"present": 0, "late": 0, "manual": 0, "absent": 0, "total": 0}
    for s in stats_by_division.values():
        for key in overall_totals:
            overall_totals[key] += s[key]
    overall = {
        **overall_totals,
        "percentage": analytics_service.attendance_percentage(
            overall_totals["present"], overall_totals["late"], overall_totals["manual"], overall_totals["total"]
        ),
    }
    attended = overall["present"] + overall["late"] + overall["manual"]

    now = utcnow()
    day_start = datetime.combine(now.date(), time.min, tzinfo=now.tzinfo)
    day_end = day_start + timedelta(days=1)
    today_lectures = (
        db.query(Lecture)
        .filter(
            Lecture.class_division_id.in_(class_division_ids),
            Lecture.scheduled_start >= day_start,
            Lecture.scheduled_start < day_end,
        )
        .order_by(Lecture.scheduled_start.asc())
        .all()
        if class_division_ids
        else []
    )
    today_schedule = []
    for lecture in today_lectures:
        class_division = class_divisions_by_id[lecture.class_division_id]
        subject = subjects_by_id[class_division.subject_id]
        start = ensure_utc(lecture.scheduled_start)
        end = ensure_utc(lecture.scheduled_end)
        if now < start:
            state = "upcoming"
        elif now > end:
            state = "past"
        else:
            state = "current"
        today_schedule.append(
            TodayScheduleItem(
                class_division_id=class_division.id,
                subject_name=subject.name,
                room=lecture.room,
                scheduled_start=lecture.scheduled_start,
                scheduled_end=lecture.scheduled_end,
                state=state,
            )
        )

    return StudentDashboardOut(
        full_name=user.full_name,
        roll_number=student_profile.roll_number,
        program=student_profile.program,
        semester=student_profile.semester,
        overall_percentage=overall["percentage"],
        total_classes=overall["total"],
        attended_classes=attended,
        standing="good" if overall["percentage"] >= REQUIRED_PCT_DEFAULT else "warning",
        subjects=subjects,
        today_schedule=today_schedule,
    )


@router.get("/me/attendance", response_model=AttendanceHistoryOut)
def attendance_history(
    subject_id: uuid.UUID | None = Query(default=None, description="class_division_id to filter by"),
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    student_profile: StudentProfile = Depends(get_student_profile),
    db: Session = Depends(get_db),
):
    enrollments = db.query(Enrollment).filter(Enrollment.student_id == student_profile.id).all()
    class_division_ids = [e.class_division_id for e in enrollments]
    if subject_id is not None:
        if subject_id not in class_division_ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not enrolled in this class")
        class_division_ids = [subject_id]

    if not class_division_ids:
        return AttendanceHistoryOut(entries=[], present=0, absent=0, late=0, manual=0, total=0, percentage=0.0)

    lecture_query = db.query(Lecture).filter(Lecture.class_division_id.in_(class_division_ids))
    if from_date:
        lecture_query = lecture_query.filter(Lecture.scheduled_start >= datetime.combine(from_date, time.min))
    if to_date:
        lecture_query = lecture_query.filter(Lecture.scheduled_start <= datetime.combine(to_date, time.max))
    lecture_query = lecture_query.filter(Lecture.scheduled_start <= utcnow())
    lectures = lecture_query.order_by(Lecture.scheduled_start.desc()).all()
    lecture_by_id = {l.id: l for l in lectures}
    lecture_ids = list(lecture_by_id.keys())

    from app.models.attendance import AttendanceRecord

    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.student_id == student_profile.id, AttendanceRecord.lecture_id.in_(lecture_ids))
        .all()
        if lecture_ids
        else []
    )
    record_by_lecture = {r.lecture_id: r for r in records}

    # class_division_ids is small and bounded (the student's own enrollments) — batch these
    # lookups once instead of 4 db.get() calls per lecture row in the loop below.
    class_divisions_by_id = {
        cd.id: cd for cd in db.query(ClassDivision).filter(ClassDivision.id.in_(class_division_ids)).all()
    }
    subjects_by_id = {
        s.id: s for s in db.query(Subject).filter(Subject.id.in_([cd.subject_id for cd in class_divisions_by_id.values()])).all()
    }
    professor_profiles_by_id = {
        p.id: p
        for p in db.query(ProfessorProfile)
        .filter(ProfessorProfile.id.in_([cd.professor_id for cd in class_divisions_by_id.values()]))
        .all()
    }
    professor_users_by_id = {
        u.id: u
        for u in db.query(User).filter(User.id.in_([p.user_id for p in professor_profiles_by_id.values()])).all()
    }

    present = late = manual = 0
    entries: list[AttendanceHistoryEntry] = []
    for lecture in lectures[offset : offset + limit]:
        class_division = class_divisions_by_id[lecture.class_division_id]
        subject = subjects_by_id[class_division.subject_id]
        professor_profile = professor_profiles_by_id.get(class_division.professor_id)
        professor_user = professor_users_by_id.get(professor_profile.user_id) if professor_profile else None
        record = record_by_lecture.get(lecture.id)
        entries.append(
            AttendanceHistoryEntry(
                id=record.id if record else uuid.uuid4(),
                lecture_id=lecture.id,
                subject_name=subject.name,
                professor_name=professor_user.full_name if professor_user else "Unknown",
                status=record.status.value if record else "absent",
                method=record.method.value if record else "-",
                marked_at=record.marked_at if record else None,
                scheduled_start=lecture.scheduled_start,
            )
        )

    for lecture in lectures:
        record = record_by_lecture.get(lecture.id)
        if record is None:
            continue
        if record.status.value == "present":
            present += 1
        elif record.status.value == "late":
            late += 1
        elif record.status.value == "manual":
            manual += 1

    total = len(lectures)
    absent = total - (present + late + manual)
    percentage = analytics_service.attendance_percentage(present, late, manual, total)

    return AttendanceHistoryOut(
        entries=entries, present=present, absent=max(absent, 0), late=late, manual=manual, total=total, percentage=percentage
    )


@router.get("/me/attendance/{subject_id}", response_model=SubjectAttendanceOut)
def subject_attendance(
    subject_id: uuid.UUID,
    student_profile: StudentProfile = Depends(get_student_profile),
    db: Session = Depends(get_db),
):
    _enrollment_or_404(db, student_profile, subject_id)
    class_division = db.get(ClassDivision, subject_id)
    subject = db.get(Subject, class_division.subject_id)
    stats = analytics_service.subject_stats(db, student_profile.id, subject_id, REQUIRED_PCT_DEFAULT)
    next_lecture = (
        db.query(Lecture)
        .filter(Lecture.class_division_id == subject_id, Lecture.scheduled_start > utcnow())
        .order_by(Lecture.scheduled_start.asc())
        .first()
    )
    return SubjectAttendanceOut(
        class_division_id=subject_id,
        subject_code=subject.code,
        subject_name=subject.name,
        division_name=class_division.name,
        next_class_at=next_lecture.scheduled_start if next_lecture else None,
        **stats,
    )


@router.get("/me/cooldown", response_model=CooldownStatusOut)
def cooldown_status(student_profile: StudentProfile = Depends(get_student_profile), db: Session = Depends(get_db)):
    cooldown = get_active_cooldown(db, student_profile.id)
    if cooldown is None:
        return CooldownStatusOut(active=False, remaining_seconds=0, expires_at=None)
    remaining = int((ensure_utc(cooldown.expires_at) - utcnow()).total_seconds())
    return CooldownStatusOut(
        active=True, remaining_seconds=max(remaining, 0), expires_at=cooldown.expires_at, reason=cooldown.reason
    )


@router.get("/me/restriction", response_model=RestrictionStatusOut)
def restriction_status(student_profile: StudentProfile = Depends(get_student_profile), db: Session = Depends(get_db)):
    """Lets the scan page redirect away before even opening the camera, the same way it already
    does for a cooldown — the backend scan() check (app/services/attendance_service.py) is the
    actual enforcement point either way."""
    restriction = violation_service.get_active_restriction(db, student_profile.id)
    if restriction is None:
        return RestrictionStatusOut(active=False)
    return RestrictionStatusOut(active=True, valid_until=restriction.restriction_end, reason=restriction.reason.value)


# How long after a QR check-in the success screen keeps showing that result on refresh.
LAST_SCAN_WINDOW = timedelta(hours=6)


@router.get("/me/last-scan", response_model=LastScanOut)
def last_scan(student_profile: StudentProfile = Depends(get_student_profile), db: Session = Depends(get_db)):
    from app.models.attendance import AttendanceMethod, AttendanceRecord

    now = utcnow()
    row = (
        db.query(AttendanceRecord, Lecture, ClassDivision, Subject)
        .join(Lecture, Lecture.id == AttendanceRecord.lecture_id)
        .join(ClassDivision, ClassDivision.id == Lecture.class_division_id)
        .join(Subject, Subject.id == ClassDivision.subject_id)
        .filter(AttendanceRecord.student_id == student_profile.id, AttendanceRecord.method == AttendanceMethod.QR)
        .order_by(AttendanceRecord.marked_at.desc())
        .first()
    )
    if row is None or now - ensure_utc(row[0].marked_at) > LAST_SCAN_WINDOW:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No recent attendance found")
    record, lecture, class_division, subject = row

    cooldown = get_active_cooldown(db, student_profile.id)
    remaining = max(int((ensure_utc(cooldown.expires_at) - now).total_seconds()), 0) if cooldown else 0
    return LastScanOut(
        attendance_status=record.status.value,
        subject_code=subject.code,
        subject_name=subject.name,
        division_name=class_division.name,
        session_topic=lecture.topic,
        marked_at=record.marked_at,
        server_time=now,
        cooldown_active=cooldown is not None,
        cooldown_remaining_seconds=remaining,
        cooldown_expires_at=cooldown.expires_at if cooldown else None,
    )


@router.get("/me/sessions", response_model=list[DeviceSessionOut])
def my_sessions(student_profile: StudentProfile = Depends(get_student_profile), db: Session = Depends(get_db)):
    sessions = (
        db.query(DeviceSession)
        .filter(DeviceSession.user_id == student_profile.user_id)
        .order_by(DeviceSession.login_at.desc())
        .limit(10)
        .all()
    )
    return [
        DeviceSessionOut(
            device_id=s.device_id,
            ip_address=s.ip_address,
            user_agent=s.user_agent,
            login_at=s.login_at,
            logout_at=s.logout_at,
            status=s.status.value,
        )
        for s in sessions
    ]


@router.post("/me/bunk-calculator", response_model=BunkCalculatorOut)
def bunk_calculator(
    payload: BunkCalculatorRequest,
    student_profile: StudentProfile = Depends(get_student_profile),
    db: Session = Depends(get_db),
):
    _enrollment_or_404(db, student_profile, payload.class_division_id)
    stats = analytics_service.subject_stats(db, student_profile.id, payload.class_division_id, payload.required_pct)
    attended = stats["present"] + stats["late"] + stats["manual"]
    return BunkCalculatorOut(
        current_percentage=stats["percentage"],
        classes_can_miss=stats["classes_can_miss"],
        classes_needed_to_recover=stats["classes_needed_to_recover"],
        projected_after_attending_1=analytics_service.projected_after_attending_n(attended, stats["total"], 1),
        projected_after_missing_1=analytics_service.projected_after_missing_n(attended, stats["total"], 1),
    )
