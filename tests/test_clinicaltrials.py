import json
import os
import urllib.parse
from pathlib import Path

import pytest

from phase2 import config
from phase2.extract import clinicaltrials as ct
from phase2.extract import recover

FIXTURE = Path(__file__).parent / "fixtures" / "ctgov_study.json"
live_only = pytest.mark.skipif(
    os.environ.get("PHASE2_NETWORK_TESTS") != "1",
    reason="set PHASE2_NETWORK_TESTS=1 to run live CT.gov tests")


# --- synthetic studies ----------------------------------------------------

def _pct_study():
    return {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT99999999"},
            "statusModule": {"completionDateStruct": {"date": "2018-06-30"}},
            "conditionsModule": {"conditions": ["Non-small cell lung cancer"]},
            "designModule": {"phases": ["PHASE2"], "enrollmentInfo": {"count": 50}},
            "armsInterventionsModule": {
                "interventions": [{"type": "DRUG", "name": "Nivolumab"}],
                "armGroups": [{"label": "Arm A", "interventionNames": ["Drug: Nivolumab"]}],
            },
        },
        "resultsSection": {"outcomeMeasuresModule": {"outcomeMeasures": [{
            "type": "SECONDARY", "title": "Overall Response Rate (ORR)",
            "paramType": "NUMBER", "unitOfMeasure": "percentage of participants",
            "groups": [{"id": "OG1", "title": "Arm A"}],
            "denoms": [{"units": "Participants", "counts": [{"groupId": "OG1", "value": "50"}]}],
            "classes": [{"categories": [{"measurements": [{"groupId": "OG1", "value": "40"}]}]}],
        }]}},
    }


def _two_arm_study():
    s = _pct_study()
    ai = s["protocolSection"]["armsInterventionsModule"]
    ai["interventions"] = [{"type": "DRUG", "name": "DrugX"}, {"type": "DRUG", "name": "DrugY"}]
    ai["armGroups"] = [
        {"label": "Mono", "interventionNames": ["Drug: DrugX"]},
        {"label": "Combo", "interventionNames": ["Drug: DrugX", "Drug: DrugY"]}]
    m = s["resultsSection"]["outcomeMeasuresModule"]["outcomeMeasures"][0]
    m["groups"] = [{"id": "OG1", "title": "Mono"}, {"id": "OG2", "title": "Combo"}]
    m["denoms"] = [{"counts": [{"groupId": "OG1", "value": "40"}, {"groupId": "OG2", "value": "60"}]}]
    m["classes"] = [{"categories": [{"measurements": [
        {"groupId": "OG1", "value": "25"}, {"groupId": "OG2", "value": "50"}]}]}]
    return s


# --- parsing --------------------------------------------------------------

def test_parse_real_count_fixture():
    study = json.loads(FIXTURE.read_text())
    recs = ct.parse_study(study)
    by_ep = {r["outcomes"][0]["endpoint"]: r for r in recs}
    assert set(by_ep) == {"ORR", "OS", "PFS"}        # fixture reports all three
    r = by_ep["ORR"]
    assert r["nct_id"] == "NCT02878057" and r["phase"] == "II"
    assert r["tumor_type"] == "Breast Cancer"
    assert [a["name"] for a in r["agents"]] == ["Apatinib"]
    o = r["outcomes"][0]
    assert o["n_events"] == 11 and o["n_at_risk"] == 26
    assert abs(o["value"] - 11 / 26) < 1e-9          # COUNT_OF_PARTICIPANTS
    # median survival captured in months
    assert abs(by_ep["OS"]["outcomes"][0]["value"] - 18.0) < 1e-9
    assert abs(by_ep["PFS"]["outcomes"][0]["value"] - 4.9) < 1e-9
    assert by_ep["OS"]["outcomes"][0]["response_criteria"] is None


