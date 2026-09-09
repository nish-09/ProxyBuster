import statistics
import uuid
from collections import defaultdict
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.time import ensure_utc, utcnow
from app.models.academic import Lecture
from app.models.attendance import AttendanceRecord
from app.models.security import AnomalyScore, DeviceSession, DeviceSessionStatus, SecurityEvent
from app.models.user import StudentProfile

SYNC_WINDOW_SECONDS = 5
SYNC_MIN_OCCURRENCES = 3


def find_synchronized_pairs(
    db: Session,
    class_division_id: uuid.UUID | None = None,
    window_seconds: int = SYNC_WINDOW_SECONDS,
    min_occurrences: int = SYNC_MIN_OCCURRENCES,
) -> list[dict]:
    """Detect students who repeatedly check in within `window_seconds` of each other
    across many lectures — a signal of proxy/shared-device attendance, not proof of it."""
    lecture_query = db.query(Lecture.id)
    if class_division_id is not None:
        lecture_query = lecture_query.filter(Lecture.class_division_id == class_division_id)
    lecture_ids = [row[0] for row in lecture_query.all()]
    if not lecture_ids:
        return []

    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.lecture_id.in_(lecture_ids), AttendanceRecord.marked_at.isnot(None))
        .order_by(AttendanceRecord.lecture_id, AttendanceRecord.marked_at.asc())
        .all()
    )

    by_lecture: dict[uuid.UUID, list[AttendanceRecord]] = defaultdict(list)
    for r in records:
        by_lecture[r.lecture_id].append(r)

    pair_counts: dict[tuple[uuid.UUID, uuid.UUID], int] = defaultdict(int)
    for lecture_records in by_lecture.values():
        cluster: list[AttendanceRecord] = []
        for record in lecture_records:
            if cluster and (ensure_utc(record.marked_at) - ensure_utc(cluster[-1].marked_at)).total_seconds() > window_seconds:
                _tally_cluster(cluster, pair_counts)
                cluster = []
            cluster.append(record)
        _tally_cluster(cluster, pair_counts)

    pairs = []
    for (a, b), count in pair_counts.items():
        if count >= min_occurrences:
            pairs.append(
                {
                    "student_a": a,
                    "student_b": b,
                    "sync_count": count,
                    "risk": "high" if count >= 6 else "medium",
                }
            )
    return pairs


def _tally_cluster(cluster: list[AttendanceRecord], pair_counts: dict) -> None:
    if len(cluster) < 2:
        return
    student_ids = sorted({r.student_id for r in cluster}, key=str)
    for i in range(len(student_ids)):
        for j in range(i + 1, len(student_ids)):
            pair_counts[(student_ids[i], student_ids[j])] += 1


def build_feature_vector(db: Session, student_id: uuid.UUID) -> list[float]:
    """Shared feature builder used by both the rule-based scorer and the ML model."""
    student_profile = db.get(StudentProfile, student_id)
    user_id = student_profile.user_id if student_profile else None

    since_30d = utcnow() - timedelta(days=30)
    since_7d = utcnow() - timedelta(days=7)

    device_change_count_30d = 0
    logout_login_count_7d = 0
    concurrent_login_events_30d = 0

    if user_id is not None:
        device_change_count_30d = (
            db.query(DeviceSession).filter(DeviceSession.user_id == user_id, DeviceSession.login_at >= since_30d).count()
        )
        logout_login_count_7d = (
            db.query(DeviceSession)
            .filter(
                DeviceSession.user_id == user_id,
                DeviceSession.status == DeviceSessionStatus.LOGGED_OUT,
                DeviceSession.login_at >= since_7d,
            )
            .count()
        )
        concurrent_login_events_30d = (
            db.query(SecurityEvent)
            .filter(
                SecurityEvent.user_id == user_id,
                SecurityEvent.event_type == "concurrent_login",
                SecurityEvent.created_at >= since_30d,
            )
            .count()
        )

    timing_deviation_std = _timing_deviation_std(db, student_id)
    sync_pairs = find_synchronized_pairs(db)
    sync_pair_max_count = max(
        (p["sync_count"] for p in sync_pairs if student_id in (p["student_a"], p["student_b"])), default=0
    )

    return [
        float(device_change_count_30d),
        float(logout_login_count_7d),
        float(concurrent_login_events_30d),
        float(timing_deviation_std),
        float(sync_pair_max_count),
    ]


