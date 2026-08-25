"""Freeze hashes for the verified local analytical dataset."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from src.polymarket.full_collection import ROOT

FILES = {
    "configuration": ROOT / "config" / "analysis.json",
    "normalized_dataset": ROOT / "data" / "processed" / "polymarket_markets.csv",
    "exclusions": ROOT / "data" / "results" / "exclusions.csv",
    "data_quality": ROOT / "data" / "results" / "data_quality.json",
    "summary": ROOT / "data" / "results" / "summary.json",
    "probability_buckets": ROOT / "data" / "results" / "probability_buckets.csv",
    "robustness": ROOT / "data" / "results" / "robustness_one_market_per_event.json",
    "robustness_buckets": ROOT / "data" / "results" / "robustness_one_market_per_event_buckets.csv",
    "dashboard_payload": ROOT / "static_dashboard" / "data.js",
    "inventory_checkpoint": ROOT / "data" / "checkpoints" / "polymarket" / "market_inventory.json",
    "price_checkpoint": ROOT / "data" / "checkpoints" / "polymarket" / "price_collection.json",
}
MANIFEST = ROOT / "data" / "results" / "dataset_manifest.json"
ARTIFACT = ROOT / ".hermes" / "artifacts" / "polymarket-dataset-freeze.md"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freeze() -> dict:
    summary = json.loads(FILES["summary"].read_text())
    quality = json.loads(FILES["data_quality"].read_text())
    hashes = {name: {"path": str(path.relative_to(ROOT)), "sha256": sha256(path), "bytes": path.stat().st_size} for name, path in FILES.items()}
    manifest = {
        "frozen_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "scope": "Polymarket canonical YES/NO markets resolved in UTC calendar year 2025",
        "included_market_count": summary["included_market_count"],
        "unique_event_count": summary["unique_event_count"],
        "inventory_candidates": quality["inventory_candidates"],
        "price_results": quality["price_results"],
        "files": hashes,
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    lines = [
        "# Polymarket Dataset Freeze",
        "",
        f"Frozen at: `{manifest['frozen_at']}`.",
        "",
        "The frozen analytical dataset contains only canonical YES/NO Polymarket markets with resolved outcomes and usable pre-resolution price snapshots.",
        "",
        f"- Included markets: **{manifest['included_market_count']:,}**.",
        f"- Unique events: **{manifest['unique_event_count']:,}**.",
        f"- Inventory candidates: **{manifest['inventory_candidates']:,}**.",
        f"- Price results: **{manifest['price_results']:,}**.",
        "",
        "## Hash manifest",
        "",
        "| Artifact | SHA-256 | Bytes |",
        "|---|---|---:|",
    ]
    for name, value in hashes.items():
        lines.append(f"| `{name}` (`{value['path']}`) | `{value['sha256']}` | {value['bytes']:,} |")
    lines += [
        "",
        "No README, dashboard, commit, push, deployment, or publication step should use a different dataset without generating a new freeze manifest.",
        "",
    ]
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text("\n".join(lines))
    return manifest


if __name__ == "__main__":
    print(json.dumps(freeze(), indent=2))
