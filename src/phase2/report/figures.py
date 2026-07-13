"""Report figures (matplotlib, headless Agg backend).

Each function no-ops gracefully when there are too few points to plot.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def agreement_scatter(estimate, observed, agr: dict, path: Path) -> bool:
    """Phase II estimate vs Phase III observed, with identity + calibration lines."""
    if len(estimate) < 2:
        return False
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(estimate, observed, alpha=0.6, edgecolor="none")
    ax.plot([0, 1], [0, 1], "k--", lw=1, label="identity")
    if agr.get("calibration_slope") is not None:
        b, a = agr["calibration_slope"], agr["calibration_intercept"]
        ax.plot([0, 1], [a, a + b], "C1-", lw=1.5, label="calibration")
    ax.set(xlim=(0, 1), ylim=(0, 1), xlabel="Phase II ORR estimate",
           ylabel="Phase III observed ORR", title="Phase II -> III ORR agreement")
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return True


def orr_over_time(groups: dict, path: Path) -> bool:
    """Scatter of ORR (%) vs completion year, one colour per phase, with a
    linear fit per group. groups: {label: (years, orr_pct)}.
    """
    import numpy as np
    if not any(ys for ys, _ in groups.values()):
        return False
    colours = {"Phase II": "C0", "Phase III": "C1"}
    fig, ax = plt.subplots(figsize=(6, 4))
    for label, (ys, os) in groups.items():
        y, o = np.asarray(ys, float), np.asarray(os, float)
        c = colours.get(label, "C2")
        ax.scatter(y, o, s=10, alpha=0.35, color=c, edgecolor="none",
                   label=f"{label} (n={len(y)})")
        if len(y) >= 2 and y.std() > 0:
            b, a = np.polyfit(y, o, 1)
            xs = np.array([y.min(), y.max()])
            ax.plot(xs, a + b * xs, color=c, lw=2)
    from matplotlib.ticker import MaxNLocator
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))  # integer year ticks
    ax.set(xlabel="Trial completion year", ylabel="ORR (%)", ylim=(0, 100))
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return True


def survival_over_time(groups: dict, path: Path) -> bool:
    """Scatter of median survival (months) vs completion year, per endpoint, with fits."""
    import numpy as np
    from matplotlib.ticker import MaxNLocator
    if not any(ys for ys, _ in groups.values()):
        return False
    fig, ax = plt.subplots(figsize=(6, 4))
    for label, (ys, ms) in groups.items():
        y, m = np.asarray(ys, float), np.asarray(ms, float)
        sc = ax.scatter(y, m, s=10, alpha=0.35, edgecolor="none", label=f"{label} (n={len(y)})")
        if len(y) >= 2 and y.std() > 0:
            b, a = np.polyfit(y, m, 1)
            xs = np.array([y.min(), y.max()])
            ax.plot(xs, a + b * xs, color=sc.get_facecolor()[0], lw=2)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set(xlabel="Trial completion year", ylabel="Median survival (months)")
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return True


def orr_vs_survival(series: dict, path: Path) -> bool:
    """Scatter of median survival (months) against ORR (%), per endpoint, with fits."""
    import numpy as np
    if not any(xs for xs, _ in series.values()):
        return False
    fig, ax = plt.subplots(figsize=(5.6, 4.2))
    for label, (xs, ms) in series.items():
        x, m = np.asarray(xs, float), np.asarray(ms, float)
        sc = ax.scatter(x, m, s=12, alpha=0.4, edgecolor="none", label=f"{label} (n={len(x)})")
        if len(x) >= 2 and x.std() > 0:
            b, a = np.polyfit(x, m, 1)
            xf = np.array([x.min(), x.max()])
            ax.plot(xf, a + b * xf, color=sc.get_facecolor()[0], lw=2)
    ax.set(xlabel="ORR (%)", ylabel="Median survival (months)")
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return True


def orr_size_trend(series: dict, path: Path) -> bool:
    """Mean ORR (%) vs combination size, one line per series, with SEM bars.

    series: {label: (xs, ys, sems)}.
    """
    if not any(xs for xs, _, _ in series.values()):
        return False
    fig, ax = plt.subplots(figsize=(5.4, 4))
    for label, (xs, ys, es) in series.items():
        ax.errorbar(xs, ys, yerr=es, marker="o", capsize=3, lw=1.5, label=label)
    xs_all = sorted({x for xs, _, _ in series.values() for x in xs})
    ax.set(xlabel="Number of anticancer agents", ylabel="Mean ORR (%)")
    ax.set_xticks(xs_all)
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return True


def bland_altman(estimate, observed, agr: dict, path: Path) -> bool:
    """Bland-Altman: mean of the pair vs their difference, with bias + LoA."""
    if len(estimate) < 2:
        return False
    import numpy as np
    est, obs = np.asarray(estimate, float), np.asarray(observed, float)
    mean, diff = (est + obs) / 2, est - obs
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.scatter(mean, diff, alpha=0.6, edgecolor="none")
    for y, ls, lbl in ((agr["ba_bias"], "-", "bias"),
                       (agr["ba_loa_low"], "--", "-1.96 SD"),
                       (agr["ba_loa_high"], "--", "+1.96 SD")):
        ax.axhline(y, color="C3", ls=ls, lw=1)
        ax.text(0.99, y, f" {lbl}", va="bottom", ha="right",
                transform=ax.get_yaxis_transform(), fontsize=7, color="C3")
    ax.axhline(0, color="k", lw=0.6)
    ax.set(xlabel="mean of Phase II & III ORR", ylabel="Phase II − Phase III ORR",
           title="Bland–Altman")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return True
