# Reglas candidatas de hipotesis — MAP-CANDIDATE-v2 (versionado ANTES de evaluar)

Version: `MAP-CANDIDATE-v2` (2026-10-17, sin corridas, sin forward,
sin optimizar umbrales). Estado: CANDIDATO DE INVESTIGACION (NO aprobado,
NO senal, NO estrategia). Suple a MAP-CANDIDATE-v1 SOLO donde se indica;
v1 queda como historico. Nada aqui autoriza operaciones ni declara edge.

## 1. Separacion H1 / H3 / H2 / rebote (vinculante)

| Escenario | Fuentes P1-11C v1 (heredadas) | Direccion candidata | Novedad vs v1 |
|---|---|---|---|
| H1 continuacion alcista | MOMENTUM_ACCELERATION_UP, EXTENDED_GAINER | LONG | Ninguna (mecanica heredada; cambia el SET: censo same-grid exhaustivo, no subconjunto retrospectivo) |
| H3 continuacion bajista | MOMENTUM_ACCELERATION_DOWN, EXTENDED_LOSER | SHORT | Idem; H3 jamas es recuperacion del perdedor |
| H2 agotamiento (fade) | FAILED_HIGH_CANDIDATE | SHORT (fade contra la deriva) | NUEVA-HIPOTESIS: v1 usaba LONG mecanico por convencion (NO era fade validado); ese LONG NO se reutiliza como correccion |
| H2 reversion (fade) | FAILED_LOW_CANDIDATE | LONG (fade contra la deriva) | NUEVA-HIPOTESIS (espejo; mismo descargo del SHORT mecanico v1) |
| H2 variante rebote | SIN definicion en P1-11C v1 | — | EXCLUIDA con causa (§4) |

## 2. Confirmacion observable por escenario (que lo haria evaluable)

- H1/H3: la formacion cerrada ES la condicion (heredada); entrada al
  siguiente open same-grid. Confirmaciones que sumarian evidencia (NO
  compuertas en v2, se registran en el selector): alineacion reciente
  1h, volumen elevado vs historia propia, fuerza relativa vs BTC.
- H2 agotamiento SHORT (`CONFIRM-H2-SHORT-v1`): dentro de las 3 velas
  same-grid siguientes a la formacion, una vela cierra at/below del
  close de formacion SIN que antes alguna cierre por encima del
  trailing_high (reclaim => INVALIDADA, descartada con motivo
  `h2-reclaim`, nunca operada). Confirmada: `formation_time'` = open de
  la vela de confirmacion, entrada al siguiente open. Sin confirmacion
  en 3 velas => descartada (`h2-no-confirmation`). Ventana 3 = IMPL
  revisable, no umbral validado.
- H2 reversion LONG (`CONFIRM-H2-LONG-v1`): espejo exacto.
- Datos exigidos por la confirmacion: opens/closes/highs/lows/volumen
  de velas cerradas + trailing high/low (disponibles en klines);
  NADA de flow/book/OI/spread en vivo (ausentes -> no se exigen).

## 3. Procedencia de cada numero (heredado / implementacion / hipotesis nueva)

- HEREDADOS (P1-11C v1 / V1, HYPOTHESIS, intactos): pisos 5%/0.5%,
  stop 0.5% gap-first (placeholder), nocional $1000 @1x,
  costes 5/1/2bps supuestos (COST-ASSUME-v1), cutoff 1790010000000
  (comparabilidad con V1), funding realizado trio (FUNDING-CAL-v1).
- HORIZONTE EFECTIVO `HORIZON-GRID4-V1` (IMPL, no optimizado): 4 velas
  same-grid (15m -> 1h heredado; 1h -> 4h). Motivo causal, no resultado:
  la regla de close conocido del motor (R1) exige al menos un close con
  `close_time <= horizon_end` dentro de la ventana; con horizonte 1h sobre
  velas 1h NINGUN close resuelve (demostrado: bruto identicamente 0,
  entrada == salida) porque el close de la vela de entrada cierra despues
  del fin de ventana y la siguiente vela queda fuera. Paridad de
  informacion: 4 velas en ambas resoluciones. Purga del harness = horizonte
  efectivo (1h en 15m, 4h en 1h).
- IMPL (reversibles, auditables): ENTRY-SAME-GRID-v1, ventana de
  confirmacion H2 = 3 velas, purga dev-crossing 1h (harness existente),
  `max_concurrent=1` intra-celda (motor existente).
- NUEVA-HIPOTESIS (requieren revision, jamas ajustadas a resultados):
  direcciones fade H2, pisos/ranking del selector (ver
  docs/EXTREME_SELECTOR_V1.md). Sin rebote definido.

## 4. Rebote: excluido con causa y condiciones de evaluabilidad

Sin definicion de bounce en P1-11C v1 (0 eventos): no evaluable.
Seria evaluable SI existieran versionados: (a) definicion washout +
  reclaim con banda y tolerancia, (b) confirmacion de volumen propio,
  (c) regla de contexto BTC (alineado/divergente) y (d) mapping aprobado.
  Hasta entonces: EXCLUIDO, nunca rellenado con el LONG/SHORT mecanico.
