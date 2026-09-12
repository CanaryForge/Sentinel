# Validación local: hardware, entorno, y bugs reales encontrados

Corrido en la máquina de Juan Esteban (`cachyos-x8664`), 2026-09-12. Objetivo:
validar que el harness funciona en un entorno real y documentar en qué
medida sus resultados (timing, TTD, hangs) dependen del hardware específico
donde corre -- relevante porque el equipo ha corrido esto en al menos 3
máquinas distintas (esta, la de Daniel con Ollama local, y presumiblemente
la de Angie) con resultados de timing muy distintos.

## Perfil de hardware

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
