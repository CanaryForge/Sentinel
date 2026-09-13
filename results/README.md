# results/

Datos crudos de las corridas. **Organizados por maquina, no por experimento.**

## Por que por maquina

Porque es lo que decide si dos conjuntos se pueden comparar. Dos corridas del
mismo experimento en maquinas con versiones distintas de Ollama **no son
comparables**: con 0.6.8 el agente entra en bucle y agota el tope de 15 turnos,
con 0.32.5 y 0.34.0 converge en 6. Esa diferencia hizo desaparecer el hallazgo
principal del proyecto durante un dia entero (ver `report/findings.md`).

Antes esto estaba organizado por experimento (`corpus/`, `causal/`,
`redteam/`), y la procedencia no se veia por ningun lado.

## Estructura

```
machine-A/                       Daniel, Ollama 0.32.5
  manifest.json
  corpus/                        63 corridas, tareas 04, 05 y 06
machine-B/                       Sergio, Windows
  manifest.json
  causal-ollama0.6.8/            30 corridas, task_06, SIN poder estadistico
  redteam-ollama0.6.8/           20 corridas, task_04
  causal-ollama0.34.0/           30 corridas, task_06, el experimento valido
controles/                       artefactos de las pruebas (no versionado)
```

La version de Ollama va en el nombre del directorio cuando una misma maquina
produjo conjuntos con versiones distintas. El `manifest.json` de cada maquina
lleva el hardware, el modelo, el digest y las advertencias que apliquen.

## Donde meter corridas nuevas

**Un conjunto nuevo va en su propio directorio, nunca mezclado con uno
existente.** El orquestador no sobrescribe: salta las corridas que ya tienen
resultados, asi que apuntar a un directorio poblado produce una mezcla
silenciosa de dos configuraciones.

Si Daniel corre mas pruebas:

- **Misma maquina, misma version de Ollama, experimento nuevo**:
  `machine-A/<experimento>/`.
- **Misma maquina, version distinta**: renombrar primero `machine-A/corpus/` a
  `machine-A/corpus-ollama0.32.5/` para que las dos versiones queden
  explicitas, y crear `machine-A/<experimento>-ollama<version>/`.
- **Maquina nueva**: `machine-C/` con su `manifest.json`.

```bash
python3 orchestrator/run_experiment.py \
  --config orchestrator/config_redteam.yaml \
  --results-dir results/machine-A/redteam
```

Desde `6fa9c4a` cada `_meta.json` registra `ollama_version`, consultada al
servidor en el momento de la corrida, asi que las corridas nuevas ya no
dependen de que alguien se acuerde. Las de `machine-A/corpus/` son anteriores
a ese cambio y su version se recupero preguntando.

## Recomputar

```bash
python3 analysis/compute_ttd.py                                              # corpus
python3 analysis/compute_ttd.py --results-dir results/machine-B/causal-ollama0.34.0
python3 analysis/compute_ttd.py --results-dir results/machine-B/redteam-ollama0.6.8
```
