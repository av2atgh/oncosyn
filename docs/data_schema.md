# Phase2 — Data Schema

Normalized relational schema for tracking trial performance and validating
Phase II ORR estimates against Phase III. Grain runs trial → arm → (regimen,
outcomes); matched pairs and validation sit on top.

```
agent ──< regimen_component >── arm >── trial
                                 │
                                 ├──< outcome
                                 └──< bliss_prediction
matched_pair (phase2_arm ↔ phase3_arm) ──< validation
```

Conventions: `*_id` = surrogate PK; snake_case; ORR/rates stored as fractions
[0,1] (not %); dates ISO-8601; nullable unless "NOT NULL".

---

## 1. `trial`
One row per clinical trial.

| column | type | notes |
|---|---|---|
| trial_id | text PK | internal id |
| nct_id | text | ClinicalTrials.gov id, unique when present |
| source_ref | text | `kang2013` / `azam2021` / `update2026` / PMID |
| phase | enum | `II`, `II/III`, `III` NOT NULL |
| title | text | |
| tumor_type | text | NOT NULL (controlled vocab, see `tumor_type` dim) |
| tumor_subtype | text | histology/molecular subtype |
| line_of_therapy | enum | `1L`, `2L`, `3L+`, `adjuvant`, `neoadjuvant`, `mixed` |
| n_arms | int | |
| n_subjects | int | enrolled total |
| start_year | int | |
| completion_year | int | |
| randomized | bool | single-arm vs randomized |
| region | text | |

## 2. `arm`
One row per treatment arm (the unit of ORR analysis).

| column | type | notes |
|---|---|---|
| arm_id | text PK | |
| trial_id | text FK→trial | NOT NULL |
| arm_label | text | e.g. "experimental", "control" |
| is_control | bool | |
| n_subjects | int | arm size (denominator N) |
| combination_size | int | # distinct anticancer agents (derived from regimen_component) |
| regimen_class | enum | `targeted`, `cytotoxic`, `mixed`, `other` (derived) |

## 3. `agent`
Drug dictionary (deduped across trials).

| column | type | notes |
|---|---|---|
| agent_id | text PK | |
| name | text | canonical NOT NULL, unique |
| synonyms | text[] | brand/aliases for matching |
| drug_class | enum | `hormonal`, `mAb`, `kinase_inhibitor`, `proteasome_inhibitor`, `checkpoint_inhibitor`, `car_t`, `cytotoxic`, `radiation`, `surgery`, `steroid`, `other` |
| is_targeted | bool | derived from drug_class |
| target | text | molecular target (e.g. EGFR, CD20) |

## 4. `regimen_component`
Junction: agents composing an arm (many-to-many).

| column | type | notes |
|---|---|---|
| arm_id | text FK→arm | PK part |
| agent_id | text FK→agent | PK part |
| dose | text | as reported |
| dose_unit | text | |
| schedule | text | e.g. "q3w", "daily" |

## 5. `outcome`
One row per (arm, endpoint) — long format for a multi-endpoint panel.

| column | type | notes |
|---|---|---|
| outcome_id | text PK | |
| arm_id | text FK→arm | NOT NULL |
| endpoint | enum | `ORR`,`CR`,`PR`,`DCR`,`DoR`,`PFS`,`TTP`,`OS`,`milestone_OS`,`milestone_PFS`,`PRO` NOT NULL |
| response_criteria | enum | `RECIST1.1`, `iRECIST`, `WHO`, `other` (for response endpoints) |
| value | numeric | rate as fraction, or median time |
| value_unit | enum | `fraction`, `months`, `score` |
| n_events | int | responders (ORR numerator) or events |
| n_at_risk | int | denominator N |
| ci_low | numeric | 95% CI |
| ci_high | numeric | 95% CI |
| ci_method | text | e.g. `beta_posterior`, `binomial_exact` |
| hr | numeric | hazard ratio vs control (time-to-event) |
| rmst_diff | numeric | restricted mean survival time difference |
| timepoint_months | numeric | for milestone endpoints |

## 6. `bliss_prediction`
Expected combination ORR under Bliss independence (predictor side).

| column | type | notes |
|---|---|---|
| bliss_id | text PK | |
| arm_id | text FK→arm | the combination arm NOT NULL |
| orr_expected | numeric | `1 − Π(1 − orr_i)` from constituent single-agent ORRs |
| orr_expected_ci_low | numeric | propagated / posterior CI |
| orr_expected_ci_high | numeric | |
| component_orr_source | jsonb | {agent_id: single_agent_orr} used |
| orr_observed | numeric | copied from arm's ORR outcome for convenience |
| delta | numeric | orr_observed − orr_expected |
| interaction | enum | `synergy`, `antagonism`, `none` |
| p_value | numeric | vs Bliss null |
| p_adjusted | numeric | Bonferroni |

## 7. `matched_pair`
Links a Phase II arm to its confirming Phase III arm (validation unit).

| column | type | notes |
|---|---|---|
| pair_id | text PK | |
| phase2_arm_id | text FK→arm | NOT NULL |
| phase3_arm_id | text FK→arm | NOT NULL |
| match_key | text | regimen+tumor+line signature used to match |
| match_method | enum | `exact_regimen`, `same_agents_diff_dose`, `manual` |
| match_confidence | enum | `high`, `medium`, `low` |

## 8. `validation`
Phase II-estimated vs Phase III-observed ORR agreement (one per matched pair).

| column | type | notes |
|---|---|---|
| validation_id | text PK | |
| pair_id | text FK→matched_pair | NOT NULL |
| orr_phase2_estimate | numeric | observed Phase II ORR or Bliss `orr_expected` |
| estimate_source | enum | `phase2_observed`, `bliss_expected` |
| orr_phase2_ci_low | numeric | |
| orr_phase2_ci_high | numeric | |
| orr_phase3_observed | numeric | ground truth |
| shrinkage | numeric | orr_phase2_estimate − orr_phase3_observed |
| within_ci | bool | Phase III ORR inside Phase II CI → "validates" |
| stratum_regimen_class | enum | for stratified agreement |
| stratum_combination_size | int | |

Cohort-level agreement stats (CCC, R², Bland–Altman bias/LoA, calibration
slope/intercept) are computed over the `validation` rows in the analysis layer,
not stored per row.

---

## Dimension / lookup tables
`tumor_type`, `drug_class`, `endpoint`, `response_criteria` — controlled
vocabularies referenced above; keep as small seed tables for join-time validation.

## Notes
- Store rates as fractions; format to % only at report time.
- `combination_size`, `regimen_class`, `is_targeted` are **derived** — compute
  in the pipeline, don't hand-enter.
- Provenance (`source_ref`, PMID, extraction date) travels on every base row so
  the 2013/2021 vs post-2020 update cohorts stay separable.
