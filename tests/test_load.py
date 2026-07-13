import sqlite3

import pytest

from phase2 import config
from phase2.load import _coerce, load_table


def _fresh_db(tmp_path):
    conn = sqlite3.connect(tmp_path / "t.db")
    conn.executescript((config.ROOT / "schema.sql").read_text())
    conn.executescript((config.ROOT / "seed.sql").read_text())
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _csv(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return p


def test_coerce_blank_to_null():
    assert _coerce("") is None
    assert _coerce(None) is None
    assert _coerce("0") == "0"


def test_load_roundtrip_and_affinity(tmp_path):
    conn = _fresh_db(tmp_path)
    load_table(conn, _csv(tmp_path, "agent.csv",
        "agent_id,name,synonyms,drug_class,is_targeted,target\n"
        "G-1,bortezomib,,proteasome_inhibitor,,proteasome\n"), "agent")
    load_table(conn, _csv(tmp_path, "trial.csv",
        "trial_id,nct_id,source_ref,phase,title,tumor_type,tumor_subtype,"
        "line_of_therapy,n_arms,n_subjects,start_year,completion_year,"
        "randomized,region,extracted_at\n"
        "T-1,,kang2013,II,,myeloma,,mixed,1,22,,2005,,,\n"), "trial")
    load_table(conn, _csv(tmp_path, "arm.csv",
        "arm_id,trial_id,arm_label,is_control,n_subjects,combination_size,"
        "regimen_class\nA-1,T-1,experimental,0,22,,\n"), "arm")
    ins, skip = load_table(conn, _csv(tmp_path, "outcome.csv",
        "outcome_id,arm_id,endpoint,response_criteria,value,value_unit,"
        "n_events,n_at_risk,ci_low,ci_high,ci_method,hr,rmst_diff,"
        "timepoint_months\nO-1,A-1,ORR,RECIST1.1,1.0,fraction,22,22,,,,,,\n"),
        "outcome")
    assert (ins, skip) == (1, 0)

    # blank cells landed as NULL; numeric strings coerced by affinity
    row = conn.execute(
        "SELECT n_subjects, completion_year, randomized FROM trial").fetchone()
    assert row == (22, 2005, None)
    assert conn.execute("SELECT value FROM outcome").fetchone()[0] == 1.0
    # CHECK on is_control IN (0,1) passed (text '0' coerced to int 0)
    assert conn.execute("SELECT is_control FROM arm").fetchone()[0] == 0


def test_load_is_idempotent(tmp_path):
    conn = _fresh_db(tmp_path)
    path = _csv(tmp_path, "agent.csv",
        "agent_id,name,synonyms,drug_class,is_targeted,target\n"
        "G-1,bortezomib,,proteasome_inhibitor,,proteasome\n")
    assert load_table(conn, path, "agent") == (1, 0)
    assert load_table(conn, path, "agent") == (0, 1)   # second run: all ignored


def test_orphan_fk_row_raises(tmp_path):
    conn = _fresh_db(tmp_path)
    # outcome referencing a non-existent arm -> FK violation raises (fail loud);
    # OR IGNORE does not suppress FK constraints.
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        load_table(conn, _csv(tmp_path, "outcome.csv",
            "outcome_id,arm_id,endpoint,response_criteria,value,value_unit,"
            "n_events,n_at_risk,ci_low,ci_high,ci_method,hr,rmst_diff,"
            "timepoint_months\nO-x,A-missing,ORR,RECIST1.1,0.5,fraction,1,2,,,,,,\n"),
            "outcome")


def test_unseeded_endpoint_raises(tmp_path):
    conn = _fresh_db(tmp_path)
    load_table(conn, _csv(tmp_path, "agent.csv",
        "agent_id,name,synonyms,drug_class,is_targeted,target\nG-1,x,,,,\n"), "agent")
    load_table(conn, _csv(tmp_path, "trial.csv",
        "trial_id,nct_id,source_ref,phase,title,tumor_type,tumor_subtype,"
        "line_of_therapy,n_arms,n_subjects,start_year,completion_year,"
        "randomized,region,extracted_at\nT-1,,k,II,,myeloma,,,1,1,,,,,\n"), "trial")
    load_table(conn, _csv(tmp_path, "arm.csv",
        "arm_id,trial_id,arm_label,is_control,n_subjects,combination_size,"
        "regimen_class\nA-1,T-1,,0,1,,\n"), "arm")
    # endpoint FK -> endpoint lookup; a bogus endpoint raises, not stored
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        load_table(conn, _csv(tmp_path, "outcome.csv",
            "outcome_id,arm_id,endpoint,response_criteria,value,value_unit,"
            "n_events,n_at_risk,ci_low,ci_high,ci_method,hr,rmst_diff,"
            "timepoint_months\nO-1,A-1,BOGUS,RECIST1.1,0.5,fraction,1,1,,,,,,\n"),
            "outcome")
