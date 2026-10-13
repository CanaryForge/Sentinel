# Formación profesional

Qué demuestra este proyecto en términos de competencias. Cada una lleva su evidencia
en el repositorio. Es un trabajo de equipo (ver [`PARTICIPACIONES.md`](PARTICIPACIONES.md)):
las competencias marcadas **(propia)** corresponden a trabajo hecho por Sofia
Rodriguez Chaparro (@Sofiro11), y las demás a lo que el proyecto demuestra como conjunto.

> Los campos `[POR COMPLETAR: …]` son espacios para datos que el historial no contiene.
> No se inventó ninguna métrica de impacto.

## Competencias

### 1. Seguridad de agentes de IA y respuesta a incidentes
- Modelo de amenaza anclado en un incidente real (SSRF + comunicación por nombres de
  directorio) y en la taxonomía OWASP Top 10 for Agentic Applications (ASI06):
  `report/scope.md`.
- Seis vectores de escape con pistas plantadas, sin exploits genéricos y sin tocar
  internet real (`tasks/`, `mocks/`, redes `internal: true` en `docker-compose.yml`).

### 2. Diseño experimental y rigor estadístico
- Matriz condición × tarea × repetición, reentrante (`orchestrator/run_experiment.py`).
- TTD con intervalos de confianza por bootstrap (`analysis/compute_ttd.py`).
- Hipótesis registrada antes de los datos y luego falsificada; los hallazgos sin
  sustento se retractaron en vez de acomodarse (`report/findings.md`, sección del
  experimento causal).
- **(propia)** Identificar y aislar 35 de 100 corridas inválidas en la máquina D,
  medir la causa (timeout de 120 s contra 115 s de evaluación del primer turno) y
  confirmar que era reproducible (`results/machine-D/*-invalidas-timeout/`,
  `report/findings.md` § Machine-D).

### 3. Reproducibilidad entre plataformas
- **(propia)** Validación independiente en Windows-on-ARM, con el mismo modelo y
  digest que las demás máquinas para descartar confusores
  (`report/hardware_validation.md`).
- **(propia)** Portabilidad a Windows: `.gitattributes` (LF obligatorio en scripts y
  Dockerfiles), codificación UTF-8 explícita en `analysis/compute_ttd.py`, y
  `MSYS_NO_PATHCONV` en `tests/*.sh`.

### 4. Infraestructura con contenedores y observabilidad
- Docker Compose con redes aisladas, `cap_drop: [ALL]` y overlays por vector
  (`docker-compose*.yml`).
- Monitores independientes del modelo con un bus de eventos común
  (`monitors/event_bus.py`); detección por eventos con inotify
  (`monitors/canary_monitor.py`); proxy de egress con mitmproxy
  (`monitors/egress_monitor.py`).

### 5. Automatización y pruebas funcionales
- Controles positivos que inyectan los eventos a mano y verifican la detección sin
  gastar cuota de LLM (`tests/positive_controls.sh`).
- **(propia)** Cadena reentrante de las seis matrices (`tests/run_full_matrix.sh`).

### 6. Comunicación técnica
- Paper en LaTeX con formato IEEE (`docs/`) y página pública (`site/`).
- **(propia)** Redacción y corrección de secciones del paper (resultados, fallos
  silenciosos, reproducibilidad) y de `report/findings.md`; `CLAUDE.md` como guía
  operativa del repositorio.

## Retos y aprendizajes

| Reto | Qué se aprendió |
|---|---|
| CRLF rompía los scripts dentro de los contenedores Linux al clonar en Windows (`env: 'bash\r'`, exit 127) | Fijar los finales de línea por tipo de archivo en `.gitattributes`, no depender de `core.autocrlf` |
| Git Bash reescribía rutas como `/app/x.py` a rutas de Windows antes de llegar al contenedor | `MSYS_NO_PATHCONV=1`: el problema era del shell del host, no del proyecto |
| En hardware ARM, un tercio de las corridas "terminaba bien" (exit 0) sin hacer nada | Un exit code limpio no prueba una corrida válida; hay que verificar que hubo tool calls reales |
| El heartbeat se atribuía detecciones que no hizo (alerta de silencio al apagar) | Separar el apagado limpio de la detección usando `docker_exit_code` |
| La hipótesis causal registrada no se sostuvo con n=30 | Reportar el resultado nulo es parte del método, no un fracaso |
| [POR COMPLETAR: otro reto personal] | [POR COMPLETAR] |

## Impacto (por completar)

- Selección o resultado en el sprint: [POR COMPLETAR]
- Recepción del paper (envío, aceptación, citas): [POR COMPLETAR]
- Visitas a la página o uso del arnés por terceros: [POR COMPLETAR]
- Horas dedicadas por mí al proyecto: [POR COMPLETAR]
