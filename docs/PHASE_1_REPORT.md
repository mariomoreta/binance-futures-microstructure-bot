# Reporte de Fase 1 — conectividad y deteccion

Fecha de verificacion: 2026-09-01 (America/La_Paz).

## Alcance implementado

- Dos conexiones WebSocket separadas segun el ruteo actual de Binance USD-M.
- Streams market: liquidaciones globales, mark price/funding global y aggTrade por simbolo.
- Streams public: bookTicker y depth20@100ms por simbolo.
- Detectores configurables para liquidacion individual/ventana, funding por percentiles y volumen por z-score.
- Resumen periodico con actividad, staleness, latencia, spread, imbalance y reconexiones.
- Rechazo de eventos con desfase temporal superior al limite configurado.
- Modo observe forzado por codigo; no existen clientes autenticados ni funciones de orden.

## Gates

| Gate | Estado | Evidencia |
|---|---|---|
| Tests unitarios de formulas conocidas y detectores | YES | 14/14 tests pasaron, incluida la prohibicion de `BOT_MODE=live` |
| Configuracion valida y URLs ruteadas | YES | `--show-streams` genero `/public` y `/market` con los streams esperados |
| Recepcion real de public + market | YES | 11 streams activos, 0 stale, 0 reconexiones en la captura final de 12.103 s |
| Latencia real medida | YES | p50 1332 ms, p95 4020 ms; solo describe esta ejecucion corta y este entorno |
| Pipeline de deteccion | YES | Tests cubren liquidacion individual/ventana, funding con warm-up y spike de volumen |
| Cruce real de umbrales | NOT_OBSERVED | 0 eventos detectados en 12.103 s; no permite concluir que los umbrales sean adecuados |

## Evidencia de ejecucion real

- Runtime: 12.103 segundos.
- Streams activos: 11 de 11 observados; lista stale vacia.
- Mensajes: liquidaciones globales 3, mark price global 22, aggTrade BTC/ETH/SOL 66/43/37, bookTicker 1753/904/917, depth 62/60/58.
- Descartados por desfase temporal: 0.
- Reconexiones: 0.
- Eventos que cruzaron umbral: 0.

Esta ventana solo prueba conectividad y recorrido de datos. No es una muestra suficiente para calibrar umbrales, medir disponibilidad sostenida ni afirmar edge.

## Seguridad

```text
BOT_MODE: observe
apiKeysUsed: 0
realOrdersSent: 0
realCapitalAtRisk: 0
maxDrawdownKillSwitchActive: false
```

## Proximo bloqueador

Ejecutar una observacion prolongada, revisar la latencia elevada observada en este entorno y reunir suficientes cruces reales para calibrar los umbrales. No iniciar Fase 2 con la evidencia corta actual.

## Phase 1B — prolonged evidence validation

Estado: **PENDING_EVIDENCE**.

La corrida original de 12.103 segundos permanece como evidencia de conectividad inicial. No se reinterpreta como calibracion, disponibilidad sostenida ni edge.

### Baseline antes de modificar

- Inventario completo inspeccionado: README, este reporte, configuracion, paquete completo y todos los tests.
- El directorio no contenia `.git`; no habia diff o status Git disponible.
- Python 3.14.3, websockets 15.0.1.
- 14/14 tests pasaron antes de editar.

### Auditoria de la medicion historica

La implementacion 0.1.0 tomaba `time.time_ns()` como reloj local. Seleccionaba `E` cuando estaba disponible y, solo como fallback, `o.T`; para arrays de mark price elegia el mayor `E`. Calculaba una unica distribucion global `localReceiveMs - selectedTimestamp`, truncaba valores negativos a cero y descartaba el mensaje completo si el valor absoluto superaba 5000 ms.

Consecuencias:

- mezclaba streams, simbolos y dos semanticas de timestamp;
- no separaba event time de transaction/trade time;
- podia estar contaminada por desfase del reloj local;
- no permitia localizar el stream responsable del p95;
- la latencia global historica se conserva ahora identificada como `legacyGlobalClampedLagMs`, no como metrica adecuada para el gate de latencia.

Semantica oficial aplicada en 0.2.0:

- aggTrade: `E` event time; `T` trade time;
- bookTicker/depth: `E` event time; `T` transaction time;
- forceOrder: `E` event time; `o.T` order trade time;
- markPrice: `E` event time; `T` es next funding time y no mide latencia.

### Cambios Phase 1B

- Clock offset por midpoint con cinco muestras de `GET /fapi/v1/time`, mediana, RTT, timestamps y contadores. Una falla conserva la ultima estimacion valida y no detiene el probe.
- Latencia raw/corregida por tipo de stream y simbolo; tiempos `E` y `T` separados cuando la semantica oficial lo permite.
- Processing latency monotónica de alta resolucion para parseo, metricas, detector y total.
- Near-miss de liquidaciones individual/ventana, z-score de volumen, warm-up y observabilidad de funding repetido.
- Detecciones por detector, simbolo y categoria/direccion raw.
- Data quality: mensajes, streams, silencios, staleness con cadencia, secuencia depth, rechazos, errores, reconexiones y uptime observado.
- Memoria acotada: cuantiles sobre las ultimas 20.000 muestras por distribucion; acumulados exactos para count/min/max/mean.
- Sin base de datos, checkpoints, endpoints privados, autenticacion ni rutas de orden.

### Correccion documentada: falso stale en streams event-driven

La metrica anterior aplicaba `stale_after_seconds` a todos los streams. Esto era incorrecto para `forceOrder`: Binance documenta que no publica si no ocurre una liquidacion. Se agrego primero un test que reprodujo el falso stale y fallo; luego `staleStreams` se limito a `markPrice@1s` y `depth@100ms`, que tienen cadencia documentada. `silentStreams` y `maxObservedSilenceMsByStream` preservan la observacion sin inventar packet loss.

### Validacion local y smoke preliminar

- Suite ampliada: 28/28 tests pasan; no dependen de red.
- Smoke live de 20 s: 11/11 streams activos, 0 errores, 0 reconexiones, 0 rechazos.
- Clock smoke: offset mediano -558.828 ms; RTT mediano 350.171 ms; 5/5 muestras validas.
- El smoke es preliminar y no reemplaza la corrida de aproximadamente cinco minutos.

### Gates actuales

| Gate | Estado | Evidencia / bloqueador |
|---|---|---|
| A — Safety | PASS | observe forzado; 0 keys/ordenes/capital; test estatico sin rutas autenticadas ni de orden |
| B — Connectivity | PENDING_EVIDENCE | smoke sano, falta evidencia sostenida principal |
| C — Data quality | PENDING_EVIDENCE | instrumentado; falta corrida principal y soaks |
| D — Latency understood | PENDING_EVIDENCE | raw/corrected/processing instrumentados; falta caracterizacion prolongada |
| E — Detector observability | PENDING_EVIDENCE | near-miss/warm-up instrumentados; falta completar warm-up real |
| F — Calibration evidence | PENDING_EVIDENCE | requiere 6 h y especialmente 24 h; cinco minutos no pueden pasarlo |

### Fuentes oficiales verificadas

- Server time: https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data
- Market streams: https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market
- Public streams: https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/public

No se declara Fase 1 terminada y no se inicia Fase 2.
