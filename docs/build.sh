#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Los ~15 archivos intermedios van a _build/ y no al directorio de fuentes.
OUT=_build
mkdir -p "$OUT"

# MiKTeX recorre el PATH y aborta si una entrada apunta a un ARCHIVO en vez de
# a un directorio ("cannot retrieve attributes for the directory ...
# claude.exe\"). Git Bash traduce el PATH de Windows y puede dejar entradas
# asi. Se filtran para esta invocacion; no se toca el PATH del usuario.
LIMPIO=""
IFS=':' read -ra _entradas <<< "$PATH"
for e in "${_entradas[@]}"; do
  [ -z "$e" ] && continue
  [ -d "$e" ] || continue
  LIMPIO="${LIMPIO:+$LIMPIO:}$e"
done
export PATH="$LIMPIO"

# bibtex corre con el cwd en _build/ (por -outdir) y no encuentra refs.bib ni
# las fuentes del padre. BIBINPUTS/TEXINPUTS se lo dicen; el ":" final
# conserva las rutas por defecto del sistema.
export BIBINPUTS=".:$PWD:"
export TEXINPUTS=".:$PWD:"

# latexmk resuelve solo cuantas pasadas hacen falta, pero en MiKTeX es un
# script Perl: sin Perl instalado falla con "Make sure 'perl' is installed".
# Por eso se prueba y, si no esta, se cae a pdflatex con pasadas explicitas.
if command -v latexmk >/dev/null 2>&1 && command -v perl >/dev/null 2>&1; then
  latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir="$OUT" paper.tex
else
  echo "-- latexmk o perl no disponibles; usando pdflatex con pasadas explicitas --"
  command -v pdflatex >/dev/null 2>&1 || {
    echo "FALLA: pdflatex no esta en el PATH (instala MiKTeX o TeX Live)." >&2
    exit 2
  }
  pdflatex -interaction=nonstopmode -halt-on-error -output-directory="$OUT" paper.tex
  # bibtex solo cuando hay citas de verdad; con refs.bib sin \cite se queja.
  if grep -qE '\cite\{' sections/*.tex paper.tex 2>/dev/null; then
    (cd "$OUT" && bibtex paper) || true
    pdflatex -interaction=nonstopmode -halt-on-error -output-directory="$OUT" paper.tex
  fi
  # Segunda pasada: referencias cruzadas y tabla de contenidos.
  pdflatex -interaction=nonstopmode -halt-on-error -output-directory="$OUT" paper.tex
fi

cp "$OUT/paper.pdf" ./paper.pdf
echo "listo -> docs/paper.pdf"

# Cuenta los marcadores abiertos. Se buscan las MACROS (	odo{ / \pending{),
# no el texto "TODO:", que solo aparece en la definicion de la macro.
t=$(grep -ro 'todo{' sections/ paper.tex 2>/dev/null | wc -l | tr -d ' ')
n=$(grep -ro 'pending{' sections/ paper.tex 2>/dev/null | wc -l | tr -d ' ')
b=$(grep -c 'PENDIENTE' refs.bib 2>/dev/null | tr -d ' ')
echo "marcadores abiertos: $t todo, $n pending, $b pendientes en refs.bib"
echo "(el paper compila con marcadores a proposito: un borrador incompleto"
echo " sigue siendo compartible)"
