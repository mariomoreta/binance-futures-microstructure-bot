# Ventana viva acotada por el camino real — `market-stream/v1` (PREPARADA, NO EJECUTADA)

Estado: **procedimiento escrito y probado con transporte controlado; la conexión
Binance continua NO se ha abierto en este bloque.** Requiere autorización humana
explícita y separada.

A diferencia del plan anterior (que hablaba directamente con el hub), la ventana
usa **el servicio existente** `scripts/market_stream_service.py` y se conecta a él
como un consumidor SSE más. No hay segundo servicio, segundo gestor ni segunda
copia de la lógica de adquisición.

Contrato: [`MARKET_STREAM_CONTRACT_V1.md`](MARKET_STREAM_CONTRACT_V1.md).
Script: `scripts/market_stream_window.py` (sin `--execute` solo imprime el plan).

## 1. Qué demuestra la ventana

Con Binance real, en una sola conexión y en el menor tiempo posible:

1. que la ruta pública `wss://fstream.binance.com/market` entrega `kline` para el
   par `(símbolo, intervalo)` suscrito, con la identidad y unidades esperadas;
2. la **cadencia real** de actualización de la vela en formación (la
   documentación pública es contradictoria: 1000–2000 ms frente a 250 ms) — se
   mide, no se asume;
3. que el cierre llega con `x=true` y `close_time_ms == open_time_ms + intervalo - 1`;
4. que la vela siguiente aparece en la misma secuencia (`open_time + intervalo`);
5. que esos mensajes atraviesan la cadena real hasta el BFF:
   `Binance → hub → servicio SSE → /api/v1/market-stream → /market-lab`;
6. que el panel del navegador declara `RECIBIENDO`/`LIVE` solo cuando se cumplen
   sus condiciones, que la vela nueva aparece **sin recargar** la página y que,
   al detener el servicio, `LIVE` desaparece y el histórico sigue visible.

No es una prueba de rentabilidad, señal, indicadores ni ejecución.

## 2. Cadena y consumidores

```text
wss://fstream.binance.com/market/stream?streams=btcusdt@kline_1m/minausdt@kline_1m
        │  1 conexión combinada
        ▼
KlineStreamHub  (anillo en memoria, 300 velas cerradas por stream)
        ▼
MarketStreamService  http://127.0.0.1:8791   (/health, /stream, /shutdown)
        ├──────────────► consumidor SSE "service" (MINAUSDT)             ← script
        └──► BFF Next  http://127.0.0.1:3020/api/v1/market-stream
                     ├──► consumidor SSE "bff" (BTCUSDT)                 ← script
                     └──► EventSource del gráfico en /market-lab         ← navegador
```

El primario (`BTCUSDT`) se consume por el **mismo camino que usa el gráfico**
(BFF); el servicio directo atiende el secundario. Así el script abre **2**
consumidores y el navegador ocupa el **tercero**: nunca hay más de 3.

El script orquesta y recoge evidencia; **no** importa el hub para la ejecución,
**no** crea otro servicio y **no** escribe velas.

### Corrección registrada antes de ejecutar (2026-10-22)

El presupuesto publicado en `ab753a1` declaraba «3 consumidores: servicio (2
símbolos) + BFF (1)» **sin contar al navegador**, lo que habría dado 4. Se
corrige sin ampliar el límite: el script baja a 2 (servicio=MINAUSDT, BFF=BTCUSDT)
y el navegador ocupa la tercera plaza. Además el script **espera** a que
`/health` muestre ese consumidor del navegador antes de abrir los suyos
(`--await-consumers 1`, 90 s); la espera exige además que **el único consumidor
sea el símbolo primario** (`BTCUSDT`), para no arrancar durante el cambio de
contrato del operador ni contar el `MINAUSDT` transitorio. Si no aparece, para
con `BROWSER_NOT_ATTACHED` sin abrir conexión con Binance. Los 2 s de espera a
que el servicio libere un consumidor cerrado (lectura perezosa, ~5 s) evitan
picos transitorios de 4.

## 3. Presupuesto de la ventana

| Parámetro | Valor | Por qué |
|---|---|---|
| Conexiones WS a Binance | **1** (combinada) | mínimo indispensable |
| Streams | **2** (`BTCUSDT` del trío + `MINAUSDT` fuera del trío) | identidad y aislamiento |
| Intervalo | `1m` | un solo cambio de minuto ya prueba provisional → cierre → siguiente |
| Duración máxima | **180 s** | garantiza ≥1–2 fronteras de minuto aunque se empiece justo después de una |
| Espera tras aceptar (`--hold-seconds`) | **20 s** | capturar el DOM sin alargar la ventana |
| Mensajes máximos (vela) | **1200** | ~3× el peor caso de 2 streams a 4/s durante 180 s |
| Eventos SSE máximos | **6000** | `candle`+`status`+`heartbeat` de 3 consumidores |
| Reconexiones máximas | **3** | por encima, se para y se declara |
| Consumidores SSE | **3** en total: 1 servicio (MINAUSDT) + 1 BFF (BTCUSDT) + 1 navegador en `/market-lab` | el navegador cuenta en el mismo presupuesto; `stats` por stream: BTCUSDT 2, MINAUSDT 1 |
| Espera al navegador | 90 s máx, exige `consumers=1` estable (2 muestras) antes de abrir los del script | garantiza que el tercer consumidor es el navegador y que no hay picos |
| `bars` por consumidor | 300 | mismo tamaño que el gráfico |
| Persistencia | ninguna | anillo en memoria |
| REST de snapshot | 0 (lectura de almacén existente, `allow_fetch=False`) | no descarga velas |
| REST de paginación (manual) | 1 petición ≤ 1000 velas | la hace el operador al pulsar "cargar anteriores" |
| REST de reparación de huecos | ≤ 2 páginas × 500 velas, ≤ 6/min | solo si aparece un hueco |
| Escrituras en DB canónica | **ninguna** | el script compara tamaño/mtime antes y después |
| Monitor del bot / Paper Lab | no se arranca, no se toca | observación pura |

