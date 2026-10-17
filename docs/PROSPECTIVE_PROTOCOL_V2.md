# Protocolo prospectivo V2 — preparacion (NO ejecutado, NO adquirido)

Version: `PROSPECTIVE-PROTOCOL-V2` (2026-10-17, preparacion; ejecucion y
adquisicion NO autorizadas por este documento). V1 queda historico.
Reajustar sobre la ventana reservada: PROHIBIDO.
Parte de EVAL-CENSUS-V2 (veredicto: 0 celdas elegibles), CENSUS-V1,
SELECTOR-EXTREME-V1 (candidato) y MAP-CANDIDATE-v2 (no aprobado).

Bloqueador actual: NINGUNA hipotesis es elegible hoy (mapping sin aprobar
+ sin prueba live + costes supuestos + ventana no pristina). Este protocolo
fija las condiciones que levantarian el bloqueo, sin prometer rentabilidad.

## 1. Hipotesis y reglas (congeladas pre-datos)

Elegibles solo con `MAP-APPROVED-v2` (aprobacion humana pendiente; hasta
entonces NADA es elegible): H1 LONG y H3 SHORT (mecanica heredada,
sets same-grid exhaustivos) + H2 fade con `CONFIRM-H2-*-v1`
(ventana 3, IMPL revisable). Rebote: excluido hasta bounce aprobado.
Horizontes efectivos `HORIZON-GRID4-V1` (15m->1h, 1h->4h). Stop 0.5%
gap-first, $1000 @1x, escalas 1x/2x/3x, `max_concurrent=1` intra-celda.
Motor `backtest-offline/v4.2` + runner (hash de codigo registrado antes
del primer dato). Desarrollo CONGELADO antes de E1; un solo replay por
celda (re-ejecucion solo por bug demostrado, con informe y version nueva).

## 2. Universo: responde al selector (el trio es control, no validacion)

Poblacion pre-registrada por criterios (liquidez, continuidad de klines,
calendario funding adquirible) + veredictos `SELECTOR-EXTREME-V1`
(WATCH/DESCARTADO con motivos) persistidos por scan desde el dia 0
segun `UNIVERSE-HISTORY-ACQ-V1`. BTC/ETH/SOL son CONTROL + cobertura
minima inicial: jamas validan el objetivo de extremos sobre el universo.
Sin snapshots desde el dia 0, lo anterior es UNKNOWN para siempre
(sin backfill retrospectivo).

## 3. Duracion y muestra: justificacion por dependencia, no por N crudo

Piso: 30 dias de la resolucion evaluada. "30 dias/100 eventos" NO
demuestra suficiencia: el censo mide solapes intra-celda de hasta 65% y
duplicados cross-familia (~6.6% filas extra), luego N crudo sobrestima
la informacion independiente. Criterio pre-registrado: por familia
elegible, semi-amplitud del IC95% de E[net]R <= 1.0 USDT/op con error
estandar robusto por clusters (cluster = dia-simbolo-grupo de
formacion; duplicados cross-familia colapsados a un cluster). El 1.0 se
justifica por escala de friccion (~1.6/op): el intervalo debe resolver
por debajo del coste, no por resultado visto (ningun dato usado para
fijarlo; valor IMPL revisable antes del inicio, nunca despues).
Piso operativo: >=100 eventos admitidos Y >=30 clusters por familia
elegible; H2 queda descriptiva por debajo. Ventana E1: pristina
(jamas resumida antes del primer replay).

## 4. Ventana de ingenieria E0 separada de la evaluacion E1

E0 (ingenieria, ventana corta autorizada aparte): prueba de formacion en
streaming (el detector computa la formacion al `close_time`, latencia
medida; query != tradable declarado), flujo de snapshots de universo,
cadena close_time intacta. Datos de E0 JAMAS entran a la economia.
E1 (evaluacion reservada): replay unico pre-registrado sobre ventana
nueva. Sin re-corte post-hoc; fallos de adquisicion siguen criterio
escrito antes (extension o aborto pre-registrado).

## 5. Funding futuro: metodo fijo antes, tasas realizadas al publicarse

Adquisicion pre-registrada (fuente venue fundingRate por simbolo, job
versionado, calendario pineado por simbolo). Las tasas realizadas se
incorporan al calendario al publicarse (cada 8h); NO se exige conocerlas
anticipadamente (no hay foresight: la contabilidad v4.2 por settlement
solo usa tasas publicadas at/before cada settlement). Posiciones con
holding sobre settlements aun no publicados al cierre de ventana =
UNKNOWN (nunca cero). Calendario sin cobertura total para un simbolo =
simbolo excluido con causa (no imputado).

## 6. Exclusiones, baseline, riesgo, costes, metricas, rechazo (pre-fijados)

Exclusiones: formation_gap, chain-violation, H2 sin confirmacion o con
reclaim, rebote (sin definicion), simbolos sin calendario completo,
clusters < piso. Baseline: `TIME-PLACEBO-v1` (misma cadencia, costes,
horizonte y calendarios; seed fijado). Riesgo: limites RISK_RULES
vigentes + kill por staleness/outage/mismatch (sin posiciones reales:
aplica a la validez de la ventana). Costes: tier documentado o
escenarios pre-fijados + sensibilidad 1x/2x/3x (supuesto != medido).
Metricas primarias: E[net]R y total_net_realized @1x + s* + E[net] @2x/@3x
(realizadas separadas de abiertas; pooled solo referencia aritmetica).
Aceptacion: E[net]R H1/H3 supera al placebo fuera de su distribucion con
1x Y sobrevive a 2x Y precision §3 cumplida. Rechazo: s* < 2 en todas,
o placebo indistinguible, o cobertura < minima, o violacion causal, o
reajuste detectado, o N-efectivo < piso.

## 7. Siguiente accion exacta (no ejecutada)

1. Aprobacion humana de `MAP-APPROVED-v2` (o constancia de bloqueo).
2. Ventana E0 autorizada (prueba live de formacion + universo).
3. Autorizacion separada para adquirir E1 (solo datos publicos) con este
   protocolo como contrato. 4. Replay unico + informe contra §6.
   Sin estos pasos, NADA avanza gates (G9/P2/P3 intactos).
