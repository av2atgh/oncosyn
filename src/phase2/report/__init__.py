"""Stage 5 — report: cohort-level agreement stats + figures.

Reads the analysis tables and computes Phase II->III ORR agreement across the
cohort, plus the synergy summary and ORR-over-time trend, writing:
  * reports/agreement.csv            CCC, Pearson/Spearman, R^2, calibration, Bland-Altman
  * reports/shrinkage_by_stratum.csv mean Phase II->III shrinkage by regimen_class / combo size
  * reports/synergy_summary.csv      interaction counts + the synergy/antagonism arms
  * reports/orr_trend.csv            ORR vs completion year (re-test of azam2021)
  * reports/orr_by_combination_size.csv
  * reports/figures/agreement_scatter.png, bland_altman.png

Empty inputs produce header-only CSVs and skipped figures rather than errors.
"""
from __future__ import annotations

import csv
from pathlib import Path

from .. import config, db
from . import figures, metrics


def _reports_dir(cfg: dict) -> Path:
    rp = Path(cfg["paths"]["reports"])
    return rp if rp.is_absolute() else config.ROOT / rp


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _shrinkage_by(rows, stratum: str, key: str) -> list[dict]:
    groups: dict = {}
    for r in rows:
        groups.setdefault(r[key], []).append(r["shrinkage"])
    return [{"stratum": stratum, "group": k, "n": len(vals),
             "mean_shrinkage": _mean(vals)}
            for k, vals in sorted(groups.items(), key=lambda kv: (kv[0] is None, kv[0]))]


