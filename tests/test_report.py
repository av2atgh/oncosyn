import csv
import sqlite3

import pytest

from phase2 import config
from phase2.report import metrics, run


# --- metrics unit tests ---------------------------------------------------

def test_agreement_perfect():
    a = metrics.agreement([0.2, 0.4, 0.6, 0.8], [0.2, 0.4, 0.6, 0.8])
    assert abs(a["ccc"] - 1.0) < 1e-9
    assert abs(a["pearson_r"] - 1.0) < 1e-9
    assert abs(a["calibration_slope"] - 1.0) < 1e-9
    assert abs(a["ba_bias"]) < 1e-9


def test_agreement_constant_bias():
    # Phase II always 0.1 higher -> perfect correlation, biased, CCC < 1
    a = metrics.agreement([0.3, 0.5, 0.7], [0.2, 0.4, 0.6])
    assert abs(a["pearson_r"] - 1.0) < 1e-9
    assert abs(a["ba_bias"] - 0.1) < 1e-9
    assert a["ccc"] < 1.0


def test_agreement_handles_too_few_points():
    a = metrics.agreement([0.5], [0.4])
    assert a["n"] == 1 and a["pearson_r"] is None
    assert abs(a["ba_bias"] - 0.1) < 1e-9


def test_trend_positive_slope():
    t = metrics.trend([0.2, 0.3, 0.4], [2000, 2010, 2020])
    assert t["slope_per_year"] > 0 and abs(t["pearson_r"] - 1.0) < 1e-9


# --- integration ----------------------------------------------------------

def _seed_db(tmp_path):
    path = tmp_path / "t.db"
    conn = sqlite3.connect(path)
    conn.executescript((config.ROOT / "schema.sql").read_text())
    conn.executescript((config.ROOT / "seed.sql").read_text())
    conn.execute("PRAGMA foreign_keys = ON")
    # minimal agent/trial/arm/outcome so views + trend query resolve
    conn.execute("INSERT INTO agent (agent_id,name) VALUES ('G-A','a')")
    for i, (phase, yr, orr, size) in enumerate([
            ("II", 2005, 0.30, 1), ("III", 2015, 0.20, 1),
            ("II", 2018, 0.55, 2), ("III", 2019, 0.45, 2)]):
        conn.execute("INSERT INTO trial (trial_id,source_ref,phase,tumor_type,"
                     "completion_year) VALUES (?,?,?,?,?)",
                     (f"T-{i}", "test", phase, "breast", yr))
        conn.execute("INSERT INTO arm (arm_id,trial_id,combination_size,regimen_class)"
                     " VALUES (?,?,?,?)", (f"A-{i}", f"T-{i}", size,
                                          "cytotoxic" if size == 1 else "mixed"))
        conn.execute("INSERT INTO regimen_component (arm_id,agent_id) VALUES (?, 'G-A')",
                     (f"A-{i}",))
        conn.execute("INSERT INTO outcome (outcome_id,arm_id,endpoint,value,"
                     "n_events,n_at_risk) VALUES (?,?, 'ORR', ?, ?, 100)",
                     (f"O-{i}", f"A-{i}", orr, int(orr * 100)))
        # median OS/PFS (months) so the survival analyses have data
        conn.execute("INSERT INTO outcome (outcome_id,arm_id,endpoint,value,"
                     "value_unit,n_at_risk) VALUES (?,?, 'OS', ?, 'months', 100)",
                     (f"OS-{i}", f"A-{i}", 12 + 6 * orr))
        conn.execute("INSERT INTO outcome (outcome_id,arm_id,endpoint,value,"
                     "value_unit,n_at_risk) VALUES (?,?, 'PFS', ?, 'months', 100)",
                     (f"PF-{i}", f"A-{i}", 4 + 4 * orr))
    # two matched pairs + validation rows
    for i, (a2, a3, est, o3, size, klass) in enumerate([
            ("A-0", "A-1", 0.30, 0.20, 1, "cytotoxic"),
            ("A-2", "A-3", 0.55, 0.45, 2, "mixed")]):
        conn.execute("INSERT INTO matched_pair (pair_id,phase2_arm_id,phase3_arm_id,"
                     "match_confidence) VALUES (?,?,?, 'high')", (f"P-{i}", a2, a3))
        conn.execute("INSERT INTO validation (validation_id,pair_id,orr_phase2_estimate,"
                     "estimate_source,orr_phase3_observed,shrinkage,within_ci,"
                     "stratum_regimen_class,stratum_combination_size) "
                     "VALUES (?,?,?, 'phase2_observed', ?,?,?,?,?)",
                     (f"V-{i}", f"P-{i}", est, o3, est - o3, 0, klass, size))
    # one bliss synergy row
    conn.execute("INSERT INTO bliss_prediction (bliss_id,arm_id,orr_expected,"
                 "orr_observed,delta,interaction,p_value,p_adjusted) "
                 "VALUES ('B-1','A-2',0.40,0.55,0.15,'synergy',0.001,0.002)")
    conn.commit()
    conn.close()
    return path


def _read(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def test_report_writes_all_outputs(tmp_path, monkeypatch):
    path = _seed_db(tmp_path)
    monkeypatch.setattr(config, "db_path", lambda: path)
    monkeypatch.setattr(config, "load", lambda: {"paths": {"reports": str(tmp_path / "reports")}})

    run()

    rep = tmp_path / "reports"
    agr = _read(rep / "agreement.csv")[0]
    assert agr["n"] == "2"
    assert float(agr["ba_bias"]) > 0                      # Phase II over-estimates
    syn = {r["interaction"]: r["n"] for r in _read(rep / "synergy_summary.csv")}
    assert syn["synergy"] == "1"
    pairs = _read(rep / "synergy_pairs.csv")
    assert len(pairs) == 1 and pairs[0]["arm_id"] == "A-2"
    strat = _read(rep / "shrinkage_by_stratum.csv")
    assert any(r["stratum"] == "regimen_class" and r["group"] == "mixed" for r in strat)
    trend = _read(rep / "orr_trend.csv")[0]
    assert int(trend["n"]) == 4
    by_size = _read(rep / "orr_by_combination_size.csv")
    assert any(r["combination_size"] == "2" for r in by_size)
    # figures rendered (2 pairs -> both plots)
    assert (rep / "figures" / "agreement_scatter.png").exists()
    assert (rep / "figures" / "bland_altman.png").exists()
    # survival outputs
    st = _read(rep / "survival_trend.csv")
    assert any(r["endpoint"] == "OS" and r["phase"] == "all" for r in st)
    pr = {r["survival_endpoint"] for r in _read(rep / "orr_survival_predictability.csv")}
    assert pr == {"OS", "PFS"}
    assert (rep / "figures" / "survival_over_time.png").exists()
    assert (rep / "figures" / "orr_vs_survival.png").exists()
