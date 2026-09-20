import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.schemas.admin import (
    AdminBulkEnrollRequest,
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
from app.services import admin_service

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# ---------- Summary ----------


@router.get("/summary", response_model=AdminSummaryOut)
def summary(db: Session = Depends(get_db)):
    return admin_service.summary(db)


# ---------- Students ----------


@router.post("/students", response_model=AdminStudentOut, status_code=201)
def create_student(payload: AdminCreateStudentRequest, db: Session = Depends(get_db)):
    return admin_service.create_student(db, payload)


@router.get("/students", response_model=list[AdminStudentOut])
def list_students(
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return admin_service.list_students(db, q, limit, offset)


@router.patch("/students/{student_id}", response_model=AdminStudentOut)
def update_student(student_id: uuid.UUID, payload: AdminUpdateStudentRequest, db: Session = Depends(get_db)):
    return admin_service.update_student(db, student_id, payload)


# ---------- Professors ----------


@router.post("/professors", response_model=AdminProfessorOut, status_code=201)
def create_professor(payload: AdminCreateProfessorRequest, db: Session = Depends(get_db)):
    return admin_service.create_professor(db, payload)


@router.get("/professors", response_model=list[AdminProfessorOut])
def list_professors(
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return admin_service.list_professors(db, q, limit, offset)


@router.patch("/professors/{professor_id}", response_model=AdminProfessorOut)
def update_professor(professor_id: uuid.UUID, payload: AdminUpdateProfessorRequest, db: Session = Depends(get_db)):
    return admin_service.update_professor(db, professor_id, payload)


# ---------- Subjects ----------


@router.post("/subjects", response_model=AdminSubjectOut, status_code=201)
def create_subject(payload: AdminCreateSubjectRequest, db: Session = Depends(get_db)):
    return admin_service.create_subject(db, payload)


@router.get("/subjects", response_model=list[AdminSubjectOut])
def list_subjects(db: Session = Depends(get_db)):
    return admin_service.list_subjects(db)


@router.patch("/subjects/{subject_id}", response_model=AdminSubjectOut)
def update_subject(subject_id: uuid.UUID, payload: AdminUpdateSubjectRequest, db: Session = Depends(get_db)):
    return admin_service.update_subject(db, subject_id, payload)


@router.delete("/subjects/{subject_id}", status_code=204)
def delete_subject(subject_id: uuid.UUID, db: Session = Depends(get_db)):
    admin_service.delete_subject(db, subject_id)
    return None


# ---------- Class divisions ----------


@router.post("/divisions", response_model=AdminDivisionOut, status_code=201)
def create_division(payload: AdminCreateDivisionRequest, db: Session = Depends(get_db)):
    return admin_service.create_division(db, payload)


@router.get("/divisions", response_model=list[AdminDivisionOut])
def list_divisions(db: Session = Depends(get_db)):
    return admin_service.list_divisions(db)


@router.patch("/divisions/{division_id}", response_model=AdminDivisionOut)
def update_division(division_id: uuid.UUID, payload: AdminUpdateDivisionRequest, db: Session = Depends(get_db)):
    return admin_service.update_division(db, division_id, payload)


# ---------- Enrollments ----------


@router.post("/enrollments", response_model=AdminEnrollmentOut, status_code=201)
def create_enrollment(payload: AdminCreateEnrollmentRequest, db: Session = Depends(get_db)):
    return admin_service.create_enrollment(db, payload)


@router.get("/enrollments", response_model=list[AdminEnrollmentOut])
def list_enrollments(class_division_id: uuid.UUID, db: Session = Depends(get_db)):
    return admin_service.list_enrollments(db, class_division_id)


@router.delete("/enrollments/{enrollment_id}", status_code=204)
def delete_enrollment(enrollment_id: uuid.UUID, db: Session = Depends(get_db)):
    admin_service.delete_enrollment(db, enrollment_id)
    return None


@router.post("/enrollments/bulk", response_model=AdminBulkEnrollResult)
def bulk_enroll(payload: AdminBulkEnrollRequest, db: Session = Depends(get_db)):
    return admin_service.bulk_enroll(db, payload.student_ids, payload.class_division_id)


# ---------- Lectures ----------


@router.post("/lectures", response_model=AdminLectureOut, status_code=201)
def create_lecture(payload: AdminCreateLectureRequest, db: Session = Depends(get_db)):
    return admin_service.create_lecture(db, payload)


@router.get("/lectures", response_model=list[AdminLectureOut])
def list_lectures(class_division_id: uuid.UUID | None = None, db: Session = Depends(get_db)):
    return admin_service.list_lectures(db, class_division_id)


@router.patch("/lectures/{lecture_id}", response_model=AdminLectureOut)
def update_lecture(lecture_id: uuid.UUID, payload: AdminUpdateLectureRequest, db: Session = Depends(get_db)):
    return admin_service.update_lecture(db, lecture_id, payload)


@router.delete("/lectures/{lecture_id}", status_code=204)
def delete_lecture(lecture_id: uuid.UUID, db: Session = Depends(get_db)):
    admin_service.delete_lecture(db, lecture_id)
    return None
