# Censo causal de detecciones — CENSUS-V1 (offline, sin selecciones retrospectivas)

Version: `CENSUS-V1` (2026-10-17, sin corridas Binance, sin forward,
sin optimizacion de umbrales). Reutiliza definiciones P1-11C verbatim
(`events.default_definition` v1, `DESCRIPTIVE_RESEARCH_ONLY_HYPOTHESIS`)
y re-deriva TODAS las detecciones desde velas cerradas, SIN usar la
tabla `event_instances` como seleccion (solo como etiquetas de
comparacion: originales preservados, nunca como entrada).
Script: `scripts/reconstruct_causal_census.py`. Motor/runner intactos.

## 1. Reglas explicitas y versionadas

- `formation_time` = OPEN de la vela de formacion (la condicion necesita
  su CLOSE; conocible solo a `close_time`).
- `available_at` = `close_time` venue de la vela de formacion (mapa de
  cadena, no del precio). Prueba de disponibilidad POR close_time,
  no solo por open_time: `chain_ok` exige `close_time` conocido y
  `close_time <= siguiente open` (0 violaciones en las 3 series).
- `decision_time` = NULL por construccion (`no-live-detector-in-offline-census`):
  el censo offline no posee detector vivo; formacion, disponibilidad y
  decision se conservan separadas.
- Entradas `ENTRY-SAME-GRID-v1`: primer OPEN de LA MISMA resolucion con
  `open_time > formation_time`. Las detecciones 1h NO se reproducen sobre
  velas 15m (ninguna regla de cruce de resolucion queda definida aqui).
- IDs: `census_id` determinista por (version, familia, version-def, simbolo,
  intervalo, formation_time, indice). `original_event_id` conservado por
  clave (definicion, simbolo, tiempo, intervalo); duplicados
  (mismo simbolo+intervalo+formacion en varias familias) contados, nunca
  tratados como independientes.

## 2. Cobertura reconstruida (candidatos / admitidos / descartados / motivos)

Series disponibles (contrato Futures USDT, `regular_close`): trio 15m x2879
+ trio 1h x719 + MINA/NMR/ORCA 1h x719. Barras evaluadas por familia:
2874/serie 15m (warmup 5) y 714/serie 1h. Sin mezclar resoluciones.

| Serie | Familia | Barras | Fires (candidatos) | Admitidos | Gap-flag | Motivo no-fire dominante |
|---|---|---|---|---|---|---|
| BTC 15m | EXTENDED_GAINER | 2874 | 21 | 21 | 0 | below-threshold 2762 / missing 91 |
| BTC 15m | EXTENDED_LOSER | 2874 | 0 | 0 | 0 | above-threshold 2783 / missing 91 |
| BTC 15m | FAILED_HIGH | 2874 | 160 | 160 | 6 | no-failure-shape 2714 |
| BTC 15m | FAILED_LOW | 2874 | 62 | 62 | 6 | no-failure-shape 2812 |
| BTC 15m | MOM_DOWN | 2874 | 869 | 869 | 27 | above-threshold 1990 / missing 15 |
| BTC 15m | MOM_UP | 2874 | 885 | 885 | 22 | below-threshold 1974 / missing 15 |
| ETH 15m | EXTENDED_GAINER | 2874 | 30 | 30 | 0 | below-threshold 2753 / missing 91 |
| ETH 15m | EXTENDED_LOSER | 2874 | 11 | 11 | 0 | above-threshold 2772 / missing 91 |
| ETH 15m | FAILED_HIGH | 2874 | 99 | 99 | 4 | no-failure-shape 2775 |
| ETH 15m | FAILED_LOW | 2874 | 35 | 35 | 5 | no-failure-shape 2839 |
| ETH 15m | MOM_DOWN | 2874 | 901 | 901 | 30 | above-threshold 1958 / missing 15 |
| ETH 15m | MOM_UP | 2874 | 925 | 925 | 24 | below-threshold 1934 / missing 15 |
| SOL 15m | EXTENDED_GAINER | 2874 | 63 | 63 | 0 | below-threshold 2720 / missing 91 |
| SOL 15m | EXTENDED_LOSER | 2874 | 13 | 13 | 0 | above-threshold 2770 / missing 91 |
| SOL 15m | FAILED_HIGH | 2874 | 66 | 66 | 3 | no-failure-shape 2808 |
| SOL 15m | FAILED_LOW | 2874 | 36 | 36 | 3 | no-failure-shape 2838 |
| SOL 15m | MOM_DOWN | 2874 | 958 | 958 | 29 | above-threshold 1901 / missing 15 |
| SOL 15m | MOM_UP | 2874 | 987 | 987 | 26 | below-threshold 1872 / missing 15 |
| 1h x6 | EXTENDED_GAINER | 714 c/u | 7/8/85/36/50/18 | todos | 0 | below-threshold / missing 19 |
| 1h x6 | EXTENDED_LOSER | 714 c/u | 0/4/47/6/12/4 | todos | 0 | above-threshold / missing 19 |
| 1h x6 | FAILED_HIGH | 714 c/u | 2/2/3/7/7/5 | todos | 3 | no-failure-shape |
| 1h x6 | FAILED_LOW | 714 c/u | 3/1/1/1/4/1 | todos | 2 | no-failure-shape |
| 1h x6 | MOM_DOWN | 714 c/u | 220/220/246/247/258/240 | todos | 43 | above-threshold |
| 1h x6 | MOM_UP | 714 c/u | 223/222/244/251/274/240 | todos | 37 | below-threshold |

