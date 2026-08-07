"""Build structured EventObjects from ParsedMarket instances."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models import ParsedMarket
from .entity_engine import Entity, EntityEngine
from .intent_engine import IntentEngine, get_intent_engine
from .resolution_engine import ResolutionEngine, ResolutionSpec
from .canonical_engine import enrich_canonical_identity
from .knowledge_engine import enrich_knowledge_identity
from .identity_v75 import enrich_v75_identity


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
    resolution_type: Optional[str] = None
    resolution_time: Optional[str] = None
    deadline: Optional[str] = None
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    canonical_country: Optional[str] = None
    canonical_party: Optional[str] = None
    proposition_subject_type: Optional[str] = None
    proposition_subject_value: Optional[str] = None
    election_id: Optional[str] = None
    race_id: Optional[str] = None
    district: Optional[int] = None
    election_type: Optional[str] = None
    canonical_candidate: Optional[str] = None
    tournament_id: Optional[str] = None
    gender: Optional[str] = None
    tour: Optional[str] = None
    surface: Optional[str] = None
    contract_type: Optional[str] = None
    contract_time_scope: Optional[str] = None

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
            self.resolution_type or "",
            self.resolution_time or "",
            self.deadline or "",
            str(self.lower_bound) if self.lower_bound is not None else "",
            str(self.upper_bound) if self.upper_bound is not None else "",
            self.canonical_country or "", self.canonical_party or "",
            self.proposition_subject_type or "", self.proposition_subject_value or "",
            self.election_id or "", self.tournament_id or "", self.gender or "",
            self.tour or "", self.surface or "",
        ]
        return "|".join(parts)


class EventEngine:
    def __init__(
        self,
        entity_engine: Optional[EntityEngine] = None,
        intent_engine: Optional[IntentEngine] = None,
        resolution_engine: Optional[ResolutionEngine] = None,
    ) -> None:
        self.entity_engine = entity_engine or EntityEngine()
        self.intent_engine = intent_engine or get_intent_engine()
        self.resolution_engine = resolution_engine or ResolutionEngine()

    def build(self, market: ParsedMarket) -> Optional[EventObject]:
        enrich_canonical_identity(market)
        enrich_knowledge_identity(market)
        enrich_v75_identity(market)
        entity = self.entity_engine.resolve(market)
        intent = self.intent_engine.resolve(market)
        if not entity or not intent:
            return None

        market.market_intent = intent
        resolution = self.resolution_engine.resolve(market)

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
            resolution_type=resolution.resolution_type if resolution else None,
            resolution_time=resolution.resolution_time if resolution else None,
            deadline=resolution.deadline if resolution else None,
            lower_bound=resolution.lower_bound if resolution else None,
            upper_bound=resolution.upper_bound if resolution else None,
            canonical_country=market.canonical_country, canonical_party=market.canonical_party,
            proposition_subject_type=market.proposition_subject_type,
            proposition_subject_value=market.proposition_subject_value,
            election_id=market.election_id, tournament_id=market.tournament_id,
            gender=market.gender, tour=market.tour, surface=market.surface,
        )

        market.market_intent = event.intent
        market.entity_key = event.entity.key
        market.event_object_key = event.key
        return event
