import json

import pytest

from src.polymarket.spec import load_config


def test_approved_config_is_explicit_and_utc():
    config = load_config()
    assert config["platform"] == "polymarket"
    assert config["resolution_start"].endswith("Z")
    assert config["resolution_end"].endswith("Z")
    assert config["probability_buckets"] == [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]


def test_rejects_invalid_window(tmp_path):
    path = tmp_path / "analysis.json"
    config = json.loads(open("config/analysis.json").read())
    config["resolution_end"] = config["resolution_start"]
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="resolution_start"):
        load_config(path)


def test_rejects_incomplete_buckets(tmp_path):
    path = tmp_path / "analysis.json"
    config = json.loads(open("config/analysis.json").read())
    config["probability_buckets"] = [0.0, 0.2, 0.2, 1.0]
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="probability_buckets"):
        load_config(path)


def test_rejects_nonpositive_cutoff(tmp_path):
    path = tmp_path / "analysis.json"
    config = json.loads(open("config/analysis.json").read())
    config["snapshot_hours_before_resolution"] = 0
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="positive"):
        load_config(path)