Totales: **9320 detecciones, 9320 admitidas, 0 descartadas**
(motivos de descarte definidos: `missing-close-time`, `chain-violation`;
ningun fire los activo: cadena intacta, 0 `close_time` nulos).
270 admitidas con `formation_gap` (flag, fuera de estadistica futura,
nunca borradas). 6 admitidas en borde de dataset (ultima vela) sin
entry same-grid (sin siguiente open conocido; honesto, no imputado).
`entry >= available` en 9314/9314 con entry existente (gap uniforme 1ms).
Duplicados cross-familia: 594 grupos (+616 filas extra) mismo
(simbolo, intervalo, formacion) — correlacionados por construccion.

## 3. Comparacion con las filas historicas (sin escoger por rendimiento)

Originales: 2831 `event_instances` (138 en 15m trio EXTENDED-only + 2693
en 1h). Coincidencias: **2831/2831 reproducidas** (`originals_only=0`):
la logica de formacion es determinista y queda preservada.

| Ambito | Originales | Reproducidas | Solo-censo (nunca corridas en piloto) |
|---|---|---|---|
| Trio 15m | 138 (solo EXTENDED) | 138/138 | 5983 (MOMENTUM± y FAILED± jamas almacenados en 15m) |
| 1h x6 | 2693 | 2693/2693 | 506 = NMR MOMENTUM± (498) + FAILED± (8): NMR solo tenia EXTENDED |
| Total | 2831 | 2831/2831 | 6489 |

Diferencias explicadas sin rendimiento posterior:
- El piloto P1-11C corrio familias por (simbolo, intervalo) de forma
  parcial: en 15m solo EXTENDED del trio; en NMR solo EXTENDED. Causa
  operativa exacta de esa seleccion: UNKNOWN (no se inventa); el efecto
  es medible: lo retenido es el 2.3% del censo exhaustivo en 15m.
- Reproducir la deteccion != reproducir la seleccion: el SET de 1558
  usado en OFFLINE-EVAL-V1 mezcla 1420 detecciones formadas en 1h
  reproducidas sobre velas 15m sin regla explicita. Este censo NO hace
  eso: cada deteccion vive en su resolucion (ENTRY-SAME-GRID-v1).
- Ninguna deteccion se incluye/excluye por resultado posterior: el
  censo no calcula outcomes; la comparacion es por claves de formacion.

## 4. Prefijo e invariancia (54/54 celdas) y close_time

Por cada (simbolo, intervalo, familia): detecciones con
`formation_time <= T` identicas entre corrida completa y corrida truncada
en T (prefijo 60%), e identicas tras mutar (x1.5) TODAS las velas con
`open_time > T`. Resultado: **54/54 celdas OK**
(6 BTC15m + 12 ETH/SOL15m + 36 1hx6), 0 malas.
Matiz de borde (declarado): mutar la propia vela EN T si altera el evento
que en ella se forma (dato de formacion, no posterior).
Disponibilidad por `close_time`: mapa venue por vela, 0 nulos, 0
violaciones de cadena en las 9 series; `available_at` derivado de la
cadena, nunca del precio; `entry` same-grid posterior o ausente honesta.

## 5. Limitaciones que conserva este censo

- `decision_time` NULL: sin detector vivo no hay senal operable; el censo
  es inventario causal, no seleccion en T.
- Sin universo/ranking historico: denominadores = barras evaluadas, no
  universo Binance; cobertura real del dataset cuantificada (§2), sin
  extrapolar al universo.
- BTC como contexto sincronizado at/before T ya viaja en `formation_features`
  (retornos 5m/15m/1h + relativo); su uso como filtro se evalua en el
  selector, no aqui.
- Sin capitalizacion medida: UNKNOWN (no inventar "low cap").
- Artefactos del censo (detections.jsonl/summary/compare) viven fuera de
  Git (temp); este documento + tests + script son la evidencia versionada.
