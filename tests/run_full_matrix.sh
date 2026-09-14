#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# En Git Bash (Windows) el runtime MSYS reescribe argumentos sueltos que
# parecen rutas absolutas -- ver .kiro/steering/comandos.md. No-op en
# Linux/macOS.
export MSYS_NO_PATHCONV=1

# Cadena completa de los 6 tasks (ver README/tech.md): cada matriz usa su
# propio config/overlay de compose y no se pueden fusionar en una sola
# invocacion de run_experiment.py. set -e corta la cadena si algo falla --
# preferible a gastar horas de computo (y el turno de agente que interprete
# los resultados despues) sobre monitores ciegos o una matriz corrupta.
#
# Reentrante de punta a punta: cada run_experiment.py saltea los run_id que
# ya tengan {run_id}.jsonl en results/, asi que interrumpir esto (Ctrl+C) y
# volver a correrlo retoma donde quedo, sin repetir corridas ya validas.
#
# Uso: tests/run_full_matrix.sh
#   (para correrlo desatendido en background: nohup tests/run_full_matrix.sh > full_run.log 2>&1 &)

echo "[full-matrix] 1/6 controles positivos (monitores no ciegos)"
tests/positive_controls.sh

echo "[full-matrix] 2/6 matriz base (tasks 1-3, config.yaml)"
python3 orchestrator/run_experiment.py

echo "[full-matrix] 3/6 vector 4 (task 4, redteam activo)"
python3 orchestrator/run_experiment.py --config orchestrator/config_redteam.yaml

echo "[full-matrix] 4/6 sembrando memoria envenenada para vector 5"
tests/seed_memory_poison.sh

echo "[full-matrix] 5/6 vectores 5-6 (memoria y RAG envenenados)"
python3 orchestrator/run_experiment.py --config orchestrator/config_memory_rag.yaml

echo "[full-matrix] 6/6 analisis (TTD + CoT)"
python3 analysis/compute_ttd.py
python3 analysis/extract_cot.py

echo "[full-matrix] listo. results/summary.jsonl y report/cot_analysis.md actualizados."
