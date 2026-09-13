# Validación local: hardware, entorno, y bugs reales encontrados

> ⚠ **Este documento NO describe la máquina que produjo los datos.**
> Perfila la máquina de Juan Esteban, que **no tiene Ollama instalado** y por
> lo tanto no generó ninguna de las 63 corridas de `results/`. Esas salieron
> de la máquina de Daniel. El título y la ubicación en `report/` invitan a
> asumir lo contrario, así que conviene leer primero la tabla de abajo.

Corrido en la máquina de Juan Esteban (`cachyos-x8664`), 2026-09-12. Objetivo:
validar que el harness funciona en un entorno real y documentar en qué
medida sus resultados (timing, TTD, hangs) dependen del hardware específico
donde corre.

## Qué máquina produjo qué

| Máquina | Produjo | Perfilada aquí |
|---|---|---|
| **Daniel** (Mac, Apple Silicon) | `results/` -- las **63 corridas** del corpus, sobre las que descansa cada cifra de `findings.md` | Parcial, abajo |
| **Juan Esteban** (`cachyos-x8664`) | ninguna corrida con LLM (sin Ollama); sí la validación de entorno y los arreglos de `positive_controls.sh` | Sí, abajo |
| **Sergio** (Windows 11) | `results/machine-B/causal-ollama0.6.8/` -- las 30 corridas del experimento causal homogéneo | Sí, abajo |
| **Sofiro11** (Windows 11 ARM64) | `results/machine-C/corpus/` -- 60 corridas, vector 4 completo + vectores 5/6 | Sí, abajo |

**El hueco de la primera fila sigue medio abierto.** El corpus no registra en
ningún artefacto con qué se corrió: el modelo (`qwen2.5:7b-instruct`) aparece
solo como prosa en `findings.md`, y la versión de Ollama y el contexto
efectivo no están en ninguna parte. El hardware ya lo confirmó Daniel de viva
voz (perfil abajo); los dos datos que faltan los pasa después. Eso importa porque el comportamiento del agente **no es el mismo entre
instalaciones**: con el mismo modelo y el mismo digest, en la máquina de
Sergio 11 de 30 corridas agotaron el tope de 15 turnos y ninguna de las 23 de
Daniel lo hizo (ver `findings.md`, experimento causal). El Hallazgo 2 no
replica fuera de la máquina de Daniel, y sin sus metadatos no se puede
explicar por qué.

Para cerrarlo hacen falta dos datos de Daniel:

```bash
ollama --version
echo $OLLAMA_CONTEXT_LENGTH   # vacío = el default de Ollama
```

Desde `a292051`, `orchestrator/run_experiment.py` escribe un bloque
`backend` en cada `{run_id}_meta.json`, así que ninguna corrida futura vuelve
a quedar sin procedencia. Las 63 del corpus son anteriores a ese cambio.

## Perfil de hardware -- Daniel (produjo el corpus de 63 corridas)

| | |
|---|---|
| Equipo | Mac, Apple Silicon **M5 Pro** |
| RAM | **24 GB** unificada |
| Modelo | `qwen2.5:7b-instruct`, digest `845dbda0ea48` (confirmado contra el tag) |
| Ollama | **0.32.5** |
| `OLLAMA_CONTEXT_LENGTH` | sin fijar (default de su version) |

Reportado verbalmente por Daniel, no leído de un artefacto: queda anotado como
lo que es.

**Con la version confirmada, la diferencia entre maquinas deja de ser un
misterio.** Ollama numera `0.MINOR.PATCH` y su minor pasó de un digito hace
tiempo, asi que **0.32.5 no es anterior a 0.6.8: son 26 versiones menores de
diferencia, y la maquina B es la vieja.** Lo confirma el propio updater de esa
maquina, que tiene descargado el instalador de la v0.34.0.

Ninguno de los dos fijo `OLLAMA_CONTEXT_LENGTH`, asi que cada uno corrio con
el default de su version. La maquina B reporta 4096 en su arranque; el default
de 0.32.5 no se midio aqui.

Entre esas dos versiones cambian la plantilla de chat, el manejo de tool calls,
los parametros de sampling por defecto y el contexto por defecto: exactamente
el conjunto que explicaria por que los agentes de la maquina B iteran hasta el
tope de 15 turnos (11 de 30 corridas) y los de la maquina A convergen con una
mediana de 4 turnos y nunca lo tocan (0 de 23).

