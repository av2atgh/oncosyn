# Phase2 — ETL + analysis pipeline
# Usage:  make db  |  make etl  |  make analyze  |  make report  |  make all
#         make clean  |  make reset

PY      := python -m
DB      := data/processed/phase2.db
SCHEMA  := schema.sql
SEED    := seed.sql

.PHONY: all db etl extract transform load derive analyze report test clean reset

all: report

## --- database bootstrap -----------------------------------------------------
db: $(DB)

$(DB): $(SCHEMA) $(SEED)
	@mkdir -p data/processed
	sqlite3 $(DB) < $(SCHEMA)
	sqlite3 $(DB) < $(SEED)
	@echo "built $(DB)"

## --- ETL stages -------------------------------------------------------------
etl: extract transform load derive

extract:                       ## raw sources -> data/raw
	$(PY) phase2.extract

transform: extract             ## raw -> normalized rows in data/interim
	$(PY) phase2.transform

load: db transform             ## normalized rows -> SQLite base tables
	$(PY) phase2.load

derive: load                   ## fill derived cols (combination_size, regimen_class, is_targeted)
	$(PY) phase2.transform.derive

## --- analysis + reporting ---------------------------------------------------
analyze: derive                ## Bliss predictions, synergy, matched pairs, validation
	$(PY) phase2.analyze

report: analyze                ## cohort agreement stats + figures -> reports/
	$(PY) phase2.report

test:
	pytest -q

## --- housekeeping -----------------------------------------------------------
clean:                         ## drop generated intermediates + reports (keep DB)
	rm -rf data/interim/* reports/figures/* reports/*.html reports/*.csv

reset: clean                   ## also drop the database
	rm -f $(DB) $(DB)-wal $(DB)-shm
