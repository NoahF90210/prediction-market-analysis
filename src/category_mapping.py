from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
TAXONOMY_PATH = CONFIG_DIR / "category_taxonomy.yml"
OVERRIDES_PATH = CONFIG_DIR / "category_overrides.csv"

CATEGORY_SOURCE_CONFIDENCE = {
    "override": 1.0,
    "platform_metadata": 0.95,
    "mapping_rule": 0.90,
    "keyword_fallback": 0.65,
    "unclassified": 0.0,
}


@dataclass(frozen=True)
class CategoryResult:
    canonical_category: str
    category_source: str
    category_confidence: float
    needs_review: bool
    review_reason: str
    raw_platform_category: str | None
    raw_tags: str


def normalize_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def encode_tags(tags: Iterable[dict] | None) -> str:
    cleaned = []
    for tag in tags or []:
        cleaned.append(
            {
                "label": str(tag.get("label") or ""),
                "slug": str(tag.get("slug") or ""),
            }
        )
    return json.dumps(cleaned, ensure_ascii=True)


@lru_cache
def load_taxonomy() -> dict:
    with TAXONOMY_PATH.open() as f:
        return yaml.safe_load(f)


@lru_cache
def load_overrides() -> list[dict]:
    if not OVERRIDES_PATH.exists():
        return []
    with OVERRIDES_PATH.open(newline="") as f:
        return list(csv.DictReader(f))


def _allowed_pair(categories: set[str]) -> bool:
    taxonomy = load_taxonomy()
    normalized_pairs = {
        tuple(sorted(pair))
        for pair in taxonomy.get("allowed_multi_category_pairs", [])
    }
    if len(categories) <= 1:
        return True
    return tuple(sorted(categories)) in normalized_pairs


def _top_category(categories: set[str]) -> str:
    priority = load_taxonomy()["category_priority"]
    for item in priority:
        if item in categories:
            return item
    return "unclassified"


def _match_override(
    platform: str,
    market_id: str | None,
    title: str | None,
    slug: str | None,
) -> dict | None:
    title_norm = normalize_text(title)
    slug_norm = normalize_text(slug)
    market_norm = normalize_text(market_id)

    for rule in load_overrides():
        if normalize_text(rule.get("platform")) not in {platform, "all"}:
            continue
        field = normalize_text(rule.get("match_field"))
        match_type = normalize_text(rule.get("match_type"))
        expected = normalize_text(rule.get("match_value"))
        actual = {
            "market_id": market_norm,
            "title": title_norm,
            "slug": slug_norm,
        }.get(field, "")
        if not actual:
            continue
        if match_type == "equals" and actual == expected:
            return rule
        if match_type == "contains" and expected in actual:
            return rule
    return None


def _collect_tag_categories(tags: Iterable[dict] | None) -> set[str]:
    mapping = load_taxonomy().get("polymarket_tag_slug_map", {})
    categories = set()
    for tag in tags or []:
        slug = normalize_text(tag.get("slug"))
        label = normalize_text(tag.get("label"))
        if slug in mapping:
            categories.add(mapping[slug])
        elif label in mapping:
            categories.add(mapping[label])
    return categories


def _map_platform_category(platform: str, raw_category: str | None) -> str | None:
    mapping = load_taxonomy().get("platform_category_map", {}).get(platform, {})
    normalized = normalize_text(raw_category)
    return mapping.get(normalized)


def _mapping_rule_category(text_blob: str) -> set[str]:
    rules = load_taxonomy().get("mapping_rules", {})
    categories = set()
    for category, phrases in rules.items():
        if any(normalize_text(phrase) in text_blob for phrase in phrases):
            categories.add(category)
    return categories


def _keyword_fallback_category(text_blob: str) -> set[str]:
    rules = load_taxonomy().get("keyword_fallback", {})
    categories = set()
    for category, phrases in rules.items():
        if any(normalize_text(phrase) in text_blob for phrase in phrases):
            categories.add(category)
    return categories


