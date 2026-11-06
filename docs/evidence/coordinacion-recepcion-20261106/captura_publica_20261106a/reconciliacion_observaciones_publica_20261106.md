# Reconciliación de observaciones y resultados — public-pilot-1h-20261106a

run_id: public-pilot-1h-20261106a
Fuente: observaciones.jsonl (análisis completo de las 216 observaciones y 504 resultados, archivo original de la corrida, solo lectura).

## 1. Conteo global

| Métrica | Valor | Verificado en |
|---------|-------|---------------|
| Ciclos de selección (kind=ciclo) | 12 | observaciones.jsonl |
| Evaluaciones (decision_ms únicos) | 12 | observaciones.jsonl |
| Observaciones (kind=observacion) | 216 | observaciones.jsonl |
| Observaciones aptas | 168 | observaciones.jsonl |
| Observaciones descartadas | 48 | observaciones.jsonl |
| Resultados (kind=resultado) | 504 | observaciones.jsonl |
| Resultados pendientes | 0 | observaciones.jsonl |
| observation_ids duplicados | 0 | observaciones.jsonl |
| (observation_id, horizon) duplicados | 0 | observaciones.jsonl |
| Resultados con observación apta padre | 504/504 | observaciones.jsonl |
| Resultados sin padre apto | 0 | observaciones.jsonl |

## 2. Resultados por horizonte

| Horizonte | Resueltos | Pendientes | No evaluables | Total |
|-----------|-----------|------------|---------------|-------|
| 5m | 168 | 0 | 0 | 168 |
| 15m | 168 | 0 | 0 | 168 |
| 60m | 168 | 0 | 0 | 168 |
| Total | 504 | 0 | 0 | 504 |

Cada observación apta (168) genera exactamente 3 resultados (uno por horizonte): 168 × 3 = 504. Todos resueltos, 0 pendientes.

## 3. Observaciones por ciclo y rol

| # | decision_ms | Fecha UTC | Total obs | Candidate | Comparator | Aptas | Descartadas |
|---|-------------|-----------|-----------|-----------|------------|-------|-------------|
| 1 | 1793942343961 | 05:19:03.961 | 20 | 12 | 8 | 20 | 0 |
| 2 | 1793942644172 | 05:24:04.172 | 20 | 12 | 8 | 13 | 7 |
| 3 | 1793942927179 | 05:28:47.179 | 20 | 12 | 8 | 14 | 6 |
| 4 | 1793943227262 | 05:33:47.262 | 16 | 11 | 5 | 12 | 4 |
| 5 | 1793943527315 | 05:38:47.315 | 20 | 12 | 8 | 18 | 2 |
| 6 | 1793943827698 | 05:43:47.698 | 15 | 11 | 5 | 13 | 2 |
| 7 | 1793944127943 | 05:48:47.943 | 18 | 11 | 7 | 13 | 5 |
| 8 | 1793944427957 | 05:53:47.957 | 18 | 12 | 6 | 11 | 7 |
| 9 | 1793944728135 | 05:58:48.135 | 19 | 11 | 8 | 16 | 3 |
| 10 | 1793945028256 | 06:03:48.256 | 14 | 11 | 3 | 11 | 3 |
| 11 | 1793945328322 | 06:08:48.322 | 19 | 11 | 8 | 16 | 3 |
| 12 | 1793945628365 | 06:13:48.365 | 17 | 11 | 6 | 11 | 6 |
| **Total** | | | **216** | **136** | **80** | **168** | **48** |

Intervalos entre ciclos: 300 211 ms, 300 007 ms, 300 083 ms, 300 053 ms, 300 383 ms, 300 245 ms, 300 014 ms, 300 178 ms, 300 121 ms, 300 066 ms, 300 043 ms — todos coherentes con cycle_seconds = 300 s (desviación máxima 383 ms, dentro del tick de 500 ms del piloto).

## 4. Explicación de 216 < 240

**20 símbolos es el máximo simultáneo, no una obligación de generar 240 observaciones.** Las selecciones rotan símbolos (n_rotaciones_salida = 25 símbolos salieron del seguimiento durante la corrida). Por tanto, no todos los 20 símbolos estuvieron presentes en los 12 ciclos:

- 12 símbolos estuvieron en todos los 12 ciclos (12 observaciones cada uno).
- 16 símbolos participaron en menos ciclos (entre 1 y 11 observaciones cada uno).
- 28 símbolos únicos aparecieron en total a lo largo de las 12 selecciones.

Ejemplos de rotación: PIEVERSEUSDT (1 obs), POWRUSDT (1 obs), BEAMXUSDT (2 obs), SOPHUSDT (2 obs) — símbolos que entraron tarde o salieron temprano. La diferencia 240 − 216 = 24 observaciones "faltantes" se explica por símbolos que no estuvieron presentes en todos los ciclos, no por un fallo del piloto.

## 5. Motivos de descarte (con solapamiento)

| Motivo | Conteo |
|--------|--------|
| dato_obsoleto_flujo | 47 |
| dato_obsoleto_libro | 4 |
| flujo_ventana_incompleta | 1 |
| **Suma de motivos** | **52** |
| **Descartadas totales** | **48** |

La suma de motivos (52) no tiene que ser igual al número de descartadas (48) porque una observación descartada puede tener varios motivos simultáneos (ej. flujo obsoleto Y ventana incompleta). Cada observación descartada tiene al menos un motivo.

## 6. Integridad: padre-hijo y fechas futuras

- **Cada resultado tiene una observación apta padre:** 504/504 resultados tienen un observation_id que coincide con una observación con `apto_para_evaluacion = true`. 0 resultados sin padre.
- **No hay duplicados:** 216 observation_ids únicos, 504 pares (observation_id, horizon) únicos.
- **Fechas futuras:** 0 observaciones con disponibilidad.* > decision_ms + 1000 ms (tolerancia FUTURE_EVENT_TOLERANCE_MS del piloto). Este comprobado cubre **las observaciones publicadas** (libro_ms, flujo_ms, selección_ms <= decision_ms). No se persisten todos los mensajes WS crudos, por lo que no se puede afirmar "0 fechas futuras en todos los mensajes WS"; el alcance comprobado es el de las observaciones emitidas.

## 7. Veredicto por criterio

| Criterio | Veredicto | Evidencia |
|----------|-----------|-----------|
| 12 selecciones | ACREDITADO | 12 registros kind=ciclo |
| 12 evaluaciones | ACREDITADO | 12 decision_ms únicos en observaciones |
| 216 observaciones | ACREDITADO | conteo directo en observaciones.jsonl |
| 168 aptas | ACREDITADO | estado = observada y apto_para_evaluacion = true |
| 48 descartadas | ACREDITADO | estado = descartada |
| 168 resultados por horizonte | ACREDITADO | 5m/15m/60m = 168 resueltos cada uno |
| 504 resultados totales | ACREDITADO | conteo directo |
| 0 pendientes | ACREDITADO | pendiente = 0 en todos los horizontes |
| 0 duplicados | ACREDITADO | observation_ids y (observation_id,horizon) únicos |
| Padre-hijo válido | ACREDITADO | 504/504 resultados con padre apto |
| 0 fechas futuras (observaciones) | ACREDITADO | verificado en las 216 observaciones |
