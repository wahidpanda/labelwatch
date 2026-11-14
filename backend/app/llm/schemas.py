"""Structured outputs for the classify and judge chains (SPEC 11.2)."""

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _max_words(limit: int) -> Callable[[str], str]:
    def check(value: str) -> str:
        words = value.split()
        return value if len(words) <= limit else " ".join(words[:limit])

    return check


class ClassifyOut(BaseModel):
    is_substantive: bool = Field(description="True for a new or stronger safety meaning")
    change_type: Literal["added", "strengthened", "modified", "editorial"]
    severity: Literal["boxed", "major", "moderate", "minor"]
    claim: str = Field(description="One sentence, at most 40 words, stating the safety claim")
    reason: str = Field(description="At most 25 words")

    _claim = field_validator("claim")(_max_words(40))
    _reason = field_validator("reason")(_max_words(25))


class JudgeOut(BaseModel):
    status: Literal["propagated", "partial", "not_propagated", "insufficient_evidence"]
    quotes: list[str] = Field(
        default_factory=list, description="Sentences copied exactly from the generic units"
    )
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(description="At most 40 words")

    _rationale = field_validator("rationale")(_max_words(40))
