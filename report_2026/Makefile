# Build the manuscript PDF
manuscript.pdf: manuscript.tex figures/agreement_scatter.png figures/bland_altman.png
	latexmk -pdf -interaction=nonstopmode manuscript.tex

clean:
	latexmk -c
	rm -f manuscript.pdf

.PHONY: clean