**Esto es una hipotesis con un mecanismo plausible, no una causa demostrada.**
El test que la cierra es barato y esta pendiente: actualizar Ollama en la
maquina B a una version comparable y repetir `task_06`. Si los agentes pasan a
converger y `sin_harness` baja del techo, la no replicacion del Hallazgo 2 pasa
de ser un resultado inexplicado a ser un artefacto de version del runtime, que
es una limitacion muy distinta de reportar.

Lo que tambien se puede afirmar, y es independiente de la version: **24 GB de memoria unificada y GPU de Apple
Silicon no son un equipo limitado para un modelo de 7B**, así que la
divergencia de comportamiento entre su máquina y la de Sergio --mediana de 4
turnos frente a 14, y 0 de 23 corridas agotando el tope frente a 11 de 30--
**no se explica por falta de recursos en ninguno de los dos lados**. La causa
probable sigue siendo el stack de inferencia (versión de Ollama o contexto
efectivo), no el hardware.

## Perfil de hardware -- Sergio (produjo `results/machine-B/causal-ollama0.6.8/`)

| | |
|---|---|
| CPU | Intel Core i7-14700K |
| RAM | 31.8 GB |
| GPU | NVIDIA GeForce RTX 3060 (el modelo carga 100% en GPU) |
| SO | Windows 11 Pro 10.0.26200 |
| Docker | 29.7.2 |
| Ollama | 0.6.8 (cliente y servidor), `OLLAMA_CONTEXT_LENGTH` sin fijar → **4096** |
| Modelo | `qwen2.5:7b-instruct`, digest `845dbda0ea48` |

Dato relevante medido aquí: el endpoint OpenAI-compatible de Ollama
**ignora en silencio `options.num_ctx`**, así que el contexto real es siempre
el default del servidor sin importar lo que diga `OLLAMA_NUM_CTX` -- variable
que además `sandbox/agent.py` nunca envía. Se comprobó levantando un segundo
servidor con `OLLAMA_CONTEXT_LENGTH=16384` (KV cache de 7.0 GB frente a
6.0 GB), y el comportamiento de bucle **no cambió**: el truncamiento de
contexto queda descartado como causa de la divergencia entre máquinas.

## Perfil de hardware -- Juan Esteban (no produjo corridas con LLM)

| | |
|---|---|
| CPU | AMD Ryzen 3 3250U, 2 núcleos / 4 hilos, hasta 3.5GHz |
| RAM | 5.7GB total |
| Storage driver Docker | overlayfs |
| Kernel | Linux 7.2.2-1-cachyos (CachyOS) |
| Docker | 29.7.2 / Compose 5.5.0, `containerd-snapshotter=true` |
| inotify | `max_user_watches=524288`, `max_user_instances=1024` (default, no es limitante) |
| Ollama | no instalado |

**Este es un equipo de gama baja para lo que el proyecto le pide.** 4 hilos y
5.7GB de RAM es notablemente menos que lo que suele asumirse para "un
laptop" en el enunciado original, y esto tiene consecuencias medibles, no
solo teóricas (ver abajo). Con Chrome + el resto del sistema abierto, la
máquina llegó a estar en **swap activo (525MB)** y **22% de I/O wait** en
reposo durante esta sesión -- bajo esa presión, cualquier medición de
latencia que involucre arrancar contenedores queda inflada por overhead de
sistema, no solo por lo que el harness mismo hace.

## 1. Build limpio (sin cache)

`docker compose -f docker-compose.yml -f docker-compose.redteam.yml build --no-cache`
para las 6 imágenes: **3 minutos 5 segundos**. La mayor parte es espera de
red/IO (pip install, pull de `python:3.11-slim`), no CPU -- consistente con
el diagnóstico de I/O wait de arriba.

## 2. Bug real encontrado y arreglado: `positive_controls.sh` gastaba cuota de LLM

`tests/positive_controls.sh` dice explícitamente en su propio comentario que
"no depende de que un backend de LLM esté disponible" -- pero su `up -d
egress-proxy fs-monitor package-registry model-hub` (sin `--no-deps`)
arrastraba a `sandbox` como dependencia implícita de `fs-monitor`
(`depends_on: [sandbox]` en `docker-compose.yml`), lanzando un **agente real
contra el backend configurado en `.env`** en cada corrida.

Confirmado con datos, no en teoría: 4 corridas de este script durante la
sesión generaron 4 transcripts reales (~12 turnos cada uno) contra la API de
pago de OpenCode Go -- ~48 llamadas reales, cero valor experimental (todas
corrían `task_01_impossible` repetidamente), exactamente lo que el diseño
del script decía evitar. Los transcripts basura se borraron de `results/`.

