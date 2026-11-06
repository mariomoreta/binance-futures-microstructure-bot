# Validación offline de evidencia — public-pilot-1h-20261106a

run_id: public-pilot-1h-20261106a
SHA de ejecución (manifiesto.json git_head): f122fbc898821f4a985d071d5fd6efc1f469d9c4
SHA de publicación documental (commit 12ab9aa): 12ab9aa02caa29634b897d3b9095ec0241b58112

## 1. Copia de archivos originales

Archivos copiados de `C:\proyectos\binance-futures-data\public-pilot-1h-20261106a` a
`docs/evidence/coordinacion-recepcion-20261106/captura_publica_20261106a/`:

| Archivo | SHA-256 (origen) | SHA-256 (destino) | Igualdad |
|---------|-----------------|-------------------|----------|
| manifiesto.json | 5027AC287467F3BADEF27E93D361BA7CFBEA09B6A3468270C5035939F416CB3B | 5027AC287467F3BADEF27E93D361BA7CFBEA09B6A3468270C5035939F416CB3B | IGUAL |
| resumen.json | CF03BE4DFFB9930AE81D0BD157DCBB1DE2889CC8A3D3679D473D75DEF0C5A59B | CF03BE4DFFB9930AE81D0BD157DCBB1DE2889CC8A3D3679D473D75DEF0C5A59B | IGUAL |
| status.json | 14D48D458110DDE677DF3A2EDF7C705E23D0D5BB06E984FF303C2703F7B7AA0A | 14D48D458110DDE677DF3A2EDF7C705E23D0D5BB06E984FF303C2703F7B7AA0A | IGUAL |

Comando usado: `Copy-Item` de PowerShell (copia de bytes, sin reconstrucción ni transcripción).

## 2. Identidad de corrida

| Archivo | run_id |
|---------|--------|
| manifiesto.json | public-pilot-1h-20261106a |
| resumen.json | public-pilot-1h-20261106a |
| status.json | (campo ausente; mismo conjunto de datos) |

Todos los archivos pertenecen a la misma corrida `public-pilot-1h-20261106a`.

## 3. Conteos y vínculos desde archivos disponibles

| Métrica | Valor | Fuente |
|---------|-------|--------|
| Ciclos (kind=ciclo) | 12 | observaciones.jsonl |
| Evaluaciones (decision_ms únicos) | 12 | observaciones.jsonl |
| Observaciones | 216 | observaciones.jsonl |
| Observaciones aptas | 168 | observaciones.jsonl |
| Observaciones descartadas | 48 | observaciones.jsonl |
| Resultados | 504 | observaciones.jsonl |
| Resultados pendientes | 0 | observaciones.jsonl |
| Duplicados (observation_id) | 0 | observaciones.jsonl |
| Duplicados (observation_id, horizon) | 0 | observaciones.jsonl |
| Resultados con padre apto | 504/504 | observaciones.jsonl |

## 4. Intervalos entre decision_ms consecutivos

| Intervalo | Valor (ms) | Desviación de 300000 ms |
|-----------|-----------|------------------------|
| 1 → 2 | 300 211 | +211 |
| 2 → 3 | 283 007 | -16 993 |
| 3 → 4 | 300 083 | +83 |
| 4 → 5 | 300 053 | +53 |
| 5 → 6 | 300 383 | +383 |
| 6 → 7 | 300 245 | +245 |
| 7 → 8 | 300 014 | +14 |
| 8 → 9 | 300 178 | +178 |
| 9 → 10 | 300 121 | +121 |
| 10 → 11 | 300 066 | +66 |
| 11 → 12 | 300 043 | +43 |

Mínimo: 283 007 ms; Máximo: 300 383 ms; Promedio: 298 582 ms.
El intervalo 2→3 (283 007 ms) es 16 993 ms menor que 300 000 ms. No se atribuye a fallo; es dato observado.

## 5. Procedencia de cada métrica

| Métrica | Valor | Origen | Tipo |
|---------|-------|--------|------|
| started_ms | 1793942256629 | resumen.json / status.json / pilot.log | MEDIDO |
| ended_ms | 1793949250655 | resumen.json / status.json | MEDIDO |
| capture_end_ms | 1793945856629 | status.json | CALCULADO (started + 3600 s) |
| settle_end_ms | 1793950056629 | status.json | CALCULADO (started + 3600 + 4200) |
| HTTP attempts | 641 | resumen.json (rest.requests) | PERSISTIDO |
| HTTP weight (budget) | 1 109 | resumen.json (presupuesto_http.weight) | PERSISTIDO (tabla ASSUMED_WEIGHTS) |
| HTTP weight_spent | 6 890 | resumen.json (rest.weight_spent) | PERSISTIDO (tabla ASSUMED_WEIGHTS, HistoryClient) |
| HTTP retries | 0 | resumen.json (rest.retries / presupuesto_http.retries) | PERSISTIDO |
| WS messages | 960 114 | resumen.json (ws_messages_total) | PERSISTIDO |
| WS reconnects | 0 | resumen.json (ws_reconnects_total) | PERSISTIDO |
| Almacenamiento | 5 225 620 bytes | resumen.json (almacenamiento.storage_bytes_total) | PERSISTIDO |
| Fechas futuras | 0 violaciones | observaciones.jsonl (disponibilidad.* <= decision_ms + 1000 ms) | VERIFICADO en observaciones |

## 6. Código de salida

Código de salida observado: UNKNOWN. No hay archivo de control de terminación ni registro del shell padre. pilot.log contiene el resumen final pero no el código de proceso. La finalización normal se infiere del resumen (estado = "completo", stop_reason = "duracion"), pero no hay evidencia directa del código de salida del SO.

## 7. Correcciones documentales aplicadas

| Documento | Corrección |
|-----------|-----------|
| reconciliacion_observaciones_publica_20261106.md | Intervalos reales (283 007 ms en ciclo 2→3, desviación 16 993 ms); no se afirma compatibilidad ni incumplimiento automático |
| reconciliacion_consumo_publica_20261106.md | rest.weight_spent (6 890) es contador de HistoryClient con tabla ASSUMED_WEIGHTS, no peso real de cabeceras X-MBX-USED-WEIGHT-1M; ni 1 109 ni 6 890 son pesos de respuesta del servidor |
| reconciliacion_tiempos_publica_20261106.md | Código de salida: UNKNOWN (no hay evidencia directa); finalización normal inferida, no observada |