Parada temprana: en cuanto se observa **provisional (≥2 actualizaciones) + cierre
+ vela siguiente** en el consumidor del servicio **y** al menos una vela por el
BFF, el script espera `--hold-seconds` y cierra. Si no, para por duración o
presupuesto y lo declara.

## 4. Procedimiento exacto (solo tras autorización)

### Paso 0 — Estado de partida

```powershell
cd C:\proyectos\binance-futures-microstructure-bot
git rev-parse --short HEAD
# servicio detenido y puerto libre
python -X utf8 scripts/market_stream_service.py --port 8791 --stop
Get-NetTCPConnection -LocalPort 8791 -ErrorAction SilentlyContinue
# dashboard sirviendo (instancia ya construida)
Invoke-WebRequest http://127.0.0.1:3020/market-lab -UseBasicParsing | Select-Object StatusCode
```

El preflight del script exige: puerto 8791 libre, `/api/v1/market-stream/status`
HTTP 200, y que el `BUILD_ID` de `frontend/.next/BUILD_ID` aparezca en el HTML
servido por 3020. Si algo falla, no se abre nada.

### Paso 1 — Plan (no abre red)

```powershell
$env:PYTHONPATH="src"
python -X utf8 scripts/market_stream_window.py
```

### Paso 2 — Abrir el gráfico ANTES de arrancar el servicio

En el navegador: `http://127.0.0.1:3020/market-lab`, contrato `BTCUSDT`, intervalo
`1m`. El panel mostrará `DESCONECTADO · servicio detenido` (correcto: aún no hay
servicio). **No recargues la página en toda la ventana**: el hook solo reintenta
al cambiar de contrato/intervalo, y la captura DOM exige `navigation_count = 1` y
`reload_count = 0`.

### Paso 3 — Ventana

```powershell
$env:PYTHONPATH="src"
python -X utf8 scripts/market_stream_window.py --execute `
    --symbols BTCUSDT,MINAUSDT --interval 1m --duration 180 --hold-seconds 20 `
    --max-messages 1200 --max-events 6000 --max-reconnects 3 `
    --browser-consumer --await-consumers 1 --await-timeout 90 `
    --out docs/evidence/market-stream-window-2026-10-22.json
```

El script arranca el servicio (sin consumidores, `attempts=0`), imprime
`servicio PID … en http://127.0.0.1:8791` y **espera**: no abre su conexión con
Binance hasta que `/health` muestre `consumers=1` y ese único consumidor sea
`BTCUSDT` (el navegador ya asentado). En ese momento cambia el contrato en el
panel (`MINAUSDT` y vuelve a `BTCUSDT`) para que el hook vuelva a consultar
`/status` y abra el `EventSource`; el cambio de contrato es una acción del
operador, no una reconexión automática. El panel debe pasar a `RECIBIENDO` y
mostrar `LIVE`. Al verlo, el script abre sus 2 consumidores (total 3) y la
conexión combinada.

### Paso 4 — Captura DOM #1 (en cuanto haya `LIVE`)

Consola del navegador (DevTools → Console), con el panel visible:

```js
(() => {
  const text = (id) => document.querySelector(`[data-testid="${id}"]`)?.textContent?.trim() ?? null;
  const count = text("explorer-stream-count") ?? "";
  const match = /(\d+)\s+cargadas\s+·\s+(\d+)\s+provisional/.exec(count);
  const nav = performance.getEntriesByType("navigation");
  const data = {
    captured_at_ms: Date.now(),
    url: location.href,
    identity: /Binance USD-M · [A-Z0-9]+ · \d+[mhd] · market-stream\/v1/
      .exec(text("explorer-stream") ?? "")?.[0] ?? null,
    state: text("explorer-stream-state"),
    live: text("explorer-stream-live"),
    updated: text("explorer-stream-updated"),
    candles: match ? Number(match[1]) : null,
    provisional: match ? Number(match[2]) : null,
    down: text("explorer-stream-down"),
    error: text("explorer-stream-error"),
    navigation_count: nav.length,
    reload_count: nav.filter((entry) => entry.type === "reload").length,
  };
  console.log(JSON.stringify(data, null, 2));
  return data;
})()
```

Copia el JSON a `docs/evidence/market-stream-window-2026-10-22-dom-1.json`.
Anota `candles` e `identity`: son la referencia de la paginación.

### Paso 5 — Captura DOM #2 (tras el cambio de minuto)

Cuando el gráfico muestre una vela nueva (el contador de velas sube y sigue
habiendo exactamente 1 provisional):

