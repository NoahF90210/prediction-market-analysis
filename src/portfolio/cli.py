from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.portfolio.pipeline import (
    DEFAULT_DASHBOARD,
    DEFAULT_OUTPUT,
    build_fixture_portfolio,
    build_portfolio,
)


def _result(payload, paths) -> dict:
    summary = payload["summary"]
    return {
        "data_status": payload["data_status"],
        "submitted_count": summary["submitted_count"],
        "included_count": summary["included_count"],
        "excluded_count": summary["excluded_count"],
        "build_id": payload["build_id"],
        "artifacts": {key: str(value) for key, value in paths.items()},
    }


def _build_fixture(args: argparse.Namespace) -> int:
    _, payload, paths = build_fixture_portfolio(
        output_dir=Path(args.output),
        dashboard_output=Path(args.dashboard_output) if args.dashboard_output else None,
    )
    print(json.dumps(_result(payload, paths), indent=2))
    return 0


def _import_normalized(args: argparse.Namespace) -> int:
    _, payload, paths = build_portfolio(
        Path(args.input),
        corpus_kind="real",
        output_dir=Path(args.output),
        dashboard_output=Path(args.dashboard_output) if args.dashboard_output else None,
    )
    print(json.dumps(_result(payload, paths), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the compact prediction-market portfolio dashboard from bounded normalized rows"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fixture = subparsers.add_parser(
        "build-fixture",
        help="Build the explicitly synthetic portfolio fixture and dashboard",
    )
    fixture.add_argument("--output", default=str(DEFAULT_OUTPUT))
    fixture.add_argument("--dashboard-output", default=str(DEFAULT_DASHBOARD))
    fixture.set_defaults(func=_build_fixture)

    normalized = subparsers.add_parser(
        "import-normalized",
        help="Validate a bounded real Polymarket CSV/JSON contract and build descriptive outputs",
    )
    normalized.add_argument("--input", required=True)
    normalized.add_argument("--output", default=str(DEFAULT_OUTPUT))
    normalized.add_argument("--dashboard-output", default=str(DEFAULT_DASHBOARD))
    normalized.set_defaults(func=_import_normalized)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
