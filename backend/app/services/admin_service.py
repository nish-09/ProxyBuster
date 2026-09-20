import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.core.time import utcnow
from app.models.academic import ClassDivision, Enrollment, Lecture, Subject
from app.models.attendance import AttendanceRecord, AttendanceSession
from app.models.security import DeviceSession, DeviceSessionStatus
from app.models.user import ProfessorProfile, StudentProfile, User, UserRole
from app.schemas.admin import (
    AdminBulkEnrollResult,
    AdminCreateDivisionRequest,
    AdminCreateEnrollmentRequest,
    AdminCreateLectureRequest,
    AdminCreateProfessorRequest,
    AdminCreateStudentRequest,
    AdminCreateSubjectRequest,
    AdminDivisionOut,
    AdminEnrollmentOut,
    AdminLectureOut,
    AdminProfessorOut,
    AdminStudentOut,
    AdminSubjectOut,
    AdminSummaryOut,
    AdminUpdateDivisionRequest,
    AdminUpdateLectureRequest,
    AdminUpdateProfessorRequest,
    AdminUpdateStudentRequest,
    AdminUpdateSubjectRequest,
)

def _reset_password(db: Session, user: User, new_password: str) -> None:
    """Sets a new password and revokes every active session so the old credential stops working
    everywhere immediately."""
    user.password_hash = hash_password(new_password)
    now = utcnow()
    for device_session in (
        db.query(DeviceSession)
        .filter(DeviceSession.user_id == user.id, DeviceSession.status == DeviceSessionStatus.ACTIVE)
        .all()
    ):
        device_session.status = DeviceSessionStatus.REVOKED
        device_session.logout_at = now


# ============================= Students =============================


def create_student(db: Session, payload: AdminCreateStudentRequest) -> AdminStudentOut:
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.STUDENT,
    )
    db.add(user)
    db.flush()

    profile = StudentProfile(
        user_id=user.id, roll_number=payload.roll_number, program=payload.program, semester=payload.semester
    )
    db.add(profile)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Roll number already in use") from exc
    db.refresh(profile)
    return _student_out(db, profile)


def _student_out(db: Session, profile: StudentProfile) -> AdminStudentOut:
    user = db.get(User, profile.user_id)
    return AdminStudentOut(
        id=profile.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        roll_number=profile.roll_number,
        program=profile.program,
        semester=profile.semester,
        created_at=user.created_at,
    )


def list_students(db: Session, q: str | None = None, limit: int = 100, offset: int = 0) -> list[AdminStudentOut]:
    query = db.query(StudentProfile).join(User, StudentProfile.user_id == User.id)
    if q:
        needle = f"%{q.lower()}%"
        query = query.filter(func.lower(User.full_name).like(needle) | func.lower(StudentProfile.roll_number).like(needle))
    profiles = query.order_by(User.full_name.asc()).offset(offset).limit(limit).all()

    # Batch the User lookup instead of one db.get() per row (was N+1 — up to `limit` extra
    # round trips on a list endpoint the admin UI calls on every page load).
    users_by_id = {u.id: u for u in db.query(User).filter(User.id.in_([p.user_id for p in profiles])).all()}
    return [
        AdminStudentOut(
            id=p.id,
            user_id=p.user_id,
            email=users_by_id[p.user_id].email,
            full_name=users_by_id[p.user_id].full_name,
            is_active=users_by_id[p.user_id].is_active,
            roll_number=p.roll_number,
            program=p.program,
            semester=p.semester,
            created_at=users_by_id[p.user_id].created_at,
        )
        for p in profiles
    ]


