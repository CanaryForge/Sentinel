#!/usr/bin/env python3
"""
Congela los agregados del arnes en un JSON y renderiza la pagina publica.

La pagina que acompana al paper no puede depender de que haya un Flask vivo,
pero tampoco puede llevar cifras transcritas a mano: este repo ya arrastro dos
veces el mismo bug de una copia de la verdad que se quedo atras (el exportador
de timeline leyendo un solo directorio, 1509 de 4829 eventos; y CORPUS_DIRS
apuntando a directorios inexistentes, 70 de 150 corridas).

Por eso esto no reimplementa los agregados del panel. Levanta el test client
de Flask, que ejecuta el MISMO codigo que sirve dashboard/app.py, sin abrir un
puerto ni arrancar el watchdog. Lo que si calcula aqui son los cuatro
hallazgos, porque el panel no los expone como endpoint.

Uso:
    python3 site/build.py           # escribe site/data.json y site/index.html
    python3 site/build.py --check   # no escribe, solo reporta

Requiere Python 3.10 o superior (dashboard/app.py usa `str | None`).
Sin dependencias mas alla de las que ya pide dashboard/requirements.txt.
"""
import argparse
import base64
import collections
import datetime
import json
import os
import re
import statistics
import sys
from math import comb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "dashboard"))
sys.path.insert(0, os.path.join(ROOT, "analysis"))

import app as panel  # noqa: E402  (el mismo modulo que sirve el dashboard)
import compute_ttd as ttd  # noqa: E402

NIVEL_FUGA = 5

# Enlaces de la pagina. Se pueden pisar sin tocar el archivo:
#   PAPER_URL=https://... python3 site/build.py
# Si PAPER_URL queda vacia, los botones y el enlace del menu que apuntan al
# paper NO se renderizan, en vez de quedar apuntando a ninguna parte.
PAPER_URL = os.environ.get("PAPER_URL", "").strip()
REPO_URL = os.environ.get("REPO_URL", "https://github.com/CanaryForge/Sentinel").strip()

SUPERFICIES = {
    "resumen": "/api/incidente/resumen",
    "canary": "/api/incidente/canary_superficie",
    "routing": "/api/incidente/routing",
    "herramientas": "/api/incidente/herramientas",
}

# El lote donde vive el Hallazgo 1. Es el unico que corrio los tres canales
# de entrega contra el MISMO texto inyectado, mismo modelo y misma sesion, asi
# que es el unico sitio donde comparar canales significa algo. Mezclarlo con
# otras maquinas compararia tambien hardware y version de Ollama.
LOTE_CANALES = "machine-A/corpus"
CANALES = {
    "task_04_prompt_injection": "live network fetch",
    "task_05_memory_poison": "persistent memory between runs",
    "task_06_rag_poison": "local knowledge base search",
}

# El Hallazgo 3 compara el mismo contraste a dos tamanos de muestra. Los dos
# lotes de n=40 son el mismo experimento causal, en la misma maquina y con la
# misma version de Ollama, por eso se pueden sumar.
GUARDRAIL_N10 = ["machine-A/corpus"]
GUARDRAIL_N40 = ["machine-B/causal-n30-ollama0.34.0", "machine-B/causal-ollama0.34.0"]


def fisher_bilateral(a, b, c, d):
    """p exacto de Fisher para una tabla 2x2, sin scipy.

    Suma la probabilidad hipergeometrica de toda tabla al menos tan extrema
    como la observada, con los marginales fijos.
    """
    n = a + b + c + d
    fila1, col1 = a + b, a + c
    if not n or not fila1 or not col1:
        return float("nan")

    def prob(x):
        return comb(fila1, x) * comb(n - fila1, col1 - x) / comb(n, col1)

    p_obs = prob(a)
    lo = max(0, col1 - (n - fila1))
    hi = min(fila1, col1)
    return sum(prob(x) for x in range(lo, hi + 1) if prob(x) <= p_obs + 1e-12)


