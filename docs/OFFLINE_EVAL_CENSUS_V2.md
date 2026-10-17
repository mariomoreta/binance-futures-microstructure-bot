# Evaluacion offline sobre censo same-grid — EVAL-CENSUS-V2 (condicionada, NO validacion)

Version: `EVAL-CENSUS-V2` (2026-10-17, sin corridas, sin forward, sin
optimizar umbrales). OFFLINE-EVAL-V1 queda como historico intacto.
Motor `backtest-offline/v4.2` y runner reutilizados SIN cambios salvo un
flag aditivo del harness (`--horizon-ms`, default 1h = conducta previa;
ver §2). Mapping: `MAP-CANDIDATE-v2` (NO aprobado). Rebote: excluido.
Censo: `CENSUS-V1` (docs/CAUSAL_CENSUS_V1.md). Selector: candidato
docs/EXTREME_SELECTOR_V1.md (no usado como filtro aqui: esta evaluacion
mide familias, no el selector).

## 1. Flujo de eventos (censo → excluidos → purga → solape → cerradas/abiertas)

Resoluciones NUNCA mezcladas; horizontes efectivos `HORIZON-GRID4-V1`
(15m -> 1h, 1h -> 4h). Cutoff unico 1790010000000 (comparabilidad V1).
Calendarios funding realizado trio (FUNDING-CAL-v1). Costes supuestos
COST-ASSUME-v1 (5/1/2bps), escalas 1x/2x/3x. Nocional $1000 @1x.

15m trio (censo 6121 = 2839 H1 + 2664 H3 + 212 H2ex + 77 H2rev + 185 gap
+ 2 sin-entry + 43 H2-sin-confirmacion + 99 H2-reclaim):
construidas 5792 direccionales + 5792 placebo (TIME-PLACEBO-v1, seed 42);
purga dev-crossing 14 (4+6+4); solapes intra-celda 7515 (peor:
SOL cont-dev 307/475 = 65%); 4055 trades @1x (BTC 1316 + ETH 1350 +
SOL 1389); abiertas `open_at_end` 3 (una por trio-oos direccional);
mismatched 0, expired 0.

1h trio (censo 1420 = 699 H1 + 666 H3 + 8 H2ex + 2 H2rev + 40 gap +
2 sin-entry + 3 reclaim): 1375 direccionales + 1375 placebo; purga 16
(3+7+6); solapes intra-celda 1107; 1200 trades @1x (BTC 378 + ETH 382 +
SOL 440); abiertas 4 (marcas de cola, excluidas de metricas-R);
mismatched 0, expired 0.

Total EVAL-CENSUS-V2: 5255 trades @1x. Cross-celda (grupos, simbolos,
dev/oos) replayada en ledgers separados: simultaneidad NO modelada;
pooled NO calculado (ninguna suma presentada como cartera).

## 2. Hallazgo de barrera: horizonte efectivo por resolucion

`HORIZON-GRID4-V1` (IMPL, causal, no optimizado): la regla de close
conocido del motor (R1) exige un close con `close_time <= horizon_end`
dentro de la ventana. Con horizonte 1h sobre velas 1h NINGUN close
resuelve (demostrado: entry == exit, bruto identicamente 0): la
combinacion es degenerada por construccion, no un resultado. El flag
`--horizon-ms` del runner es aditivo (default 1h; tests previos verdes)
y queda registrado en el manifiesto (`exit_horizon_ms`).
Paridad: 4 velas en ambas resoluciones. Pruebas:
`tests/test_eval_horizon_grid.py` (degenerado 1h/1h, resuelve 4h/1h y
1h/15m, default preservado).

## 3. Economia condicionada @1x (USDT por $1000 @1x; R = solo-realizadas)

