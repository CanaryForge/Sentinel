# Participaciones

Proyecto de equipo hecho durante el AI Incident Response Sprint (Apart Research /
CeSIA), del 2026-09-12 al 2026-09-14. El repositorio canónico es
[CanaryForge/Sentinel](https://github.com/CanaryForge/Sentinel); este fork conserva el
historial completo, así que cada afirmación de esta página se puede verificar con
`git log --author=<nombre>`.

## Método

- Cifras sacadas del historial de git (todas las ramas, sin commits de merge).
- "Líneas de código y docs" excluye los datos de corridas (`results/`,
  `results_causal/`, `results_redteam/`) y el andamiaje de herramientas generado
  (`.specify/`, `.claude/`). Los datos de corridas se cuentan aparte porque son
  salida del experimento, no código escrito a mano.
- Las líneas miden volumen, no valor: un commit de 6 líneas que destraba la
  ejecución en Windows puede importar más que uno de mil.

## Resumen por persona

| Persona (nombre en git) | GitHub | Commits | Fechas | Líneas de código y docs | Datos de corridas |
|---|---|---|---|---|---|
| Sergio Alejandro Castaño Arcila | [@5ergioC](https://github.com/5ergioC) | 61 | 09-12 → 09-14 | +18.967 / −5.373 | +18.228 |
| Juanesillo (Juan Esteban Triviño Nieves) | [@Juanesillo](https://github.com/Juanesillo) | 16 | 09-12 → 09-13 | +8.926 / −1.569 | — |
| Sofiro11 (Sofia Rodriguez Chaparro) | [@Sofiro11](https://github.com/Sofiro11) | 5 | 09-12 → 09-14 | +1.633 / −637 | +6.431 |
| Daniel Diab (Daniel Felipe Diab Gonzalez) | [@DanielDiab](https://github.com/DanielDiab) | 8 | 09-12 → 09-13 | +1.069 / −100 | +1.110 |
| Angie Gutierrez (Angie Camila Gutierrez Trujillo) | [@AngieGuti](https://github.com/AngieGuti) | 6 | 09-12 → 09-13 | +963 / −225 | — |

## Qué hizo cada quien

### Juanesillo — arnés base, monitores y dashboard
- Primera versión completa del arnés (2026-09-12): sandbox con agente propio de
  tool-calling, proxy de egress, mocks, tareas y orquestador.
- Corrección del falso crédito de detección del heartbeat y primera matriz real de
  60 corridas.
- Reemplazo del polling de `canary_monitor.py` por detección por eventos
  (watchdog/inotify), y barrido determinístico de fortaleza de monitores.
- Dashboard Flask: polling en vivo, luego push por SSE y rediseño en dos
  superficies (corrida en vivo y análisis del incidente).
- Validación de hardware local y runbook post-incidente.

### Sergio Alejandro Castaño Arcila — experimento causal, paper, página pública y diseño
- Experimento causal homogéneo (n=30 por celda, tres brazos), que falsificó la
  hipótesis de *priming* registrada de antemano.
- Datasets de las máquinas B y C, calibración del parser y recuperación opcional de
  tool calls escritas como texto.
- Reorganización de `results/` por máquina y versión de runtime.
- Correcciones para ejecutar en Windows (rutas de MSYS en los scripts) y otros
  defectos del arnés y del dashboard.
- Exportador de línea de tiempo forense e ingesta en OpenObserve.
- Paper completo en LaTeX (estructura, secciones, figuras TikZ, trabajo relacionado),
  página pública en Vercel y direcciones de diseño.

### Sofiro11 (Sofia Rodriguez Chaparro) — validación en Windows ARM64, redacción y documentación
- Dataset de la máquina D (Windows-on-ARM, Snapdragon X Plus): unas 100 corridas de
  los vectores 4, 5 y 6. Incluye diagnosticar que 35 eran inválidas por un timeout
  fijo más corto que la evaluación del primer turno en ese hardware (medido: 115 s)
  y aislarlas del análisis.
- Ajustes de portabilidad a Windows: `.gitattributes` para forzar LF en scripts y
  Dockerfiles (CRLF rompía el shebang dentro de los contenedores), lectura y
  escritura UTF-8 explícita en `analysis/compute_ttd.py`, y `MSYS_NO_PATHCONV`
  en los scripts de prueba.
- `tests/run_full_matrix.sh`: cadena reentrante de las seis matrices.
- `CLAUDE.md` del repositorio y sección de machine-D en `report/findings.md`.
- Redacción y corrección de secciones del paper (resultados, fallos silenciosos,
  compromiso sospechado y reproducibilidad).

### Daniel Diab — vectores 5 y 6, configs experimentales y matriz de la máquina A
- Vectores de memoria y RAG envenenados (`tasks/task_05_*`, `tasks/task_06_*` y sus
  semillas, `tests/seed_memory_poison.sh`) y los configs `config_memory_rag.yaml`,
  `config_redteam.yaml` y `config_causal_priming.yaml`.
- Cambios al agente y a los prompts (`sandbox/agent.py`, `sandbox/prompts.py`), y
  primera integración con promptfoo.
- Comandos para correr la matriz completa.
- Dataset de la máquina A (Apple Silicon), incluido completar el brazo
  `con_harness_generico`.
- Pruebas de "harness sano".

### Angie Gutierrez — análisis de razonamiento (CoT) y documentación
- Configuraciones iniciales y análisis de la cadena de razonamiento previa al
  escape (`analysis/extract_cot.py`, `report/cot_analysis.md`).
- Integración inicial de promptfoo.
- En el paper: resumen, introducción, sección del arnés y figura de arquitectura
  (`docs/figures/architecture.tex`).
