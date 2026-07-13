-- Phase2 — SQLite DDL
-- Trial performance tracking + Phase II ORR estimate → Phase III validation.
-- Grain: trial → arm → (regimen, outcomes); matched_pair + validation on top.
--
-- Conventions:
--   * rates/ORR stored as fractions in [0,1] (format to % at report time)
--   * dates ISO-8601 text; enums enforced via CHECK constraints
--   * derived cols (combination_size, regimen_class, is_targeted) filled by the
--     pipeline, not hand-entered
--
-- Load with:  sqlite3 phase2.db < schema.sql

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-------------------------------------------------------------------------------
-- Dimension / lookup tables (controlled vocabularies)
-------------------------------------------------------------------------------

CREATE TABLE tumor_type (
    tumor_type   TEXT PRIMARY KEY,
    description  TEXT
);

CREATE TABLE endpoint (
    endpoint     TEXT PRIMARY KEY,   -- ORR, CR, PR, DCR, DoR, PFS, TTP, OS, ...
    kind         TEXT NOT NULL CHECK (kind IN ('response','time_to_event','pro')),
    description  TEXT
);

CREATE TABLE response_criteria (
    response_criteria TEXT PRIMARY KEY,  -- RECIST1.1, iRECIST, WHO, other
    description       TEXT
);

-------------------------------------------------------------------------------
-- 1. trial
-------------------------------------------------------------------------------

CREATE TABLE trial (
    trial_id         TEXT PRIMARY KEY,
    nct_id           TEXT,
    source_ref       TEXT NOT NULL,                 -- kang2013 / azam2021 / update2026 / PMID
    phase            TEXT NOT NULL CHECK (phase IN ('II','II/III','III')),
    title            TEXT,
    tumor_type       TEXT NOT NULL REFERENCES tumor_type(tumor_type),
    tumor_subtype    TEXT,
    line_of_therapy  TEXT CHECK (line_of_therapy IN
                        ('1L','2L','3L+','adjuvant','neoadjuvant','mixed')),
    n_arms           INTEGER CHECK (n_arms >= 0),
    n_subjects       INTEGER CHECK (n_subjects >= 0),
    start_year       INTEGER,
    completion_year  INTEGER,
    randomized       INTEGER CHECK (randomized IN (0,1)),  -- boolean
    region           TEXT,
    extracted_at     TEXT,                                   -- ISO-8601 provenance
    -- matches transform's trial natural key (source_ref + nct_id): the same NCT
    -- may appear once per source cohort (cohorts stay separable), while true
    -- duplicates within a cohort are still rejected. NULL nct_ids don't collide.
    UNIQUE (source_ref, nct_id)
);

CREATE INDEX idx_trial_phase       ON trial(phase);
CREATE INDEX idx_trial_tumor       ON trial(tumor_type);
CREATE INDEX idx_trial_source      ON trial(source_ref);

-------------------------------------------------------------------------------
-- 2. arm
-------------------------------------------------------------------------------

CREATE TABLE arm (
    arm_id            TEXT PRIMARY KEY,
    trial_id          TEXT NOT NULL REFERENCES trial(trial_id) ON DELETE CASCADE,
    arm_label         TEXT,
    is_control        INTEGER CHECK (is_control IN (0,1)),
    n_subjects        INTEGER CHECK (n_subjects >= 0),         -- denominator N
    combination_size  INTEGER CHECK (combination_size >= 0),   -- derived
    regimen_class     TEXT CHECK (regimen_class IN
                        ('targeted','cytotoxic','mixed','other'))  -- derived
);

CREATE INDEX idx_arm_trial ON arm(trial_id);

-------------------------------------------------------------------------------
-- 3. agent
-------------------------------------------------------------------------------

CREATE TABLE agent (
    agent_id     TEXT PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    synonyms     TEXT,                    -- JSON array of aliases
    drug_class   TEXT CHECK (drug_class IN
                    ('hormonal','mAb','kinase_inhibitor','proteasome_inhibitor',
                     'checkpoint_inhibitor','car_t','cytotoxic','radiation',
                     'surgery','steroid','other')),
    is_targeted  INTEGER CHECK (is_targeted IN (0,1)),  -- derived from drug_class
    target       TEXT
);

-------------------------------------------------------------------------------
-- 4. regimen_component  (arm ⇄ agent junction)
-------------------------------------------------------------------------------

CREATE TABLE regimen_component (
    arm_id     TEXT NOT NULL REFERENCES arm(arm_id) ON DELETE CASCADE,
    agent_id   TEXT NOT NULL REFERENCES agent(agent_id),
    dose       TEXT,
    dose_unit  TEXT,
    schedule   TEXT,
    PRIMARY KEY (arm_id, agent_id)
);

CREATE INDEX idx_regcomp_agent ON regimen_component(agent_id);

-------------------------------------------------------------------------------
-- 5. outcome  (long format: one row per arm × endpoint)
-------------------------------------------------------------------------------