def test_measure_kind_classification():
    assert ct._measure_kind("Objective Response Rate") == "ORR"
    assert ct._measure_kind("Overall Survival") == "OS"
    assert ct._measure_kind("Progression-free Survival") == "PFS"
    assert ct._measure_kind("Progression Free Survival") == "PFS"
    assert ct._measure_kind("Disease Control Rate") is None
    assert ct._measure_kind("Duration of Response") is None


def test_median_months_units_and_na():
    def meas(unit, val):
        return {"unitOfMeasure": unit,
                "classes": [{"categories": [{"measurements": [{"groupId": "g", "value": val}]}]}]}
    assert abs(ct._median_months(meas("Months", "12"), "g") - 12) < 1e-9
    assert abs(ct._median_months(meas("Years", "2"), "g") - 24) < 1e-9
    assert ct._median_months(meas("percentage of participants", "40"), "g") is None  # rate, not time
    assert ct._median_months(meas("Months", "NA"), "g") is None                       # not reached
    assert ct._median_months(meas("Months", "999"), "g") is None                      # >50 yr, implausible


def test_parse_percentage_encoding():
    r = ct.parse_study(_pct_study())[0]
    o = r["outcomes"][0]
    assert abs(o["value"] - 0.40) < 1e-9             # 40% -> fraction
    assert o["n_events"] == 20 and o["n_at_risk"] == 50
    assert r["tumor_type"] == "Non-small cell lung cancer" and r["year"] == 2018


def test_parse_multi_arm_maps_agents_per_arm():
    recs = {r["arm_label"]: r for r in ct.parse_study(_two_arm_study())}
    assert set(recs) == {"Mono", "Combo"}
    assert [a["name"] for a in recs["Mono"]["agents"]] == ["DrugX"]
    assert [a["name"] for a in recs["Combo"]["agents"]] == ["DrugX", "DrugY"]
    assert abs(recs["Combo"]["outcomes"][0]["value"] - 0.50) < 1e-9


def _two_arm_diff_study():
    """Arm I = anastrozole; Arm II = anastrozole + fulvestrant (via armGroupLabels)."""
    return {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT00075764"},
            "statusModule": {"completionDateStruct": {"date": "2011"}},
            "conditionsModule": {"conditions": ["Breast Cancer"]},
            "designModule": {"phases": ["PHASE3"]},
            "armsInterventionsModule": {
                "armGroups": [{"label": "Arm I"}, {"label": "Arm II"}],
                "interventions": [
                    {"type": "DRUG", "name": "anastrozole", "armGroupLabels": ["Arm I", "Arm II"]},
                    {"type": "DRUG", "name": "fulvestrant", "armGroupLabels": ["Arm II"]},
                    {"type": "OTHER", "name": "Questionnaire", "armGroupLabels": ["Arm I", "Arm II"]},
                ]},
        },
        "resultsSection": {"outcomeMeasuresModule": {"outcomeMeasures": [{
            "type": "SECONDARY", "title": "Objective Response Rate",
            "paramType": "COUNT_OF_PARTICIPANTS",
            "groups": [{"id": "OG0", "title": "Arm I"}, {"id": "OG1", "title": "Arm II"}],
            "denoms": [{"counts": [{"groupId": "OG0", "value": "100"},
                                   {"groupId": "OG1", "value": "100"}]}],
            "classes": [{"categories": [{"measurements": [
                {"groupId": "OG0", "value": "20"}, {"groupId": "OG1", "value": "35"}]}]}],
        }]}},
    }


def test_arm_drug_map_from_armgrouplabels_typefiltered():
    m = {"armGroups": [{"label": "A"}, {"label": "B"}],
         "interventions": [
             {"type": "DRUG", "name": "X", "armGroupLabels": ["A", "B"]},
             {"type": "DRUG", "name": "Y", "armGroupLabels": ["B"]},
             {"type": "OTHER", "name": "Questionnaire", "armGroupLabels": ["A", "B"]}]}
    assert ct.arm_drug_map(m) == {"A": ["X"], "B": ["X", "Y"]}   # Questionnaire excluded


