#!/usr/bin/env python3
"""Generate supplementary_tables.xlsx: every synergistic (Table S1) and
antagonistic (Table S2) combination, read from the analysis database. Reproducible:
rerun after the pipeline to refresh the supplement.

    python make_supp.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

DB = Path(__file__).resolve().parent.parent / "data" / "processed" / "phase2.db"
OUT = Path(__file__).resolve().parent / "supplementary_tables.xlsx"

# Combinations previously reported (canonical lowercase names), by interaction
# class, in Kang et al. 2013 and Azam & Vazquez 2021. A row is flagged "New" if
# its agent set is not among these for the same class.
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

HEADER = ["Combination", "Tumour", "Expected ORR (%)", "Observed ORR (%)",
          "Adjusted p-value", "New"]
_NOTE = ('"New" = combination not reported in this interaction class by '
         "Kang et al. (2013) or Azam & Vazquez (2021).")


def fmt_p(p) -> str:
    if p is None:
        return "n/a"
    return "<0.001" if p < 1e-3 else f"{p:.3f}"


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
        tumour = (tum or "").replace("_", " ")
        key = (agents, tumour, round(e, 3), round(o, 3))
        if key in seen:
            continue          # collapse exact-duplicate display rows
        seen.add(key)
        is_new = frozenset(x.lower() for x in parts) not in prev
        n_new += is_new
        out.append([agents, tumour, round(100 * e), round(100 * o),
                    fmt_p(p), "Yes" if is_new else "No"])
    return out, n_new


def write_sheet(ws, title, rows):
    ws.title = title
    ws.append(HEADER)
    for r in rows:
        ws.append(r)
    for cell in ws[1]:                       # bold header
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(HEADER))}{len(rows) + 1}"
    for col, w in zip("ABCDEF", (34, 22, 15, 15, 14, 6)):
        ws.column_dimensions[col].width = w
    for c in ("C", "D", "E", "F"):           # centre the numeric/flag columns
        for cell in ws[c]:
            cell.alignment = Alignment(horizontal="center")
    ws.append([])
    ws.append([_NOTE])


def main():
    conn = sqlite3.connect(DB)
    syn, syn_new = rows_for(conn, "synergy")
    ant, ant_new = rows_for(conn, "antagonism")
    conn.close()

    wb = Workbook()
    write_sheet(wb.active, "Table S1 Synergistic", syn)
    write_sheet(wb.create_sheet(), "Table S2 Antagonistic", ant)
    wb.save(OUT)
    print(f"wrote {OUT.name}: Table S1 {len(syn)} synergistic ({syn_new} new), "
          f"Table S2 {len(ant)} antagonistic ({ant_new} new)")


if __name__ == "__main__":
    main()