1. pulsa **“cargar anteriores”** una vez y confirma que el contador sube sin
   cambiar de contrato ni recargar;
2. ejecuta el mismo snippet con el bloque `pagination` añadido (sustituye
   `before` por lo anotado en el paso 4):

```js
// … mismo cuerpo que el snippet anterior, añadiendo antes de console.log:
data.pagination = {
  candles_before: 300,                                 // <- paso 4
  candles_after: data.candles,
  same_identity: data.identity === "Binance USD-M · BTCUSDT · 1m · market-stream/v1",
  exhausted: false,                                    // true solo si el gráfico avisa de que no hay más historia
  error: data.error,
};
```

Guarda el resultado como `…-dom-2.json`. Si el cierre llega antes de que puedas
capturar #1, la comprobación `dom_candles_grew` quedará como evidencia
insuficiente (`UNKNOWN`), nunca como `PASS`.

### Paso 6 — Parada y captura DOM #3

El script cierra sus consumidores, comprueba `/health` con `consumers=1` (queda
solo el navegador; en una ejecución sin navegador el esperado es `0`), para el
servicio y verifica: proceso terminado, puerto 8791 cerrado, PID file eliminado y
`/health` rechazado. Espera hasta **40 s** (el hook reintenta cada 5 s hasta 6
veces) y captura de nuevo con el mismo snippet como `…-dom-stop.json`: debe decir
`DESCONECTADO · servicio detenido`, sin `LIVE`, con las mismas velas o más y el
aviso honesto de que el histórico sigue disponible.

### Paso 7 — Veredicto (offline, sin red)

```powershell
$env:PYTHONPATH="src"
python -X utf8 scripts/market_stream_window.py --finalize `
    docs/evidence/market-stream-window-2026-10-22.json `
    --dom-first docs/evidence/market-stream-window-2026-10-22-dom-1.json `
    --dom-last  docs/evidence/market-stream-window-2026-10-22-dom-2.json `
    --dom-after-stop docs/evidence/market-stream-window-2026-10-22-dom-stop.json
```

Exit codes: `0` PASS, `1` FAIL, `2` UNKNOWN. La revisión visual, si existe, se
añade con `--visual-review pass|fail --screenshot <ruta>` y se registra **aparte**:
nunca sustituye a la evidencia DOM ni a la de Binance.

### Paso 8 — Limpieza y registro

```powershell
Get-Process python -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 8791 -ErrorAction SilentlyContinue
Get-ChildItem data\microprobe.db,data\historical\historical.db | Select-Object Name,Length,LastWriteTime
python -X utf8 scripts/market_stream_service.py --port 8791 --stop   # idempotente
```

Registrar en `docs/CURRENT_STATE.md` el estado alcanzado, sin mezclar los cuatro
planos: implementado / probado con transporte controlado / servido / verificado
con Binance.

## 5. Aceptación: check del script ↔ criterio

| Check | Fuente | Criterio |
|---|---|---|
| `preflight` | script | puerto libre, dashboard 200 y build servido |
| `service_started` | script | `/health` responde con PID y puerto |
| `no_socket_without_consumer` | script | al arrancar, `socket.connected=false`, `attempts=0`, `consumers=0` |
| `socket_connected` | script | alguna muestra de `/health` con `connected=true` |
| `messages_primary` / `messages_secondary` | script | ≥1 evento de vela por símbolo |
| `identity_exact` | script | `venue=binance`, `market_type=usd_m_futures`, `symbol` e `interval` exactos en `hello` y en las velas |
| `no_protocol_errors` | script | `invalid=0`, `identity_mismatch=0` en `/health` |
| `provisional_updates` | script | ≥2 actualizaciones con la misma `open_time_ms` |
| `close_confirmed` | script | `close_time_ms == open_time_ms + intervalo - 1` |
| `next_candle` | script | vela con `open_time_ms == cerrada + intervalo` y `seq` posterior |
| `live_status_seen` | script | `live=true` con estado `RECEIVING` |
| `bff_delivered` | script | `hello` + `snapshot` + ≥1 vela por `/api/v1/market-stream` |
| `coverage_intact` | script | sin huecos `partial`/`failed` ni `BUFFER_OVERFLOW` |
| `consumers_released` | script | `/health` con `consumers=1` tras cerrar los del script (queda el navegador; sin navegador, `0`) |
| `consumer_budget` | script | pico observado ≤ 3 declarados y, con navegador, `consumers=3` justo antes de cerrar |
| `service_stopped` | script | proceso terminado, puerto cerrado, PID file eliminado |
| `canonical_dbs_unchanged` | script | tamaño y mtime de `microprobe.db` y `historical.db` idénticos |
| `dom_identity` | navegador | `Binance USD-M · SYMBOL · 1m · market-stream/v1` en el panel |
| `dom_state_live` | navegador | capturas #1 y #2 en `RECIBIENDO`/`LIVE` |
| `dom_update_fresh` | navegador | marca UTC del panel dentro de la ventana y edad ≤ 15 s |
| `dom_candles_grew` | navegador | captura #1 antes del cierre, #2 después, y el contador sube con 1 provisional |
| `dom_pagination_preserved` | navegador | el contador crece al paginar, misma identidad, sin error |
| `dom_no_reload` | navegador | `navigation_count=1`, `reload_count=0` en ambas capturas |
| `dom_after_stop` | navegador | tras parar: `DESCONECTADO`, sin `LIVE`, velas ≥ captura #2, aviso presente |
| `transport_origin` | script | informativo: `binance` o `loopback_test` (no afecta al veredicto) |