def test_arm_drug_map_from_interventionnames_typefiltered():
    m = {"armGroups": [
            {"label": "A", "interventionNames": ["Drug: X", "Other: Quality-of-Life",
                                                 "Procedure: Surgery"]},
            {"label": "B", "interventionNames": ["Radiation: RT", "Biological: Z"]}],
         "interventions": []}
    assert ct.arm_drug_map(m) == {"A": ["X"], "B": ["RT", "Z"]}  # Other/Procedure dropped


def test_match_group_normalized_and_substring():
    per_arm = {"TX05 (trastuzumab)": ["Trastuzumab"], "Herceptin®": ["Trastuzumab"]}
    ordered = list(per_arm)
    titles = ["TX05 (Trastuzumab)", "Herceptin®"]
    # case-only difference -> normalized match
    assert ct.match_group_to_arm(titles[0], 0, titles, ordered, per_arm, []) == ["Trastuzumab"]
    per_arm2 = {"Cohort 1": ["lapatinib"], "Cohort 2": ["paclitaxel"]}
    t2 = ["Cohort 1: Paclitaxel 80/Lapatinib 1000", "Cohort 2: x"]
    # armGroup label is a substring of the verbose outcome title
    assert ct.match_group_to_arm(t2[0], 0, t2, list(per_arm2), per_arm2, []) == ["lapatinib"]


def test_match_group_positional_and_none():
    per_arm = {"1": ["a"], "2": ["b"]}
    ordered = list(per_arm)
    titles = ["G-CSF Arm", "Placebo Arm"]              # labels share nothing with "1"/"2"
    assert ct.match_group_to_arm("Placebo Arm", 1, titles, ordered, per_arm, []) == ["b"]
    # 3 groups vs 2 arms -> positional unsafe -> None (caller parses the title)
    assert ct.match_group_to_arm("X", 0, ["X", "Y", "Z"], ordered, per_arm, []) is None


def test_parse_multi_arm_no_drug_leakage():
    recs = {r["arm_label"]: [a["name"] for a in r["agents"]]
            for r in ct.parse_study(_two_arm_diff_study())}
    assert recs["Arm I"] == ["anastrozole"]            # NOT anastrozole+fulvestrant
    assert recs["Arm II"] == ["anastrozole", "fulvestrant"]


def test_parse_skips_non_phase23():
    s = _pct_study()
    s["protocolSection"]["designModule"]["phases"] = ["PHASE1"]
    assert ct.parse_study(s) == []


def test_normalize_splits_combinations():
    n = ct.normalize_agent_names
    assert n(["Docetaxel + Oxaliplatin + 5-FU"]) == ["Docetaxel", "Oxaliplatin", "5-FU"]
    assert n(["Bevacizumab and Etoposide"]) == ["Bevacizumab", "Etoposide"]
    assert n(["Vinflunine plus Capecitabine"]) == ["Vinflunine", "Capecitabine"]
    assert n(["Irinotecan, oxaliplatin, and cetuximab"]) == ["Irinotecan", "oxaliplatin", "cetuximab"]


def test_normalize_strips_decorations():
    n = ct.normalize_agent_names
    assert n(["Gemcitabine Hydrochloride"]) == ["Gemcitabine"]
    assert n(["Sunitinib-Malate"]) == ["Sunitinib"]
    assert n(["azacitidine for injectable suspension"]) == ["azacitidine"]
    assert n(["Voreloxin Injection"]) == ["Voreloxin"]
    assert n(["ZD4054 10 mg"]) == ["ZD4054"]
    assert n(["Gefitinib 250mg"]) == ["Gefitinib"]
    assert n(["250 mg/m2 aldoxorubicin"]) == ["aldoxorubicin"]


def test_normalize_parentheticals_and_choice():
    n = ct.normalize_agent_names
    assert set(n(["ZD6474 (vandetanib)"])) == {"ZD6474", "vandetanib"}
    assert n(["Doublet (RAD001 and LBH589)"]) == ["RAD001", "LBH589"]
    # "a, b, or c" inside parens is a treatment choice, not a combination -> dropped
    assert n(["Treatment of Choice (topotecan, paclitaxel, or gemcitabine)"]) == []


