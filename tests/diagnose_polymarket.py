"""Run directly to diagnose the public Polymarket Gamma API."""

import requests

URLS = [
    "https://gamma-api.polymarket.com/markets/keyset?limit=5",
    "https://gamma-api.polymarket.com/markets?limit=5&active=true&closed=false",
]

for url in URLS:
    print("\nURL:", url)
    try:
        response = requests.get(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "prediction-market-arbitrage/6.1",
            },
            timeout=20,
        )
        print("Status:", response.status_code)
        print("Body:", response.text[:500])
    except Exception as exc:
        print("Error:", repr(exc))
