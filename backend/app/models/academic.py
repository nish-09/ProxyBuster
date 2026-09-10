import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.types import GUID


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    credits: Mapped[int] = mapped_column(default=3, nullable=False)

    class_divisions: Mapped[list["ClassDivision"]] = relationship(back_populates="subject")


class ClassDivision(Base):
    """A subject taught to a specific division/section by a specific professor."""

    __tablename__ = "class_divisions"
    __table_args__ = (UniqueConstraint("subject_id", "name", name="uq_subject_division_name"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    subject_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("subjects.id"), nullable=False)
    professor_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("professor_profiles.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "Div A"
    semester: Mapped[int] = mapped_column(nullable=False)
    room: Mapped[str] = mapped_column(String(50), nullable=True)

    subject: Mapped["Subject"] = relationship(back_populates="class_divisions")
    professor: Mapped["ProfessorProfile"] = relationship(back_populates="class_divisions")  # noqa: F821
    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="class_division")
    lectures: Mapped[list["Lecture"]] = relationship(back_populates="class_division")


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("student_id", "class_division_id", name="uq_student_division"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("student_profiles.id"), nullable=False
    )
    class_division_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("class_divisions.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    student: Mapped["StudentProfile"] = relationship(back_populates="enrollments")  # noqa: F821
    class_division: Mapped["ClassDivision"] = relationship(back_populates="enrollments")


class Lecture(Base):
    __tablename__ = "lectures"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    class_division_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("class_divisions.id"), nullable=False, index=True
    )
    topic: Mapped[str] = mapped_column(String(255), nullable=True)
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    room: Mapped[str] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    class_division: Mapped["ClassDivision"] = relationship(back_populates="lectures")
