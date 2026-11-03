# Resultado ventana pública `eng-run-public-20261102d`

Fecha: 2026-11-03 · Base: `d307fc7` (`diag/recorrido-local-4f4273c`) · Ventana única autorizada.

## Veredicto global: **PASS**

Cadena acreditada completa: sesión creada → cierre nuevo admitido POR la sesión → avance de T → evaluación vinculada con decisión y motivo → parada limpia.

## Acreditado por etapa

### 1. Identidad y referencia temporal (válidas)
- `create_ok: true`, `session_id=PL-MINAUSDT-LONG-1793674533011-ff05e947`, `config_hash=4a339c046cc3ad63`, regla `RULE-CAUSAL-V1`, símbolo MINAUSDT, referencia BTCUSDT, intervalo 1m, notional 1000 USDT.
- Clock público sincronizado: `source=public_sincronizado`, offset −17.06 ms, RTT 369 ms, 5/5 samples válidos, reloj listo en 1793674532215 (sin fallback local).

### 2. Cierres nuevos admitidos por la sesión: 3 (✓ ≥ 1)
Trazas con `open_time_ms` y `at_ms`:
- 1: open 1793674500000, admitido en 1793674561120 (watermark → 1793674500000)
- 2: open 1793674560000, admitido en 1793674621326 (watermark → 1793674560000)
- 3: open 1793674620000, admitido en 1793674680716 (watermark → 1793674620000)

`cierres_admitidos_final: 3`, `watermark_final: 1793674620000`, T avanzó de 1793674499999 → 1793674620000.

### 3. Evaluaciones ejecutadas y vinculadas: 2 (✓ ≥ 1)

| # | Evento disparador | T | config_hash | Decisión | Motivo |
|---|---|---|---|---|---|
| 1 | closed open 1793674500000, close 1793674559999, received 1793674560685 | 1793674500000 | 4a339c04… | SIN_ENTRADA | "Velas abiertas en T pero close todavía desconocido (última abierta @ 1793674500000): señal no confirmada, abstención." (abstención válida) |
| 2 | closed open 1793674560000, close 1793674619999, received 1793674620707 | 1793674560000 | 4a339c04… | ENTRADA_SIMULADA | "Señal de entrada en T pero sin fill posible en el prefijo conocido: run_backtest no admite operación con datos disponibles en T. Señal pendiente de fill." |

`evaluacion_contador_final: 2`, `evaluacion_vinculada` con evento/T/config_hash/rule_version/decisión/motivo; `config_hash` de la evaluación == `config_hash` de la sesión creada.

### 4. Adaptador de ingeniería (SSE)
- frames 97, bad_frames 0, unknown_frames 0, provisional_frames 34 (contados, nunca conducen)
- disconnects 3, reconnects 3, connect_errors 0 → los 3 cortes fueron de **fase LECTURA** (clasificados `READ_TIMEOUT`), no de conexión
- `last_disconnect_reason: READ_TIMEOUT`, `connected_at_ms: 1793674655721`, `last_frame_at_ms: 1793674696978`
- `events_processed_final: 95` (contador ya NO congelado en 0: corregido en d307fc7)

### 5. Recorrido del servicio de mercado (HUB)
- ws_connects 4, ws_messages_received 381, ws_klines_parsed 381
- ws_closed_by_symbol: BTCUSDT 3, MINAUSDT 3
- sse_frames_sent 381 (WS mensajes ≠ frames SSE; contados por alcance separado)
- consumidores máximos simultáneos: 2 (≤ 3 permitidos)

### 6. Límites y presupuesto (acreditados por ledger y contadores)
- rest_count: 2 / 7 HTTP upstream (dentro del presupuesto de 7)
- ledger_total_por_run_id: 7 (exactamente el tope, jamás excedido; run_id nuevo con 0 usos previos)
- Reconexiones acumuladas: 0 (≤ 3)
- Escrituras en historical.db / microprobe.db: 0 (hashes canónicas intactas: d8930ec5 / 6ea98cab)
- No hubo órdenes reales, claves privadas, pagos, móvil ni cambios económicos.
- Recuperación REST desactivada (conservada).

### 7. Limpieza efectiva
- Procesos propios terminados: ingeniería, mercado (ninguno falló)
- Logs cerrados: ingeniería_stdout/stderr, mercado_stdout/stderr (stderr vacíos)
- pid-files propios eliminados; puertos 8791 y 8797 libres post-run
- pid-file de 8792 (pid 31124) **no sobrescrito ni reconstruido**, intacto
- Dashboard 3020 disponible con entorno original, sin sesiones de ensayo activas
- `opencode.json` modificado y fuera de commits (preservado)

## Estado de la sesión al cierre

- `status: abierta` (conducción detenida por parada del arnés, no por fallo)
- `position.open: true`, dirección LONG, entry_px 0.05564, entry_cost 1000.0 USDT (paper-lab simulado, **sin orden real en Binance**), stop_px 0.052858, marca no realizada conservada
- `clock_ms: 1793674620000`, `revision: 10`, `cursor: 3`, `candles: 3`, `context_candles: 600`, `events: 3`
- Decisión final: `ENTRADA_SIMULADA` (señal pendiente de fill; **no se inventó salida, comisión ni realizado**)

## Evidencia
- `docs/evidence/engineering-live-public-20261102d/evidence.json` (traza completa del arnés)
- `docs/evidence/engineering-live-public-20261102d/harness-stdout.log` (stdout persistente desde el lanzamiento; UTF-16LE, sin stderr)
- `docs/evidence/engineering-live-public-20261102d/harness-stderr.log` (vacío)
- `docs/evidence/engineering-live-public-20261102d/service_logs/*` (servicio e ingeniería, stderr vacíos)
- `docs/evidence/engineering-live-public-20261102d/sessions/` (sesión persistida, run-id.json, drive-registry.json)
- `docs/evidence/engineering-live-public-20261102d/command.txt`, `preflight.json`

## SHA / BUILD_ID
- SHA-256 del arnés (`scripts/engineering_live_window.py`): `3ef9e5f45a90a8ca…`
- BUILD_ID servido en `/market-lab` del dashboard 3020: `t4z0bfKQ_kIP9qv1WHCKR` (literal presente en el HTML servido)
- Árbol frontend: `1f6f0500cb9115fa5c9d44e07be2c5524bdee690` (= HEAD:frontend)

## Nota de alcance
Este PASS acredita el recorrido de observación (obtener → entender → papel) para una sola ventana pública. No valida rentabilidad ni edge, y no autoriza ejecución con fondos reales. La sesión queda abierta y congelada por diseño; ninguna orden real fue enviada.
