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
    })

    print(f"[orquestador] corriendo {run_id}", flush=True)
    up = subprocess.run(
        ["docker", "compose", "-p", project, *compose_args,
         "up", "--build", "--abort-on-container-exit", "--exit-code-from", "sandbox"],
        cwd=ROOT, env=env,
    )

    meta["docker_exit_code"] = up.returncode
    meta["t1"] = time.time()
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    subprocess.run(
        ["docker", "compose", "-p", project, *compose_args, "down", "-v", "--remove-orphans"],
        cwd=ROOT, env=env,
    )
    print(f"[orquestador] {run_id} terminado, exit={up.returncode}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "config.yaml"),
                         help="archivo de config (default: orchestrator/config.yaml)")
    parser.add_argument("--dry-run", action="store_true", help="solo lista las corridas planeadas")
    parser.add_argument("--limit", type=int, default=None, help="corta la matriz a las primeras N corridas")
    args = parser.parse_args()

    cfg = load_config(args.config)
    os.makedirs(RESULTS_DIR, exist_ok=True)

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


if __name__ == "__main__":
    main()
