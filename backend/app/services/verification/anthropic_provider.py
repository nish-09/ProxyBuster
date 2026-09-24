import base64
import logging

from app.core.config import get_settings
from app.services.verification.provider import StudentObservation, StudentReference, VisionAnalysis

logger = logging.getLogger("proxybusters.verification.anthropic")

TOOL_NAME = "report_classroom_observations"

_TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Report, for each listed student, your confidence (0.0-1.0) that their reference "
        "photo's face appears somewhere in the classroom photo(s). Omit a student entirely if "
        "you see no plausible match — never guess an identity you are not reasonably "
        "confident about."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "observations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "roll_number": {
                            "type": "string",
                            "description": "The student's roll number, exactly as given.",
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["roll_number", "confidence"],
                },
            }
        },
        "required": ["observations"],
    },
}

_INSTRUCTIONS = (
    "You are assisting a professor in verifying classroom attendance from photos. You will be "
    "shown one reference photo per enrolled student (each labelled with their name and roll "
    "number), followed by 1-3 photos taken of the classroom during the lecture. For each "
    "enrolled student, decide how confident you are that they are visibly present in the "
    "classroom photo(s), based on matching their appearance against their reference photo.\n\n"
    "Rules:\n"
    "- This is for attendance verification only. A human professor reviews every result before "
    "anything happens — nothing you report is ever applied automatically.\n"
    "- Never guess. If a face is unclear, partially hidden, poorly lit, or you are simply not "
    "confident, report a LOW confidence rather than a high one.\n"
    "- If you cannot find any plausible match for a student anywhere in the photo(s), omit "
    "them from your response entirely rather than reporting a near-zero confidence.\n"
    "- Do not count the same physical person twice across multiple photos of the same room.\n"
    "- Call the report_classroom_observations tool exactly once with your findings."
)

_ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _media_type(content_type: str) -> str:
    return content_type if content_type in _ALLOWED_MEDIA_TYPES else "image/jpeg"


class AnthropicVisionProvider:
    """VisionProvider backed by Anthropic's Claude vision models. A plain HTTPS call with no
    native build dependencies, so it stays swappable behind services.verification.provider —
    see ClassroomVerificationService."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")
        import anthropic  # local import: the SDK stays optional for anyone not using this feature

        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_vision_model

    def analyze_classroom(self, images: list[bytes], students: list[StudentReference]) -> VisionAnalysis:
        content: list[dict] = [{"type": "text", "text": _INSTRUCTIONS}]
        for student in students:
            content.append(
                {"type": "text", "text": f"Reference photo — {student.full_name} (Roll: {student.roll_number}):"}
            )
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": _media_type(student.content_type),
                        "data": base64.b64encode(student.image_bytes).decode(),
                    },
                }
            )
        content.append({"type": "text", "text": "Classroom photo(s):"})
        for image_bytes in images:
            content.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(image_bytes).decode()},
                }
            )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[{"role": "user", "content": content}],
        )

        roll_to_student = {s.roll_number: s.student_id for s in students}
        observations: list[StudentObservation] = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use" or block.name != TOOL_NAME:
                continue
            for item in (block.input or {}).get("observations", []):
                student_id = roll_to_student.get(item.get("roll_number"))
                if student_id is None:
                    continue  # the model referenced a roll number we never gave it — never fabricate
                try:
                    confidence = float(item.get("confidence", 0.0))
                except (TypeError, ValueError):
                    continue
                observations.append(StudentObservation(student_id=student_id, confidence=max(0.0, min(1.0, confidence))))

        return VisionAnalysis(observations=observations)
