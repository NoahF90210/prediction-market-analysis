import csv
import json

from src.polymarket import analyze


def test_bucket_boundaries():
    assert analyze.bucket(0.0)[0] == "[0.0, 0.2)"
    assert analyze.bucket(0.2)[0] == "[0.2, 0.4)"
    assert analyze.bucket(1.0)[0] == "[0.8, 1.0]"


def test_analyze_pools_categories_and_reconciles(tmp_path, monkeypatch):
    markets = tmp_path / "markets.csv"
    results = tmp_path / "results"
    markets.write_text(
        "market_id,event_id,event_title,question,category,tags,yes_token_id,probability,probability_timestamp,snapshot_cutoff,snapshot_age_hours,resolution,resolution_timestamp,resolution_source,market_url,volume\n"
        "1,e1,E1,Q1,Sports,[],t1,0.2,2025-01-01T00:00:00Z,2025-01-02T00:00:00Z,24,1,2025-01-03T00:00:00Z,,,\n"
        "2,e2,E2,Q2,Finance,[],t2,0.8,2025-01-01T00:00:00Z,2025-01-02T00:00:00Z,24,0,2025-01-03T00:00:00Z,,,\n"
    )
    monkeypatch.setattr(analyze, "MARKETS_CSV", markets)
    monkeypatch.setattr(analyze, "RESULTS", results)
    monkeypatch.setattr(analyze, "BUCKETS_CSV", results / "probability_buckets.csv")
    monkeypatch.setattr(analyze, "SUMMARY_JSON", results / "summary.json")
    summary = analyze.analyze()
    assert summary["included_market_count"] == 2
    assert summary["bucket_count_sum"] == 2
    assert summary["overall_observed_yes_frequency"] == 0.5
    assert summary["category_counts"] == {"Sports": 1, "Finance": 1}
    assert json.loads((results / "summary.json").read_text())["included_market_count"] == 2
    assert len(list(csv.DictReader((results / "probability_buckets.csv").open()))) == 2
