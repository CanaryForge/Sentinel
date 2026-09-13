#!/usr/bin/env python3
"""
Panel local (Capa 5, herramienta de investigacion): sirve los datos reales
de results/ como API JSON para el dashboard en dashboard/static/index.html,
mas un feed en vivo por Server-Sent Events (/api/stream) empujado por un
watchdog.Observer sobre results/ -- el panel deja de depender de que el
frontend relea el disco a intervalos; es el propio filesystem (inotify) el
que dispara cada item del feed en el instante en que un monitor o el agente
escriben una linea nueva.

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
import json
import os
import queue
import sys
import threading

from flask import Flask, Response, jsonify, send_from_directory, stream_with_context
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT, "results")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

sys.path.insert(0, os.path.join(ROOT, "analysis"))
import compute_ttd as ttd  # noqa: E402

ttd.RESULTS_DIR = RESULTS_DIR

app = Flask(__name__, static_folder=None)

# ---------------------------------------------------------------------------
# Feed en vivo (SSE): un watchdog.Observer corre en su propio hilo, entero
# separado del ciclo request/response de Flask. Cuando toca una linea nueva
# en un *.jsonl de results/, la parsea y la reparte a cada cliente conectado
# via su Queue. app.run(..., threaded=True) es lo que permite tener el
# stream abierto de un cliente mientras otros piden /api/runs etc.
# ---------------------------------------------------------------------------

_subscribers: set[queue.Queue] = set()
_subscribers_lock = threading.Lock()
_file_offsets: dict[str, int] = {}
_meta_seen: set[str] = set()
_meta_seen_t1: dict[str, bool] = {}
_state_lock = threading.Lock()


def _broadcast(payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False)
    with _subscribers_lock:
        dead = []
        for q in _subscribers:
            try:
                q.put_nowait(data)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _subscribers.discard(q)


def _classify_jsonl(path: str):
    name = os.path.basename(path)
    if not name.endswith(".jsonl"):
        return None
    if name in ("summary.jsonl", "monitor_strength.jsonl"):
        return None
    if name.endswith("_transcript.jsonl"):
        return name[: -len("_transcript.jsonl")], "transcript"
    return name[: -len(".jsonl")], "monitor"


def _read_new_lines(path: str) -> list:
    try:
        size = os.path.getsize(path)
    except OSError:
        return []
    with _state_lock:
        start = _file_offsets.get(path, 0)
        if size < start:
            start = 0  # archivo truncado o recreado -- releer desde el inicio
        if size == start:
            return []
        with open(path, "r") as f:
            f.seek(start)
            chunk = f.read()
        _file_offsets[path] = size
    return [line for line in chunk.split("\n") if line.strip()]


def _handle_meta_change(path: str) -> None:
    run_id = os.path.basename(path)[: -len("_meta.json")]
    try:
        meta = ttd.load_json(path)
    except (OSError, ValueError):
        return
    has_t1 = "t1" in meta
    with _state_lock:
        is_new = run_id not in _meta_seen
        _meta_seen.add(run_id)
        already_finished = _meta_seen_t1.get(run_id, False)
        _meta_seen_t1[run_id] = has_t1
    if is_new:
        _broadcast({"feed_type": "run_started", "run_id": run_id, "data": meta})
        if has_t1:
            _broadcast({"feed_type": "run_finished", "run_id": run_id, "data": meta})
    elif has_t1 and not already_finished:
        _broadcast({"feed_type": "run_finished", "run_id": run_id, "data": meta})


def _handle_jsonl_change(path: str) -> None:
    info = _classify_jsonl(path)
    if info is None:
        return
    run_id, kind = info
    for line in _read_new_lines(path):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        _broadcast({"feed_type": kind, "run_id": run_id, "data": obj})


def _handle_fs_event(path: str) -> None:
    name = os.path.basename(path)
    if name.endswith("_meta.json"):
        _handle_meta_change(path)
    elif name.endswith(".jsonl"):
        _handle_jsonl_change(path)


class _ResultsHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            _handle_fs_event(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            _handle_fs_event(event.src_path)


def _prime_watch_state() -> None:
    """
    Al arrancar: marca el tamano actual de cada *.jsonl y que corridas ya
    tienen t1, sin emitir nada (nadie esta suscrito todavia). Sin esto, el
    primer evento de filesystem que llegue leeria cada archivo desde el
    byte 0 y el feed arrancaria repitiendo el historial completo como si
    fuera "en vivo".
    """
    for path in glob.glob(os.path.join(RESULTS_DIR, "*.jsonl")):
        try:
            _file_offsets[path] = os.path.getsize(path)
        except OSError:
            pass
    for meta_path in glob.glob(os.path.join(RESULTS_DIR, "*_meta.json")):
        run_id = os.path.basename(meta_path)[: -len("_meta.json")]
        try:
            meta = ttd.load_json(meta_path)
        except (OSError, ValueError):
            continue
        _meta_seen.add(run_id)
        _meta_seen_t1[run_id] = "t1" in meta


def _start_watcher() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    _prime_watch_state()
    observer = Observer()
    observer.schedule(_ResultsHandler(), RESULTS_DIR, recursive=False)
    observer.daemon = True
    observer.start()


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


@app.route("/api/stream")
def api_stream():
    """
    SSE: un evento por linea nueva en results/*.jsonl (monitor o transcript
    del agente) y por cambio de ciclo de vida de una corrida (arranca /
    termina, segun _meta.json). El cliente es un EventSource nativo del
    navegador -- reconecta solo si se cae la conexion, no hace falta
    logica de retry en el frontend.
    """
    client_q: queue.Queue = queue.Queue(maxsize=500)
    with _subscribers_lock:
        _subscribers.add(client_q)

    def gen():
        try:
            yield "retry: 2000\n\n"
            while True:
                try:
                    data = client_q.get(timeout=15)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with _subscribers_lock:
                _subscribers.discard(client_q)

    return Response(
        stream_with_context(gen()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
    print(f"[dashboard] feed en vivo: watchdog.Observer sobre {RESULTS_DIR}")
    print(f"[dashboard] abrir http://{args.host}:{args.port}")
    _start_watcher()
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