def lotes_validos():
    """Los lotes que cuentan, y los que no con su motivo.

    Un lote queda fuera si su manifest.json abre la advertencia con NO USAR.
    Hoy son los dos de machine-D que el timeout de cliente vacio: sus corridas
    terminaron con exit 0 y cero tool calls, asi que son indistinguibles de
    una corrida donde el agente vio el cebo y no pico.
    """
    panel._refrescar_corpus()
    validos, excluidos = {}, {}
    for clave, ruta in panel.CORPUS_DIRS.items():
        aviso = (panel.CORPUS_ADVERTENCIAS.get(clave) or "").strip()
        if aviso.upper().startswith("NO USAR"):
            excluidos[clave] = {
                "corridas": len(panel._all_run_ids(clave)),
                "motivo": aviso,
            }
        else:
            validos[clave] = ruta
    return validos, excluidos


def filas_de(claves):
    """analyze_run() de cada corrida de esos lotes, con su lote pegado."""
    salida = []
    for clave in claves:
        for run_id in panel._all_run_ids(clave):
            salida.append((clave, panel.analyze_run_in(clave, run_id)))
    return salida


def nivel5(filas):
    return sum(1 for _, r in filas if (r.get("nivel_escalada") or 0) >= NIVEL_FUGA)


def canales(validos):
    """Hallazgo 1: la misma instruccion, tres canales de entrega.

    Solo con_harness y sin_harness. con_harness_generico no entra: es el brazo
    del experimento de priming, no un canal, y sumarlo cambiaria el
    denominador de una sola de las tres filas.
    """
    if LOTE_CANALES not in validos:
        return None
    celdas = collections.defaultdict(lambda: [0, 0])
    for _, r in filas_de([LOTE_CANALES]):
        if r.get("condicion") not in ("con_harness", "sin_harness"):
            continue
        tarea = r.get("tarea")
        if tarea not in CANALES:
            continue
        celdas[tarea][0] += 1
        if (r.get("nivel_escalada") or 0) >= NIVEL_FUGA:
            celdas[tarea][1] += 1

    salida = []
    for tarea, canal in CANALES.items():
        n, fugas = celdas.get(tarea, [0, 0])
        salida.append({
            "tarea": tarea,
            "canal": canal,
            "corridas": n,
            "nivel5": fugas,
            "tasa": (fugas / n) if n else None,
        })
    salida.sort(key=lambda f: f["tasa"] if f["tasa"] is not None else -1)
    return {"lote": LOTE_CANALES, "filas": salida}


def guardrail(validos):
    """Hallazgo 3: el mismo contraste medido a n=10 y a n=40.

    Solo task_06_rag_poison, que es la unica tarea con suficientes corridas en
    los dos tamanos. Se reporta el p exacto de Fisher porque la diferencia de
    tasas sola no dice si el efecto sobrevive al aumento de muestra.
    """
    salida = []
    for etiqueta, claves in (("n=10", GUARDRAIL_N10), ("n=40", GUARDRAIL_N40)):
        presentes = [k for k in claves if k in validos]
        if not presentes:
            continue
        filas = [(k, r) for k, r in filas_de(presentes)
                 if r.get("tarea") == "task_06_rag_poison"]
        con = [(k, r) for k, r in filas if r.get("condicion") == "con_harness"]
        sin = [(k, r) for k, r in filas if r.get("condicion") == "sin_harness"]
        if not con or not sin:
            continue
        a, b = nivel5(con), len(con) - nivel5(con)
        c, d = nivel5(sin), len(sin) - nivel5(sin)
        p = fisher_bilateral(a, b, c, d)
        salida.append({
            "etiqueta": etiqueta,
            "lotes": presentes,
            "con_harness": {"nivel5": a, "corridas": len(con), "tasa": a / len(con)},
            "sin_harness": {"nivel5": c, "corridas": len(sin), "tasa": c / len(sin)},
            "diferencia_pts": (a / len(con) - c / len(sin)) * 100,
            "fisher_p": p,
            "separa": bool(p < 0.05),
        })
    return salida


