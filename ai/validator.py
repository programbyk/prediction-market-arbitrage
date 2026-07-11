"""Future AI validation layer.

The rule-based matcher remains authoritative. This interface is ready for
a later semantic validator without changing the rest of the application.
"""
from dataclasses import dataclass
from models import MatchResult

@dataclass
class ValidationResult:
    equivalent: bool
    confidence: int
    reason: str

def validate_match(match: MatchResult) -> ValidationResult:
    return ValidationResult(
        equivalent=match.accepted,
        confidence=match.confidence,
        reason="Rule-based V6.1 validation",
    )
