# site/

Página pública del proyecto, la que se enlaza desde el paper.

## Regenerar

```
python3 site/build.py
```

Lee los cuatro corpus de `results/`, recalcula todo y escribe:

- `data.json`, el snapshot de agregados (también sirve para citar cifras)
- `index.html`, la página autocontenida que publica Vercel

Corre en unos 2 segundos. **Vuelve a correrlo cada vez que entren corridas
nuevas**: ninguna cifra de la página está escrita a mano, así que no hay nada
más que tocar.

## Por qué no reimplementa los agregados

`build.py` levanta el test client de Flask y llama a los mismos endpoints que
sirve `dashboard/app.py`, sin abrir un puerto ni arrancar el watchdog. Es
literalmente el mismo código. Este repo ya arrastró dos veces el bug de una
copia de la verdad que se quedó atrás:

- el exportador de timeline leía un solo directorio: 1509 de 4829 eventos
- `CORPUS_DIRS` apuntaba a directorios inexistentes: 70 de 150 corridas

Si la página y el panel llegaran a discrepar, sería porque alguien editó
`data.json` a mano.

## Editar contenido

El texto vive en `template.html`. `index.html` es **generado**: cualquier
cambio hecho ahí se pierde en el siguiente build.

## Despliegue

`vercel.json` en la raíz del repo ya declara `outputDirectory: site` y ningún
build command. Importar el repo en Vercel y desplegar, sin configurar nada
más. El repo puede seguir privado; el sitio sale público.
