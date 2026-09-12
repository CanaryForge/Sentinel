"""
Heartbeat de Capa 4 (senal 1): ping periodico desde dentro del sandbox.
Va DIRECTO al monitor (bypassea el proxy de egress a proposito, via
proxies={"http": None, "https": None}) porque es un canal de instrumentacion,
no trafico del agente que se este evaluando. Si el heartbeat dejara de sonar
(agente colgado, contenedor matado, o el propio heartbeat bloqueado por un
agente que satura la red saliente), el monitor del otro lado lo marca.
"""
import os
import socket
import sys
import time

import requests

RUN_ID = os.environ.get("RUN_ID", "unknown")
INTERVAL = float(os.environ.get("HEARTBEAT_INTERVAL", "5"))
URL = os.environ.get("HEARTBEAT_URL", "http://egress-proxy:9000/heartbeat")


def ping(seq: int) -> None:
    payload = {
        "type": "heartbeat",
        "run_id": RUN_ID,
        "seq": seq,
        "ts": time.time(),
        "host": socket.gethostname(),
    }
    requests.post(URL, json=payload, timeout=2, proxies={"http": None, "https": None})


def main() -> None:
    seq = 0
    while True:
        try:
            ping(seq)
        except Exception as e:  # nunca debe tumbar el proceso principal
            print(f"[heartbeat] fallo seq={seq}: {e}", file=sys.stderr, flush=True)
        seq += 1
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
