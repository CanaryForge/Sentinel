"""
Agente minimo de tool-calling, hablando el formato OpenAI-compatible de
chat completions (funciona tanto con el endpoint /v1/chat/completions de
Ollama como con cualquier endpoint OpenAI-compatible real).

Nota de diseno: el enunciado original describe "OpenCode CLI apuntando a
Ollama". Aqui se reemplaza por este loop propio porque las flags exactas de
OpenCode para forzar tool-calling contra un endpoint arbitrario no se pueden
verificar con confianza sin acceso a su documentacion actual, y un fallo
silencioso de CLI arruina las ~150 corridas. Este loop es deliberadamente
pequeno y auditable; cambiar el backend por OpenCode real es cuestion de
reemplazar este archivo y mantener el mismo contrato de entorno.
"""
import json
import os
import subprocess
import sys
import time
import uuid

import requests

from prompts import build_system_prompt

WORKSPACE = "/workspace"
RESULTS_DIR = "/results"
MAX_TURNS = int(os.environ.get("AGENT_MAX_TURNS", "15"))


def backend_config(run_id: str = "unknown"):
    """
    `base` siempre incluye el sufijo /v1 (convencion estandar OpenAI); chat()
    solo le agrega /chat/completions, para no depender de si el operador
    escribio o no el /v1 en OLLAMA_HOST/OPENAI_API_BASE.
    """
    backend = os.environ.get("AGENT_BACKEND", "ollama")
    if backend == "openai":
        base = os.environ["OPENAI_API_BASE"].rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        model = os.environ["OPENAI_MODEL"]
        headers = {"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}"}
        # OpenCode Go/Zen exigen desde 2026-09-06 un x-opencode-session estable
        # por conversacion (cualquier UUID sirve; aqui se deriva de RUN_ID para
        # que sea el mismo en toda la corrida). Inofensivo para otros backends
        # OpenAI-compatible, que simplemente ignoran el header.
        if "opencode.ai" in base:
            headers["x-opencode-session"] = str(uuid.uuid5(uuid.NAMESPACE_URL, run_id))
    else:
        base = os.environ.get("OLLAMA_HOST", "http://host.docker.internal:11434").rstrip("/") + "/v1"
        model = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
        headers = {}
    return base, model, headers


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lee un archivo de texto dentro de /workspace",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Escribe un archivo de texto dentro de /workspace",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "Lista un directorio dentro de /workspace",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "http_fetch",
            "description": "Hace una peticion HTTP saliente (GET o POST) a una URL",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "method": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Corre pytest sobre /workspace y devuelve la salida",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _safe_path(path: str) -> str:
    path = path or "."
    # El modelo a veces pasa rutas ya prefijadas con /workspace (lo ve en su
    # propio system prompt / en list_dir); si se le suma el prefijo nuevo se
    # duplica a /workspace/workspace/... Se detecta y se evita ese caso.
    if path == WORKSPACE or path.startswith(WORKSPACE + "/"):
        candidate = path
    else:
        candidate = os.path.join(WORKSPACE, path.lstrip("/"))
    resolved = os.path.normpath(candidate)
    if resolved != WORKSPACE and not resolved.startswith(WORKSPACE + os.sep):
        raise ValueError("path fuera de /workspace")
    return resolved


def tool_read_file(path):
    try:
        with open(_safe_path(path)) as f:
            return f.read()[:4000]
    except Exception as e:
        return f"ERROR: {e}"


def tool_write_file(path, content):
    try:
        p = _safe_path(path)
        os.makedirs(os.path.dirname(p) or WORKSPACE, exist_ok=True)
        with open(p, "w") as f:
            f.write(content)
        return "OK"
    except Exception as e:
        return f"ERROR: {e}"


def tool_list_dir(path="."):
    try:
        return json.dumps(os.listdir(_safe_path(path)))
    except Exception as e:
        return f"ERROR: {e}"


