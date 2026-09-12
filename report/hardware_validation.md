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

## 3. Bug ambiental sin resolver: `docker compose run` cuelga indefinidamente

Este es el hallazgo más importante y menos cómodo de esta validación: en un
punto de la sesión (no está claro exactamente cuándo empezó), **`docker
compose run` para las imágenes de este proyecto empezó a colgarse
indefinidamente**, reproducible en `tests/positive_controls.sh` (control 2
en adelante) y en pruebas aisladas manuales, siempre en el mismo punto: el
contenedor efímero llega a `Created` y nunca pasa a `Starting`.

### Lo que se descartó, con evidencia, no por intuición

Se probó cada hipótesis razonable, una por una:

| Hipótesis | Prueba | Resultado |
|---|---|---|
| Asignación de pseudo-TTY | `docker compose run -T ...` | Sigue colgado |
| `cap_drop: [ALL]` + `security_opt` | Reproducido con y sin esas opciones en un compose mínimo | No es la causa (funciona con ellas en un proyecto de prueba) |
| Red `internal: true` | Compose mínimo de 2 servicios, uno en red interna, uno en red normal | Ambos funcionan bien (4-5s) |
| Override de `--entrypoint` | Probado con y sin override, mismo resultado | No es la causa |
| La imagen en sí | `docker run` puro (sin compose) con la misma imagen exacta | **Funciona perfecto, 4.4-4.6s**, siempre |
| Degradación del daemon tras ~5h de sesión | `sudo systemctl restart docker` | Sigue colgado exactamente igual |
| Sesión de BuildKit trabada en containerd (18h sin reiniciar) | `sudo systemctl restart containerd docker` | Sigue colgado exactamente igual |

**Lo que sí se encontró**: los logs de `dockerd` (`journalctl -u docker`)
muestran, repetidamente y de forma recurrente (incluso ~1 minuto después de
un reinicio limpio de containerd+docker), este error:

```
level=error msg="healthcheck failed fatally" error="session healthcheck
failed fatally: Unavailable: connection error: desc = \"transport: Error
while dialing: only one connection allowed\""
```

Es un error del mecanismo de sesión de BuildKit (usado para sincronizar el
contexto de build local). Que reaparezca minutos después de un reinicio
limpio de ambos servicios descarta que sea estado acumulado del daemon --
algo en el entorno de esta sesión especifica lo sigue disparando, pero no se
identificó qué proceso exactamente (se reviso `lsof`/`/proc/*/fd` sobre
`docker.sock` sin encontrar un proceso persistente sosteniendo la conexión
conflictiva -- la conexión problematica es transitoria, solo aparece durante
el build/run mismo).

### Lo que SÍ sigue funcionando, sin excepción, durante toda la sesión

- `docker run` directo (sin compose): siempre funciono, en cualquier momento de la sesión.
- `docker compose up` (no `run`): el orquestador (`orchestrator/run_experiment.py`), el dashboard, y todas las corridas reales de agente de esta sesión usaron `up`, no `run`, y **nunca se colgaron** -- incluyendo la matriz completa de 60 corridas y las corridas del vector 4/5/6.
- El barrido `tests/monitor_strength_sweep.sh` (que también usa `docker compose run`) corrió exitosamente varias veces MÁS TEMPRANO en esta misma sesión, con resultados reales medidos (ver `report/findings.md`, seccion de watchdog). El problema con `run` parece haber aparecido en algún punto DESPUES de eso.

### Impacto práctico y recomendación

`tests/positive_controls.sh` y `tests/monitor_strength_sweep.sh` (los dos
scripts de validación determinista, sin LLM) dependen de `docker compose
run` para disparar sus eventos sintéticos. En esta máquina, en el estado
actual, **ambos quedarían bloqueados si alguien los corre ahora mismo**. El
resto del proyecto (experimentos reales, dashboard) no se ve afectado
porque usa `up`, no `run`.

**No se probó un reinicio completo del sistema operativo** (solo se
reiniciaron los servicios `docker` y `containerd` individualmente, dos
veces, sin éxito) -- es el siguiente paso obvio si alguien del equipo se
topa con este mismo síntoma, y no se descarta que sea la solución real dado
que ambos reinicios de servicio fallaron por igual.

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
compose up`, el orquestador, el dashboard), encontró y arregló un bug real
de costo (`positive_controls.sh` gastando cuota de LLM sin necesidad), y
encontró -- sin lograr cerrar la causa raíz -- un problema ambiental
especifico de `docker compose run` en esta máquina que no aparecía antes en
la misma sesión y que sobrevivió a dos reinicios de servicio. Se documenta
tal cual en vez de forzar una conclusión limpia que los datos no sostienen.
