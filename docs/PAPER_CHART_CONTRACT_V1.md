# Contrato de datos del gráfico Paper Lab — `paper-chart/v1`

Fecha: 2026-10-21. Base: `ac716d35ac5844fa25bf79d6e8d7e1b497ab1858`.
Alcance de esta entrega: **Paper Lab sobre fixtures**, escritorio, sin Binance en
vivo, sin feed prospectivo y sin adquisición. Este documento describe lo que el
código implementa y lo que queda explícitamente fuera (UNKNOWN / futuro). No
declara validación económica ni edge.

ID de seguimiento: F-CHART-BINANCE-01 (ver `docs/FEATURE_BACKLOG.md`).
Acuerdo funcional de origen: `docs/ACUERDOS_GRAFICO_BINANCE_V1.md`.

## 1. Auditoría: productores y contratos existentes

Antes de añadir un contrato se inventariaron los productores reales:

| Productor | Archivo | Qué produce | Autoridad |
|---|---|---|---|
| Motor Paper Lab | `src/microstructure_probe/paper_lab_engine.py` | sesión, reloj de simulación, velas conocidas en T, posición, stop efectivo, eventos, resultado y costes | **Única** |
| Representación pública | `paper_lab_engine.session_to_public_dict` | JSON de sesión filtrado a T (velas solo-open con OHLC `null`, `can_step`, `position.stop_px`, `exit_executed`), `event_id` estable | única para el gráfico |
| BFF | `frontend/src/app/api/v1/paper-lab/**` | transporte HTTP local; no decide ni calcula economía | transporte |
| Cliente tipado | `frontend/src/lib/paper-lab-live.ts` | tipos y llamadas; ahora acepta `high/low/close/close_time_ms` nulos | presentación |
| Fixtures | `frontend/src/lib/paper-fixtures.ts` | velas sintéticas determinísticas y contexto | datos de ingeniería |
| Adaptador de gráfico | `frontend/src/lib/paper-chart-contract.ts` | `paper-chart/v1` (identidad, tiempos, velas, operación, marcas, cobertura) | **solo presentación** |
| Componente | `frontend/src/components/paper-lab-live/PaperChart.tsx` | monta Lightweight Charts y dibuja el modelo | solo presentación |

No existe en esta fase ningún productor de indicadores ni de volumen para Paper
Lab. El motor de backtest (`backtest_offline.py`) y el replay histórico tienen
sus propios contratos y **no** se reutilizan aquí ni se modifican.

## 2. Identidad

| Campo | Tipo | Implementado | Origen |
|---|---|---|---|
| `contract_version` | `"paper-chart/v1"` | sí | constante del adaptador |
| `identity.source` | `"fixture"` | sí | fuente real de esta pantalla |
| `identity.venue` | `null` | sí (UNKNOWN) | no hay venue Binance detrás de una fixture |
| `identity.venue_status` | `"UNKNOWN"` | sí | ausencia explícita, nunca string inventado |
| `identity.market_type` | `"simulated_futures"` | sí | simulación, no contrato vivo |
| `identity.symbol` | string | sí | `config.symbol` |
| `identity.interval` | string | sí | `config.interval` |
| `identity.session_id` | string | sí | sesión del backend |
| `identity.fixture_id` | string \| null | sí | selección del usuario |
| `event_id` | string | sí | `session_id:ev:<índice>:<kind>:<at_ms>` |

`event_id` es opaco y estable dentro de la sesión: los eventos son append-only y
el índice no cambia al refrescar. No se usa como hash económico.

## 3. Tiempos y unidades

- Backend y modelo: **milisegundos Unix UTC** (`times.unit = "ms"`,
  `times.epoch = "unix_utc"`).
- Lightweight Charts: **segundos Unix UTC**. La conversión es explícita
  (`msToChartSecond`, `floor(ms/1000)`), nunca implícita en la biblioteca.
- El milisegundo exacto se conserva en `open_time_ms`, `time_ms`, `at_ms` y en
  los IDs; el eje solo aproxima a segundos. Dos instantes del mismo segundo
  comparten coordenada visual, pero no se confunden en el modelo ni en el
  detalle.

| Concepto | Campo | Semántica |
|---|---|---|
| Reloj de simulación | `times.clock_ms` = `clock_ms` | T; único instante que decide qué es conocido |
| Apertura/revelación | `open_time_ms` | la vela se revela por su open en T |
| Disponibilidad | `available_at` | cuándo el backend considera legible el dato (puede ser `null` = UNKNOWN) |
| Recepción | `received_at` | cuándo el feed entregó la vela (`null` = UNKNOWN en fixtures) |
| Cierre de vela | `close_time_ms` | `open_time_ms + 899999` para 15m; `null` si no se conoce |
| Evento de operación | `PaperEvent.at_ms` | tiempo de **simulación** del evento (entrada, salida, marca, decisión) |
| Registro de evaluación | `decision_evidence.evaluated_at_ms` | hora de pared en que se ejecutó la evaluación; no se dibuja |
| Cursor | `cursor` | número de aperturas reveladas (no índice de la última vela) |

