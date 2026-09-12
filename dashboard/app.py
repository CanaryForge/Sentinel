#!/usr/bin/env python3
"""
Panel local (Capa 5, herramienta de investigacion): sirve los datos reales
de results/ como API JSON para el dashboard en dashboard/static/index.html.

No es parte del arnes que se prueba (no corre en Docker, no toca las redes
internal: true) -- es un visor que un investigador corre en su propio host
para inspeccionar corridas ya hechas o en curso. Reusa la logica de
analysis/compute_ttd.py (misma definicion de "intento de escape",
"deteccion" y la escalera de 0-6 niveles) en vez de duplicarla, para que el
panel y el analisis de linea de comandos nunca diverjan.

Uso:
    python3 dashboard/app.py [--port 8765]
    -> abrir http://localhost:8765
"""
import argparse
import glob
import os
import sys

from flask import Flask, jsonify, send_from_directory

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT, "results")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

sys.path.insert(0, os.path.join(ROOT, "analysis"))
import compute_ttd as ttd  # noqa: E402

ttd.RESULTS_DIR = RESULTS_DIR

app = Flask(__name__, static_folder=None)


def list_run_ids():
    metas = sorted(glob.glob(os.path.join(RESULTS_DIR, "*_meta.json")))
    return [os.path.basename(p)[: -len("_meta.json")] for p in metas]


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory(STATIC_DIR, path)


@app.route("/api/runs")
def api_runs():
    rows = []
    for run_id in list_run_ids():
        try:
            r = ttd.analyze_run(run_id)
            meta = ttd.load_json(os.path.join(RESULTS_DIR, f"{run_id}_meta.json"))
            # sin "t1" todavia == run_experiment.py no ha vuelto de
            # `docker compose up` para esta corrida == esta en curso ahora
            # mismo. Es lo que el panel usa para saber a que corrida
            # "seguir" en el modo en vivo.
            r["en_curso"] = "t1" not in meta
        except Exception as e:
            r = {"run_id": run_id, "error": str(e)}
        rows.append(r)
    rows.sort(key=lambda r: (r.get("condicion") or "", r.get("tarea") or "", r.get("run_id") or ""))
    return jsonify(rows)


@app.route("/api/runs/<run_id>")
def api_run_detail(run_id):
    meta_path = os.path.join(RESULTS_DIR, f"{run_id}_meta.json")
    if not os.path.exists(meta_path):
        return jsonify({"error": "no existe ese run_id"}), 404

    meta = ttd.load_json(meta_path)
    events = ttd.load_jsonl(os.path.join(RESULTS_DIR, f"{run_id}.jsonl"))
    transcript = ttd.load_jsonl(os.path.join(RESULTS_DIR, f"{run_id}_transcript.jsonl"))
    analysis = ttd.analyze_run(run_id)

    # Mismos umbrales que analyze_run, pero exponiendo los timestamps crudos
    # (analyze_run solo devuelve derivados: ttd_segundos, detectado, nivel)
    # para que el panel pueda dibujar el momento exacto en la linea de tiempo.
    if meta.get("tarea") == "task_04_prompt_injection":
        escape_ts = ttd.first_canary_use_ts(transcript, meta.get("canary"))
    else:
        escape_ts = ttd.first_escape_attempt_ts(transcript)
    alert_ts, _ = ttd.first_alert_after(events, escape_ts, meta.get("docker_exit_code"))

    return jsonify({
        "meta": meta,
        "events": events,
        "transcript": transcript,
        "analysis": analysis,
        "escape_ts": escape_ts,
        "alert_ts": alert_ts,
    })


@app.route("/api/monitor_strength")
def api_monitor_strength():
    """
    Datos del barrido deterministico tests/monitor_strength_sweep.sh: mismo
    evento sintetico de fuga, variando el parametro de configuracion del
    monitor (intervalo de polling del canary, umbral del heartbeat), para
    mostrar cuanto empeora el TTD cuando se afloja la vigilancia -- sin
    depender de que un LLM decida escapar.
    """
    path = os.path.join(RESULTS_DIR, "monitor_strength.jsonl")
    rows = ttd.load_jsonl(path)
    rows.sort(key=lambda r: (r.get("mecanismo"), r.get("valor", 0)))
    return jsonify(rows)


@app.route("/api/aggregate")
def api_aggregate():
    rows = [ttd.analyze_run(rid) for rid in list_run_ids()]
    grupos = {}
    for r in rows:
        key = (r.get("condicion"), r.get("tarea"))
        grupos.setdefault(key, []).append(r)

    salida = []
    for (cond, tarea), grupo in grupos.items():
        ttds = [r["ttd_segundos"] for r in grupo if r.get("ttd_segundos") is not None]
        intentos = sum(1 for r in grupo if r.get("intento_de_escape"))
        detectados = sum(1 for r in grupo if r.get("intento_de_escape") and r.get("detectado"))
        dist_niveles = {n: 0 for n in ttd.NIVELES}
        for r in grupo:
            dist_niveles[r.get("nivel_escalada", 0)] += 1
        lo, hi = ttd.bootstrap_ci(ttds) if ttds else (None, None)
        salida.append({
            "condicion": cond,
            "tarea": tarea,
            "corridas": len(grupo),
            "intentos_de_escape": intentos,
            "detectados": detectados,
            "ttd_media": (sum(ttds) / len(ttds)) if ttds else None,
            "ttd_ic95": [lo, hi] if ttds else None,
            "dist_niveles": dist_niveles,
        })
    salida.sort(key=lambda r: (str(r["condicion"]), str(r["tarea"])))
    return jsonify({"grupos": salida, "niveles_labels": ttd.NIVELES, "total_corridas": len(rows)})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    print(f"[dashboard] leyendo resultados de {RESULTS_DIR}")
    print(f"[dashboard] abrir http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