15m H1 LONG: BTC dev 145 -1.456 / oos 185R -1.375; ETH dev 158 -1.221 /
oos 188R+1 -1.946; SOL dev 168 -1.742 / oos 192R+1 -1.570.
Todas negativas @1x (brutos +0.03...+0.38, friccion ~1.60).
15m H3 SHORT: BTC dev -2.283 / oos -1.306R; ETH dev -2.309 / oos -1.695;
SOL dev -2.149 / oos -1.684. Todas negativas @1x (brutos -0.71...+0.29).
15m H2 fade (nuevo, confirmadas): exh BTC 24 -1.848 / 35 -1.245;
ETH 13 -2.246 / 26 -1.109; SOL 19 -1.035 / 18 -0.096 (bruto +1.486,
s* 0.94, mejor celda direccional 15m). rev BTC 13 -0.703 / 13 -2.859;
ETH 5 -2.417 / 11 -1.990; SOL 8 -2.169 / 8 **+0.687** (bruto +2.289,
s* 1.43, n=8 INSUFFICIENT: reportada, cercada, no evidencia).
1h H1 LONG (horizonte 4h): BTC dev 51 -2.078 (bruto -0.449) /
oos 62 -1.199 (bruto +0.411, s* 0.26); ETH dev 52 -1.180 (bruto +0.431,
s* 0.27) / oos 61 -1.652R (bruto -0.035); SOL dev 59 -2.241 (bruto
-0.633) / oos 72 -1.535 (bruto +0.073). Todas negativas @1x.
1h H3 SHORT (4h): BTC dev 49 -2.283 (bruto -0.705) / oos 61 -1.151
(bruto +0.442, s* 0.28); ETH dev 50 -0.975 (bruto +0.617, s* 0.39) /
oos 66 -1.408 (bruto +0.177); SOL dev 57 -2.168 / oos 73 -1.875R.
Todas negativas @1x.
1h H2 fade: n<=4 en todas las celdas (correction-e BTC dev n=1 +2.026,
correction-r BTC oos n=1 +6.599, SOL ce-dev n=4 -3.634 y ce-oos n=1
stopped -6.504: ANECDOTAS cercadas, no lectura; H2-reversal 1h de ETH y
SOL con 0 eventos: excluidas).

Sensibilidad: TODAS las celdas direccionales con n>=30 son negativas a
2x y 3x (incl. SOL corr-r-oos +0.687 -> -0.915 -> -2.517). s* maximo en
celdas suficientes: 0.56 (BTC corr-r-dev n=13, insuficiente).

## 4. Baseline TIME-PLACEBO-v1 (misma cobertura y costes)

Placebo 15m @1x: BTC dev -1.513 / oos -1.559; ETH -1.447 / -1.822;
SOL -2.201 / -1.383. Placebo 1h @1x: BTC dev -2.221 / oos -2.259; ETH dev -1.450 /
oos -1.534; SOL dev -0.704 (bruto +0.900, s* 0.56) / oos -2.596R.
El placebo SOL-1h-dev (-0.704) supera a las direccionales SOL-1h-dev
(H1 -2.241, H3 -2.168): varias celdas direccionales rinden PEOR que
exposicion aleatoria equivalente. Ninguna celda direccional supera al
placebo Y sobrevive a 2x (criterio de aceptacion del protocolo): las
H1/H3 estan dentro o debajo de la banda placebo; las dos celdas H2 con
mejor bruto (SOL 15m) fallan 2x y tienen n insuficiente.

## 5. Funding, exposicion, abiertas, purga (conservado de V1)

Funding realizado con signo: 741 liquidaciones aplicadas en ventana
(0 unknown-excluded en las 60 celdas; todo settlement en ventana liquido
sobre marca fresca); 24/60 celdas con holdings de cola fuera del
calendario = uncovered/UNKNOWN (nunca cero; p. ej. BTC15m cont-oos
182/185 completas). Realizadas separadas de abiertas (sufijo R y
`total_net_realized`; 7 marcas abiertas en total, costes hipoteticos de
salida separados). Purga dev-crossing segun horizonte efectivo (14 en
15m, 16 en 1h). Exposicion: `max_concurrent=1` INTRA-celda (hasta 65% de
skips en SOL cont-dev); cross-celda no modelada, no reclamada.
MFE 0.18-0.66% / MAE 0.10-0.42%: existe excursion favorable; la captura
es pregunta de regla de salida no respondida aqui.

## 6. Veredicto (criterio pre-fijado §7 del protocolo, sin reajustes)

