# Reconciliación de tiempos — public-pilot-1h-20261106a

run_id: public-pilot-1h-20261106a
SHA de ejecución (en manifiesto.json, campo git_head): f122fbc898821f4a985d071d5fd6efc1f469d9c4
SHA posterior de publicación documental: b9eff01b664a62f8a791ccfbb43ba0ee63e11e9c

## 1. Instantes (todos en UTC)

| Momento | Valor (ms ISO) | Valor legible | Origen | Tipo |
|---------|---------------|---------------|--------|------|
| Inicio real (started_ms) | 1793942256629 | 2026-11-06T05:17:36.629Z | resumen.json / status.json / pilot.log | MEDIDO |
| Fin de captura (capture_end_ms) | 1793945856629 | 2026-11-06T06:17:36.629Z | status.json (campo capture_end_ms) | CALCULADO (started_ms + duration_seconds = 05:17:36.629 + 3600 s) |
| Fin del proceso / fin de settle medido (ended_ms / now_ms final) | 1793949250655 | 2026-11-06T07:14:10.655Z | resumen.json (ended_ms) / status.json (now_ms final) / pilot.log | MEDIDO |
| Límite nominal captura + settle | 1793950056629 | 2026-11-06T07:27:36.629Z | Calculado (started_ms + 3600 + 4200) | CALCULADO (no alcanzado) |

## 2. Qué representa realmente 07:14:10.655Z

**07:14:10.655Z es el fin del proceso (ended_ms / now_ms final), es decir, el fin del settle medido.** NO es el fin nominal de captura (06:17:36.629Z) ni el límite nominal de captura+settle (07:27:36.629Z).

Secuencia temporal real:
1. **05:17:36.629Z** — Inicio de captura (started_ms, medido).
2. **06:17:36.629Z** — Fin nominal de captura (capture_end_ms = started_ms + 3600 s, CALCULADO). A esta hora el piloto deja de seleccionar/evaluar; la última observación tiene decision_ms 06:13:48.365Z (último corte dentro de la captura).
3. **06:17:36.629Z → 07:14:10.655Z** — Fase de settle. El piloto madura resultados pendientes (resuelve klines). Como ya no quedaban pendientes (pendiente = 0 en resumen.json), el settle terminó **antes** de su límite nominal.
4. **07:14:10.655Z** — Fin del proceso (ended_ms, medido). El proceso se detuvo aquí porque el settle ya no tenía pendientes que procesar; no esperó hasta el límite nominal de 07:27:36.629Z.
5. **07:27:36.629Z** — Límite nominal capture + settle (CALCULADO, NO alcanzado).

## 3. ¿El settle terminó temprano?

**Sí.** El settle terminó temprano porque no quedaban resultados pendientes (n_pendientes = 0 en resumen.json; todos los 504 resultados están en estado "resuelto"). El bucle de settle del piloto corre `while (clock < settle_end_ms AND pending AND not terminal_stop)`; al vaciarse `pending`, sale antes del límite nominal.

Por tanto:
- Fin de captura medido: NO hay un evento separado de "fin de captura"; se infiere como started_ms + duration_seconds = 06:17:36.629Z (CALCULADO).
- Fin de settle medido: 07:14:10.655Z (ended_ms, MEDIDO).
- Fin del proceso: 07:14:10.655Z (medido, coincide con fin de settle).
- Límite nominal capture+settle: 07:27:36.629Z (CALCULADO, no alcanzado).

## 4. Código de salida

Código de salida observado: UNKNOWN. El archivo pilot.log contiene el resumen final del piloto ({"run_id": "public-pilot-1h-20261106a", "estado": "completo", ...}), pero no incluye un código de salida de proceso. No existe archivo de control de terminación (exit code file) ni registro del shell padre en los archivos de la corrida. La finalización normal se infiere del resumen (estado = "completo", stop_reason = "duracion") y del camino de salida normal del código (main() retorna 0 al finalizar pilot.run() sin excepción), pero no hay evidencia directa del código de salida del sistema operativo.

## 5. Distinción de tipos

- Medido: started_ms (05:17:36.629Z), ended_ms/now_ms final (07:14:10.655Z), decision_ms de cada observación/resultado.
- Calculado: capture_end_ms (06:17:36.629Z), settle_end_ms (07:27:36.629Z) — derivados de started_ms + duration_seconds / + settle_seconds.
- Inferido: que el capture se mantuvo activo hasta capture_end (basado en stop_reason = "duracion" y en que la última observación es anterior a capture_end); que el settle terminó temprano por pending vacío (basado en n_pendientes = 0 y en que ended_ms < settle_end_ms).
