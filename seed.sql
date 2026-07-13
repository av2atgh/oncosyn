-- Phase2 — lookup table seed data (controlled vocabularies)
-- Load after schema.sql:  sqlite3 phase2.db < seed.sql
-- Idempotent: INSERT OR IGNORE lets you re-run without duplicate-key errors.

-------------------------------------------------------------------------------
-- endpoint
-------------------------------------------------------------------------------
INSERT OR IGNORE INTO endpoint (endpoint, kind, description) VALUES
  ('ORR',          'response',      'Objective response rate = CR + PR (primary readout)'),
  ('CR',           'response',      'Complete response — disappearance of all target lesions'),
  ('PR',           'response',      'Partial response — >=30% decrease in sum of target-lesion diameters'),
  ('DCR',          'response',      'Disease control rate = CR + PR + stable disease'),
  ('DoR',          'time_to_event', 'Duration of response — response to progression/death'),
  ('PFS',          'time_to_event', 'Progression-free survival'),
  ('TTP',          'time_to_event', 'Time to progression (excludes death)'),
  ('OS',           'time_to_event', 'Overall survival — time to death'),
  ('milestone_OS', 'time_to_event', 'OS rate at a fixed landmark timepoint'),
  ('milestone_PFS','time_to_event', 'PFS rate at a fixed landmark timepoint'),
  ('PRO',          'pro',           'Patient-reported outcome / quality of life');

-------------------------------------------------------------------------------
-- response_criteria
-------------------------------------------------------------------------------
INSERT OR IGNORE INTO response_criteria (response_criteria, description) VALUES
  ('RECIST1.1', 'Response Evaluation Criteria in Solid Tumors v1.1'),
  ('iRECIST',   'Immune-modified RECIST (iUPD -> iCPD; handles pseudoprogression)'),
  ('WHO',       'WHO bidimensional response criteria (legacy)'),
  ('other',     'Other / unspecified response criteria');

-------------------------------------------------------------------------------
-- tumor_type
-------------------------------------------------------------------------------
INSERT OR IGNORE INTO tumor_type (tumor_type, description) VALUES
  ('breast',            'Breast cancer'),
  ('lung_nsclc',        'Non-small-cell lung cancer'),
  ('lung_sclc',         'Small-cell lung cancer'),
  ('colorectal',        'Colorectal cancer'),
  ('prostate',          'Prostate cancer'),
  ('ovarian',           'Ovarian cancer'),
  ('pancreatic',        'Pancreatic cancer'),
  ('gastric',           'Gastric / gastroesophageal cancer'),
  ('hepatocellular',    'Hepatocellular carcinoma'),
  ('bladder',           'Bladder / urothelial cancer'),
  ('renal',             'Renal cell carcinoma'),
  ('head_neck',         'Head and neck squamous-cell carcinoma'),
  ('melanoma',          'Melanoma'),
  ('glioma',            'Glioma / glioblastoma'),
  ('cervical',          'Cervical cancer'),
  ('endometrial',       'Endometrial cancer'),
  ('esophageal',        'Esophageal cancer'),
  ('sarcoma',           'Soft-tissue / bone sarcoma (incl. osteosarcoma, GIST)'),
  ('thyroid',           'Thyroid cancer'),
  ('neuroendocrine',    'Neuroendocrine tumors'),
  ('leukemia_aml',      'Acute myeloid leukemia'),
  ('leukemia_all',      'Acute lymphoblastic leukemia'),
  ('leukemia_cll',      'Chronic lymphocytic leukemia'),
  ('leukemia_cml',      'Chronic myeloid leukemia'),
  ('lymphoma_hodgkin',  'Hodgkin lymphoma'),
  ('lymphoma_nhl',      'Non-Hodgkin lymphoma'),
  ('myeloma',           'Multiple myeloma'),
  ('mixed',             'Mixed / basket trial across tumor types'),
  ('other',             'Other / unspecified solid or hematologic tumor');
