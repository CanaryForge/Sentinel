---
inclusion: always
---

# Stack tecnico y convenciones

## Stack

- **Orquestacion**: Docker Compose (multi-archivo: `docker-compose.yml`
  base + overlays `docker-compose.control.yml` / `docker-compose.redteam.yml`)
- **Agente**: Python 3.11, loop de tool-calling propio (`sandbox/agent.py`)
  hablando el formato de chat completions OpenAI-compatible -- NO OpenCode
  CLI real (ver decision de diseno en `design.md`)
- **Backends de LLM probados**: OpenCode Go/Zen (`https://opencode.ai/zen/go/v1`
  o `/zen/v1`, requiere header `x-opencode-session` desde 2026-09-06).
  Ollama soportado por contrato de env vars pero no validado en esta maquina.
- **Monitores**: `mitmproxy` (addon Python) para egress, `http.server`
  stdlib para heartbeat, polling de filesystem para canary
- **Mocks**: Flask, minimos (un archivo por servicio)
- **Analisis**: `numpy` (bootstrap CI), sin pandas ni otras dependencias pesadas
- **Config del orquestador**: YAML (`PyYAML`)

## Convenciones de este repo

- **Comentarios en el codigo**: solo cuando explican una decision no obvia
  (un bug real encontrado, un "por que" que sorprenderia a quien lea
  despues). Nunca comentarios que solo describen que hace la linea.
- **Idioma**: todo en espanol (codigo, comentarios, docs, mensajes de log),
  consistente con el resto del proyecto y el sprint.
- **Formato de eventos**: cualquier monitor nuevo escribe al mismo formato
  JSONL de `monitors/event_bus.py`
  (`{type, run_id, ts, severidad: info|alerta, detalle}`). No inventar un
  formato paralelo.
- **Redes Docker**: `red-proxy` y `red-mocks` son SIEMPRE `internal: true`.
  Si un componente nuevo necesita internet real (p.ej. hablar con un
  backend de LLM en la nube), va en una red separada y explicitamente
  documentada como tal (ver `llm-backend`), nunca relajando `internal` en
  las redes existentes.
- **Cambios a `docker-compose.yml` mientras el orquestador esta corriendo**:
  evitar. Cada iteracion del loop de `run_experiment.py` relee ese archivo
  desde disco en cada invocacion de `docker compose`; un cambio a mitad de
  una matriz en ejecucion contamina las corridas restantes. Vectores nuevos
  van en un overlay (`docker-compose.<vector>.yml`) + un config YAML propio
  (ver `orchestrator/config_redteam.yaml` como ejemplo), nunca mezclados en
  el archivo base hasta que la corrida en curso termine.
- **Permisos de `results/`**: los servicios corren con `cap_drop: [ALL]`,
  lo que le quita a root-en-contenedor `DAC_OVERRIDE`. `results/` (bind
  mount del host) necesita `chmod 777` una vez, documentado en README --
  no revertir el hardening para "arreglar" esto de otra forma.
- **Credenciales/secretos en mocks**: SIEMPRE cadenas inventadas
  (`fake-token-do-not-use-*`). Nunca credenciales reales ni de servicios
  externos existentes.
