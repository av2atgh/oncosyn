import sqlite3

import pytest

from phase2 import config
from phase2.analyze import bliss, matching, stats, validate
from phase2.analyze.matching import _confidence
from phase2.transform import derive
from phase2.transform.derive import classify_regimen

AGENTS = [("G-A", "drugA", "cytotoxic"), ("G-B", "drugB", "kinase_inhibitor")]
TRIALS = [  # trial_id, source, phase, tumor, line
    ("T-S1", "test", "II", "breast", None), ("T-S2", "test", "II", "breast", None),
    ("T-C1", "test", "II", "breast", None),
    ("T-P2", "test", "II", "breast", "1L"), ("T-P3", "test", "III", "breast", "1L"),
]
ARMS = [("A-S1", "T-S1", 100), ("A-S2", "T-S2", 100), ("A-C1", "T-C1", 100),
        ("A-P2", "T-P2", 100), ("A-P3", "T-P3", 200)]
REGCOMP = [("A-S1", "G-A"), ("A-S2", "G-B"), ("A-C1", "G-A"), ("A-C1", "G-B"),
           ("A-P2", "G-A"), ("A-P2", "G-B"), ("A-P3", "G-A"), ("A-P3", "G-B")]
OUTCOMES = [  # outcome_id, arm, endpoint, criteria, value, n_events, n_at_risk
    ("O-S1", "A-S1", "ORR", "RECIST1.1", 0.30, 30, 100),
    ("O-S2", "A-S2", "ORR", "RECIST1.1", 0.40, 40, 100),
    ("O-C1", "A-C1", "ORR", "RECIST1.1", 0.80, 80, 100),
    ("O-P2", "A-P2", "ORR", "RECIST1.1", 0.50, 50, 100),
    ("O-P3", "A-P3", "ORR", "RECIST1.1", 0.20, 40, 200),
]


@pytest.fixture
def analyzed_db(tmp_path, monkeypatch):
    path = tmp_path / "t.db"
    conn = sqlite3.connect(path)
    conn.executescript((config.ROOT / "schema.sql").read_text())
    conn.executescript((config.ROOT / "seed.sql").read_text())
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executemany("INSERT INTO agent (agent_id,name,drug_class) VALUES (?,?,?)", AGENTS)
    conn.executemany(
        "INSERT INTO trial (trial_id,source_ref,phase,tumor_type,line_of_therapy) "
        "VALUES (?,?,?,?,?)", TRIALS)
    conn.executemany("INSERT INTO arm (arm_id,trial_id,n_subjects) VALUES (?,?,?)", ARMS)
    conn.executemany(
        "INSERT INTO regimen_component (arm_id,agent_id) VALUES (?,?)", REGCOMP)
    conn.executemany(
        "INSERT INTO outcome (outcome_id,arm_id,endpoint,response_criteria,value,"
        "n_events,n_at_risk) VALUES (?,?,?,?,?,?,?)", OUTCOMES)
    conn.commit()
    conn.close()
    monkeypatch.setattr(config, "db_path", lambda: path)
    derive.run()
    bliss.run()
    matching.run()
    validate.run()
    return path


def _q(path, sql, params=()):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


# --- pure functions -------------------------------------------------------

def test_bliss_expected_formula():
    assert abs(stats.bliss_expected([0.3, 0.4]) - 0.58) < 1e-9


def test_pooled_rate_jeffreys_mean():
    mean, lo, hi = stats.pooled_rate(30, 100)
    assert abs(mean - 30.5 / 101) < 1e-9
    assert lo < mean < hi


def test_classify_regimen():
    assert classify_regimen(["cytotoxic"]) == (1, "cytotoxic")
    assert classify_regimen(["kinase_inhibitor"]) == (1, "targeted")
    assert classify_regimen(["cytotoxic", "kinase_inhibitor"]) == (2, "mixed")
    assert classify_regimen(["steroid"]) == (0, "other")   # supportive-only


def test_confidence_rules():
    assert _confidence("1L", "1L", True) == "high"
    assert _confidence("1L", "2L", True) is None            # differ, strict
    assert _confidence("1L", "2L", False) == "low"
    assert _confidence(None, "1L", True) == "medium"


# --- derive ---------------------------------------------------------------

def test_derive_sizes_and_classes(analyzed_db):
    by_arm = {r["arm_id"]: r for r in _q(analyzed_db,
        "SELECT arm_id, combination_size, regimen_class FROM arm")}
    assert by_arm["A-S1"]["combination_size"] == 1
    assert by_arm["A-S1"]["regimen_class"] == "cytotoxic"
    assert by_arm["A-C1"]["combination_size"] == 2
    assert by_arm["A-C1"]["regimen_class"] == "mixed"
    tgt = {r["name"]: r["is_targeted"] for r in _q(analyzed_db,
        "SELECT name, is_targeted FROM agent")}
    assert tgt["drugB"] == 1 and tgt["drugA"] == 0


# --- bliss ----------------------------------------------------------------

def test_bliss_detects_synergy(analyzed_db):
    row = _q(analyzed_db,
        "SELECT * FROM bliss_prediction WHERE arm_id='A-C1'")[0]
    assert abs(row["orr_expected"] - 0.582) < 0.01     # 1-(1-.302)(1-.401)
    assert row["orr_observed"] == 0.8
    assert row["delta"] > 0
    assert row["interaction"] == "synergy"             # 80/100 >> 58%, p tiny


def test_bliss_ci_brackets_expected(analyzed_db):
    row = _q(analyzed_db, "SELECT * FROM bliss_prediction WHERE arm_id='A-C1'")[0]
    assert row["orr_expected_ci_low"] < row["orr_expected"] < row["orr_expected_ci_high"]


# --- matching + validation ------------------------------------------------

def test_matching_pairs_phase2_to_phase3(analyzed_db):
    pair = _q(analyzed_db,
        "SELECT * FROM matched_pair WHERE phase2_arm_id='A-P2' AND phase3_arm_id='A-P3'")
    assert len(pair) == 1
    assert pair[0]["match_confidence"] == "high"       # same tumor + line 1L


def test_validation_shrinkage_and_within_ci(analyzed_db):
    v = _q(analyzed_db,
        "SELECT v.* FROM validation v JOIN matched_pair mp ON mp.pair_id=v.pair_id "
        "WHERE mp.phase2_arm_id='A-P2' AND mp.phase3_arm_id='A-P3'")[0]
    assert abs(v["orr_phase2_estimate"] - 0.5) < 0.02   # ~50/100
    assert v["orr_phase3_observed"] == 0.2              # 40/200
    assert v["shrinkage"] > 0                           # Phase II over-estimated
    assert v["within_ci"] == 0                          # 0.20 outside [~0.40,0.60]
    assert v["stratum_regimen_class"] == "mixed"
