"""Bliss-independence expected combination ORR + synergy/antagonism calls.

For every combination arm (>=2 anticancer agents) whose constituent single
agents each have a pooled single-agent ORR, compute the Bliss-expected ORR,
compare it to the observed ORR with an exact binomial test, and classify the
interaction as synergy / antagonism / none after Bonferroni correction.

Populates the bliss_prediction table. Idempotent: clears and rebuilds.
"""
from __future__ import annotations

import hashlib
import json

from .. import config, db
from . import stats

NON_ANTICANCER = ("radiation", "surgery", "steroid")
_ANTI = f"(ag.drug_class IS NULL OR ag.drug_class NOT IN ({','.join('?' * len(NON_ANTICANCER))}))"


def _bliss_id(arm_id: str) -> str:
    return "B-" + hashlib.md5(arm_id.encode()).hexdigest()[:12]


def single_agent_rates(conn) -> dict[str, dict]:
    """Pool ORR across single-agent arms -> {agent_id: {name, rate, n}}."""
    rows = conn.execute(
        "SELECT rc.agent_id, ag.name, o.n_events, o.n_at_risk "
        "FROM arm a "
        "JOIN regimen_component rc ON rc.arm_id = a.arm_id "
        "JOIN agent ag ON ag.agent_id = rc.agent_id "
        "JOIN outcome o ON o.arm_id = a.arm_id AND o.endpoint = 'ORR' "
        f"WHERE a.combination_size = 1 AND {_ANTI}",
        NON_ANTICANCER,
    ).fetchall()
    agg: dict[str, dict] = {}
    for r in rows:
        if r["n_events"] is None or not r["n_at_risk"]:
            continue
        e = agg.setdefault(r["agent_id"], {"name": r["name"], "events": 0, "n": 0})
        e["events"] += r["n_events"]
        e["n"] += r["n_at_risk"]
    out = {}
    for aid, v in agg.items():
        if v["n"] > 0:
            rate, _, _ = stats.pooled_rate(v["events"], v["n"])
            out[aid] = {"name": v["name"], "rate": rate, "n": v["n"]}
    return out


def _combination_arms(conn):
    for arm in conn.execute(
        "SELECT arm_id FROM arm WHERE combination_size >= 2"
    ).fetchall():
        agents = conn.execute(
            "SELECT rc.agent_id, ag.name "
            "FROM regimen_component rc JOIN agent ag ON ag.agent_id = rc.agent_id "
            f"WHERE rc.arm_id = ? AND {_ANTI}",
            (arm["arm_id"], *NON_ANTICANCER),
        ).fetchall()
        obs = conn.execute(
            "SELECT n_events, n_at_risk FROM outcome "
            "WHERE arm_id = ? AND endpoint = 'ORR'",
            (arm["arm_id"],),
        ).fetchone()
        yield arm["arm_id"], agents, obs


def run() -> None:
    cfg = config.load().get("analysis", {})
    alpha = cfg.get("significance_alpha", 0.05)
    ci_level = cfg.get("ci_level", 0.95)

    with db.session() as conn:
        rates = single_agent_rates(conn)
        predictions = []
        for arm_id, agents, obs in _combination_arms(conn):
            if obs is None or obs["n_events"] is None or not obs["n_at_risk"]:
                continue
            if not agents or any(a["agent_id"] not in rates for a in agents):
                continue  # need a single-agent ORR for every component
            comps = [(rates[a["agent_id"]]["rate"], rates[a["agent_id"]]["n"])
                     for a in agents]
            expected, lo, hi = stats.bliss_expected_ci(comps, ci_level)
            observed = obs["n_events"] / obs["n_at_risk"]
            p = stats.binom_test_two_sided(obs["n_events"], obs["n_at_risk"], expected)
            predictions.append({
                "arm_id": arm_id, "orr_expected": expected,
                "orr_expected_ci_low": lo, "orr_expected_ci_high": hi,
                "component_orr_source": json.dumps(
                    {a["name"]: round(rates[a["agent_id"]]["rate"], 4) for a in agents}),
                "orr_observed": observed, "delta": observed - expected, "p_value": p,
            })

        # Bonferroni across the tested combinations
        m = len(predictions) or 1
        rows = []
        for pr in predictions:
            p_adj = min(1.0, pr["p_value"] * m)
            if p_adj < alpha and pr["delta"] > 0:
                interaction = "synergy"
            elif p_adj < alpha and pr["delta"] < 0:
                interaction = "antagonism"
            else:
                interaction = "none"
            rows.append((
                _bliss_id(pr["arm_id"]), pr["arm_id"], pr["orr_expected"],
                pr["orr_expected_ci_low"], pr["orr_expected_ci_high"],
                pr["component_orr_source"], pr["orr_observed"], pr["delta"],
                interaction, pr["p_value"], p_adj,
            ))

        conn.execute("DELETE FROM bliss_prediction")
        conn.executemany(
            "INSERT INTO bliss_prediction (bliss_id, arm_id, orr_expected, "
            "orr_expected_ci_low, orr_expected_ci_high, component_orr_source, "
            "orr_observed, delta, interaction, p_value, p_adjusted) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
    n_syn = sum(1 for r in rows if r[8] == "synergy")
    n_ant = sum(1 for r in rows if r[8] == "antagonism")
    print(f"[analyze.bliss] {len(rows)} combinations tested; "
          f"{n_syn} synergy, {n_ant} antagonism")
