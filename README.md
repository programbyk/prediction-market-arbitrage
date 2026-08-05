# Prediction Market Arbitrage

Modular compatibility release based on the tested scanner V6.1.

## Run

```bash
python -m pip install -r requirements.txt
python main.py --no-cache --show-candidates 20
```

## Structure

- `fetchers/`: Kalshi and Polymarket downloads
- `parsers/`: normalization and structured parsing
- `matcher/`: candidate generation and equivalence rules
- `arbitrage/`: opportunity calculations
- `scanner/`: application orchestration
- `ai/`: future semantic validation
- `legacy/`: tested V6.1 implementation used during safe migration

## Migration strategy

This first modular release deliberately keeps the tested V6.1 engine in
`legacy/scanner_v6_1.py`. Each module exposes a stable interface around it.
That means the project can be uploaded and run immediately without losing
behavior. In later commits, the implementations can be moved out of
`legacy/` one module at a time, with tests after every move.


## Stage 2 migration progress

### Step 2.1 — Utilities migrated

The following functions now live independently in `utils/helpers.py`:

- `normalize_text`
- `words`
- `important_words`
- `parse_year`
- `parse_number`
- `safe_float`
- `parse_json_maybe`
- `bounded_alt`

The legacy engine imports them temporarily. Run:

```bash
python -m pytest tests/test_helpers.py
python main.py --no-cache --show-candidates 5
```


### Step 2.2 — Knowledge engine added

New JSON knowledge files:

- `knowledge/sports.json`
- `knowledge/politics.json`
- `knowledge/crypto.json`
- `knowledge/economy.json`

The first live integration is sports competition resolution. Existing regex
rules remain as fallback during migration.

Run:

```bash
python -m pytest tests/test_helpers.py tests/test_knowledge.py
python main.py --no-cache --show-candidates 5
```


### Step 2.2.2 — Polymarket HTTP 422 ordering fix

Polymarket rejected `order=volume_num` with:

```text
422 validation_error: order fields are not valid
```

The custom `order` and `ascending` parameters were removed from both the
keyset and standard market requests. Pagination now uses the API's default
ordering.

Run:

```bash
python tests/diagnose_polymarket.py
python main.py --no-cache --show-candidates 5
```


## V6.2 — Event identity candidate filtering

V6.2 adds:

- `participant_type`
- canonical `event_fingerprint`
- hard candidate prefilters before full scoring
- strong golf/PGA detection before generic FIFA aliases
- competition + participant-type indexes
- tests for the `Fifa Laopakdee` false candidate

Run:

```bash
python -m pytest tests/test_helpers.py tests/test_knowledge.py tests/test_v62_identity.py
python main.py --no-cache --show-candidates 10
```

Expected effect: candidate comparisons should decrease, while exact event
pairs remain eligible for ACCEPTED or REVIEW.


## V6.2.1 — Parser isolation and boundary-safe aliases

Fixes the observed false classification where:

- `nuclear` accidentally matched the alias `ucl`
- political markets inherited `champions_league`, `uefa`, and `soccer`
- ticker or diagnostic metadata influenced semantic classification

Knowledge aliases now match complete words or phrases. Category detection now
uses only the human-facing market question/title; ticker metadata remains
available only for diagnostics.

Run:

```bash
python -m pytest tests/test_helpers.py tests/test_knowledge.py tests/test_v62_identity.py tests/test_v621_parser_isolation.py
python main.py --no-cache --show-candidates 10
```


## V6.2.2 — Sports event action and subject identity

Generic sports events now extract:

- `event_action`: retire, join_team, sign_team, trade, released, suspended, etc.
- `event_subject`: the player/person whose action resolves the market

This prevents markets about the same athlete but different real-world actions
from becoming candidate matches.

Example rejected before scoring:

```text
LeBron James joins an NBA team
vs
LeBron James retires
```

Run:

```bash
python -m pytest tests/test_v621_parser_isolation.py tests/test_v622_sports_events.py
python main.py --no-cache --show-candidates 10
```


## V6.3 — Expanded coverage

V6.3 raises the total scan target to:

- Kalshi: up to 20 pages × 1,000 = 20,000 markets
- Polymarket: up to 200 pages × 100 = 20,000 markets