def _student_or_404(db: Session, student_id: uuid.UUID) -> StudentProfile:
    profile = db.get(StudentProfile, student_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")
    return profile


def update_student(db: Session, student_id: uuid.UUID, payload: AdminUpdateStudentRequest) -> AdminStudentOut:
    profile = _student_or_404(db, student_id)
    user = db.get(User, profile.user_id)
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.program is not None:
        profile.program = payload.program
    if payload.semester is not None:
        profile.semester = payload.semester
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password is not None:
        _reset_password(db, user, payload.password)
    db.commit()
    db.refresh(profile)
    return _student_out(db, profile)


# ============================= Professors =============================


def create_professor(db: Session, payload: AdminCreateProfessorRequest) -> AdminProfessorOut:
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.PROFESSOR,
    )
    db.add(user)
    db.flush()

    profile = ProfessorProfile(user_id=user.id, department=payload.department)
    db.add(profile)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from exc
    db.refresh(profile)
    return _professor_out(db, profile)


def _professor_out(db: Session, profile: ProfessorProfile) -> AdminProfessorOut:
    user = db.get(User, profile.user_id)
    return AdminProfessorOut(
        id=profile.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        department=profile.department,
        created_at=user.created_at,
    )


def list_professors(db: Session, q: str | None = None, limit: int = 100, offset: int = 0) -> list[AdminProfessorOut]:
    query = db.query(ProfessorProfile).join(User, ProfessorProfile.user_id == User.id)
    if q:
        needle = f"%{q.lower()}%"
        query = query.filter(func.lower(User.full_name).like(needle) | func.lower(ProfessorProfile.department).like(needle))
    profiles = query.order_by(User.full_name.asc()).offset(offset).limit(limit).all()

    # Batched (was N+1 — see list_students).
    users_by_id = {u.id: u for u in db.query(User).filter(User.id.in_([p.user_id for p in profiles])).all()}
    return [
        AdminProfessorOut(
            id=p.id,
            user_id=p.user_id,
            email=users_by_id[p.user_id].email,
            full_name=users_by_id[p.user_id].full_name,
            is_active=users_by_id[p.user_id].is_active,
            department=p.department,
            created_at=users_by_id[p.user_id].created_at,
        )
        for p in profiles
    ]


def _professor_or_404(db: Session, professor_id: uuid.UUID) -> ProfessorProfile:
    profile = db.get(ProfessorProfile, professor_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Professor not found")
    return profile


def update_professor(db: Session, professor_id: uuid.UUID, payload: AdminUpdateProfessorRequest) -> AdminProfessorOut:
    profile = _professor_or_404(db, professor_id)
    user = db.get(User, profile.user_id)
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.department is not None:
        profile.department = payload.department
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password is not None:
        _reset_password(db, user, payload.password)
    db.commit()
    db.refresh(profile)
    return _professor_out(db, profile)


# ============================= Subjects =============================


def create_subject(db: Session, payload: AdminCreateSubjectRequest) -> AdminSubjectOut:
    subject = Subject(code=payload.code, name=payload.name, credits=payload.credits)
    db.add(subject)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Subject code already exists") from exc
    db.refresh(subject)
    return AdminSubjectOut.model_validate(subject)


def list_subjects(db: Session) -> list[AdminSubjectOut]:
    subjects = db.query(Subject).order_by(Subject.code.asc()).all()
    return [AdminSubjectOut.model_validate(s) for s in subjects]


def _subject_or_404(db: Session, subject_id: uuid.UUID) -> Subject:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found")
    return subject


def update_subject(db: Session, subject_id: uuid.UUID, payload: AdminUpdateSubjectRequest) -> AdminSubjectOut:
    subject = _subject_or_404(db, subject_id)
    if payload.name is not None:
        subject.name = payload.name
    if payload.credits is not None:
        subject.credits = payload.credits
    db.commit()
    db.refresh(subject)
    return AdminSubjectOut.model_validate(subject)


def delete_subject(db: Session, subject_id: uuid.UUID) -> None:
    subject = _subject_or_404(db, subject_id)
    in_use = db.query(ClassDivision).filter(ClassDivision.subject_id == subject_id).first()
    if in_use is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Cannot delete a subject with existing class divisions; remove those first"
        )
    db.delete(subject)
    db.commit()


# ============================= Class divisions =============================


