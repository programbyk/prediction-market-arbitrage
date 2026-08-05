#!/usr/bin/env python3
"""
scanner_v6.1.py
Prediction-market arbitrage scanner for Kalshi + Polymarket.

V6.1 changes:
- Expands non-binary Polymarket outcomes into synthetic YES/NO contracts.
- Adds REVIEW mode for structurally compatible pairs below the acceptance threshold.
- Enriches Polymarket titles with group/outcome metadata.
- Reduces false crypto classification by requiring crypto context.
- Keeps hard rejection rules for different competitions, countries, periods and candidates.
- Sports-first parser prevents athletes and teams from being classified as politics.
- Adds strict sports identity: sport, league, competition, participant and year.
- Rejects Home Run Derby vs MVP, NCAA vs MLB, and different-award false matches.
- Adds strict economic-market identity: country, metric, comparison operator and period.
- Rejects Canada-vs-USA, monthly-vs-yearly and above-vs-at-least false matches.
- Unicode-aware normalization: Raphaël, Éric, etc. are preserved as comparable ASCII names.
- Dynamic political subject extraction from phrases such as "Will X win..." and Kalshi subtitles.
- International country extraction and country mismatch rejection.
- Primary/nomination markets are no longer compared with general-election winner markets.
- Candidate names no longer need to exist in a small hard-coded alias dictionary.
- Better diagnostics for extracted candidate, country, and election stage.

Previous multi-index changes:
- Fixes "Candidate comparisons: 0" by replacing rigid single-bucket matching
  with a multi-index candidate generator.
- Each market is indexed in multiple loose buckets:
    politics|state|colorado
    politics|office|governor
    politics|year|2026
    politics|party|democratic_party
    crypto|asset|bitcoin
    sports|team|mexico
- The score engine decides compatibility after candidates are generated.
- Shows diagnostic counts so you can tell whether the scanner is comparing.
- Keeps strict resolution compatibility: winner != margin, state mismatch rejected,
  candidate-specific vs generic political markets rejected.

Install:
    pip install requests rapidfuzz

Run:
    python scanner_v6.py --no-cache
    python scanner_v6.py --no-cache --min-confidence 80 --show-candidates 20
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import requests

try:
    from rapidfuzz import fuzz
except Exception:
    fuzz = None


from knowledge.loader import get_knowledge_base
from utils.helpers import (
    bounded_alt,
    important_words,
    normalize_text,
    parse_json_maybe,
    parse_number,
    parse_year,
    safe_float,
    words,
)

# -----------------------------
# Config
# -----------------------------

KALSHI_API_URL = "https://external-api.kalshi.com/trade-api/v2/markets"
POLYMARKET_API_URL = "https://gamma-api.polymarket.com/markets/keyset"

REQUEST_TIMEOUT = 20
CACHE_DIR = "cache"
CACHE_TTL_SECONDS = 180

KALSHI_MAX_PAGES = 20
KALSHI_LIMIT = 1000

POLY_MAX_PAGES = 200
POLY_LIMIT = 100

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 1.5

MIN_MATCH_CONFIDENCE = 86
REVIEW_MIN_CONFIDENCE = 70
MIN_ARBITRAGE_PROFIT = 0.005
SHOW_TOP_MATCHES = 30
SHOW_TOP_CANDIDATES = 15
DEBUG = False


# -----------------------------
# Models
# -----------------------------

@dataclass
class MarketPrice:
    yes: Optional[float] = None
    no: Optional[float] = None

    def is_tradeable(self) -> bool:
        return (
            self.yes is not None and self.no is not None
            and 0 < self.yes < 1 and 0 < self.no < 1
        )


@dataclass
class ParsedMarket:
    platform: str
    source_id: str
    title: str
    raw: Dict[str, Any]
    price: MarketPrice

    category: str = "other"
    market_type: str = "unknown"
    subtype: str = "unknown"

    country: Optional[str] = None
    state: Optional[str] = None
    office: Optional[str] = None
    candidate: Optional[str] = None
    party: Optional[str] = None
    year: Optional[int] = None

    asset: Optional[str] = None
    threshold: Optional[float] = None
    direction: Optional[str] = None

    # Economy / exact resolution identity
    metric: Optional[str] = None
    comparison: Optional[str] = None
    period: Optional[str] = None
    resolution_scope: Optional[str] = None

    sport: Optional[str] = None
    league: Optional[str] = None
    competition: Optional[str] = None
    event_scope: Optional[str] = None
    event_kind: Optional[str] = None
    event_action: Optional[str] = None
    event_subject: Optional[str] = None
    participant_type: Optional[str] = None
    event_fingerprint: Optional[str] = None

    # V7 Event Graph identity
    market_intent: Optional[str] = None
    entity_key: Optional[str] = None
    event_object_key: Optional[str] = None

    # V7.2 Resolution Engine
    resolution_type: Optional[str] = None
    resolution_time: Optional[str] = None
    deadline: Optional[str] = None
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None

    teams: Tuple[str, ...] = field(default_factory=tuple)
    player: Optional[str] = None

    entities: Set[str] = field(default_factory=set)
    parser_notes: List[str] = field(default_factory=list)


@dataclass
class CandidatePair:
    kalshi: ParsedMarket
    polymarket: ParsedMarket
    bucket_hits: int


@dataclass
class MatchResult:
    kalshi: ParsedMarket
    polymarket: ParsedMarket
    confidence: int
    accepted: bool
    reasons: List[str]
    rejects: List[str]
    bucket_hits: int = 0


@dataclass
class ArbitrageOpportunity:
    match: MatchResult
    trade: str
    cost: float
    gross_profit: float


# -----------------------------
# Normalization dictionaries
# -----------------------------

US_STATES = {
    "alabama": "alabama", "alaska": "alaska", "arizona": "arizona", "arkansas": "arkansas",
    "california": "california", "colorado": "colorado", "connecticut": "connecticut",
    "delaware": "delaware", "florida": "florida", "georgia": "georgia", "hawaii": "hawaii",
    "idaho": "idaho", "illinois": "illinois", "indiana": "indiana", "iowa": "iowa",
    "kansas": "kansas", "kentucky": "kentucky", "louisiana": "louisiana", "maine": "maine",
    "maryland": "maryland", "massachusetts": "massachusetts", "michigan": "michigan",
    "minnesota": "minnesota", "mississippi": "mississippi", "missouri": "missouri",
    "montana": "montana", "nebraska": "nebraska", "nevada": "nevada",
    "new hampshire": "new_hampshire", "new jersey": "new_jersey", "new mexico": "new_mexico",
    "new york": "new_york", "north carolina": "north_carolina", "north dakota": "north_dakota",
    "ohio": "ohio", "oklahoma": "oklahoma", "oregon": "oregon", "pennsylvania": "pennsylvania",
    "rhode island": "rhode_island", "south carolina": "south_carolina",
    "south dakota": "south_dakota", "tennessee": "tennessee", "texas": "texas",
    "utah": "utah", "vermont": "vermont", "virginia": "virginia", "washington": "washington",
    "west virginia": "west_virginia", "wisconsin": "wisconsin", "wyoming": "wyoming",
    "dc": "district_of_columbia", "washington dc": "district_of_columbia",
}

STATE_ABBR = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas", "CA": "california",
    "CO": "colorado", "CT": "connecticut", "DE": "delaware", "FL": "florida", "GA": "georgia",
    "HI": "hawaii", "ID": "idaho", "IL": "illinois", "IN": "indiana", "IA": "iowa",
    "KS": "kansas", "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
    "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
    "NH": "new_hampshire", "NJ": "new_jersey", "NM": "new_mexico", "NY": "new_york",
    "NC": "north_carolina", "ND": "north_dakota", "OH": "ohio", "OK": "oklahoma",
    "OR": "oregon", "PA": "pennsylvania", "RI": "rhode_island", "SC": "south_carolina",
    "SD": "south_dakota", "TN": "tennessee", "TX": "texas", "UT": "utah",
    "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "west_virginia",
    "WI": "wisconsin", "WY": "wyoming",
}

COUNTRY_ALIASES = {
    "united states": "usa", "u s": "usa", "us": "usa", "usa": "usa",
    "france": "france", "french": "france",
    "bulgaria": "bulgaria", "bulgarian": "bulgaria",
    "united kingdom": "united_kingdom", "uk": "united_kingdom", "britain": "united_kingdom", "british": "united_kingdom",
    "germany": "germany", "german": "germany",
    "italy": "italy", "italian": "italy",
    "spain": "spain", "spanish": "spain",
    "canada": "canada", "canadian": "canada",
    "mexico": "mexico", "mexican": "mexico",
    "brazil": "brazil", "brazilian": "brazil",
    "argentina": "argentina", "argentinian": "argentina",
    "taiwan": "taiwan", "taiwanese": "taiwan",
    "australia": "australia", "australian": "australia",
    "india": "india", "indian": "india",
    "japan": "japan", "japanese": "japan",
    "south korea": "south_korea", "korean": "south_korea",
}

PARTY_ALIASES = {
    "democrat": "democratic_party", "democrats": "democratic_party", "democratic": "democratic_party",
    "democratic party": "democratic_party", "dem": "democratic_party",
    "republican": "republican_party", "republicans": "republican_party",
    "gop": "republican_party", "republican party": "republican_party",
    "independent": "independent", "libertarian": "libertarian_party",
}

CANDIDATE_ALIASES = {
    # Use full names for most politicians. Single surnames caused false positives:
    # "Haley Thogmartin" was incorrectly parsed as Nikki Haley, and generic surnames
    # like Bennet/Polis/Weiser can match unrelated markets. "trump" remains allowed
    # because it is unusually distinctive in prediction markets.
    "donald trump": "donald_trump",
    "trump": "donald_trump",
    "joe biden": "joe_biden",
    "kamala harris": "kamala_harris",
    "phil weiser": "phil_weiser",
    "michael bennet": "michael_bennet",
    "diana degette": "diana_degette",
    "jared polis": "jared_polis",
    "gavin newsom": "gavin_newsom",
    "ron desantis": "ron_desantis",
    "jd vance": "jd_vance",
    "j.d. vance": "jd_vance",
    "nikki haley": "nikki_haley",
}

CRYPTO_ALIASES = {
    "btc": "bitcoin", "bitcoin": "bitcoin", "xbt": "bitcoin",
    "eth": "ethereum", "ethereum": "ethereum",
    "sol": "solana", "solana": "solana",
    "xrp": "xrp", "ripple": "xrp",
    "doge": "dogecoin", "dogecoin": "dogecoin",
}

SPORT_TEAMS_COMMON = {
    "mexico": "mexico", "brazil": "brazil", "argentina": "argentina",
    "germany": "germany", "france": "france", "spain": "spain",
    "england": "england", "croatia": "croatia", "netherlands": "netherlands",
    "switzerland": "switzerland", "portugal": "portugal",
    "real madrid": "real_madrid", "barcelona": "barcelona",
    "manchester city": "manchester_city", "lakers": "los_angeles_lakers",
    "celtics": "boston_celtics", "yankees": "new_york_yankees",
    "dodgers": "los_angeles_dodgers", "chiefs": "kansas_city_chiefs",
    "eagles": "philadelphia_eagles",
}

STOPWORDS = {
    "will", "the", "and", "that", "this", "with", "from", "have", "has",
    "over", "under", "above", "below", "before", "after", "market", "yes",
    "no", "into", "than", "more", "less", "election", "race", "win", "wins",
    "winner", "party", "candidate", "2024", "2025", "2026", "2027", "2028",
    "2029", "2030",
}

GENERIC_POLITICS_ENTITIES = {
    "democratic", "democrats", "democratic_party", "republican", "republicans",
    "republican_party", "governor", "gubernatorial", "senate", "senator",
    "house", "primary", "general", "election", "race", "party", "margin",
    "victory", "president", "presidential",
}


# -----------------------------
# Utility functions
# -----------------------------















def extract_state(text: str) -> Optional[str]:
    t = normalize_text(text)
    for name, norm in sorted(US_STATES.items(), key=lambda kv: len(kv[0]), reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", t):
            return norm
    for abbr, norm in STATE_ABBR.items():
        if re.search(rf"\b{abbr}\b", text):
            return norm
    return None


def extract_country(text: str, state: Optional[str] = None) -> Optional[str]:
    if state:
        return "usa"
    t = normalize_text(text)
    for alias, norm in sorted(COUNTRY_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", t):
            return norm
    return None


def normalize_person_name(value: str) -> Optional[str]:
    t = normalize_text(value)
    # Remove common titles and trailing market language.
    t = re.sub(r"\b(?:mr|mrs|ms|dr|senator|governor|president)\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" -|'?")
    parts = [w for w in t.split() if w not in STOPWORDS]
    if len(parts) < 2 or len(parts) > 5:
        return None
    if any(w in {"democratic", "republican", "socialist", "party", "people", "candidate"} for w in parts):
        return None
    return "_".join(parts)


def extract_dynamic_candidate(text: str) -> Optional[str]:
    """Extract candidate/person names without requiring a hard-coded alias.

    Handles common forms:
      Will Raphael Glucksmann win ...
      Will Eric Zemmour be elected ...
      ... | Raphael Glucksmann | Raphael Glucksmann | ticker
    """
    original = text or ""
    nt = normalize_text(original)

    # Prefer the subject immediately after "will" and before the action.
    patterns = [
        r"\bwill\s+(.+?)\s+(?:win|be elected|become|secure|receive|get|take)\b",
        r"\bdoes\s+(.+?)\s+(?:win|become|get|receive)\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, nt)
        if m:
            candidate = normalize_person_name(m.group(1))
            if candidate:
                return candidate

    # Kalshi often repeats the candidate in pipe-separated subtitles.
    for part in original.split("|")[1:4]:
        candidate = normalize_person_name(part)
        if candidate:
            return candidate
    return None


def election_stage(text: str) -> str:
    t = normalize_text(text)
    if re.search(bounded_alt("primary", "nomination", "nominee", "select the candidate", "party candidate"), t):
        return "primary"
    if re.search(bounded_alt("general election", "runoff", "second round"), t):
        return "general"
    return "election"


def extract_party(text: str) -> Optional[str]:
    t = normalize_text(text)
    for alias, norm in sorted(PARTY_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", t):
            return norm
    return None


def extract_candidate(text: str) -> Optional[str]:
    t = normalize_text(text)
    for alias, norm in sorted(CANDIDATE_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", t):
            return norm
    return extract_dynamic_candidate(text)


def extract_office(text: str) -> Optional[str]:
    t = normalize_text(text)
    if re.search(bounded_alt("president", "presidential", "white house"), t):
        return "president"
    if re.search(bounded_alt("governor", "gubernatorial"), t):
        return "governor"
    if re.search(bounded_alt("senate", "senator"), t):
        return "senate"
    if re.search(bounded_alt("house", "representative", "congress", "congressional"), t):
        return "house"
    if re.search(bounded_alt("mayor", "mayoral"), t):
        return "mayor"
    return None


def detect_market_type(text: str) -> str:
    t = normalize_text(text)
    if re.search(bounded_alt("margin", "by more than", "by over", "by less than", "spread", r"points?"), t):
        return "margin"
    if re.search(bounded_alt("above", "below", "over", "under", "exceed", "greater than",
                             "less than", "at least", "more than", "fewer than"), t):
        if re.search(r"\$|btc|bitcoin|eth|ethereum|price|market cap", t):
            return "price"
        return "over_under"
    if re.search(bounded_alt("win", "wins", "winner", "elected", "become president",
                             "take control", "party to win"), t):
        return "winner"
    if re.search(bounded_alt("release", "launch", "recognize", "pass", "sign",
                             "resign", "drop out", "withdraw", "nominate"), t):
        return "event"
    return "unknown"


def detect_direction(text: str) -> Optional[str]:
    t = normalize_text(text)
    if re.search(bounded_alt("above", "over", "exceed", "greater than", "more than", "at least"), t):
        return "over"
    if re.search(bounded_alt("below", "under", "less than", "fewer than"), t):
        return "under"
    return None



MONTH_ALIASES = {
    "january": 1, "jan": 1, "february": 2, "feb": 2,
    "march": 3, "mar": 3, "april": 4, "apr": 4, "may": 5,
    "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def detect_comparison(text: str) -> Optional[str]:
    t = normalize_text(text)
    if re.search(bounded_alt("at least", "no less than", "greater than or equal to"), t):
        return "at_least"
    if re.search(bounded_alt("at most", "no more than", "less than or equal to"), t):
        return "at_most"
    if re.search(bounded_alt("above", "over", "exceed", "exceeds", "greater than", "more than"), t):
        return "strictly_above"
    if re.search(bounded_alt("below", "under", "less than", "fewer than"), t):
        return "strictly_below"
    return None


def extract_economic_metric(text: str) -> Optional[str]:
    t = normalize_text(text)
    if re.search(bounded_alt("unemployment rate", "unemployment"), t):
        return "unemployment_rate"
    if re.search(bounded_alt("nonfarm payrolls", "payrolls", "jobs report", "jobs added"), t):
        return "payrolls"
    if re.search(bounded_alt("consumer price index", "cpi", "inflation rate", "inflation"), t):
        return "inflation_rate"
    if re.search(bounded_alt("interest rate", "fed funds rate", "federal funds rate", "rate cut", "rate hike"), t):
        return "interest_rate"
    if re.search(bounded_alt("gross domestic product", "gdp"), t):
        return "gdp"
    return None


def extract_period(text: str) -> Optional[str]:
    t = normalize_text(text)
    year = parse_year(t)

    m = re.search(r"\b(20[2-4][0-9])[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12][0-9]|3[01])\b", t)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    q = re.search(r"\b(?:q([1-4])|([1-4])(?:st|nd|rd|th)? quarter)\b", t)
    if q and year:
        quarter = q.group(1) or q.group(2)
        return f"{year}-Q{quarter}"

    for alias, month in sorted(MONTH_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", t) and year:
            return f"{year}-{month:02d}"

    return str(year) if year else None


def infer_economy_country(text: str) -> Optional[str]:
    country = extract_country(text)
    if country:
        return country
    t = normalize_text(text)
    if re.search(bounded_alt("fed", "federal reserve", "us unemployment", "u s unemployment"), t):
        return "usa"
    return None


def extract_asset(text: str) -> Optional[str]:
    """Extract a crypto asset only when the surrounding text is financial.

    V6.0 was occasionally classifying unrelated Kalshi tickers or names as
    crypto merely because they contained a token such as SOL.
    """
    t = normalize_text(text)
    crypto_context = bool(
        re.search(
            bounded_alt(
                "crypto", "cryptocurrency", "token", "coin", "blockchain",
                "market cap", "price", "etf", "all time high", "ath",
                "bitcoin", "ethereum", "solana", "xrp", "dogecoin"
            ),
            t,
        )
        or "$" in (text or "")
    )

    for alias, norm in sorted(CRYPTO_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
        if not re.search(rf"\b{re.escape(alias)}\b", t):
            continue
        # Full asset names are enough by themselves. Short tickers require context.
        if len(alias) > 3 or crypto_context:
            return norm
    return None


def detect_sport(text: str) -> Optional[str]:
    t = normalize_text(text)
    if re.search(bounded_alt("fifa", "world cup", "soccer", "premier league", "champions league", "laliga", "uefa", "concacaf"), t):
        return "soccer"
    if re.search(bounded_alt("nba", "basketball", "wnba"), t):
        return "basketball"
    if re.search(bounded_alt("nfl", "football", "super bowl"), t):
        return "american_football"
    if re.search(bounded_alt("mlb", "baseball", "world series"), t):
        return "baseball"
    if re.search(bounded_alt("nhl", "hockey", "stanley cup"), t):
        return "hockey"
    if re.search(bounded_alt("tennis", "wimbledon", "us open", "french open", "australian open"), t):
        return "tennis"
    if re.search(bounded_alt("golf", "masters", "pga", "open championship"), t):
        return "golf"
    return None


def extract_teams(text: str) -> Tuple[str, ...]:
    t = normalize_text(text)
    found: Set[str] = set()
    for alias, norm in sorted(SPORT_TEAMS_COMMON.items(), key=lambda kv: len(kv[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", t):
            found.add(norm)
    return tuple(sorted(found))



SPORT_COMPETITIONS = [
    (r"\bhome run derby\b", "home_run_derby", "baseball", "mlb"),
    (r"\bnational league (?:mvp|most valuable player|hank aaron award)\b", "nl_mvp", "baseball", "mlb"),
    (r"\bamerican league (?:mvp|most valuable player|hank aaron award)\b", "al_mvp", "baseball", "mlb"),
    (r"\bnl cy young\b", "nl_cy_young", "baseball", "mlb"),
    (r"\bal cy young\b", "al_cy_young", "baseball", "mlb"),
    (r"\bcy young\b", "cy_young", "baseball", "mlb"),
    (r"\bworld series\b", "world_series", "baseball", "mlb"),
    (r"\b(super bowl)\b", "super_bowl", "american_football", "nfl"),
    (r"\bcollege football playoff\b", "college_football_playoff", "american_football", "ncaa"),
    (r"\bncaa\b|\bcollege football\b", "ncaa_football", "american_football", "ncaa"),
    (r"\bnba finals\b", "nba_finals", "basketball", "nba"),
    (r"\bstanley cup\b", "stanley_cup", "hockey", "nhl"),
    (r"\bballon d[' ]?or\b", "ballon_dor", "soccer", "international"),
    (r"\bchampions league\b", "champions_league", "soccer", "uefa"),
    (r"\bworld cup\b|\bfifa\b", "world_cup", "soccer", "fifa"),
    (r"\bpremier league\b", "premier_league", "soccer", "epl"),
    (r"\bmap [1-9]\b|\bmap winner\b", "map_winner", "esports", "esports"),
    (r"\bmatch winner\b.*\b(esports|valorant|league of legends|counter strike|cs2)\b", "match_winner", "esports", "esports"),
]

LEAGUE_PATTERNS = [
    (r"\bmlb\b|\bmajor league baseball\b", "mlb"),
    (r"\bnfl\b", "nfl"),
    (r"\bnba\b", "nba"),
    (r"\bwnba\b", "wnba"),
    (r"\bnhl\b", "nhl"),
    (r"\bncaa\b|\bcollege football\b|\bcollege basketball\b", "ncaa"),
    (r"\buefa\b|\bchampions league\b", "uefa"),
    (r"\bfifa\b|\bworld cup\b", "fifa"),
    (r"\bvalorant\b|\bleague of legends\b|\bcounter strike\b|\bcs2\b|\besports\b", "esports"),
]


def detect_sports_identity(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return sport, league and exact competition.

    V6.2 prioritizes strong contextual signals before generic aliases. This
    prevents a golfer named "Fifa Laopakdee" from being classified as a FIFA
    World Cup market merely because the person's first name is Fifa.
    """
    t = normalize_text(text)

    # Strong golf context takes priority over names and generic FIFA tokens.
    if re.search(
        bounded_alt(
            "pga", "golf", "3 ball", "3-ball", "three ball",
            "birdies", "bogeys", "front nine", "back nine"
        ),
        t,
    ) or re.search(r"\bkxpga", t):
        if re.search(bounded_alt("round", "matchup", "3 ball", "3-ball", "three ball"), t):
            return "golf", "pga", "golf_round_matchup"
        return "golf", "pga", "golf_tournament"

    identity = get_knowledge_base().resolve_sports_identity(text)
    if identity:
        return identity.sport, identity.league, identity.competition

    for pattern, competition, sport, league in SPORT_COMPETITIONS:
        if re.search(pattern, t):
            return sport, league, competition

    sport = detect_sport(t)
    league = None
    for pattern, normalized in LEAGUE_PATTERNS:
        if re.search(pattern, t):
            league = normalized
            break

    if sport == "baseball" and league is None:
        league = "mlb"
    return sport, league, None


