---
name: phase2
description: Track and report the performance of cancer treatment from Phase II and Phase III clinical trials — response-rate (ORR) analysis, drug-combination synergy/antagonism, and modern time-to-event/value endpoints. Use for any phase2 work on trial performance metrics, endpoint tracking, synergy modeling, or outcome reporting.
---

# Phase2 — Cancer Treatment Trial Performance

## Scope

Track and report the performance of cancer treatment based on Phase II and
Phase III clinical trials. The project collects trial-level outcome data,
computes efficacy and drug-interaction metrics, and reports on how treatment
performance evolves — extending the analysis of the reference papers with
**more recent (post-2020) trial data** and updated methodology.

The central objective is to **estimate ORR from Phase II data** (single-agent,
combination, and Bliss-predicted) and **validate those estimates against the
ORR observed in the corresponding Phase III trials** — quantifying how well
Phase II ORR predicts Phase III ORR, and where (and why) the prediction breaks
down.

## Key references

- Kang W, DiPaola RS, Vazquez A. *Inference of synergy/antagonism between
  anticancer drugs from the pooled analysis of clinical trials.*
  BMC Medical Research Methodology 2013, 13:77.
  https://link.springer.com/article/10.1186/1471-2288-13-77 ·
  full text: https://pmc.ncbi.nlm.nih.gov/articles/PMC3694030/
- Azam F, Vazquez A. *Trends in Phase II Trials for Cancer Therapies.*
  Cancers 2021, 13(2):178.
  https://www.mdpi.com/2072-6694/13/2/178 ·
  full text: https://pmc.ncbi.nlm.nih.gov/articles/PMC7825663/

> **Note on framing.** Both references analyze **Phase II drug-combination
> synergy from ORR** (a Bliss-independence null model). This project reproduces
> and updates that work **and extends it to Phase II→Phase III validation**:
> the ORR estimated from Phase II is tested against the ORR observed in the
> matched Phase III trials.

---

## Metrics and endpoints to track

Modeled on the reference papers (ORR + Bliss synergy), extended with the
endpoints and statistics that are standard practice for a 2020–2026 update.

### (A) Efficacy endpoints

| Endpoint | Definition | Role in this project |
|---|---|---|
| **ORR** (CR + PR) | RECIST 1.1: PR ≥ 30% ↓ in sum of target-lesion diameters; CR = disappearance | **Primary** readout — the only endpoint in both refs |
| **CR / PR** | Complete / partial response components | Granular efficacy breakdown |
| **DCR** | CR + PR + SD (stable disease) | Broader activity signal |
| **DoR** | Duration of response (response → progression/death) | Durability alongside ORR (accelerated-approval basis) *[extension]* |
| **PFS / TTP** | (Time to) progression-free survival | Phase III primary/co-primary *[extension]* |
| **OS** | Overall survival (time to death) | Gold-standard Phase III endpoint *[extension]* |
| **Milestone survival** | OS/PFS rate at fixed 1/2/3/5 yr | Captures the immunotherapy "tail" *[extension]* |
| **PROs / QoL** | Patient-reported outcomes | Value-framework input *[extension]* |

For immunotherapy trials, record response under **iRECIST** (iUPD → iCPD
confirmation) to handle pseudoprogression, not RECIST 1.1 alone. *[extension]*

### (B) Statistical measures

- **Observed ORR (ORR_O)** as % with binomial **95% CI**; modeled as
  **Binomial(N, p)** with a **Bayesian Beta posterior** (α = Σnᵢ, β = Σ(Nᵢ−nᵢ)).
- **Expected combination ORR (ORR_E) — Bliss independence** (core formula from
  both refs): `ORR_E = 100% × [1 − (1 − ORR_A/100)(1 − ORR_B/100)]`;
  generally, `q = 1 − Π(1 − pᵢ)`.
- **Interaction term** `ΔJ_ij = J_ij − J°_ij` flags synergy/antagonism between
  agents i and j.