## 6. Adquisición y veredicto son cosas distintas

`acquisition_finished` responde solo a: hubo mensajes, se vio la vela provisional,
el cierre y la vela siguiente, y el servicio se detuvo. El **veredicto** añade la
cadena completa y la evidencia del navegador:

| Situación | Veredicto |
|---|---|
| Cero mensajes, identidad incorrecta, servicio/BFF caídos, DB canónica tocada, cierre limpio fallido | **FAIL** |
| Mensajes pero sin cierre/siguiente habiendo agotado duración o presupuesto | **FAIL** |
| Cadena backend completa pero sin evidencia DOM (o BFF omitido) | **UNKNOWN** |
| Adquisición interrumpida por reconexiones/límite antes de ver cierre | **UNKNOWN** |
| Hueco no reparado | **FAIL** (`coverage_intact`) |
| Cadena + DOM completos | **PASS** |

Regla dura: **cero mensajes o cadena incompleta nunca producen `PASS`**. La
revisión visual es un campo aparte (`visual_review`) y no altera el veredicto.

## 7. Evidencia que queda en disco

- `docs/evidence/market-stream-window-<fecha>.json`: objetivo, presupuesto,
  preflight, banner y PID, `/health` antes del consumidor, muestras (2 s), eventos
  compactos de vela, `hello`/`snapshot`, huecos, cadencia medida, `/health` antes
  y después de retirar consumidores, estado tras la parada, DBs antes/después,
  checks y veredicto.
- `…-dom-1.json`, `…-dom-2.json`, `…-dom-stop.json`: capturas del panel.
- Nada más: no se escriben velas, ni caché, ni sesiones Paper Lab.

## 8. Reglas de parada

1. aceptación alcanzada + espera de captura;
2. duración (180 s), mensajes (1200) o eventos (6000);
3. reconexiones > 3;
4. `identity_mismatch` o símbolo/intervalo distinto del solicitado;
5. servicio caído (`SERVICE_EXIT`), `/health` inalcanzable 5 sondeos o transporte
   terminado;
6. cualquier indicio de credenciales, orden, cuenta privada o escritura en DB
   canónica → se aborta y se registra.

No hay reintentos en bucle: el transporte aplica backoff 1 s → 30 s con jitter y
presupuesto de 20 fallos consecutivos.

## 9. Qué NO demuestra

- No generaliza al universo ni a otros intervalos: dos símbolos y `1m`.
- No valida rentabilidad, señal, indicadores ni ejecución.
- No valida rate limits del exchange más allá del presupuesto local.
- No sustituye la revisión visual: el DOM prueba estado y contadores, no píxeles.
- Un `PASS` con `transport.origin = loopback_test` es **transporte controlado**,
  no recepción de Binance.

## 10. Evidencia controlada ya obtenida (sin Binance)

- `tests/test_market_stream_window.py` (20 pruebas): evaluador puro, `--finalize`,
  cliente SSE contra el servicio real en puerto efímero y **cadena completa
  controlada** con un WS local que imita el mensaje combinado de Binance.
- `docs/evidence/market-stream-window-loopback-2026-10-22.json`: ejecución real
  del orquestador sobre ese WS local. `stop_reason=ACCEPTANCE_REACHED`,
  `acquisition_finished=true`, servicio parado y puerto cerrado, `verdict=UNKNOWN`
  por falta de BFF y de DOM. `transport.origin=loopback_test`.
- `frontend/src/app/api/v1/market-stream/route.test.ts` (5 pruebas): el BFF
  reenvía el SSE, devuelve `503 STREAM_SERVICE_DOWN` si el servicio no responde y
  rechaza identidad/ventana/origen inválidos antes de llamar al servicio.

Nada de esto acredita recepción real de Binance ni el gráfico del navegador: eso
es exactamente lo que autoriza y mide la ventana.

## 11. Resultado de la ejecución real (2026-10-24, una sola ventana)

Ejecutada **una vez** con autorización explícita; sin repetición automática ni
ampliación de límites. Base `4956dee`, BUILD_ID `eiXlHvN4lJBLWcuOopsh_` (PID
33960), `BTCUSDT` + `MINAUSDT` 1m.

| Concepto | Medido |
|---|---|
| Ventana | `2026-10-24T00:47:04Z` → `00:48:27Z` (83,46 s de 180 s) |
| Conexión WS | 1 combinada, **1 intento, 0 reconexiones** |
| Consumidores SSE | navegador `BTCUSDT`, BFF `BTCUSDT`, servicio `MINAUSDT`; pico **3**, residual **1** |
| Eventos | 96 `BTCUSDT` + 14 `MINAUSDT` (servicio y BFF alineados) |
| Provisional | 50 actualizaciones sobre la misma apertura |
| Cierre / siguiente | `1792802820000` / `1792802880000` |
| Huecos | 0 (sin reparaciones) |
| Cadencia medida | mediana 418 ms · mínimo 250 ms · máximo 12041 ms |
| Parada | exit 0, puerto 8791 cerrado, PID file eliminado, `/health` rechazado |
| DBs | `microprobe.db` y `historical.db` intactas (mtime 2026-10-15 11:46:27); `market_cache.db` actualizada por la paginación REST |

