# Matriz de evaluabilidad del objetivo "movers extremos" (§6)

Estado: **preparatoria**, no una evaluación. Conecta cada requisito del
objetivo de extremos con los datos que HOY existen, la limitación concreta
y la adquisición siguiente necesaria. No sustituye un requisito por cero,
ni por información conocida sólo después del instante de decisión, ni usa el
censo como sustituto del ranking/liquidez que el censo no contiene.

Fuentes de objetivo: `docs/EXTREME_MOVERS_OBJECTIVE.md`,
`docs/PRODUCT_GOAL.md`, `docs/MASTER_PLAN.md`.

Definición operativa de "elegible en T": un símbolo es elegible en el
instante T si, con información disponible **en o antes de T**, cumple los
criterios de universo y liquidez que autorizan estudiar su movimiento. El
censo actual NO conoce el universo elegible en T; por eso la estrategia
completa no es evaluable todavía (ver `docs/OFFLINE_EVAL_CENSUS_V2.md`,
`docs/CURRENT_STATE.md`).

## Matriz requisito → dato disponible → limitación → adquisición siguiente

| Requisito del objetivo | Dato disponible hoy | Limitación concreta | Adquisición necesaria |
|---|---|---|---|
| Universo elegible conocido **en T** (qué símbolos se podían vigilar en T) | Lista de símbolos hallados a posteriori en el censo; sin snapshot de universo por instante | Universo elegible en T **UNKNOWN**; el censo sólo ve lo que ya movió (selección retrospectiva) | Snapshots periódicos del universo de futuros (símbolos activos + filtros de listado) con marca temporal |
| Ranking rolling-24h (gainers/losers) y **aceleración temprana** | Cambios 24h puntuales en algunos payloads; sin serie rolling causal | No hay ranking causal reproducible por instante; la aceleración temprana no es medible con el dato actual | Serie rolling-24h por símbolo (precio/volumen), almacenada con `available_at` |
| Volumen relativo / agresión (compra vs venta) | Velas OHLCV derivadas; sin flujo de agresor por lado | Volumen relativo aproximado; agresión (taker buy/sell) **UNKNOWN** | Klines con `taker_buy_*` o aggTrade agregado por lado con marca temporal |
| Spread / profundidad y coste de ejecución | Comisiones por escenario oficiales; spread/slippage **UNKNOWN** | El coste de ejecución real no está modelado; sólo escenarios 1x/2x/3x como coste hipotético | Snapshots de order book (top of book / profundidad) o estimación de spread por instante |
| Contexto BTC (régimen de mercado) | Series BTCUSDT 15m/1h en el paquete | Contexto BTC usado como símbolo, no como régimen explícito por instante | Serie de régimen BTC (retorno/volatilidad rolling) alineada causalmente |
| Formación / disponibilidad de la señal | `formation_time_ms`, `available_at`, fronteras de entrada/salida (Paper Lab + censo) | **Verificado** para el censo mismo-grid; no generaliza a un universo mayor | Extender la reconstrucción causal al universo ampliado |
| Funding y costes recurrentes | Calendario `FUNDING-CAL-V1` (BTC/ETH/SOL) + fallback de intervalo | Fuera de BTC/ETH/SOL el calendario es **UNKNOWN** (residual MINA/NMR sin `build_report`) | Calendarios de funding por contrato para el universo ampliado |
| Resultado económico por operación | Motor `backtest-offline/v4.2` (realizado/abierto, costes ejecutados vs hipotéticos, funding asentado) | El motor no conoce universo/liquidez; sólo evalúa lo que el censo le entrega | Ingesta del universo/ranking/liquidez al pipeline de eventos |

## Qué NO hace esta matriz

- No declara evaluada la estrategia de extremos: sólo enumera qué falta.
- No rellena huecos con 0 ni con información posterior al instante T.
- No usa el censo EVAL-CENSUS-V2 como sustituto del ranking o liquidez
  que el censo no contiene (el censo es same-grid y conoce símbolos a
  posteriori).

## Próximo paso mínimo propuesto

Adquirir, con marca temporal de disponibilidad, (a) snapshots de universo y
(b) series rolling-24h por símbolo; sin ellos la evaluación de elegibilidad
en T permanece **UNKNOWN**. Detalle de secuencia en
`docs/EXTREME_MOVERS_OBJECTIVE.md`.
