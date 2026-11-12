# RECTIFICACIÓN del diagnóstico — ventana `exp-v2-ventana-1-20261112a`

**Fecha de la rectificación:** 2026-11-12 · **Estado:** `OFFICIAL` (contrato
documentado) + `IMPLEMENTADO` + `PROBADO_LOCAL` (corrección) · **Lo que
queda:** `UNKNOWN` (comportamiento real del venue para la URL antigua).

Este documento **no reescribe** la corrida ni sus artefactos: la configuración
ejecutada sigue siendo la que fue, y el dataset original permanece intacto en
`C:\proyectos\binance-futures-data\exp-v2-ventana-1-20261112a`. Corrige una
afirmación publicada en [INFORRE-CIERRE.md](INFORRE-CIERRE.md).

---

## 1. Qué se rectifica

En el informe de cierre se publicó:

> «La URL reconstruida localmente (sin abrir conexión) es
> `wss://fstream.binance.com/stream?streams=<símbolo>@aggTrade/...` (20
> símbolos por generación), **la forma correcta del endpoint combinado**.»

**Esa afirmación es incorrecta.** `wss://fstream.binance.com/stream?streams=…`
es la **URL antigua**, retirada por el venue el 2026-04-23. La forma vigente
separa el tráfico por categoría:

| Conexión | URL correcta (documentada) | Stream del piloto |
|---|---|---|
| Libro | `wss://fstream.binance.com/public/stream?streams=<symbol>@depth20@100ms/…` | `depth20@100ms` |
| Flujo | `wss://fstream.binance.com/market/stream?streams=<symbol>@aggTrade/…` | `aggTrade` |

En la corrida, `build_stream_url()` añadía `/stream?streams=…` a la base que
se le pasó, y esa base fue la **raíz sin categoría** en ambas conexiones
(`ws_public_base = ws_market_base = wss://fstream.binance.com`, persistido en
`manifiesto.json` y `resumen.json` de la corrida). El resultado fue que el
piloto se suscribió a la **URL antigua** en los dos feeds.

## 2. Evidencia (sin abrir sockets ni endpoints públicos de mercado)

**2.1 Documentación oficial vigente (consultada 2026-11-12).**

- Aviso de rutas:
  <https://www.binance.com/en/support/announcement/detail/ebf9b0aa9eca4ff3804eef6fb09ba32a>
  («Binance USDⓈ-M Futures WebSocket System Upgrade Notice», 2026-03-06):
  tres bases dedicadas (`/public`, `/market`, `/private`); «Legacy WebSocket
  URLs will be permanently retired on **2026-04-23**».
- Registro de cambios (API Change Log):
  <https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Important-WebSocket-Change-Notice>
  (página modificada el 2026-11-12):
  - *Endpoint & Stream Mapping*: **Public** → `bookTicker`, `<symbol>@depth<levels>`
    (con `@100ms`); **Market** → `<symbol>@aggTrade`, `markPrice`, `kline`,
    `ticker`, `forceOrder`.
  - *Compatibility & Migration Guidance*: «After the upgrade, any connections
    not migrated will ONLY be able to receive data from
    `wss://fstream.binance.com/public`. Channels under `/market` and `/private`
    will stop pushing data.»
  - *Action Required*: «Switch base URLs to `/public`, `/market`, `/private`»;
    «Legacy URLs (`wss://fstream.binance.com/ws`,
    `wss://fstream.binance.com/stream`) will no longer be available.»
  - Para suscripciones combinadas, la documentación recomienda el modo
    `stream` (`?streams=`) — el mecanismo que ya usa el piloto.

**2.2 Precedente del propio repositorio (captura pública anterior, ya
autorizada y archivada).** `public-pilot-1h-20261106a`
(`docs/evidence/coordinacion-recepcion-20261106/captura_publica_20261106a/`),
mismo código de piloto, seis días antes:

| | 2026-11-06 (`/public` + `/market`) | 2026-11-12 (raíz antigua) |
|---|---|---|
| `ws.public.url_shape` | `wss://fstream.binance.com/public/stream` | `wss://fstream.binance.com/stream` |
| `ws.market.url_shape` | `wss://fstream.binance.com/market/stream` | `wss://fstream.binance.com/stream` |
| mensajes feed public | 26 192 | 149 742 |
| mensajes feed market (aggTrade) | **55 265** | **0** |
| `research_flow_10s` / `_1m` | 6 391 / 1 236 | **0 / 0** |
| observaciones / aptas | 216 / **168** | 232 / **0** |