**Evidencia DOM.** #1 `00:47:46Z`: `Binance USD-M · BTCUSDT · 1m ·
market-stream/v1`, `RECIBIENDO`, `LIVE`, 299 velas, `nav=1`/`reload=0`. #2
`00:48:29Z`: misma identidad, 303 velas, paginación `300→303` con identidad
preservada y sin error, **pero ya con el servicio parado**. #3 `00:50:06Z`:
`DESCONECTADO`, `no LIVE`, 303 velas conservadas, sin aviso
`explorer-stream-down`.

**Veredicto: `FAIL` (exit 1).** `acquired=true`; pasan los 19 checks de cadena,
servicio, presupuesto y DBs (incluidos `dom_identity`, `dom_update_fresh`,
`dom_candles_grew` 299→303, `dom_pagination_preserved` y `dom_no_reload`).
Fallan solo `dom_state_live` (captura #2 posterior a la parada: la espera de 20 s
expiró durante la paginación) y `dom_after_stop` (el aviso de servicio detenido
no apareció porque el SSE del BFF siguió abierto y no se agotaron los reintentos).
No es un fallo de datos: la cadena real llegó al gráfico.

**Correcciones propuestas (no ejecutadas, requieren nueva autorización de
ventana):** paginar antes del cierre o ampliar `--hold-seconds`; hacer que el BFF
cierre el SSE al caer el upstream o que el hook reconsulte `/status`; investigar
por qué la paginación subió el contador `300→303` con ~45 KB nuevos en caché.

## 12. Remediación posterior a la ventana (2026-10-24, sin nueva ventana)

Autorizada como corrección acotada, **sin repetir la ventana** y sin abrir
conexión Binance nueva. El veredicto `FAIL` de §11 se mantiene y su evidencia no
se reescribe. Base `965ab87`.

### 12.1 Causa demostrada

1. **BFF** (`frontend/src/app/api/v1/market-stream/route.ts`): devolvía
   `upstream.body` en crudo. No declaraba el fin ni el error del upstream, no
   emitía causa y no abortaba el upstream al cancelar el cliente. Con el SSE
   abierto, el navegador no tenía señal de que el feed había muerto.
2. **Hook** (`frontend/src/lib/use-market-stream.ts`): `onerror` solo
   incrementaba `attempts` (sin cambio visible) y `LIVE` se derivaba de un
   `status` congelado. Sin mensajes nuevos el panel podía seguir pareciendo vivo
   o quedarse mudo sin causa hasta agotar 6 reintentos (≈30 s) o indefinidamente
   si el SSE del BFF seguía abierto.

### 12.2 Corrección

- BFF: `AbortController` + escucha de `req.signal`, bombeo de frames del
  upstream, frames `event: error` con `STREAM_UPSTREAM_CLOSED` /
  `STREAM_UPSTREAM_ERROR`, `cancel()` aborta el upstream y libera el lector.
- Hook: frescura local con ticker de 1 s (STALE > `fresh_ms`, DISCONNECTED >
  `stale_ms`, `LIVE` = `live && age <= fresh`), causa inmediata en `onerror` y en
  `event: error` con código; el heartbeat limpia el error.
- Servicio: al cerrar el cliente se despierta el bucle del consumidor (sin
  esperar al heartbeat de 5 s); la liberación es inmediata.
- Paginación: se pide el bloque estrictamente anterior al borde cargado
  (`to = anchor - step`, `from = to - 299·step`) y se antepone con
  `mergeEarlierSeries` (dedupe por `open_time`, gana la fila ya cargada,
  cobertura/huecos recalculados, `added` = velas únicas). `added === 0` o bloque
  agotado marca `earlierExhausted`; no se exige `+300`.

### 12.3 Medido con transporte controlado (sin Binance)

| Medición | Resultado | Evidencia |
|---|---|---|
| Cliente cierra, servicio vivo | consumidores 1 → **0 en 14 ms** | `market-stream-controlled-disconnect-2026-10-24.json` |
| Servicio se detiene | EOF + `event: error` `STREAM_UPSTREAM_ERROR` en **6025 ms** | ídem |
| DOM real tras parada | `DESCONECTADO` + causa en **12 ms** | `market-lab-controlled-disconnect-2026-10-24.json` |
| Paginación (bloque almacenado) | 300 devueltas, 0 solapan, merge conserva el extremo reciente | `pagination-300-303-2026-10-24.json` |
| Pruebas | backend 29/29 + 25/25; frontend focalizado 28/28; contrato 13/13; `tsc`/`eslint` 0 | — |

La captura `LIVE` del transporte controlado **no** acredita recepción real; eso
sigue acreditado solo por la captura #1 de §11.

### 12.4 Pendiente (requiere nueva autorización de ventana)

Repetir la ventana real con el procedimiento corregido: capturar #2 con `LIVE`
(paginar antes del cierre o ampliar el `hold`) y #3 con el aviso de desconexión
ya visible. Sin esa repetición, `F-CHART-BINANCE-04` sigue `FAIL` en su veredicto
medido, con la causa y la corrección demostradas por separado.

### 12.5 Desviaciones del diagnóstico (declaradas)

- Dos arranques del servicio sin `--base-url` abrieron el WS público de Binance
  ~9 s y ~30 s (sin claves, sin API privada, sin órdenes); no son ventana de
  aceptación ni evidencia.
- Una página `/market-lab` con `0GUSDT` 1h seleccionado encadenó 12 peticiones
  REST públicas (`01:43:47Z`–`01:44:18Z`) que añadieron 3.552 velas a la caché
  derivada (47 → 3.599 filas), sin perder filas previas; DBs canónicas intactas.
  Se ejecutó `wal_checkpoint(TRUNCATE)`. El cliente exacto queda `UNKNOWN`.
- Segunda observación del mismo defecto antes de la corrección: `ACTUSDT` 1h
  encadenó 6 peticiones REST públicas (`12:07:10.299Z`–`12:07:27.733Z`, 17,4 s,
  ids 54–59 del `market_fetch_ledger`) y añadió 1.799 velas (la caché no tenía
  filas de ese símbolo). Cliente `UNKNOWN`; no consta ninguna ejecución de
  navegador en el bloque de corrección. DBs canónicas intactas. Evidencia:
  `docs/evidence/market-lab-pagination-cascade-2026-10-24.json`.
- Riesgo residual corregido el 2026-10-24 (§12.6): el transporte ya no puede
  caer al endpoint público y la paginación está acotada a una página por gesto.
  La evidencia histórica de esta sección **no** se borra ni se reinterpreta.

### 12.6 Corrección de los dos defectos (2026-10-24, sin ventana real)

1. **Transporte aislado y falla cerrado.** `market_stream_service.py` exige
   `--transport local|public`. `local` valida `ws://` loopback, desactiva la
   reparación REST y no tiene fallback; `public` es la activación explícita del
   WS de Binance. Sin transporte válido: exit 2 (`TRANSPORT_CONFIG`) y cero
   sockets. El orquestador de ventana pasa `--transport local` con `--base-url`
   y `--transport public` sin él. Evidencia:
   `docs/evidence/market-stream-transport-failclosed-2026-10-24.json` y
   `tests/test_market_stream_transport.py` (incluye un servicio real con WS
   falso local: cero resoluciones de `fstream.binance.com`).
