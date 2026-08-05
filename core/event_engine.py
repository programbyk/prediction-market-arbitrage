"""Build structured EventObjects from ParsedMarket instances."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models import ParsedMarket
from .entity_engine import Entity, EntityEngine
from .intent_engine import IntentEngine, get_intent_engine


@dataclass(frozen=True)
class EventObject:
    category: str
    entity: Entity
    intent: str
    year: Optional[int]
    sport: Optional[str] = None
    league: Optional[str] = None
    competition: Optional[str] = None
    threshold: Optional[float] = None
    direction: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None
    office: Optional[str] = None
    period: Optional[str] = None

    @property
    def key(self) -> str:
        parts = [
            self.category,
            self.entity.key,
            self.intent,
            str(self.year or ""),
            self.sport or "",
            self.league or "",
            self.competition or "",
            str(self.threshold) if self.threshold is not None else "",
            self.direction or "",
            self.country or "",
            self.state or "",
            self.office or "",
            self.period or "",
        ]
        return "|".join(parts)


class EventEngine:
    def __init__(
        self,
        entity_engine: Optional[EntityEngine] = None,
        intent_engine: Optional[IntentEngine] = None,
    ) -> None:
        self.entity_engine = entity_engine or EntityEngine()
        self.intent_engine = intent_engine or get_intent_engine()

    def build(self, market: ParsedMarket) -> Optional[EventObject]:
        entity = self.entity_engine.resolve(market)
        intent = self.intent_engine.resolve(market)
        if not entity or not intent:
            return None

        event = EventObject(
            category=market.category,
            entity=entity,
            intent=intent,
            year=market.year,
            sport=market.sport,
            league=market.league,
            competition=market.competition,
            threshold=market.threshold,
            direction=market.direction,
            country=market.country,
            state=market.state,
            office=market.office,
            period=market.period,
        )

        market.market_intent = event.intent
        market.entity_key = event.entity.key
        market.event_object_key = event.key
        return event