This is **20,000 total per platform**, not 20,000 in a single API request.
The APIs impose smaller per-request limits, so pagination is required.

The scanner also prints a cross-platform category coverage report before
matching.

Run:

```bash
python main.py --no-cache --show-candidates 10
```

A full fresh scan can take several minutes depending on network speed and API
throttling.


## V6.4 — Semantic Sports

V6.4 adds `event_kind`, the exact proposition being resolved.

Examples:

- `relegation`
- `promotion`
- `team_of_the_year`
- `top_scorer_award`
- `championship_winner`
- `champions_league_qualification`
- `first_half_btts`
- `retirement`
- `trade`
- `record_milestone`

Candidate generation now rejects different event kinds before scoring. This
prevents a Premier League relegation market from being compared with a PFA
Team of the Year market merely because both share league and season.

Run:

```bash
python -m pytest tests/test_v64_semantic_sports.py
python main.py --no-cache --show-candidates 15
```


## V6.5 — Parser Diagnostics

This version investigates why markets fall into `category="other"` before
changing the parser.

Run a fresh diagnosis:

```bash
python main.py --no-cache --diagnose-parser --diagnostic-limit 15
```

Or reuse the cache for a faster diagnosis:

```bash
python main.py --diagnose-parser --diagnostic-limit 15
```

The command:

- skips matching and arbitrage calculations;
- counts tradeable markets hidden inside `other`;
- estimates whether each market is likely sports, politics, crypto,
  economy, weather, entertainment, technology, geopolitics, or unknown;
- prints the most common Kalshi series/event prefixes;
- prints sample titles and the signals that triggered the diagnosis;
- exports full reports to:

```text
exports/kalshi_parser_other_diagnostics.csv
exports/polymarket_parser_other_diagnostics.csv
```

The CSV reports provide the evidence needed to decide which parser rules
should be added in V6.6.


## V6.6 — Cross-Platform Overlap Analyzer

This mode searches broadly for possible shared coverage before applying the
strict equivalence matcher.

```bash
python main.py --analyze-overlap --overlap-min-score 45 --overlap-top-per-market 5
```

Fresh 20,000 + 20,000 scan:

```bash
python main.py --no-cache --analyze-overlap --overlap-min-score 45 --overlap-top-per-market 5
```

Outputs:

```text
exports/overlap_candidates_all.csv
exports/overlap_candidates_sports.csv
exports/overlap_candidates_politics.csv
exports/overlap_candidates_crypto.csv
exports/overlap_candidates_economy.csv
exports/overlap_summary.json
```

These are development candidates, not confirmed arbitrage matches.


## V7.0 — Event Graph Engine

V7 changes candidate generation from entity-only grouping to:

```text
category + entity + market_intent + year + event scope
```

Examples:

```text
New England Patriots + playoff_host
New England Patriots + most_sacks
```

These now belong to different event nodes and are never compared.

The Event Graph also compares **all** Polymarket contracts inside a compatible
node against each Kalshi contract. A Kalshi market is therefore allowed to
produce multiple relevant Polymarket options.

Run the Event Graph Engine:

```bash
python main.py
```

Fresh 20,000 + 20,000 scan:

```bash
python main.py --no-cache --show-candidates 20
```

Inspect generated event nodes:

```text
exports/event_graph_nodes.csv
```

The old matcher remains available for comparison:

```bash
python main.py --legacy-matcher
```

Run V7 tests:

```bash
python -m pytest tests/test_v7_event_graph.py
```


## V7.1 — Semantic Core

V7.1 separates market understanding into three engines:

```text
core/entity_engine.py
core/intent_engine.py
core/event_engine.py
```

Intent aliases now live outside Python:

```text
knowledge/intents/sports.json
knowledge/intents/politics.json
knowledge/intents/crypto.json
knowledge/intents/economy.json
```

To add a new intent or phrase, edit the corresponding JSON file instead of
changing matcher code.

The Event Graph now compares structured EventObjects containing:

```text
category
entity
intent
year
sport / league / competition
threshold / direction
country / state / office
period
```

Run:

```bash
python -m pytest tests/test_v71_semantic_core.py
python main.py --show-candidates 20
```

A full fresh scan:

```bash
python main.py --no-cache --show-candidates 20
```
