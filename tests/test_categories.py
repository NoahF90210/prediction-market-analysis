from src.rebuild.categories import classify_market


def test_polymarket_tags_map_to_geopolitics() -> None:
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
    )
    assert result.canonical_category == "geopolitics"
    assert result.category_source in {"override", "platform_metadata"}
    assert result.needs_review is False


def test_polymarket_sports_market_maps_from_title() -> None:
    result = classify_market(
        platform="polymarket",
        market_id="pm-dota-1",
        title="Dota 2: Xtreme Gaming vs Natus Vincere",
        slug="dota-2-xtreme-gaming-vs-natus-vincere",
        raw_platform_category="",
        raw_tags=[],
    )
    assert result.canonical_category == "sports"
    assert result.category_source == "mapping_rule"
    assert result.needs_review is False


def test_unknown_polymarket_market_fails_closed() -> None:
    result = classify_market(
        platform="polymarket",
        market_id="mystery-1",
        title="Will the bespoke internal milestone resolve?",
        slug="mystery-1",
        raw_platform_category="",
        raw_tags=[],
    )
    assert result.canonical_category == "unclassified"
    assert result.needs_review is True
    assert result.category_source == "unclassified"
