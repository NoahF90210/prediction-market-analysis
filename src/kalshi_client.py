import base64
import datetime
import json
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

BASE_URL = os.environ.get("KALSHI_BASE_URL", "https://external-api.kalshi.com/trade-api/v2").rstrip("/")
SESSION = requests.Session()

_API_KEY_ID = os.environ.get("KALSHI_API_KEY_ID", "").strip()
_PRIVATE_KEY_TEXT = os.environ.get("KALSHI_PRIVATE_KEY", "").strip()
_private_key = None
if _API_KEY_ID and _PRIVATE_KEY_TEXT:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization

    _private_key = serialization.load_pem_private_key(
        _PRIVATE_KEY_TEXT.replace("\\n", "\n").encode(),
        password=None,
        backend=default_backend(),
    )


def sign_request(method: str, path: str) -> dict:
    if not _API_KEY_ID or _private_key is None:
        return {}
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    timestamp = str(int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000))
    message = f"{timestamp}{method.upper()}{path}"
    signature = _private_key.sign(
        message.encode("utf-8"),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY": _API_KEY_ID,
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("utf-8"),
    }


def get(path: str, params: dict | None = None) -> dict:
    # path must be the full API path from the root, e.g. "/trade-api/v2/markets"
    # sign_request uses this path without query params
    api_path = f"/trade-api/v2{path}"
    headers = sign_request("GET", api_path)
    url = f"{BASE_URL}{path}"
    for attempt in range(4):
        response = SESSION.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 429:
            wait = 2 ** attempt * 5
            print(f"  rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        if not response.ok:
            print(f"HTTP {response.status_code}: {response.text}")
        response.raise_for_status()
        return response.json()
    raise RuntimeError(f"Failed after retries: {url}")


def get_nba_markets() -> list:
    return get("/markets", {"series_ticker": "NBA", "status": "open", "limit": 100})["markets"]


def get_market_history(ticker: str) -> list:
    return get(f"/markets/{ticker}/history")["history"]


if __name__ == "__main__":
    print("=== Open Series ===")
    series = get("/series")
    print(json.dumps(series, indent=2))

    print("\n=== NBA Markets ===")
    markets = get_nba_markets()
    print(json.dumps(markets, indent=2))
