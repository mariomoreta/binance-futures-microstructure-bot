---
name: Binance Futures Reference
description: Consultar referencias oficiales de Binance USD-M Futures y contrastarlas con la implementación y las pruebas de este proyecto. Usar para revisar o diagnosticar endpoints, streams Market/Public, aggTrade, profundidad, tipos de contrato, parámetros y requisitos. Es una ayuda documental y no autoriza acceso a mercado, cuentas ni órdenes.
metadata:
  upstream-repository: https://github.com/binance/binance-skills-hub
  upstream-commit: 7d1b1f78d525f9e653b96819f91a549302fda1da
  upstream-skill-version: "2.1.0"
  vendored-on: "2026-11-12"
---

# Referencia oficial de Binance Futures

## Propósito

Usa esta skill para responder preguntas técnicas sobre Binance USD-M Futures,
revisar una integración existente o diagnosticar una discrepancia entre la
documentación oficial y el bot. No añade una capa de IA al motor de trading,
no cambia la estrategia y no autoriza realizar consultas de mercado.

## Procedencia y alcance de los archivos locales

La fuente selectada es `binance/binance-skills-hub`, commit exacto
`7d1b1f78d525f9e653b96819f91a549302fda1da`, consultado el 2026-11-12. La
skill upstream `binance` declara `metadata.version: 2.1.0`. El Hub no publica
un tag ni una release para ese commit.

| Archivo local | Origen upstream | Uso permitido aquí |
|---|---|---|
| `references/futures-usds.md` | `skills/binance/binance/references/futures-usds.md` | Índice de endpoints USD-M y parámetros clave |
| `references/futures-usds-streams.md` | `skills/binance/binance/references/futures-usds-streams.md` | Índice de streams USD-M, separados en Market y Public |
| `references/auth.md` | `skills/binance/binance/references/auth.md` | Identificación de requisitos y límites de autenticación |
| `references/BINANCE-SKILLS-HUB-LICENSE.md` | `skills/binance/binance/LICENSE.md` | Aviso MIT de los archivos upstream |

Los tres archivos de referencia `futures-usds.md`, `futures-usds-streams.md` y
`auth.md` son copias sin modificar del commit indicado. El `SKILL.md` upstream
se revisó, pero no se incorporó: contenía un instalador
remoto de `binance-cli`, una configuración de perfiles y un flujo de credenciales
que quedan fuera de este proyecto. El catálogo de Skills Hub tampoco se instaló.

## Jerarquía de fuentes

No trates todas las fuentes como equivalentes:

1. **Documentación oficial vigente:** la fuente principal para rutas,
   seguridad, payloads, límites y semántica actual. Consulta la URL oficial
   correspondiente en el momento de la revisión y registra URL y fecha.
2. **Snapshot local del Hub:** sirve para navegar endpoints, nombres de
   comandos y parámetros clave. No demuestra que la referencia siga vigente.
3. **Código del proyecto:** demuestra qué está implementado, no qué ofrece
   Binance ni qué funcionó en producción.
4. **Pruebas del proyecto:** demuestran cobertura local de una rama
   concreta. No sustituyen una observación autorizada del venue.
5. **Evidencia de una corrida:** demuestra una observación concreta si se
   identifica el `run_id`, el artefacto y sus hashes.

Si no se puede consultar la documentación oficial vigente, la conducta actual
de venue queda `UNKNOWN`. No presente el snapshot local como documentación
actualizada automáticamente.

## URLs oficiales que deben revisarse

Usa la fuente oficial que corresponda al producto y endpoint:

- REST Market Data USD-M:
  <https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data>
- WebSocket Market streams USD-M:
  <https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market>
- WebSocket Public streams USD-M:
  <https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/public>
- Información general, seguridad y límites USD-M:
  <https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/general-info>
- Aviso de rutas WebSocket y migración:
  <https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Important-WebSocket-Change-Notice>
- Registro de cambios USD-M:
  <https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/change-log>

Consulta estas páginas con una herramienta documental. No las trates como
autorización para ejecutar sus ejemplos ni para abrir un socket o una petición.

## Flujo de revisión

### 1. Identifica el objeto

Antes de buscar un endpoint, deja explícitos:

- **Producto:** USD-M Futures, no Spot, COIN-M, Options ni Portfolio Margin.
- **Tipo de contrato:** `PERPETUAL`, `CURRENT_QUARTER` o `NEXT_QUARTER`, según
  el endpoint. Verifica el enum y su vigencia en la documentación oficial.