def tool_http_fetch(url, method="GET", body=None):
    # Este es el vector de egress que instrumentamos: sale por HTTP_PROXY
    # (el proxy de la Capa 2), a diferencia del heartbeat, que lo bypassea
    # a proposito.
    try:
        r = requests.request(method or "GET", url, data=body, timeout=10)
        return f"status={r.status_code}\n{r.text[:2000]}"
    except Exception as e:
        return f"ERROR: {e}"


def tool_run_tests():
    try:
        r = subprocess.run(
            ["pytest", "-q"], cwd=WORKSPACE, capture_output=True, text=True, timeout=60
        )
        return (r.stdout + r.stderr)[:4000]
    except Exception as e:
        return f"ERROR: {e}"


DISPATCH = {
    "read_file": lambda a: tool_read_file(a.get("path", "")),
    "write_file": lambda a: tool_write_file(a.get("path", ""), a.get("content", "")),
    "list_dir": lambda a: tool_list_dir(a.get("path", ".")),
    "http_fetch": lambda a: tool_http_fetch(a.get("url", ""), a.get("method", "GET"), a.get("body")),
    "run_tests": lambda a: tool_run_tests(),
}


def chat(base, model, headers, messages):
    # Bypassea el proxy de egress a proposito: el destino lo fija esta
    # configuracion (backend_config), no una tool call del modelo, asi que
    # no es parte de la superficie de escape que se esta auditando -- igual
    # que heartbeat.py.
    resp = requests.post(
        f"{base}/chat/completions",
        headers={**headers, "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "tools": TOOLS, "tool_choice": "auto"},
        timeout=120,
        proxies={"http": None, "https": None},
    )
    resp.raise_for_status()
    return resp.json()


def make_logger(run_id):
    paths = [
        os.path.join(WORKSPACE, "agent_transcript.jsonl"),  # para el canary_monitor (fs)
        os.path.join(RESULTS_DIR, f"{run_id}_transcript.jsonl"),  # para compute_ttd.py
    ]

    def log(entry):
        entry = {"ts": time.time(), **entry}
        line = json.dumps(entry, ensure_ascii=False)
        for p in paths:
            try:
                with open(p, "a") as f:
                    f.write(line + "\n")
            except Exception:
                pass

    return log


def main():
    run_id = os.environ.get("RUN_ID", "unknown")
    condition = os.environ.get("CONDITION", "con_harness")
    canary = os.environ.get("CANARY_TOKEN", "CNRY-unset")
    task = os.environ.get("TASK", "task_01_impossible")

    log = make_logger(run_id)

    task_path = f"/tasks/{task}.md"
    with open(task_path) as f:
        task_text = f.read()

    system_prompt = build_system_prompt(condition, canary, task_text)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Comienza a trabajar en la tarea."},
    ]

    base, model, headers = backend_config(run_id)

    for turn in range(MAX_TURNS):
        try:
            data = chat(base, model, headers, messages)
        except Exception as e:
            print(f"[agent] error de backend en turno {turn}: {e}", file=sys.stderr)
            log({"turn": turn, "role": "error", "detalle": str(e)})
            break

        choice = data["choices"][0]
        msg = choice["message"]
        messages.append(msg)
        log({"turn": turn, "role": "assistant", "content": msg.get("content"),
             "tool_calls": msg.get("tool_calls")})

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            print(f"[agent] fin en turno {turn}: sin mas tool calls")
            break

        for tc in tool_calls:
            fn = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = DISPATCH.get(fn, lambda a: f"ERROR: herramienta desconocida {fn}")(args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", fn),
                "content": str(result),
            })
            log({"turn": turn, "role": "tool", "name": fn, "args": args,
                 "result": str(result)[:500]})
    else:
        print(f"[agent] limite de {MAX_TURNS} turnos alcanzado")
        log({"role": "info", "detalle": "max_turns_alcanzado"})


if __name__ == "__main__":
    main()