2. **Paginación acotada a una página por interacción.** La descarga ya no se
   decide en el evento de rango (anteponer velas también lo emite): se evalúa al
   **terminar un gesto** (rueda con debounce, `pointerup`, `keyup`) con la puerta
   `frontend/src/lib/earlier-gate.ts` (gesto nuevo + cooldown + borde + ancla).
   Además, anteponer conserva el encuadre por índice exacto aunque el feed haya
   actualizado la última vela (antes `isSuffix` fallaba y la vista caía sobre el
   bloque nuevo). En el explorador: guard síncrono de petición en vuelo, mismo
   rango no repetido, y distinción cancelación / agotamiento / fallo con
   reintento manual habilitado. Evidencia: pruebas de `earlier-gate`,
   `price-chart-market` (incluye la reproducción del disparador) y
   `contract-explorer` (dos clics → una petición; fallo → gráfico conservado).

El veredicto medido de la ventana sigue `FAIL`; esta corrección no lo cambia.

## 13. Segunda ventana real (2026-10-24 14:04Z, base `2f2f9ea`): FAIL de aceptación

**Autorización.** Una sola ventana desde `2f2f9ea` con el procedimiento existente
actualizado y el parche de medición autorizado antes de conectar
(`--release-browser`, `--release-timeout`, `--reconnect-timeout`; sin cambios de
producto). Sin relanzamiento y sin segunda ventana.

**Identidad de la ejecución.** HEAD `2f2f9ea` en
`review/o1-funcional-v2-observacion`; dashboard PID 32712 en `127.0.0.1:3020`
con `BUILD_ID=y_fx2dQ35CUiQeOHtUhfl`; servicio PID 3020 en `127.0.0.1:8791`
con `--transport public`; `started=2026-10-24T14:04:37.065Z`,
`finished=2026-10-24T14:05:43.957Z`, `duration_s=66.89` (de 180 s
autorizados); `stop_reason=ACCEPTANCE_REACHED`; `transport.origin=binance`.

**Presupuesto consumido.** 1 conexión WS combinada (1 intento, 0 reconexiones);
2 streams `BTCUSDT` + `MINAUSDT` 1m; 3 consumidores SSE (navegador 1, BFF 1,
servicio 1; por stream `BTCUSDT` 2 y `MINAUSDT` 1); 58 mensajes, 58 aplicados y
2 cierres; 46 eventos de vela `BTCUSDT` y 12 `MINAUSDT`; 38 actualizaciones
provisionales de la misma apertura; 0 huecos; 2 peticiones REST públicas de
velas (1 carga inicial de 299 y 1 paginación de 300; catálogo desde caché con
`catalog_fetched_at_ms=1792850007876`, sin `exchangeInfo` en la ventana); sin
monitor, sin paper, sin órdenes, sin móvil.

