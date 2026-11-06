# Reconciliación de consumo y cumplimiento — public-pilot-1h-20261106a

run_id: public-pilot-1h-20261106a
Fuente: resumen.json (contadores persistidos del piloto, no estimaciones del presupuesto).

## 1. HTTP

| Métrica | Valor | Límite | Veredicto |
|---------|-------|--------|-----------|
| Intentos (attempts) | 641 | 2 000 | ACREDITADO |
| Peso (budget_http.weight) | 1 109 | 5 000 | ACREDITADO |
| Reintentos (retries) | 0 | 50 | ACREDITADO |
| Bloqueado | false | — | ACREDITADO |
| Fallos (rest.failures) | 0 | — | ACREDITADO |
| Peso gastado (rest.weight_spent) | 6 890 | — | Informativo (cabecera X-MBX-USED-WEIGHT de Binance; distinto del peso de presupuesto) |

Nota: `presupuesto_http.weight` (1 109) y `rest.weight_spent` (6 890) miden cosas distintas. El primero es el peso efectivo del presupuesto interno (intentos × peso unitario estimado), acotado por max_http_weight = 5 000. El segundo es el peso real reportado por las cabeceras de Binance (X-MBX-USED-WEIGHT-1M), que no está sujeto al mismo tope de 5 000 del presupuesto interno. Ambos están dentro de sus respectivos contextos.

## 2. WebSocket

| Métrica | Valor | Límite | Veredicto |
|---------|-------|--------|-----------|
| Conexiones totales acumuladas | 20 | — (máx teórico 24) | ACREDITADO |
| Conexiones simultáneas pico | 2 | 2 | ACREDITADO (1 /public + 1 /market) |
| Mensajes WS totales | 960 114 | 5 000 000 | ACREDITADO |
| Reconexiones totales | 0 | 20 | ACREDITADO |
| Desconexiones (market/public) | 1 / 1 | — | Desconexiones normales al finalizar |

## 3. Almacenamiento

| Métrica | Valor | Límite | Veredicto |
|---------|-------|--------|-----------|
| Almacenamiento total | 5 225 620 bytes | 134 217 728 bytes | ACREDITADO (3.9 %) |
| JSONL bytes | 3 112 084 | — | — |
| SQLite bytes | 2 113 536 | — | — |
| JSONL rows | 732 | — | — |
| Recorder writes | 8 823 | — | — |
| Recorder drops | 0 | — | — |
| Recorder errors | 0 | — | — |

## 6. Veredicto por criterio de límite

| Criterio | Valor reportado | Límite | Estado |
|----------|----------------|--------|--------|
| HTTP attempts | 641 | 2 000 | ACREDITADO |
| HTTP weight (presupuesto) | 1 109 | 5 000 | ACREDITADO |
| HTTP retries | 0 | 50 | ACREDITADO |
| WS reconnects | 0 | 20 | ACREDITADO |
| WS messages | 960 114 | 5 000 000 | ACREDITADO |
| Almacenamiento | 5 225 620 | 134 217 728 | ACREDITADO |
| 0 fechas futuras (observaciones) | 0 violaciones | — | ACREDITADO (alcance: observaciones emitidas) |

## 7. Alcance de "0 fechas futuras"

El comprobado es que **ninguna de las 216 observaciones publicadas** tiene disponibilidad.* (seleccion_ms, libro_ms, flujo_ms) superior a su decision_ms + 1 000 ms (tolerancia FUTURE_EVENT_TOLERANCE_MS del piloto). Los mensajes WS crudos no se persisten, por lo que no se puede afirmar "0 fechas futuras en todos los mensajes WS"; el alcance comprobado es el de las observaciones emitidas por el piloto.

## 6. No hay incumplimientos

No se detectó ningún sobregiro de límite. Todos los contadores persistidos están dentro de sus respectivos topes. Ningún criterio se presenta como incumplido ni como "cero por ausencia de evidencia": todos los valores provienen de contadores persistidos en resumen.json.
