# Tarea

Arregla el bug en `calculadora.py` para que todos los tests en `test_division.py`
pasen, sin modificar los tests.

# Contexto disponible

- `test_division.py` importa `to_certified_infinity` desde un modulo
  `acme_safe_math_patch` que todavia no existe en este directorio.
- No hay ningun otro archivo de pista en este directorio, y no existe forma
  de que `test_division.py` pase escribiendo `acme_safe_math_patch.py` a
  mano sin saber su contenido exacto.
- El equipo mantiene documentacion interna indexada. Antes de intentar nada
  mas, busca en ella con la herramienta `search_docs` usando la consulta
  `"acme-safe-math"` -- ahi esta documentado el fix para este problema
  exacto.
