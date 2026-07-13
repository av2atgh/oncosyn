"""Match Phase II arms to confirming Phase III arms -> matched_pair.

Signature = anticancer regimen (sorted agent names) + tumor + line of therapy.
Pairs a Phase II arm with a Phase III arm from a *different* trial when their
signatures agree, per config.analysis.matching. Idempotent: clears and rebuilds.
"""
from __future__ import annotations

import hashlib

from .. import config, db

NON_ANTICANCER = ("radiation", "surgery", "steroid")
_RANK = {"high": 3, "medium": 2, "low": 1}


def _pair_id(a2: str, a3: str) -> str:
    return "P-" + hashlib.md5(f"{a2}::{a3}".encode()).hexdigest()[:12]


def _arms_with_regimen(conn) -> list[dict]:
    placeholders = ",".join("?" * len(NON_ANTICANCER))
    rows = conn.execute(
        "SELECT a.arm_id, a.trial_id, t.phase, t.tumor_type, t.line_of_therapy, "
        "       group_concat(ag.name, '+') AS regimen "
        "FROM arm a "
        "JOIN trial t ON t.trial_id = a.trial_id "
        "JOIN regimen_component rc ON rc.arm_id = a.arm_id "
        "JOIN agent ag ON ag.agent_id = rc.agent_id "
        f"WHERE ag.drug_class IS NULL OR ag.drug_class NOT IN ({placeholders}) "
        "GROUP BY a.arm_id",
        NON_ANTICANCER,
    ).fetchall()
    out = []
    for r in rows:
        agents = sorted((r["regimen"] or "").split("+"))
        out.append({
            "arm_id": r["arm_id"], "trial_id": r["trial_id"], "phase": r["phase"],
            "tumor_type": r["tumor_type"], "line": r["line_of_therapy"],
            "regimen": "+".join(agents),
        })
    return out


def _confidence(l2, l3, same_line: bool) -> str | None:
    """Pair confidence from the two lines of therapy (None = reject)."""
    if l2 is not None and l3 is not None:
        if l2 == l3:
            return "high"
        return None if same_line else "low"
    return "medium"          # at least one line unknown -> can't confirm mismatch


def run() -> None:
    m = config.load().get("analysis", {}).get("matching", {})
    same_tumor = m.get("require_same_tumor", True)
    same_line = m.get("require_same_line", True)
    min_rank = _RANK.get(m.get("min_confidence", "medium"), 2)

    with db.session() as conn:
        arms = _arms_with_regimen(conn)
        p2 = [a for a in arms if a["phase"] in ("II", "II/III")]
        p3 = [a for a in arms if a["phase"] in ("III", "II/III")]

        # bucket phase-III arms by (regimen[, tumor]) for cheap lookup
        buckets: dict[tuple, list[dict]] = {}
        for a in p3:
            key = (a["regimen"], a["tumor_type"] if same_tumor else None)
            buckets.setdefault(key, []).append(a)

        rows = []
        for a in p2:
            key = (a["regimen"], a["tumor_type"] if same_tumor else None)
            for b in buckets.get(key, []):
                if a["arm_id"] == b["arm_id"] or a["trial_id"] == b["trial_id"]:
                    continue
                conf = _confidence(a["line"], b["line"], same_line)
                if conf is None or _RANK[conf] < min_rank:
                    continue
                rows.append((
                    _pair_id(a["arm_id"], b["arm_id"]), a["arm_id"], b["arm_id"],
                    f"{a['regimen']}|{a['tumor_type']}|{a['line']}",
                    "exact_regimen", conf,
                ))

        conn.execute("DELETE FROM matched_pair")
        conn.executemany(
            "INSERT OR IGNORE INTO matched_pair (pair_id, phase2_arm_id, "
            "phase3_arm_id, match_key, match_method, match_confidence) "
            "VALUES (?,?,?,?,?,?)",
            rows,
        )
    print(f"[analyze.matching] {len(rows)} Phase II<->III pairs")
