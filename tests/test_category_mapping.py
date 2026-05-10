from __future__ import annotations

import json

import pandas as pd

from src.build_accuracy_dataset import review_queue
from src.category_mapping import classify_market, comparable_categories


def test_polymarket_tags_map_iran_series_to_geopolitics() -> None:
    result = classify_market(
        platform="polymarket",
        market_id="pm-iran-1",
        title="Iran x Israel/US conflict ends by April 15?",
        slug="iran-x-israelus-conflict-ends-by-april-15",
        raw_platform_category="",
        raw_tags=[
            {"slug": "middle-east", "label": "Middle East"},
            {"slug": "iran", "label": "Iran"},
            {"slug": "politics", "label": "Politics"},
            {"slug": "geopolitics", "label": "Geopolitics"},
        ],
        context_fields=["Iran x Israel/US conflict ends by...?"],
    )
    assert result.canonical_category == "geopolitics"
    assert result.category_source in {"override", "platform_metadata"}
    assert result.needs_review is False


def test_kalshi_sports_market_maps_without_review() -> None:
    result = classify_market(
        platform="kalshi",
        market_id="KXNBAGAME",
        title="Game 5: Minnesota at Denver Winner?",
        slug="KXNBAGAME",
        raw_platform_category="",
        raw_tags=[],
        context_fields=["NBA playoff game", "sports", "denver winner"],
    )
    assert result.canonical_category == "sports"
    assert result.category_source == "mapping_rule"
    assert result.needs_review is False


def test_unknown_market_fails_closed() -> None:
    result = classify_market(
        platform="kalshi",
        market_id="mystery-1",
        title="Will the bespoke internal milestone resolve?",
        slug="mystery-1",
        raw_platform_category="",
        raw_tags=[],
        context_fields=["totally custom market"],
    )
    assert result.canonical_category == "unclassified"
    assert result.needs_review is True
    assert result.category_source == "unclassified"


def test_kalshi_tennis_market_maps_to_sports() -> None:
    result = classify_market(
        platform="kalshi",
        market_id="KXWTAMATCH-26APR27BENBAP-BEN",
        title="Will Belinda Bencic win the Bencic vs Baptiste: Round Of 16 match?",
        slug="KXWTAMATCH-26APR27BENBAP-BEN",
        raw_platform_category="",
        raw_tags=[],
        context_fields=[
            "WTA",
            "KXWTAMATCH-26APR27BENBAP",
            "tennis",
        ],
    )
    assert result.canonical_category == "sports"
    assert result.category_source == "mapping_rule"
    assert result.needs_review is False


def test_esports_market_maps_to_sports() -> None:
    result = classify_market(
        platform="polymarket",
        market_id="pm-dota-1",
        title="Dota 2: Xtreme Gaming vs Natus Vincere (BO3) - PGL Wallachia Group Stage",
        slug="dota-2-xtreme-gaming-vs-natus-vincere-bo3-pgl-wallachia-group-stage",
        raw_platform_category="",
        raw_tags=[],
    )
    assert result.canonical_category == "sports"
    assert result.category_source == "mapping_rule"
    assert result.needs_review is False


def test_comparable_categories_requires_both_platforms() -> None:
    df = pd.DataFrame(
        [
            {"platform": "polymarket", "category": "sports", "include_in_analysis": True},
            {"platform": "polymarket", "category": "sports", "include_in_analysis": True},
            {"platform": "kalshi", "category": "sports", "include_in_analysis": True},
            {"platform": "kalshi", "category": "sports", "include_in_analysis": True},
            {"platform": "polymarket", "category": "geopolitics", "include_in_analysis": True},
            {"platform": "polymarket", "category": "geopolitics", "include_in_analysis": True},
            {"platform": "kalshi", "category": "geopolitics", "include_in_analysis": False},
        ]
    )
    categories = comparable_categories(df, min_markets_per_platform=2)
    assert "sports" in categories
    assert "geopolitics" not in categories


def test_review_queue_prioritizes_flagged_rows() -> None:
    df = pd.DataFrame(
        [
            {
                "platform": "polymarket",
                "market_id": "1",
                "title": "Reviewed",
                "category": "sports",
                "raw_tags": json.dumps([]),
                "needs_review": False,
                "include_in_analysis": True,
                "category_confidence": 0.95,
                "review_reason": "",
                "volume": 100_000,
            },
            {
                "platform": "polymarket",
                "market_id": "2",
                "title": "Needs review",
                "category": "unclassified",
                "raw_tags": json.dumps([]),
                "needs_review": True,
                "include_in_analysis": False,
                "category_confidence": 0.0,
                "review_reason": "No reliable category signal was available.",
                "volume": 500_000,
            },
        ]
    )
    queue = review_queue(df)
    assert queue["market_id"].tolist() == ["2"]
