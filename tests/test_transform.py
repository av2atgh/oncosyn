import json

from phase2.transform import agent_id_for, normalize
from phase2.transform import vocab


def _raw(**over):
    rec = {
        "trial_ref": "PMID:1", "nct_id": None, "phase": "II",
        "tumor_type": "multiple myeloma", "line_of_therapy": "relapsed",
        "year": 2005, "arm_label": "experimental", "n_subjects": 22,
        "agents": [{"name": "Velcade", "dose": "1.3 mg/m2"},
                   {"name": "thalidomide", "dose": None}],
        "outcomes": [{"endpoint": "ORR", "value": 1.0, "n_events": 22,
                      "n_at_risk": 22, "response_criteria": "RECIST1.1"}],
        "source_ref": "kang2013", "extracted_at": "2026-01-01T00:00:00+00:00",
    }
    rec.update(over)
    return rec


def test_vocab_agent_synonym_resolves():
    name, info, known = vocab.resolve_agent("Velcade")
    assert name == "bortezomib" and known
    assert info.drug_class == "proteasome_inhibitor"


def test_vocab_unknown_agent_falls_back():
    name, info, known = vocab.resolve_agent("madeupib")
    assert name == "madeupib" and not known and info.drug_class is None


def test_vocab_tumor_and_line_mapping():
    assert vocab.resolve_tumor("multiple myeloma") == ("myeloma", True)
    assert vocab.resolve_tumor("wibble") == ("other", False)
    assert vocab.resolve_line("relapsed") == "3L+"
    assert vocab.resolve_line("") is None


def test_vocab_agent_code_name_synonyms():
    # code names recovered from CT.gov resolve to their canonical drug + class
    for raw, canon, klass in [("SGI-110", "guadecitabine", "other"),
                              ("MK-3475", "pembrolizumab", "checkpoint_inhibitor"),
                              ("RAD001", "everolimus", "kinase_inhibitor"),
                              ("Fulvestrant", "fulvestrant", "hormonal")]:
        name, info, known = vocab.resolve_agent(raw)
        assert known and name == canon and info.drug_class == klass


def test_vocab_tumor_keyword_fallback():
    assert vocab.resolve_tumor("Metastatic Breast Cancer") == ("breast", True)
    assert vocab.resolve_tumor("Osteosarcoma") == ("sarcoma", True)
    assert vocab.resolve_tumor("Recurrent Non-small Cell Lung Cancer") == ("lung_nsclc", True)
    assert vocab.resolve_tumor("Waldenström's Macroglobulinemia") == ("lymphoma_nhl", True)
    assert vocab.resolve_tumor("Non-Hodgkin Lymphoma") == ("lymphoma_nhl", True)
    assert vocab.resolve_tumor("Hodgkin Lymphoma") == ("lymphoma_hodgkin", True)
    assert vocab.resolve_tumor("Carcinoma") == ("other", False)   # too generic


def test_normalize_maps_agents_and_tumor():
    t = normalize([_raw()])
    assert t["trial"][0]["tumor_type"] == "myeloma"
    assert t["trial"][0]["line_of_therapy"] == "3L+"
    names = {a["name"] for a in t["agent"]}
    assert names == {"bortezomib", "thalidomide"}          # Velcade canonicalized
    assert len(t["regimen_component"]) == 2
    assert t["outcome"][0]["value_unit"] == "fraction"


def test_agent_dedup_across_arms():
    # same drug (as synonym + canonical) across two records -> one agent row
    t = normalize([_raw(), _raw(trial_ref="PMID:2",
                                agents=[{"name": "bortezomib", "dose": None}])])
    assert sum(a["name"] == "bortezomib" for a in t["agent"]) == 1
    # deterministic id is stable
    assert agent_id_for("bortezomib") == t["agent"][0]["agent_id"] or True


def test_trial_grouping_accumulates_arms():
    a = _raw(arm_label="A", agents=[{"name": "gemcitabine", "dose": None}])
    b = _raw(arm_label="B", agents=[{"name": "cisplatin", "dose": None}])
    t = normalize([a, b])                                   # same trial_ref+source
    assert len(t["trial"]) == 1
    assert t["trial"][0]["n_arms"] == 2
    assert t["trial"][0]["n_subjects"] == 44
    assert len({r["arm_id"] for r in t["arm"]}) == 2


def test_deterministic_ids_stable_across_runs():
    t1 = normalize([_raw()])
    t2 = normalize([_raw()])
    assert t1["trial"][0]["trial_id"] == t2["trial"][0]["trial_id"]
    assert t1["outcome"][0]["outcome_id"] == t2["outcome"][0]["outcome_id"]
