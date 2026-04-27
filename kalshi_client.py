import base64
import datetime
import json
import os

import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

_API_KEY_ID = os.environ["KALSHI_API_KEY_ID"].strip()
_private_key = serialization.load_pem_private_key(
    os.environ["KALSHI_PRIVATE_KEY"].strip().encode(),
    password=None,
    backend=default_backend(),
)


def sign_request(method: str, path: str) -> dict:
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
    response = requests.get(f"{BASE_URL}{path}", headers=headers, params=params)
    if not response.ok:
        print(f"HTTP {response.status_code}: {response.text}")
    response.raise_for_status()
    return response.json()


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
