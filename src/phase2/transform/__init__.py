"""Stage 2 — transform: normalize raw records into schema-shaped rows.

Reads data/raw/*.jsonl (per-arm envelopes from stage 1), emits normalized CSVs
to data/interim/ — one per base table: trial, arm, agent, regimen_component,
outcome.

Responsibilities:
  * agent resolution / dedup against the canonical `agent` dictionary (vocab).
  * split each arm's regimen into regimen_component rows.
  * carry each arm's endpoints into long-format `outcome` rows (rates as fractions).
  * map free-text tumor/line to controlled vocab (tumor_type, line_of_therapy).

IDs are deterministic hashes of natural keys, so re-runs are idempotent and the
downstream INSERT OR IGNORE never duplicates.

Derived columns (arm.combination_size, arm.regimen_class, agent.is_targeted) are
left blank here and filled post-load by `transform.derive`.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from .. import config
from . import vocab

# output column order per base table (matches schema.sql)
COLUMNS = {
    "trial": ["trial_id", "nct_id", "source_ref", "phase", "title", "tumor_type",
              "tumor_subtype", "line_of_therapy", "n_arms", "n_subjects",
              "start_year", "completion_year", "randomized", "region", "extracted_at"],
    "arm": ["arm_id", "trial_id", "arm_label", "is_control", "n_subjects",
            "combination_size", "regimen_class"],
    "agent": ["agent_id", "name", "synonyms", "drug_class", "is_targeted", "target"],
    "regimen_component": ["arm_id", "agent_id", "dose", "dose_unit", "schedule"],
    "outcome": ["outcome_id", "arm_id", "endpoint", "response_criteria", "value",
                "value_unit", "n_events", "n_at_risk", "ci_low", "ci_high",
                "ci_method", "hr", "rmst_diff", "timepoint_months"],
}

RATE_ENDPOINTS = {"ORR", "CR", "PR", "DCR"}
TIME_ENDPOINTS = {"OS", "PFS", "TTP", "DoR"}


def _id(prefix: str, *parts: str) -> str:
    digest = hashlib.md5("::".join(parts).encode()).hexdigest()[:12]
    return f"{prefix}-{digest}"


def agent_id_for(name: str) -> str:
    return _id("G", name)


def _trial_key(rec: dict) -> str:
    """Natural key grouping arms into a trial.

    Scoped by source_ref so cohorts stay separable — the same NCT id appearing
    in a legacy set and in update2026 stays two trials (cross-source dedup, if
    wanted, is a later explicit step). Within a source, nct_id groups arms; if
    absent, the trial citation does.
    """
    return f"{rec['source_ref']}::{rec.get('nct_id') or rec['trial_ref']}"


def _read_raw(raw_dir: Path) -> list[dict]:
    records: list[dict] = []
    for path in sorted(raw_dir.glob("*.jsonl")):
        with open(path) as fh:
            records.extend(json.loads(line) for line in fh if line.strip())
    return records


def normalize(records: list[dict]) -> dict[str, list[dict]]:
    """Turn raw arm-envelopes into base-table row lists.

    Arms, regimen components, and outcomes are keyed by their deterministic id,
    so a row seen twice (e.g. the same arm digitized on two source lines) is
    stored once. Trial n_arms / n_subjects are aggregated from the distinct
    arms afterwards, so re-seen arms never double-count.
    """
    agents_seen: dict[str, dict] = {}
    trials: dict[str, dict] = {}
    arms: dict[str, dict] = {}
    regcomp: dict[tuple[str, str], dict] = {}
    outcomes: dict[str, dict] = {}
    stats = {"agent_unknown": 0, "tumor_unknown": 0}

    for rec in records:
        tkey = _trial_key(rec)

        # trial (created once per key)
        if tkey not in trials:
            tumor, tumor_ok = vocab.resolve_tumor(rec["tumor_type"])
            if not tumor_ok:
                stats["tumor_unknown"] += 1
            trial = {c: None for c in COLUMNS["trial"]}
            trial.update(
                trial_id=_id("T", tkey), nct_id=rec.get("nct_id"),
                source_ref=rec["source_ref"], phase=rec["phase"], tumor_type=tumor,
                line_of_therapy=vocab.resolve_line(rec.get("line_of_therapy")),
                completion_year=rec.get("year"), extracted_at=rec.get("extracted_at"),
                n_arms=0, n_subjects=0, _tkey=tkey,
            )
            trials[tkey] = trial
        trial_id = trials[tkey]["trial_id"]

        # arm (deduped by deterministic arm_id)
        canon_agents = [vocab.resolve_agent(a["name"]) for a in rec["agents"]]
        regimen_sig = "+".join(sorted(name for name, _, _ in canon_agents))
        label = rec.get("arm_label") or ""
        arm_id = _id("A", tkey, label, regimen_sig)
        if arm_id not in arms:
            arms[arm_id] = {
                "arm_id": arm_id, "trial_id": trial_id,
                "arm_label": rec.get("arm_label"),
                "is_control": 1 if "control" in label.lower() else 0,
                "n_subjects": rec.get("n_subjects"),
                "combination_size": None, "regimen_class": None,  # derive fills these
                "_tkey": tkey,
            }

        # agents + regimen_component
        for (name, info, known), raw_agent in zip(canon_agents, rec["agents"]):
            if not known:
                stats["agent_unknown"] += 1
            aid = agent_id_for(name)
            agents_seen.setdefault(name, {
                "agent_id": aid, "name": name,
                "synonyms": json.dumps(info.synonyms) if info.synonyms else None,
                "drug_class": info.drug_class, "is_targeted": None,
                "target": info.target,
            })
            regcomp.setdefault((arm_id, aid), {
                "arm_id": arm_id, "agent_id": aid,
                "dose": raw_agent.get("dose"), "dose_unit": None, "schedule": None,
            })

        # outcomes (deduped by deterministic outcome_id)
        for out in rec["outcomes"]:
            ep = out["endpoint"]
            oid = _id("O", arm_id, ep, out.get("response_criteria") or "",
                      str(out.get("timepoint_months") or ""))
            outcomes.setdefault(oid, {
                "outcome_id": oid, "arm_id": arm_id, "endpoint": ep,
                "response_criteria": out.get("response_criteria"),
                "value": out.get("value"),
                "value_unit": ("fraction" if ep in RATE_ENDPOINTS
                               else "months" if ep in TIME_ENDPOINTS else None),
                "n_events": out.get("n_events"), "n_at_risk": out.get("n_at_risk"),
                "ci_low": None, "ci_high": None, "ci_method": None,
                "hr": None, "rmst_diff": None, "timepoint_months": out.get("timepoint_months"),
            })

    # aggregate trial counts from distinct arms, then drop scratch keys
    for arm in arms.values():
        tr = trials[arm.pop("_tkey")]
        tr["n_arms"] += 1
        tr["n_subjects"] += arm["n_subjects"] or 0
    for tr in trials.values():
        tr.pop("_tkey", None)

    return {
        "trial": list(trials.values()),
        "arm": list(arms.values()),
        "agent": list(agents_seen.values()),
        "regimen_component": list(regcomp.values()),
        "outcome": list(outcomes.values()),
        "_stats": {**stats, "arms": len(arms)},
    }


def run() -> None:
    cfg = config.load()
    raw_dir = config.ROOT / cfg["paths"]["raw"]
    interim = config.ROOT / cfg["paths"]["interim"]
    interim.mkdir(parents=True, exist_ok=True)

    records = _read_raw(raw_dir)
    if not records:
        print("[transform] no data/raw/*.jsonl — run extract first")
        return

    tables = normalize(records)
    stats = tables.pop("_stats")

    for table, cols in COLUMNS.items():
        with open(interim / f"{table}.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(tables[table])
        print(f"[transform] {table}: {len(tables[table])} rows")
    print(f"[transform] {stats['arms']} arms; "
          f"{stats['agent_unknown']} unknown-agent refs, "
          f"{stats['tumor_unknown']} unknown-tumor rows (fallbacks applied)")
