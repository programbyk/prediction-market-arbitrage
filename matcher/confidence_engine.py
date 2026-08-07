"""V7.3 confidence based on canonical EventObject identity."""

from __future__ import annotations

from typing import List, Tuple

from core.event_engine import EventObject
from models import MatchResult, ParsedMarket
from legacy.scanner_v6_1 import fuzzy_score


def _same_or_missing(left, right) -> bool:
    return not left or not right or left == right


def semantic_confidence(
    kalshi_market: ParsedMarket,
    poly_market: ParsedMarket,
    kalshi_event: EventObject,
    poly_event: EventObject,
    bucket_hits: int,
) -> MatchResult:
    reasons: List[str] = []
    rejects: List[str] = []

    # Mandatory canonical identity.
    if kalshi_event.category != poly_event.category:
        rejects.append("canonical category mismatch")
    if kalshi_event.entity.key != poly_event.entity.key:
        rejects.append(
            f"canonical entity mismatch: "
            f"{kalshi_event.entity.key} vs {poly_event.entity.key}"
        )
    if kalshi_event.intent != poly_event.intent:
        rejects.append(
            f"canonical intent mismatch: "
            f"{kalshi_event.intent} vs {poly_event.intent}"
        )
    if (
        kalshi_event.resolution_type
        and poly_event.resolution_type
        and kalshi_event.resolution_type != poly_event.resolution_type
    ):
        rejects.append(
            f"resolution mismatch: "
            f"{kalshi_event.resolution_type} vs {poly_event.resolution_type}"
        )

    for label, left, right in (
        ("country", kalshi_event.canonical_country, poly_event.canonical_country),
        ("party", kalshi_event.canonical_party, poly_event.canonical_party),
        ("election", kalshi_event.election_id, poly_event.election_id),
        ("proposition subject type", kalshi_event.proposition_subject_type, poly_event.proposition_subject_type),
        ("proposition subject", kalshi_event.proposition_subject_value, poly_event.proposition_subject_value),
        ("tournament", kalshi_event.tournament_id, poly_event.tournament_id),
        ("gender", kalshi_event.gender, poly_event.gender),
    ):
        if left and right and left != right:
            rejects.append(f"{label} mismatch: {left} vs {right}")

    if rejects:
        return MatchResult(
            kalshi_market,
            poly_market,
            0,
            False,
            reasons,
            rejects,
            bucket_hits,
        )

    score = 55
    reasons.extend(
        [
            "same canonical category (+10)",
            "same canonical entity (+25)",
            "same canonical intent (+20)",
        ]
    )

    if kalshi_event.resolution_type and poly_event.resolution_type:
        score += 15
        reasons.append(
            f"same resolution_type: {kalshi_event.resolution_type} (+15)"
        )

    if kalshi_event.sport and poly_event.sport:
        if kalshi_event.sport != poly_event.sport:
            rejects.append(
                f"sport mismatch: {kalshi_event.sport} vs {poly_event.sport}"
            )
        else:
            score += 5
            reasons.append(f"same sport: {kalshi_event.sport} (+5)")

    if kalshi_event.competition and poly_event.competition:
        if kalshi_event.competition != poly_event.competition:
            rejects.append(
                f"competition mismatch: "
                f"{kalshi_event.competition} vs {poly_event.competition}"
            )
        else:
            score += 15
            reasons.append(
                f"same canonical competition: "
                f"{kalshi_event.competition} (+15)"
            )

    if kalshi_event.year and poly_event.year:
        if kalshi_event.year != poly_event.year:
            rejects.append(
                f"year mismatch: {kalshi_event.year} vs {poly_event.year}"
            )
        else:
            score += 5
            reasons.append(f"same year: {kalshi_event.year} (+5)")
    elif kalshi_event.year or poly_event.year:
        # Missing year is allowed only when event identity is otherwise exact.
        reasons.append(
            f"one side missing year but canonical identity agrees: "
            f"{kalshi_event.year} vs {poly_event.year} (+0)"
        )

    # Resolution parameters are mandatory when present on both sides.
    parameter_pairs = (
        ("threshold", kalshi_event.threshold, poly_event.threshold),
        ("direction", kalshi_event.direction, poly_event.direction),
        ("resolution_time", kalshi_event.resolution_time, poly_event.resolution_time),
        ("deadline", kalshi_event.deadline, poly_event.deadline),
        ("lower_bound", kalshi_event.lower_bound, poly_event.lower_bound),
        ("upper_bound", kalshi_event.upper_bound, poly_event.upper_bound),
    )
    for label, left, right in parameter_pairs:
        if left is not None and right is not None:
            if left != right:
                rejects.append(f"{label} mismatch: {left} vs {right}")
            else:
                score += 3
                reasons.append(f"same {label}: {left} (+3)")

    if rejects:
        return MatchResult(
            kalshi_market,
            poly_market,
            min(score, 100),
            False,
            reasons,
            rejects,
            bucket_hits,
        )

    for label, left, right, pts in (
        ("country", kalshi_event.canonical_country, poly_event.canonical_country, 5),
        ("party", kalshi_event.canonical_party, poly_event.canonical_party, 5),
        ("election", kalshi_event.election_id, poly_event.election_id, 8),
        ("proposition subject type", kalshi_event.proposition_subject_type, poly_event.proposition_subject_type, 5),
        ("proposition subject", kalshi_event.proposition_subject_value, poly_event.proposition_subject_value, 8),
        ("tournament", kalshi_event.tournament_id, poly_event.tournament_id, 8),
        ("gender", kalshi_event.gender, poly_event.gender, 3),
    ):
        if left and right and left == right:
            score += pts
            reasons.append(f"same {label}: {left} (+{pts})")

    title_similarity = fuzzy_score(kalshi_market.title, poly_market.title)
    if title_similarity >= 70:
        score += 5
        reasons.append(f"supporting title similarity: {title_similarity} (+5)")
    else:
        reasons.append(f"title similarity not required: {title_similarity} (+0)")

    if bucket_hits >= 2:
        score += 2
        reasons.append(f"multiple graph routes: {bucket_hits} (+2)")

    confidence = min(score, 100)
    accepted = confidence >= 86

    if not accepted:
        rejects.append(f"semantic confidence below threshold: {confidence} < 86")

    return MatchResult(
        kalshi_market,
        poly_market,
        confidence,
        accepted,
        reasons,
        rejects,
        bucket_hits,
    )
