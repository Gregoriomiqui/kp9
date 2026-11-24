# kp9

Cliente HTTP para la terminal, al estilo Postman y con navegación tipo **k9s**: se maneja con
el teclado, tiene una vista por recurso y una barra de comandos `:`.

Las colecciones son archivos **JSON** comunes, uno por request, así que puedes editarlos a mano
y versionarlos en git si quieres. Los secretos y el historial se guardan aparte, en `.kp9/`,
que no se versiona.

- Jerarquía **Grupo → Colección → Carpeta → Request**.
- Entornos con variables `{{var}}`, secretos fuera del repo y entornos protegidos.
- Auth: Bearer, Basic, API Key y OAuth2 client credentials (con caché del token).
- Árbol de colecciones en un sidebar ocultable, como en Postman, con teclado y ratón.
- Editor integrado de requests con autocompletado de `{{variables}}`, como en Postman.
- Historial navegable y re-ejecutable. Los datos sensibles se ocultan antes de guardarse.
- Importación de colecciones y entornos de Postman v2.1.

## Instalación en macOS

Elige una de estas opciones. En todas, después basta con escribir `kp9` en la terminal.

### Opción A: binario autónomo (no requiere Python)

```sh
tar -xzf kp9-0.1.0-macos-arm64.tar.gz
./kp9-0.1.0-macos-arm64/install.sh        # instala en ~/.local (sin sudo)
```

Si `~/.local/bin` no está en tu `PATH`, el instalador te dice qué línea agregar a `~/.zshrc`.
El binario sirve para la arquitectura del Mac donde se construyó: `arm64` en Apple Silicon y
`x86_64` en Intel. Para desinstalar: `rm -rf ~/.local/share/kp9 ~/.local/bin/kp9`.

### Opción B: wheel con uv

