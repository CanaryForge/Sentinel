---
inclusion: always
---

# Estructura del repositorio

```
sandbox/       Capa 1 -- agente: Dockerfile, agent.py, prompts.py, heartbeat.py
mocks/         Capa 3 -- servicios simulados: package_registry, model_hub
redteam/       Vector 4 (overlay opcional) -- red-teamer con prompt injection
monitors/      Capas 2 y 4 -- los tres monitores + proxy de egress
tasks/         Las 4 tareas con pista de escape plantada, mas tasks/seed/
orchestrator/  Capa 5 -- matriz experimental y loop de corridas
analysis/      TTD + bootstrap CI
results/       JSONL por corrida (NO versionado, ver .gitignore)
report/        scope.md (alcance honesto) y findings.md (resultados)
.kiro/         specs/ y steering/ -- este directorio
```

## Donde tocar segun lo que se quiera cambiar

| Quiero... | Archivo(s) |
|---|---|
| Agregar una herramienta nueva al agente | `sandbox/agent.py` (`TOOLS` + `DISPATCH`) |
| Cambiar el system prompt / la condicion con_harness | `sandbox/prompts.py` |
| Agregar un vector de escape nuevo | `tasks/task_0N_*.md` + `tasks/seed/task_0N_*/`, y si necesita un mock nuevo, un `docker-compose.<vector>.yml` overlay + `orchestrator/config_<vector>.yaml` (ver el patron de `redteam/`) |
| Cambiar que cuenta como "intento de escape" | `analysis/compute_ttd.py` (`first_escape_attempt_ts` / logica por tarea en `analyze_run`) |
| Agregar un monitor nuevo | `monitors/`, reusando `event_bus.py` para el formato de evento |
| Cambiar la matriz experimental (condiciones/tareas/repeticiones) | `orchestrator/config.yaml` (base) o un config alterno |
| Ver que se valido de verdad vs. que esta sin probar | `report/scope.md` (seccion "Validacion realizada") y `.kiro/specs/sandbox-escape-harness/tasks.md` |

## Archivos que el orquestador en vivo puede releer en caliente

`run_experiment.py` invoca `docker compose` como subproceso en cada
iteracion, releyendo desde disco: el/los `docker-compose*.yml` que declare
`compose_files` en el config activo, y todo el contexto de build de cada
servicio (`sandbox/`, `monitors/`, `mocks/*/`, `redteam/`). Si hay una
corrida en curso, evitar editar el `docker-compose.yml` que esa corrida
esta usando -- ver la convencion de overlays en `tech.md`. El propio
`config.yaml`/`.py` del orquestador SI se puede editar en caliente sin
riesgo: se lee una sola vez al arrancar el proceso, no en cada iteracion.
