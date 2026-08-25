import json

from src.polymarket.publish import OUTPUT
from src.rebuild.claims import load_dashboard_payload


def test_checked_in_dashboard_payload_matches_publication_contract():
    data = load_dashboard_payload(OUTPUT)
    assert data["summary"]["included_count"] == 75036
    assert data["summary"]["event_count"] == 14678
    assert len(data["buckets"]) == 5
    assert data["robustness"]["included_count"] == 14678
    assert OUTPUT.exists()
    text = OUTPUT.read_text()
    assert "75036" in text
    assert "14678" in text
    assert json.loads(json.dumps(data))["summary"]["gap"] < 0