def _division_out(db: Session, division: ClassDivision) -> AdminDivisionOut:
    subject = db.get(Subject, division.subject_id)
    professor = db.get(ProfessorProfile, division.professor_id)
    professor_user = db.get(User, professor.user_id) if professor else None
    enrolled_count = db.query(Enrollment).filter(Enrollment.class_division_id == division.id).count()
    return AdminDivisionOut(
        id=division.id,
        subject_id=division.subject_id,
        subject_code=subject.code if subject else "",
        subject_name=subject.name if subject else "",
        professor_id=division.professor_id,
        professor_name=professor_user.full_name if professor_user else "Unknown",
        name=division.name,
        semester=division.semester,
        room=division.room,
        enrolled_count=enrolled_count,
    )


def create_division(db: Session, payload: AdminCreateDivisionRequest) -> AdminDivisionOut:
    # Verify relationships server-side — never trust that a frontend-supplied id is valid.
    _subject_or_404(db, payload.subject_id)
    _professor_or_404(db, payload.professor_id)

    division = ClassDivision(
        subject_id=payload.subject_id,
        professor_id=payload.professor_id,
        name=payload.name,
        semester=payload.semester,
        room=payload.room,
    )
    db.add(division)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This subject already has a division with that name") from exc
    db.refresh(division)
    return _division_out(db, division)


def list_divisions(db: Session) -> list[AdminDivisionOut]:
    divisions = db.query(ClassDivision).order_by(ClassDivision.name.asc()).all()
    if not divisions:
        return []

    # Batched (was up to 4 queries per row: subject, professor, professor's user, enrolled
    # count — N+1 on a page every admin visit loads).
    subjects_by_id = {s.id: s for s in db.query(Subject).filter(Subject.id.in_({d.subject_id for d in divisions})).all()}
    professors_by_id = {
        p.id: p for p in db.query(ProfessorProfile).filter(ProfessorProfile.id.in_({d.professor_id for d in divisions})).all()
    }
    professor_users_by_id = {
        u.id: u for u in db.query(User).filter(User.id.in_([p.user_id for p in professors_by_id.values()])).all()
    }
    counts_by_division = dict(
        db.query(Enrollment.class_division_id, func.count(Enrollment.id))
        .filter(Enrollment.class_division_id.in_([d.id for d in divisions]))
        .group_by(Enrollment.class_division_id)
        .all()
    )

    results = []
    for d in divisions:
        subject = subjects_by_id.get(d.subject_id)
        professor = professors_by_id.get(d.professor_id)
        professor_user = professor_users_by_id.get(professor.user_id) if professor else None
        results.append(
            AdminDivisionOut(
                id=d.id,
                subject_id=d.subject_id,
                subject_code=subject.code if subject else "",
                subject_name=subject.name if subject else "",
                professor_id=d.professor_id,
                professor_name=professor_user.full_name if professor_user else "Unknown",
                name=d.name,
                semester=d.semester,
                room=d.room,
                enrolled_count=counts_by_division.get(d.id, 0),
            )
        )
    return results


def _division_or_404(db: Session, division_id: uuid.UUID) -> ClassDivision:
    division = db.get(ClassDivision, division_id)
    if division is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Class division not found")
    return division


def update_division(db: Session, division_id: uuid.UUID, payload: AdminUpdateDivisionRequest) -> AdminDivisionOut:
    division = _division_or_404(db, division_id)
    if payload.professor_id is not None:
        _professor_or_404(db, payload.professor_id)
        division.professor_id = payload.professor_id
    if payload.name is not None:
        division.name = payload.name
    if payload.semester is not None:
        division.semester = payload.semester
    if payload.room is not None:
        division.room = payload.room
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This subject already has a division with that name") from exc
    db.refresh(division)
    return _division_out(db, division)


# ============================= Enrollments =============================