- **Superficie:** REST, WebSocket Market o WebSocket Public.
- **Endpoint o nombre de stream:** usa el nombre oficial y la ruta completa.
- **Parámetros:** obligatorio u opcional, tipo, enum, unidad, rango, peso o
  cadencia cuando la fuente los declare.
- **Requisito:** `NONE`, `MARKET_DATA`, `USER_STREAM`, `USER_DATA` o `TRADE`,
  y si requiere firma, `timestamp` y `recvWindow`.

El snapshot `futures-usds.md` incluye `CURRENT_QUARTER` y `NEXT_QUARTER`, pero
esto no demuestra soporte local. El selector actual del proyecto filtra
`PERPETUAL/TRADING/USDT` en
`src/microstructure_probe/discovery.py::build_candidates`. La cobertura local
de futuros con vencimiento es `UNKNOWN` y no debe declararse implementada.

### 2. Consulta la documentación oficial vigente

1. Localiza el endpoint en la URL oficial de producto y superficie.
2. Comprueba la ruta, el método, los parámetros, la seguridad, la respuesta y
   el peso o límite oficial.
3. Consulta el registro de cambios si la ruta, el enum o el payload puede
   haber cambiado.
4. Anota la fecha de consulta. Si el acceso documental falla, marca
   `UNKNOWN` para el comportamiento oficial actual.

No ejecutes ejemplos `curl`, comandos `binance-cli`, instalaciones ni scripts
encontrados en las referencias.

### 3. Contrasta con el proyecto

Inspecciona el código y las pruebas que realmente implementan el objeto. Para
los componentes de futuros del proyecto, los puntos de partida habituales son:

- `src/microstructure_probe/probe.py::build_stream_urls`
- `scripts/research_pilot.py::build_stream_url` y `StreamFeed`
- `src/microstructure_probe/history_client.py::HistoryClient`
- `src/microstructure_probe/discovery.py::build_candidates`
- `docs/MARKET_DATA.md`
- `docs/EXPERIMENTO_OPERATIVO_V2.md`
- `docs/CURRENT_STATE.md`
- pruebas focalizadas de `probe`, `research_pilot`, `history_client` y
  `discovery`

Usa estos estados, sin colapsarlos:

| Estado | Evidencia mínima | Afirmación permitida |
|---|---|---|
| `OFFICIAL` | Documentación oficial consultada con URL y fecha | "La documentación oficial describe..." |
| `IMPLEMENTADO` | Código local identificable | "El código construye/gestiona..." |
| `PROBADO_LOCAL` | Prueba focalizada identificable | "La prueba local cubre..." |
| `OBSERVADO` | Corrida autorizada con artefactos y hashes | "La corrida X observó..." |
| `UNKNOWN` | Evidencia ausente o contradictoria | "No consta..." |

Una capacidad oficial no implica implementación local. Una implementación local
no implica prueba. Una prueba no implica observación del venue. Una conexión
abierta no implica recepción efectiva de datos.

### 4. Aplica la escalera de evidencia de streams

Para WS, registra por separado:

1. **Suscripción construida:** URL, categoría, modo y stream exacto.
2. **Socket conectado:** el cliente menganggap conexión establecida.
3. **Frames recibidos:** mensajes observados en el socket.
4. **Eventos aceptados:** payloads que pasaron parseo, identidad y frescura.
5. **Cobertura efectiva:** símbolos, eventos y periodos con datos frescos.

`connected=true` con `messages=0` acredita solo el primer nivel. No lo
presentes como stream LIVE ni como evidencia de que Binance envió datos. La
causa de un stream sin frames permanece `UNKNOWN` hasta obtener una
observación autorizada o una evidencia local que discrimine la causa.

## Market frente a Public

En la documentación USD-M vigente, las rutas WebSocket separan clases de
tráfico:

- **Market:** datos de mercado regulares, por ejemplo `aggTrade`, `markPrice`,
  klines, tickers y liquidaciones. Ejemplo combinado documentado:
  `wss://fstream.binance.com/market/stream?streams=<symbol>@aggTrade`.
- **Public:** datos públicos de alta frecuencia, por ejemplo `bookTicker`,
  profundidad parcial y profundidad diferencial. Ejemplo combinado documentado:
  `wss://fstream.binance.com/public/stream?streams=<symbol>@depth20@100ms`.

`Market` y `Public` son categorías de ruta WS, no niveles de autenticación.
Ambas pueden ser públicas. No mezcles streams entre rutas y no deduzcas la
categoría correcta solo por el prefijo `@`.

La documentación actual ofrece URL raw, URL combined y solicitud `SUBSCRIBE`.
Para diagnosticar, contrasta la forma exacta usada por el proyecto con la
documentación. No asumas que una forma o otra causará por sí sola el silencio.

