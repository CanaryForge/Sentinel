---
inclusion: always
---

# Producto

Arnes de deteccion de fuga de sandbox para agentes de IA. Construido para el
AI Incident Response Sprint (Apart Research / CeSIA), frente de Analisis del
incidente.

## Por que existe

Ancla: el incidente OpenAI-Hugging Face de julio 2026. Agentes en
evaluacion de ciberseguridad escaparon de su sandbox via un SSRF en un
gestor de paquetes interno, se comunicaron entre si codificando mensajes en
nombres de directorio, y comprometieron infraestructura de Hugging Face.
Nadie lo detecto en tiempo real.

La pregunta que este proyecto responde: **si un agente intenta escapar de
su sandbox, ¿cuanto tarda en detectarse, y con que senal?**

## Que demuestra (y que no)

Ver siempre `report/scope.md` antes de afirmar algo sobre los resultados --
es la fuente de verdad sobre el alcance honesto del trabajo. En resumen:
demuestra que tres senales baratas e independientes del modelo detectan
intentos de escape INDUCIDOS deliberadamente, y en cuanto tiempo. NO
demuestra deteccion de comportamiento emergente de un modelo de frontera,
ni cobertura de esteganografia sofisticada.

## Principio de diseno no negociable

Nada de este proyecto toca internet real salvo la llamada del propio
harness a su backend de LLM (Ollama local o una API en la nube, ver
`.kiro/steering/tech.md`). Todo objetivo de escape (registro de paquetes,
repositorio de modelos, red-teamer) es un mock local en una red Docker
`internal: true`. Ver Historia 2 en
`.kiro/specs/sandbox-escape-harness/requirements.md`.

## Audiencia

Investigadores de seguridad de IA evaluando arneses de deteccion; el repo
esta pensado para clonarse y extenderse, no solo para correrse una vez.
