"""Controlled-vocabulary resolution for stage 2.

Loads the version-controlled reference dictionaries under ``reference/`` and
provides canonicalization for agents, tumor types, and line of therapy. Unknown
values fall back conservatively (agent -> its own normalized name with unknown
class; tumor -> 'other'; line -> None) and are counted so transform can report
how much of the input needed a fallback.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache

from .. import config


@dataclass
class AgentInfo:
    name: str                      # canonical name
    drug_class: str | None = None
    target: str | None = None
    synonyms: list[str] = field(default_factory=list)


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


@lru_cache(maxsize=1)
def _agents() -> tuple[dict[str, AgentInfo], dict[str, str]]:
    """Return (canonical_name -> AgentInfo, alias_norm -> canonical_name)."""
    path = config.ROOT / "reference" / "agents.csv"
    canon: dict[str, AgentInfo] = {}
    alias: dict[str, str] = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            name = row["name"].strip()
            syns = [s.strip() for s in (row.get("synonyms") or "").split("|") if s.strip()]
            canon[name] = AgentInfo(
                name=name,
                drug_class=(row.get("drug_class") or "").strip() or None,
                target=(row.get("target") or "").strip() or None,
                synonyms=syns,
            )
            alias[_norm(name)] = name
            for s in syns:
                alias[_norm(s)] = name
    return canon, alias


@lru_cache(maxsize=1)
def _tumors() -> tuple[dict[str, str], set[str]]:
    """Return (alias_norm -> canonical, set of canonical values)."""
    path = config.ROOT / "reference" / "tumor_types.csv"
    alias: dict[str, str] = {}
    canon: set[str] = set()
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            c = row["tumor_type"].strip()
            alias[_norm(row["alias"])] = c
            canon.add(c)
    return alias, canon


# Ordered keyword -> canonical fallback for free-text tumor strings (checked
# after exact alias). Specific phrases must precede the general ones they contain.
_TUMOR_KEYWORDS: list[tuple[str, str]] = [
    ("non-small cell lung", "lung_nsclc"), ("non small cell lung", "lung_nsclc"),
    ("nsclc", "lung_nsclc"), ("small cell lung", "lung_sclc"), ("sclc", "lung_sclc"),
    ("lung", "lung_nsclc"),
    ("breast", "breast"),
    ("colorectal", "colorectal"), ("colon", "colorectal"), ("rectal", "colorectal"),
    ("gastrointestinal stromal", "sarcoma"), ("gist", "sarcoma"),
    ("gastric", "gastric"), ("stomach", "gastric"),
    ("hepatocellular", "hepatocellular"),
    ("pancrea", "pancreatic"),
    ("ovar", "ovarian"), ("fallopian", "ovarian"), ("peritoneal", "ovarian"),
    ("renal", "renal"),
    ("prostate", "prostate"),
    ("urothelial", "bladder"), ("transitional cell", "bladder"), ("bladder", "bladder"),
    ("melanoma", "melanoma"),
    ("glioblastoma", "glioma"), ("glioma", "glioma"),
    ("myeloma", "myeloma"),
    ("non-hodgkin", "lymphoma_nhl"), ("hodgkin", "lymphoma_hodgkin"),
    ("waldenstrom", "lymphoma_nhl"), ("waldenström", "lymphoma_nhl"),
    ("macroglobulinemia", "lymphoma_nhl"), ("mycosis fungoides", "lymphoma_nhl"),
    ("sezary", "lymphoma_nhl"), ("lymphoma", "lymphoma_nhl"),
    ("chronic lymphocytic", "leukemia_cll"), ("cll", "leukemia_cll"),
    ("acute myeloid", "leukemia_aml"), ("aml", "leukemia_aml"),
    ("acute lymphoblastic", "leukemia_all"),
    ("chronic myeloid", "leukemia_cml"), ("cml", "leukemia_cml"),
    ("head and neck", "head_neck"), ("salivary", "head_neck"),
    ("osteosarcoma", "sarcoma"), ("sarcoma", "sarcoma"),
    ("esophag", "esophageal"), ("oesophag", "esophageal"),
    ("cervical", "cervical"), ("endometrial", "endometrial"),
    ("thyroid", "thyroid"), ("neuroendocrine", "neuroendocrine"),
]

_LINE_MAP = {
    "1l": "1L", "first line": "1L", "first-line": "1L", "frontline": "1L",
    "front-line": "1L", "1st line": "1L", "untreated": "1L",
    "2l": "2L", "second line": "2L", "second-line": "2L", "2nd line": "2L",
    "3l+": "3L+", "3l": "3L+", "third line": "3L+", "third-line": "3L+",
    "relapsed": "3L+", "refractory": "3L+", "relapsed/refractory": "3L+",
    "adjuvant": "adjuvant", "neoadjuvant": "neoadjuvant", "mixed": "mixed",
}


def resolve_agent(raw_name: str) -> tuple[str, AgentInfo, bool]:
    """Map a raw agent name to (canonical_name, AgentInfo, is_known).

    Unknown agents become their own canonical (title-normalized) with no class.
    """
    canon, alias = _agents()
    key = _norm(raw_name)
    if key in alias:
        name = alias[key]
        return name, canon[name], True
    fallback = raw_name.strip().lower()
    return fallback, AgentInfo(name=fallback), False


def resolve_tumor(raw: str) -> tuple[str, bool]:
    """Map free-text tumor to a controlled value; ('other', False) if unknown.

    Tries exact alias, then exact canonical, then an ordered keyword-substring
    fallback (handles the free-text variants from ClinicalTrials.gov).
    """
    alias, canon = _tumors()
    key = _norm(raw)
    if key in alias:
        return alias[key], True
    if key in {_norm(c) for c in canon}:
        return next(c for c in canon if _norm(c) == key), True
    for kw, canonical in _TUMOR_KEYWORDS:
        if kw in key:
            return canonical, True
    return "other", False


def resolve_line(raw: str | None) -> str | None:
    """Normalize line of therapy to the schema enum, or None if unknown/blank."""
    if not raw:
        return None
    return _LINE_MAP.get(_norm(raw))
