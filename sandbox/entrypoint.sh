#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] run_id=${RUN_ID:-?} condition=${CONDITION:-?} task=${TASK:-?}"

mkdir -p /workspace

# Siembra el workspace: variante especifica de la tarea primero (puede
# sobreescribir archivos base, p.ej. un test_division.py distinto), luego
# la base comun con -n para no pisar lo que ya puso la variante. down -v
# destruye el volumen entre corridas, asi que esto se repite en cada una.
if [ -d "/tasks/seed/${TASK:-}" ]; then
  cp -r "/tasks/seed/${TASK}/." /workspace/ 2>/dev/null || true
fi
cp -rn /tasks/seed/common/. /workspace/ 2>/dev/null || true

python3 /app/heartbeat.py &
HEARTBEAT_PID=$!
trap 'kill "$HEARTBEAT_PID" 2>/dev/null || true' EXIT

set +e
timeout "${RUN_TIMEOUT_SECONDS:-240}" python3 /app/agent.py
STATUS=$?
set -e

echo "[entrypoint] agente termino con status=$STATUS"
exit "$STATUS"
