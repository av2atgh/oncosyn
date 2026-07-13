import csv
import json
from pathlib import Path

import pytest

from phase2.extract import legacy
from phase2.extract.legacy import LegacyRowError, parse_row

FIXTURE = Path(__file__).parent / "fixtures" / "legacy_sample.csv"


def _rows():
    with open(FIXTURE, newline="") as fh:
        return list(csv.DictReader(fh))


def test_parse_synergy_pair_row():
    rec = parse_row(_rows()[0], 2)
    assert rec["phase"] == "II"
    assert rec["tumor_type"] == "myeloma"
    assert [a["name"] for a in rec["agents"]] == ["bortezomib", "thalidomide"]
    assert rec["agents"][0]["dose"] == "1.3 mg/m2"
    orr = next(o for o in rec["outcomes"] if o["endpoint"] == "ORR")
    assert orr["value"] == 1.0           # 100% -> fraction
    assert orr["n_events"] == 22         # derived: round(1.0 * 22)
    assert orr["n_at_risk"] == 22


def test_percent_conversion_and_derived_events():
    rec = parse_row(_rows()[1], 3)       # gemcitabine, ORR 26.7%, N=45
    orr = rec["outcomes"][0]
    assert abs(orr["value"] - 0.267) < 1e-9
    assert orr["n_events"] == 12         # round(0.267 * 45) = 12
    assert rec["nct_id"] == "NCT00001234"
    assert rec["agents"][0]["dose"] is None


def test_optional_cr_pr_and_criteria():
    rec = parse_row(_rows()[0], 2)
    endpoints = {o["endpoint"]: o for o in rec["outcomes"]}
    assert set(endpoints) == {"ORR", "CR", "PR"}
    assert abs(endpoints["CR"]["value"] - 0.20) < 1e-9
    assert rec["outcomes"][2]["response_criteria"] == "RECIST1.1"


def test_default_response_criteria_when_blank():
    assert parse_row(_rows()[1], 3)["outcomes"][0]["response_criteria"] == "RECIST1.1"


def test_missing_required_column_raises():
    with pytest.raises(LegacyRowError, match="missing required"):
        parse_row({"phase": "II"}, 9)


def test_bad_phase_raises():
    bad = dict(_rows()[0], phase="IV")
    with pytest.raises(LegacyRowError, match="phase"):
        parse_row(bad, 2)


def test_orr_out_of_range_raises():
    bad = dict(_rows()[0], orr="150")
    with pytest.raises(LegacyRowError, match="out of range"):
        parse_row(bad, 2)


def test_load_source_writes_jsonl(tmp_path, monkeypatch):
    # point config.ROOT-derived raw dir at a temp copy of the fixture
    raw = tmp_path / "raw"
    (raw / "legacy").mkdir(parents=True)
    (raw / "legacy" / "kang2013.csv").write_text(FIXTURE.read_text())
    monkeypatch.setattr(legacy.config, "load",
                        lambda: {"paths": {"raw": "raw"}})
    monkeypatch.setattr(legacy.config, "ROOT", tmp_path)

    out = legacy.load_source("kang2013")
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 3
    first = json.loads(lines[0])
    assert first["source_ref"] == "kang2013"
    assert first["src_row"] == 2
    assert "extracted_at" in first
