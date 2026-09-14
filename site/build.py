#!/usr/bin/env python3
"""
Congela los agregados del panel en un JSON para la pagina estatica.

La pagina que ve el jurado no puede depender de que haya un Flask vivo, pero
tampoco puede llevar cifras transcritas a mano: este repo ya arrastro dos
veces el mismo bug de una copia de la verdad que se quedo atras (el
exportador de timeline leyendo un solo directorio, 1509 de 4829 eventos; y
CORPUS_DIRS apuntando a directorios inexistentes, 70 de 150 corridas).

Por eso esto no reimplementa ningun agregado. Levanta el test client de
Flask, que ejecuta EXACTAMENTE el mismo codigo que sirve el panel, sin abrir
un puerto ni arrancar el watchdog. Si el panel y la pagina discrepan alguna
vez, es porque alguien edito el JSON a mano.

Uso:
    python3 site/build.py                  # escribe site/data.json
    python3 site/build.py --check          # no escribe, solo reporta

Cuando entren las corridas que faltan, se vuelve a correr y la pagina queda
al dia sin tocar una sola cifra.
"""
import argparse
import datetime
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "dashboard"))
sys.path.insert(0, os.path.join(ROOT, "analysis"))

import app as panel  # noqa: E402  (el mismo modulo que sirve el dashboard)
import compute_ttd as ttd  # noqa: E402

# Las superficies que la pagina necesita. La clave es el nombre con el que
# aterriza en data.json; el valor es la ruta real del panel.
SUPERFICIES = {
    "resumen": "/api/incidente/resumen",
    "comparacion": "/api/incidente/corpus_comparacion",
    "canary": "/api/incidente/canary_superficie",
    "routing": "/api/incidente/routing",
    "herramientas": "/api/incidente/herramientas",
    "memoria": "/api/incidente/memoria",
}


def escalera():
    """Por peldaño: cuantas corridas se detuvieron ahi y cuantas dispararon
    su señal, que no es lo mismo. Ver ttd.niveles_disparados: los niveles se
    evaluan de forma independiente, asi que llegar a 5 no implica haber
    pasado por 3 y 4, y sumar la distribucion hacia arriba mentiría.
    """
    detenidas = {n: 0 for n in ttd.NIVELES}
    disparadas = {n: 0 for n in ttd.NIVELES}
    sin_red = 0
    fugas = 0
    for corpus, dirpath in panel.CORPUS_DIRS.items():
        for run_id in panel._all_run_ids(corpus):
            meta = ttd.load_json(os.path.join(dirpath, run_id + "_meta.json"))
            transcript = ttd.load_jsonl(os.path.join(dirpath, run_id + "_transcript.jsonl"))
            eventos = ttd.load_jsonl(os.path.join(dirpath, run_id + ".jsonl"))
            vistos = ttd.niveles_disparados(transcript, eventos, meta)
            detenidas[max(vistos)] += 1
            for n in vistos:
                disparadas[n] += 1
            if 5 in vistos:
                fugas += 1
                # Ni intento de contactar un host mock ni contacto exitoso:
                # el canary salio sin que el trafico de red lo llevara.
                if not ({3, 4} & vistos):
                    sin_red += 1
    return {
        "detenidas": detenidas,
        "disparadas": disparadas,
        "fugas": fugas,
        "fugas_sin_red": sin_red,
    }


def ttd_distribucion():
    """Media y mediana del TTD sobre todos los corpus.

    El panel publica la media por grupo, nunca la global ni la mediana, y las
    dos cuentan historias distintas: la mediana esta en milisegundos y la
    media en mas de un segundo, porque unas pocas corridas lentas tiran del
    promedio. La pagina dice las dos, asi que se calculan aqui.
    """
    valores = []
    for corpus in panel.CORPUS_DIRS:
        for run_id in panel._all_run_ids(corpus):
            fila = panel.analyze_run_in(corpus, run_id)
            if fila.get("ttd_segundos") is not None:
                valores.append(fila["ttd_segundos"])
    if not valores:
        return None
    return {
        "n": len(valores),
        "media": statistics.mean(valores),
        "mediana": statistics.median(valores),
        "min": min(valores),
        "max": max(valores),
    }