0 celdas elegibles para operacion: ninguna supera al placebo con costes
1x Y sobrevive a 2x. H1/H3: RECHAZADAS (negativas @1x en 12/12 celdas
15m y 6/6 1h). H2 fade: RECHAZADO como metodologia (mejor s* < 2 o n
insuficiente; anecdotas n=1 cercadas). Rebote: sigue EXCLUIDO.
Etiquetas: in-sample/non-pristine (misma ventana que V1 + definiciones
predeterminadas, reutilizacion declarada), costes supuestos, seleccion
exhaustiva same-grid (el sesgo de subconjunto retrospectivo de V1 queda
eliminado; subsisten: ventana no pristina, sin prueba live, mapping
candidato). Sin optimizacion: umbrales intactos, reglas v2 versionadas
ANTES de los replays (docs/HYPOTHESIS_MAPPING_CANDIDATE_V2.md),
formacion `--formation-method MAP-CANDIDATE-v2-census-same-grid` en
manifiestos (hashes e0c231a7/d2794e1c/e5cdca53/416a0007/b2c1d0e0/9766ab7a).

## §A. Tablas por celda y reproduccion

Manifiestos (temp, fuera de Git): `eval15_btc/manifest_BTCUSDT_15m.json`,
`eval15_ethsol/manifest_{ETH,SOL}USDT_15m.json`,
`eval1h_trio/manifest_*_1h.json` (+ `both_*` = dev+oos purgados,
`selection_*` con conteos, `build_report.json` con la construccion).
Reproduccion: `scripts/build_census_eval_inputs.py --detections <censo>
--symbols ... --interval ... --out-dir ...` (seed 42) ->
`select_eval_events.py --cutoff-ms 1790010000000 --horizon-ms <3600000 |
14400000>` -> `run_family_evaluation.py --horizon-ms <mismo> --calendar
docs/evidence/FUNDING_CALENDAR_<SYM>_V1.json --formation-method
MAP-CANDIDATE-v2-census-same-grid`. Celdas con abiertas marcadas †
(valores R en §3 donde aplica).

## 7. Matriz de resultados (A/B/C) y limitaciones

### A. Resultados de reglas sobre el censo histórico disponible (EVALADO)

Reglas H1/H3/H2-fade sobre CENSUS-V1 exhaustivo (9320 detecciones,
9320 admitidas, 0 descartadas; entry>=available 9314/9314; 594 grupos
duplicados contados, nunca independientes). 5255 trades @1x
(4055 15m + 1200 1h). 0 celdas elegibles: ninguna supera al placebo Y
sobrevive 2x. H1/H3 RECHAZADAS (18/18 15m + 6/6 1h negativas @1x).
H2 fade RECHAZADO como metodologia (mejor s* < 2 o n insuficiente;
anecdotas n=1 cercadas, no lectura). Funding: 741 liquidaciones
aplicadas (0 UNKNOWN-excluded en 60 celdas); 24/60 celdas con
holdings de cola fuera de calendario = uncovered/UNKNOWN. Placebo
TIME-PLACEBO-v1 seed 42, misma cobertura/costes; una realizacion,
no distribucion. HORIZON-GRID4-V1: degeneracion 1h/1h demostrada
(entry==exit, bruto 0 por construccion); separacion explicita vs
experimento original OFFLINE-EVAL-V1 (horizonte 1h por defecto).
No es optimizacion validada. Limitaciones: in-sample/non-pristine,
costes supuestos COST-ASSUME-v1, mapping candidato MAP-CANDIDATE-v2,
sin prueba live, MFE/MAE no capturados (pregunta de regla de salida
no respondida).

### B. Selector probado con fixtures (MECANISMO, NO evaluado)

SELECTOR-EXTREME-V1: mecanismo de seleccion rank/coverage probado con
sinteticos (tests/test_extreme_selector.py). Cobertura de
universe/liquidez UNKNOWN (sin historico de ranking ni spread/depth);
market_cap UNKNOWN (nunca low-cap-by-proxy). Ranking != entry
(disciplina opportunity-engine). Umbrales HYPOTHESIS (INHERITED de
P1-11C v1, no validados). NO aprobado como senal, NO evaluado sobre
el censo (el censo mide familias, no el selector).

### C. Estrategia completa de extremos sobre universo y liquidez (NO EVALUADA)

Falta datos: universe_ranking_history, liquidity_spread_depth,
market_cap datado. Sin estos inputs, estrategia completa de extremos
sobre universo y liquidez NO EVALUADA donde falten datos. El selector
registra UNKNOWN cuando el historico esta ausente (no inventa
cobertura). Consecuencia: all 9320 detections at best PARTIAL-input;
full-input decisions impossible on this dataset.
