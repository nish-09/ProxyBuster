import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user, get_professor_profile, get_student_profile
from app.core.rate_limit import limiter
from app.models.academic import ClassDivision, Enrollment, Lecture
from app.models.attendance import AttendanceRecord, AttendanceSession, AttendanceStatus, SessionStatus
from app.models.user import ProfessorProfile, StudentProfile
from app.schemas.attendance import (
    AttendanceSessionCreate,
    AttendanceSessionOut,
    LiveFeedEntry,
    LiveSessionState,
    ManualAttendanceOut,
    ManualAttendanceRequest,
    ScanRequest,
    ScanResult,
)
from app.services import attendance_service, realtime

router = APIRouter(prefix="/attendance", tags=["attendance"])

PRESENT_LIKE = (AttendanceStatus.PRESENT, AttendanceStatus.LATE, AttendanceStatus.MANUAL)


def _session_or_404(db: Session, session_id: uuid.UUID) -> AttendanceSession:
    session_obj = db.get(AttendanceSession, session_id)
    if session_obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return session_obj


def _counts(db: Session, session_obj: AttendanceSession) -> tuple[int, int]:
    lecture = db.get(Lecture, session_obj.lecture_id)
    class_division = db.get(ClassDivision, lecture.class_division_id)
    total_enrolled = (
        db.query(Enrollment).filter(Enrollment.class_division_id == class_division.id).count()
    )
    present_count = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.lecture_id == lecture.id, AttendanceRecord.status.in_(PRESENT_LIKE))
        .count()
    )
    return present_count, total_enrolled


@router.post("/sessions", response_model=AttendanceSessionOut, status_code=201)
@limiter.limit("20/minute")
async def start_session(
    payload: AttendanceSessionCreate,
    request: Request,
    professor_profile: ProfessorProfile = Depends(get_professor_profile),
    db: Session = Depends(get_db),
):
    session_obj = attendance_service.create_session(db, professor_profile, payload.lecture_id)
    realtime.start_rotation(session_obj.id)
    return session_obj


@router.get("/sessions/{session_id}", response_model=AttendanceSessionOut)
def get_session(
    session_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return attendance_service.authorize_session_access(db, session_id, current.user)


@router.post("/sessions/{session_id}/close", response_model=AttendanceSessionOut)
async def close_session(
    session_id: uuid.UUID,
    professor_profile: ProfessorProfile = Depends(get_professor_profile),
    db: Session = Depends(get_db),
):
    session_obj = attendance_service.close_session(db, professor_profile, session_id)
    realtime.stop_rotation(session_id)
    await realtime.manager.broadcast(str(session_id), {"type": "closed"})
    return session_obj


@router.get("/sessions/{session_id}/live", response_model=LiveSessionState)
def live_session(
    session_id: uuid.UUID,
    professor_profile: ProfessorProfile = Depends(get_professor_profile),
    db: Session = Depends(get_db),
):
    session_obj = _session_or_404(db, session_id)
    lecture = db.get(Lecture, session_obj.lecture_id)
    class_division = db.get(ClassDivision, lecture.class_division_id)
    if class_division.professor_id != professor_profile.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not own this session")

    present_count, total_enrolled = _counts(db, session_obj)

    qr_payload = None
    current_token_expires_at = None
    if session_obj.status == SessionStatus.ACTIVE:
        token = attendance_service.get_or_issue_current_token(db, session_obj)
        qr_payload = attendance_service.encode_qr_payload(token)
        current_token_expires_at = token.expires_at

    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.lecture_id == lecture.id)
        .order_by(AttendanceRecord.marked_at.desc())
        .limit(20)
        .all()
    )
    feed = []
    for record in records:
        student_profile = db.get(StudentProfile, record.student_id)
        feed.append(
            LiveFeedEntry(
                id=record.id,
                student_name=student_profile.user.full_name if student_profile else "Unknown",
                roll_number=student_profile.roll_number if student_profile else "",
                status=record.status,
                marked_at=record.marked_at,
            )
        )

    return LiveSessionState(
        session_id=session_obj.id,
        status=session_obj.status,
        present_count=present_count,
        total_enrolled=total_enrolled,
        current_token_expires_at=current_token_expires_at,
        qr_payload=qr_payload,
        feed=feed,
    )


@router.post("/scan", response_model=ScanResult)
@limiter.limit("20/minute")
async def scan_qr(
    payload: ScanRequest,
    request: Request,
    student_profile: StudentProfile = Depends(get_student_profile),
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else None
    record, class_division_id = attendance_service.scan(db, student_profile, payload.token, ip)

    present_count, total_enrolled = _counts(db, db.get(AttendanceSession, record.session_id))
    await realtime.manager.broadcast(
        str(record.session_id),
        {
            "type": "checkin",
            "student_name": student_profile.user.full_name,
            "roll_number": student_profile.roll_number,
            "status": record.status.value,
            "marked_at": record.marked_at.isoformat(),
            "present_count": present_count,
            "total_enrolled": total_enrolled,
        },
    )

    return ScanResult(status="marked", attendance_status=record.status.value, message="Attendance marked")


@router.post("/manual", response_model=ManualAttendanceOut)
@limiter.limit("30/minute")
async def manual_attendance(
    payload: ManualAttendanceRequest,
    request: Request,
    professor_profile: ProfessorProfile = Depends(get_professor_profile),
    db: Session = Depends(get_db),
):
    audit = attendance_service.manual_mark(db, professor_profile, payload)

    active_session = (
        db.query(AttendanceSession)
        .filter(AttendanceSession.lecture_id == payload.lecture_id, AttendanceSession.status == SessionStatus.ACTIVE)
        .first()
    )
    if active_session:
        present_count, total_enrolled = _counts(db, active_session)
        await realtime.manager.broadcast(
            str(active_session.id),
            {
                "type": "manual",
                "new_status": audit.new_status,
                "present_count": present_count,
                "total_enrolled": total_enrolled,
            },
        )

    return audit
