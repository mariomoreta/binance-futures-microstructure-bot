# Reconciliación y cierre — captura pública public-pilot-1h-20261106a

run_id: public-pilot-1h-20261106a
Carpeta de evidencia: C:\proyectos\binance-futures-data\public-pilot-1h-20261106a\_evidence_publish (fuera de Git)
Documentos publicados en Git: docs/evidence/coordinacion-recepcion-20261106/traza_captura_publica_20261106.md

## 1. Identidad y versiones

| Concepto | Valor |
|----------|-------|
| run_id | public-pilot-1h-20261106a |
| SHA de ejecución (manifiesto.json → git_head) | f122fbc898821f4a985d071d5fd6efc1f469d9c4 |
| SHA posterior de publicación documental (HEAD actual) | b9eff01b664a62f8a791ccfbb43ba0ee63e11e9c |
| Rama | research/universe-liquidity-v1 |
| PILOT_VERSION | research-pilot-v1 |
| POLICY_VERSION | research-selector-v2 |
| PROTOCOL_VERSION | prospective-protocol-v1 (captura_protocol_version = 3) |

Distingue:
- **SHA de ejecución (f122fbc):** el código que ejecutó la captura pública, registrado en manifiesto.json (campo git_head). Es el SHA vigente al momento de ejecutar.
- **SHA de publicación documental (b9eff01):** el commit que contiene esta reconciliación y los documentos de cierre, posterior a la ejecución.
- **Configuración propuesta vs ejecutada:** la configuración ejecutada coincide con la propuesta (3600 s captura, 4200 s settle, selection_seconds=300, cycle_seconds=300, max_data_age_ms=5000, 12 candidatos/8 comparadores, max 20 símbolos, horizontes 5m/15m/60m). Una diferencia documental: el archivo comando.txt guardado en la corrida contiene `--budget-only` (era la preflight); el comando efectivo ejecutado NO tenía `--budget-only` y sí añadía `--status-file`. Esto queda documentado en `comando_efectivo.txt`.

## 2. Archivos autoritativos (solo lectura, fuera de Git)

| Archivo | Tamaño | SHA-256 | Contenido |
|---------|--------|---------|-----------|
| observaciones.jsonl | 3 112 084 | 43cc26e529b38e97494217d3015f4a42f826bf515f0df34898d9a764a54a1165 | 216 observaciones + 504 resultados + 12 ciclos |
| resumen.json | 6 277 | cf03be4dffb9930ae81d0bd157dcbb1de2889cc8a3d3679d473d75def0c5a59b | Resumen final, consumo, límites, horizontes |
| manifiesto.json | 2 100 | (ver manifiesto.json) | Manifiesto original, hashes, git_head |
| status.json | 9 727 | (ver hashes_fuentes.json) | Estado final del proceso |
| pilot.log | 478 | (ver hashes_fuentes.json) | Stdout al terminar (código de salida 0) |
| comando.txt | 687 | (ver hashes_fuentes.json) | Comando guardado (contiene --budget-only; NO es el comando ejecutado) |
| presupuesto.json | 4 712 | (ver hashes_fuentes.json) | Presupuesto pre-captura (--budget-only) |
| research.db | 2 113 536 | — | SQLite (fuera de Git, no se modifica) |

## 3. Resumen de resultados

| Métrica | Valor |
|---------|-------|
| Ciclos | 12 |
| Evaluaciones | 12 |
| Observaciones | 216 (168 aptas, 48 descartadas) |
| Resultados | 504 (168 × 3 horizontes) |
| Pendientes | 0 |
| Motivos descarte | dato_obsoleto_flujo: 47, dato_obsoleto_libro: 4, flujo_ventana_incompleta: 1 (suma 52, solapamiento) |
| HTTP attempts | 641 / 2 000 |
| HTTP weight | 1 109 / 5 000 |
| HTTP retries | 0 / 50 |
| WS conexiones totales | 20 (acumulado; pico simultáneo 2) |
| WS mensajes | 960 114 / 5 000 000 |
| WS reconnects | 0 / 20 |
| Almacenamiento | 5 225 620 / 134 217 728 bytes (3.9 %) |
| Fechas futuras (observaciones) | 0 |
| Código de salida | 0 |

## 4. Tiempos (reconciliados)

| Momento | Valor | Tipo |
|---------|-------|------|
| Inicio real | 2026-11-06T05:17:36.629Z | Medido (started_ms) |
| Fin de captura | 2026-11-06T06:17:36.629Z | Calculado (started_ms + 3600 s) |
| Fin de settle (fin del proceso) | 2026-11-06T07:14:10.655Z | Medido (ended_ms) |
| Límite nominal capture + settle | 2026-11-06T07:27:36.629Z | Calculado (no alcanzado) |

El settle terminó temprano (07:14:10.655Z vs límite 07:27:36.629Z) porque no quedaban resultados pendientes (n_pendientes = 0).

## 6. Veredicto por criterio

| Criterio | Veredicto |
|----------|-----------|
| 12 ciclos / 12 evaluaciones | ACREDITADO |
| 216 observaciones | ACREDITADO |
| 168 aptas, 48 descartadas con motivo explícito | ACREDITADO |
| 504 resultados, 0 pendientes | ACREDITADO |
| 0 duplicados | ACREDITADO |
| Padre-hijo válido (504/504) | ACREDITADO |
| 0 fechas futuras en observaciones | ACREDITADO |
| Límites HTTP/WS/almacenamiento respetados | ACREDITADO |
| 0 conexiones públicas adicionales, 0 órdenes, 0 claves privadas | ACREDITADO |

## 7. Limitaciones declaradas

- "0 fechas futuras" se verificó únicamente en las observaciones publicadas (disponibilidad <= decision_ms). Los mensajes WS crudos no se persisten.
- ws_connections_total = 20 es acumulado, no simultáneo; el pico simultáneo es 2 (1 /public + 1 /market).
- El neto de retornos es UNKNOWN (sin supuestos de costes/ejecución). No se declara ventaja ni rentabilidad.
- No se repitió la captura; no se modificó el dataset original, SQLite, ni DBs canónicas.

## 8. Archivos publicados en Git

- docs/evidence/coordinacion-recepcion-20261106/traza_captura_publica_20261106.md (traza narrativa, versión vigente)
- docs/evidence/coordinacion-recepcion-20261106/ (evidencias previas: antes_fix, aceptación, trazado de corte, etc.)
- docs/DECISIONS.md, docs/CURRENT_STATE.md, docs/TASK_QUEUE.md, docs/RESEARCH_UNIVERSE_LIQUIDITY_V1.md (actualizados)

Dataset completo, SQLite y logs permanecen fuera de Git (C:\proyectos\binance-futures-data\public-pilot-1h-20261106a). Solo se publican manifiesto, hashes y muestra pequeña.
