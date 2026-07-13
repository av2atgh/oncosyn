"""Cohort-level agreement metrics for Phase II estimate vs Phase III observed ORR."""
from __future__ import annotations

import numpy as np
from scipy import stats as sstats


def agreement(estimate: list[float], observed: list[float]) -> dict:
    """Agreement stats between paired Phase II estimates and Phase III observations.

    Returns CCC (Lin), Pearson/Spearman, R^2, calibration slope/intercept
    (observed ~ estimate; ideal 1/0), and Bland-Altman bias + 95% limits of
    agreement. Metrics needing >=2 points (or variance) are None when undefined.
    """
    est = np.asarray(estimate, dtype=float)
    obs = np.asarray(observed, dtype=float)
    n = int(est.size)
    out: dict = {"n": n, "ccc": None, "pearson_r": None, "pearson_r2": None,
                 "spearman_rho": None, "calibration_slope": None,
                 "calibration_intercept": None, "ba_bias": None,
                 "ba_loa_low": None, "ba_loa_high": None}
    if n == 0:
        return out

    diff = est - obs
    out["ba_bias"] = float(diff.mean())
    if n >= 2:
        sd = float(diff.std(ddof=1))
        out["ba_loa_low"] = out["ba_bias"] - 1.96 * sd
        out["ba_loa_high"] = out["ba_bias"] + 1.96 * sd

    # Lin's concordance correlation coefficient (population moments)
    mx, my = est.mean(), obs.mean()
    vx, vy = est.var(), obs.var()
    cov = ((est - mx) * (obs - my)).mean()
    denom = vx + vy + (mx - my) ** 2
    if denom > 0:
        out["ccc"] = float(2 * cov / denom)

    # correlations + calibration need variation in both arms
    if n >= 2 and vx > 0 and vy > 0:
        out["pearson_r"] = float(sstats.pearsonr(est, obs)[0])
        out["pearson_r2"] = out["pearson_r"] ** 2
        out["spearman_rho"] = float(sstats.spearmanr(est, obs)[0])
        slope, intercept = np.polyfit(est, obs, 1)
        out["calibration_slope"] = float(slope)
        out["calibration_intercept"] = float(intercept)
    return out


def trend(orr: list[float], year: list[float]) -> dict:
    """Correlate ORR with completion year (re-test of the azam2021 no-trend finding)."""
    o = np.asarray(orr, dtype=float)
    y = np.asarray(year, dtype=float)
    if o.size < 2 or o.std() == 0 or y.std() == 0:
        return {"n": int(o.size), "pearson_r": None, "spearman_rho": None,
                "slope_per_year": None}
    slope, _ = np.polyfit(y, o, 1)
    return {"n": int(o.size), "pearson_r": float(sstats.pearsonr(y, o)[0]),
            "spearman_rho": float(sstats.spearmanr(y, o)[0]),
            "slope_per_year": float(slope)}