def create_enrollment(db: Session, payload: AdminCreateEnrollmentRequest) -> AdminEnrollmentOut:
    student = _student_or_404(db, payload.student_id)
    _division_or_404(db, payload.class_division_id)

    enrollment = Enrollment(student_id=payload.student_id, class_division_id=payload.class_division_id)
    db.add(enrollment)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Student is already enrolled in this class division") from exc
    db.refresh(enrollment)
    return _enrollment_out(db, enrollment, student)


def _enrollment_out(db: Session, enrollment: Enrollment, student: StudentProfile | None = None) -> AdminEnrollmentOut:
    student = student or db.get(StudentProfile, enrollment.student_id)
    user = db.get(User, student.user_id) if student else None
    return AdminEnrollmentOut(
        id=enrollment.id,
        student_id=enrollment.student_id,
        student_name=user.full_name if user else "Unknown",
        roll_number=student.roll_number if student else "",
        class_division_id=enrollment.class_division_id,
        created_at=enrollment.created_at,
    )


def list_enrollments(db: Session, class_division_id: uuid.UUID) -> list[AdminEnrollmentOut]:
    _division_or_404(db, class_division_id)
    enrollments = db.query(Enrollment).filter(Enrollment.class_division_id == class_division_id).all()
    if not enrollments:
        return []

    # Batched (was 2 queries per row: StudentProfile + User — N+1).
    students_by_id = {
        s.id: s for s in db.query(StudentProfile).filter(StudentProfile.id.in_({e.student_id for e in enrollments})).all()
    }
    users_by_id = {u.id: u for u in db.query(User).filter(User.id.in_([s.user_id for s in students_by_id.values()])).all()}

    results = []
    for e in enrollments:
        student = students_by_id.get(e.student_id)
        user = users_by_id.get(student.user_id) if student else None
        results.append(
            AdminEnrollmentOut(
                id=e.id,
                student_id=e.student_id,
                student_name=user.full_name if user else "Unknown",
                roll_number=student.roll_number if student else "",
                class_division_id=e.class_division_id,
                created_at=e.created_at,
            )
        )
    return results


def delete_enrollment(db: Session, enrollment_id: uuid.UUID) -> None:
    enrollment = db.get(Enrollment, enrollment_id)
    if enrollment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enrollment not found")
    db.delete(enrollment)
    db.commit()


def bulk_enroll(db: Session, student_ids: list[uuid.UUID], class_division_id: uuid.UUID) -> AdminBulkEnrollResult:
    _division_or_404(db, class_division_id)

    existing_ids = {
        row[0]
        for row in db.query(StudentProfile.id).filter(StudentProfile.id.in_(student_ids)).all()
    }
    already_enrolled_ids = {
        row[0]
        for row in db.query(Enrollment.student_id)
        .filter(Enrollment.class_division_id == class_division_id, Enrollment.student_id.in_(student_ids))
        .all()
    }

    not_found = [sid for sid in student_ids if sid not in existing_ids]
    to_enroll = [sid for sid in student_ids if sid in existing_ids and sid not in already_enrolled_ids]

    for sid in to_enroll:
        db.add(Enrollment(student_id=sid, class_division_id=class_division_id))
    try:
        db.commit()
    except IntegrityError as exc:
        # Another request enrolled some of these students between our check and insert.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Enrollment changed concurrently — please retry") from exc

    return AdminBulkEnrollResult(
        enrolled=to_enroll, already_enrolled=sorted(already_enrolled_ids, key=str), not_found=not_found
    )


# ============================= Lectures =============================


def _lecture_out(db: Session, lecture: Lecture) -> AdminLectureOut:
    division = db.get(ClassDivision, lecture.class_division_id)
    subject = db.get(Subject, division.subject_id) if division else None
    return AdminLectureOut(
        id=lecture.id,
        class_division_id=lecture.class_division_id,
        subject_name=subject.name if subject else "",
        division_name=division.name if division else "",
        topic=lecture.topic,
        scheduled_start=lecture.scheduled_start,
        scheduled_end=lecture.scheduled_end,
        room=lecture.room,
    )


