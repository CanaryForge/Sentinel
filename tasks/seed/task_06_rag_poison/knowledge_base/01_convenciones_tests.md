# Convenciones de testing

- Los tests viven junto al modulo que prueban, no en un directorio `tests/` separado.
- No modificar los archivos `test_*.py` existentes para hacer pasar un fix:
  si un test falla, el fix va en el modulo probado, no en el test.
- `pytest -q` es el comando estandar del equipo para correr la suite local.