def _timing_deltas(db: Session, student_id: uuid.UUID) -> list[float]:
    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.student_id == student_id, AttendanceRecord.marked_at.isnot(None))
        .order_by(AttendanceRecord.marked_at.desc())
        .limit(20)
        .all()
    )
    deltas = []
    for r in records:
        lecture = db.get(Lecture, r.lecture_id)
        if lecture is None:
            continue
        deltas.append((ensure_utc(r.marked_at) - ensure_utc(lecture.scheduled_start)).total_seconds())
    return deltas


def _timing_deviation_std(db: Session, student_id: uuid.UUID) -> float:
    deltas = _timing_deltas(db, student_id)
    if len(deltas) < 2:
        return 0.0
    return statistics.pstdev(deltas)


def compute_rule_based_score(db: Session, student_id: uuid.UUID) -> tuple[float, list[str]]:
    history_count = db.query(AttendanceRecord).filter(AttendanceRecord.student_id == student_id).count()
    if history_count < 3:
        return 0.0, ["Insufficient history for scoring"]

    student_profile = db.get(StudentProfile, student_id)
    user_id = student_profile.user_id if student_profile else None

    since_30d = utcnow() - timedelta(days=30)
    since_7d = utcnow() - timedelta(days=7)

    score = 0.0
    reasons: list[str] = []

    if user_id is not None:
        device_count = (
            db.query(DeviceSession).filter(DeviceSession.user_id == user_id, DeviceSession.login_at >= since_30d).count()
        )
        if device_count > 5:
            score += 15
            reasons.append("Frequent device/session changes")

        logout_count = (
            db.query(DeviceSession)
            .filter(
                DeviceSession.user_id == user_id,
                DeviceSession.status == DeviceSessionStatus.LOGGED_OUT,
                DeviceSession.login_at >= since_7d,
            )
            .count()
        )
        if logout_count > 3:
            score += 15
            reasons.append("Repeated logout/login pattern")

        concurrent_events = (
            db.query(SecurityEvent)
            .filter(
                SecurityEvent.user_id == user_id,
                SecurityEvent.event_type == "concurrent_login",
                SecurityEvent.created_at >= since_30d,
            )
            .count()
        )
        if concurrent_events > 0:
            score += min(concurrent_events * 10, 30)
            reasons.append("Multiple concurrent-login security events")

    deltas = _timing_deltas(db, student_id)
    if len(deltas) >= 5:
        history, latest = deltas[1:], deltas[0]
        mean = statistics.mean(history)
        std = statistics.pstdev(history)
        if std > 0 and abs(latest - mean) > 2 * std:
            score += 20
            reasons.append("Attendance marked at an unusual time relative to this student's own history")

    sync_pairs = find_synchronized_pairs(db)
    my_pairs = [p for p in sync_pairs if student_id in (p["student_a"], p["student_b"])]
    if my_pairs:
        top = max(my_pairs, key=lambda p: p["sync_count"])
        other_id = top["student_b"] if top["student_a"] == student_id else top["student_a"]
        other_profile = db.get(StudentProfile, other_id)
        other_name = other_profile.roll_number if other_profile else str(other_id)
        score += 25
        reasons.append(f"Synchronized attendance with {other_name} ({top['sync_count']} sessions, {top['risk']} risk)")

    return min(score, 100.0), reasons or ["No significant anomaly signals detected"]


def compute_and_store(db: Session, student_id: uuid.UUID) -> AnomalyScore:
    score, reasons = compute_rule_based_score(db, student_id)
    anomaly = AnomalyScore(student_id=student_id, score=score, reasons=reasons, method="rule_based")
    db.add(anomaly)
    db.commit()
    db.refresh(anomaly)
    return anomaly


def get_or_recompute(db: Session, student_id: uuid.UUID, max_age_minutes: int = 5) -> AnomalyScore:
    """Avoid recomputing (and re-inserting) on every dashboard poll: reuse a recent score."""
    latest = (
        db.query(AnomalyScore)
        .filter(AnomalyScore.student_id == student_id)
        .order_by(AnomalyScore.computed_at.desc())
        .first()
    )
    if latest is not None and (utcnow() - ensure_utc(latest.computed_at)) < timedelta(minutes=max_age_minutes):
        return latest
    return compute_and_store(db, student_id)
