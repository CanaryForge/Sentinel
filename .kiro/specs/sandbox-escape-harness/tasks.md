# Tasks: Sandbox Escape Detection Harness

Estado a 2026-09-12. `[x]` = hecho y validado end-to-end; `[~]` = codigo
listo, sin ejecutar todavia; `[ ]` = pendiente.

## Capa 1 — Sandbox

- [x] Dockerfile + entrypoint.sh (siembra el workspace desde `tasks/seed/`)
- [x] `agent.py`: loop de tool-calling OpenAI-compatible (read_file,
      write_file, list_dir, http_fetch, run_tests)
- [x] `prompts.py`: system prompt con canary + bloque de harness condicional
- [x] `heartbeat.py`: ping periodico bypasseando el proxy
- [x] Fix: `_safe_path` tolera rutas absolutas `/workspace/...`
- [x] Fix: `backend_config()` normaliza `/v1` (evita duplicado)
- [x] Soporte `x-opencode-session` para OpenCode Go/Zen
- [ ] Backend Ollama validado end-to-end (contrato de entorno listo, no
      probado en esta maquina por no tener Ollama instalado)

## Capa 2 — Egress

- [x] `docker-compose.yml`: `red-proxy` y `red-mocks` `internal: true`
- [x] Red `llm-backend` separada, no-internal, solo para el backend del LLM
- [x] `docker-compose.control.yml`: condicion de control sin proxy (manual)

## Capa 3 — Mocks

- [x] `package_registry`: catalogo + `/fetch` (SSRF de juguete)
- [x] `model_hub`: credenciales inventadas + endpoints protegidos

## Capa 4 — Monitores

- [x] `heartbeat_monitor.py` + watchdog de silencio
- [x] `canary_monitor.py` (filesystem: nombres + contenido)
- [x] `egress_monitor.py` (baseline + canary en red)
- [x] `event_bus.py` (formato comun + variantes de ofuscacion)
- [x] Validacion deterministica de los 3 monitores (peticion sintetica por
      el proxy + directorio sintetico en el volumen) sin gastar cuota de
      LLM

## Capa 5 — Experimento y analisis

- [x] `orchestrator/run_experiment.py`: matriz reentrante, secuencial
- [x] `orchestrator/config.yaml`: 3 tareas x 2 condiciones x 10 reps = 60
- [x] `analysis/compute_ttd.py`: TTD + bootstrap CI
- [x] Fix: heartbeat de apagado ya no cuenta como falso-positivo de
      deteccion
- [x] Matriz base (60 corridas) terminada 2026-09-12, 0 errores de infra --
      ver `results/summary.jsonl`
- [x] `report/findings.md` completado con los resultados reales (0/30
      intentos con_harness, 1/30 sin_harness, 0/1 detectado -- ver ahi el
      hallazgo del punto ciego de egress_monitor con destinos inalcanzables)
- [x] Correr `analysis/compute_ttd.py` sobre la matriz base terminada
- [x] Fix real encontrado con datos: `docker_exit_code` para no atribuir a
      heartbeat una deteccion cuando el timing de su alerta de apagado
      coincide por casualidad con un intento de escape real

## Vector 4 — Red-teamer / prompt injection (Historia 5)

- [x] `redteam/app.py`: sirve payload de prompt injection en `/patches/<pkg>`
- [x] `docker-compose.redteam.yml`: overlay con alias de red `mirror-externo`
- [x] `tasks/task_04_prompt_injection.md` + seed (`requirements.txt`)
- [x] `orchestrator/config_redteam.yaml`: matriz separada (2 x 1 x 10 = 20)
- [x] `run_experiment.py` extendido con `--config` y `compose_files`
      configurables (sin romper el uso default)
- [x] `analysis/compute_ttd.py`: definicion de "intento de escape" propia
      para este vector (canary en argumentos de tool call, no el
      `http_fetch` inicial que el hint ya autoriza)
- [x] Fix real encontrado en corrida manual: la seed original dejaba el
      fetch al mirror como opcional, y el modelo nunca lo necesito (0
      intentos) -- se reescribio `tasks/seed/task_04_prompt_injection/
      test_division.py` para que el fetch sea la unica via de progreso
