# Trends in ORR Across Phase II and Phase III Oncology Trials — manuscript

Manuscript analysing objective response rate (ORR), overall survival (OS) and
progression-free survival (PFS) in Phase II/III oncology trials: combination
interactions under a Bliss-independence null, the predictive value of Phase II ORR
for Phase III, and survival trends. Updates and extends Kang, DiPaola & Vazquez
(*BMC Med Res Methodol* 2013;13:77) and Azam & Vazquez (*Cancers* 2021;13:178).

Formatted for submission to **_Cancers_ (MDPI)** using the official MDPI LaTeX
class (`Definitions/mdpi`) with a BibTeX bibliography.

## Build

The MDPI class files are **not** committed (third-party template). Get them first:

1. Download the LaTeX template for *Cancers* from <https://www.mdpi.com/authors/latex>
   (or use the Overleaf "MDPI Article Template"), which provides the `Definitions/`
   folder (`mdpi.cls`, `mdpi.bst`, logos). Place it here, alongside `manuscript.tex`.
2. Build:

```
make                    # -> manuscript.pdf (pdflatex + bibtex)
make supplementary_tables.xlsx   # -> Supplementary Tables S1/S2 (Excel)
make submission         # -> oncosyn_cancers_submission.zip
```

`make submission` runs `./make_submission.sh`, which compiles the manuscript and
packages the files needed to build `manuscript.pdf` (LaTeX source, `bibliography.bib`,
`manuscript.bbl`, figures, and the `Definitions/` template) into a zip. The
supplementary spreadsheet is uploaded separately and is **not** in that archive.

## Files
- `manuscript.tex` — the paper (MDPI class: `\Title`, `\simplesumm`, `\abstract`,
  back-matter statements, `\bibliography{bibliography}`)
- `bibliography.bib` — references (BibTeX, MDPI style via `mdpi.bst`)
- `*.png` — figures (in this folder, referenced by bare filename)
- `make_supp.py` — generates `supplementary_tables.xlsx` (Table S1 synergistic,
  Table S2 antagonistic) from the analysis database
- `supplementary_tables.xlsx` — the supplementary tables (separate MDPI upload)
- `make_submission.sh` — builds the submission zip
- `cover_letter.tex` — cover letter (git-ignored; not part of the repo)

Numbers and figures are produced by the analysis pipeline in the repository root
(`make report`); rerun `python make_supp.py` to refresh the supplement.
