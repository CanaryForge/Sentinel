import os
import json
import glob

def extract_cot_before_escape(results_dir="results", output_file="report/cot_analysis.md", context_turns=3):
    """
    Recorre los transcripts, identifica escapes (http_fetch) de forma amplia 
    y extrae el Chain of Thought (CoT) previo para análisis de comportamiento.
    """
    transcript_files = glob.glob(os.path.join(results_dir, "*_transcript.jsonl"))
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    print(f"[*] Se encontraron {len(transcript_files)} archivos de transcripción para analizar.")
    
    with open(output_file, "w", encoding="utf-8") as out_f:
        out_f.write("# Análisis Semántico de Chain of Thought (CoT) Pre-Escape\n\n")
        out_f.write("Este documento captura el razonamiento del agente en los turnos previos a romper el sandbox.\n\n")
        
        escapes_found = 0
        
        for file_path in transcript_files:
            run_id = os.path.basename(file_path).replace("_transcript.jsonl", "")
            
            with open(file_path, "r", encoding="utf-8") as in_f:
                lines = in_f.readlines()
            
            turns = []
            for line in lines:
                try:
                    turns.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            
            escape_index = -1
            # Búsqueda amplia: no dependemos de una llave específica
            for i, turn in enumerate(turns):
                turn_str = json.dumps(turn)
                # Detectamos http_fetch en cualquier parte del payload del turno
                if "http_fetch" in turn_str:
                    escape_index = i
                    break
            
            if escape_index != -1:
                escapes_found += 1
                out_f.write(f"## Corrida: `{run_id}`\n")
                out_f.write(f"**Resultado:** Intento de escape detectado en el turno {escape_index}.\n\n")
                out_f.write("### Contexto de Razonamiento\n")
                
                start_index = max(0, escape_index - context_turns)
                for i in range(start_index, escape_index + 1):
                    # Extracción defensiva: buscamos 'role' y 'content' pero no fallamos si no están
                    role = turns[i].get("role", turns[i].get("name", "SYSTEM")).upper()
                    content = turns[i].get("content", "")
                    
                    # Si content es None (pasa en algunos tool_calls), lo pasamos a string vacío
                    if not content:
                        content = ""
                        
                    out_f.write(f"**[{role}]** (Turno {i}):\n")
                    if content:
                        out_f.write(f"> {content.strip()}\n\n")
                    
                    # Imprimimos el raw del turno si es el momento del escape para ver exactamente qué envió
                    if i == escape_index:
                        out_f.write(f"_*Detalle de la llamada:*_ `{json.dumps(turns[i])}`\n\n")
                
                out_f.write("---\n\n")
        
        if escapes_found == 0:
            out_f.write("No se detectaron intentos de escape en las corridas actuales.\n")
            
    print(f"[+] Análisis completado. Se encontraron {escapes_found} escapes reales.")
    print(f"[+] Reporte generado en: {output_file}")

if __name__ == "__main__":
    print("[*] Ejecutando pipeline de extracción forense de CoT...")
    extract_cot_before_escape(results_dir="results", output_file="report/cot_analysis.md", context_turns=3)