def extract_sports_participant(title: str) -> Optional[str]:
    """Extract a player or team from common winner-question wording.

    V6.0.1 fix:
    - Uses normalize_text(), which already removes accents safely.
    - Does not depend on the undefined ascii_fold/normalize_entity_name helpers.
    """
    plain = normalize_text(title)
    patterns = [
        r"\bwill\s+(.+?)\s+win\b",
        r"\bcan\s+(.+?)\s+win\b",
        r"\bdoes\s+(.+?)\s+win\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, plain, flags=re.IGNORECASE)
        if not match:
            continue

        raw_name = match.group(1).strip(" -|'?")
        parts = [
            token for token in raw_name.split()
            if token not in STOPWORDS
            and token not in {"the", "a", "an"}
        ]

        if 1 <= len(parts) <= 6:
            return "_".join(parts)

    return None


def sports_event_scope(text: str) -> Optional[str]:
    t = normalize_text(text)
    if re.search(r"\bmap\s*[1-9]\b", t):
        m = re.search(r"\bmap\s*([1-9])\b", t)
        return f"map_{m.group(1)}" if m else "map"
    if re.search(r"\bregular season\b", t):
        return "regular_season"
    if re.search(r"\bplayoffs?\b", t):
        return "playoffs"
    if re.search(r"\bfinals?\b", t):
        return "final"
    return None






# -----------------------------
# Cache + fetchers
# -----------------------------

def ensure_cache_dir() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)


