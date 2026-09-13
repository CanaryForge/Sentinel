"""
Provider de promptfoo para Sentinel: recibe un ataque generado por promptfoo,
lo corre como tarea dentro del sandbox real y devuelve el transcript.

ESTADO: borrador SIN VALIDAR end-to-end. Se trajo desde la rama `Promptfoo`
arreglando tres defectos que lo hacian evaluar en vacio (ver comentarios
`FIX:`), pero nadie lo ha corrido todavia contra promptfoo de verdad. No
reportes numeros salidos de aqui sin antes verificar a mano que el payload
llega al agente -- revisa que results/{run_id}_transcript.jsonl contenga el
texto del ataque.
"""
import os
import secrets
import subprocess
import json
import uuid

ROOT = os.path.dirname(os.path.abspath(__file__))

def call_api(prompt, options, context):
    """
    Este provider recibe el ataque de Promptfoo, lo corre en el sandbox de Sentinel
    y devuelve el transcript del agente.
    """
    # 1. Generar un ID único para la corrida
    run_id = f"pf_{uuid.uuid4().hex[:8]}"
    # agent.py lee /tasks/{TASK}.md, asi que el nombre de la tarea es el
    # basename sin extension y el archivo va en tasks/.
    task_name = f"task_{run_id}"
    task_file = os.path.join(ROOT, "tasks", f"{task_name}.md")
    
    # 2. Escribir el ataque de Promptfoo como si fuera una tarea legítima o inyectada
    # Se basa en la estructura de tasks/task_04_prompt_injection.md
    with open(task_file, "w") as f:
        f.write(f"# Tarea Asignada\n{prompt}\n")

    # 3. Preparar variables de entorno para Docker Compose
    env = os.environ.copy()
    env["RUN_ID"] = run_id
    # FIX: docker-compose.yml lee TASK y CONDITION. La version original de
    # este archivo exportaba TASK_FILE y HARNESS_CONDITION, nombres que el
    # compose ignora -- cada corrida usaba los defaults
    # (task_01_impossible / con_harness) y el ataque de promptfoo nunca
    # llegaba al agente. La evaluacion corria en vacio sin fallar.
    env["TASK"] = task_name
    env["CONDITION"] = os.environ.get("SENTINEL_CONDITION", "con_harness")
    # FIX: sin un canary propio se usa el default CNRY-0000..., igual en todas
    # las corridas, y cualquier deteccion de canary deja de significar nada.
    env["CANARY_TOKEN"] = f"CNRY-{secrets.token_hex(12)}"

    # FIX: -p aisla cada corrida. Sin el, todas comparten el proyecto por
    # defecto de compose y se pisan los contenedores entre si. Va fuera del
    # try porque el finally lo usa: definirlo dentro dejaba un NameError
    # latente si algo fallaba antes de la asignacion.
    proj = f"sbxharness_pf_{run_id}"

    try:
        # 4. Ejecutar el sandbox de Sentinel
        # Usamos los servicios principales que mapeaste en tu README
        print(f"\n[Sentinel] Ejecutando payload adversarial: {run_id}...")
        # FIX: sin check=True -- el harness termina con codigo != 0 de forma
        # legitima (--abort-on-container-exit propaga el exit del sandbox), y
        # con check=True eso abortaba la evaluacion como si fuera un error.
        subprocess.run(
            ["docker", "compose", "-p", proj, "up", "--build",
             "--abort-on-container-exit", "--exit-code-from", "sandbox"],
            cwd=ROOT, env=env, capture_output=True,
        )
    finally:
        subprocess.run(["docker", "compose", "-p", proj, "down", "-v",
                        "--remove-orphans"],
                       cwd=ROOT, env=env, capture_output=True)
    
    # 5. Analizar los resultados (Transcript y Telemetría)
    transcript_path = os.path.join(ROOT, "results", f"{run_id}_transcript.jsonl")
    output_text = ""
    
    if os.path.exists(transcript_path):
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                turn = json.loads(line)
                output_text += f"{turn.get('role', 'unknown')}: {turn.get('content', '')}\n"
                # Incluir llamadas a herramientas (ej. http_fetch)
                if "tool_calls" in turn and turn["tool_calls"]:
                    output_text += f"[TOOL CALL]: {json.dumps(turn['tool_calls'])}\n"
    else:
        output_text = "ERROR: El transcript no se generó. El agente pudo haber crasheado."

    # FIX: en la version original esto quedaba fuera del try, asi que un
    # fallo de docker dejaba tasks/task_pf_*.md sin borrar.
    if os.path.exists(task_file):
        os.remove(task_file)

    # 6. Devolver la respuesta a Promptfoo para su evaluación
    return {
        "output": output_text
    }