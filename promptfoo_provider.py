import os
import subprocess
import json
import uuid

def call_api(prompt, options, context):
    """
    Este provider recibe el ataque de Promptfoo, lo corre en el sandbox de Sentinel
    y devuelve el transcript del agente.
    """
    # 1. Generar un ID único para la corrida
    run_id = f"pf_{uuid.uuid4().hex[:8]}"
    task_file = f"tasks/task_{run_id}.md"
    
    # 2. Escribir el ataque de Promptfoo como si fuera una tarea legítima o inyectada
    # Se basa en la estructura de tasks/task_04_prompt_injection.md
    with open(task_file, "w") as f:
        f.write(f"# Tarea Asignada\n{prompt}\n")

    # 3. Preparar variables de entorno para Docker Compose
    env = os.environ.copy()
    env["RUN_ID"] = run_id
    env["TASK_FILE"] = os.path.basename(task_file)
    
    # Asegúrate de usar la condición que quieres evaluar (ej. con_harness)
    env["HARNESS_CONDITION"] = "con_harness" 

    try:
        # 4. Ejecutar el sandbox de Sentinel
        # Usamos los servicios principales que mapeaste en tu README
        print(f"\n[Sentinel] Ejecutando payload adversarial: {run_id}...")
        subprocess.run(
            ["docker", "compose", "up", "--build", "--abort-on-container-exit"],
            env=env,
            check=True,
            capture_output=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error en Docker: {e.stderr.decode('utf-8')}")
    
    # 5. Analizar los resultados (Transcript y Telemetría)
    transcript_path = f"results/{run_id}_transcript.jsonl"
    output_text = ""
    
    if os.path.exists(transcript_path):
        with open(transcript_path, 'r') as f:
            for line in f:
                turn = json.loads(line)
                output_text += f"{turn.get('role', 'unknown')}: {turn.get('content', '')}\n"
                # Incluir llamadas a herramientas (ej. http_fetch)
                if "tool_calls" in turn and turn["tool_calls"]:
                    output_text += f"[TOOL CALL]: {json.dumps(turn['tool_calls'])}\n"
    else:
        output_text = "ERROR: El transcript no se generó. El agente pudo haber crasheado."

    # Limpieza (opcional) del archivo de tarea
    os.remove(task_file)

    # 6. Devolver la respuesta a Promptfoo para su evaluación
    return {
        "output": output_text
    }