def cache_path(name: str) -> str:
    ensure_cache_dir()
    return os.path.join(CACHE_DIR, name)


def load_cache(name: str, ignore_ttl: bool = False) -> Optional[Any]:
    path = cache_path(name)
    if not os.path.exists(path):
        return None
    if not ignore_ttl and time.time() - os.path.getmtime(path) > CACHE_TTL_SECONDS:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_cache(name: str, data: Any) -> None:
    with open(cache_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f)


def request_with_retry(url: str, params: Dict[str, Any]) -> requests.Response:
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 429 or resp.status_code >= 500:
                resp.raise_for_status()
            elif resp.status_code >= 400:
                resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            if attempt == MAX_RETRIES:
                break
            sleep_for = RETRY_BACKOFF_BASE ** attempt
            print(f"[Retry] request failed: {exc}. Retrying in {sleep_for:.1f}s")
            time.sleep(sleep_for)
    raise last_exc


def fetch_kalshi_markets(use_cache: bool = True) -> List[Dict[str, Any]]:
    cached = load_cache("kalshi_markets_v6_1.json") if use_cache else None
    if cached is not None:
        print(f"[Kalshi] Using cache: {len(cached)} raw markets")
        return cached

    markets: List[Dict[str, Any]] = []
    cursor: Optional[str] = None

    try:
        for page in range(1, KALSHI_MAX_PAGES + 1):
            params: Dict[str, Any] = {
                "limit": KALSHI_LIMIT,
                "status": "open",
                "mve_filter": "exclude",
            }
            if cursor:
                params["cursor"] = cursor
            print(f"[Kalshi] Fetching page {page}/{KALSHI_MAX_PAGES}...")
            resp = request_with_retry(KALSHI_API_URL, params)
            data = resp.json()
            page_markets = data.get("markets", [])
            markets.extend(page_markets)
            cursor = data.get("cursor")
            if not cursor or not page_markets:
                break
    except requests.exceptions.RequestException as exc:
        print(f"[Kalshi] live fetch failed: {exc}")
        stale = load_cache("kalshi_markets_v6_1.json", ignore_ttl=True)
        return stale or []

    save_cache("kalshi_markets_v6_1.json", markets)
    print(f"[Kalshi] Raw markets fetched: {len(markets)}")
    return markets


def fetch_polymarket_markets(use_cache: bool = True) -> List[Dict[str, Any]]:
    """Fetch up to 5,000 open Polymarket markets.

    Uses the official keyset endpoint first. If that endpoint returns an HTTP
    error, an unexpected payload, or zero markets, it automatically falls back
    to the standard /markets endpoint with offset pagination.

    The function never discards markets already downloaded because a later
    page fails.
    """
    cache_name = "polymarket_markets_v6_1_keyset.json"
    cached = load_cache(cache_name) if use_cache else None
    if cached is not None and isinstance(cached, list) and cached:
        print(f"[Polymarket] Using cache: {len(cached)} raw markets")
        return cached

    headers = {
        "Accept": "application/json",
        "User-Agent": "prediction-market-arbitrage/6.1",
    }

    def add_unique(
        target: List[Dict[str, Any]],
        seen: Set[str],
        batch: Any,
    ) -> int:
        if not isinstance(batch, list):
            return 0

        added = 0
        for market in batch:
            if not isinstance(market, dict):
                continue
            if market.get("closed") is True:
                continue
            if market.get("active") is False:
                continue

            market_id = str(
                market.get("id")
                or market.get("conditionId")
                or market.get("slug")
                or market.get("question")
                or ""
            )
            if not market_id or market_id in seen:
                continue

            seen.add(market_id)
            target.append(market)
            added += 1

            if len(target) >= POLY_MAX_PAGES * POLY_LIMIT:
                break
        return added

    markets: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    cursor: Optional[str] = None
    keyset_failed = False

    # Official cursor-based endpoint.
    for page in range(1, POLY_MAX_PAGES + 1):
        params: Dict[str, Any] = {
            "limit": min(POLY_LIMIT, 100),
            "closed": "false",
        }
        if cursor:
            params["after_cursor"] = cursor

        print(f"[Polymarket] Keyset page {page}/{POLY_MAX_PAGES}...")

        try:
            resp = requests.get(
                "https://gamma-api.polymarket.com/markets/keyset",
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )

            if resp.status_code == 429 or resp.status_code >= 500:
                resp = request_with_retry(
                    "https://gamma-api.polymarket.com/markets/keyset",
                    params,
                )

            if resp.status_code >= 400:
                print(
                    f"[Polymarket] Keyset HTTP {resp.status_code}: "
                    f"{resp.text[:300]}"
                )
                keyset_failed = True
                break

            payload = resp.json()
            if isinstance(payload, dict):
                batch = payload.get("markets")
                if batch is None:
                    batch = payload.get("data", [])
                next_cursor = payload.get("next_cursor")
            elif isinstance(payload, list):
                batch = payload
                next_cursor = None
            else:
                print(
                    "[Polymarket] Unexpected keyset payload type: "
                    f"{type(payload).__name__}"
                )
                keyset_failed = True
                break

        except (requests.exceptions.RequestException, ValueError) as exc:
            print(f"[Polymarket] Keyset request failed: {exc}")
            keyset_failed = True
            break

        added = add_unique(markets, seen_ids, batch)
        received = len(batch) if isinstance(batch, list) else 0
        print(
            f"[Polymarket] Keyset page {page}: {received} received, "
            f"{added} added, total {len(markets)}"
        )
        if page % 10 == 0:
            print(
                f"[Polymarket] Progress checkpoint: "
                f"{len(markets)}/20000 raw markets"
            )

        if len(markets) >= POLY_MAX_PAGES * POLY_LIMIT:
            break
        if not batch:
            break
        if not next_cursor or str(next_cursor) == cursor:
            break
        cursor = str(next_cursor)

    # Standard endpoint fallback. This is especially useful when keyset
    # pagination is temporarily unavailable or not configured server-side.
    if not markets or keyset_failed:
        print(
            "[Polymarket] Switching to standard /markets pagination "
            f"(currently have {len(markets)} markets)."
        )
        offset = 0

        for page in range(1, POLY_MAX_PAGES + 1):
            params = {
                "limit": min(POLY_LIMIT, 100),
                "offset": offset,
                "active": "true",
                "closed": "false",
            }
            print(f"[Polymarket] Standard page {page}/{POLY_MAX_PAGES}...")

            try:
                resp = requests.get(
                    "https://gamma-api.polymarket.com/markets",
                    params=params,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                )

                if resp.status_code == 429 or resp.status_code >= 500:
                    resp = request_with_retry(
                        "https://gamma-api.polymarket.com/markets",
                        params,
                    )

                if resp.status_code >= 400:
                    print(
                        f"[Polymarket] Standard HTTP {resp.status_code}: "
                        f"{resp.text[:300]}"
                    )
                    break

                payload = resp.json()
                if isinstance(payload, list):
                    batch = payload
                elif isinstance(payload, dict):
                    batch = payload.get("markets", payload.get("data", []))
                else:
                    batch = []

            except (requests.exceptions.RequestException, ValueError) as exc:
                print(f"[Polymarket] Standard request failed: {exc}")
                break

            added = add_unique(markets, seen_ids, batch)
            received = len(batch) if isinstance(batch, list) else 0
            print(
                f"[Polymarket] Standard page {page}: {received} received, "
                f"{added} added, total {len(markets)}"
            )
            if page % 10 == 0:
                print(
                    f"[Polymarket] Progress checkpoint: "
                    f"{len(markets)}/20000 raw markets"
                )

            if len(markets) >= POLY_MAX_PAGES * POLY_LIMIT:
                break
            if not isinstance(batch, list) or len(batch) < min(POLY_LIMIT, 100):
                break
            offset += min(POLY_LIMIT, 100)

    save_cache(cache_name, markets)
    print(f"[Polymarket] Raw markets fetched: {len(markets)}")
    return markets


