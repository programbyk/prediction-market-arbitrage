"""Extract the primary entity from a parsed market."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models import ParsedMarket
from .knowledge_engine import enrich_knowledge_identity


@dataclass(frozen=True)
class Entity:
    entity_type: str
    entity_id: str

    @property
    def key(self) -> str:
        return f"{self.entity_type}:{self.entity_id}"


class EntityEngine:
    """Resolve the real-world subject whose outcome settles the market."""

    def resolve(self, market: ParsedMarket) -> Optional[Entity]:
        if market.category == "sports":
            if market.player:
                return Entity("player", market.player)
            if market.teams:
                return Entity("teams", "+".join(sorted(market.teams)))
            if market.event_subject:
                return Entity("subject", market.event_subject)
            if market.competition:
                return Entity("competition", market.competition)

        elif market.category == "politics":
            enrich_knowledge_identity(market)
            if market.proposition_subject_type == "candidate" and market.proposition_subject_value:
                return Entity("candidate", market.proposition_subject_value)
            if market.proposition_subject_type and market.proposition_subject_value and market.election_id:
                return Entity(market.proposition_subject_type, f"{market.election_id}:{market.proposition_subject_value}")
            if market.candidate:
                return Entity("candidate", market.candidate)
            if market.canonical_party and market.canonical_country:
                return Entity("party", f"{market.canonical_country}:{market.canonical_party}")
            if market.election_id:
                return Entity("election", market.election_id)
            geography = market.state or market.canonical_country or market.country
            if geography and market.office:
                return Entity("race", f"{geography}:{market.office}")

        elif market.category == "crypto":
            if market.asset:
                return Entity("asset", market.asset)

        elif market.category == "economy":
            if market.metric:
                geography = market.country or "unknown_country"
                return Entity("metric", f"{geography}:{market.metric}")

        return None
