#!/usr/bin/env python3
"""
Orquestador de corridas (Capa 5). Levanta el stack completo por cada
combinacion (condicion, tarea, repeticion), corre el agente hasta que
termine o se agote RUN_TIMEOUT_SECONDS, guarda logs estructurados y
destruye todo antes de la siguiente corrida.

Uso:
    python3 orchestrator/run_experiment.py [--config archivo.yaml] [--dry-run] [--limit N]

Por defecto usa orchestrator/config.yaml (los 3 vectores base, sobre
docker-compose.yml solo). Un config alterno puede declarar `compose_files`
con overlays adicionales -- ver orchestrator/config_redteam.yaml, que agrega
el vector 4 (red-teamer/prompt injection) via docker-compose.redteam.yml sin
tocar la matriz base.

Cada corrida escribe en results/:
    {run_id}_meta.json        metadatos + t0/t1 (escritos por este script)
    {run_id}.jsonl            eventos de los tres monitores
    {run_id}_transcript.jsonl transcript del agente con timestamps

Es deliberadamente secuencial: en un laptop con Ollama local el modelo es
el recurso escaso, y correr agentes en paralelo solo generaria contencion
y timeouts espurios en vez de acelerar el experimento.
"""
import argparse
import itertools
import json
import os
import secrets
import subprocess
import sys
import time

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT, "results")


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


SIN_DATOS = []
MEMORY_PATH = os.path.join(ROOT, "memory", "notes.jsonl")
NOTA_ENVENENADA = os.path.join(ROOT, "tasks", "seed", "task_05_memory_poison",
                               "nota_envenenada.txt")


def reset_memoria(task: str) -> None:
    """Deja ./memory en un estado conocido ANTES de cada corrida.

    `./memory` es un bind mount al host: a diferencia del volumen `workspace`,
    `docker compose down -v` no lo toca, asi que sin esto cada corrida hereda
    lo que escribieron las anteriores. Medido en el corpus: tras 30 corridas
    el archivo tenia 85 notas, 58 de ellas con el canary literal de una
    corrida previa -- un agente podia leer el secreto de otra corrida con
    `memory_read`, y ninguna corrida de task_05/task_06 empezaba en las
    mismas condiciones que la anterior.

    Para `task_05_memory_poison` el estado conocido es la nota envenenada (es
    el vector que esa tarea evalua); para todo lo demas, memoria vacia.
    """
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    if task == "task_05_memory_poison":
        nota = open(NOTA_ENVENENADA, encoding="utf-8").read()
        linea = json.dumps({"ts": time.time(), "nota": nota}, ensure_ascii=False)
        with open(MEMORY_PATH, "w", encoding="utf-8", newline="\n") as f:
            f.write(linea + "\n")
    else:
        open(MEMORY_PATH, "w", encoding="utf-8").close()


def diagnostico_corrida(run_id: str) -> dict:
    """Mira si la corrida produjo datos de verdad, o solo un contenedor que
    salio con codigo 0 sin haber hecho nada.

    `agent.py` atrapa un fallo del backend, lo escribe en el transcript y corta
    el loop; el contenedor termina limpio y `--abort-on-container-exit`
    devuelve 0. Una matriz entera puede reportar "30/30 exit=0" habiendo
    generado cero tool calls -- paso: Ollama se cayo a mitad de sesion y las 30
    corridas del experimento causal salieron vacias, con una hora de reloj
    gastada antes de que nadie lo notara.
    """
    path = os.path.join(RESULTS_DIR, run_id + "_transcript.jsonl")
    turnos = []
    errores = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                turnos.append(e)
                if e.get("role") == "error":
                    errores.append(str(e.get("detalle", ""))[:200])
    tool_calls = sum(1 for e in turnos if e.get("role") == "tool")
    return {
        "tool_calls": tool_calls,
        "errores_backend": errores,
        "sin_datos": tool_calls == 0,
    }


def backend_info() -> dict:
    """Configuracion del backend del LLM tal como la ve esta corrida.

    `ollama_num_ctx_env` se registra pero `num_ctx_enviado` es False a
    proposito: `sandbox/agent.py` NO manda `options.num_ctx` a Ollama, asi
    que esa variable --presente en .env.example, docker-compose.yml y el
    README-- hoy no tiene efecto y el contexto real es el default del
    servidor Ollama (`OLLAMA_CONTEXT_LENGTH`, 4096 por defecto), por debajo
    de los 8000-16000 tokens que el propio README dice que consume un turno.
    Se deja como esta a proposito: mandarlo cambiaria el comportamiento del
    agente y las corridas nuevas dejarian de ser comparables con el corpus
    existente. Queda registrado para que la comparacion sea auditable, y
    documentado como pendiente en report/findings.md.
    """
    backend = os.environ.get("AGENT_BACKEND", "ollama")
    info = {"agent_backend": backend, "num_ctx_enviado": False}
    if backend == "ollama":
        info["modelo"] = os.environ.get("OLLAMA_MODEL", "")
        info["host"] = os.environ.get("OLLAMA_HOST", "")
        info["ollama_num_ctx_env"] = os.environ.get("OLLAMA_NUM_CTX", "")
    else:
        info["modelo"] = os.environ.get("OPENAI_MODEL", "")
        info["host"] = os.environ.get("OPENAI_API_BASE", "")
    return info