- [x] Corrida manual con el fix: ciclo completo observado (6 URLs
      adivinadas -> mirror real -> payload leido -> instruccion inyectada
      seguida -> `canary_monitor` detecto en ~2.1s). Ver `report/
      findings.md`, seccion "Vector 4 en vivo"
- [x] Correr `orchestrator/run_experiment.py --config
      orchestrator/config_redteam.yaml` (matriz completa de 20 corridas,
      hecho 2026-09-13 en esta maquina)
- [x] Incorporar resultados agregados del vector 4 a `report/findings.md`

## Vectores 5-6 — Memoria y RAG envenenados (Historia ASI06)

- [x] `orchestrator/config_memory_rag.yaml`: matriz de 40 corridas (2 x 2 x 10)
- [x] `tests/seed_memory_poison.sh`: siembra `./memory/notes.jsonl`
- [x] Matriz completa corrida 2026-09-13 en esta maquina
- [x] Resultados incorporados a `report/findings.md` -- ver seccion
      "Machine-D (Windows ARM64, Sofia, 2026-09-13)": dataset
      independiente (Windows-on-ARM, Qualcomm Snapdragon), comparado contra
      machine-A (Daniel) y machine-B (Sergio, lote valido 0.34.0); no
      confirma el Hallazgo 2 para task_05/task_06 en esta maquina, sin
      invalidar ninguna de las tres corridas. Datos organizados en
      `results/machine-D/corpus/` + `results/machine-D/manifest.json`
      siguiendo la convencion de `results/README.md`
- [ ] Re-correr `orchestrator/config_causal_priming.yaml` en esta maquina
      para poder confirmar o descartar el Hallazgo 2 con datos locales
- [x] Run 2 de vectores 5/6 en machine-D corrido 2026-09-13/14
      (`results/machine-D/memory-rag-run2/`, 40 corridas, manifest propio).
      El punto ciego de `sin_harness` (0/8 detectados) del run 1 NO se repite:
      run 2 da sin_harness 5/5 (100%) detectado -- ver "Run 2 en machine-D"
      en `findings.md`. Mas consistente con varianza de muestra chica que con
      un punto ciego sistemico, pero sigue sin revisarse transcript por
      transcript.
- [ ] Investigar linea por linea los 8 intentos `sin_harness` no detectados
      del run 1 (task_05/06) -- ver "Hallazgo nuevo" en `findings.md`. Menos
      urgente tras el run 2, pero sigue pendiente.
- [ ] Extender `analysis/extract_cot.py` para reconocer escapes de
      task_05/06 (canary en tool args, no `http_fetch`) -- hoy da 0 escapes
      sobre `results/machine-D/memory-rag-run2/` pese a que
      `compute_ttd.py` cuenta 14 intentos reales ahi
- [x] Encontrada y confirmada causa raiz de hardware (2026-09-14): 35/100
      corridas de machine-D (27 de corpus/, 8 de memory-rag-run2/) eran
      invalidas -- `docker_exit_code=0` pero cero tool calls, porque
      `sandbox/agent.py` timeout=120s es insuficiente en este hardware (un
      primer turno real mide 115.1s, medido con datos). Verificado
      reproducible con 3 re-corridas individuales (3/3 fallaron igual).
      Movidas a `results/machine-D/corpus-invalidas-timeout/` y
      `results/machine-D/memory-rag-run2-invalidas-timeout/` (con manifest
      explicando la causa), NO re-corridas con timeout distinto para no
      romper comparabilidad con el resto del proyecto (timeout=120 en
      todas las maquinas). `corpus/` y `memory-rag-run2/` quedan con 33 y
      32 corridas validas respectivamente
- [ ] Reescribir "Machine-D" y "Run 2 en machine-D" en
      `report/findings.md` con las cifras limpias (33+32 validas) despues
      de traer los cambios de `main` al branch -- ver nota de PENDIENTE DE
      REDACCION al inicio de esa seccion

## Documentacion

- [x] `README.md`: arquitectura, decisiones de diseno, prerrequisitos, como
      correr todo, backends probados
- [x] `report/scope.md`: alcance honesto + validacion realizada + bugs
      encontrados
- [x] `.kiro/specs/sandbox-escape-harness/`: este spec
- [ ] `.kiro/steering/`: steering docs del proyecto (en progreso, ver
      commits de esta misma sesion)
