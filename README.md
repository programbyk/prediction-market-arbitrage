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
