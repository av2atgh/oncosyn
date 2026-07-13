"""Stage 1 — extract: pull raw trial records from configured sources into data/raw.

Sources (see config.yaml `sources`):
  * kang2013 / azam2021 — digitized legacy tables from the reference papers,
    read via `legacy.load_source` (kind: legacy_table).
  * update2026 — ClinicalTrials.gov API + PubMed extraction (kind:
    clinicaltrials_api), completion year >= 2020.

Output: one raw file per source under data/raw/<source_ref>.jsonl (structured
per-arm envelopes, provenance-stamped). Controlled-vocab mapping and agent dedup
happen later, in transform.
"""
from __future__ import annotations

from .. import config
from . import clinicaltrials, legacy


def run() -> None:
    cfg = config.load()
    for src in cfg["sources"]:
        ref, kind = src["source_ref"], src["kind"]
        if kind == "legacy_table":
            legacy.load_source(ref, cfg)
        elif kind == "clinicaltrials_api":
            clinicaltrials.load_source(ref, cfg)
        else:
            raise ValueError(f"unknown source kind {kind!r} for {ref}")
