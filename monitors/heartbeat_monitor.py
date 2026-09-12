"""
Monitor 1 (Capa 4): heartbeat. Escucha pings del sandbox en :9000 y marca
un evento de alerta si un run_id deja de sonar por mas de
HEARTBEAT_INTERVAL * HEARTBEAT_TIMEOUT_MULT segundos.

Corre dentro del mismo contenedor que el proxy de egress (ver entrypoint.sh),
en un proceso separado, porque este canal es intencionalmente independiente
del trafico que se esta auditando.
"""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from event_bus import append_event

INTERVAL = float(os.environ.get("HEARTBEAT_INTERVAL", "5"))
TIMEOUT_MULT = float(os.environ.get("HEARTBEAT_TIMEOUT_MULT", "2"))

last_seen = {}
alerted = set()
lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        if self.path != "/heartbeat":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        run_id = data.get("run_id", "unknown")
        with lock:
            last_seen[run_id] = time.time()
            alerted.discard(run_id)
        append_event(run_id, "heartbeat", "info", {"seq": data.get("seq")})

        self.send_response(200)
        self.end_headers()


def watchdog():
    while True:
        time.sleep(1)
        now = time.time()
        with lock:
            for run_id, ts in list(last_seen.items()):
                if run_id in alerted:
                    continue
                if now - ts > INTERVAL * TIMEOUT_MULT:
                    alerted.add(run_id)
                    append_event(run_id, "heartbeat", "alerta", {
                        "motivo": "silencio",
                        "segundos_sin_ping": now - ts,
                    })


def main():
    threading.Thread(target=watchdog, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", 9000), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