Decisión de contrato (2026-10-21): los eventos de decisión (`protection`) usan
`signal_at_ms` (reloj de simulación), igual que entrada/salida/marca. Antes
usaban hora de pared y rompían el orden causal del log. La hora de pared queda
en `evaluated_at_ms`/`updated_at_ms`.

## 4. Velas

El backend publica toda vela con `open_time_ms <= T`. Si su cierre aún no es
conocido en T, publica **solo** `open_time_ms` y `open`; `high`, `low`, `close` y
`close_time_ms` son `null`.

El adaptador produce:

```ts
type ChartCandle =
  | {kind:"closed"; open_time_ms; close_time_ms; open; high; low; close;
     available_at_ms; received_at_ms}
  | {kind:"open"; open_time_ms; close_time_ms:null; open;
     high:null; low:null; close:null; available_at_ms; received_at_ms};
```

Reglas:

1. **Nunca** se rellena un campo desconocido con `0`, con el open, con el cierre
   anterior ni con interpolación.
2. Se descartan velas sin `open`/`open_time_ms` finitos (no se inventa nada).
3. Se ordena por `open_time_ms` y se deduplica por tiempo conservando la última
   observación recibida (el backend ya deduplica; esto es defensa).
4. El adaptador vuelve a filtrar por `clock_ms`: aunque el llamador entregue la
   lista completa, nada posterior a T se presenta como conocido. Sin reloj
   (`clock_ms = null`) no se asume conocimiento.
5. `context` solo contiene velas cerradas anteriores a la ventana de operación.
6. La vela solo-open se dibuja como **punto ámbar** en el open conocido
   (`LineSeries` sin línea y con point markers) más un marcador `open`. No se
   dibuja cuerpo, mecha ni cierre; no se interpola.
7. **Volumen**: `null` / `UNKNOWN`. La fixture no lo trae y no se sintetiza; no
   hay serie de histograma.

## 5. Indicadores

`indicators: []`. El backend de Paper Lab no produce indicadores en esta fase.
La UI declara “Indicadores: ninguno” y no dibuja EMA/RSI/ATR ni niveles que no
existan. Cualquier indicador futuro deberá declarar nombre, versión, unidades,
warm-up y validez antes de aparecer.

## 6. Operación

| Concepto | Campo del modelo | Regla |
|---|---|---|
| Decisión | `operation.decision` | `config.decision`; puede ser `null` |
| Señal | `operation.signal` | solo si `decision == "ENTRADA_SIMULADA"`; tiempo `decision_evidence.decision_at_ms`, precio `trigger_px` (puede ser `null`) |
| Entrada pendiente | `operation.pending_entry` | solo `status == "en_espera"`, decisión de entrada y sin posición; precio de **referencia**, no fill |
| Fill ejecutado | `operation.entry` | solo si existen `position.entry_px` y `position.entry_ms` (o el resultado equivalente) |
| Stop efectivo | `operation.stop_effective_px` | `position.stop_px` cuando hay fill; es el stop que gobierna la operación |
| Objetivo | `operation.target_px` | `null` / `UNKNOWN`; no existe en el backend |
| Salida | `operation.exit` | **solo** `result.exit_executed == true`; usa `exit_px`, `exit_ms`, `exit_reason` |
| Realizado | `operation.realized_net` | solo con salida ejecutada; `realized_net` del backend. Si falta → `UNKNOWN`, no se sustituye por `net_pnl` |
| No realizado | `operation.unrealized_net` | posición abierta; en `open_at_end` puede venir de `result.net_pnl` marcado como no realizado |
| Fin de datos abierto | `operation.open_at_end` | `result.open_at_end`; **no** genera marca de salida |
| Última marca | `operation.mark_px/mark_ms` | informativa; no es un cierre |

`open_at_end` conserva `status = "cerrada"`, `position.open = true`, `exit_executed
= false`, `realized_net = null` y una marca no realizada. El gráfico no dibuja
“Salida” en ese estado.

## 7. Marcadores

`markers` contiene como máximo señal, entrada y salida, ordenados por
`time_ms` y luego por tipo:

