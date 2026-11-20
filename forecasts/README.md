# Forecasts

Phase III objective response rate (ORR) forecasts made with the oncosyn Phase II→III
calibration (`report_2026/manuscript.tex`, 157 matched arm pairs):

ORR_III = 0.230 + 0.418 × ORR_II, with Bland–Altman limits of agreement [−0.59, 0.43].

For combinations the Phase II input is the Bliss-independence expectation
1 − ∏(1 − p_i). Each forecast is dated and is not edited after recording; resolution
adds the observed value in `forecasts.csv`. Numbers are reproduced by
`python3 forecasts/forecast.py`.

The limits of agreement are wide, so the bands are close to uninformative: the point
forecast and the directional claims carry the content.

## Retrospective check (recorded 2026-11-20, after the readout)

RASolute 302, daraxonrasib vs chemotherapy, second-line metastatic PDAC. Phase II ORR
0.35 (300 mg, second line, G12-mutant, n = 26) gives a forecast of 0.38; observed Phase III
ORR 0.33 (chemotherapy 0.12). Median OS 13.2 vs 6.7 months, HR 0.40. ORR at 0.33 did
not anticipate an OS hazard ratio of 0.40: the survival benefit came from disease
control, consistent with ORR explaining about a quarter of the variance in median
survival.

KRAS G12C precedent in second-line NSCLC: sotorasib Phase II 0.37 (CodeBreaK 100) →
Phase III 0.28 vs docetaxel 0.13 (CodeBreaK 200, PFS HR 0.66, OS HR 1.01); adagrasib
Phase II 0.43 (KRYSTAL-1, n = 112) → Phase III 0.32 vs docetaxel 0.09 (KRYSTAL-12,
PFS HR 0.58, OS immature at the primary analysis). Sources: de Langen et al., Lancet
2023 (CodeBreaK 200); FDA ODAC briefing, Oct 2023; Barlesi et al., ASCO 2024 and
Mok et al., Lancet 2024 (KRYSTAL-12); Jänne et al., NEJM 2022 (KRYSTAL-1).

## F1 — RASolute 303 (recorded 2026-11-20)

First-line metastatic PDAC, daraxonrasib + gemcitabine + nab-paclitaxel (GnP) vs GnP.

- Inputs: daraxonrasib 0.33 (RASolute 302 arm), gemcitabine 0.08 and nab-paclitaxel
  0.19 (oncosyn pooled single-agent arms). Bliss: GnP 0.26; triplet 0.50.
- Forecast Phase III ORR of the triplet: **0.44** (band 0.07–1.00).
- Directional claim: observed triplet ORR **at or below the Bliss expectation 0.50**.
  Antagonism outnumbers synergy 87 to 33 in the cohort, and gemcitabine +
  nab-paclitaxel is itself antagonistic.

## F2 — RASolve 301 (recorded 2026-11-20)

Second-line RAS-mutant NSCLC, daraxonrasib vs docetaxel.

- Input: Phase 1/2 ORR 0.30–0.38 in previously treated RAS-mutant NSCLC.
- Forecast Phase III ORR: **0.36–0.39** (band 0.00–0.97).
- Directional claims: ORR and PFS favour daraxonrasib; the OS benefit is smaller than
  in PDAC and may not reach significance (CodeBreaK 200 precedent).