# -----------------------------
# Price extraction + parsers
# -----------------------------

def extract_kalshi_price(m: Dict[str, Any]) -> MarketPrice:
    yes = safe_float(m.get("yes_ask_dollars"))
    no = safe_float(m.get("no_ask_dollars"))
    if yes is None or yes <= 0:
        yes = safe_float(m.get("yes_bid_dollars"))
    if no is None or no <= 0:
        no = safe_float(m.get("no_bid_dollars"))
    return MarketPrice(yes=yes, no=no)


def extract_polymarket_price(m: Dict[str, Any]) -> MarketPrice:
    outcomes = parse_json_maybe(m.get("outcomes"))
    prices = parse_json_maybe(m.get("outcomePrices"))
    if not isinstance(outcomes, list) or not isinstance(prices, list):
        return MarketPrice()
    lower = [str(o).lower() for o in outcomes]
    try:
        yes_idx = lower.index("yes")
        no_idx = lower.index("no")
    except ValueError:
        return MarketPrice()
    yes = safe_float(prices[yes_idx]) if yes_idx < len(prices) else None
    no = safe_float(prices[no_idx]) if no_idx < len(prices) else None
    return MarketPrice(yes=yes, no=no)



def expand_polymarket_raw_market(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Expand a non-binary Polymarket market into one synthetic binary market per outcome.

    Binary Yes/No markets are returned unchanged. For a market such as
    "Texas Senate Election Winner" with outcomes Ken Paxton and James
    Talarico, this creates two internal contracts:

      Texas Senate Election Winner | Ken Paxton
      Texas Senate Election Winner | James Talarico

    Each synthetic contract has YES equal to the outcome price and NO equal
    to 1 - outcome price. These are scanner-only objects; no trades are placed.
    """
    outcomes = parse_json_maybe(raw.get("outcomes"))
    prices = parse_json_maybe(raw.get("outcomePrices"))

    if not isinstance(outcomes, list) or not isinstance(prices, list):
        return [raw]
    if len(outcomes) != len(prices) or len(outcomes) <= 2:
        return [raw]

    normalized = [normalize_text(str(o)) for o in outcomes]
    if set(normalized) == {"yes", "no"}:
        return [raw]

    parent_id = str(
        raw.get("conditionId")
        or raw.get("id")
        or raw.get("slug")
        or raw.get("question")
        or "poly"
    )

    expanded: List[Dict[str, Any]] = []
    for index, outcome in enumerate(outcomes):
        outcome_price = safe_float(prices[index])
        if outcome_price is None or not (0 < outcome_price < 1):
            continue

        synthetic = dict(raw)
        synthetic["_expanded_outcome"] = str(outcome)
        synthetic["_expanded_source_id"] = f"{parent_id}::outcome::{index}"
        synthetic["_parent_market_id"] = parent_id
        synthetic["outcomes"] = ["Yes", "No"]
        synthetic["outcomePrices"] = [outcome_price, 1.0 - outcome_price]
        expanded.append(synthetic)

    return expanded or [raw]


def parse_market_collection(
    platform: str,
    raw_markets: Sequence[Dict[str, Any]],
) -> List[ParsedMarket]:
    parsed: List[ParsedMarket] = []
    expanded_count = 0

    for raw in raw_markets:
        variants = expand_polymarket_raw_market(raw) if platform == "polymarket" else [raw]
        expanded_count += max(0, len(variants) - 1)
        for variant in variants:
            parsed.append(parse_market(platform, variant))

    if platform == "polymarket":
        print(
            f"[Polymarket] Parsed contracts after outcome expansion: {len(parsed)} "
            f"(synthetic additions: {expanded_count})"
        )
    return parsed


def parse_market(platform: str, raw: Dict[str, Any]) -> ParsedMarket:
    if platform == "kalshi":
        title_parts = [
            raw.get("title") or "",
            raw.get("subtitle") or "",
            raw.get("yes_sub_title") or "",
            raw.get("no_sub_title") or "",
            raw.get("event_ticker") or "",
            raw.get("series_ticker") or "",
        ]
        title = " | ".join([p for p in title_parts if p]).strip()
        source_id = raw.get("ticker") or raw.get("id") or title[:80]
        price = extract_kalshi_price(raw)
    else:
        base_title = raw.get("question") or raw.get("title") or raw.get("slug") or ""
        metadata_parts: List[str] = []

        group_title = raw.get("groupItemTitle") or raw.get("group_item_title")
        outcome_label = raw.get("_expanded_outcome") or raw.get("outcome")

        if group_title and normalize_text(str(group_title)) not in normalize_text(str(base_title)):
            metadata_parts.append(str(group_title))
        if outcome_label and normalize_text(str(outcome_label)) not in normalize_text(str(base_title)):
            metadata_parts.append(str(outcome_label))

        title = " | ".join([str(base_title)] + metadata_parts).strip(" |")
        source_id = (
            raw.get("_expanded_source_id")
            or raw.get("conditionId")
            or raw.get("id")
            or raw.get("slug")
            or title[:80]
        )
        price = extract_polymarket_price(raw)

    pm = ParsedMarket(
        platform=platform,
        source_id=str(source_id),
        title=title,
        raw=raw,
        price=price,
    )
    parse_common(pm)
    return pm


def parse_common(pm: ParsedMarket) -> None:
    source_text = pm.title
    display_text = source_text.split("|", 1)[0].strip()
    nt = normalize_text(display_text)

    # Only human-facing market text determines semantic identity.
    # Tickers and diagnostic metadata may contain accidental tokens such as
    # UCL, SOL, FIFA, etc. and must not classify the market.
    pm.year = parse_year(nt)
    pm.entities = important_words(nt)

    asset = extract_asset(display_text)
    sport, league, competition = detect_sports_identity(display_text)
    office = extract_office(nt)
    party = extract_party(nt)
    state = extract_state(display_text)
    candidate = extract_candidate(display_text)
    country = extract_country(display_text, state)

    if asset:
        parse_crypto(pm, nt, asset)
        return

    # V6: sports must be detected before dynamic person-name extraction can
    # misclassify athletes as political candidates.
    if sport or competition:
        parse_sports(pm, nt, sport or "unknown", league, competition)
        return

    if re.search(
        bounded_alt(
            "fed", "cpi", "inflation", "jobs report", "unemployment",
            "gdp", "interest rate", "payrolls"
        ),
        nt,
    ):
        parse_economy(pm, nt)
        return

    political_signal = bool(
        office
        or party
        or re.search(
            bounded_alt(
                "election", "primary", "governor", "senate", "president",
                "presidential", "democrat", "republican", "gop",
                "parliament", "prime minister", "mayor", "nomination"
            ),
            nt,
        )
    )

    # A person name alone is no longer enough to label a market as politics.
    if political_signal:
        parse_politics(pm, nt, state, party, candidate, office, country)
        return

    pm.category = "other"
    pm.market_type = detect_market_type(nt)
    pm.subtype = "unknown"


def parse_crypto(pm: ParsedMarket, nt: str, asset: str) -> None:
    pm.category = "crypto"
    pm.asset = asset
    pm.market_type = "price" if detect_market_type(nt) in {"price", "over_under"} else detect_market_type(nt)
    pm.subtype = f"{asset}_{pm.market_type}"
    pm.threshold = parse_number(nt)
    pm.direction = detect_direction(nt)


def parse_politics(
    pm: ParsedMarket,
    nt: str,
    state: Optional[str],
    party: Optional[str],
    candidate: Optional[str],
    office: Optional[str],
    country: Optional[str],
) -> None:
    pm.category = "politics"
    pm.country = country
    pm.state = state
    pm.office = office
    pm.party = party
    pm.candidate = candidate

    if re.search(bounded_alt("margin", "by more than", "by over", "by less than", "percentage points?", r"points?"), nt):
        pm.market_type = "margin"
        pm.threshold = parse_number(nt)
        pm.direction = detect_direction(nt)
    elif re.search(bounded_alt("win", "wins", "winner", "elected", "become president", "take control"), nt):
        pm.market_type = "winner"
    elif detect_market_type(nt) == "over_under":
        pm.market_type = "over_under"
        pm.threshold = parse_number(nt)
        pm.direction = detect_direction(nt)
    else:
        pm.market_type = detect_market_type(nt)

    election_kind = election_stage(nt)
    pm.subtype = f"{office or 'unknown_office'}_{election_kind}"



TEAM_COMPETITIONS = {
    "world_series", "super_bowl", "nba_finals", "stanley_cup",
    "champions_league", "premier_league", "college_football_playoff",
}

PLAYER_COMPETITIONS = {
    "home_run_derby", "nl_mvp", "al_mvp", "nl_hank_aaron",
    "al_hank_aaron", "nl_cy_young", "al_cy_young", "cy_young",
    "gold_glove", "silver_slugger", "rookie_of_the_year",
    "ballon_dor", "golf_round_matchup", "golf_tournament",
}




SPORTS_EVENT_KIND_PATTERNS = [
    # Match-level markets
    (r"\bboth teams (?:to )?score\b.*\b1st half\b|\b1st half\b.*\bboth teams (?:to )?score\b", "first_half_btts"),
    (r"\bboth teams (?:to )?score\b|\bbtts\b", "both_teams_to_score"),
    (r"\bmatch winner\b|\bwin the match\b|\bbeat\b|\bdefeat\b", "match_winner"),
    (r"\bmap\s*\d+\b.*\bwin\b|\bwin\b.*\bmap\s*\d+\b", "map_winner"),
    (r"\bseries winner\b|\bwin the series\b", "series_winner"),
    (r"\btotal goals?\b|\bover \d+(?:\.\d+)? goals?\b|\bunder \d+(?:\.\d+)? goals?\b", "total_goals"),
    (r"\bclean sheet\b", "clean_sheet"),
    (r"\bscore first\b|\bfirst goal\b", "first_scorer"),
    (r"\bcorrect score\b", "correct_score"),

    # League/season outcomes
    (r"\brelegat(?:e|ed|ion)\b", "relegation"),
    (r"\bpromot(?:e|ed|ion)\b", "promotion"),
    (r"\bqualif(?:y|ies|ied|ication)\b.*\bchampions league\b|\bchampions league\b.*\bqualif", "champions_league_qualification"),
    (r"\bqualif(?:y|ies|ied|ication)\b.*\bplayoffs?\b|\bplayoffs?\b.*\bqualif", "playoff_qualification"),
    (r"\bwin (?:the )?(?:league|title|championship)\b|\bleague winner\b|\bchampion\b", "championship_winner"),
    (r"\bfinish (?:in )?top 4\b|\btop four\b", "top_four_finish"),
    (r"\bfinish (?:in )?top 6\b|\btop six\b", "top_six_finish"),
    (r"\bfinish last\b|\bbottom of (?:the )?league\b", "finish_last"),
    (r"\bregular season wins?\b", "regular_season_wins"),

    # Individual awards and honors
    (r"\bteam of the year\b|\bpfa team of the year\b", "team_of_the_year"),
    (r"\bgolden boot\b|\btop scorer\b|\bmost goals\b", "top_scorer_award"),
    (r"\bplayer of the year\b|\bmost valuable player\b|\bmvp\b", "mvp_award"),
    (r"\brookie of the year\b", "rookie_of_the_year_award"),
    (r"\bcoach of the year\b|\bmanager of the year\b", "coach_of_the_year"),
    (r"\bdefensive player of the year\b|\bdpoy\b", "defensive_player_of_year"),
    (r"\bcy young\b", "cy_young_award"),
    (r"\bhank aaron award\b", "hank_aaron_award"),
    (r"\bgold glove\b", "gold_glove_award"),
    (r"\bsilver slugger\b", "silver_slugger_award"),
    (r"\bballon d[' ]?or\b", "ballon_dor_award"),

    # Career/roster/status events
    (r"\bretire(?:s|d|ment|ing)?\b", "retirement"),
    (r"\bjoin(?:s|ed|ing)?\b.*\bteam\b|\bsign(?:s|ed|ing)?\b.*\bteam\b", "team_move"),
    (r"\btrad(?:e|es|ed|ing)\b", "trade"),
    (r"\bwaiv(?:e|es|ed|ing)\b|\breleas(?:e|es|ed|ing)\b", "release_or_waiver"),
    (r"\bsuspend(?:s|ed|ing)?\b", "suspension"),
    (r"\binjur(?:y|ed|ies)\b", "injury_status"),
    (r"\breturn(?:s|ed|ing)?\b", "return_to_play"),
    (r"\bfired\b|\bsacked\b|\bdismissed\b", "coach_fired"),

    # Records/statistical milestones
    (r"\bbreak (?:the )?record\b|\bset (?:a |the )?record\b|\brecord more\b", "record_milestone"),
    (r"\bscore \d+\+? points?\b|\bpoints per game\b", "points_milestone"),
    (r"\bscore \d+\+? goals?\b", "goals_milestone"),
    (r"\bhit \d+\+? home runs?\b", "home_runs_milestone"),
    (r"\bwin \d+\+? games?\b", "wins_milestone"),
]


def detect_sports_event_kind(text: str) -> Optional[str]:
    """Return the exact semantic proposition type for a sports market."""
    normalized = normalize_text(text)
    for pattern, event_kind in SPORTS_EVENT_KIND_PATTERNS:
        if re.search(pattern, normalized):
            return event_kind
    return None


SPORTS_EVENT_ACTIONS = [
    (r"\bretire(?:s|d|ment|ing)?\b", "retire"),
    (r"\bjoin(?:s|ed|ing)?\b.*\bteam\b", "join_team"),
    (r"\bsign(?:s|ed|ing)?\b.*\bteam\b", "sign_team"),
    (r"\btrad(?:e|es|ed|ing)\b", "trade"),
    (r"\bwaiv(?:e|es|ed|ing)\b", "waived"),
    (r"\breleas(?:e|es|ed|ing)\b", "released"),
    (r"\bsuspend(?:s|ed|ing)?\b", "suspended"),
    (r"\binjur(?:y|ed|ies)\b", "injury"),
    (r"\bannounce(?:s|d|ment|ing)?\b.*\breturn\b", "return"),
    (r"\breturn(?:s|ed|ing)?\b", "return"),
]


def detect_sports_event_action(text: str) -> Optional[str]:
    normalized = normalize_text(text)
    for pattern, action in SPORTS_EVENT_ACTIONS:
        if re.search(pattern, normalized):
            return action
    return None



def extract_semantic_sports_entity(title: str, event_kind: Optional[str]) -> Optional[str]:
    """Extract the team/player named in common semantic sports propositions."""
    patterns_by_kind = {
        "relegation": [
            r"\bWill\s+(.+?)\s+be relegated\b",
            r"\b(.+?)\s+to be relegated\b",
        ],
        "promotion": [
            r"\bWill\s+(.+?)\s+be promoted\b",
            r"\b(.+?)\s+to be promoted\b",
        ],
        "team_of_the_year": [
            r"\bWill\s+(.+?)\s+be named to\b.*\bTeam of the Year\b",
            r"\bWill\s+(.+?)\s+make\b.*\bTeam of the Year\b",
        ],
        "top_scorer_award": [
            r"\bWill\s+(.+?)\s+(?:win|be)\b.*\b(?:Golden Boot|top scorer)\b",
        ],
        "championship_winner": [
            r"\bWill\s+(.+?)\s+win\b",
        ],
        "top_four_finish": [
            r"\bWill\s+(.+?)\s+finish\b.*\btop 4\b",
        ],
        "top_six_finish": [
            r"\bWill\s+(.+?)\s+finish\b.*\btop 6\b",
        ],
        "champions_league_qualification": [
            r"\bWill\s+(.+?)\s+qualif(?:y|ies)\b",
        ],
    }

    for pattern in patterns_by_kind.get(event_kind or "", []):
        match = re.search(pattern, title, flags=re.IGNORECASE)
        if not match:
            continue
        value = normalize_text(match.group(1)).strip()
        value = re.sub(r"\bthe\b", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        if value and len(value.split()) <= 7:
            return value.replace(" ", "_")
    return None


def extract_sports_event_subject(title: str) -> Optional[str]:
    """Extract the person whose action resolves a generic sports event."""
    patterns = [
        # "... announce that LeBron James is joining ..."
        r"\bthat\s+([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,4})\s+is\s+"
        r"(?:joining|signing|retiring|returning|being traded)",
        # "Will LeBron James retire/join/sign/return ..."
        r"\bWill\s+([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,4})\s+"
        r"(?:retire|join|sign|return|be traded|be released|be suspended)",
        # "LeBron James to retire/join ..."
        r"\b([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,4})\s+to\s+"
        r"(?:retire|join|sign|return|be traded)",
    ]

    for pattern in patterns:
        match = re.search(pattern, title)
        if not match:
            continue
        subject = normalize_text(match.group(1)).replace(" ", "_")
        if subject:
            return subject
    return None


def infer_participant_type(pm: ParsedMarket) -> Optional[str]:
    """Classify the resolution subject for candidate filtering."""
    title = normalize_text(pm.title)

    if pm.event_subject:
        return "player"

    if pm.sport == "golf":
        return "player"

    if pm.event_kind in {
        "team_of_the_year", "top_scorer_award", "mvp_award",
        "rookie_of_the_year_award", "coach_of_the_year",
        "defensive_player_of_year", "cy_young_award",
        "hank_aaron_award", "gold_glove_award",
        "silver_slugger_award", "ballon_dor_award",
    }:
        return "player"

    if pm.event_kind in {
        "relegation", "promotion", "champions_league_qualification",
        "playoff_qualification", "championship_winner",
        "top_four_finish", "top_six_finish", "finish_last",
    }:
        return "team"

    if pm.competition in PLAYER_COMPETITIONS:
        return "player"

    if pm.competition in TEAM_COMPETITIONS:
        return "team"

    if pm.competition == "world_cup":
        if re.search(bounded_alt("uefa", "concacaf", "afc", "caf", "conmebol", "ofc", "europe"), title):
            return "region"
        return "national_team"

    if pm.market_type == "player_prop":
        return "player"

    if pm.teams:
        return "team"

    if pm.player:
        # Most winner markets with a two-word proper name are individual
        # participants unless the exact competition is team-based.
        return "participant"

    return None


def build_event_fingerprint(pm: ParsedMarket) -> str:
    """Build a canonical event identity used for diagnostics and indexing."""
    participant = pm.player or "+".join(sorted(pm.teams))
    fields = [
        pm.category,
        pm.sport,
        pm.league,
        pm.competition,
        pm.event_scope,
        pm.event_kind,
        pm.event_action,
        pm.event_subject,
        pm.participant_type,
        participant,
        str(pm.year or ""),
        pm.market_type,
    ]
    return "|".join(str(value or "") for value in fields)


def parse_sports(
    pm: ParsedMarket,
    nt: str,
    sport: str,
    league: Optional[str] = None,
    competition: Optional[str] = None,
) -> None:
    pm.category = "sports"
    pm.sport = sport
    pm.league = league
    pm.competition = competition
    pm.event_scope = sports_event_scope(pm.title)
    pm.event_kind = detect_sports_event_kind(pm.title)
    pm.event_action = detect_sports_event_action(pm.title)
    pm.event_subject = extract_sports_event_subject(pm.title)
    pm.teams = extract_teams(nt)
    semantic_entity = extract_semantic_sports_entity(
        pm.title,
        pm.event_kind,
    )
    pm.player = (
        semantic_entity
        or extract_sports_participant(pm.title)
        or pm.event_subject
    )
    pm.market_type = detect_market_type(nt)

    prop_pattern = bounded_alt(
        "score or assist", r"assists?", r"points?", r"rebounds?",
        r"threes?", "home runs?", r"strikeouts?", "corners"
    )

    if re.search(prop_pattern, nt) and competition not in {
        "home_run_derby", "nl_mvp", "al_mvp", "cy_young",
        "nl_cy_young", "al_cy_young"
    }:
        pm.market_type = "player_prop"
    elif re.search(bounded_alt("win", "wins", "winner", "beat", "defeat"), nt):
        pm.market_type = "winner"
    elif pm.market_type == "unknown":
        pm.market_type = "event"

    pm.subtype = competition or f"{sport}_{pm.market_type}"
    pm.participant_type = infer_participant_type(pm)
    pm.event_fingerprint = build_event_fingerprint(pm)

    if pm.competition is None:
        pm.parser_notes.append("sports_missing_competition")
    if pm.market_type == "winner" and not (pm.player or pm.teams):
        pm.parser_notes.append("sports_missing_participant")
    if pm.participant_type is None:
        pm.parser_notes.append("sports_missing_participant_type")


def parse_economy(pm: ParsedMarket, nt: str) -> None:
    pm.category = "economy"
    pm.metric = extract_economic_metric(pm.title)
    pm.country = infer_economy_country(pm.title)
    pm.period = extract_period(pm.title)
    pm.comparison = detect_comparison(pm.title)
    pm.resolution_scope = pm.period

    if pm.metric == "inflation_rate":
        pm.subtype = "inflation"
    elif pm.metric == "interest_rate":
        pm.subtype = "fed_rates"
    elif pm.metric in {"unemployment_rate", "payrolls"}:
        pm.subtype = "jobs"
    elif pm.metric == "gdp":
        pm.subtype = "gdp"
    else:
        pm.subtype = "economy_unknown"

    pm.market_type = detect_market_type(nt)
    pm.threshold = parse_number(nt)
    pm.direction = detect_direction(nt)

    if pm.country is None:
        pm.parser_notes.append("economy_missing_country")
    if pm.metric is None:
        pm.parser_notes.append("economy_missing_metric")
    if pm.period is None:
        pm.parser_notes.append("economy_missing_period")
    if pm.market_type == "over_under" and pm.comparison is None:
        pm.parser_notes.append("economy_missing_comparison")


# -----------------------------
# V6 multi-index candidate generator
# -----------------------------

def index_keys(m: ParsedMarket) -> Set[str]:
    """Loose multi-index keys. A market can live in many buckets."""
    keys: Set[str] = set()
    if m.category == "other" or m.market_type == "unknown":
        return keys

    keys.add(f"cat|{m.category}")
    keys.add(f"type|{m.category}|{m.market_type}")

    if m.year:
        keys.add(f"year|{m.category}|{m.year}")

    if m.category == "politics":
        if m.country:
            keys.add(f"pol|country|{m.country}")
        if m.state:
            keys.add(f"pol|state|{m.state}")
        if m.office:
            keys.add(f"pol|office|{m.office}")
        if m.subtype != "unknown":
            keys.add(f"pol|subtype|{m.subtype}")
        if m.party:
            keys.add(f"pol|party|{m.party}")
        if m.candidate:
            keys.add(f"pol|candidate|{m.candidate}")
        if m.state and m.office:
            keys.add(f"pol|stateoffice|{m.state}|{m.office}")
        if m.state and m.year:
            keys.add(f"pol|stateyear|{m.state}|{m.year}")
        if m.office and m.year:
            keys.add(f"pol|officeyear|{m.office}|{m.year}")

    elif m.category == "crypto":
        if m.asset:
            keys.add(f"crypto|asset|{m.asset}")
        if m.asset and m.market_type:
            keys.add(f"crypto|assettype|{m.asset}|{m.market_type}")
        if m.asset and m.threshold:
            keys.add(f"crypto|assetthreshold|{m.asset}|{round(m.threshold, 2)}")

    elif m.category == "sports":
        if m.sport:
            keys.add(f"sports|sport|{m.sport}")
        if m.league:
            keys.add(f"sports|league|{m.league}")
        if m.competition:
            keys.add(f"sports|competition|{m.competition}")
        if m.event_scope:
            keys.add(f"sports|scope|{m.event_scope}")
        if m.event_kind:
            keys.add(f"sports|eventkind|{m.event_kind}")
        if m.event_kind and m.year:
            keys.add(f"sports|eventkindyear|{m.event_kind}|{m.year}")
        if m.event_action:
            keys.add(f"sports|action|{m.event_action}")
        if m.event_subject:
            keys.add(f"sports|subject|{m.event_subject}")
        if m.event_action and m.event_subject:
            keys.add(
                f"sports|actionsubject|{m.event_action}|{m.event_subject}"
            )
        for team in m.teams:
            keys.add(f"sports|team|{team}")
        if m.player:
            keys.add(f"sports|player|{m.player}")
        if m.sport and m.market_type:
            keys.add(f"sports|sporttype|{m.sport}|{m.market_type}")
        if m.participant_type:
            keys.add(f"sports|participanttype|{m.participant_type}")
        if m.competition and m.player:
            keys.add(f"sports|competitionplayer|{m.competition}|{m.player}")
        if m.competition and m.participant_type:
            keys.add(
                f"sports|competitiontype|{m.competition}|{m.participant_type}"
            )
        if m.competition and m.year:
            keys.add(f"sports|competitionyear|{m.competition}|{m.year}")
        if m.league and m.year:
            keys.add(f"sports|leagueyear|{m.league}|{m.year}")
        if m.event_fingerprint:
            keys.add(f"sports|fingerprint|{m.event_fingerprint}")

    elif m.category == "economy":
        keys.add(f"economy|subtype|{m.subtype}")
        if m.metric:
            keys.add(f"economy|metric|{m.metric}")
        if m.country:
            keys.add(f"economy|country|{m.country}")
        if m.period:
            keys.add(f"economy|period|{m.period}")
        if m.comparison:
            keys.add(f"economy|comparison|{m.comparison}")
        if m.threshold is not None:
            keys.add(f"economy|threshold|{round(m.threshold, 3)}")
        if m.country and m.metric:
            keys.add(f"economy|countrymetric|{m.country}|{m.metric}")
        if m.metric and m.period:
            keys.add(f"economy|metricperiod|{m.metric}|{m.period}")

    # Add non-generic entities as weak paths.
    for e in m.entities:
        if m.category == "politics" and e in GENERIC_POLITICS_ENTITIES:
            continue
        if len(e) > 3:
            keys.add(f"entity|{m.category}|{e}")

    return keys


def build_index(markets: Sequence[ParsedMarket]) -> Dict[str, List[ParsedMarket]]:
    idx: Dict[str, List[ParsedMarket]] = {}
    for m in markets:
        for key in index_keys(m):
            idx.setdefault(key, []).append(m)
    return idx



def candidate_compatible(k: ParsedMarket, p: ParsedMarket) -> bool:
    """Cheap hard filters applied before full scoring.

    This prevents obviously unrelated markets from becoming debug candidates,
    while retaining pairs with incomplete metadata for REVIEW.
    """
    if k.category != p.category or k.market_type != p.market_type:
        return False

    if k.year and p.year and k.year != p.year:
        return False

    if k.category == "sports":
        if k.sport and p.sport and k.sport != p.sport:
            return False
        if k.league and p.league and k.league != p.league:
            return False
        if k.competition and p.competition and k.competition != p.competition:
            return False
        if (
            k.participant_type
            and p.participant_type
            and k.participant_type != p.participant_type
        ):
            return False
        if k.event_scope and p.event_scope and k.event_scope != p.event_scope:
            return False
        if k.event_kind and p.event_kind and k.event_kind != p.event_kind:
            return False

        # For generic event markets, a known event kind on only one side is
        # insufficient evidence of equivalence. Do not generate the pair.
        if k.market_type == "event" and p.market_type == "event":
            if bool(k.event_kind) != bool(p.event_kind):
                return False

        if k.event_action and p.event_action and k.event_action != p.event_action:
            return False
        if k.event_subject and p.event_subject and k.event_subject != p.event_subject:
            return False

        # Generic event markets require compatible semantic identity.
        if (
            k.market_type == "event"
            and p.market_type == "event"
            and not k.competition
            and not p.competition
        ):
            if k.event_kind or p.event_kind:
                if not k.event_kind or not p.event_kind:
                    return False
                if k.event_kind != p.event_kind:
                    return False

            if k.event_action or p.event_action:
                if not k.event_action or not p.event_action:
                    return False
                if k.event_action != p.event_action:
                    return False

            if k.event_subject or p.event_subject:
                if not k.event_subject or not p.event_subject:
                    return False
                if k.event_subject != p.event_subject:
                    return False

        # When both participants are known, require identity before full scoring.
        if k.player and p.player and k.player != p.player:
            return False
        if k.teams and p.teams and set(k.teams) != set(p.teams):
            return False

    elif k.category == "politics":
        if k.country and p.country and k.country != p.country:
            return False
        if k.state and p.state and k.state != p.state:
            return False
        if k.office and p.office and k.office != p.office:
            return False
        if k.candidate and p.candidate and k.candidate != p.candidate:
            return False

    elif k.category == "crypto":
        if k.asset and p.asset and k.asset != p.asset:
            return False

    elif k.category == "economy":
        if k.metric and p.metric and k.metric != p.metric:
            return False
        if k.country and p.country and k.country != p.country:
            return False
        if k.period and p.period and k.period != p.period:
            return False

    return True


def candidate_pairs(kalshi: Sequence[ParsedMarket], poly: Sequence[ParsedMarket]) -> List[CandidatePair]:
    poly_index = build_index(poly)
    raw_scores: Dict[Tuple[str, str], Tuple[ParsedMarket, ParsedMarket, int]] = {}

    for k in kalshi:
        keys = index_keys(k)
        if not keys:
            continue

        for key in keys:
            for p in poly_index.get(key, []):
                if not candidate_compatible(k, p):
                    continue
                pair_id = (k.source_id, p.source_id)
                if pair_id not in raw_scores:
                    raw_scores[pair_id] = (k, p, 0)
                old_k, old_p, hits = raw_scores[pair_id]
                raw_scores[pair_id] = (old_k, old_p, hits + 1)

    pairs = [
        CandidatePair(k, p, hits)
        for (k_id, p_id), (k, p, hits) in raw_scores.items()
        if hits >= min_bucket_hits(k, p)
    ]

    return sorted(pairs, key=lambda cp: cp.bucket_hits, reverse=True)


def min_bucket_hits(k: ParsedMarket, p: ParsedMarket) -> int:
    # Politics needs at least two common routes unless a candidate matches.
    if k.category == "politics":
        if k.candidate and p.candidate and k.candidate == p.candidate:
            return 1
        return 2
    if k.category == "sports":
        if (
            k.competition and p.competition
            and k.competition == p.competition
            and k.player and p.player
            and k.player == p.player
        ):
            return 1
        return 2
    return 1


# -----------------------------
# Compatibility + scoring
# -----------------------------

def fuzzy_score(a: str, b: str) -> int:
    if fuzz is None:
        return 0
    return int(fuzz.token_set_ratio(a, b))


def compare_markets(k: ParsedMarket, p: ParsedMarket, bucket_hits: int = 0) -> MatchResult:
    reasons: List[str] = []
    rejects: List[str] = []
    score = 0

    if k.category != p.category:
        return MatchResult(k, p, 0, False, reasons, [f"category mismatch: {k.category} vs {p.category}"], bucket_hits)

    if k.category == "other":
        return MatchResult(k, p, 0, False, reasons, ["category is other"], bucket_hits)

    score += 10
    reasons.append(f"same category: {k.category} (+10)")

    # Hard rule: don't compare different resolution types.
    if k.market_type != p.market_type:
        return MatchResult(
            k, p, 0, False, reasons,
            [f"market_type mismatch: {k.market_type} vs {p.market_type}"],
            bucket_hits
        )

    score += 20
    reasons.append(f"same market_type: {k.market_type} (+20)")

    if k.category == "politics":
        extra, ok, rs, rj = score_politics(k, p)
    elif k.category == "crypto":
        extra, ok, rs, rj = score_crypto(k, p)
    elif k.category == "sports":
        extra, ok, rs, rj = score_sports(k, p)
    elif k.category == "economy":
        extra, ok, rs, rj = score_economy(k, p)
    else:
        extra, ok, rs, rj = (0, False, [], ["unsupported category"])

    score += extra
    reasons.extend(rs)
    rejects.extend(rj)

    if not ok:
        return MatchResult(k, p, score, False, reasons, rejects, bucket_hits)

    # Bucket evidence matters but cannot carry a weak match by itself.
    if bucket_hits >= 4:
        score += 5
        reasons.append(f"multiple bucket hits: {bucket_hits} (+5)")
    elif bucket_hits >= 2:
        score += 2
        reasons.append(f"bucket hits: {bucket_hits} (+2)")

    fz = fuzzy_score(k.title, p.title)
    if fz >= 85:
        score += 6
        reasons.append(f"high fuzzy title similarity: {fz} (+6)")
    elif fz >= 70:
        score += 3
        reasons.append(f"medium fuzzy title similarity: {fz} (+3)")
    else:
        reasons.append(f"low fuzzy title similarity: {fz} (+0)")

    confidence = min(score, 100)
    accepted = confidence >= MIN_MATCH_CONFIDENCE
    if not accepted:
        rejects.append(f"confidence below threshold: {confidence} < {MIN_MATCH_CONFIDENCE}")

    return MatchResult(k, p, confidence, accepted, reasons, rejects, bucket_hits)


def score_politics(k: ParsedMarket, p: ParsedMarket) -> Tuple[int, bool, List[str], List[str]]:
    score = 0
    reasons: List[str] = []
    rejects: List[str] = []

    # Hard incompatibilities.
    if k.office and p.office and k.office != p.office:
        rejects.append(f"office mismatch: {k.office} vs {p.office}")
        return score, False, reasons, rejects

    if k.country and p.country and k.country != p.country:
        rejects.append(f"country mismatch: {k.country} vs {p.country}")
        return score, False, reasons, rejects

    # A party primary/nomination and a general-election winner do not resolve alike.
    k_stage = k.subtype.rsplit("_", 1)[-1] if k.subtype else "election"
    p_stage = p.subtype.rsplit("_", 1)[-1] if p.subtype else "election"
    if {k_stage, p_stage} & {"primary"} and k_stage != p_stage:
        rejects.append(f"election stage mismatch: {k_stage} vs {p_stage}")
        return score, False, reasons, rejects

    if k.state and p.state and k.state != p.state:
        rejects.append(f"state mismatch: {k.state} vs {p.state}")
        return score, False, reasons, rejects

    if k.year and p.year and abs(k.year - p.year) > 0:
        rejects.append(f"year mismatch: {k.year} vs {p.year}")
        return score, False, reasons, rejects

    # State-level offices require a state on both sides.
    state_level = {"governor", "senate", "house"}
    if (k.office in state_level or p.office in state_level) and not (k.state and p.state):
        rejects.append("state required for state-level political market")
        return score, False, reasons, rejects

    if k.office and p.office and k.office == p.office:
        score += 15
        reasons.append(f"same office: {k.office} (+15)")
    elif k.office or p.office:
        rejects.append("one side missing office")
        return score, False, reasons, rejects

    if k.country and p.country and k.country == p.country:
        score += 10
        reasons.append(f"same country: {k.country} (+10)")

    if k.state and p.state and k.state == p.state:
        score += 20
        reasons.append(f"same state: {k.state} (+20)")

    if k.year and p.year and k.year == p.year:
        score += 10
        reasons.append(f"same year: {k.year} (+10)")
    elif k.year or p.year:
        score += 2
        reasons.append("only one side has year (+2)")

    # Candidate-specific markets cannot match generic party markets.
    if k.candidate and p.candidate:
        if k.candidate != p.candidate:
            rejects.append(f"candidate mismatch: {k.candidate} vs {p.candidate}")
            return score, False, reasons, rejects
        score += 25
        reasons.append(f"same candidate: {k.candidate} (+25)")
    elif k.candidate or p.candidate:
        rejects.append("candidate-specific market vs non-candidate market")
        return score, False, reasons, rejects
    elif k.party and p.party:
        if k.party != p.party:
            rejects.append(f"party mismatch: {k.party} vs {p.party}")
            return score, False, reasons, rejects
        score += 15
        reasons.append(f"same party: {k.party} (+15)")
    else:
        rejects.append("politics market lacks candidate or party match")
        return score, False, reasons, rejects

    if k.market_type in {"margin", "over_under", "price"}:
        if k.threshold is None or p.threshold is None:
            rejects.append("threshold required for margin/over_under/price")
            return score, False, reasons, rejects
        if abs(k.threshold - p.threshold) > 0.001:
            rejects.append(f"threshold mismatch: {k.threshold} vs {p.threshold}")
            return score, False, reasons, rejects
        score += 15
        reasons.append(f"same threshold: {k.threshold} (+15)")

    return score, True, reasons, rejects


def score_crypto(k: ParsedMarket, p: ParsedMarket) -> Tuple[int, bool, List[str], List[str]]:
    score = 0
    reasons: List[str] = []
    rejects: List[str] = []

    if not k.asset or not p.asset or k.asset != p.asset:
        rejects.append(f"asset mismatch: {k.asset} vs {p.asset}")
        return score, False, reasons, rejects

    score += 25
    reasons.append(f"same asset: {k.asset} (+25)")

    if k.market_type == "price":
        if k.threshold is None or p.threshold is None:
            rejects.append("price market missing threshold")
            return score, False, reasons, rejects
        tolerance = max(1.0, 0.001 * max(k.threshold, p.threshold))
        if abs(k.threshold - p.threshold) > tolerance:
            rejects.append(f"threshold mismatch: {k.threshold} vs {p.threshold}")
            return score, False, reasons, rejects
        score += 25
        reasons.append(f"same price threshold: {k.threshold:g} (+25)")

        if k.direction and p.direction and k.direction != p.direction:
            rejects.append(f"direction mismatch: {k.direction} vs {p.direction}")
            return score, False, reasons, rejects
        if k.direction and p.direction:
            score += 15
            reasons.append(f"same direction: {k.direction} (+15)")

    if k.year and p.year:
        if k.year != p.year:
            rejects.append(f"year mismatch: {k.year} vs {p.year}")
            return score, False, reasons, rejects
        score += 10
        reasons.append(f"same year: {k.year} (+10)")

    return score, True, reasons, rejects


def score_sports(k: ParsedMarket, p: ParsedMarket) -> Tuple[int, bool, List[str], List[str]]:
    score = 0
    reasons: List[str] = []
    rejects: List[str] = []

    if not k.sport or not p.sport or k.sport != p.sport:
        rejects.append(f"sport mismatch: {k.sport} vs {p.sport}")
        return score, False, reasons, rejects
    score += 15
    reasons.append(f"same sport: {k.sport} (+15)")

    if k.league and p.league:
        if k.league != p.league:
            rejects.append(f"league mismatch: {k.league} vs {p.league}")
            return score, False, reasons, rejects
        score += 15
        reasons.append(f"same league: {k.league} (+15)")
    elif k.league or p.league:
        score += 3
        reasons.append(f"one side missing league metadata: {k.league} vs {p.league} (+3)")


    if k.participant_type and p.participant_type:
        if k.participant_type != p.participant_type:
            rejects.append(
                f"participant_type mismatch: "
                f"{k.participant_type} vs {p.participant_type}"
            )
            return score, False, reasons, rejects
        score += 10
        reasons.append(
            f"same participant_type: {k.participant_type} (+10)"
        )

    if k.event_kind or p.event_kind:
        if not k.event_kind or not p.event_kind:
            rejects.append(
                f"one side missing event_kind: {k.event_kind} vs {p.event_kind}"
            )
            return score, False, reasons, rejects
        if k.event_kind != p.event_kind:
            rejects.append(
                f"event_kind mismatch: {k.event_kind} vs {p.event_kind}"
            )
            return score, False, reasons, rejects
        score += 25
        reasons.append(f"same event_kind: {k.event_kind} (+25)")

    if k.event_action or p.event_action:
        if not k.event_action or not p.event_action:
            rejects.append(
                f"one side missing event_action: "
                f"{k.event_action} vs {p.event_action}"
            )
            return score, False, reasons, rejects
        if k.event_action != p.event_action:
            rejects.append(
                f"event_action mismatch: {k.event_action} vs {p.event_action}"
            )
            return score, False, reasons, rejects
        score += 20
        reasons.append(f"same event_action: {k.event_action} (+20)")

    if k.event_subject or p.event_subject:
        if not k.event_subject or not p.event_subject:
            rejects.append(
                f"one side missing event_subject: "
                f"{k.event_subject} vs {p.event_subject}"
            )
            return score, False, reasons, rejects
        if k.event_subject != p.event_subject:
            rejects.append(
                f"event_subject mismatch: "
                f"{k.event_subject} vs {p.event_subject}"
            )
            return score, False, reasons, rejects
        score += 20
        reasons.append(f"same event_subject: {k.event_subject} (+20)")

    # Home Run Derby, MVP, Cy Young, World Series, etc. are different
    # resolution events even when the same athlete appears.
    if k.competition and p.competition:
        if k.competition != p.competition:
            rejects.append(f"competition mismatch: {k.competition} vs {p.competition}")
            return score, False, reasons, rejects
        score += 25
        reasons.append(f"same competition: {k.competition} (+25)")
    elif k.competition or p.competition:
        # Missing metadata is allowed into REVIEW only when every other
        # identity field agrees. A conflicting competition remains a hard reject.
        score += 5
        reasons.append(
            f"one side missing competition metadata: {k.competition} vs {p.competition} (+5)"
        )
    else:
        score += 0
        reasons.append("both sides missing competition metadata (+0)")

    if k.event_scope or p.event_scope:
        if k.event_scope != p.event_scope:
            rejects.append(f"event scope mismatch: {k.event_scope} vs {p.event_scope}")
            return score, False, reasons, rejects
        score += 5
        reasons.append(f"same event scope: {k.event_scope} (+5)")

    if k.player or p.player:
        if not k.player or not p.player or k.player != p.player:
            rejects.append(f"participant mismatch: {k.player} vs {p.player}")
            return score, False, reasons, rejects
        score += 25
        reasons.append(f"same participant: {k.player} (+25)")
    elif k.teams or p.teams:
        if not k.teams or not p.teams or set(k.teams) != set(p.teams):
            rejects.append(f"teams mismatch: {k.teams} vs {p.teams}")
            return score, False, reasons, rejects
        score += 25
        reasons.append(f"same teams: {', '.join(k.teams)} (+25)")
    else:
        rejects.append("sports market missing participant/team identity")
        return score, False, reasons, rejects

    if k.year and p.year:
        if k.year != p.year:
            rejects.append(f"year mismatch: {k.year} vs {p.year}")
            return score, False, reasons, rejects
        score += 10
        reasons.append(f"same year: {k.year} (+10)")
    elif k.year or p.year:
        rejects.append(f"one side missing year: {k.year} vs {p.year}")
        return score, False, reasons, rejects

    return score, True, reasons, rejects


def score_economy(k: ParsedMarket, p: ParsedMarket) -> Tuple[int, bool, List[str], List[str]]:
    score = 0
    reasons: List[str] = []
    rejects: List[str] = []

    if not k.metric or not p.metric:
        rejects.append(f"economic metric required: {k.metric} vs {p.metric}")
        return score, False, reasons, rejects
    if k.metric != p.metric:
        rejects.append(f"economic metric mismatch: {k.metric} vs {p.metric}")
        return score, False, reasons, rejects
    score += 20
    reasons.append(f"same economic metric: {k.metric} (+20)")

    if not k.country or not p.country:
        rejects.append(f"country required for economic market: {k.country} vs {p.country}")
        return score, False, reasons, rejects
    if k.country != p.country:
        rejects.append(f"country mismatch: {k.country} vs {p.country}")
        return score, False, reasons, rejects
    score += 20
    reasons.append(f"same country: {k.country} (+20)")

    if not k.period or not p.period:
        rejects.append(f"exact period required: {k.period} vs {p.period}")
        return score, False, reasons, rejects
    if k.period != p.period:
        rejects.append(f"period mismatch: {k.period} vs {p.period}")
        return score, False, reasons, rejects
    score += 15
    reasons.append(f"same period: {k.period} (+15)")

    if k.subtype != p.subtype:
        rejects.append(f"economy subtype mismatch: {k.subtype} vs {p.subtype}")
        return score, False, reasons, rejects
    score += 10
    reasons.append(f"same economy subtype: {k.subtype} (+10)")

    if k.market_type == "over_under":
        if not k.comparison or not p.comparison:
            rejects.append(f"comparison operator required: {k.comparison} vs {p.comparison}")
            return score, False, reasons, rejects
        if k.comparison != p.comparison:
            rejects.append(f"comparison mismatch: {k.comparison} vs {p.comparison}")
            return score, False, reasons, rejects
        score += 15
        reasons.append(f"same comparison: {k.comparison} (+15)")

    if k.threshold is None or p.threshold is None:
        rejects.append(f"threshold required: {k.threshold} vs {p.threshold}")
        return score, False, reasons, rejects
    if abs(k.threshold - p.threshold) > 0.001:
        rejects.append(f"threshold mismatch: {k.threshold} vs {p.threshold}")
        return score, False, reasons, rejects
    score += 20
    reasons.append(f"same threshold: {k.threshold} (+20)")

    return score, True, reasons, rejects


def is_review_candidate(match: MatchResult) -> bool:
    """Return True only for compatible pairs that missed acceptance by score.

    Hard mismatches such as different competition, candidate, country,
    threshold or period are never placed in REVIEW.
    """
    if match.accepted or match.confidence < REVIEW_MIN_CONFIDENCE:
        return False
    if not match.rejects:
        return True
    return all(reason.startswith("confidence below threshold:") for reason in match.rejects)


def find_matches(
    kalshi: Sequence[ParsedMarket],
    poly: Sequence[ParsedMarket],
) -> Tuple[List[MatchResult], List[MatchResult], List[MatchResult]]:
    pairs = candidate_pairs(kalshi, poly)
    print(f"[Matcher] Candidate pairs generated: {len(pairs)}")

    all_scored: List[MatchResult] = []
    accepted: List[MatchResult] = []
    review: List[MatchResult] = []

    for cp in pairs:
        match = compare_markets(cp.kalshi, cp.polymarket, cp.bucket_hits)
        all_scored.append(match)
        if match.accepted:
            accepted.append(match)
        elif is_review_candidate(match):
            review.append(match)

    all_scored.sort(key=lambda m: (m.confidence, m.bucket_hits), reverse=True)
    accepted.sort(key=lambda m: (m.confidence, m.bucket_hits), reverse=True)
    review.sort(key=lambda m: (m.confidence, m.bucket_hits), reverse=True)

    print(f"[Matcher] Candidate comparisons: {len(all_scored)}")
    print(f"[Matcher] Review candidates: {len(review)}")
    return accepted, review, all_scored


# -----------------------------
# Arbitrage
# -----------------------------

def require_price(mp: MarketPrice) -> Tuple[float, float]:
    if mp.yes is None or mp.no is None:
        raise ValueError("Expected tradeable price")
    return mp.yes, mp.no


def calculate_arbitrage(matches: Sequence[MatchResult]) -> List[ArbitrageOpportunity]:
    opps: List[ArbitrageOpportunity] = []
    for m in matches:
        k = m.kalshi
        p = m.polymarket
        if not k.price.is_tradeable() or not p.price.is_tradeable():
            continue

        k_yes, k_no = require_price(k.price)
        p_yes, p_no = require_price(p.price)

        cost1 = k_yes + p_no
        if cost1 < 1 - MIN_ARBITRAGE_PROFIT:
            opps.append(ArbitrageOpportunity(m, "YES Kalshi + NO Polymarket", cost1, 1 - cost1))

        cost2 = p_yes + k_no
        if cost2 < 1 - MIN_ARBITRAGE_PROFIT:
            opps.append(ArbitrageOpportunity(m, "YES Polymarket + NO Kalshi", cost2, 1 - cost2))

    return sorted(opps, key=lambda o: o.gross_profit, reverse=True)


# -----------------------------
# Output
# -----------------------------

def fmt_price(v: Optional[float]) -> str:
    return "N/A" if v is None else f"${v:.4f}"


def compact_fields(m: ParsedMarket) -> str:
    d = {
        "category": m.category,
        "market_type": m.market_type,
        "subtype": m.subtype,
        "state": m.state,
        "office": m.office,
        "candidate": m.candidate,
        "party": m.party,
        "year": m.year,
        "country": m.country,
        "asset": m.asset,
        "threshold": m.threshold,
        "direction": m.direction,
        "metric": m.metric,
        "comparison": m.comparison,
        "period": m.period,
        "resolution_scope": m.resolution_scope,
        "sport": m.sport,
        "league": m.league,
        "competition": m.competition,
        "event_scope": m.event_scope,
        "event_kind": m.event_kind,
        "event_action": m.event_action,
        "event_subject": m.event_subject,
        "participant_type": m.participant_type,
        "event_fingerprint": m.event_fingerprint,
        "market_intent": m.market_intent,
        "entity_key": m.entity_key,
        "event_object_key": m.event_object_key,
        "resolution_type": m.resolution_type,
        "resolution_time": m.resolution_time,
        "deadline": m.deadline,
        "lower_bound": m.lower_bound,
        "upper_bound": m.upper_bound,
        "teams": m.teams,
        "player": m.player,
    }
    d = {k: v for k, v in d.items() if v not in (None, "", (), "unknown")}
    return json.dumps(d, ensure_ascii=False, sort_keys=True)


def print_market_summary(label: str, markets: Sequence[ParsedMarket]) -> None:
    counts: Dict[str, int] = {}
    tradeable = 0
    for m in markets:
        counts[m.category] = counts.get(m.category, 0) + 1
        if m.price.is_tradeable():
            tradeable += 1
    print(f"\n{label}: {len(markets)} parsed markets ({tradeable} tradeable)")
    for cat, n in sorted(counts.items(), key=lambda kv: kv[0]):
        print(f"  - {cat}: {n}")


def print_match(m: MatchResult, idx: int, label: str = "MATCH") -> None:
    print("=" * 80)
    print(f"{label} #{idx} | Confidence: {m.confidence}/100 | Bucket hits: {m.bucket_hits}")
    print(f"Kalshi:     {m.kalshi.title}")
    print(f"Polymarket: {m.polymarket.title}")
    print(f"Kalshi price: Y={fmt_price(m.kalshi.price.yes)} N={fmt_price(m.kalshi.price.no)}")
    print(f"Poly price:   Y={fmt_price(m.polymarket.price.yes)} N={fmt_price(m.polymarket.price.no)}")
    print(f"Kalshi fields: {compact_fields(m.kalshi)}")
    print(f"Poly fields:   {compact_fields(m.polymarket)}")
    print("Reasons:")
    for r in m.reasons[:8]:
        print(f"  ✓ {r}")
    if m.rejects:
        print("Rejects:")
        for r in m.rejects[:6]:
            print(f"  ✗ {r}")


def print_arbitrage(o: ArbitrageOpportunity, idx: int) -> None:
    print("#" * 80)
    print(f"ARBITRAGE #{idx} | Gross profit: {o.gross_profit*100:.2f}% | Cost: {o.cost:.4f}")
    print(f"Trade: {o.trade}")
    print(f"Confidence: {o.match.confidence}/100")
    print(f"Kalshi:     {o.match.kalshi.title}")
    print(f"Polymarket: {o.match.polymarket.title}")
    print(f"Kalshi price: Y={fmt_price(o.match.kalshi.price.yes)} N={fmt_price(o.match.kalshi.price.no)}")
    print(f"Poly price:   Y={fmt_price(o.match.polymarket.price.yes)} N={fmt_price(o.match.polymarket.price.no)}")


# -----------------------------
# Main
# -----------------------------

def run_scan(use_cache: bool = True) -> None:
    print("Prediction Market Arbitrage Scanner V6")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print("Mode: V6.1 outcome expansion + review matching")

    kalshi_raw = fetch_kalshi_markets(use_cache=use_cache)
    poly_raw = fetch_polymarket_markets(use_cache=use_cache)

    kalshi = parse_market_collection("kalshi", kalshi_raw)
    poly = parse_market_collection("polymarket", poly_raw)

    print_market_summary("Kalshi", kalshi)
    print_market_summary("Polymarket", poly)

    matches, review_matches, candidates = find_matches(kalshi, poly)

    print(f"\nAccepted matches: {len(matches)}")
    for i, match in enumerate(matches[:SHOW_TOP_MATCHES], 1):
        print_match(match, i)

    print(f"\nReview matches ({REVIEW_MIN_CONFIDENCE}-{MIN_MATCH_CONFIDENCE - 1}): {len(review_matches)}")
    for i, match in enumerate(review_matches[:SHOW_TOP_CANDIDATES], 1):
        print_match(match, i, label="REVIEW")

    if not matches and not review_matches and candidates:
        print(
            f"\nNo accepted or review matches. Top "
            f"{min(SHOW_TOP_CANDIDATES, len(candidates))} rejected candidates for debugging:"
        )
        for i, cand in enumerate(candidates[:SHOW_TOP_CANDIDATES], 1):
            print_match(cand, i, label="REJECTED CANDIDATE")

    opps = calculate_arbitrage(matches)
    print(f"\nArbitrage opportunities: {len(opps)}")
    for i, opp in enumerate(opps[:20], 1):
        print_arbitrage(opp, i)

    if not opps:
        print("\nNo gross arbitrage above threshold found in this run.")
        print("If candidate comparisons are now > 0, V6 fixed the bucketing problem.")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prediction-market arbitrage scanner for Kalshi + Polymarket.")
    parser.add_argument("--no-cache", action="store_true", help="Bypass local cache.")
    parser.add_argument("--min-confidence", type=int, default=MIN_MATCH_CONFIDENCE)
    parser.add_argument("--review-confidence", type=int, default=REVIEW_MIN_CONFIDENCE)
    parser.add_argument("--min-profit", type=float, default=MIN_ARBITRAGE_PROFIT)
    parser.add_argument("--show-candidates", type=int, default=SHOW_TOP_CANDIDATES)
    parser.add_argument("--debug", action="store_true")
    return parser


def main() -> None:
    global MIN_MATCH_CONFIDENCE, REVIEW_MIN_CONFIDENCE, MIN_ARBITRAGE_PROFIT, SHOW_TOP_CANDIDATES, DEBUG
    args = build_arg_parser().parse_args()
    MIN_MATCH_CONFIDENCE = args.min_confidence
    REVIEW_MIN_CONFIDENCE = args.review_confidence
    MIN_ARBITRAGE_PROFIT = args.min_profit
    SHOW_TOP_CANDIDATES = args.show_candidates
    DEBUG = args.debug
    run_scan(use_cache=not args.no_cache)


if __name__ == "__main__":
    main()