| kind | Cuándo | Posición | ID |
|---|---|---|---|
| `signal` | decisión de entrada confirmada | `belowBar` en el tiempo de decisión (se adjunta al punto open si esa vela sigue solo-open) | `signal:<session>:<ms>` + `event_id` si existe |
| `entry` | fill ejecutado | `atPriceMiddle` en `entry_px` | `entry:<session>:<ms>` + `event_id` |
| `exit` | solo `exit_executed` | `atPriceMiddle` en `exit_px` | `exit:<session>:<ms>` + `event_id` |

Los eventos `mark` no se dibujan como operación. No se dibujan objetivos,
indicadores ni niveles ausentes. Los IDs y `time_ms` exactos se conservan aunque
el eje use segundos.

## 8. Cobertura y capacidad de avance

`capabilities` publica `status`, `can_step`, `cursor`, conteos de contexto /
cerradas / solo-open y un texto de límites. El backend es quien decide
`can_step`; el gráfico no infiere el final de la fixture por el número de velas
recibidas. Abrir o refrescar la pantalla no inicia el monitor ni una
adquisición.

## 9. Biblioteca e integración

- Paquete oficial `lightweight-charts` **5.2.1**, fijado sin rango en
  `frontend/package.json`; lockfile con `integrity`.
- Licencia Apache-2.0 (TradingView, Inc.); aviso y texto en
  `frontend/THIRD_PARTY_NOTICES.md` y `frontend/THIRD_PARTY_LICENSES/`.
  Dependencia transitiva `fancy-canvas@2.1.0` (MIT).
- Montaje **solo cliente** mediante `import()` dinámico dentro de `useEffect`;
  sin SSR.
- `autoSize` para el tamaño; un único `createChart` por montaje.
- Limpieza: `unsubscribeCrosshairMove`, `unsubscribeVisibleTimeRangeChange`,
  `detach()` de los plugins de marcadores y `chart.remove()`.
- Actualización incremental: contexto/velas se añaden con `update()` si la
  serie previa es prefijo exacto; si no, `setData()`. Cambiar de sesión
  descarta datos, marcadores, líneas y respuestas tardías, y reajusta la vista.
- Líneas de precio informativas (entrada, stop, salida, pendiente). Arrastrar
  stop/objetivo queda **diferido**.
- Zoom/desplazamiento nativos de la biblioteca; botón “Ajustar”; lectura de
  ventana visible y cursor (fecha/precio) en texto DOM.

## 10. Implementado vs. futuro

| Capacidad | Estado |
|---|---|
| Gráfico de velas de contexto + velas reveladas | implementado |
| Vela solo-open como punto, sin OHLC inventado | implementado |
| Señal / pendiente / fill / stop efectivo / salida ejecutada | implementado |
| `open_at_end` sin salida inventada | implementado |
| Zoom, pan, ajuste, cursor con fecha/precio | implementado |
| Estado FIXTURE/SIMULACIÓN, reloj y cobertura | implementado |
| Volumen | **UNKNOWN** (no hay fuente) |
| Indicadores | **no implementados** |
| Objetivo | **UNKNOWN** (no existe en el backend) |
| Venue Binance real | **no implementado** (fixtures) |
| Búsqueda de contratos, histórico paginado, feed vivo | **fuera de este bloque** |
| Stops/objetivos arrastrables | **diferido** |

## 11. Aceptación con fixtures (A–H)

| Caso | Verificación |
|---|---|
| A. Inicio sin futuros | contexto visible, ninguna vela con `open_time_ms > clock_ms` |
| B. Señal pendiente | marcador de señal y línea punteada de referencia; sin marcador/línea de fill |
| C. Fill | entrada y stop iguales a `position.entry_px`/`position.stop_px` del backend |
| D. Cierre automático | marcador de salida solo con `exit_executed`; tiempo/precio/resultado reconciliados |
| E. Fin de datos abierto | sin marcador de salida; “no realizado”; `realized_net = null` |
| F. Refresco/recuperación | misma sesión, misma operación y niveles |
| G. Cambio de sesión | sin velas, líneas ni marcas de la sesión anterior |
| H. Zoom/pan/legibilidad | ventana visible cambia; etiquetas de escritorio legibles |

La regresión económica aceptada se conserva: LONG 101 → stop/salida 95.95 →
neto -51.56, sin salida posterior a 80.

## 12. Evidencia de esta entrega (2026-10-21)

- **Base:** `ac716d35ac5844fa25bf79d6e8d7e1b497ab1858`.
- **Biblioteca:** `lightweight-charts@5.2.1` (Apache-2.0, TradingView) fijada sin
  rango; `fancy-canvas@2.1.0` (MIT) transitiva. Avisos en
  `frontend/THIRD_PARTY_NOTICES.md` y `frontend/THIRD_PARTY_LICENSES/`.
