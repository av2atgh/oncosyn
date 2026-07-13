"""ClinicalTrials.gov API v2 extractor for the update / recovery cohorts.

Two layers, so parsing is testable without network:
  * parse_study(study) -> raw arm envelopes (pure; unit-tested against fixtures)
  * fetch_studies(...) -> paginates the live API (http_get injectable)

Emits the same envelope shape as the legacy loader (trial_ref, nct_id, phase,
tumor_type, line_of_therapy, year, arm_label, n_subjects, agents[], outcomes[]),
so transform/load/analyze consume it unchanged.

ORR is read from results outcome measures, handling both encodings:
  * COUNT_OF_PARTICIPANTS -> fraction = responders / group denominator
  * NUMBER as a percentage -> fraction = value / 100, denominator from denoms
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .. import config

API = "https://clinicaltrials.gov/api/v2/studies"
_PHASE_MAP = {
    frozenset({"PHASE2"}): "II",
    frozenset({"PHASE3"}): "III",
    frozenset({"PHASE2", "PHASE3"}): "II/III",
}
_DRUG_TYPES = {"DRUG", "BIOLOGICAL", "RADIATION", "COMBINATION_PRODUCT"}


# --- pure parsing ---------------------------------------------------------

def _phase(design: dict) -> str | None:
    phases = design.get("phases") or []
    return _PHASE_MAP.get(frozenset(phases))


def _year(status: dict) -> int | None:
    for key in ("completionDateStruct", "primaryCompletionDateStruct"):
        date = (status.get(key) or {}).get("date")
        if date:
            m = re.match(r"(\d{4})", date)
            if m:
                return int(m.group(1))
    return None


# Line-of-therapy cues, ordered by precedence (explicit line words win over
# naive/relapsed hints). Scanned over title + eligibility, EXCEPT adjuvant/
# neoadjuvant which are title-only ("prior adjuvant allowed" is ubiquitous in
# metastatic-trial eligibility and would mis-fire).
_NEOADJ_RE = re.compile(r"neo-?adjuvant|pre-?operative", re.I)
_ADJ_RE = re.compile(r"\badjuvant\b|post-?operative", re.I)
_LINE_TEXT_PATTERNS = [
    (re.compile(r"first[\s-]?line|1st[\s-]?line|front[\s-]?line", re.I), "1L"),
    (re.compile(r"second[\s-]?line|2nd[\s-]?line", re.I), "2L"),
    (re.compile(r"third[\s-]?line|3rd[\s-]?line", re.I), "3L+"),
    (re.compile(r"relapsed|refractory|\br/r\b|heavily pre[\s-]?treated", re.I), "3L+"),
    (re.compile(r"previously untreated|treatment[\s-]?na[iï]ve|chemo(?:therapy)?[\s-]?"
                r"na[iï]ve|newly diagnosed|no prior (?:chemo|systemic|anti-?cancer|"
                r"therap|treatment)", re.I), "1L"),
    (re.compile(r"at least\s+(?:two|three|2|3)\s+(?:prior|previous)|(?:two|three|2|3)"
                r"\s+or\s+more\s+(?:prior|previous)|multiple prior", re.I), "3L+"),
    (re.compile(r"\bone prior\b|\b1 prior\b|after (?:one|1) prior", re.I), "2L"),
]


def _line_of_therapy(ps: dict) -> str | None:
    """Infer line of therapy from title + eligibility (heuristic; None if unclear)."""
    idm = ps.get("identificationModule", {})
    title = f"{idm.get('briefTitle', '')} {idm.get('officialTitle', '')}"
    if _NEOADJ_RE.search(title):
        return "neoadjuvant"
    if _ADJ_RE.search(title):
        return "adjuvant"
    text = title + "\n" + (ps.get("eligibilityModule", {}).get("eligibilityCriteria", "") or "")
    for pat, line in _LINE_TEXT_PATTERNS:
        if pat.search(text):
            return line
    return None


def _is_orr_title(title: str) -> bool:
    t = (title or "").lower()
    if "response rate" in t and any(w in t for w in ("objective", "overall", "best")):
        return True
    return bool(re.search(r"\borr\b", t))


# --- agent-name normalization --------------------------------------------
# Split combination/regimen strings, strip salt/formulation/dose decorations,
# and drop non-drug intervention labels, so raw CT.gov names resolve in vocab.

_SEP_RE = re.compile(
    r"\s*(?:[+/&,]|\band\b|\bplus\b|\bwith\b|\bmatching\b|\bto match\b)\s*", re.I)
_DOSE_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mg/m2|mg/kg|mcg|µg|mg|g|ml|units?|iu|%)\b", re.I)
_SALT_RE = re.compile(
    r"[\s-](?:hydrochloride|hcl|mesylate|maleate|malate|ditosylate|tosylate|"
    r"dihydrochloride|disodium|sodium|sulfate|sulphate|phosphate|acetate|"
    r"citrate|besylate|fumarate|succinate)\b", re.I)
_FORM_RE = re.compile(
    r"\b(?:for injectable suspension|injectable|injections?|infusions?|"
    r"suspension|tablets?|capsules?|solution|intravenous)\b", re.I)
_DESC_RE = re.compile(
    r"\b(?:combined|combination|chemotherapy|chemo|regimen|monotherapy)\b", re.I)
_NONDRUG_SUBSTR = ("biomarker", "pharmacogenomic", "pharmacolog", "analysis",
                   " study", "studies", "supportive care", "dendritic cell",
                   "skin treatment", "vitamin", "herbal", "hyperthermia")
_NONDRUG_EXACT = {"placebo", "treatment", "treatment of choice", "observation",
                  "doublet", "triplet", "regimen", "therapy", "chemotherapy",
                  "standard of care", "best supportive care", "no treatment",
                  "control", "immunotherapy"}


def _candidate_parts(raw: str) -> list[str]:
    """Split one raw name into candidate agent tokens (handles parentheticals)."""
    raw = _DOSE_RE.sub(" ", raw)                        # before "/" split, so mg/m2 survives
    inners = re.findall(r"\(([^)]*)\)", raw)
    pieces = [re.sub(r"\([^)]*\)", " ", raw)]           # outside the parentheses
    for inner in inners:
        if re.search(r"\bor\b", inner, re.I):
            continue                                    # "a, b, or c" = choice, ambiguous
        pieces.append(inner)
    parts = []
    for p in pieces:
        parts.extend(_SEP_RE.split(p))
    return parts


def _clean_token(t: str) -> str:
    t = _DOSE_RE.sub(" ", t)
    t = _SALT_RE.sub(" ", t)
    t = _FORM_RE.sub(" ", t)
    t = _DESC_RE.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip(" -/,")


_ARM_PLACEHOLDER = re.compile(r"arm\s+[a-z0-9]+$", re.I)


def _is_nondrug(name: str) -> bool:
    lc = name.lower()
    return (len(lc) < 2 or lc in _NONDRUG_EXACT
            or bool(_ARM_PLACEHOLDER.fullmatch(lc))
            or any(s in lc for s in _NONDRUG_SUBSTR))


def _default_is_known(name: str) -> bool:
    from ..transform import vocab      # lazy: keeps extract importable on its own
    return vocab.resolve_agent(name)[2]


def _maybe_split_hyphen(name: str, is_known) -> list[str]:
    """Split "Etoposide-Cisplatin" only when it isn't itself a known drug and
    every hyphen-part is known — so "nab-paclitaxel"/"5-fluorouracil" stay whole."""
    if "-" not in name or is_known(name):
        return [name]
    parts = [p.strip() for p in name.split("-") if p.strip()]
    if len(parts) >= 2 and all(is_known(p) for p in parts):
        return parts
    return [name]


def normalize_agent_names(raw_names: list[str], is_known=None) -> list[str]:
    """Normalize + split raw intervention names into clean single-agent names.

    is_known(name) -> bool decides whether a token resolves to a known drug;
    it gates hyphen-splitting. Defaults to a vocab lookup.
    """
    is_known = is_known or _default_is_known
    out, seen = [], set()
    for raw in raw_names:
        for part in _candidate_parts(raw or ""):
            name = _clean_token(part)
            if not name or _is_nondrug(name):
                continue
            for tok in _maybe_split_hyphen(name, is_known):
                if tok and not _is_nondrug(tok) and tok.lower() not in seen:
                    seen.add(tok.lower())
                    out.append(tok)
    return out


# --- arm <-> intervention mapping ----------------------------------------
# armGroup.interventionNames look like "Drug: Apatinib"; keep only drug-ish types.
_DRUGISH_PREFIX = {"drug", "biological", "radiation", "combination product"}


def _norm_label(s: str) -> str:
    return " ".join((s or "").lower().split())


def _typed_intervention(raw: str) -> tuple[str, str]:
    typ, sep, rest = (raw or "").partition(":")
    return (typ.strip().lower(), rest.strip()) if sep else ("drug", (raw or "").strip())


def arm_drug_map(arms_module: dict) -> dict[str, list[str]]:
    """{armGroup label -> ordered unique drug names}.

    Built from BOTH directions so a gap in either field is covered:
      * intervention.armGroupLabels (authoritative reverse link, type-tagged)
      * armGroup.interventionNames  (the "Type: Name" forward list)
    Non-drug interventions (procedures, questionnaires, dietary supplements) are
    excluded so an arm's regimen is just its drugs/biologics/radiation.
    """
    labels = [ag.get("label", "") for ag in arms_module.get("armGroups", [])]
    per_arm: dict[str, list[str]] = {lab: [] for lab in labels}
    for iv in arms_module.get("interventions", []):
        if iv.get("type") not in _DRUG_TYPES or not iv.get("name"):
            continue
        for lab in iv.get("armGroupLabels", []):
            per_arm.setdefault(lab, []).append(iv["name"])
    for ag in arms_module.get("armGroups", []):
        lab = ag.get("label", "")
        for entry in ag.get("interventionNames") or []:
            typ, name = _typed_intervention(entry)
            if typ in _DRUGISH_PREFIX and name:
                per_arm[lab].append(name)
    out: dict[str, list[str]] = {}
    for lab, names in per_arm.items():
        seen, uniq = set(), []
        for n in names:
            if n.lower() not in seen:
                seen.add(n.lower())
                uniq.append(n)
        out[lab] = uniq
    return out


def match_group_to_arm(title, idx, group_titles, ordered_labels, per_arm, all_drugs):
    """Resolve an outcome-measure group to its arm's drug list.

    Cascade: single-arm -> exact/normalized label -> substring either direction
    -> positional (only when the measure's groups line up 1:1 with the arms).
    Returns None when nothing matches (caller then parses the group title itself).
    """
    if len(per_arm) <= 1:
        only = next(iter(per_arm.values()), None)
        return only if only else all_drugs
    gt = _norm_label(title)
    norm = {lab: _norm_label(lab) for lab in ordered_labels}
    for lab in ordered_labels:                       # exact / normalized
        if norm[lab] and norm[lab] == gt:
            return per_arm.get(lab, [])
    cands = [lab for lab in ordered_labels           # substring either direction
             if norm[lab] and (norm[lab] in gt or gt in norm[lab])]
    if cands:
        return per_arm.get(max(cands, key=lambda l: len(norm[l])), [])
    if len(group_titles) == len(ordered_labels):     # positional 1:1 fallback
        return per_arm.get(ordered_labels[idx], [])
    return None


def _orr_fraction(measure: dict, group_id: str, denom: int | None):
    """(value_fraction, n_events, n_at_risk) for a group, or None if unusable."""
    val = None
    for cls in measure.get("classes", []):
        for cat in cls.get("categories", []):
            for meas in cat.get("measurements", []):
                if meas.get("groupId") == group_id:
                    try:
                        val = float(meas["value"])
                    except (TypeError, ValueError):
                        continue  # 'NA', '', missing -> not usable
    if val is None:
        return None
    unit = (measure.get("unitOfMeasure") or "").lower()
    ptype = measure.get("paramType", "")
    if ptype == "COUNT_OF_PARTICIPANTS":
        if not denom:
            return None
        events = int(round(val))
        return events / denom, events, denom
    if "percent" in unit or ptype == "NUMBER":
        if not 0 <= val <= 100:
            return None
        frac = val / 100.0
        events = int(round(frac * denom)) if denom else None
        return frac, events, denom
    return None


# median survival is reported in various time units; normalise to months
_TIME_UNITS = [("month", 1.0), ("year", 12.0), ("week", 1 / 4.345), ("day", 1 / 30.4375)]


def _measure_kind(title: str) -> str | None:
    """Classify an outcome-measure title as ORR / OS / PFS (else None)."""
    if _is_orr_title(title):
        return "ORR"
    t = (title or "").lower()
    if "overall survival" in t:
        return "OS"
    if "progression-free survival" in t or "progression free survival" in t:
        return "PFS"
    return None


def _median_months(measure: dict, group_id: str) -> float | None:
    """Median survival for a group, converted to months; None if unusable.

    Gated on a time unit, so survival *rates* (unit 'percentage') are skipped.
    'NA' / not-reached medians are non-numeric and drop out.
    """
    unit = (measure.get("unitOfMeasure") or "").lower()
    factor = next((f for key, f in _TIME_UNITS if key in unit), None)
    if factor is None:
        return None
    for cls in measure.get("classes", []):
        for cat in cls.get("categories", []):
            for meas in cat.get("measurements", []):
                if meas.get("groupId") == group_id:
                    try:
                        months = float(meas["value"]) * factor
                    except (TypeError, ValueError):
                        continue
                    if 0 < months <= 600:          # sanity: <= 50 years
                        return months
    return None


def _read_outcome(measure: dict, kind: str, gid: str, denom: int | None):
    """Build one outcome dict for a group, or (outcome, n_subjects); None if unusable."""
    if kind == "ORR":
        res = _orr_fraction(measure, gid, denom)
        if res is None:
            return None
        frac, events, n = res
        return {"endpoint": "ORR", "value": frac, "n_events": events,
                "n_at_risk": n, "response_criteria": "RECIST1.1"}, n
    med = _median_months(measure, gid)
    if med is None:
        return None
    return {"endpoint": kind, "value": med, "n_events": None,
            "n_at_risk": denom, "response_criteria": None}, denom


def parse_study(study: dict) -> list[dict]:
    """Parse one CT.gov study into raw arm envelopes with ORR / OS / PFS outcomes.

    Emits one envelope per (measure, arm); transform merges them into one arm
    with a long-format list of outcomes. For each endpoint only the first usable
    results measure is taken.
    """
    ps = study.get("protocolSection", {})
    phase = _phase(ps.get("designModule", {}))
    if phase is None:
        return []
    nct = ps.get("identificationModule", {}).get("nctId")
    conditions = ps.get("conditionsModule", {}).get("conditions") or []
    tumor = conditions[0] if conditions else "other"
    year = _year(ps.get("statusModule", {}))
    line = _line_of_therapy(ps)
    arms_module = ps.get("armsInterventionsModule", {})
    per_arm = arm_drug_map(arms_module)
    ordered_labels = [ag.get("label", "") for ag in arms_module.get("armGroups", [])]
    all_drugs = [iv["name"] for iv in arms_module.get("interventions", [])
                 if iv.get("type") in _DRUG_TYPES and iv.get("name")]

    measures = (study.get("resultsSection", {})
                .get("outcomeMeasuresModule", {}).get("outcomeMeasures", []))
    records = []
    done: set[str] = set()          # first usable measure per endpoint
    for m in measures:
        kind = _measure_kind(m.get("title", ""))
        if kind is None or kind in done:
            continue
        denoms = {c["groupId"]: int(c["value"])
                  for d in m.get("denoms", []) for c in d.get("counts", [])
                  if c.get("value", "").isdigit()}
        group_titles = [g.get("title", "") for g in m.get("groups", [])]
        produced = False
        for idx, g in enumerate(m.get("groups", [])):
            gid, label = g.get("id"), g.get("title", "")
            built = _read_outcome(m, kind, gid, denoms.get(gid))
            if built is None:
                continue
            outcome, n = built
            drugs = match_group_to_arm(label, idx, group_titles, ordered_labels,
                                       per_arm, all_drugs)
            # no arm matched -> parse the outcome group's own title for a regimen
            agents = normalize_agent_names(drugs if drugs is not None else [label])
            if not agents:
                continue
            records.append({
                "trial_ref": nct, "nct_id": nct, "phase": phase,
                "tumor_type": tumor, "line_of_therapy": line, "year": year,
                "arm_label": label, "n_subjects": n,
                "agents": [{"name": a, "dose": None} for a in agents],
                "outcomes": [outcome],
            })
            produced = True
        if produced:
            done.add(kind)
    return records


# --- live fetch -----------------------------------------------------------

def _default_get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "phase2-extractor/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_studies(params: dict, max_pages: int = 20, page_size: int = 100, http_get=_default_get):
    """Yield studies across pages of the API (stops at max_pages)."""
    token = None
    for _ in range(max_pages):
        q = dict(params, pageSize=page_size)
        if token:
            q["pageToken"] = token
        data = http_get(f"{API}?{urllib.parse.urlencode(q)}")
        yield from data.get("studies", [])
        token = data.get("nextPageToken")
        if not token:
            return


def build_params(src: dict) -> dict:
    """Build API query params from a config `sources` entry."""
    q = src.get("query", {})
    phases = "PHASE2 OR PHASE3"
    adv = [f"AREA[Phase]({phases})"]
    if q.get("min_completion_year"):
        adv.append(f"AREA[CompletionDate]RANGE[{q['min_completion_year']}-01-01,MAX]")
    if q.get("max_completion_year"):
        adv.append(f"AREA[CompletionDate]RANGE[MIN,{q['max_completion_year']}-12-31]")
    return {
        "query.cond": q.get("conditions", "cancer"),
        "aggFilters": "results:with",
        "filter.advanced": " AND ".join(adv),
    }


def load_source(source_ref: str, cfg: dict | None = None, **fetch_kwargs) -> Path:
    """Query the API for a config source, parse, and write data/raw/<ref>.jsonl."""
    cfg = cfg or config.load()
    src = next(s for s in cfg["sources"] if s["source_ref"] == source_ref)
    raw_dir = config.ROOT / cfg["paths"]["raw"]
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_path = raw_dir / f"{source_ref}.jsonl"
    stamped_at = datetime.now(timezone.utc).isoformat()

    n_studies = n_records = 0
    with open(out_path, "w") as out:
        for study in fetch_studies(build_params(src), **fetch_kwargs):
            n_studies += 1
            for rec in parse_study(study):
                rec.update(source_ref=source_ref, extracted_at=stamped_at)
                out.write(json.dumps(rec) + "\n")
                n_records += 1
    print(f"[extract.clinicaltrials] {source_ref}: {n_studies} studies -> "
          f"{n_records} arm-records (ORR/OS/PFS) -> {out_path.name}")
    return out_path
