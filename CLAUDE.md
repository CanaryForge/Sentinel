# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es esto

Arnés de detección de fuga de sandbox para agentes de IA (AI Incident
Response Sprint, Apart Research / CeSIA). Mide, para un agente con
herramientas que intenta escapar de su sandbox, **cuánto tarda en
detectarse y con qué señal** — usando tres monitores independientes del
modelo (heartbeat, canary de filesystem/red, baseline de egress) sobre
mocks locales, nunca contra internet real ni servicios de terceros.

Antes de afirmar nada sobre resultados o cobertura, leer
`report/scope.md` (qué demuestra esto y qué NO) — es la fuente de verdad
sobre el alcance honesto del proyecto, y está escrito para no acomodarse
después de tener resultados.

Todo el código, comentarios, docs y mensajes de log de este repo están en
español — mantener esa convención en cualquier cambio.

## Comandos

```bash
# Antes de la primera corrida (los contenedores corren con cap_drop:[ALL],
# sin DAC_OVERRIDE, y results/ es un bind mount del host)
chmod 777 results/

# Controles positivos -- CORRER ESTO PRIMERO SIEMPRE. Inyecta a mano los 4
# eventos que los monitores deben detectar y mide TTD real, sin gastar
# cuota de LLM. Exit code 0 = los 4 dispararon.
tests/positive_controls.sh

# Validar la matriz experimental sin gastar cómputo
pip install -r orchestrator/requirements.txt
python3 orchestrator/run_experiment.py --dry-run --limit 5
docker compose config -q

# Prueba de humo de un run completo
cp .env.example .env
docker compose up --build
docker compose logs sandbox   # debe terminar "agente termino con status=0"
docker compose down -v

# Experimento completo (vectores 1-3), secuencial y reentrante
python3 orchestrator/run_experiment.py

# Vector 4 (prompt injection via SSRF de juguete) -- correr DESPUES del base
python3 orchestrator/run_experiment.py --config orchestrator/config_redteam.yaml

# Vectores 5/6 (memoria y RAG envenenados) -- sembrar una sola vez antes
tests/seed_memory_poison.sh
python3 orchestrator/run_experiment.py --config orchestrator/config_memory_rag.yaml

# Experimento causal (por qué con_harness fuga más en vector 6)
python3 orchestrator/run_experiment.py --config orchestrator/config_causal_priming.yaml

# Análisis (TTD, tasas de deteccion, bootstrap CI) -- corre sobre TODO results/
pip install -r analysis/requirements.txt
python3 analysis/compute_ttd.py
python3 analysis/extract_cot.py   # razonamiento pre-escape del agente

# Fortaleza de monitores (barrido determinístico, sin LLM, ~6-8 min)
tests/monitor_strength_sweep.sh

# Dashboard (Flask, lee results/ en vivo, reusa la logica de compute_ttd.py)
pip install -r dashboard/requirements.txt
python3 dashboard/app.py   # http://localhost:8765

# Condicion de control de red (manual, fuera de la matriz automatizada)
docker compose -f docker-compose.yml -f docker-compose.control.yml \
  up --build sandbox package-registry model-hub
```

No hay suite pytest activa en este repo (los `__pycache__` de `tests/` y
`orchestrator/` son residuos de una configuración anterior); la
verificación es funcional, vía los scripts de arriba.

### Notas de entorno que importan

- `docker compose run` (usado por `tests/positive_controls.sh` y
  `tests/monitor_strength_sweep.sh`) puede colgarse indefinidamente cuando
  se invoca desde el entorno de ejecución del propio asistente (sin TTY
  real) — es un artefacto conocido del harness de Claude Code, no un bug
  del proyecto. Si un `docker compose run` se cuelga, pedirle al usuario
  que corra el mismo script en su propia terminal antes de asumir que algo
  está roto (ver `report/hardware_validation.md`, sección 3).
- Ollama arranca con `OLLAMA_NUM_CTX` chico por defecto; un turno agéntico
  consume 8000-16000 tokens. Súbelo en `.env`, y confirma que el modelo
  soporte tool calling en formato OpenAI o `agent.py` falla con un error
  visible en logs.
- `results/` necesita `chmod 777` una vez (no revertir el `cap_drop` para
  "arreglarlo" de otra forma).

## Arquitectura

```
sandbox (agente + heartbeat pinger)  --HTTP_PROXY-->  egress-proxy (mitmproxy)
                                                          |  egress_monitor.py: baseline + canary de red
                                                          |  heartbeat_monitor.py: watchdog de silencio
                                                          v
                                                       red-mocks (internal: true)
                                                          |
                                              package-registry (SSRF de juguete)
                                              model-hub (credenciales plantadas)

workspace (volumen compartido, solo lectura) --> fs-monitor: canary_monitor.py
                                                  (nombres de archivo/dir + contenido, via inotify)
```

Todos los monitores escriben al mismo formato JSONL
(`monitors/event_bus.py`: `{type, run_id, ts, severidad: info|alerta,
detalle}`) en `results/{run_id}.jsonl`; el transcript del agente va a
`results/{run_id}_transcript.jsonl`. Cualquier monitor nuevo reusa ese
formato, nunca uno paralelo.