- **Pruebas:** backend focalizado 38/38; suite completa `python run_tests.py -q`
  1290 OK (2 skipped); frontend `npm test` 484 passed + 1 skipped;
  `tsc --noEmit` 0; `eslint src` 0 errores (5 warnings preexistentes). Pruebas
  nuevas: `frontend/src/test/paper-chart-contract.test.ts`,
  `frontend/src/test/paper-chart.test.tsx` y casos de `event_id`/solo-open/
  tiempo de simulación en `tests/test_paper_lab_engine.py`.
- **Servido:** build `PPE-Io-M4ivYg3dvJRqwh`, PID 27612,
  `http://127.0.0.1:3020/paper-lab-live`, HTTP 200; reemplazo del listener
  anterior solo tras comprobar `runtime running=false/COMPLETED`, job
  `completado` y ausencia de trabajos activos.
- **Navegador (1440×900, controles reales):** A sesión
  `PL-BTCUSDT-LONG-1792631052590-413d566e` (48 contexto, 0 operación, ventana
  10:00→21:45, reloj 21:59:59.999); B 2 pasos → EN ESPERA sin fill; C `Entrar` →
  ABIERTA 78,537.18/78,144.49; D fixture stop
  `PL-BTCUSDT-LONG-1792631699330-f0747528` → CERRADA, salida 95.95, neto
  -51.560000000000116, sin salida 80; E sesión A sin cierre inventado y “No
  realizado”; F recarga y carga desde persistencia con los mismos niveles; G
  carga de `PL-BTCUSDT-LONG-1792627398136-5241b33a` sin residuos de la sesión
  anterior; H rueda 17:00→17:30, arrastre 16:45→04:00, `Ajustar` 16:00→04:45 y
  cursor `2026-09-08T23:15:00Z · 100.00`. Capturas
  `.playwright-mcp/paper-chart-{A..H}*.png`.
- **Inspección visual:** no hubo proveedor de visión disponible; se acredita
  DOM/geometría/HTTP y capturas, **no** un PASS visual.
- **Residuales conocidos:** solo fixtures (sin venue Binance real); sin
  volumen/indicadores/objetivo; el selector de persistencia solo se renderiza
  cuando ya existe una sesión, así que recuperar tras un refresco exige
  seleccionar una fixture primero; tras pasos incrementales el ajuste inicial
  puede omitir la primera vela de contexto hasta pulsar `Ajustar`; 5 avisos de
  `npm audit` no abordados; sin móvil/Flutter. `open_at_end` mantiene
  `realized_net=null` y no genera marcador de salida.

## Actualización 2026-10-21 — componente compartido y correcciones de encuadre/persistencia

Contrato `paper-chart/v1`: **sin cambios**. Lo que cambia es el componente que lo
dibuja y dos defectos detectados en la verificación real.

- **Componente único.** `frontend/src/components/chart/PriceChart.tsx` acepta la
  unión `PaperChartModel | MarketChartModel` discriminada por
  `contract_version`, y `frontend/src/components/paper-lab-live/PaperChart.tsx`
  queda como reexportación. Los `data-testid` `paper-chart*`, las líneas de
  entrada/stop/salida, las marcas de contexto y la regla de vela solo-open se
  conservan; las pruebas de Paper Lab siguen pasando sin cambios de aserción.
- **Corregido: recuperar sesión desde la pantalla inicial.** El selector de
  persistencia se renderiza también cuando no hay sesión cargada, así que una
  sesión guardada se puede listar y cargar sin crear una fixture previa. La carga
  hace `GET` del estado autoritativo y no re-evalúa la decisión. Verificado con
  clic real: 0 `POST` durante la recuperación.
- **Corregido: encuadre inicial.** `fitContent` se aplica una sola vez, con ancho
  real del contenedor; si el ancho es 0 se difiere y se reintenta al recibir
  `ResizeObserver`. Las actualizaciones de estado y los bloques antepuestos ya no
  reencuadran, y `Ajustar` sigue reencuadrando de forma explícita.
- **Sigue fuera de contrato para Paper Lab:** `volume`/`indicators`/`target` son
  `UNKNOWN`/`[]`/`UNKNOWN` porque el backend de este flujo no los produce. El
  volumen y los indicadores del modo mercado (`market-chart/v1`) son otra rama
  del componente y otra fuente; se documentan en
  `docs/MARKET_EXPLORER_CONTRACT_V1.md`, no aquí.
- **Inspección visual:** sigue sin proveedor de visión; DOM/geometría/HTTP y
  capturas, **no** PASS visual.
