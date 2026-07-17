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
