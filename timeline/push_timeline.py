#!/usr/bin/env python3
"""
Empuja results/timeline_combined.jsonl a la API de ingesta de OpenObserve.

    POST http://localhost:5080/api/{org}/{stream}/_json
    basic auth con ZO_ROOT_USER_EMAIL / ZO_ROOT_USER_PASSWORD

Solo stdlib a proposito: el harness ya depende de Python en todas partes y
esto no justifica agregar `requests` a un requirements nuevo.

Uso:
    python3 timeline/push_timeline.py
    python3 timeline/push_timeline.py --stream sentinel_demo --batch 200
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_IN = os.path.join(ROOT, "results", "timeline_combined.jsonl")


def _lotes(items, n):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def enviar(url: str, auth: str, lote: list) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(lote, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default=DEFAULT_IN)
    parser.add_argument("--host", default=os.environ.get("OPENOBSERVE_URL", "http://localhost:5080"))
    parser.add_argument("--org", default=os.environ.get("OPENOBSERVE_ORG", "default"))
    parser.add_argument("--stream", default=os.environ.get("OPENOBSERVE_STREAM", "sentinel"))
    parser.add_argument("--user", default=os.environ.get("ZO_ROOT_USER_EMAIL", "root@sentinel.local"))
    parser.add_argument("--password", default=os.environ.get("ZO_ROOT_USER_PASSWORD", "Complexpass#123"))
    parser.add_argument("--batch", type=int, default=500,
                        help="eventos por peticion (default 500)")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"error: no existe {args.input}. Corre primero "
              f"`python3 timeline/export_timeline.py`.", file=sys.stderr)
        return 1

    eventos = []
    with open(args.input, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if linea:
                eventos.append(json.loads(linea))

    if not eventos:
        print(f"{args.input} esta vacio: no hay nada que ingerir. "
              f"Corre el experimento antes.", file=sys.stderr)
        return 1

    url = f"{args.host.rstrip('/')}/api/{args.org}/{args.stream}/_json"
    auth = base64.b64encode(f"{args.user}:{args.password}".encode()).decode()

    enviados = 0
    for i, lote in enumerate(_lotes(eventos, args.batch), 1):
        try:
            resp = enviar(url, auth, lote)
        except urllib.error.HTTPError as e:
            print(f"error HTTP {e.code} en el lote {i}: {e.read().decode(errors='replace')[:500]}",
                  file=sys.stderr)
            return 1
        except urllib.error.URLError as e:
            print(f"error: no se pudo contactar a {args.host} ({e.reason}). "
                  f"Levanta OpenObserve con "
                  f"`docker compose --profile forense up -d openobserve`.", file=sys.stderr)
            return 1
        # HTTP 200 NO significa ingerido: OpenObserve responde 200 con un
        # `status` por stream donde `failed` puede ser el lote entero (p.ej.
        # "Too old data"). Verificar el cuerpo, no el codigo.
        ok = sum(st.get("successful", 0) for st in resp.get("status", []))
        fallidos = [st for st in resp.get("status", []) if st.get("failed")]
        enviados += ok
        if fallidos:
            for st in fallidos:
                print(f"  lote {i}: {st.get('failed')} eventos RECHAZADOS por el stream "
                      f"'{st.get('name')}': {st.get('error')}", file=sys.stderr)
            print("  revisa ZO_INGEST_ALLOWED_UPTO en docker-compose.yml si el motivo "
                  "es la antiguedad de los datos.", file=sys.stderr)
            return 1
        print(f"  lote {i}: {ok} eventos aceptados")

    print(f"{enviados} eventos ingeridos en {url}")
    print(f"abre {args.host.rstrip('/')}/web/logs y selecciona el stream '{args.stream}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
