"""Phase II ORR estimate vs Phase III observed ORR -> validation.

For each matched pair, take the Phase II arm's observed ORR (Beta posterior mean
+ credible interval) as the estimate, and compare it to the Phase III arm's
observed ORR. Records the estimate-minus-observed shrinkage, whether Phase III
fell inside the Phase II interval, and strata for subgroup agreement analysis.

Populates the validation table. Idempotent: clears and rebuilds.
"""
from __future__ import annotations

import hashlib

from .. import config, db
from . import stats


def _validation_id(pair_id: str) -> str:
    return "V-" + hashlib.md5(pair_id.encode()).hexdigest()[:12]


def run() -> None:
    ci_level = config.load().get("analysis", {}).get("ci_level", 0.95)

    with db.session() as conn:
        pairs = conn.execute(
            "SELECT mp.pair_id, a2.regimen_class, a2.combination_size, "
            "       o2.n_events AS e2, o2.n_at_risk AS n2, "
            "       o3.n_events AS e3, o3.n_at_risk AS n3, o3.value AS v3 "
            "FROM matched_pair mp "
            "JOIN arm a2 ON a2.arm_id = mp.phase2_arm_id "
            "JOIN outcome o2 ON o2.arm_id = mp.phase2_arm_id AND o2.endpoint = 'ORR' "
            "JOIN outcome o3 ON o3.arm_id = mp.phase3_arm_id AND o3.endpoint = 'ORR'"
        ).fetchall()

        rows = []
        for p in pairs:
            if p["e2"] is None or not p["n2"]:
                continue
            est, lo, hi = stats.pooled_rate(p["e2"], p["n2"], ci_level)
            # Phase III observed ORR: prefer counts, fall back to stored value
            if p["e3"] is not None and p["n3"]:
                obs3 = p["e3"] / p["n3"]
            elif p["v3"] is not None:
                obs3 = p["v3"]
            else:
                continue
            rows.append((
                _validation_id(p["pair_id"]), p["pair_id"], est, "phase2_observed",
                lo, hi, obs3, est - obs3, 1 if lo <= obs3 <= hi else 0,
                p["regimen_class"], p["combination_size"],
            ))

        conn.execute("DELETE FROM validation")
        conn.executemany(
            "INSERT INTO validation (validation_id, pair_id, orr_phase2_estimate, "
            "estimate_source, orr_phase2_ci_low, orr_phase2_ci_high, "
            "orr_phase3_observed, shrinkage, within_ci, stratum_regimen_class, "
            "stratum_combination_size) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
    n_val = sum(1 for r in rows if r[8] == 1)
    print(f"[analyze.validate] {len(rows)} pairs validated; "
          f"{n_val} Phase III within Phase II CI")