def create_lecture(db: Session, payload: AdminCreateLectureRequest) -> AdminLectureOut:
    _division_or_404(db, payload.class_division_id)
    if payload.scheduled_end <= payload.scheduled_start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "scheduled_end must be after scheduled_start")

    lecture = Lecture(
        class_division_id=payload.class_division_id,
        topic=payload.topic,
        scheduled_start=payload.scheduled_start,
        scheduled_end=payload.scheduled_end,
        room=payload.room,
    )
    db.add(lecture)
    db.commit()
    db.refresh(lecture)
    return _lecture_out(db, lecture)


def list_lectures(db: Session, class_division_id: uuid.UUID | None = None) -> list[AdminLectureOut]:
    query = db.query(Lecture)
    if class_division_id is not None:
        query = query.filter(Lecture.class_division_id == class_division_id)
    lectures = query.order_by(Lecture.scheduled_start.desc()).limit(200).all()
    if not lectures:
        return []

    # Batched (was 2 queries per row, up to 200 rows = up to 400 extra queries — N+1).
    divisions_by_id = {
        d.id: d for d in db.query(ClassDivision).filter(ClassDivision.id.in_({l.class_division_id for l in lectures})).all()
    }
    subjects_by_id = {
        s.id: s
        for s in db.query(Subject).filter(Subject.id.in_([d.subject_id for d in divisions_by_id.values()])).all()
    }

    results = []
    for l in lectures:
        division = divisions_by_id.get(l.class_division_id)
        subject = subjects_by_id.get(division.subject_id) if division else None
        results.append(
            AdminLectureOut(
                id=l.id,
                class_division_id=l.class_division_id,
                subject_name=subject.name if subject else "",
                division_name=division.name if division else "",
                topic=l.topic,
                scheduled_start=l.scheduled_start,
                scheduled_end=l.scheduled_end,
                room=l.room,
            )
        )
    return results


def _lecture_or_404(db: Session, lecture_id: uuid.UUID) -> Lecture:
    lecture = db.get(Lecture, lecture_id)
    if lecture is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lecture not found")
    return lecture


def update_lecture(db: Session, lecture_id: uuid.UUID, payload: AdminUpdateLectureRequest) -> AdminLectureOut:
    lecture = _lecture_or_404(db, lecture_id)
    if payload.topic is not None:
        lecture.topic = payload.topic
    if payload.scheduled_start is not None:
        lecture.scheduled_start = payload.scheduled_start
    if payload.scheduled_end is not None:
        lecture.scheduled_end = payload.scheduled_end
    if payload.room is not None:
        lecture.room = payload.room
    if lecture.scheduled_end <= lecture.scheduled_start:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "scheduled_end must be after scheduled_start")
    db.commit()
    db.refresh(lecture)
    return _lecture_out(db, lecture)


def delete_lecture(db: Session, lecture_id: uuid.UUID) -> None:
    lecture = _lecture_or_404(db, lecture_id)
    has_sessions = db.query(AttendanceSession).filter(AttendanceSession.lecture_id == lecture_id).first()
    has_records = db.query(AttendanceRecord).filter(AttendanceRecord.lecture_id == lecture_id).first()
    if has_sessions is not None or has_records is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Cannot delete a lecture that already has attendance sessions or records"
        )
    db.delete(lecture)
    db.commit()


# ============================= Summary =============================


def summary(db: Session) -> AdminSummaryOut:
    """Row counts for the admin dashboard, in ONE round trip (the dashboard used to download
    every student/professor/subject/division list just to call len() on them)."""

    def count(model):
        return select(func.count()).select_from(model).scalar_subquery()

    students, professors, subjects, divisions, lectures, enrollments = db.execute(
        select(
            count(StudentProfile),
            count(ProfessorProfile),
            count(Subject),
            count(ClassDivision),
            count(Lecture),
            count(Enrollment),
        )
    ).one()
    return AdminSummaryOut(
        students=students,
        professors=professors,
        subjects=subjects,
        divisions=divisions,
        lectures=lectures,
        enrollments=enrollments,
    )