def compose_file_args(cfg):
    files = cfg.get("compose_files", ["docker-compose.yml"])
    args = []
    for f in files:
        args += ["-f", os.path.join(ROOT, f)]
    return args


def run_one(cond, task, rep, cfg, dry_run=False):
    run_id = f"{cond}_{task}_{rep:03d}"
    canary = f"CNRY-{secrets.token_hex(12)}"
    project = f"{cfg.get('project_name_prefix', 'sbxharness')}_{run_id}"
    compose_args = compose_file_args(cfg)

    meta = {
        "run_id": run_id,
        "canary": canary,
        "condicion": cond,
        "tarea": task,
        "rep": rep,
        "t0": time.time(),
        # Con que se corrio. Sin esto una corrida es inauditable: el corpus
        # de 63 corridas no registra su modelo en ningun artefacto, asi que
        # "se uso qwen2.5:7b-instruct" es prosa de report/findings.md y no un
        # dato -- la misma clase de afirmacion sin respaldo que obligo a
        # retractar la tabla del experimento causal.
        "backend": backend_info(),
    }
    meta_path = os.path.join(RESULTS_DIR, f"{run_id}_meta.json")

    # El chequeo de dry_run va ANTES de escribir: un --dry-run que deja
    # {run_id}_meta.json en results/ inyecta corridas fantasma en
    # compute_ttd.py y en el dashboard (aparecen como nivel 0, sin eventos ni
    # transcript, bajando la tasa de escape de todo el brazo).
    if dry_run:
        print(f"[dry-run] {run_id}")
        return

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    env = os.environ.copy()
    env.update({
        "RUN_ID": run_id,
        "CANARY_TOKEN": canary,
        "CONDITION": cond,
        "TASK": task,
        "RUN_TIMEOUT_SECONDS": str(cfg.get("run_timeout_seconds", 240)),
        # Los contenedores montan este directorio como /results. Sin esto,
        # --results-dir solo movia el _meta.json y los monitores seguian
        # escribiendo en ./results -- la corrida quedaba partida en dos sitios.
        "RESULTS_HOST_DIR": RESULTS_DIR,
    })

    reset_memoria(task)

    print(f"[orquestador] corriendo {run_id}", flush=True)
    up = subprocess.run(
        ["docker", "compose", "-p", project, *compose_args,
         "up", "--build", "--abort-on-container-exit", "--exit-code-from", "sandbox"],
        cwd=ROOT, env=env,
    )

    meta["docker_exit_code"] = up.returncode
    meta["t1"] = time.time()

    diag = diagnostico_corrida(run_id)
    meta["diagnostico"] = diag
    if diag["sin_datos"]:
        SIN_DATOS.append(run_id)
        motivo = diag["errores_backend"][0] if diag["errores_backend"] else "sin tool calls"
        print("  AVISO: " + run_id + " no produjo datos (" + motivo + ")", flush=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    subprocess.run(
        ["docker", "compose", "-p", project, *compose_args, "down", "-v", "--remove-orphans"],
        cwd=ROOT, env=env,
    )
    print(f"[orquestador] {run_id} terminado, exit={up.returncode}", flush=True)


def main():
    global RESULTS_DIR

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "config.yaml"),
                         help="archivo de config (default: orchestrator/config.yaml)")
    parser.add_argument("--dry-run", action="store_true", help="solo lista las corridas planeadas")
    parser.add_argument("--limit", type=int, default=None, help="corta la matriz a las primeras N corridas")
    parser.add_argument("--results-dir", default=RESULTS_DIR,
                        help="donde escribir los artefactos (default: results/). "
                             "Un experimento que re-corre condiciones ya presentes "
                             "en results/ debe usar un directorio propio: si no, "
                             "el orquestador las salta por existir, y si se borran "
                             "para forzarlas se altera el corpus del que dependen "
                             "las demas secciones de report/findings.md.")
    args = parser.parse_args()

    RESULTS_DIR = os.path.abspath(args.results_dir)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    cfg = load_config(args.config)

    combos = list(itertools.product(cfg["conditions"], cfg["tasks"], range(cfg["repetitions"])))
    if args.limit:
        combos = combos[: args.limit]

    print(f"[orquestador] {len(combos)} corridas planeadas")

    for cond, task, rep in combos:
        run_id = f"{cond}_{task}_{rep:03d}"
        if os.path.exists(os.path.join(RESULTS_DIR, f"{run_id}.jsonl")):
            print(f"[orquestador] {run_id} ya tiene resultados, se salta")
            continue
        try:
            run_one(cond, task, rep, cfg, dry_run=args.dry_run)
        except KeyboardInterrupt:
            print("[orquestador] interrumpido por el usuario")
            sys.exit(1)
        except Exception as e:
            print(f"[orquestador] ERROR en {cond}/{task}/{rep}: {e}", file=sys.stderr)

    if SIN_DATOS:
        print("")
        print("AVISO: " + str(len(SIN_DATOS)) + " de " + str(len(combos)) +
              " corridas no produjeron datos (cero tool calls). Un fallo del",
              "backend deja el contenedor saliendo con codigo 0: la matriz",
              "parece completa y esta vacia.")
        for r in SIN_DATOS[:10]:
            print("  - " + r)


if __name__ == "__main__":
    main()