- **Comparisons:** two-tailed Student's t-test at 5% with **Bonferroni
  correction**; Kolmogorov–Smirnov to compare ORR distributions across
  agent/tumor classes.
- **Time-to-event *[extension]*:** **hazard ratio (HR)** + 95% CI, log-rank,
  Kaplan–Meier median PFS/OS. Because immunotherapy violates proportional
  hazards, also report **Restricted Mean Survival Time (RMST)** difference/ratio
  and milestone survival.
- **Surrogacy *[extension]*:** trial-level **R²** (weighted regression of
  log-HR_surrogate vs log-HR_OS) and individual-level correlation (Kendall τ).

### (C) Thresholds / decision rules

- **Synergy:** ORR_O > ORR_E with p < 0.05 (after Bonferroni).
- **Antagonism:** ORR_O < ORR_E with p < 0.05.
- **Clinically meaningful benefit:** score with **ESMO-MCBS v1.1**
  (≥ 4 = substantial) and **ASCO Value Framework NHB v2** (≥ 45 substantial,
  ≤ 40 low). *[extension]*
- **Surrogacy strength convention:** trial-level R² ≥ 0.7–0.8 strong,
  0.5–0.7 moderate, < 0.5 weak. *[extension]*

### (D) Drug / trial classification

- **Targeted** (hormonals, mAbs, kinase/proteasome inhibitors, checkpoint
  inhibitors, CAR-T) vs **non-targeted cytotoxics**; radiation/surgery/steroids
  recorded but unclassified.
- Group ORR by **combination size** (single / 2-agent / 3+-agent), tumor type,
  and **time window** (to test whether ORR improves with newer targeted agents —
  the 2021 paper found no temporal gain through 2020; the update re-tests this
  with post-2020 data).

### (E) Phase II → Phase III ORR validation (core objective)

Estimate ORR from Phase II and check it against Phase III observed ORR.

- **Trial matching:** link each Phase III arm to its supporting Phase II
  trial(s) by regimen (agents + doses), tumor type, and line of therapy. Keep a
  matched Phase II / Phase III pair table as the unit of analysis.
- **Phase II ORR estimate (predictor):** for combinations, the Bliss-predicted
  `ORR_E` from constituent single-agent ORRs; for regimens tested directly in
  Phase II, the observed Phase II ORR with its Beta-posterior CI.
- **Phase III ORR (ground truth):** observed ORR in the matched Phase III arm.
- **Validation metrics:**
  - agreement — Pearson/Spearman/**concordance correlation (CCC)**, **R²**, and
    **Bland–Altman** bias/limits-of-agreement between Phase II-estimated and
    Phase III-observed ORR;
  - calibration — regression slope/intercept of Phase III vs Phase II ORR
    (ideal slope 1, intercept 0);
  - the systematic **ORR shrinkage** from Phase II to Phase III (efficacy often
    drops in the larger, less selected Phase III population);
  - stratified agreement by targeted vs cytotoxic, combination size, and tumor
    type — to locate where Phase II over-predicts.
- **Decision rule:** a Phase II regimen "validates" if the Phase III ORR falls
  within the predicted CI; flag over-optimistic predictions (Phase II CI
  excludes the lower Phase III value).

---

## Update goals (what "more recent data" means here)

1. Extend the Azam & Vazquez 2021 dataset (1,002 trials / through ~2020) with
   **Phase II (and Phase III) trials from ~2020–2026**.
2. Re-test whether ORR improves over time as targeted-agent share grows.
3. Recompute synergy/antagonism pairs on the enlarged dataset.
4. **Estimate ORR from Phase II and validate against matched Phase III ORR**
   (section E) — the core deliverable: quantify prediction accuracy,
   calibration, and Phase II→III shrinkage.
5. Add the modern endpoint panel (DoR, PFS/OS, RMST, iRECIST) and value scores
   (ESMO-MCBS, ASCO-NHB) beyond ORR-only.
6. *[extension]* Add a trial-level surrogacy module relating Phase II ORR/PFS to
   Phase III OS (does Phase II ORR predict Phase III survival, not just ORR).
