"""Rule-based scoring (app.services.anomaly_service) is the default and always available.

This module only activates once there's enough real history to fit a meaningful model —
it never fabricates a confidence score from insufficient data. Below the thresholds it
returns an empty list and callers fall back to rule-based scoring only.
"""
import uuid

from sqlalchemy.orm import Session

from app.models.attendance import AttendanceRecord
from app.models.user import StudentProfile
from app.services.anomaly_service import build_feature_vector

MIN_STUDENTS = 30
MIN_RECORDS_PER_STUDENT = 5


def _eligible_student_ids(db: Session) -> list[uuid.UUID]:
    student_ids = [row[0] for row in db.query(StudentProfile.id).all()]
    eligible = []
    for sid in student_ids:
        count = db.query(AttendanceRecord).filter(AttendanceRecord.student_id == sid).count()
        if count >= MIN_RECORDS_PER_STUDENT:
            eligible.append(sid)
    return eligible


def compute_ml_scores(db: Session, class_division_id: uuid.UUID | None = None) -> list[dict]:
    eligible = _eligible_student_ids(db)
    if len(eligible) < MIN_STUDENTS:
        return []

    from sklearn.ensemble import IsolationForest  # local import: optional heavy dependency

    features = [build_feature_vector(db, sid) for sid in eligible]

    model = IsolationForest(contamination="auto", random_state=42)
    model.fit(features)
    raw_scores = model.decision_function(features)  # higher = more normal

    lo, hi = min(raw_scores), max(raw_scores)
    span = hi - lo or 1.0

    results = []
    for sid, raw in zip(eligible, raw_scores):
        # Invert + normalize so 0 = normal, 100 = most anomalous, matching rule-based scale.
        normalized = (hi - raw) / span * 100
        results.append({"student_id": sid, "score": round(float(normalized), 2), "method": "ml"})
    return results
