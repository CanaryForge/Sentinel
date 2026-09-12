#!/usr/bin/env python3
"""
Espera en el .jsonl de eventos de una corrida a que aparezca uno que cumpla
el filtro dado, y reporta cuanto tardo desde --since. Usado por
tests/positive_controls.sh para medir tiempo de deteccion sin depender de
jq/bash para parsear JSON (unica dependencia: python3, ya prerrequisito del
proyecto).

Uso:
    python3 tests/_wait_for_event.py results/run.jsonl --since 123.456 \
        --type heartbeat --contains CNRY-xyz --timeout 30

Imprime el tiempo transcurrido (segundos, 3 decimales) y termina con exit 0
si encontro el evento antes de --timeout; imprime TIMEOUT y termina con
exit 1 si no.
"""
import argparse
import json
import time


def matches(event, tipo, severidad, contains):
    if tipo and event.get("type") != tipo:
        return False
    if severidad and event.get("severidad") != severidad:
        return False
    if contains and contains not in json.dumps(event.get("detalle", {})):
        return False
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("path")
    p.add_argument("--since", type=float, required=True)
    p.add_argument("--type")
    p.add_argument("--severidad", default="alerta")
    p.add_argument("--contains")
    p.add_argument("--timeout", type=float, default=30)
    args = p.parse_args()

    deadline = time.time() + args.timeout
    seen = 0
    while time.time() < deadline:
        try:
            with open(args.path) as f:
                lines = f.readlines()
        except FileNotFoundError:
            lines = []
        for line in lines[seen:]:
            seen += 1
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("ts", 0) < args.since:
                continue
            if matches(event, args.type, args.severidad, args.contains):
                print(f"{event['ts'] - args.since:.3f}")
                return 0
        time.sleep(0.2)
    print("TIMEOUT")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
