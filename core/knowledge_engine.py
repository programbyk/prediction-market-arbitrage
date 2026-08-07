from __future__ import annotations
import json,re
from functools import lru_cache
from pathlib import Path
from typing import Optional,Tuple
from models import ParsedMarket
from legacy.scanner_v6_1 import normalize_text

def _load(name):
    p=Path(__file__).resolve().parents[1]/'knowledge'/'entities'/name
    return json.loads(p.read_text(encoding='utf-8'))
@lru_cache(maxsize=1)
def countries_catalog(): return _load('countries.json')
@lru_cache(maxsize=1)
def parties_catalog(): return _load('political_parties.json')
def _match(text,phrase):
    q=normalize_text(phrase)
    return re.search(r'(?<![a-z0-9])'+re.escape(q).replace(r'\ ',r'\s+')+r'(?![a-z0-9])',text) is not None

def infer_country(m):
    if m.canonical_country: return m.canonical_country
    if m.country: return m.country
    t=normalize_text(m.title)
    for country,aliases in countries_catalog().items():
        if any(_match(t,a) for a in aliases): return country
    raw=m.raw or {}; blob=' '.join(str(raw.get(f) or '') for f in ('ticker','event_ticker','series_ticker')).upper()
    if m.platform=='kalshi' and any(x in blob for x in ('PRES','SEN','HOUSE','GOV','FOURSTATE')): return 'usa'
    return None

def infer_party(m,country):
    t=normalize_text(m.title)
    if country in parties_catalog():
        for pid,aliases in parties_catalog()[country].items():
            if any(_match(t,a) for a in aliases): return pid
    if m.party and country: return m.party
    return None

def infer_subject(m)->Tuple[Optional[str],Optional[str]]:
    title=m.title.split('|',1)[0].strip(); t=normalize_text(title)
    if m.candidate: return 'candidate',m.candidate
    z=re.search(r'\bwill\s+([A-Z][A-Za-z\'.-]+(?:\s+[A-Z][A-Za-z\'.-]+){1,4})\s+(?:be|become)\s+(?:the\s+)?nominee\b',title)
    if z: return 'candidate',normalize_text(z.group(1)).replace(' ','_')
    if re.search(r'\bnominee\b.*\bwoman\b|\bwoman\b.*\bnominee\b',t): return 'demographic','female'
    if re.search(r'\bnominee\b.*\bman\b|\bman\b.*\bnominee\b',t): return 'demographic','male'
    if re.search(r'\bwin all 4\b|\bdemocratic sweep\b',t): return 'sweep','all_four'
    if re.search(r'\bwin none\b|\brepublican sweep\b',t): return 'sweep','none'
    if 'second most seats' in t: return 'seat_rank','second'
    if 'third most seats' in t: return 'seat_rank','third'
    if 'most seats' in t: return 'seat_rank','most'
    return None,None

def enrich_knowledge_identity(m):
    if m.category=='politics':
        c=infer_country(m); p=infer_party(m,c); st,sv=infer_subject(m)
        m.canonical_country=c; m.canonical_party=p; m.proposition_subject_type=st; m.proposition_subject_value=sv
        if c and m.year:
            m.election_id=':'.join(x for x in (c,m.state or '',m.office or '',m.subtype or '',str(m.year)) if x)
    elif m.category=='sports':
        t=normalize_text(m.title)
        if m.competition: m.tournament_id=m.competition
        if 'women' in t or 'wta' in t: m.gender='women'; m.tour='wta'
        elif 'men' in t or 'atp' in t: m.gender='men'; m.tour='atp'
        if 'clay' in t: m.surface='clay'
        elif 'grass' in t: m.surface='grass'
        elif 'hard court' in t or 'hardcourt' in t: m.surface='hard'