def test_normalize_drops_nondrug_and_placebo():
    n = ct.normalize_agent_names
    assert n(["laboratory biomarker analysis"]) == []
    assert n(["treatment"]) == []
    assert n(["pharmacogenomic studies"]) == []
    assert n(["Buparlisib matching Placebo"]) == ["Buparlisib"]
    assert n(["Dexamethasone plus Placebo"]) == ["Dexamethasone"]
    assert n(["Placebo to match idelalisib"]) == ["idelalisib"]


def test_normalize_splits_hyphen_when_both_known():
    known = {"etoposide", "cisplatin", "carboplatin", "paclitaxel"}.__contains__
    n = ct.normalize_agent_names
    assert n(["Etoposide-Cisplatin"], is_known=lambda x: known(x.lower())) == ["Etoposide", "Cisplatin"]
    # descriptor words stripped first, then the hyphen combo splits
    assert n(["Etoposide-Cisplatin combined chemotherapy"],
             is_known=lambda x: known(x.lower())) == ["Etoposide", "Cisplatin"]


def test_normalize_hyphen_kept_when_not_both_known():
    known = {"paclitaxel", "cisplatin"}.__contains__
    n = ct.normalize_agent_names
    # 'nab' is not a known drug -> keep "nab-paclitaxel" intact
    assert n(["nab-paclitaxel"], is_known=lambda x: known(x.lower())) == ["nab-paclitaxel"]
    assert n(["Foo-Bar"], is_known=lambda x: known(x.lower())) == ["Foo-Bar"]


def test_normalize_hyphen_never_splits_a_known_whole_name():
    # a hyphenated name that is itself a known drug is never split, even if a part is known too
    known = {"nab-paclitaxel", "paclitaxel"}.__contains__
    assert ct.normalize_agent_names(["nab-paclitaxel"],
                                    is_known=lambda x: known(x.lower())) == ["nab-paclitaxel"]


def test_normalize_hyphen_default_vocab():
    # with the real vocab default, 5-fluorouracil (known synonym) stays whole
    assert ct.normalize_agent_names(["5-fluorouracil"]) == ["5-fluorouracil"]
    # a real hyphen combo of two dictionary drugs splits
    assert ct.normalize_agent_names(["Gemcitabine-Cisplatin"]) == ["Gemcitabine", "Cisplatin"]


def test_normalize_preserves_real_multiword_names():
    n = ct.normalize_agent_names
    assert n(["nab-paclitaxel"]) == ["nab-paclitaxel"]          # hyphen not a separator
    assert n(["brentuximab vedotin"]) == ["brentuximab vedotin"]  # space not a separator
    assert n(["Radiation Therapy"]) == ["Radiation Therapy"]


def test_normalize_then_resolve_reduces_unknowns():
    # end-to-end: decorated/combo names all resolve to known canonicals after normalization
    from phase2.transform import vocab
    raw = ["Docetaxel + Oxaliplatin", "Gemcitabine Hydrochloride", "ZD6474 (vandetanib)"]
    names = ct.normalize_agent_names(raw)
    resolved = [vocab.resolve_agent(a) for a in names]
    assert all(known for _, _, known in resolved)
    assert {c for c, _, _ in resolved} == {"docetaxel", "oxaliplatin", "gemcitabine", "vandetanib"}


def _ps(title="", elig=""):
    return {"identificationModule": {"briefTitle": title},
            "eligibilityModule": {"eligibilityCriteria": elig}}


def test_line_of_therapy_from_title():
    lot = ct._line_of_therapy
    assert lot(_ps(title="A Study of X in First-Line Metastatic NSCLC")) == "1L"
    assert lot(_ps(title="Second-line Y in Advanced Gastric Cancer")) == "2L"
    assert lot(_ps(title="Z in Relapsed/Refractory Multiple Myeloma")) == "3L+"
    assert lot(_ps(title="Adjuvant Chemotherapy After Resection")) == "adjuvant"
    assert lot(_ps(title="Neoadjuvant X Before Surgery")) == "neoadjuvant"


