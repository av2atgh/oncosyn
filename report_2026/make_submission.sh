#!/usr/bin/env bash
# Build the Cancers (MDPI) submission archive: the files needed to compile
# manuscript.pdf. The supplementary spreadsheet is uploaded separately and is
# NOT included here.
#
#   ./make_submission.sh
#
# Requires: a TeX distribution (latexmk) and the MDPI template files in
# ./Definitions (download from https://www.mdpi.com/authors/latex).
set -euo pipefail
cd "$(dirname "$0")"

ZIP="oncosyn_cancers_submission.zip"

if [ ! -d Definitions ]; then
  echo "ERROR: ./Definitions (MDPI template) not found." >&2
  echo "Download the Cancers LaTeX template from https://www.mdpi.com/authors/latex" >&2
  exit 1
fi

echo "[1/2] compiling manuscript.pdf (pdflatex + bibtex)"
latexmk -pdf -interaction=nonstopmode manuscript.tex >/dev/null

echo "[2/2] assembling $ZIP"
rm -f "$ZIP"
zip -r "$ZIP" \
    manuscript.tex \
    bibliography.bib \
    manuscript.bbl \
    manuscript.pdf \
    ./*.png \
    Definitions \
    -x '*.DS_Store' >/dev/null

latexmk -c >/dev/null 2>&1   # tidy LaTeX aux (keeps .pdf and the .zip)

echo
echo "wrote $ZIP:"
unzip -l "$ZIP" | awk 'NR>3 && $4!="" {print "  "$4}' | sed '/^  $/d'
