# Phase2

Track and report cancer-treatment performance from Phase II and Phase III
clinical trials — **estimate ORR from Phase II** (observed or Bliss-predicted for
combinations) and **validate it against the ORR observed in matched Phase III
trials**. Extends Kang et al. 2013 (BMC Med Res Methodol 13:77) and
Azam & Vazquez 2021 (Cancers 13:178) with post-2020 data.

See `.claude/skills/phase2/SKILL.md` for full scope and `docs/data_schema.md`
for the data model.

## Layout

```
phase2/
├── schema.sql            SQLite DDL (11 tables + v_validation_pairs view)
├── seed.sql              lookup-table seed data (endpoint, response_criteria, tumor_type)
├── config.yaml           sources, analysis params, matching rules
├── Makefile              db -> etl -> analyze -> report
├── requirements.txt
├── data/
│   ├── raw/              stage-1 output: per-source extracted records
│   ├── interim/          stage-2 output: normalized CSVs (one per base table)
│   └── processed/        phase2.db lives here
├── reports/             cohort stats (*.csv) + figures/
├── forecasts/           dated Phase III ORR forecasts (forecasts.csv) + forecast.py
├── docs/data_schema.md
├── src/phase2/
│   ├── config.py, db.py
│   ├── extract/          stage 1: sources -> data/raw
│   ├── transform/        stage 2: raw -> normalized; derive.py: computed cols
│   ├── load/             stage 3: normalized -> SQLite
│   ├── analyze/          stage 4: bliss, matching, validate
│   └── report/           stage 5: agreement stats + figures
├── notebooks/
└── tests/
```

## Pipeline

```
extract  →  transform  →  load  →  derive  →  analyze  →  report
 raw/       interim/      DB      DB cols     bliss/       CCC, R², Bland–Altman,
 records    CSVs                  filled      matched_pair, calibration, shrinkage,
                                              validation    synergy + ORR trend
```

## Quickstart

```bash
pip install -r requirements.txt
make db        # create + seed data/processed/phase2.db
make all       # run full pipeline (extract → … → report)
make test      # pytest
make reset     # drop DB + intermediates
```

Individual stages: `make extract | transform | load | derive | analyze | report`.

> Stages currently print `TODO` — the schema, config, DB helpers, and Bliss
> formula are implemented; extraction/normalization/stats logic is scaffolded
> for fill-in.