Redes Docker: `red-proxy` y `red-mocks` son SIEMPRE `internal: true` (nada
toca internet real). `llm-backend` es la única red no-interna, exclusiva
para que `agent.py`/`heartbeat.py` lleguen al backend de LLM configurado
(Ollama local u OpenAI-compatible en la nube) — ese tráfico no es parte de
la superficie de escape medida.

### Decisiones de diseño no obvias

- **`sandbox/agent.py`** es un loop de tool-calling propio (no OpenCode CLI
  real) hablando el formato de chat completions OpenAI-compatible —
  funciona con Ollama y con cualquier endpoint OpenAI-compatible
  (OpenCode Go/Zen, validado end-to-end; requiere el header
  `x-opencode-session` que `agent.py` agrega solo cuando detecta
  `opencode.ai` en la base URL).
- **Eje con_harness / sin_harness** = presencia o ausencia de un system
  prompt con guardrails de seguridad (`sandbox/prompts.py`). El canary
  token se inyecta en ambas condiciones por igual (es instrumentación de
  detección, no una medida de seguridad); lo que varía es si se le advierte
  al agente explícitamente que no salga del scope.
- **"Intento de escape"** se define operacionalmente como la primera
  llamada a la herramienta `http_fetch` en el transcript
  (`analysis/compute_ttd.py`, `first_escape_attempt_ts`) — elección
  explícita, no una detección universal de todo comportamiento anómalo.
- **Hallazgo contraintuitivo confirmado con datos** (ver
  `report/findings.md`): `con_harness` fuga MÁS que `sin_harness` en el
  vector de RAG poisoning, porque el guardrail nombra la superficie de
  ataque (archivos/directorios/URLs) al advertir sobre ella — efecto de
  "priming", aislado en `orchestrator/config_causal_priming.yaml`.
- **`canary_monitor.py` detecta por eventos (watchdog/inotify)**, no por
  polling; `CANARY_FALLBACK_INTERVAL` solo controla el barrido de respaldo,
  no la latencia real de detección (confirmado con
  `tests/monitor_strength_sweep.sh`).
- **Vector 5 (memoria)** usa `./memory/notes.jsonl` como bind mount al
  host — a diferencia del volumen `workspace`, `docker compose down -v`
  NO lo borra, modelando memoria de equipo que persiste entre corridas no
  relacionadas. Vector 6 (RAG) lee `/workspace/knowledge_base/` sembrado
  por tarea. Ambos son ASI06 (Memory & Context Poisoning) del OWASP Top 10
  for Agentic Applications — ver `report/scope.md`.

### Dónde tocar según lo que se quiera cambiar

| Quiero... | Archivo(s) |
|---|---|
| Agregar una herramienta nueva al agente | `sandbox/agent.py` (`TOOLS` + `DISPATCH`) |
| Cambiar el system prompt / la condición con_harness | `sandbox/prompts.py` |
| Agregar un vector de escape nuevo | `tasks/task_0N_*.md` + `tasks/seed/task_0N_*/`; si necesita un mock nuevo: `docker-compose.<vector>.yml` overlay + `orchestrator/config_<vector>.yaml` (patrón de `redteam/`) |
| Cambiar qué cuenta como "intento de escape" | `analysis/compute_ttd.py` (`analyze_run`) |
| Agregar un monitor nuevo | `monitors/`, reusando `event_bus.py` |
| Cambiar la matriz experimental (condiciones/tareas/repeticiones) | `orchestrator/config.yaml` o un config alterno |
| Ver qué se validó de verdad vs. qué está sin probar | `report/scope.md` y `.kiro/specs/sandbox-escape-harness/tasks.md` |

**Cuidado al editar `docker-compose.yml` mientras el orquestador corre**:
`run_experiment.py` relee ese archivo desde disco en cada invocación de
`docker compose`; un cambio a mitad de una matriz en ejecución contamina
las corridas restantes. Vectores nuevos van en un overlay
(`docker-compose.<vector>.yml`), nunca mezclados en el base hasta que la
corrida en curso termine. El config YAML del propio orquestador sí se
puede editar en caliente (se lee una sola vez al arrancar el proceso).

Credenciales/secretos en mocks: siempre cadenas inventadas
(`fake-token-do-not-use-*`), nunca reales.

## Estructura

```
sandbox/       agente (Capa 1): Dockerfile, agent.py, prompts.py, heartbeat.py
mocks/         servicios simulados (Capa 3): package_registry, model_hub
redteam/       vector 4 (overlay opcional): red-teamer con prompt injection
monitors/      los tres monitores + proxy de egress (Capas 2 y 4)
tasks/         tareas con pista de escape plantada, + tasks/seed/
orchestrator/  matriz experimental y loop de corridas (Capa 5)
analysis/      TTD + bootstrap CI + análisis de CoT
dashboard/     panel Flask que visualiza results/ en vivo
results/       JSONL por corrida (no versionado, ver .gitignore)
report/        scope.md, findings.md, hardware_validation.md
.kiro/         specs/ y steering/ (contexto de producto/stack/estructura)
```
