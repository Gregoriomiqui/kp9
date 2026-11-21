# kp9

Cliente HTTP para la terminal con navegación estilo k9s. Las colecciones son archivos JSON.

## Instalación

```
uv tool install --editable .
```

## Uso

```
kp9 init mis-apis
cd mis-apis
kp9 import ~/Downloads/coleccion.json --group pagos --env ~/Downloads/qa.postman_environment.json
kp9
```

Teclas: `1` grupos · `2` colecciones · `E` entornos · `h` historial · `:` comando · `/` filtro ·
`Enter` abrir · `Esc` volver/cancelar · `s` enviar · `n`/`e`/`d` crear/editar/borrar ·
`c` copiar curl · `y` copiar body · `r` re-ejecutar · `?` ayuda.

## Desarrollo

```
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
```
