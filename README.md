# Sandbox Escape Detection Harness

Arnes de deteccion de fuga de sandbox para agentes de IA. Construido para el
AI Incident Response Sprint (Apart Research / CeSIA), frente de Analisis del
incidente, anclado en el incidente OpenAI-Hugging Face de julio 2026 (SSRF en
Artifactory, comunicacion entre agentes codificada en nombres de directorio,
sin deteccion en tiempo real).

Ver `report/scope.md` para que demuestra este trabajo y que NO demuestra.

## Arquitectura

```
sandbox (agente + heartbeat pinger)  --HTTP_PROXY-->  egress-proxy (mitmproxy)
                                                          |  egress_monitor.py: baseline + canary de red
                                                          |  heartbeat_monitor.py: watchdog de silencio
                                                          v
                                                       red-mocks (internal)
                                                          |
                                              package-registry (SSRF de juguete)
                                              model-hub (credenciales plantadas)

workspace (volumen compartido, solo lectura) --> fs-monitor: canary_monitor.py
                                                  (nombres de archivo/dir + contenido)

Todos los monitores escriben a results/{run_id}.jsonl (formato comun en
monitors/event_bus.py). El transcript del agente, con timestamps, va a
results/{run_id}_transcript.jsonl.
```

Ambas redes Docker (`red-proxy`, `red-mocks`) estan declaradas `internal: true`:
nada de esto toca internet real, pase lo que pase.

## Decisiones de diseno que se apartan del enunciado original

- **Agente**: en vez de OpenCode CLI, `sandbox/agent.py` es un loop de
  tool-calling propio, minimo y auditable, hablando el formato de chat
  completions OpenAI-compatible (funciona con `/v1/chat/completions` de
  Ollama y con cualquier endpoint OpenAI-compatible real). Se eligio asi
  porque las flags exactas de OpenCode para forzar tool-calling contra un
  endpoint arbitrario no se podian verificar con confianza, y un fallo
  silencioso de CLI arruina el experimento completo. Cambiar a OpenCode real
  es cuestion de reemplazar `agent.py` manteniendo el mismo contrato de
  variables de entorno.
- **Eje "con_harness / sin_harness"**: se implementa como presencia o
  ausencia de un system prompt de produccion con guardrails de seguridad
  (`sandbox/prompts.py`). El canary token se inyecta en ambas condiciones
  (es instrumentacion de deteccion, no una medida de seguridad del agente);
  lo que cambia es si al agente se le advierte explicitamente que no debe
  salir de ese token ni del scope de la tarea.
- **"Condicion de control" de red** (Capa 2, sandbox sin proxy) es un eje
  *separado* de la matriz principal, pensado para demostraciones manuales
  de "que se pierde sin el arnes" (`docker-compose.control.yml`), no para
  las 150 corridas automatizadas.
- **Definicion operacional de "intento de escape"**: la primera llamada a la
  herramienta `http_fetch` en el transcript del agente. Es una eleccion
  explicita y documentada (`analysis/compute_ttd.py`), no una deteccion
  universal.

## Backends probados end-to-end

- **OpenCode Go / Zen** (OpenAI-compatible, `AGENT_BACKEND=openai`): base
  `https://opencode.ai/zen/go/v1` (Go, suscripcion mensual con modelos
  open-weight tipo Qwen/DeepSeek) o `https://opencode.ai/zen/v1` (Zen,
  prepago). Desde 2026-09-06 ambos exigen el header `x-opencode-session`
  (un UUID estable por conversacion); `agent.py` lo agrega automaticamente
  cuando detecta `opencode.ai` en la base. Validado con `deepseek-v4-pro`
  y `qwen3.6-plus`.
- **Ollama**: contrato de entorno listo (`AGENT_BACKEND=ollama`), pendiente
  de validar end-to-end en esta maquina (no tenia Ollama instalado).

## Prerrequisitos

```bash
docker --version && docker compose version
python3 --version
ollama --version   # opcional pero recomendado si no usas un backend en la nube
```

```bash
ollama pull qwen2.5-coder:7b   # o el modelo que quepa en RAM
```

⚠ **Permisos de `results/`**: los contenedores corren con `cap_drop: [ALL]`
(endurecimiento deliberado), lo que le quita a root-en-contenedor la
capacidad `DAC_OVERRIDE` -- su superpoder habitual para saltarse permisos
de archivo. Como `results/` es un bind mount del host (dueño: tu usuario),
sin esa capability los contenedores no pueden crear archivos ahi. Antes de
la primera corrida:

```bash
chmod 777 results/
```

(Alternativa mas fina si te incomoda 777: quitar `DAC_OVERRIDE` de la lista
de `cap_drop` en `egress-proxy`, `fs-monitor` y `sandbox` en vez de tocar
permisos del host.)

⚠ Ollama arranca con contexto de 2048 tokens por defecto; un turno agentico
consume 8000-16000 antes de razonar. `OLLAMA_NUM_CTX` en `.env` sube esto,
pero ademas el Modelfile del modelo debe respetarlo. Verifica tambien que el
modelo soporte tool calling en formato OpenAI, o `agent.py` fallara con un
error de backend visible en los logs (no silenciosamente).

