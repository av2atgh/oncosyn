#!/usr/bin/env python3
"""Generate supp_tables.tex: longtables of every synergistic / antagonistic
combination, read from the phase2 analysis database. Reproducible: rerun after
the pipeline to refresh the supplement.

    python make_supp.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "processed" / "phase2.db"
OUT = Path(__file__).resolve().parent / "supp_tables.tex"

_ESC = {"&": r"\&", "%": r"\%", "_": " ", "#": r"\#", "$": r"\$"}

# Combinations previously reported (canonical lowercase names), by interaction
# class, in Kang et al. 2013 and Azam & Vazquez 2021. A row in our tables is
# flagged new (*) if its agent set is not among these for the same class.
_PREV_SYN = {frozenset(s) for s in [
    # Kang 2013 (Table 1)
    ("docetaxel", "doxorubicin"), ("oxaliplatin", "fluorouracil"),
    ("irinotecan", "etoposide"), ("doxorubicin", "ifosfamide"),
    ("bortezomib", "thalidomide"), ("capecitabine", "irinotecan"),
    ("s-1", "irinotecan"), ("oxaliplatin", "doxorubicin"),
    ("oxaliplatin", "irinotecan"), ("capecitabine", "radiation therapy"),
    ("rituximab", "interferon alfa"), ("oxaliplatin", "capecitabine"),
    ("fluorouracil", "irinotecan"), ("capecitabine", "interferon alfa"),
    ("fludarabine", "thalidomide"),
    # Azam 2021 (Table 2)
    ("doxorubicin", "carboplatin"), ("carboplatin", "nab-paclitaxel"),
    ("rituximab", "ibrutinib"), ("s-1", "nab-paclitaxel"),
]}
_PREV_ANT = {frozenset(s) for s in [
    # Kang 2013 (Table 2)
    ("docetaxel", "topotecan"), ("bortezomib", "rituximab"),
    ("temozolomide", "interferon alfa"), ("capecitabine", "bortezomib"),
    ("fludarabine", "alemtuzumab"), ("bevacizumab", "temozolomide"),
    ("capecitabine", "trimetrexate"), ("docetaxel", "irinotecan"),
    ("bortezomib", "temsirolimus"), ("temozolomide", "aldesleukin"),
    ("docetaxel", "gefitinib"), ("docetaxel", "fluorouracil"),
    ("rituximab", "temsirolimus"), ("temozolomide", "radiation therapy"),
    ("fludarabine", "interferon alfa"), ("g-csf", "rituximab"),
    ("doxorubicin", "bevacizumab"), ("docetaxel", "imatinib"),
    ("docetaxel", "capecitabine"), ("vinorelbine", "mitoxantrone"),
    # Azam 2021 (Table 3)
    ("afatinib", "bevacizumab"), ("carboplatin", "gemcitabine"),
    ("ibrutinib", "durvalumab"), ("erlotinib", "bevacizumab"),
    ("erlotinib", "gemcitabine"), ("nab-paclitaxel", "gemcitabine"),
    ("gemcitabine", "paclitaxel"), ("trastuzumab", "neratinib"),
    ("irinotecan", "cetuximab"), ("folfoxiri", "cetuximab"),
]}


def esc(s: str) -> str:
    return "".join(_ESC.get(c, c) for c in (s or ""))


def fmt_p(p) -> str:
    if p is None:
        return "--"
    return "$<0.001$" if p < 1e-3 else f"{p:.3f}"


def rows_for(conn, interaction):
    q = conn.execute(
        "SELECT b.orr_expected e, b.orr_observed o, b.p_adjusted p, t.tumor_type tum, "
        "  (SELECT group_concat(ag.name, '|') FROM regimen_component rc "
        "     JOIN agent ag ON ag.agent_id = rc.agent_id "
        "   WHERE rc.arm_id = b.arm_id AND (ag.drug_class IS NULL "
        "     OR ag.drug_class NOT IN ('radiation','surgery','steroid'))) AS combo "
        "FROM bliss_prediction b "
        "JOIN arm a ON a.arm_id = b.arm_id "
        "JOIN trial t ON t.trial_id = a.trial_id "
        "WHERE b.interaction = ? "
        "ORDER BY t.tumor_type, b.p_adjusted, b.orr_observed DESC",
        (interaction,),
    ).fetchall()
    prev = _PREV_SYN if interaction == "synergy" else _PREV_ANT
    seen, out, n_new = set(), [], 0
    for e, o, p, tum, combo in q:
        parts = [x for x in (combo or "").split("|") if x]
        agents = " + ".join(sorted(parts))
        key = (agents, tum, round(e, 3), round(o, 3))
        if key in seen:
            continue          # collapse exact-duplicate display rows
        seen.add(key)
        is_new = frozenset(x.lower() for x in parts) not in prev
        n_new += is_new
        disp = esc(agents) + ("$^{*}$" if is_new else "")
        out.append((disp, esc(tum), round(100 * e), round(100 * o), fmt_p(p)))
    return out, n_new


def longtable(rows, label, caption):
    head = (
        "\\begin{footnotesize}\n"
        f"\\begin{{longtable}}{{p{{6.2cm}}p{{3.0cm}}rrr}}\n"
        f"\\caption{{{caption}}}\\label{{{label}}}\\\\\n"
        "\\toprule\nCombination & Tumour & Exp. & Obs. & Adj. $p$ \\\\\n\\midrule\n"
        "\\endfirsthead\n"
        "\\multicolumn{5}{l}{\\footnotesize\\itshape continued from previous page}\\\\\n"
        "\\toprule\nCombination & Tumour & Exp. & Obs. & Adj. $p$ \\\\\n\\midrule\n"
        "\\endhead\n"
        "\\midrule\\multicolumn{5}{r}{\\footnotesize\\itshape continued on next page}\\\\\n"
        "\\endfoot\n\\bottomrule\n\\endlastfoot\n"
    )
    body = "".join(
        f"{a} & {t} & {e}\\% & {o}\\% & {p} \\\\\n" for a, t, e, o, p in rows)
    return head + body + "\\end{longtable}\n\\end{footnotesize}\n"


_NOTE = ("Combinations marked $^{*}$ were not reported in this interaction class "
         "by Kang et al.\\ (2013) or Azam \\& Vazquez (2021).")


def main():
    conn = sqlite3.connect(DB)
    syn, syn_new = rows_for(conn, "synergy")
    ant, ant_new = rows_for(conn, "antagonism")
    conn.close()
    text = (
        "% Auto-generated by make_supp.py -- do not edit by hand.\n"
        + longtable(syn, "tab:S1",
                    f"All synergistic combinations ($n={len(syn)}$): observed ORR "
                    "significantly above the Bliss-independence expectation "
                    f"(Bonferroni-adjusted). {_NOTE} Exp., expected ORR; Obs., observed ORR.")
        + "\n\\clearpage\n"
        + longtable(ant, "tab:S2",
                    f"All antagonistic combinations ($n={len(ant)}$): observed ORR "
                    "significantly below the Bliss-independence expectation "
                    f"(Bonferroni-adjusted). {_NOTE} Exp., expected ORR; Obs., observed ORR.")
    )
    OUT.write_text(text)
    print(f"wrote {OUT.name}: {len(syn)} synergistic ({syn_new} new), "
          f"{len(ant)} antagonistic ({ant_new} new) rows")


if __name__ == "__main__":
    main()