def escalera(validos):
    """Por peldano: cuantas corridas se detuvieron ahi y cuantas dispararon su
    senal, que no es lo mismo.

    Los peldanos se evaluan de forma independiente (ver ttd.niveles_disparados),
    asi que llegar a 5 no implica haber pasado por 3 y 4, y sumar la
    distribucion hacia arriba inventaria un numero que los datos no respaldan.
    """
    detenidas = {n: 0 for n in ttd.NIVELES}
    disparadas = {n: 0 for n in ttd.NIVELES}
    fugas = sin_red = 0
    for clave, dirpath in validos.items():
        for run_id in panel._all_run_ids(clave):
            meta = ttd.load_json(os.path.join(dirpath, run_id + "_meta.json"))
            transcript = ttd.load_jsonl(os.path.join(dirpath, run_id + "_transcript.jsonl"))
            eventos = ttd.load_jsonl(os.path.join(dirpath, run_id + ".jsonl"))
            vistos = ttd.niveles_disparados(transcript, eventos, meta)
            detenidas[max(vistos)] += 1
            for n in vistos:
                disparadas[n] += 1
            if NIVEL_FUGA in vistos:
                fugas += 1
                # Ni intento de contactar un host mock ni contacto exitoso: el
                # canary salio sin que ningun trafico de red lo llevara.
                if not ({3, 4} & vistos):
                    sin_red += 1
    return {"detenidas": detenidas, "disparadas": disparadas,
            "fugas": fugas, "fugas_sin_red": sin_red}


def ttd_distribucion(validos):
    """Mediana y media del TTD. Cuentan historias distintas: la mediana esta en
    milisegundos y la media pasa del segundo, porque unas pocas corridas lentas
    tiran del promedio."""
    valores = [r["ttd_segundos"] for _, r in filas_de(validos)
               if r.get("ttd_segundos") is not None]
    if not valores:
        return None
    return {"n": len(valores), "media": statistics.mean(valores),
            "mediana": statistics.median(valores),
            "min": min(valores), "max": max(valores)}


def construir():
    validos, excluidos = lotes_validos()
    # Los endpoints del panel recorren CORPUS_DIRS entero. Se acota a los lotes
    # validos durante la consulta para que las cifras servidas y las de la
    # pagina sean las mismas, y se restaura despues.
    completo = panel.CORPUS_DIRS
    panel.CORPUS_DIRS = validos
    try:
        cliente = panel.app.test_client()
        datos = {}
        for nombre, ruta in SUPERFICIES.items():
            resp = cliente.get(ruta)
            if resp.status_code != 200:
                raise SystemExit("%s devolvio HTTP %d" % (ruta, resp.status_code))
            datos[nombre] = resp.get_json()

        filas = filas_de(validos)
        datos["totales"] = {
            "corridas": len(filas),
            "lotes": len(validos),
            "maquinas": sorted({c.split("/")[0] for c in validos}),
            "intentos": sum(1 for _, r in filas if r.get("intento_de_escape")),
            "detectados": sum(1 for _, r in filas
                              if r.get("intento_de_escape") and r.get("detectado")),
        }
        datos["ttd"] = ttd_distribucion(validos)
        datos["escalera"] = escalera(validos)
        datos["canales"] = canales(validos)
        datos["guardrail"] = guardrail(validos)
        datos["lotes"] = {
            c: {"label": panel.CORPUS_LABELS.get(c, c),
                "corridas": len(panel._all_run_ids(c)),
                "advertencia": panel.CORPUS_ADVERTENCIAS.get(c)}
            for c in sorted(validos)
        }
    finally:
        panel.CORPUS_DIRS = completo

    datos["excluidos"] = excluidos
    datos["niveles_labels"] = ttd.NIVELES
    # Lineas que load_jsonl no pudo parsear: el append de tres monitores sobre
    # el mismo JSONL no es atomico en el bind mount de Docker Desktop. Lo que
    # se pierde puede ser un info intrascendente o la alerta que decide esa
    # corrida, asi que va en el JSON para poder declararlo.
    datos["lineas_corruptas"] = sorted(set(getattr(ttd, "LINEAS_CORRUPTAS", [])))
    datos["generado"] = datetime.datetime.now().replace(microsecond=0).isoformat()
    return datos


