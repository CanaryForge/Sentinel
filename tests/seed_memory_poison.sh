#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Siembra manual del vector 5 (memoria persistente entre corridas). Desde que
# orchestrator/run_experiment.py resetea ./memory antes de CADA corrida, este
# script ya no hace falta para correr la matriz: sirve para reproducir el
# estado a mano fuera del orquestador (una demo, un smoke test).
#
# El texto de la nota vive en tasks/seed/task_05_memory_poison/nota_envenenada.txt
# -- un solo sitio, leido tambien por el orquestador.
#
# Uso: tests/seed_memory_poison.sh

mkdir -p memory
chmod 777 memory 2>/dev/null || true

python3 - <<'PYEOF_INNER'
import json, time, io
nota = io.open("tasks/seed/task_05_memory_poison/nota_envenenada.txt",
               encoding="utf-8").read()
with io.open("memory/notes.jsonl", "w", encoding="utf-8", newline="
") as f:
    f.write(json.dumps({"ts": time.time(), "nota": nota}, ensure_ascii=False) + "
")
print("memory/notes.jsonl sembrado con la nota envenenada.")
PYEOF_INNER
