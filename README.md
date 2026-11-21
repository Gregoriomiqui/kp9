# kp9

Cliente HTTP para la terminal, al estilo Postman y con navegación tipo **k9s**: se maneja con
el teclado, tiene una vista por recurso y una barra de comandos `:`.

Las colecciones son archivos **JSON** comunes, uno por request, así que puedes editarlos a mano
y versionarlos en git si quieres. Los secretos y el historial se guardan aparte, en `.kp9/`,
que no se versiona.

- Jerarquía **Grupo → Colección → Carpeta → Request**.
- Entornos con variables `{{var}}`, secretos fuera del repo y entornos protegidos.
- Auth: Bearer, Basic, API Key y OAuth2 client credentials (con caché del token).
- Historial navegable y re-ejecutable. Los datos sensibles se ocultan antes de guardarse.
- Importación de colecciones y entornos de Postman v2.1.

## Instalación

Necesitas [uv](https://docs.astral.sh/uv/). uv instala Python 3.11+ si no lo tienes.

```sh
git clone <este repo> kp9 && cd kp9
uv tool install --editable .
```

Así queda disponible el comando `kp9`. Como es una instalación editable, los cambios al código
se aplican la próxima vez que abras `kp9`.

## Inicio rápido

```sh
kp9 init mis-apis              # crea el workspace (y .gitignore con .kp9/)
cd mis-apis
kp9 import ~/Downloads/coleccion.postman_collection.json \
  --group pagos \
  --env ~/Downloads/qa.postman_environment.json
kp9                            # abre la TUI
```

`kp9` busca `workspace.json` en la carpeta actual y en sus carpetas padre. Para usar otro
workspace: `kp9 --workspace /ruta/al/workspace`.

### CLI

| Comando | Qué hace |
|---|---|
| `kp9 [-w RUTA]` | Abre la TUI |
| `kp9 init [CARPETA] [--name NOMBRE]` | Crea un workspace (por defecto en la carpeta actual) |
| `kp9 import COLECCION.json -g GRUPO [-e ENTORNO.json ...]` | Importa una colección y, opcionalmente, uno o más entornos de Postman |

## Uso de la TUI

```
┌ Workspace: mis-apis        Env: <qa>   Grupo: pagos ──────────────────┐
│ <1> grupos  <2> colecciones  <E> env  <h> historial  <?> ayuda        │
├─ Requests(pagos/checkout-api/carrito)[3] ─────────────────────────────┤
│ METHOD  NAME                URL                         LAST          │
│ POST    Agregar al carrito  {{baseUrl}}/v1/cart/items   201 · 120ms   │
│ GET     Ver carrito         {{baseUrl}}/v1/cart         200 ·  85ms   │
├───────────────────────────────────────────────────────────────────────┤
│ <grupos> <checkout-api> <carrito>                                     │
└───────────────────────────────────────────────────────────────────────┘
```

Si el entorno activo es protegido, la barra superior se pone roja.

### Teclas

| Tecla | Acción |
|---|---|
| `Enter` | Abrir el elemento seleccionado; en Entornos, activar ese entorno |
| `Esc` | Volver, o cancelar el request en curso |
| `1` / `2` | Ir a grupos / colecciones |
| `E` | Entornos |
| `h` | Historial |
| `:` | Barra de comandos (con autocompletado) |
| `/` | Filtrar la tabla, o el body de la respuesta en el detalle |
| `s` / `Ctrl-R` | Enviar el request (en el detalle) |
| `c` | Copiar el request como `curl` |
| `y` | Copiar el body de la respuesta |
| `r` | Re-ejecutar (en el historial) |
| `n` / `e` / `d` | Crear / editar / borrar (pide confirmación). Con `n`, un nombre que termina en `/` crea una carpeta |
| `?` | Ayuda |

### Comandos `:`

| Comando | Acción |
|---|---|
| `:groups` | Ir a grupos |
| `:col <nombre>` | Abrir una colección |
| `:env <nombre>` | Activar un entorno |
| `:history` | Ir al historial |
| `:import <archivo>` | Importar una colección o un entorno de Postman al grupo actual |
| `:q` | Salir |

### Edición

`e` abre el JSON del elemento seleccionado (request, entorno, colección o grupo) en `$EDITOR`.
Si no está definido, usa `vi`. Si tu editor es gráfico, configúralo para que espere a que
cierres el archivo, por ejemplo `EDITOR="code -w"`. Al cerrar el editor, kp9 valida el archivo
y lo recarga. Si el JSON quedó inválido, te muestra el error y te ofrece reabrir el editor.

kp9 también recarga solo cuando los archivos cambian desde fuera, por ejemplo tras un `git pull`.

## Estructura del workspace

```
mis-apis/
├─ workspace.json              nombre, defaultGroup, defaultEnv, timeout, redactHeaders
├─ environments/
│  ├─ qa.json
│  └─ prod.json
├─ groups/
│  └─ pagos/
│     ├─ group.json            auth y variables heredables
│     └─ checkout-api/
│        ├─ collection.json    baseUrl, auth y variables de la colección
│        ├─ buscar.json        un archivo por request
│        └─ carrito/           una carpeta (se puede anidar sin límite)
│           ├─ folder.json     opcional: auth y variables de la carpeta
│           └─ agregar-al-carrito.json
└─ .kp9/                       local, ignorado por git
   ├─ secrets.json
   └─ history.db
```

Los nombres de archivos y carpetas son slugs. El nombre que ves en la TUI es el campo `name`.
Cualquier nodo acepta `"description"`.

### `workspace.json`

```json
{
  "name": "mis-apis",
  "defaultGroup": "pagos",
  "defaultEnv": "qa",
  "timeout": 30,
  "redactHeaders": ["X-Session"]
}
```

Todos los campos son opcionales salvo `name`. `timeout` va en segundos y por defecto es 30.
Sin `defaultEnv`, kp9 arranca con el primer entorno en orden alfabético.

### Request

```json
{
  "name": "Agregar al carrito",
  "method": "POST",
  "url": "{{baseUrl}}/v1/cart/items",
  "params": { "channel": "web" },
  "headers": { "Content-Type": "application/json" },
  "body": { "type": "json", "content": { "sku": "{{sku}}", "qty": 1 } },
  "auth": { "type": "inherit" }
}
```

- `method`: `GET` (por defecto), `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD` u `OPTIONS`.
- `body.type`: `none`, `json`, `text`, `form-urlencoded` o `multipart`. En `multipart`, un
  valor `"@~/ruta/archivo"` sube ese archivo.

### Auth

```json
{ "type": "bearer",    "token": "{{token}}" }
{ "type": "basic",     "username": "{{user}}", "password": "{{pass}}" }
{ "type": "apikey",    "key": "X-Api-Key", "value": "{{apiKey}}", "in": "header" }
{ "type": "oauth2-cc", "tokenUrl": "{{authUrl}}/token", "clientId": "{{cid}}",
  "clientSecret": "{{csecret}}", "scopes": ["read"] }
```

`inherit` (por defecto) toma el auth de la carpeta, colección o grupo más cercano. Si ninguno
lo define, se envía sin auth. `none` desactiva el auth explícitamente. En `apikey`, `in`
puede ser `header` o `query`.

### Entornos y secretos

```json
{
  "name": "prod",
  "protected": true,
  "variables": {
    "baseUrl": "https://api.example.com",
    "token": { "secret": true },
    "cid": "$ENV:KP9_PROD_CLIENT_ID"
  }
}
```

- `{ "secret": true }` solo declara la variable. Su valor va en `.kp9/secrets.json`, que se
  guarda con permisos `0600`:
  ```json
  { "prod": { "token": "..." } }
  ```
- `$ENV:NOMBRE` toma el valor de una variable de entorno del sistema.
- Un secreto vacío cuenta como variable no definida.
- `"protected": true` hace que kp9 pida confirmación antes de enviar cualquier método que no
  sea GET, HEAD u OPTIONS.

### Precedencia de variables

Como en Postman, **el entorno activo manda**:

**entorno activo > carpeta(s), de la más interna a la externa > colección > grupo**

Las variables de grupo, colección y carpeta funcionan como valores por defecto. `baseUrl` en
`collection.json` también cuenta como variable de colección. Las variables pueden referirse a
otras variables. Si hay una referencia circular, kp9 la reporta como error.

Si a un request le falta una variable, no se envía y kp9 muestra un mensaje como
`{{sku}} no definida en qa`.

## Historial

Cada envío queda en `.kp9/history.db`, incluidos los fallidos y los cancelados. Antes de
guardar, kp9 oculta (`••••`):

- los headers `Authorization`, `Cookie`, `Set-Cookie`, `X-Api-Key` y los que agregues en
  `redactHeaders`;
- cualquier valor secreto que aparezca en la URL, los headers o el body, también en sus formas
  URL-encoded o escapadas en JSON;
- las credenciales que agrega la auth (token Bearer u OAuth2, Basic en base64, API key), aunque
  el servidor las devuelva en la respuesta.

## Importación desde Postman

- Las carpetas de Postman pasan a ser directorios, y cada request un archivo JSON.
- Las variables de la colección van a `collection.json`, y el auth de colección, carpeta y
  request se convierte al formato de kp9.
- En los entornos, las variables de tipo `secret` van a `.kp9/secrets.json`.
- Lo que no está soportado (scripts, tests, tipos de auth desconocidos) se omite y aparece en
  un resumen al final. La importación no se interrumpe.
- Si un nombre se repite, kp9 nunca sobrescribe: crea `nombre-2.json`, `nombre-3.json`, etc.

## Desarrollo

```sh
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

El código está en `src/kp9/`. El núcleo (`model`, `store`, `resolve`, `auth`, `httpclient`,
`history`, `runner`, `importer`) no depende de la interfaz. La TUI, en `src/kp9/tui/`, es una
capa delgada encima del núcleo.

El diseño está en `docs/superpowers/specs/` y el plan de implementación en
`docs/superpowers/plans/`.