def _resolve_categories(categories: set[str], source: str) -> tuple[str, bool, str]:
    if not categories:
        return "unclassified", True, "No category could be determined from metadata or mapping rules."
    chosen = _top_category(categories)
    if len(categories) == 1 or _allowed_pair(categories):
        return chosen, False, ""
    return chosen, True, f"Conflicting category signals: {', '.join(sorted(categories))}"


def classify_market(
    *,
    platform: str,
    market_id: str | None = None,
    title: str | None = None,
    slug: str | None = None,
    raw_platform_category: str | None = None,
    raw_tags: Iterable[dict] | None = None,
    context_fields: Iterable[str | None] = (),
) -> CategoryResult:
    override = _match_override(platform, market_id, title, slug)
    tags_payload = encode_tags(raw_tags)
    if override:
        confidence = float(override.get("confidence") or CATEGORY_SOURCE_CONFIDENCE["override"])
        return CategoryResult(
            canonical_category=override["canonical_category"],
            category_source="override",
            category_confidence=confidence,
            needs_review=False,
            review_reason=normalize_text(override.get("reason")),
            raw_platform_category=raw_platform_category,
            raw_tags=tags_payload,
        )

    platform_category = _map_platform_category(platform, raw_platform_category)
    if platform_category:
        return CategoryResult(
            canonical_category=platform_category,
            category_source="platform_metadata",
            category_confidence=CATEGORY_SOURCE_CONFIDENCE["platform_metadata"],
            needs_review=False,
            review_reason="",
            raw_platform_category=raw_platform_category,
            raw_tags=tags_payload,
        )

    if platform == "polymarket":
        tag_categories = _collect_tag_categories(raw_tags)
        category, needs_review, reason = _resolve_categories(tag_categories, "platform_metadata")
        if category != "unclassified":
            return CategoryResult(
                canonical_category=category,
                category_source="platform_metadata",
                category_confidence=CATEGORY_SOURCE_CONFIDENCE["platform_metadata"],
                needs_review=needs_review,
                review_reason=reason,
                raw_platform_category=raw_platform_category,
                raw_tags=tags_payload,
            )

    text_blob = normalize_text(" ".join([title or "", slug or "", *(field or "" for field in context_fields)]))

    mapped_categories = _mapping_rule_category(text_blob)
    category, needs_review, reason = _resolve_categories(mapped_categories, "mapping_rule")
    if category != "unclassified":
        return CategoryResult(
            canonical_category=category,
            category_source="mapping_rule",
            category_confidence=CATEGORY_SOURCE_CONFIDENCE["mapping_rule"],
            needs_review=needs_review,
            review_reason=reason,
            raw_platform_category=raw_platform_category,
            raw_tags=tags_payload,
        )

    fallback_categories = _keyword_fallback_category(text_blob)
    category, needs_review, reason = _resolve_categories(fallback_categories, "keyword_fallback")
    if category != "unclassified":
        return CategoryResult(
            canonical_category=category,
            category_source="keyword_fallback",
            category_confidence=CATEGORY_SOURCE_CONFIDENCE["keyword_fallback"],
            needs_review=True,
            review_reason=reason or "Category assigned by keyword fallback only.",
            raw_platform_category=raw_platform_category,
            raw_tags=tags_payload,
        )

    return CategoryResult(
        canonical_category="unclassified",
        category_source="unclassified",
        category_confidence=CATEGORY_SOURCE_CONFIDENCE["unclassified"],
        needs_review=True,
        review_reason="No reliable category signal was available.",
        raw_platform_category=raw_platform_category,
        raw_tags=tags_payload,
    )


def comparable_categories(df, min_markets_per_platform: int = 20) -> set[str]:
    if df.empty or "platform" not in df.columns or "category" not in df.columns:
        return set()
    eligible = df[df["include_in_analysis"]].groupby(["category", "platform"], observed=True).size().unstack(fill_value=0)
    return {
        category
        for category, row in eligible.iterrows()
        if len([count for count in row if count >= min_markets_per_platform]) >= 2
    }