def test_line_of_therapy_from_eligibility():
    lot = ct._line_of_therapy
    assert lot(_ps(elig="Patients must be treatment-naive with no prior systemic therapy")) == "1L"
    assert lot(_ps(elig="Must have relapsed or refractory disease after prior lines")) == "3L+"
    assert lot(_ps(elig="At least two prior lines of therapy required")) == "3L+"


def test_line_of_therapy_adjuvant_in_eligibility_does_not_fire():
    # "prior adjuvant therapy allowed" is common in metastatic 1L trials
    lot = ct._line_of_therapy
    ps = _ps(title="Study of X in Metastatic Breast Cancer",
             elig="Prior adjuvant chemotherapy allowed; no prior therapy for metastatic disease")
    assert lot(ps) == "1L"                     # not "adjuvant"


def test_line_of_therapy_none_when_unclear():
    assert ct._line_of_therapy(_ps(title="A Study of X in Solid Tumors")) is None


def test_parse_sets_line_of_therapy():
    s = _pct_study()
    s["protocolSection"]["identificationModule"]["briefTitle"] = "First-Line Nivolumab in NSCLC"
    assert ct.parse_study(s)[0]["line_of_therapy"] == "1L"


def test_orr_title_matcher():
    assert ct._is_orr_title("Objective Response Rate")
    assert ct._is_orr_title("Overall Response Rate (ORR)")
    assert not ct._is_orr_title("Disease Control Rate")
    assert not ct._is_orr_title("Duration of Response")
    assert not ct._is_orr_title("Overall Survival")


# --- fetch pagination + params -------------------------------------------

def test_fetch_studies_paginates():
    pages = {
        None: {"studies": [{"id": 1}], "nextPageToken": "t1"},
        "t1": {"studies": [{"id": 2}], "nextPageToken": None},
    }

    def fake_get(url):
        tok = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("pageToken", [None])[0]
        return pages[tok]

    got = list(ct.fetch_studies({"query.cond": "x"}, http_get=fake_get))
    assert [s["id"] for s in got] == [1, 2]


def test_build_params_date_range():
    p = ct.build_params({"query": {"conditions": "cancer", "min_completion_year": 2020}})
    assert p["aggFilters"] == "results:with"
    assert "AREA[Phase]" in p["filter.advanced"]
    assert "RANGE[2020-01-01,MAX]" in p["filter.advanced"]


# --- recovery (offline, mocked API) --------------------------------------

def test_recover_offline(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    monkeypatch.setattr(config, "load", lambda: {"paths": {"raw": str(raw)}})
    page = {"studies": [_pct_study(), _two_arm_study(),
                        {"protocolSection": {"designModule": {"phases": ["PHASE1"]}}}],
            "nextPageToken": None}
    stats = recover.recover(max_pages=1, http_get=lambda url: page)
    assert stats["studies_fetched"] == 3
    assert stats["studies_with_orr"] == 2            # phase-1 study yields nothing
    assert stats["arm_records"] == 3                 # 1 + 2 arms
    assert stats["combination_arms"] == 1            # the Combo arm
    assert stats["mean_orr"] is not None
    lines = (raw / "recover_pre2020.jsonl").read_text().strip().splitlines()
    assert len(lines) == 3
    assert json.loads(lines[0])["source_ref"] == "recover_pre2020"


# --- live recovery (network-gated) ---------------------------------------

@live_only
@pytest.mark.network
def test_recover_live_pre2020(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "load", lambda: {"paths": {"raw": str(tmp_path)}})
    stats = recover.recover(max_pages=1, conditions="breast cancer")
    assert stats["studies_fetched"] > 0
    assert stats["studies_with_orr"] > 0             # recovers pre-2020 ORR data
    assert 0.0 <= (stats["mean_orr"] or 0) <= 1.0
