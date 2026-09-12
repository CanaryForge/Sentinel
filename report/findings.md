# Hallazgos

Por completar despues de correr `orchestrator/run_experiment.py` y
`analysis/compute_ttd.py`. Estructura sugerida:

## Resumen

- Corridas totales: ?
- Tasa de intento de escape por condicion (con_harness vs sin_harness) y tarea
- TTD medio con IC 95% por condicion
- Que monitor detecto primero, y con que frecuencia

## Interpretacion

(Completar una vez existan resultados: el harness de produccion, ¿reduce la
tasa de intentos de escape, el tiempo hasta deteccion, o ambos? ¿Cual de las
tres senales resulto mas rapida en la practica, y coincide con la hipotesis
de diseno -egress deberia ser casi instantaneo, canary de filesystem depende
del intervalo de polling, heartbeat detecta ausencia, no el escape mismo-?)

## Limitaciones observadas

(Completar con lo que realmente paso: falsos positivos, corridas que
timeoutearon sin intentar nada, fallos del backend del modelo, etc.)

Ver `report/scope.md` para las limitaciones conocidas de antemano.
