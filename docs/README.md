# docs/ : el paper

Esqueleto LaTeX del reporte para el AI Incident Response Sprint
(Apart Research / CeSIA), frente de Analisis del incidente.

## Compilar

```bash
./build.sh
```

Deja `docs/paper.pdf` y manda los ~15 archivos intermedios a `_build/`, que
esta en `.gitignore` junto al PDF. Se versiona la fuente, no lo que se
regenera.

El script prefiere `latexmk` y cae a `pdflatex` con pasadas explicitas si no
esta, o si falta Perl (en MiKTeX `latexmk` es un script Perl). Ademas sanea el
`PATH` antes de invocar a MiKTeX: si una entrada apunta a un archivo en vez de
a un directorio --Git Bash a veces las deja al traducir el PATH de Windows--
MiKTeX aborta con `cannot retrieve attributes for the directory`.

Al terminar imprime cuantos marcadores quedan abiertos.

## Estructura

| | |
|---|---|
| `paper.tex` | preambulo y orden de secciones |
| `sections/*.tex` | una seccion por archivo |
| `refs.bib` | bibliografia |
| `figures/` | figuras (exportar aqui el diagrama de arquitectura) |

## Marcadores

`\todo{...}` en rojo para lo que falta escribir, `\pending{...}` en naranja
para una cifra que aun no se verifico contra los artefactos. **El paper
compila con marcadores presentes a proposito**: un borrador incompleto sigue
siendo compartible, y los marcadores salen visibles en el PDF para que nadie
los pase por alto.

## Regla para los numeros

Toda cifra de este paper se cuenta sobre `results/` o `results_causal/`, con
codigo, en el momento de escribirla. **Nunca se lee de un archivo de
configuracion ni se copia de una version anterior del texto.**

No es una regla abstracta: la tabla del experimento causal se redacto leyendo
`repetitions: 10` de un YAML cuando en disco habia 3 corridas, y hubo que
retractarla. La Seccion 5 documenta esa y otras tres correcciones.

Los datos estan versionados en el repositorio (~1.8 MB), asi que cualquier
tabla se puede recomputar sin gastar cuota de API:

```bash
python3 analysis/compute_ttd.py                              # corpus de 63
python3 analysis/compute_ttd.py --results-dir results_causal # causal, 30
```

## Convenciones de redaccion

- **Sin guion largo.** Ni en el paper ni en este README. Usar coma, dos
  puntos, punto o parentesis segun el caso.
- Toda cifra se cuenta sobre los artefactos, nunca se lee de un config.

## Idioma

El paper va en **ingles**; el resto del repositorio (`report/`, comentarios,
commits en espanol donde ya los habia) se queda como esta.
