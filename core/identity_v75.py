"""V7.5 political race identity and crypto contract classification."""

from __future__ import annotations
import re
from typing import Optional, Tuple
from models import ParsedMarket
from legacy.scanner_v6_1 import normalize_text

STATE_CODES = {
    "AL":"alabama","AK":"alaska","AZ":"arizona","AR":"arkansas",
    "CA":"california","CO":"colorado","CT":"connecticut","DE":"delaware",
    "FL":"florida","GA":"georgia","HI":"hawaii","ID":"idaho",
    "IL":"illinois","IN":"indiana","IA":"iowa","KS":"kansas",
    "KY":"kentucky","LA":"louisiana","ME":"maine","MD":"maryland",
    "MA":"massachusetts","MI":"michigan","MN":"minnesota","MS":"mississippi",
    "MO":"missouri","MT":"montana","NE":"nebraska","NV":"nevada",
    "NH":"new_hampshire","NJ":"new_jersey","NM":"new_mexico",
    "NY":"new_york","NC":"north_carolina","ND":"north_dakota",
    "OH":"ohio","OK":"oklahoma","OR":"oregon","PA":"pennsylvania",
    "RI":"rhode_island","SC":"south_carolina","SD":"south_dakota",
    "TN":"tennessee","TX":"texas","UT":"utah","VT":"vermont",
    "VA":"virginia","WA":"washington","WV":"west_virginia",
    "WI":"wisconsin","WY":"wyoming",
}

def infer_us_district(text: str) -> Tuple[Optional[str], Optional[int]]:
    m = re.search(r"\b([A-Z]{2})-(\d{1,2})\b", text)
    return (STATE_CODES.get(m.group(1)), int(m.group(2))) if m else (None, None)

def infer_candidate(text: str) -> Optional[str]:
    patterns = [
        r"\bWill it be confirmed that ([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,4}) is\b",
        r"\bWill ([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,4}) be the\b",
        r"\bWill ([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,4}) win\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return normalize_text(m.group(1)).replace(" ", "_")
    return None

def enrich_political_race(market: ParsedMarket) -> None:
    if market.category != "politics":
        return
    title = market.title.split("|", 1)[0].strip()
    normalized = normalize_text(title)

    state, district = infer_us_district(title)
    if state:
        market.state = state
    if district is not None:
        market.district = district
        market.office = "house"

    if not market.office:
        if "senate" in normalized or "senator" in normalized:
            market.office = "senate"
        elif "governor" in normalized:
            market.office = "governor"
        elif "president" in normalized:
            market.office = "president"
        elif "house" in normalized or "congress" in normalized:
            market.office = "house"

    if any(x in normalized for x in ("nominee", "nomination", "primary")):
        market.election_type = "primary"
    elif "runoff" in normalized:
        market.election_type = "runoff"
    elif "general election" in normalized:
        market.election_type = "general"

    candidate = infer_candidate(title) or market.candidate
    if candidate:
        market.candidate = candidate
        market.canonical_candidate = candidate
        market.proposition_subject_type = "candidate"
        market.proposition_subject_value = candidate

    country = market.canonical_country or market.country
    party = market.canonical_party or market.party
    if country and market.office and market.election_type:
        parts = [country]
        if market.state:
            parts.append(market.state)
        parts.append(market.office)
        if market.district is not None:
            parts.append(f"district_{market.district}")
        if party:
            parts.append(party)
        parts.append(market.election_type)
        if market.year:
            parts.append(str(market.year))
        market.race_id = ":".join(parts)

def classify_crypto_contract(market: ParsedMarket) -> None:
    if market.category != "crypto":
        return
    text = normalize_text(market.title)
    rt = market.resolution_type or ""
    if rt == "price_at_time":
        market.contract_type = "price_snapshot"
        market.contract_time_scope = market.resolution_time
    elif rt == "any_time_before":
        market.contract_type = "price_reach"
        market.contract_time_scope = market.deadline
    elif rt == "bounded_range":
        market.contract_type = "price_range"
        market.contract_time_scope = market.resolution_time or market.deadline
    elif "all time high" in text or re.search(r"\bath\b", text):
        market.contract_type = "all_time_high"
        market.contract_time_scope = market.deadline
    elif "market cap" in text or "market capitalization" in text:
        market.contract_type = "market_cap"
        market.contract_time_scope = market.deadline
    elif "etf" in text:
        market.contract_type = "etf"
        market.contract_time_scope = market.deadline
    elif rt in {"threshold_at_deadline", "threshold_generic"}:
        market.contract_type = "price_threshold"
        market.contract_time_scope = market.deadline

def enrich_v75_identity(market: ParsedMarket) -> None:
    enrich_political_race(market)
    classify_crypto_contract(market)
