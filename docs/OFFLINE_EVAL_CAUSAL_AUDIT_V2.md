# Auditoria de senal causal — OFFLINE-EVAL-V1 mappings H1/H2/H3

Version: `OFFLINE-EVAL-CAUSAL-V2` (2026-10-17, sobre `b748d22`,
sin corridas Binance, sin ventana forward, sin optimizacion de
umbrales). Motor/runner/contratos reutilizados sin cambios
(`backtest-offline/v4.2`). Mapping bajo auditoria:
`MAP-CANDIDATE-v1` (`PROPOSED-P1-11C-map-v1`, NO aprobado).
Kronos/IA diferidos.

## 1. Definiciones y condicion por mapping

Fuente: familias descriptivas P1-11C (`src/microstructure_probe/events.py`,
`default_definition` v1, `DESCRIPTIVE_RESEARCH_ONLY_HYPOTHESIS`) +
hipotesis H1/H2/H3 (`docs/RESEARCH_BACKTEST_CONTRACT_ETAPA3.md`).

| Mapping | Fuente P1-11C | Direccion motor | Condicion (solo barras `open_time <= T`) |
|---|---|---|---|
| H1 continuacion alcista (LONG) | `MOMENTUM_ACCELERATION_UP` (accel_proxy >= +0.001 y ret1h >= 0), `EXTENDED_GAINER` (ret24h >= 5%, ret1h >= 0.5%, range_pos >= 0.7) | `up` → LONG | Deriva pasada + aceleracion kline (proxy historico, no P1-05 live) |
| H3 continuacion bajista (SHORT) | `MOMENTUM_ACCELERATION_DOWN` (accel <= −0.001 y ret1h <= 0), `EXTENDED_LOSER` (ret24h <= −5%, ret1h <= −0.5%, range_pos <= 0.3) | `down` → SHORT | Espejo bajista. H3 es continuacion DOWN tras perdida de soporte; la recuperacion del perdedor (down + reversal UP) pertenece a H2, nunca a H3 |
| H2 agotamiento (`correction-exhaustion`, LONG mecanico) | `FAILED_HIGH_CANDIDATE` (ref en [high·(1−0.2%), high·(1−0.1%)]) | `up` → LONG (convencion mecanica, NO fade validado) | Fallo de maximo de 96 barras |
| H2 reversal (`correction-reversal`, SHORT mecanico) | `FAILED_LOW_CANDIDATE` (ref en [low·(1+0.1%), low·(1+0.2%)]) | `down` → SHORT (convencion mecanica) | Fallo de minimo de 96 barras |
| H2 variante rebote (`rebound-variant`) | SIN definicion fuente en P1-11C v1 | — | 0 eventos: excluida como no evaluable hasta definir bounce |

Datos necesarios: klines cerradas trio 15m con cadena de
`close_time` intacta (2879/simbolo, 0 violaciones) + fila
`event_instances` (features ya calculadas sobre prefijo).
Ventana: formacion usa trailing hasta 24h (retornos),
96 barras (trailing high/low), 100 barras (percentiles);
salida del motor a 1h (placeholder no validado).

## 2. Formacion / disponibilidad / decision / entrada

- FORMACION (`event_time`): open de la vela de formacion
  (ultima barra cerrada en el indice de scan). La condicion
  necesita su CLOSE → conocible solo a `close_time`.
- DISPONIBILIDAD (`available_at`): `close_time` de la vela de
  formacion (= siguiente open − 1ms en cadena intacta; gap
  uniforme 1ms). Derivada de la cadena venue, no del precio.
- DECISION: en V1 no existe detector vivo; la "decision" es
  la fila retrospectiva `event_instances` reutilizada
  verbatim por el runner (no inventa entradas; mismatches
  contados, 0 en V1).
- ENTRADA (`entry_time`): primer `open_time > event_time`
  (fill del motor). En cadena intacta coincide con el
  primer instante conocible. `reference_price` (close de
  formacion) es solo metadata: nunca fija un fill; en
  cadena con huecos el motor rellena en el siguiente open
  conocido (>= available_at por construccion) con salidas
  gap-first.