CREATE TABLE outcome (
    outcome_id        TEXT PRIMARY KEY,
    arm_id            TEXT NOT NULL REFERENCES arm(arm_id) ON DELETE CASCADE,
    endpoint          TEXT NOT NULL REFERENCES endpoint(endpoint),
    response_criteria TEXT REFERENCES response_criteria(response_criteria),
    value             REAL,                       -- fraction, or median time
    value_unit        TEXT CHECK (value_unit IN ('fraction','months','score')),
    n_events          INTEGER CHECK (n_events >= 0),   -- responders / events
    n_at_risk         INTEGER CHECK (n_at_risk >= 0),  -- denominator N
    ci_low            REAL,
    ci_high           REAL,
    ci_method         TEXT,                       -- beta_posterior, binomial_exact
    hr                REAL,
    rmst_diff         REAL,
    timepoint_months  REAL,                       -- for milestone endpoints
    CHECK (ci_low IS NULL OR ci_high IS NULL OR ci_low <= ci_high)
);

CREATE INDEX idx_outcome_arm      ON outcome(arm_id);
CREATE INDEX idx_outcome_endpoint ON outcome(endpoint);
-- one value per (arm, endpoint, criteria, timepoint)
CREATE UNIQUE INDEX uq_outcome
    ON outcome(arm_id, endpoint, IFNULL(response_criteria,''), IFNULL(timepoint_months,-1));

-------------------------------------------------------------------------------
-- 6. bliss_prediction  (expected combination ORR under Bliss independence)
-------------------------------------------------------------------------------

CREATE TABLE bliss_prediction (
    bliss_id             TEXT PRIMARY KEY,
    arm_id               TEXT NOT NULL UNIQUE REFERENCES arm(arm_id) ON DELETE CASCADE,
    orr_expected         REAL,        -- 1 - Π(1 - orr_i)
    orr_expected_ci_low  REAL,
    orr_expected_ci_high REAL,
    component_orr_source TEXT,         -- JSON {agent_id: single_agent_orr}
    orr_observed         REAL,         -- copied from arm's ORR outcome
    delta                REAL,         -- orr_observed - orr_expected
    interaction          TEXT CHECK (interaction IN ('synergy','antagonism','none')),
    p_value              REAL,
    p_adjusted           REAL          -- Bonferroni
);

-------------------------------------------------------------------------------
-- 7. matched_pair  (Phase II arm ↔ confirming Phase III arm)
-------------------------------------------------------------------------------

CREATE TABLE matched_pair (
    pair_id          TEXT PRIMARY KEY,
    phase2_arm_id    TEXT NOT NULL REFERENCES arm(arm_id) ON DELETE CASCADE,
    phase3_arm_id    TEXT NOT NULL REFERENCES arm(arm_id) ON DELETE CASCADE,
    match_key        TEXT,            -- regimen+tumor+line signature
    match_method     TEXT CHECK (match_method IN
                        ('exact_regimen','same_agents_diff_dose','manual')),
    match_confidence TEXT CHECK (match_confidence IN ('high','medium','low')),
    UNIQUE (phase2_arm_id, phase3_arm_id)
);

CREATE INDEX idx_pair_p2 ON matched_pair(phase2_arm_id);
CREATE INDEX idx_pair_p3 ON matched_pair(phase3_arm_id);

-------------------------------------------------------------------------------
-- 8. validation  (Phase II estimate vs Phase III observed ORR)
-------------------------------------------------------------------------------

CREATE TABLE validation (
    validation_id            TEXT PRIMARY KEY,
    pair_id                  TEXT NOT NULL REFERENCES matched_pair(pair_id) ON DELETE CASCADE,
    orr_phase2_estimate      REAL,
    estimate_source          TEXT CHECK (estimate_source IN
                                ('phase2_observed','bliss_expected')),
    orr_phase2_ci_low        REAL,
    orr_phase2_ci_high       REAL,
    orr_phase3_observed      REAL,
    shrinkage                REAL,     -- orr_phase2_estimate - orr_phase3_observed
    within_ci                INTEGER CHECK (within_ci IN (0,1)),  -- validates?
    stratum_regimen_class    TEXT CHECK (stratum_regimen_class IN
                                ('targeted','cytotoxic','mixed','other')),
    stratum_combination_size INTEGER
);

CREATE INDEX idx_validation_pair ON validation(pair_id);

-------------------------------------------------------------------------------
-- Convenience view: matched-pair ORR comparison for cohort-level agreement
-- stats (CCC, R², Bland–Altman, calibration) computed in the analysis layer.
-------------------------------------------------------------------------------

CREATE VIEW v_validation_pairs AS
SELECT
    v.validation_id,
    v.pair_id,
    mp.match_confidence,
    p2.trial_id            AS phase2_trial_id,
    p3.trial_id            AS phase3_trial_id,
    v.estimate_source,
    v.orr_phase2_estimate,
    v.orr_phase3_observed,
    v.shrinkage,
    v.within_ci,
    v.stratum_regimen_class,
    v.stratum_combination_size
FROM validation v
JOIN matched_pair mp ON mp.pair_id       = v.pair_id
JOIN arm         p2 ON p2.arm_id         = mp.phase2_arm_id
JOIN arm         p3 ON p3.arm_id         = mp.phase3_arm_id;