Necesitas [uv](https://docs.astral.sh/uv/). uv instala Python 3.11+ si no lo tienes.

```sh
uv tool install kp9-0.1.0-py3-none-any.whl
```

### Opción C: desde el código, en modo editable

```sh
git clone <este repo> kp9 && cd kp9
uv tool install --editable .
```

Los cambios al código se aplican la próxima vez que abras `kp9`.

### Construir los paquetes

```sh
uv build                          # dist/kp9-<versión>-py3-none-any.whl y .tar.gz
./packaging/build-macos.sh        # dist/kp9-<versión>-macos-<arch>.tar.gz (binario + install.sh)
```

`build-macos.sh` usa PyInstaller, que es una dependencia de desarrollo. Al terminar, comprueba
que el binario arranca.

## Inicio rápido

```sh
kp9
```

Eso es todo. La primera vez se crea el workspace por defecto en `~/kp9` y se abre la app. Con
`n` creas un grupo; con `Enter` entras en él y con `n` creas una colección, y dentro de ella un
request. Con `i` lo editas dentro de kp9 (escribe `{{` para ver las variables), con `e` lo
abres en tu `$EDITOR` y con `s` lo envías. El árbol de la izquierda muestra todo el workspace; `t` lo enfoca.

Para traer tus colecciones de Postman:

```sh
kp9 import ~/Downloads/coleccion.postman_collection.json \
  --group pagos \
  --env ~/Downloads/qa.postman_environment.json
kp9
```

### Dónde se guardan los datos (workspace)

`kp9` busca `workspace.json` en la carpeta actual y en sus carpetas padre. Si no encuentra
ninguno, usa el **workspace por defecto** `~/kp9` y lo crea la primera vez. Puedes cambiar esa
ruta con la variable de entorno `KP9_HOME`, por ejemplo `export KP9_HOME=~/apis` en
`~/.zshrc`. Así, escribir `kp9` desde cualquier carpeta abre la app. `kp9 import` usa la misma
regla.

Para tener un workspace por proyecto, por ejemplo dentro de un repo para versionarlo con git:

```sh
cd mi-proyecto && kp9 init     # crea workspace.json y agrega .kp9/ a .gitignore
kp9                            # dentro de esa carpeta, abre ese workspace
```

Para abrir un workspace concreto desde cualquier lugar: `kp9 --workspace /ruta/al/workspace`.

### CLI

| Comando | Qué hace |
|---|---|
| `kp9 [-w RUTA]` | Abre la TUI |
| `kp9 init [CARPETA] [--name NOMBRE]` | Crea un workspace (por defecto en la carpeta actual) |
| `kp9 import COLECCION.json -g GRUPO [-e ENTORNO.json ...]` | Importa una colección y, opcionalmente, uno o más entornos de Postman |

## Uso de la TUI

```
┌ Workspace: mis-apis        Env: <qa>   Grupo: pagos ───────────────────────────────────┐
│ <1> grupos  <2> colecciones  <E> env  <t> árbol  <ctrl+b> ocultar  <?> ayuda           │
├─ Árbol ───────────────────┬─ Requests(pagos/checkout-api/carrito)[2] ──────────────────┤
│ ▼ Pagos                   │ METHOD  NAME                URL                       LAST │
│   ▼ Checkout API          │ POST    Agregar al carrito  {{baseUrl}}/v1/cart/items 201  │
│     ▼ carrito             │ GET     Ver carrito         {{baseUrl}}/v1/cart       200  │
│         POST Agregar al…  │                                                            │
│         GET  Ver carrito  │                                                            │
│       GET  Buscar         │                                                            │
├───────────────────────────┴────────────────────────────────────────────────────────────┤
│ <grupos> <checkout-api> <carrito>                                                      │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

Si el entorno activo es protegido, la barra superior se pone roja. El panel que tiene el foco
se marca con borde ámbar.

### Teclas

| Tecla | Acción |
|---|---|
| `Enter` | Abrir el elemento seleccionado; en Entornos, activar ese entorno |
| `Esc` | Volver, o cancelar el request en curso |
| `1` / `2` | Ir a grupos / colecciones |
| `E` | Entornos |
| `t` | Ir al árbol lateral; si ya tiene el foco, lo oculta (ver abajo) |
| `Ctrl-B` | Mostrar u ocultar el árbol lateral |
| `h` | Historial |
| `:` | Barra de comandos (con autocompletado) |
| `/` | Filtrar la tabla, o el body de la respuesta en el detalle |
| `s` / `Ctrl-R` | Enviar el request (en el detalle) |
| `c` | Copiar el request como `curl` |
| `y` | Copiar el body de la respuesta |
| `r` | Re-ejecutar (en el historial) |
| `i` | Editor integrado del request, con autocompletado de `{{variables}}` (ver abajo) |
| `n` / `e` / `d` | Crear / editar / borrar (pide confirmación). Con `n`, un nombre que termina en `/` crea una carpeta |
| `?` | Ayuda |

### Árbol de colecciones (sidebar)

A la izquierda siempre está el árbol con todo el workspace, como la barra lateral de Postman.
Se puede ocultar para dejarle toda la pantalla a la vista principal:

- `t` (o `:tree`) mueve el foco al árbol y lo muestra si estaba oculto. Si el árbol ya tiene el
  foco, `t` lo oculta.
- `Ctrl-B` lo muestra u oculta en cualquier momento.
- `Esc` en el árbol devuelve el foco a la vista principal (o quita el filtro, si hay uno).


```
▼ Pagos
  ▼ Checkout API
    ▼ carrito
        POST Agregar al carrito
        GET  Ver carrito
      GET  Buscar
▶ Usuarios
```

| Tecla / ratón | Acción |
|---|---|
| `↑` `↓` o `j` `k` | Moverse |
| `→` o `l` | Desplegar |
| `←` o `h` | Plegar; sobre un nodo ya plegado, sube al padre |
| `Enter` o clic | En un request: abrirlo en la vista principal. En un grupo, colección o carpeta: plegar o desplegar |
| `Espacio` | Plegar o desplegar |
| `/` | Con el foco en el árbol: filtrar por nombre de request (muestra las coincidencias con sus carpetas) |
| `i` | Abrir el request seleccionado en el editor integrado |
| `e` | Editar el elemento seleccionado en `$EDITOR` |
| `Esc` | Quitar el filtro, o volver a la vista principal |

Al abrir un request desde el árbol, la vista principal queda en grupos > colección > carpetas >
detalle, así que `Esc` sube por esa ruta. Si abres un request desde la tabla, el cursor del árbol
se mueve a ese request. Si los archivos cambian, el árbol se recarga y conserva los nodos
plegados y la posición del cursor.

### Comandos `:`

| Comando | Acción |
|---|---|
| `:groups` | Ir a grupos |
| `:col <nombre>` | Abrir una colección |
| `:env <nombre>` | Activar un entorno |
| `:tree` | Abrir el árbol de colecciones |
| `:history` | Ir al historial |
| `:import <archivo>` | Importar una colección o un entorno de Postman al grupo actual |
| `:q` | Salir |

### Editor integrado y autocompletado de variables

`i`, desde el detalle de un request, la lista de requests o el árbol, abre un editor dentro de
kp9 con el método, la URL, los params, los headers, el tipo de body y el body.

Al escribir `{{` en cualquier campo aparece la lista de variables disponibles para ese
request, como en Postman:

```
URL  {{baseUrl}}/v1/cart/{{s█
                         ┌──────────────────────────────────────┐
                         │ sku        SKU-1           env qa     │
                         │ sessionId  ••••            env qa     │
                         └──────────────────────────────────────┘
```

- Cada variable muestra su valor y la capa de donde viene (env, carpeta, colección o grupo),
  según la misma precedencia que se usa al enviar. Los secretos aparecen como `••••`.
- Al seguir escribiendo se filtra la lista: primero las que empiezan con lo escrito, después
  las que lo contienen.
- `↑`/`↓` eligen, `Tab` o `Enter` insertan `nombre}}` (sin duplicar `}}` si ya estaba) y
  `Esc` cierra la lista.

Formato de los campos:

- **Params y headers:** uno por línea, `nombre: valor`. Las líneas vacías y las que empiezan
  con `#` se ignoran.
- **Body:** según el tipo. `json` es JSON tal cual. En `form-urlencoded` y `multipart`, un
  objeto JSON `{"campo": "valor"}`, y en `multipart` un valor `"@~/ruta"` sube ese archivo.
  `text` va tal cual.

`Ctrl+S` guarda. Si algo no es válido, por ejemplo un JSON mal formado, el editor muestra el
error con línea y columna y no guarda. `Esc` cierra el editor y, si hay cambios sin guardar,
pregunta antes de descartarlos. El nombre, la descripción y el auth del request se conservan;
para cambiarlos, usa `e`.

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

## Solución de problemas

| Síntoma | Solución |
|---|---|
| `zsh: command not found: kp9` | Agrega `export PATH="$HOME/.local/bin:$PATH"` a `~/.zshrc` y abre una terminal nueva |
| macOS dice que no puede verificar el desarrollador | `xattr -dr com.apple.quarantine ~/.local/share/kp9`. `install.sh` ya lo hace por ti |
| `e` no abre el editor, o vuelve enseguida sin cambios | Define `EDITOR`, por ejemplo `export EDITOR=nvim`. Con un editor gráfico, usa la opción que lo hace esperar: `EDITOR="code -w"` |
| `{{baseUrl}} no definida (sin entorno activo)` | Activa un entorno con `E` + `Enter` o `:env <nombre>`, o define `defaultEnv` en `workspace.json` |
| `{{x}} no definida en qa` | Agrega la variable al entorno. Si es un secreto, pon su valor en `.kp9/secrets.json` |
| Un archivo aparece con ⚠ | Su JSON es inválido. El mensaje indica archivo:línea:columna; `e` lo abre para corregirlo |
| Al escribir `{{` no aparece la lista | Solo aparece si hay variables para ese request. Activa un entorno (`E` + `Enter`) o define variables en el grupo, la colección o la carpeta. La lista funciona en el editor integrado (`i`), no en `$EDITOR` |
| `Request URL is missing an 'http://' or 'https://' protocol` | La URL resuelta no empieza con `http://` o `https://`. Revisa la URL o el valor de `baseUrl` en el entorno. Los espacios al inicio y al final se quitan solos |

## Desarrollo

```sh
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

El empaquetado para macOS está en `packaging/`: `build-macos.sh`, `install.sh` y el punto de
entrada para PyInstaller. Los artefactos quedan en `dist/` y los intermedios en `build/`; las
dos carpetas están ignoradas por git.

El código está en `src/kp9/`. El núcleo (`model`, `store`, `resolve`, `auth`, `httpclient`,
`history`, `runner`, `importer`, `variables`, `form`) no depende de la interfaz. La TUI, en `src/kp9/tui/`, es una
capa delgada encima del núcleo; el editor integrado está en `request_editor.py` y el
autocompletado en `completion.py`.

El diseño está en `docs/superpowers/specs/` y el plan de implementación en
`docs/superpowers/plans/`.