def construir():
    cliente = panel.app.test_client()
    datos = {}
    for nombre, ruta in SUPERFICIES.items():
        resp = cliente.get(ruta)
        if resp.status_code != 200:
            raise SystemExit("%s devolvio HTTP %d" % (ruta, resp.status_code))
        datos[nombre] = resp.get_json()

    datos["ttd"] = ttd_distribucion()
    datos["escalera"] = escalera()
    datos["corpus"] = {
        clave: {
            "label": panel.CORPUS_LABELS[clave],
            "corridas": len(panel._all_run_ids(clave)),
        }
        for clave in panel.CORPUS_DIRS
    }
    datos["niveles_labels"] = ttd.NIVELES

    # Las lineas que load_jsonl no pudo parsear. Un append no atomico sobre
    # el bind mount de Docker Desktop parte alguna linea, y lo que se pierde
    # puede ser un `info` o puede ser la alerta que decide esa corrida. Va en
    # el JSON para que la pagina pueda declararlo en vez de callarlo.
    datos["lineas_corruptas"] = sorted(set(getattr(ttd, "LINEAS_CORRUPTAS", [])))

    datos["generado"] = datetime.datetime.now().replace(microsecond=0).isoformat()
    return datos


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="no escribe, solo reporta lo que saldria")
    parser.add_argument("--out", default=os.path.join(ROOT, "site", "data.json"))
    args = parser.parse_args()

    datos = construir()
    resumen = datos["resumen"]
    total = resumen["total_corridas"]
    combinado = resumen["combinado"]
    intentos = sum(f["intentos_de_escape"] for f in combinado)
    detectados = sum(f["detectados"] for f in combinado)
    agente = sum(f["detectados_superficie_agente"] for f in combinado)

    print("corridas            %d" % total)
    print("intentos de escape  %d" % intentos)
    print("detectados          %d" % detectados)
    print("superficie agente   %d" % agente)
    if datos["ttd"]:
        print("ttd mediana %.3fs, media %.3fs, max %.3fs"
              % (datos["ttd"]["mediana"], datos["ttd"]["media"], datos["ttd"]["max"]))
    for clave, info in sorted(datos["corpus"].items()):
        print("  %-32s %3d corridas" % (clave, info["corridas"]))
    esc = datos["escalera"]
    print("fugas sin tocar la red  %d de %d" % (esc["fugas_sin_red"], esc["fugas"]))
    if datos["lineas_corruptas"]:
        print("lineas corruptas    %d  %s"
              % (len(datos["lineas_corruptas"]), ", ".join(datos["lineas_corruptas"][:3])))

    if args.check:
        print("\n--check: no se escribio nada")
        return

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    print("\nescrito %s (%.1f KB)" % (args.out, os.path.getsize(args.out) / 1024))

    render(datos)


def render(datos):
    """Inyecta los datos y el logo en la plantilla y escribe site/index.html.

    Sale un unico archivo autocontenido: sin fetch, sin archivos al lado, sin
    servidor. Abre con doble clic y es exactamente lo que publica Vercel, que
    es lo que se enlaza desde el paper.
    """
    import base64
    import io as _io

    from PIL import Image

    plantilla = os.path.join(ROOT, "site", "template.html")
    salida = os.path.join(ROOT, "site", "index.html")
    with open(plantilla, encoding="utf-8") as f:
        html = f.read()

    # El original son 593 KB para una marca de 32 px, y base64 lo infla otro
    # tercio. Se rasteriza a 128 px antes de embeberlo.
    logo = Image.open(os.path.join(ROOT, "dashboard", "static", "logo.png")).convert("RGBA")
    logo.thumbnail((128, 128), Image.LANCZOS)
    buf = _io.BytesIO()
    logo.save(buf, "PNG", optimize=True)
    uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    marcador = "const D = window.SENTINEL_DATA;"
    if marcador not in html:
        raise SystemExit("template.html no tiene el marcador de datos")

    html = html.replace("__LOGO__", uri)
    html = html.replace(
        marcador,
        "window.SENTINEL_DATA = " + json.dumps(datos, ensure_ascii=False) + ";\n" + marcador,
        1)

    with open(salida, "w", encoding="utf-8") as f:
        f.write(html)
    print("escrito %s (%.1f KB)" % (salida, os.path.getsize(salida) / 1024))


if __name__ == "__main__":
    main()