**Cadena medida (real).** Pasan `socket_connected`, `messages_primary`,
`messages_secondary`, `identity_exact`, `no_protocol_errors`,
`provisional_updates`, `close_confirmed` (`close_time_ms=1792850640000`),
`next_candle` (`next_open_ms=1792850700000`), `live_status_seen=RECEIVING`,
`bff_delivered` (46 eventos, identidad `BTCUSDT/1m`), `coverage_intact` (0
huecos), `consumer_budget` (pico 3 = declarado 3), `service_stopped` (exit 0,
puerto cerrado, PID file eliminado, `/health` rechazado) y
`canonical_dbs_unchanged`. La cadena real Binance → hub → servicio → BFF →
navegador funciona en esta ventana.

**Criterios DOM medidos.** Captura #1 a las `14:05:02.749Z`: identidad exacta,
`RECIBIENDO`, `LIVE`, 300 velas, 1 provisional, `nav=1`, `reload=0`. Captura #2
a las `14:06:16.349Z`: misma identidad, 600 velas (paginación `300→600`), pero
`OBSOLETO`/`no LIVE` con `age_ms=35000` y error de frescura; se capturó
**después** de la parada del servicio (`14:05:43.957Z`) porque la paginación
terminó fuera del `hold` de 20 s. Captura #3 a las `14:07:08.459Z`:
`DESCONECTADO`, `no LIVE`, 600 velas conservadas, sin aviso
`explorer-stream-down`.

**Veredicto medido: `FAIL` (exit 1), `acquired=true`.** Fallan
`consumers_released` (1 ≠ 0: la desconexión del navegador no se ejecutó dentro
de los 20 s), `browser_reconnected` (sin liberación previa, el `consumers=1` no
acredita una reconexión), `dom_state_live`, `dom_update_fresh`,
`dom_pagination_preserved` (error de frescura) y `dom_after_stop` (sin aviso);
falta `dom_candles_grew` (las capturas no rodean el cierre: #1 llegó ~2 s
después del cierre de las 14:05:00). `visual_review=NOT_REVIEWED`.

**Causas y lección.** (1) La operadora quedó bloqueada en la captura de la
paginación; la ventana de liberación (20 s) expiró con `consumers=1`. (2) La
petición de paginación superó el `hold` de 20 s; la captura #2 cayó después de
la parada. (3) La página se adjuntó cerca del borde de minuto y `LIVE` apareció
con el cierre, así que #1 no precede al cierre. La desconexión/reconexión
funciona (probada antes de la ventana con el mismo mecanismo del navegador:
`consumers=0` con el servicio vivo y `consumers=1` con recepción), pero **no se
ejecutó dentro de la ventana**. Lección: las acciones del navegador deben estar
automatizadas y acotadas (desconectar al aviso y capturar dentro del `hold`) o
la ventana debe separar la paginación de la fase de liberación; el `hold` debe
cubrir la latencia de la paginación. No se repite la ventana; una nueva requiere
autorización explícita y procedimiento revisado.

**Desviaciones declaradas del ensayo local previo.** El ensayo con transporte
local (autorizado, sin Binance) hizo, por un defecto del arnés (doble
`addInitScript` del reloj desplazado), 1 petición pública `exchangeInfo` y 1
petición pública de 299 velas 1m a las `13:53Z`/`13:56Z`; el WS falso no
implementaba `SUBSCRIBE` (por eso `MINAUSDT` quedó `CONNECTING` en el ensayo).
La ventana real no usó reloj falso ni WS falso: Binance atendió `SUBSCRIBE`
(`MINAUSDT` 12 eventos). Sin cambios de producto.

**Evidencia.** `docs/evidence/market-stream-window-2026-10-24.json` +
`docs/evidence/market-stream-window-2026-10-24-dom-1.json`,
`docs/evidence/market-stream-window-2026-10-24-dom-2.json` y
`docs/evidence/market-stream-window-2026-10-24-dom-stop.json`.

## 14. Aceptación local automatizada: dos recorridos consecutivos PASS (2026-10-24, base `6be44b9`, sin ventana Binance)

**Objetivo.** Demostrar el procedimiento completo `WS público -> servicio SSE ->
BFF -> /market-lab` sin abrir una ventana real: transporte loopback, catálogo e
histórico preparados, aislamiento de red real y coordinación por condiciones
observadas (sin esperas manuales de 20 s). Este bloque NO solicita ni ejecuta
una ventana Binance.

**Arnés.** `scripts/market_stream_local_acceptance.py`:

- cache temporal vía `MICROPROBE_MARKET_CACHE_DB` (2 contratos, 1m 7 días y 1h
  30 días; catálogo de 2 entradas), sin tocar las DBs canónicas;
- raíz sombra `MARKET_EXPLORER_ROOT` con `sitecustomize.py` que bloquea y
  registra cualquier conexión no loopback, y un wrapper del explorador que
  añade `--no-fetch` (respuestas con `fetch.allowed=false` y
  `catalog.refresh.reason=DISABLED`);
- proxy local 8793 que registra y rechaza intentos públicos; allowlist del
  navegador solo `127.0.0.1:3020` (cualquier otro origen se aborta y registra);
- WS falso 8794 en reloj real (`SUBSCRIBE`/`UNSUBSCRIBE`, provisional, cierre y
  siguiente vela), servicio real 8792 con `--transport local`, dashboard en
  3020 con el build nuevo;
- fases con máximo propio y límite global 180 s: `minute_phase`, `page_ready`,
  `acceptance`, `pagination`, `release`, `reconnect`, `down_notice`.

