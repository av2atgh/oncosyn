"""Legacy-table loader — digitized supplement tables from the reference papers.

Reads a hand-digitized CSV for a legacy source (kang2013 / azam2021) and emits
provenance-stamped raw records to ``data/raw/<source_ref>.jsonl``. No controlled-
vocabulary mapping or agent dedup happens here (that is stage 2, transform); this
loader only parses the flat table into structured, per-arm JSON envelopes.

Input CSV location:  ``<paths.raw>/legacy/<source_ref>.csv``

Input CSV columns
-----------------
Required:
  trial_ref     source citation / PMID (e.g. "PMID:15774776")
  phase         II | II/III | III
  tumor_type    free text (mapped to controlled vocab downstream)
  agents        pipe-delimited regimen, e.g. "bortezomib|thalidomide"
  n_subjects    arm size (denominator N)
  orr           objective response rate as a PERCENT in [0, 100]

Optional:
  nct_id, line_of_therapy, year, arm_label,
  doses         pipe-delimited, aligned 1:1 with `agents` (blanks allowed)
  cr, pr        complete / partial response, PERCENT in [0, 100]
  response_criteria   RECIST1.1 | iRECIST | WHO | other  (default RECIST1.1)

Rates are converted from percent to fractions; n_events is derived from
orr x n_subjects when not otherwise available.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .. import config

REQUIRED = ("trial_ref", "phase", "tumor_type", "agents", "n_subjects", "orr")
VALID_PHASE = {"II", "II/III", "III"}


class LegacyRowError(ValueError):
    """A digitized row failed validation; message names the row and problem."""


def _pct_to_fraction(raw: str, field: str, row_no: int) -> float | None:
    raw = (raw or "").strip().rstrip("%").strip()
    if raw == "":
        return None
    try:
        pct = float(raw)
    except ValueError as e:
        raise LegacyRowError(f"row {row_no}: {field}={raw!r} is not numeric") from e
    if not 0.0 <= pct <= 100.0:
        raise LegacyRowError(f"row {row_no}: {field}={pct} out of range [0,100]")
    return pct / 100.0


def _int(raw: str, field: str, row_no: int) -> int | None:
    raw = (raw or "").strip()
    if raw == "":
        return None
    try:
        return int(float(raw))
    except ValueError as e:
        raise LegacyRowError(f"row {row_no}: {field}={raw!r} is not an integer") from e


def _agents(agents_cell: str, doses_cell: str, row_no: int) -> list[dict]:
    names = [a.strip() for a in (agents_cell or "").split("|") if a.strip()]
    if not names:
        raise LegacyRowError(f"row {row_no}: empty `agents`")
    doses = [d.strip() for d in (doses_cell or "").split("|")] if doses_cell else []
    out = []
    for i, name in enumerate(names):
        dose = doses[i] if i < len(doses) and doses[i] else None
        out.append({"name": name, "dose": dose})
    return out


def parse_row(row: dict, row_no: int) -> dict:
    """Turn one CSV row into a structured raw record (no provenance yet)."""
    missing = [c for c in REQUIRED if not (row.get(c) or "").strip()]
    if missing:
        raise LegacyRowError(f"row {row_no}: missing required {missing}")

    phase = row["phase"].strip()
    if phase not in VALID_PHASE:
        raise LegacyRowError(f"row {row_no}: phase={phase!r} not in {sorted(VALID_PHASE)}")

    n_subjects = _int(row["n_subjects"], "n_subjects", row_no)
    orr = _pct_to_fraction(row["orr"], "orr", row_no)
    criteria = (row.get("response_criteria") or "RECIST1.1").strip() or "RECIST1.1"

    outcomes = [{
        "endpoint": "ORR",
        "value": orr,
        "n_events": round(orr * n_subjects) if (orr is not None and n_subjects) else None,
        "n_at_risk": n_subjects,
        "response_criteria": criteria,
    }]
    for ep in ("cr", "pr"):
        frac = _pct_to_fraction(row.get(ep, ""), ep, row_no)
        if frac is not None:
            outcomes.append({
                "endpoint": ep.upper(),
                "value": frac,
                "n_events": round(frac * n_subjects) if n_subjects else None,
                "n_at_risk": n_subjects,
                "response_criteria": criteria,
            })

    return {
        "trial_ref": row["trial_ref"].strip(),
        "nct_id": (row.get("nct_id") or "").strip() or None,
        "phase": phase,
        "tumor_type": row["tumor_type"].strip(),
        "line_of_therapy": (row.get("line_of_therapy") or "").strip() or None,
        "year": _int(row.get("year", ""), "year", row_no),
        "arm_label": (row.get("arm_label") or "").strip() or None,
        "n_subjects": n_subjects,
        "agents": _agents(row["agents"], row.get("doses", ""), row_no),
        "outcomes": outcomes,
    }


def load_source(source_ref: str, cfg: dict | None = None) -> Path:
    """Parse ``<raw>/legacy/<source_ref>.csv`` -> ``<raw>/<source_ref>.jsonl``.

    Returns the output path. Raises LegacyRowError on the first bad row so a
    digitization mistake fails loudly rather than silently dropping data.
    """
    cfg = cfg or config.load()
    raw_dir = config.ROOT / cfg["paths"]["raw"]
    in_path = raw_dir / "legacy" / f"{source_ref}.csv"
    if not in_path.exists():
        raise FileNotFoundError(f"legacy input not found: {in_path}")

    stamped_at = datetime.now(timezone.utc).isoformat()
    out_path = raw_dir / f"{source_ref}.jsonl"

    n = 0
    with open(in_path, newline="") as fh, open(out_path, "w") as out:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader, start=2):  # row 1 is the header
            record = parse_row(row, i)
            record["source_ref"] = source_ref
            record["extracted_at"] = stamped_at
            record["src_row"] = i
            out.write(json.dumps(record) + "\n")
            n += 1

    print(f"[extract.legacy] {source_ref}: {n} rows -> {out_path.name}")
    return out_path
