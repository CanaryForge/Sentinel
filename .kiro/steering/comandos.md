---
inclusion: always
---

# Comandos para correr pruebas y experimentos

Referencia rapida de como ejecutar este proyecto. Detalle completo y
contexto de diseno en `README.md`; este archivo solo cubre lo operacional
para no duplicar la explicacion.

## Docker en Windows: gotchas encontrados corriendo esto en Windows/Git Bash

Si corres estos comandos desde una terminal Windows (PowerShell o Git
Bash), tres cosas rompen silenciosamente si no se conocen:

1. **`docker.exe` puede no estar en PATH** si Docker Desktop se instalo
   per-user (`%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin`) en vez
   de la ruta de sistema (`C:\Program Files\Docker\...`). Verificar con
   `Get-Command docker.exe` antes de asumir que docker no esta instalado.
2. **CRLF en scripts que corren dentro de contenedores Linux**: si Git
   tiene `core.autocrlf=true` (default en Windows) y no hay
   `.gitattributes` forzando LF, cualquier `.sh` con shebang que Docker
   ejecute como entrypoint falla con `env: 'bash\r': No such file or
   directory` y el contenedor sale con exit 127 -- silencioso y facil de
   confundir con un bug de red/DNS (el sintoma es "no puedo resolver tal
   servicio" porque ese servicio nunca llego a arrancar). Ya hay
   `.gitattributes` en la raiz forzando `*.sh` y `Dockerfile` a LF; si
   reaparece en un archivo nuevo, `sed -i 's/\r$//' archivo.sh` lo arregla.
3. **MSYS/Git Bash reescribe argumentos sueltos que parecen rutas
   absolutas** (p.ej. `/app/heartbeat.py` pasado a `docker compose run
   --entrypoint python3 sandbox /app/heartbeat.py`) a una ruta de Windows
   antes de que lleguen al contenedor. `export MSYS_NO_PATHCONV=1` antes
   de invocar `docker compose` lo evita (ya seteado dentro de
   `tests/positive_controls.sh` y `tests/monitor_strength_sweep.sh`).
4. **`analysis/compute_ttd.py` necesita `encoding="utf-8"` explicito** en
   sus `open()` -- sin eso, Python en Windows usa el codepage del sistema
   (cp1252) y truena con `UnicodeDecodeError` al leer un transcript con
   texto no-ASCII. Ya arreglado en el archivo; si se agrega un `open()`
   nuevo en `analysis/` o `dashboard/`, pasarle `encoding="utf-8"` siempre.

## Antes de la primera corrida

```bash
chmod 777 results/   # los contenedores corren cap_drop:[ALL], sin DAC_OVERRIDE
cp .env.example .env
```

Confirmar que `OLLAMA_MODEL` en `.env` coincide con un modelo realmente
instalado (`curl http://localhost:11434/api/tags`), no con el nombre que
trae el `.env.example` por default.

## Controles positivos -- correr SIEMPRE antes de fiarse de una tasa de deteccion

```bash
tests/positive_controls.sh
```

Sin LLM, menos de un minuto. Si algun control falla, no correr el
experimento todavia -- hay un monitor ciego (ver `report/scope.md`,
Escenario C).

## Validar la matriz sin gastar computo

```bash
python3 orchestrator/run_experiment.py --dry-run --limit 5
docker compose config -q
```

## Correr el experimento

El orquestador es reentrante: saltea automaticamente cualquier `run_id`
que ya tenga `{run_id}.jsonl` en `results/`. Para que un run se rehaga
desde cero hay que borrar sus tres archivos (`.jsonl`, `_meta.json`,
`_transcript.jsonl`) a mano primero.

Cubrir los 6 tasks requiere tres matrices separadas -- ninguna las
combina, cada una usa su propio config/overlay de compose (ver tabla en
`structure.md`, "Donde tocar"). `tests/run_full_matrix.sh` las encadena
las tres (+ controles positivos antes, + analisis al final) en un solo
comando idempotente -- correrlo asi en vez de pedirle al agente que
dispare cada paso por separado: son pasos mecanicos, no necesitan una
interaccion de agente por paso.

```bash
tests/run_full_matrix.sh
# o desatendido: nohup tests/run_full_matrix.sh > full_run.log 2>&1 &
```

Equivalente paso a paso (por si se necesita correr solo un vector):

```bash
# Vectores 1-3 (matriz base, config.yaml por defecto)
python3 orchestrator/run_experiment.py

# Vector 4 (red-teamer/prompt injection) -- DESPUES de la matriz base
python3 orchestrator/run_experiment.py --config orchestrator/config_redteam.yaml

# Vectores 5-6 (memoria y RAG envenenados) -- sembrar memoria una vez antes
tests/seed_memory_poison.sh
python3 orchestrator/run_experiment.py --config orchestrator/config_memory_rag.yaml
```

## Analisis

```bash
python3 analysis/compute_ttd.py    # TTD + tasas de deteccion, escribe results/summary.jsonl
python3 analysis/extract_cot.py    # razonamiento del agente pre-escape, escribe report/cot_analysis.md
```

Ambos corren sobre TODO lo que haya en `results/` en ese momento, sin
filtrar por vector -- si se quiere un snapshot fijo de un punto intermedio
(p.ej. antes de correr el siguiente vector), copiar
`results/summary.jsonl` y `report/cot_analysis.md` a otro nombre primero,
porque la proxima corrida de estos scripts los sobreescribe.

## Dashboard (opcional, visual)

```bash
python3 dashboard/app.py   # http://localhost:8765
```