def run() -> None:
    cfg = config.load()
    reports = _reports_dir(cfg)
    figs = reports / "figures"
    figs.mkdir(parents=True, exist_ok=True)

    with db.session() as conn:
        val = [dict(r) for r in conn.execute("SELECT * FROM v_validation_pairs")]
        bliss = [dict(r) for r in conn.execute("SELECT * FROM bliss_prediction")]
        orr = [dict(r) for r in conn.execute(
            "SELECT o.value AS orr, t.completion_year AS year, a.regimen_class, "
            "       a.combination_size AS size "
            "FROM outcome o JOIN arm a ON a.arm_id = o.arm_id "
            "JOIN trial t ON t.trial_id = a.trial_id "
            "WHERE o.endpoint = 'ORR' AND o.value IS NOT NULL")]
        # median OS/PFS (months) with year + phase
        surv_rows = [dict(r) for r in conn.execute(
            "SELECT o.endpoint AS ep, o.value AS m, t.completion_year AS yr, t.phase AS ph "
            "FROM outcome o JOIN arm a ON a.arm_id = o.arm_id "
            "JOIN trial t ON t.trial_id = a.trial_id "
            "WHERE o.endpoint IN ('OS','PFS') AND o.value_unit = 'months' "
            "AND o.value IS NOT NULL AND t.completion_year BETWEEN 2005 AND 2026")]
        # per-arm pivot of ORR / OS / PFS for the predictability analysis
        pivot_rows = [dict(r) for r in conn.execute(
            "SELECT a.arm_id, t.phase AS ph, "
            "  MAX(CASE WHEN o.endpoint='ORR' THEN o.value END) AS orr, "
            "  MAX(CASE WHEN o.endpoint='OS'  THEN o.value END) AS os, "
            "  MAX(CASE WHEN o.endpoint='PFS' THEN o.value END) AS pfs "
            "FROM arm a JOIN trial t ON t.trial_id = a.trial_id "
            "JOIN outcome o ON o.arm_id = a.arm_id "
            "WHERE o.endpoint IN ('ORR','OS','PFS') GROUP BY a.arm_id")]
        # ORR over time, by phase (figure)
        time_rows = [dict(r) for r in conn.execute(
            "SELECT o.value AS v, t.completion_year AS yr, t.phase AS ph "
            "FROM outcome o JOIN arm a ON a.arm_id = o.arm_id "
            "JOIN trial t ON t.trial_id = a.trial_id "
            "WHERE o.endpoint = 'ORR' AND o.value IS NOT NULL "
            "AND t.completion_year BETWEEN 2005 AND 2026")]
        # ORR-by-size, flagged for presence of a targeted agent
        trend_rows = [dict(r) for r in conn.execute(
            "SELECT a.combination_size AS sz, o.value AS v, "
            "  (SELECT COUNT(*) FROM regimen_component rc "
            "     JOIN agent ag ON ag.agent_id = rc.agent_id "
            "   WHERE rc.arm_id = a.arm_id AND ag.is_targeted = 1) AS tgt "
            "FROM arm a JOIN outcome o ON o.arm_id = a.arm_id AND o.endpoint = 'ORR' "
            "WHERE a.combination_size BETWEEN 1 AND 5 AND o.value IS NOT NULL")]

    # --- agreement -------------------------------------------------------
    est = [r["orr_phase2_estimate"] for r in val if r["orr_phase2_estimate"] is not None]
    obs = [r["orr_phase3_observed"] for r in val if r["orr_phase2_estimate"] is not None]
    agr = metrics.agreement(est, obs)
    _write_csv(reports / "agreement.csv", list(agr), [agr])

    # --- shrinkage by stratum -------------------------------------------
    shr = [r for r in val if r["shrinkage"] is not None]
    strat_rows = (_shrinkage_by(shr, "regimen_class", "stratum_regimen_class")
                  + _shrinkage_by(shr, "combination_size", "stratum_combination_size"))
    _write_csv(reports / "shrinkage_by_stratum.csv",
               ["stratum", "group", "n", "mean_shrinkage"], strat_rows)

    # --- synergy summary -------------------------------------------------
    counts: dict = {"synergy": 0, "antagonism": 0, "none": 0}
    for b in bliss:
        counts[b["interaction"]] = counts.get(b["interaction"], 0) + 1
    _write_csv(reports / "synergy_summary.csv", ["interaction", "n"],
               [{"interaction": k, "n": v} for k, v in counts.items()])
    _write_csv(reports / "synergy_pairs.csv",
               ["arm_id", "interaction", "orr_expected", "orr_observed", "delta", "p_adjusted"],
               [{k: b[k] for k in ("arm_id", "interaction", "orr_expected",
                                   "orr_observed", "delta", "p_adjusted")}
                for b in bliss if b["interaction"] != "none"])

    # --- ORR trend + by combination size --------------------------------
    yr = [(r["orr"], r["year"]) for r in orr if r["year"] is not None]
    tr = metrics.trend([o for o, _ in yr], [y for _, y in yr])
    _write_csv(reports / "orr_trend.csv", list(tr), [tr])
    size_groups: dict = {}
    for r in orr:
        size_groups.setdefault(r["size"], []).append(r["orr"])
    _write_csv(reports / "orr_by_combination_size.csv",
               ["combination_size", "n", "mean_orr"],
               [{"combination_size": k, "n": len(v), "mean_orr": _mean(v)}
                for k, v in sorted(size_groups.items(), key=lambda kv: (kv[0] is None, kv[0]))])

    # ORR-by-size series (mean %, SEM) for all arms and targeted-containing arms
    def _series(pred):
        xs, ys, es = [], [], []
        for s in range(1, 6):
            vals = [r["v"] for r in trend_rows if r["sz"] == s and pred(r)]
            if len(vals) >= 3:
                m = sum(vals) / len(vals)
                sd = (sum((x - m) ** 2 for x in vals) / (len(vals) - 1)) ** 0.5
                xs.append(s); ys.append(100 * m); es.append(100 * sd / len(vals) ** 0.5)
        return xs, ys, es
    size_series = {"All arms": _series(lambda r: True),
                   "Contains targeted agent": _series(lambda r: r["tgt"] > 0)}

    # --- survival over time + ORR->survival predictability ---------------
    import numpy as np
    from scipy import stats as sstats

    def _corr(xs, ys):
        x, y = np.asarray(xs, float), np.asarray(ys, float)
        if len(x) < 3 or x.std() == 0 or y.std() == 0:
            return {"n": int(len(x)), "slope": None, "pearson_r": None,
                    "pearson_r2": None, "spearman_rho": None, "p": None}
        sl, _, r, p, _ = sstats.linregress(x, y)
        return {"n": int(len(x)), "slope": float(sl), "pearson_r": float(r),
                "pearson_r2": float(r * r),
                "spearman_rho": float(sstats.spearmanr(x, y).correlation),
                "p": float(p)}

    surv_groups = {
        "Median OS": ([r["yr"] for r in surv_rows if r["ep"] == "OS"],
                      [r["m"] for r in surv_rows if r["ep"] == "OS"]),
        "Median PFS": ([r["yr"] for r in surv_rows if r["ep"] == "PFS"],
                       [r["m"] for r in surv_rows if r["ep"] == "PFS"]),
    }
    _COLS = ["endpoint", "phase", "n", "slope", "pearson_r", "pearson_r2", "spearman_rho", "p"]
    surv_trend = []
    for ep in ("OS", "PFS"):
        for ph_label, phases in (("all", None), ("II", {"II", "II/III"}), ("III", {"III"})):
            sub = [r for r in surv_rows if r["ep"] == ep
                   and (phases is None or r["ph"] in phases)]
            surv_trend.append({"endpoint": ep, "phase": ph_label,
                               **_corr([r["yr"] for r in sub], [r["m"] for r in sub])})
    _write_csv(reports / "survival_trend.csv", _COLS,
               [{k: d.get(k) for k in _COLS} for d in surv_trend])

    os_pairs = [(100 * r["orr"], r["os"]) for r in pivot_rows
                if r["orr"] is not None and r["os"] is not None]
    pfs_pairs = [(100 * r["orr"], r["pfs"]) for r in pivot_rows
                 if r["orr"] is not None and r["pfs"] is not None]
    _PC = ["survival_endpoint", "n", "slope", "pearson_r", "pearson_r2", "spearman_rho", "p"]
    pred = [{"survival_endpoint": lbl, **_corr([x for x, _ in pr], [y for _, y in pr])}
            for lbl, pr in (("OS", os_pairs), ("PFS", pfs_pairs))]
    _write_csv(reports / "orr_survival_predictability.csv", _PC,
               [{k: d.get(k) for k in _PC} for d in pred])
    pred_series = {"OS": ([x for x, _ in os_pairs], [y for _, y in os_pairs]),
                   "PFS": ([x for x, _ in pfs_pairs], [y for _, y in pfs_pairs])}

    def _phase_group(phases):
        pts = [(r["yr"], 100 * r["v"]) for r in time_rows if r["ph"] in phases]
        return [y for y, _ in pts], [o for _, o in pts]
    time_groups = {"Phase II": _phase_group({"II", "II/III"}),
                   "Phase III": _phase_group({"III"})}

    # --- figures ---------------------------------------------------------
    n_fig = sum([
        figures.orr_over_time(time_groups, figs / "orr_over_time.png"),
        figures.survival_over_time(surv_groups, figs / "survival_over_time.png"),
        figures.orr_vs_survival(pred_series, figs / "orr_vs_survival.png"),
        figures.agreement_scatter(est, obs, agr, figs / "agreement_scatter.png"),
        figures.bland_altman(est, obs, agr, figs / "bland_altman.png"),
        figures.orr_size_trend(size_series, figs / "orr_size_trend.png"),
    ])
    print(f"[report] {len(val)} validated pairs, {len(bliss)} bliss rows; "
          f"CSVs + {n_fig} figures -> {reports}")