**Procedimiento ejecutado (por recorrido).** Espera a la fase de minuto; abre
`/market-lab`; selecciona BTCUSDT/1m; espera identidad exacta + `LIVE`; captura
#1; pagina una vez y verifica una sola petición, velas nuevas únicas, amplitud
de ventana preservada y actualizaciones recientes; captura #2 con el servicio
vivo; al aviso del orquestador desconecta la suscripción y comprueba
`consumers=0` con el servicio vivo; al aviso de reconexión reabre el
`EventSource`, comprueba `consumers=1` y una actualización posterior a la
reconexión; captura de reconexión; escribe la señal `--post-reconnect-signal`
para que el orquestador no pare el servicio durante la captura; tras la parada
verifica puerto cerrado, PID eliminado, `/health` rechazado, aviso
`explorer-stream-down` con causa real, histórico conservado y sin recarga.

**Cambios de soporte (no económicos).**

1. Orquestador `--post-reconnect-signal`: tras observar `consumers=1` mantiene
   el servicio vivo hasta la señal del arnés (máximo `--reconnect-timeout`),
   eliminando la carrera entre la captura DOM de reconexión y la parada limpia.
2. `--dashboard-url` usa host/puerto reales para el consumidor BFF;
   `_service_env` conserva el `PYTHONPATH` del arnés en el hijo.
3. Hook `useMarketStream`: al error del `EventSource` con el stream ya abierto
   consulta `/api/v1/market-stream/status`; si `available=false`, cierra y
   declara el aviso con la causa real. El BFF responde 503 JSON cuando el
   servicio está caído; para `EventSource` eso es fatal (no reintenta), por lo
   que sin esta consulta `attempts` se quedaba en 1 y el aviso no aparecía.
   La causa de frescura ya no sobrescribe el aviso terminal.
4. `ContractExplorer` muestra el detalle real en el aviso (`TypeError:
   ECONNREFUSED` en este recorrido).

**Resultado medido (dos recorridos consecutivos, mismo build).**

- `summary.json.git_sha = 6be44b96b11a9362f2ec128947034f782726e971`,
  `build_id = FE1Eg1exjGrbZJpHz5vRO`, `transport = loopback_test`,
  `binance_accredited = false`.
- Recorrido 1: `PASS` procedural, 83.0 s; recorrido 2: `PASS` procedural,
  115.5 s (ambos por debajo del límite global de 180 s).
- Cero intentos públicos en los dos recorridos (`proxy=0`, `guard=0`,
  `browser=0`); cero consumidores residuales; parada limpia; finalizer `PASS`
  con `failed=[]` y `missing=[]`.
- Paginación: `298 -> 599` velas, 1 petición, 300 aperturas nuevas únicas,
  amplitud de ventana preservada, identidad intacta; actualizaciones recientes
  (≤10 s) con el servicio vivo.
- Reconexión: `consumers=0` con el servicio vivo y `consumers=1` tras reabrir;
  la primera reapertura puede coincidir con el cierre del SSE anterior en el
  BFF, por lo que el arnés reabre dentro de la misma fase (2 intentos, ~3.8 s
  observados); la captura de reconexión muestra `LIVE` con `updated` posterior.
- Parada: `explorer-stream-down` con `Servicio de datos detenido (TypeError:
  ECONNREFUSED)`, estado `DESCONECTADO · servicio detenido`, 599 velas
  conservadas, `nav=1`, `reload=0`.
- El `orchestrator_exit=2` es esperado: el orquestador escribe `UNKNOWN` antes
  de que el arnés aporte la evidencia DOM; el `--finalize` posterior actualiza
  el veredicto a `PASS`. El código de salida del orquestador no es el veredicto
  de aceptación.

**Diagnóstico cerrado.** (1) El fallo de la segunda ventana real fue del
procedimiento de captura/liberación, no de los datos: la secuencia del navegador
no se ejecutó dentro del `hold` y la paginación lo superó. El arnés sustituye
las esperas manuales por condiciones observadas y señalización. (2) El aviso
`explorer-stream-down` era un hueco funcional: el 503 JSON del BFF es fatal para
`EventSource`; ahora se consulta el estado y se declara la causa real. (3) La
reconexión puede necesitar una reapertura adicional por la carrera con el cierre
del SSE anterior; se resuelve dentro de la fase, sin ampliar el presupuesto.

**Límites.** El WS es falso y loopback: este PASS **no acredita recepción de
Binance**. El check `transport_origin` es `required=false` y queda en `ok=false`
(`origen=loopback_test`), por eso el finalizer local puede dar `PASS`; la
acreditación real sigue exigiendo `--transport public` y autorización humana
explícita. No se tocaron economía, riesgo, paper, órdenes ni móvil. La
actualización de Next.js 16.4.1 sigue **no ejecutada** (ver el diagnóstico de
seguridad en `docs/CURRENT_STATE.md`); el build usado es
`FE1Eg1exjGrbZJpHz5vRO`.

**Evidencia.** `docs/evidence/local-acceptance-2026-10-24/summary.json`,
`run-1/` y `run-2/` (`run.json`, `local.json`, `dom-1.json`, `dom-2.json`,
`dom-reconnected.json`, `dom-stop.json`, `network.json`). Los `.log` del
orquestador y del finalize quedan solo en local porque `.gitignore` ignora
`*.log`; el veredicto y las fases están en `run.json`/`local.json`.
