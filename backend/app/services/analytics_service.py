import math
import uuid

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.academic import Enrollment, Lecture
from app.models.attendance import AttendanceRecord, AttendanceStatus

PRESENT_LIKE = (AttendanceStatus.PRESENT, AttendanceStatus.LATE, AttendanceStatus.MANUAL)


def attendance_percentage(present: int, late: int, manual: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round((present + late + manual) / total * 100, 2)


def classes_can_miss(attended: int, total: int, required_pct: float) -> int:
    if required_pct <= 0:
        return 0
    k = math.floor(attended * 100 / required_pct) - total
    return max(k, 0)


def classes_needed_to_recover(attended: int, total: int, required_pct: float) -> int:
    if total == 0:
        return 0
    current_pct = attended / total * 100
    if current_pct >= required_pct:
        return 0
    if required_pct >= 100:
        # Can never reach 100% again if a single class has already been missed.
        return max(total - attended, 1) * 10_000 if attended < total else 0
    k = math.ceil((required_pct * total - 100 * attended) / (100 - required_pct))
    return max(k, 0)


def projected_after_attending_n(attended: int, total: int, n: int) -> float:
    denom = total + n
    if denom == 0:
        return 0.0
    return round((attended + n) / denom * 100, 2)


def projected_after_missing_n(attended: int, total: int, n: int) -> float:
    denom = total + n
    if denom == 0:
        return 0.0
    return round(attended / denom * 100, 2)


def _counts_for_lectures(db: Session, student_id: uuid.UUID, lecture_ids: list[uuid.UUID]) -> dict:
    present = late = manual = 0
    if lecture_ids:
        records = (
            db.query(AttendanceRecord)
            .filter(AttendanceRecord.student_id == student_id, AttendanceRecord.lecture_id.in_(lecture_ids))
            .all()
        )
        for r in records:
            if r.status == AttendanceStatus.PRESENT:
                present += 1
            elif r.status == AttendanceStatus.LATE:
                late += 1
            elif r.status == AttendanceStatus.MANUAL:
                manual += 1

    total = len(lecture_ids)
    # Absent = every lecture the student did not attend. A record whose status is ABSENT (a
    # professor's manual override) counts as absent too, not as "recorded".
    absent = total - (present + late + manual)
    return {"present": present, "late": late, "manual": manual, "absent": max(absent, 0), "total": total}


def subject_stats(
    db: Session, student_id: uuid.UUID, class_division_id: uuid.UUID, required_pct: float = 75.0
) -> dict:
    lectures = (
        db.query(Lecture)
        .filter(Lecture.class_division_id == class_division_id, Lecture.scheduled_start <= utcnow())
        .all()
    )
    lecture_ids = [l.id for l in lectures]
    counts = _counts_for_lectures(db, student_id, lecture_ids)
    attended = counts["present"] + counts["late"] + counts["manual"]
    pct = attendance_percentage(counts["present"], counts["late"], counts["manual"], counts["total"])
    return {
        "class_division_id": class_division_id,
        **counts,
        "percentage": pct,
        "classes_can_miss": classes_can_miss(attended, counts["total"], required_pct),
        "classes_needed_to_recover": classes_needed_to_recover(attended, counts["total"], required_pct),
    }


def batch_subject_stats(
    db: Session, student_ids: list[uuid.UUID], class_division_id: uuid.UUID, required_pct: float = 75.0
) -> dict[uuid.UUID, dict]:
    """Same output shape as subject_stats, for many students in one class division at once —
    one query for the lectures, one for all matching attendance records, instead of the
    N-queries-per-student pattern subject_stats has when called in a loop."""
    lectures = (
        db.query(Lecture)
        .filter(Lecture.class_division_id == class_division_id, Lecture.scheduled_start <= utcnow())
        .all()
    )
    lecture_ids = [l.id for l in lectures]
    total = len(lecture_ids)

    counts = {sid: {"present": 0, "late": 0, "manual": 0} for sid in student_ids}
    recorded_lectures = {sid: set() for sid in student_ids}

    if lecture_ids and student_ids:
        records = (
            db.query(AttendanceRecord)
            .filter(AttendanceRecord.student_id.in_(student_ids), AttendanceRecord.lecture_id.in_(lecture_ids))
            .all()
        )
        for r in records:
            if r.student_id not in counts:
                continue
            recorded_lectures[r.student_id].add(r.lecture_id)
            if r.status == AttendanceStatus.PRESENT:
                counts[r.student_id]["present"] += 1
            elif r.status == AttendanceStatus.LATE:
                counts[r.student_id]["late"] += 1
            elif r.status == AttendanceStatus.MANUAL:
                counts[r.student_id]["manual"] += 1

    result: dict[uuid.UUID, dict] = {}
    for sid in student_ids:
        c = counts[sid]
        attended = c["present"] + c["late"] + c["manual"]
        absent = max(total - attended, 0)
        pct = attendance_percentage(c["present"], c["late"], c["manual"], total)
        result[sid] = {
            "class_division_id": class_division_id,
            "present": c["present"],
            "late": c["late"],
            "manual": c["manual"],
            "absent": absent,
            "total": total,
            "percentage": pct,
            "classes_can_miss": classes_can_miss(attended, total, required_pct),
            "classes_needed_to_recover": classes_needed_to_recover(attended, total, required_pct),
        }
    return result


def batch_overall_stats(
    db: Session, student_ids: list[uuid.UUID], class_division_ids: list[uuid.UUID], required_pct: float = 75.0
) -> dict[uuid.UUID, dict]:
    """Same output shape as student_overall_stats, for many students across many class
    divisions at once — O(divisions) queries instead of O(students x divisions)."""
    totals = {sid: {"present": 0, "late": 0, "manual": 0, "absent": 0, "total": 0} for sid in student_ids}
    for cd_id in class_division_ids:
        per_division = batch_subject_stats(db, student_ids, cd_id, required_pct)
        for sid, s in per_division.items():
            for key in ("present", "late", "manual", "absent", "total"):
                totals[sid][key] += s[key]

    result: dict[uuid.UUID, dict] = {}
    for sid, t in totals.items():
        attended = t["present"] + t["late"] + t["manual"]
        pct = attendance_percentage(t["present"], t["late"], t["manual"], t["total"])
        result[sid] = {
            **t,
            "percentage": pct,
            "classes_can_miss": classes_can_miss(attended, t["total"], required_pct),
            "classes_needed_to_recover": classes_needed_to_recover(attended, t["total"], required_pct),
        }
    return result


def student_overall_stats(
    db: Session, student_id: uuid.UUID, required_pct: float = 75.0, class_division_ids: list[uuid.UUID] | None = None
) -> dict:
    if class_division_ids is None:
        class_division_ids = [
            e.class_division_id
            for e in db.query(Enrollment).filter(Enrollment.student_id == student_id).all()
        ]

    total_present = total_late = total_manual = total_absent = total_classes = 0
    for cd_id in class_division_ids:
        stats = subject_stats(db, student_id, cd_id, required_pct)
        total_present += stats["present"]
        total_late += stats["late"]
        total_manual += stats["manual"]
        total_absent += stats["absent"]
        total_classes += stats["total"]

    attended = total_present + total_late + total_manual
    pct = attendance_percentage(total_present, total_late, total_manual, total_classes)
    return {
        "present": total_present,
        "late": total_late,
        "manual": total_manual,
        "absent": total_absent,
        "total": total_classes,
        "percentage": pct,
        "classes_can_miss": classes_can_miss(attended, total_classes, required_pct),
        "classes_needed_to_recover": classes_needed_to_recover(attended, total_classes, required_pct),
    }