**Fix aplicado** (`tests/positive_controls.sh`): se agregó `--no-deps` a ese
`up -d`. Verificado: tras el fix, el control 1 (heartbeat) corrió limpio,
**sin ningún transcript nuevo generado** -- confirmado que ya no toca el LLM.

## 3. Falsa alarma resuelta: `docker compose run` "colgado" era el entorno de ejecucion del asistente, no el proyecto

> **Matiz añadido después (Windows).** La conclusión de esta sección es
> correcta para el síntoma que describe --un cuelgue indefinido en Linux, con
> el ciclo detenido entre `attach` y `start`-- pero **no generaliza**: en
> Windows con Git Bash hay un fallo distinto y real del proyecto en el mismo
> comando. MSYS reescribe cualquier argumento con pinta de ruta POSIX antes de
> pasárselo a `docker.exe`, así que `docker compose run ... python3
> /app/heartbeat.py` llega al contenedor como
> `/app/C:/Program Files/Git/app/heartbeat.py`, sale con código 2 al instante
> y `--rm` borra el contenedor antes de que quede rastro. Síntoma: los 4 casos
> de heartbeat del barrido dan `SIN DETECTAR` y no se crea ningún
> `results/mstr_heartbeat_*.jsonl`. Corregido con `MSYS_NO_PATHCONV=1` en los
> dos scripts de prueba (`45fd1e7`).
>
> Son dos modos de fallo distintos sobre la misma línea: uno del entorno
> (Linux, cuelgue) y otro del proyecto (Windows, exit 2). Tal como estaba
> redactado, este apartado le decía al siguiente que no investigara.


Durante esta validación, `docker compose run` (usado por `tests/
positive_controls.sh` y `tests/monitor_strength_sweep.sh` para disparar sus
eventos sintéticos) empezó a colgarse indefinidamente en todas las
invocaciones hechas *por el asistente* -- el contenedor efímero llegaba a
`Created`/`attach` y nunca a `start`. Se descartaron uno por uno, con
pruebas aisladas: asignación de TTY, `cap_drop`/`security_opt`, la red
`internal: true`, el override de `--entrypoint`, la imagen en sí (`docker
run` puro siempre funcionó, 4.4-4.6s), y estado del daemon (sobrevivió a
reiniciar `docker` y `containerd`, dos veces cada uno). `docker events -f`
en vivo durante el cuelgue mostró la causa exacta: el ciclo se detiene justo
después del evento `container attach`, antes de que exista un evento
`start` -- `docker compose run` hace `attach` a los streams del contenedor
*antes* de arrancarlo (para transmitir su salida en vivo), a diferencia de
`docker run`/`up`.

**Prueba decisiva**: se le pidió al usuario correr el mismo script
(`tests/positive_controls.sh`) directamente en su propia terminal, fuera del
asistente. **Corrió limpio, sin colgarse.**

Esto confirma que el cuelgue era un artefacto del entorno de ejecución
sandboxed del asistente (sin una terminal/TTY real, con stdin/stdout
conectados de forma distinta a como los conecta una shell interactiva
normal) interactuando mal con el protocolo `attach`-antes-de-`start` que usa
específicamente `docker compose run` -- **no un bug del proyecto, no un
problema de esta máquina, y no algo roto por ninguno de los cambios hechos
en esta sesión.** `docker compose up` (usado por el orquestador, el
dashboard, y las 60+ corridas reales de agente) nunca se vio afectado
porque no usa ese mismo protocolo de arranque.

**Conclusión práctica**: `tests/positive_controls.sh` y `tests/
monitor_strength_sweep.sh` funcionan correctamente en esta máquina cuando se
corren desde una terminal real. Si el asistente necesita correrlos de nuevo
en una sesión futura, debe asumir que un cuelgue en `docker compose run`
específicamente probablemente sea de su propio entorno de ejecución, y
pedirle al usuario que lo verifique en su propia terminal antes de asumir un
bug real -- exactamente el paso que resolvió esto aquí.

### Resultado final, corrido por el usuario en su propia terminal (2026-09-12)

```
[1/4] Heartbeat                -> OK, detectado en 9.385s
[2/4] Canary (filesystem)      -> OK, detectado en 3.437s
[3/4] Canary (red)             -> OK, detectado en 3.488s
[4/4] Egress baseline          -> OK, marcado anomalo en 3.579s

== Los 4 controles dispararon. Los monitores no estan ciegos. ==
```