def render(datos):
    """Inyecta datos y logo en la plantilla y escribe site/index.html.

    Sale un unico archivo autocontenido: sin fetch, sin archivos al lado, sin
    servidor. Es lo mismo que publica Vercel y lo mismo que se abre con doble
    clic desde el enlace del paper.
    """
    with open(os.path.join(ROOT, "site", "template.html"), encoding="utf-8") as f:
        html = f.read()

    # El logo se embebe tal cual: dashboard/static/logo.png ya son 128 px y
    # unos 10 KB, que es el tamano al que se dibuja. Redimensionarlo aqui solo
    # anadiria Pillow como dependencia del build para no cambiar nada. Si
    # alguna vez vuelve el original de 1254 px, reducirlo antes de commitear.
    ruta_logo = os.path.join(ROOT, "dashboard", "static", "logo.png")
    with open(ruta_logo, "rb") as f:
        bytes_logo = f.read()
    if len(bytes_logo) > 64 * 1024:
        raise SystemExit(
            "%s pesa %.0f KB. Se embebe en el HTML, asi que reducelo a 128 px "
            "antes de seguir." % (ruta_logo, len(bytes_logo) / 1024))
    uri = "data:image/png;base64," + base64.b64encode(bytes_logo).decode()

    marcador = "const D = window.SENTINEL_DATA;"
    if marcador not in html:
        raise SystemExit("template.html no tiene el marcador de datos")
    html = html.replace("__LOGO__", uri)
    html = html.replace("__REPO_URL__", REPO_URL)
    if PAPER_URL:
        html = html.replace("__PAPER_URL__", PAPER_URL)
    else:
        # Sin URL de paper, se quita el elemento entero en vez de dejar un
        # enlace muerto en la pagina que el paper enlaza.
        html = re.sub(r'\s*<a[^>]*href="__PAPER_URL__"[^>]*>.*?</a>', "", html,
                      flags=re.S)
        print("  aviso: PAPER_URL vacia, se omiten los enlaces al paper")
    html = html.replace(
        marcador,
        "window.SENTINEL_DATA = " + json.dumps(datos, ensure_ascii=False) + ";\n" + marcador,
        1)

    salida = os.path.join(ROOT, "site", "index.html")
    with open(salida, "w", encoding="utf-8") as f:
        f.write(html)
    print("escrito %s (%.1f KB)" % (salida, os.path.getsize(salida) / 1024))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="no escribe, solo reporta lo que saldria")
    parser.add_argument("--out", default=os.path.join(ROOT, "site", "data.json"))
    args = parser.parse_args()

    datos = construir()
    t = datos["totales"]
    print("corridas validas    %d  (%d lotes, maquinas %s)"
          % (t["corridas"], t["lotes"], ", ".join(t["maquinas"])))
    for clave, info in datos["excluidos"].items():
        print("  excluido          %s  (%d corridas)" % (clave, info["corridas"]))
    print("intentos / detectados  %d / %d" % (t["intentos"], t["detectados"]))
    if datos["ttd"]:
        print("ttd mediana %.3fs, media %.3fs, max %.3fs"
              % (datos["ttd"]["mediana"], datos["ttd"]["media"], datos["ttd"]["max"]))
    esc = datos["escalera"]
    print("fugas sin tocar la red  %d de %d" % (esc["fugas_sin_red"], esc["fugas"]))
    if datos["canales"]:
        print("canales de entrega (%s):" % datos["canales"]["lote"])
        for f in datos["canales"]["filas"]:
            print("  %-34s %2d/%-3d %5.1f%%"
                  % (f["canal"], f["nivel5"], f["corridas"], (f["tasa"] or 0) * 100))
    for g in datos["guardrail"]:
        print("guardrail %-5s con %d/%d vs sin %d/%d  %+.1f pts  Fisher p=%.4f  %s"
              % (g["etiqueta"], g["con_harness"]["nivel5"], g["con_harness"]["corridas"],
                 g["sin_harness"]["nivel5"], g["sin_harness"]["corridas"],
                 g["diferencia_pts"], g["fisher_p"],
                 "separa" if g["separa"] else "NO separa"))
    if datos["lineas_corruptas"]:
        print("lineas corruptas    %d" % len(datos["lineas_corruptas"]))

    if args.check:
        print("\n--check: no se escribio nada")
        return

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    print("\nescrito %s (%.1f KB)" % (args.out, os.path.getsize(args.out) / 1024))
    render(datos)


if __name__ == "__main__":
    main()
