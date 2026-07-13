"""Stage 4 — analyze: Bliss predictions, synergy calls, matched pairs, validation.

Pipeline (all read/write the database):
  1. bliss     -> populate bliss_prediction: expected combination ORR
                  1 - prod(1 - orr_i), delta, synergy/antagonism at alpha (Bonferroni).
  2. matching  -> populate matched_pair: link Phase II arms to confirming Phase III
                  arms by regimen+tumor+line signature (config.analysis.matching).
  3. validate  -> populate validation: Phase II ORR estimate (observed or Bliss)
                  vs Phase III observed ORR; shrinkage, within_ci decision, strata.

Cohort-level agreement stats (CCC, R2, Bland-Altman, calibration) live in
`report`, computed over the validation rows / v_validation_pairs view.
"""
from __future__ import annotations

from . import bliss, matching, validate


def run() -> None:
    bliss.run()
    matching.run()
    validate.run()
