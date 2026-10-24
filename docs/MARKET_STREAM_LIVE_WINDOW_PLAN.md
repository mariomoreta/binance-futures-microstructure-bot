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
