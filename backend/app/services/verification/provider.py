import dataclasses
import uuid
from typing import Protocol


@dataclasses.dataclass
class StudentReference:
    """One enrolled student's reference photo, handed to a provider for one analysis call.
    Never persisted by the provider itself — the caller owns the image bytes' lifetime."""

    student_id: uuid.UUID
    full_name: str
    roll_number: str
    image_bytes: bytes
    content_type: str


@dataclasses.dataclass
class StudentObservation:
    student_id: uuid.UUID
    # Raw 0.0-1.0 signal from the provider. Bucketing this into CONFIRMED / HIGH_CONFIDENCE /
    # UNCERTAIN / NOT_DETECTED happens in services/verification/service.py, never here — a
    # provider's job is only to report how confident it is, not to make the final call.
    confidence: float


@dataclasses.dataclass
class VisionAnalysis:
    observations: list[StudentObservation]


class VisionProvider(Protocol):
    """Swappable classroom-image analysis backend (Person Detection -> Face Detection ->
    Identity Matching -> Confidence Score). analyze_classroom must NEVER fabricate an
    identity: a student it cannot find with reasonable confidence must simply be omitted from
    `observations` (the caller then treats them as NOT_DETECTED) rather than guessed."""

    def analyze_classroom(self, images: list[bytes], students: list[StudentReference]) -> VisionAnalysis: ...
