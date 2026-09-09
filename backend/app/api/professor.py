import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_professor_profile
from app.models.user import ProfessorProfile, StudentProfile, User
from app.schemas.professor import (
    AnomalyScoreOut,
    AttendanceSheetOut,
    CooldownListItem,
    ProfessorDashboardOut,
    SecurityEventOut,
    StudentDetailOut,
    StudentListOut,
)
from app.services import anomaly_service, professor_service

router = APIRouter(prefix="/professor", tags=["professor"])


@router.get("/dashboard", response_model=ProfessorDashboardOut)
def get_dashboard(professor_profile: ProfessorProfile = Depends(get_professor_profile), db: Session = Depends(get_db)):
    return professor_service.dashboard(db, professor_profile)


@router.get("/students", response_model=StudentListOut)
def get_students(
    q: str | None = None,
    class_division_id: uuid.UUID | None = None,
    min_pct: float | None = None,
    max_pct: float | None = None,
    sort: str | None = None,
    professor_profile: ProfessorProfile = Depends(get_professor_profile),
    db: Session = Depends(get_db),
):
    return professor_service.list_students(db, professor_profile, q, class_division_id, min_pct, max_pct, sort)


@router.get("/students/{student_id}", response_model=StudentDetailOut)
def get_student(
    student_id: uuid.UUID,
    professor_profile: ProfessorProfile = Depends(get_professor_profile),
    db: Session = Depends(get_db),
):
    return professor_service.student_detail(db, professor_profile, student_id)


@router.post("/students/{student_id}/force-logout", status_code=204)
def force_logout(
    student_id: uuid.UUID,
    professor_profile: ProfessorProfile = Depends(get_professor_profile),
    db: Session = Depends(get_db),
):
    professor_service.force_logout(db, professor_profile, student_id)
    return None


@router.get("/attendance-sheet", response_model=AttendanceSheetOut)
def get_attendance_sheet(
    class_division_id: uuid.UUID,
    date_from: date,
    date_to: date,
    professor_profile: ProfessorProfile = Depends(get_professor_profile),
    db: Session = Depends(get_db),
):
    return professor_service.attendance_sheet(db, professor_profile, class_division_id, date_from, date_to)


@router.get("/analytics", response_model=ProfessorDashboardOut)
def get_analytics(professor_profile: ProfessorProfile = Depends(get_professor_profile), db: Session = Depends(get_db)):
    # No separate "analytics" Stitch screen exists — professor_analytics_dashboard.code.html
    # and professor_dashboard_mobile.code.html both turned out to BE the professor dashboard.
    # This endpoint exists to satisfy the spec's API surface but intentionally returns the
    # same aggregate the dashboard page already renders, rather than inventing new UI/data.
    return professor_service.dashboard(db, professor_profile)


@router.get("/security", response_model=list[SecurityEventOut])
def get_security_events(
    status: str | None = None,
    severity: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    professor_profile: ProfessorProfile = Depends(get_professor_profile),
    db: Session = Depends(get_db),
):
    return professor_service.security_events(db, professor_profile, status, severity, limit)


@router.post("/security/{event_id}/flag", status_code=204)
def flag_security_event(
    event_id: uuid.UUID,
    professor_profile: ProfessorProfile = Depends(get_professor_profile),
    db: Session = Depends(get_db),
):
    professor_service.flag_event(db, professor_profile, event_id)
    return None


@router.post("/security/{event_id}/dismiss", status_code=204)
def dismiss_security_event(
    event_id: uuid.UUID,
    professor_profile: ProfessorProfile = Depends(get_professor_profile),
    db: Session = Depends(get_db),
):
    professor_service.dismiss_event(db, professor_profile, event_id)
    return None


@router.get("/cooldowns", response_model=list[CooldownListItem])
def get_cooldowns(professor_profile: ProfessorProfile = Depends(get_professor_profile), db: Session = Depends(get_db)):
    return professor_service.cooldowns(db, professor_profile)


@router.get("/anomaly-scores", response_model=list[AnomalyScoreOut])
def get_anomaly_scores(
    class_division_id: uuid.UUID | None = None,
    professor_profile: ProfessorProfile = Depends(get_professor_profile),
    db: Session = Depends(get_db),
):
    owned_ids = professor_service.owned_class_division_ids(db, professor_profile)
    scope_ids = [class_division_id] if class_division_id else owned_ids
    if class_division_id and class_division_id not in owned_ids:
        scope_ids = []
    student_ids = professor_service.enrolled_student_ids(db, scope_ids)

    results = []
    for sid in student_ids:
        anomaly = anomaly_service.get_or_recompute(db, sid)
        student_profile = db.get(StudentProfile, sid)
        user = db.get(User, student_profile.user_id)
        results.append(
            AnomalyScoreOut(
                student_id=sid,
                full_name=user.full_name,
                roll_number=student_profile.roll_number,
                score=float(anomaly.score),
                reasons=anomaly.reasons or [],
                method=anomaly.method,
                computed_at=anomaly.computed_at,
            )
        )
    return results
