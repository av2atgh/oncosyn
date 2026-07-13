"""Validation: recover the pre-2020 cohort from ClinicalTrials.gov.

The legacy tables (kang2013, azam2021) are pre-2020 Phase II ORR data. This
routine queries CT.gov for the *same era* — Phase II/III oncology trials with
results and a completion date before 2020 — and reruns the live extractor,
reporting how much of that cohort the new pipeline recovers with a parseable
ORR. It is a live-network check (run on demand), not part of the pytest suite.

  python -m phase2.extract.recover [max_pages] [conditions]

Writes data/raw/recover_pre2020.jsonl so the recovered cohort can flow through
transform -> load -> analyze like any other source.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from .. import config
from . import clinicaltrials as ct

SOURCE_REF = "recover_pre2020"


def recover(max_pages: int = 5, conditions: str = "cancer", http_get=ct._default_get) -> dict:
    """Fetch pre-2020 studies, parse ORR, write JSONL, return recovery stats."""
    params = ct.build_params({"query": {
        "conditions": conditions, "max_completion_year": 2019}})
    raw_dir = config.ROOT / config.load()["paths"]["raw"]
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_path = raw_dir / f"{SOURCE_REF}.jsonl"
    stamped_at = datetime.now(timezone.utc).isoformat()

    n_studies = n_with_orr = n_records = n_combo = 0
    orrs: list[float] = []
    with open(out_path, "w") as out:
        ep_counts = {"ORR": 0, "OS": 0, "PFS": 0}
        for study in ct.fetch_studies(params, max_pages=max_pages, http_get=http_get):
            n_studies += 1
            recs = ct.parse_study(study)
            if any(r["outcomes"][0]["endpoint"] == "ORR" for r in recs):
                n_with_orr += 1
            for rec in recs:
                rec.update(source_ref=SOURCE_REF, extracted_at=stamped_at)
                out.write(json.dumps(rec) + "\n")
                n_records += 1
                ep = rec["outcomes"][0]["endpoint"]
                ep_counts[ep] = ep_counts.get(ep, 0) + 1
                if ep == "ORR":                       # ORR-only stats
                    orrs.append(rec["outcomes"][0]["value"])
                    if len(rec["agents"]) >= 2:
                        n_combo += 1

    stats = {
        "studies_fetched": n_studies,
        "studies_with_orr": n_with_orr,
        "arm_records": n_records,
        "orr_records": ep_counts["ORR"], "os_records": ep_counts["OS"],
        "pfs_records": ep_counts["PFS"],
        "combination_arms": n_combo,
        "recovery_rate": round(n_with_orr / n_studies, 3) if n_studies else 0.0,
        "mean_orr": round(sum(orrs) / len(orrs), 3) if orrs else None,
        "output": str(out_path),
    }
    return stats


def main() -> None:
    max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    conditions = sys.argv[2] if len(sys.argv) > 2 else "cancer"
    stats = recover(max_pages=max_pages, conditions=conditions)
    print("[recover] pre-2020 cohort recovery:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if stats["studies_with_orr"] == 0:
        raise SystemExit("recovery FAILED: no ORR recovered from the pre-2020 cohort")


if __name__ == "__main__":
    main()
