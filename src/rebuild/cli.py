from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from src.portfolio.pipeline import build_portfolio
from src.rebuild.collectors import KalshiCollector, PolymarketCollector
from src.rebuild.gates import write_candidates
from src.rebuild.pipeline import build_fixture_analysis, build_real_analysis
from src.rebuild.portfolio_bridge import load_analysis_rows, write_portfolio_input
from src.rebuild.protocol import ROOT, load_protocol
from src.rebuild.provenance import RawResponseStore, collector_commit


def _collect(args: argparse.Namespace) -> int:
    protocol = load_protocol()
    output = Path(args.output)
    raw_root = output / "raw"
    store = RawResponseStore(raw_root, protocol, commit=collector_commit(ROOT))
    candidates = []
    max_pages = None if args.max_pages == 0 else args.max_pages
    max_markets = None if args.max_markets == 0 else args.max_markets
    if args.platform in {"polymarket", "both"}:
        candidates.extend(
            PolymarketCollector(protocol, store).collect(
                max_event_pages=max_pages,
                max_markets=max_markets,
                after_cursor=args.after_cursor,
            )
        )
    if args.platform in {"kalshi", "both"}:
        candidates.extend(
            KalshiCollector(protocol, store).collect(
                max_market_pages=max_pages,
                max_markets=max_markets,
            )
        )
    candidate_hash = write_candidates(output / "candidate_records.json", candidates)
    manifest = store.write_manifest(
        output / "manifest.json",
        candidate_records_sha256=candidate_hash,
    )
    print(
        json.dumps(
            {
                "platform": args.platform,
                "candidate_count": len(candidates),
                "raw_record_count": len(manifest["records"]),
                "build_id": manifest["build_id"],
                "output": str(output),
                "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
            indent=2,
        )
    )
    return 0


def _build_fixture(args: argparse.Namespace) -> int:
    rows, paths = build_fixture_analysis(output_dir=Path(args.output))
    included = [row for row in rows if row["inclusion_status"] == "included"]
    event_count = len({(row["platform"], row["event_group_id"]) for row in included})
    print(
        json.dumps(
            {
                "fixture_only": True,
                "contract_count": len(included),
                "event_count": event_count,
                "excluded_count": len(rows) - len(included),
                "artifacts": {key: str(value) for key, value in paths.items()},
            },
            indent=2,
        )
    )
    return 0


def _build_real(args: argparse.Namespace) -> int:
    rows, paths = build_real_analysis(Path(args.source), output_dir=Path(args.output))
    included = [row for row in rows if row["inclusion_status"] == "included"]
    event_count = len({(row["platform"], row["event_group_id"]) for row in included})
    summary = json.loads(paths["evaluation"].read_text())
    print(
        json.dumps(
            {
                "data_status": summary["validation_status"],
                "submitted_count": len(rows),
                "included_count": len(included),
                "event_count": event_count,
                "excluded_count": len(rows) - len(included),
                "evaluation": str(paths["evaluation"]),
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


def _publish_dashboard(args: argparse.Namespace) -> int:
    rows = load_analysis_rows(Path(args.analysis))
    input_path = write_portfolio_input(rows, Path(args.input))
    _, payload, paths = build_portfolio(
        input_path,
        corpus_kind="real",
        output_dir=Path(args.output),
        dashboard_output=Path(args.dashboard),
    )
    print(
        json.dumps(
            {
                "data_status": payload["data_status"],
                "submitted_count": payload["summary"]["submitted_count"],
                "included_count": payload["summary"]["included_count"],
                "dashboard": str(paths["dashboard"]),
                "input": str(input_path),
                "summary": str(paths["summary"]),
            },
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provenance-safe prediction-market rebuild")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fixture = subparsers.add_parser("build-fixture", help="Build deterministic fixture analysis artifacts")
    fixture.add_argument("--output", default=str(ROOT / "data" / "derived" / "rebuild"))
    fixture.set_defaults(func=_build_fixture)

    real = subparsers.add_parser("build-real", help="Build a validated real-corpus analysis")
    real.add_argument("--source", required=True, help="Collected real corpus directory containing manifest.json")
    real.add_argument("--output", default=str(ROOT / "data" / "derived" / "rebuild-real"))
    real.set_defaults(func=_build_real)

    publish = subparsers.add_parser("publish-dashboard", help="Build the static dashboard from verified analysis rows")
    publish.add_argument("--analysis", required=True, help="Analysis rows JSON from build-real")
    publish.add_argument("--input", default=str(ROOT / "data" / "real" / "polymarket_normalized.json"))
    publish.add_argument("--output", default=str(ROOT / "data" / "derived" / "portfolio-real"))
    publish.add_argument("--dashboard", default=str(ROOT / "static_dashboard" / "data.js"))
    publish.set_defaults(func=_publish_dashboard)

    collect = subparsers.add_parser("collect", help="Collect immutable public API responses without scoring")
    collect.add_argument("--platform", choices=("polymarket", "kalshi", "both"), required=True)
    collect.add_argument("--output", default=str(ROOT / "data" / "raw" / "rebuild"))
    collect.add_argument("--max-pages", type=int, default=1, help="Safety cap; use 0 only for a reviewed full collection")
    collect.add_argument("--max-markets", type=int, default=3, help="Safety cap on history requests; use 0 for all eligible markets")
    collect.add_argument("--after-cursor", default=None, help="Resume Polymarket event pagination from a prior keyset cursor")
    collect.set_defaults(func=_collect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