**2.3 El propio piloto ya documentaba la separación.** El snapshot de
configuración del piloto dice: «depth20@100ms pertenece a /public; aggTrade a
/market: son dos conexiones distintas (docs oficiales, aviso de rutas)». La
divergencia estaba solo en las bases que se le pasaron al comando.

**2.4 Corrección de una etiqueta en evidencia histórica (no se reescribe).**
En `docs/evidence/coordinacion-recepcion-20261106/traza_captura_publica_20261106.md`,
la línea 25 describe «feeds: market (depth20@100ms) + public (aggTrade)»: las
etiquetas están invertidas respecto del código y del manifiesto de esa misma
captura (`/public` con `depth20@100ms`, `/market` con `aggTrade`). Se deja
constancia sin modificar el artefacto histórico.

## 3. Qué queda probado y qué NO

- **Probado (documental):** la configuración ejecutada era incompatible con la
  arquitectura vigente; las URLs antiguas se retiraron el 2026-04-23, es decir
  **cinco meses antes** de la ventana; el mapeo stream→categoría es el
  documentado; el mecanismo de suscripción por URL en modo `stream` es el
  documentado para suscripciones combinadas.
- **Hipótesis fuerte, NO causalidad pública demostrada:** la documentación
  dice que una conexión no migrada solo recibe datos de `/public` y que los
  canales de `/market` dejan de empujar datos. Eso **predice exactamente** la
  asimetría observada (libro sí, trades no) y encaja con el precedente del
  repo. Pero no se abrió ningún socket durante ni después de la corrida para
  comparar ambas formas de URL, así que **no se ha observado** el
  comportamiento del venue para la URL antigua. La causa raíz final sigue
  siendo **UNKNOWN**.
- **No se atribuye el fallo a Binance.** Lo que se constata es una
  incompatibilidad entre la configuración ejecutada y el contrato vigente; la
  parte que corresponde a la configuración es del lado de este proyecto.
- **No se afirma que el arreglo recupere recepción real.** Eso solo puede
  comprobarse con una comprobación pública autorizada (ver propuesta en
  `docs/TASK_QUEUE.md`).

## 4. Qué se corrigió (local, sin mercado público)

1. `scripts/research_pilot.py`:
   - `build_stream_url(base, streams, categoria)` construye la URL con la
     **categoría del feed** (`/public` para libro, `/market` para flujo),
     símbolos en minúsculas y nombre `aggTrade` intacto.
   - `normalizar_base_ws()` valida **antes de conectar**: base con esquema
     `ws/wss` y host, categoría cruzada, `/stream` ya incluido o ruta no
     compatible → `ValueError` explícito.
   - En modo público se exige host `fstream.binance.com`; base pública
     incompatible → error explícito (`base publica incompatible`).
   - El snapshot de configuración publica ahora `categorias` y
     `plantilla_url` efectivas.
2. `tests/test_research_pilot.py`: el proveedor loopback existente distingue
   `/public/stream` (libro) de `/market/stream` (aggTrade), rechaza rutas
   inexistentes y streams de categoría cruzada (cierre 1008, sin emitir dato)
   y lleva contadores separados por categoría.
3. `scripts/run_pilot_window.py` (nuevo): envoltorio de lanzamiento que espera
   la finalización real y **lee** el código de salida del proceso
   (`Popen.wait()`), persistiendo `stdout.log`, `stderr.log`, `exit_code.txt`
   y `launcher.json`. El código **nunca** se infiere de `phase=fin`, del stdout
   ni de un stderr vacío.
4. `tests/test_pilot_ws_rutas.py` (nuevo) y
   `tests/test_pilot_launcher_exit_code.py` (nuevo): contrato de rutas A–F y
   verificación del envoltorio con salidas 0 y no cero.

## 5. Lo que sigue sin comprobarse

- Que `/market/stream?streams=…@aggTrade` reciba frames **hoy** en este
  entorno: requiere una comprobación pública autorizada.
- Que la URL antigua haya dejado de servir datos de `/market` por la razón
  documentada, o por otra: no se observó.
- La vía A (espera contable, liquidaciones observadas, neto COMPLETO vs.
  CONDICIONADO) **sigue sin ejercitarse**: la ventana del 2026-11-12 fue
  INSUFICIENTE en datos.

## 6. Código de salida histórico

El exit code de `exp-v2-ventana-1-20261112a` sigue siendo **UNKNOWN**.
`exit_code.txt` quedó vacío (0 bytes) por el defecto del envoltorio anterior
(`Start-Process -PassThru` sin `Refresh()`). **No se rellena
retrospectivamente**: se conserva el artefacto tal cual y se corrige el
envoltorio para las próximas ejecuciones.