Los 4 controles deterministas pasan limpio. El control 2 (canary de
filesystem, ~3.4s) es consistente con la validación de `watchdog` de la
sección 4 -- confirma en un entorno real, no solo en pruebas aisladas del
asistente, que la detección por inotify funciona de punta a punta.

## 4. Validación de `watchdog` (deteccion por eventos) -- resultados de esta sesión, aún válidos

Ver `report/findings.md` para el detalle completo. Resumen: `canary_monitor.py`
detecta ahora por inotify en vez de polling; una medición aislada mostró el
evento de detección con timestamp *anterior* al momento en que el contenedor
de prueba efímero terminaba de cerrarse. Esta validación se hizo ANTES de que
apareciera el problema de `docker compose run` documentado arriba, así que
sus números siguen siendo válidos y no están afectados por el hang.

## Perfil de hardware -- Sofiro11 (produjo `results/machine-C/corpus/`)

Cuarta maquina del proyecto, primera en Windows-on-ARM. **No es la primera
ARM64** -- la de Daniel (Apple Silicon M5 Pro) tambien lo es -- lo que la
distingue es el SoC (Qualcomm Oryon vs Apple Silicon) y sobre todo el
sistema operativo: Windows + Docker Desktop (WSL2) en vez de macOS, lo que
implica un build de Ollama/llama.cpp completamente distinto al de Daniel
aunque ambos sean ARM64. Corrida completa de vector 4 (20 corridas) y
vectores 5/6 (40 corridas) sobre este hardware, Ollama 0.34.0 (misma
version que la corrida valida de Sergio, asi que el confusor de version ya
conocido en este proyecto -- ver seccion de arriba -- no aplica aqui).

| | |
|---|---|
| CPU | Qualcomm Snapdragon X Plus (X1P42100, Oryon), 8 nucleos/8 hilos, ARM64 |
| RAM | 15.6GB total |
| OS | Windows 11 Home |
| Docker | 29.7.2 / Compose 5.5.1 (Docker Desktop, instalado per-user) |
| Ollama | 0.34.0 |
| Modelo | `qwen2.5:7b-instruct`, digest `845dbda0ea48` (mismo digest que Daniel y Sergio) |

**Bugs de portabilidad Windows encontrados en esta maquina** (no
relacionados al ARM64 en si, son de Windows/Git Bash en general --
documentados en detalle en `.kiro/steering/comandos.md` para que Kiro/Claude
no los repitan): `docker.exe` fuera de PATH (instalacion per-user de Docker
Desktop), CRLF en `monitors/entrypoint.sh` (rompia `egress-proxy` con exit
127, silencioso), MSYS reescribiendo argumentos de ruta absoluta en
`docker compose run`, y `analysis/compute_ttd.py` sin `encoding="utf-8"`
explicito (cp1252 por default en Windows). Los primeros tres eran nuevos
hasta esta sesion; el `.gitattributes` agregado deberia prevenir que el de
CRLF reaparezca en cualquier maquina Windows futura, no solo esta.

**Resultados de esta corrida**: ver `report/findings.md`, seccion "Tercera
maquina (machine-C, Windows ARM64, 2026-09-13)" -- se reportan como dataset
propio, comparado contra machine-A (Daniel) y machine-B (Sergio, lote
valido de 0.34.0), no como intento de replicar ni invalidar ninguna de las
dos. Con la version de Ollama y el modelo controlados contra el dato de
Sergio, la diferencia observada en task_05/06 no se explica por el
confusor de version ya conocido -- queda como pregunta abierta, no como
error atribuido a ninguna maquina.

## Conclusión honesta

Esta sesión de validación confirmó que el proyecto corre correctamente en
hardware modesto (4 hilos, 5.7GB RAM) para su flujo principal (`docker
compose up`, el orquestador, el dashboard, `docker compose run` desde una
terminal real), encontró y arregló un bug real de costo
(`positive_controls.sh` gastando cuota de LLM sin necesidad), y descartó una
falsa alarma (el cuelgue de `docker compose run` era del entorno de
ejecución del asistente, no del proyecto ni de esta máquina, confirmado
haciendo que el usuario corriera el mismo comando en su propia terminal).
Ambos procesos -- diagnosticar a fondo antes de concluir, y verificar contra
una ejecución independiente del usuario antes de aceptar la propia
conclusión -- son el punto central de este reporte, no solo los resultados.