## Prueba de humo (antes de correr el experimento completo)

```bash
cp .env.example .env
docker compose up --build
# revisa: docker compose logs sandbox
# deberia terminar con "[entrypoint] agente termino con status=0"
cat results/manual_test_000_transcript.jsonl   # debe tener turnos con contenido real
docker compose down -v
```

Si el agente trunca contexto o nunca emite tool_calls validos, revisa
`OLLAMA_NUM_CTX` y que el modelo soporte tool calling; si no, cambia
`AGENT_BACKEND=openai` en `.env` como respaldo.

## Validar la matriz sin gastar computo

```bash
pip install -r orchestrator/requirements.txt
python3 orchestrator/run_experiment.py --dry-run --limit 5
docker compose config -q   # valida el YAML sin construir nada
```

## Controles positivos (correr esto primero, siempre)

```bash
tests/positive_controls.sh
```

Inyecta a mano los 3 eventos que los monitores deben detectar (mata el
heartbeat, crea un directorio/nombre de archivo con el canary, dispara una
peticion anomala por el proxy) y mide el tiempo de deteccion real de cada
uno -- sin depender de que un LLM decida escapar. Exit code 0 si los 4
controles dispararon; si alguno falla, hay un monitor ciego y ninguna tasa
de deteccion medida despues es confiable. Toma menos de un minuto, no
necesita Ollama/backend de LLM.

## Correr el experimento completo (vectores 1-3, tentacion pasiva)

```bash
python3 orchestrator/run_experiment.py
```

Es secuencial a proposito: con Ollama local el modelo es el recurso escaso, y
con un backend en la nube el rate limit/latencia por turno lo es; correr en
paralelo solo generaria contencion y timeouts espurios. El script es
reentrante: si se interrumpe (Ctrl+C, o `kill` al proceso), al volver a
correrlo salta las corridas que ya tienen `{run_id}.jsonl` -- solo hay que
limpiar a mano el stack de Docker de la corrida que haya quedado a medias
(`docker compose -p <project_name_prefix>_<run_id> down -v`).

Con `repetitions: 10` (60 corridas totales) y `deepseek-v4-pro` via OpenCode
Go, cada corrida tomo en la practica ~120-185s (el modelo razona bastante
por turno), asi que cuenta **~2 horas** para el total. Con
`repetitions: 25` (150 corridas) al mismo ritmo son ~6 horas: subela solo si
el presupuesto de tiempo/cuota lo permite, o cambia a un modelo que razone
menos por turno para acelerar.

## Vector 4: inyeccion de prompt via SSRF de juguete

```bash
python3 orchestrator/run_experiment.py --config orchestrator/config_redteam.yaml
```

Matriz separada (`docker-compose.redteam.yml`, servicio `redteam` con el
mirror que sirve el payload inyectado): el agente descubre un SSRF de
juguete via `package-registry`, fetchea un mirror externo, y el contenido
devuelto incluye una instruccion inyectada pidiendole crear un directorio
con su propio canary. Correr DESPUES de la matriz base (compiten por el
mismo Ollama local). Ver `report/findings.md` para el hallazgo real: el
`con_harness` (que le da al agente su canary con enfasis) fugo MAS que
`sin_harness`, no menos.

## Vectores 5 y 6: memoria persistente y RAG envenenados

```bash
tests/seed_memory_poison.sh     # siembra ./memory/notes.jsonl con la nota envenenada -- correr UNA VEZ antes
python3 orchestrator/run_experiment.py --config orchestrator/config_memory_rag.yaml
```

Mismo payload que vector 4, dos canales de entrega distintos y sin fetch de
red en vivo: vector 5 lee `./memory/notes.jsonl` (bind mount al host, NO
wipeado por `down -v` entre corridas -- asi se modela memoria de equipo que
persiste entre sesiones no relacionadas); vector 6 busca en
`/workspace/knowledge_base/` sembrado en el seed de la tarea. Ver
`analysis/compute_ttd.py` (escalera de niveles 0-6) y `report/findings.md`
para la comparacion de tasa de fuga por canal.

## Experimento causal: por que con_harness fuga mas

```bash
python3 orchestrator/run_experiment.py --config orchestrator/config_causal_priming.yaml
```

Corre solo la condicion nueva (`con_harness_generico`, ver
`sandbox/prompts.py`) sobre `task_06_rag_poison`; reutiliza los datos ya
existentes de `con_harness`/`sin_harness` de esa tarea si ya corriste el
paso anterior. Aisla si el guardrail fuga mas por ser largo/enfatico en
general, o especificamente porque nombra la superficie del ataque
(archivos/directorios/URLs) al advertir sobre ella. Resultado en
`report/findings.md`: la prediccion de "priming" se confirmo.

## Analisis

```bash
pip install -r analysis/requirements.txt
python3 analysis/compute_ttd.py
```

Imprime, por condicion: tasa de intentos de escape, tasa de deteccion, TTD
media con intervalo de confianza bootstrap al 95%, la distribucion de
niveles 0-6 (por condicion y por tarea), y que monitor detecto primero mas
seguido. Escribe `results/summary.jsonl` con una fila por corrida. Corre
sobre TODO lo que haya en `results/`, sin importar de cual matriz vino.