Prueba por operacion: `docs/evidence/OFFLINE_EVAL_AUDIT_V1.json`
— 1412/1412 `entry >= available`, 0 violaciones, 0 nulos.

## 3. Dependencia de informacion posterior

- `direction`: signo de la deriva YA realizada (retorno
  pasado / proxy de aceleracion sobre prefijo). Conocible
  en T con barras cerradas; no usa resultados futuros.
- `reference_price`: close de la vela de formacion.
  Conocido solo en `close_time` (disponibilidad, no
  posterior): el motor nunca lo usa como precio de fill.
- Seleccion de eventos: RETROSPECTIVA. Las 1558 filas son
  el subconjunto piloto P1-11C retenido sobre la ventana
  completa (38 runs piloto sobre barras 1h/15m; una
  re-deteccion exhaustiva actual sobre 15m daria ~1997 solo
  en BTC — ordenes de magnitud por encima — luego lo
  retenido es seleccion, no censo). La seleccion se hizo
  mirando la ventana completa; un entry posterior a
  `available_at` NO elimina ese sesgo: la muestra misma fue
  elegida con conocimiento del periodo.
- H3: direccion preservada verbatim (`down` → SHORT);
  ninguna direccion se eligio por rendimiento posterior
  (H3 nunca redefinido como recuperacion; H2/H3 jamas
  poolados; runner con contratos por grupo).

## 4. Reconstruccion offline sobre prefijos (sin futuro)

Experimento (solo lectura, `HistoryStore.load_bars` + `detect_events`,
mismo codigo P1-11C, sin `event_instances`):

- Prefijo 60% por simbolo: detecciones con `event_time <= T`
  identicas entre corrida completa y corrida truncada en T
  (BTC 6/6 familias: EXTENDED_GAINER 21/21,
  MOMENTUM_UP 528/528, MOMENTUM_DOWN 527/527,
  EXTENDED_LOSER 0/0, FAILED_HIGH 79/79, FAILED_LOW 43/43).
- Invariancia estricta: mutar TODAS las barras con
  `open_time > T` (closes x1.5) no altera ninguna decision
  con `event_time <= T` — 3 simbolos x 6 familias = 18/18
  identicas (BTC/ETH/SOL ALL=True).
- Matiz de borde: mutar la propia barra EN T si altera el
  evento que se forma en ella (dato de formacion, no
  "posterior"): la invariancia rige para posterior
  estricto (`> T`), como debe.
- Contraste con `event_instances`: la logica de formacion
  es reconstruible causalmente, pero el SET retenido (1558)
  es un subconjunto piloto retrospectivo, no la salida
  exhaustiva del detector (ver §3). Reproducir la
  deteccion != reproducir la seleccion.

## 5. Matriz causal por familia (vinculante)

| Familia | Formacion causal | Seleccion | Disponibilidad live | Clasificacion |
|---|---|---|---|---|
| H1 continuacion alcista (LONG) | Reconstruible causalmente (prefijo + invariancia 18/18) | Retrospectiva (subconjunto piloto) | UNKNOWN (sin prueba streaming) | RETROSPECTIVA, no utilizable como senal |
| H3 continuacion bajista (SHORT) | Reconstruible causalmente (idem, espejo) | Retrospectiva | UNKNOWN | RETROSPECTIVA, no utilizable como senal |
| H2 agotamiento (LONG mecanico) | Reconstruible causalmente | Retrospectiva + n=14 (INSUFFICIENT) + direccion = convencion no-fade | UNKNOWN | RETROSPECTIVA, no utilizable como senal |
| H2 reversal (SHORT mecanico) | Reconstruible causalmente | Idem | UNKNOWN | RETROSPECTIVA, no utilizable como senal |
| H2 variante rebote | Sin definicion (0 eventos) | No evaluable | UNKNOWN | UNKNOWN por datos insuficientes (excluida) |

Ninguna familia es "reconstruible causalmente" COMO SENAL:
la mecanica de formacion/entry lo es; la senal operable no
(falta mapping aprobado + prueba de disponibilidad en vivo +
ventana pristina + costes medidos — ver protocolo
`docs/PROSPECTIVE_PROTOCOL_V1.md`). La mecanica causal
probada (entry >= available) no demuestra tradability.
