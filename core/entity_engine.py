"""Extract the primary entity from a parsed market."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models import ParsedMarket


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
            if market.candidate:
                return Entity("candidate", market.candidate)
            if market.party:
                return Entity("party", market.party)
            geography = market.state or market.country
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