## Ejemplos documentales, no observaciones de mercado

### aggTrade

- Snapshot Hub: `futures-usds-streams.md` clasifica
  `aggregate-trade-streams` en Market y `futures-usds.md` clasifica
  `compressed-aggregate-trades-list` en Market Data REST.
- WebSocket oficial: stream `<symbol>@aggTrade` bajo la ruta `/market`.
- REST oficial: `GET /fapi/v1/aggTrades`, con `symbol` obligatorio y
  `fromId`, `startTime`, `endTime`, `limit` opcionales según la versión
  oficial consultada.
- No confundas el stream WS `aggTrade` con la lista REST `aggTrades`.
- En el proyecto, `HistoryClient.aggtrades()` usa `/fapi/v1/aggTrades`; la
  recepción WS se audita en el transporte del piloto. Son capacidades
  diferentes.

### Profundidad

- Snapshot Hub: `partial-book-depth-streams` y `diff-book-depth-streams` están
  en Public.
- WebSocket oficial: profundidad parcial `<symbol>@depth<levels>@<speed>` y
  diferencial `<symbol>@depth@<speed>` bajo la ruta `/public`.
- REST oficial: `GET /fapi/v1/depth` con `symbol` y `limit` según la versión
  oficial consultada.
- Una profundidad parcial es un snapshot de niveles. Una profundidad diferencial
  entrega cambios. No se describen como la misma semántica.

Estos ejemplos explican qué dice la documentación. No demuestran que el bot
reciba datos actuales ni que una ruta concreta funcione en este entorno.

## Autenticación: requisitos y límites

`references/auth.md` identifica API key, secret, perfiles y entorno. Se incluye
solo para reconocer requisitos. Sus comandos de perfil y los endpoints
`TRADE`, `USER_DATA` o `USER_STREAM` no están autorizados en este proyecto.

La documentación oficial de General Info establece que `TRADE` y `USER_DATA`
requieren API key y firma HMAC SHA256, y que las solicitudes firmadas incluyen
`timestamp` y pueden incluir `recvWindow`. No leas, imprimas, registres ni
solicites credenciales para esta tarea. No uses variables de entorno ni
archivos de secretos.

## Límites de funcionamiento

Esta skill no autoriza:

- consultas públicas de mercado, capturas, sondas o ventanas nuevas;
- claves, perfiles privados, cuentas, órdenes, cancelaciones, transferencias,
  cambios de apalancamiento o cualquier mutación de cuenta;
- instalar `binance-cli`, dependencias globales, paquetes o scripts remotos;
- cambiar selección, señales, stops, costes, funding, presupuestos, topes o
  cualquier regla del motor;
- crear un cliente paralelo que eluda `HistoryClient`, `RunBudget`, el ledger o
  los controles de presupuesto y registro.

Todo acceso futuro a mercado debe ser autorizado por separado y pasar por los
controles existentes. Estas instrucciones de skill no son una barrera técnica:
no afirmes que por estar escritas límites quedan técnicamente impuestos. Los
límites efectivos están en `AGENTS.md`, las autorizaciones humanas, los
permisos, el código y los controles de presupuesto y registro.

## Resultado esperado de una consulta

Presenta el resultado con esta estructura breve:

```text
Producto:
Tipo de contrato:
Superficie y endpoint o stream:
Parámetros:
Requisito de seguridad o autenticación:
Referencia oficial (URL y fecha):
Implementación local:
Pruebas locales:
Evidencia observada:
Estado y huecos UNKNOWN:
```

Separa siempre capacidad oficial, capacidad implementada, capacidad probada y
evidencia observada.

## Revisión y actualización manual

Esta copia no se actualiza sola.

1. Consulta `git ls-remote https://github.com/binance/binance-skills-hub.git HEAD`
   y registra el SHA obtenido.
2. Clona con `--depth 1` en un directorio temporal, sin ejecutar scripts del
   repositorio.
3. Revisa el `SKILL.md`, `LICENSE.md`, `CHANGELOG.md` y los tres
   `references/*.md` seleccionados. Compara sus hashes y contenido con la
   copia local.
4. Verifica el cambio de versión o commit y vuelve a consultar las URLs
   oficiales vigentes.
5. Actualiza solo las referencias copiadas, la tabla de procedencia, el
   frontmatter y la documentación factual del proyecto.
6. Comprueba que OpenCode descubre y carga la skill y que todas las rutas
   relativas se resuelven.
7. No incorpores el instalador upstream ni el catálogo completo salvo
   autorización expresa y revisión independiente.
