# Build the Cancers (MDPI) manuscript and submission archive.
# Requires the MDPI template in ./Definitions (https://www.mdpi.com/authors/latex).

manuscript.pdf: manuscript.tex bibliography.bib $(wildcard *.png)
	latexmk -pdf -interaction=nonstopmode manuscript.tex

supplementary_tables.xlsx: make_supp.py
	python make_supp.py

submission: manuscript.pdf          ## build oncosyn_cancers_submission.zip
	./make_submission.sh

clean:
	latexmk -c
	rm -f manuscript.pdf oncosyn_cancers_submission.zip

.PHONY: submission clean