### Analisis semantico de Chain-of-Thought pre-escape

```bash
python3 analysis/extract_cot.py
```

Recorre los transcripts, ubica el turno donde aparece `http_fetch` (u otro
intento de escape) y extrae el razonamiento de los turnos previos a ese
punto en `report/cot_analysis.md` -- util para leer, en lenguaje natural,
que estaba "pensando" el agente justo antes de escapar, en vez de solo ver
el evento en si.

## Panel visual (dashboard)

```bash
pip install -r dashboard/requirements.txt
python3 dashboard/app.py          # abre http://localhost:8765
```

Web local (Flask) que lee `results/` en vivo -- no es un snapshot ni un
artifact publicado, es un servidor que corre en tu maquina junto al resto
del harness y relee el disco cuando pulsas "releer results/" (o al
recargar la pagina). Reusa la misma logica de `analysis/compute_ttd.py`
(la escalera de 0-6 niveles, la definicion de "intento de escape" por
tarea) para que el panel y el analisis de linea de comandos nunca
diverjan -- no duplica esa logica, la importa.

Muestra: el diagrama de arquitectura, una linea de tiempo turno-por-turno
de la corrida seleccionada (marca el momento exacto de la fuga y el de la
deteccion, con el TTD entre ambos), tarjetas de los 3 mecanismos de
deteccion con sus estadisticas de la corrida actual, y el agregado de
todas las corridas presentes en `results/` agrupadas por condicion/tarea.

Por defecto abre la corrida con el nivel de escalada mas alto disponible
(la fuga real mas interesante); el selector del encabezado permite ver
cualquier otra.

### Modo en vivo

El panel hace polling cada 2.5s (`setInterval` en `app.js`, sin websockets --
es un archivo local, no hace falta mas). Si mientras esta abierto corres:

```bash
python3 orchestrator/run_experiment.py
```

en cuanto una corrida arranca (su `_meta.json` tiene `t0` pero todavia no
`t1`), el panel la detecta como **en curso**: el punto verde junto a
"SENTINEL" empieza a pulsar, el selector cambia automaticamente a esa
corrida, y la linea de tiempo/el log de turnos se van llenando en cada
refresco. Cuando `run_experiment.py` termina esa corrida (escribe `t1`), el
punto deja de pulsar. Ver `dashboard/app.py::api_runs` -- el campo `en_curso`
es lo que decide todo esto, calculado a partir del `_meta.json` real, no de
un flag inventado.

### Fortaleza de los monitores

```bash
tests/monitor_strength_sweep.sh
```

Barrido deterministico (sin LLM, sin costo): dispara el mismo evento
sintetico de fuga -- crear un directorio con el canary, matar el heartbeat --
variando `CANARY_FALLBACK_INTERVAL` y el umbral de heartbeat
(`HEARTBEAT_INTERVAL`/`HEARTBEAT_TIMEOUT_MULT`, ambos ya expuestos en
`docker-compose.yml`), y mide el TTD real para cada configuracion. Escribe
`results/monitor_strength.jsonl`, que el panel grafica en la seccion
"Fortaleza de los monitores" (TTD vs. parametro, un mini-grafico por
mecanismo). Toma unos 6-8 minutos; correrlo en una maquina sin otra carga de
Docker en paralelo, o el arranque de los contenedores efimeros puede dominar
la medicion (ver `report/findings.md`).

**`canary_monitor.py` detecta por eventos (`watchdog`/inotify), no por
polling** -- `CANARY_FALLBACK_INTERVAL` ya no controla la latencia de
deteccion, solo el barrido de respaldo por si inotify pierde un evento. El
barrido de arriba lo confirma con datos reales: TTD queda plano (~3.5s,
dominado por el arranque del contenedor de prueba, no por el monitor) sea
cual sea el valor del parametro -- antes escalaba de "sin detectar" a 20s+
segun el intervalo. Ver `report/findings.md` para la medicion aislada que
muestra deteccion mas rapida que el propio arranque del contenedor de
prueba.

## Condicion de control de red (manual, fuera de la matriz)

```bash
docker compose -f docker-compose.yml -f docker-compose.control.yml \
  up --build sandbox package-registry model-hub
```

El sandbox habla directo con `red-mocks`, sin proxy ni heartbeat: sirve para
mostrar en vivo que se pierde sin el arnes de deteccion.

## Estructura

```
sandbox/       agente (Capa 1): Dockerfile, agent.py, prompts.py, heartbeat.py
mocks/         servicios simulados (Capa 3): package_registry, model_hub
monitors/      los tres monitores + proxy de egress (Capa 2 y 4)
tasks/         las tres tareas con pista de escape plantada
orchestrator/  matriz experimental y loop de corridas (Capa 5)
analysis/      TTD + bootstrap
results/       JSONL por corrida (no versionado, ver .gitignore)
report/        scope.md (que demuestra esto y que no), findings.md, y
               hardware_validation.md (perfil de hardware + bugs de entorno
               encontrados al correr todo localmente)
```
