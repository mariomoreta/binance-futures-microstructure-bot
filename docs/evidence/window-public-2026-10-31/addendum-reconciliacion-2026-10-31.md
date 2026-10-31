# Addendum: reconciliación de resultado y presupuesto REST — ventana pública 2026-10-31

Base: commit `e2243c9` (HEAD). Ejecución: `docs/evidence/window-public-2026-10-31/run-1/`.
Este addendum **no modifica los originales** (`run.json`, `network.json`, `local.json`, `summary.json`); solo los interpreta y añade el recálculo offline conservado.

## 1. Resultado global reconciliado

| Dimensión | Veredicto | Motivo |
|-----------|-----------|--------|
| Gráfico / transporte (cadena Binance → hub → servicio SSE → BFF → DOM) | **PASS** | 21/21 checks OK (7/7 DOM): `dom_identity`, `dom_state_live`, `dom_update_fresh`, `dom_candles_grew` (299→600), `dom_pagination_preserved`, `dom_no_reload`, `dom_after_stop`. `acquisition_finished=true`, `stop_reason=ACCEPTANCE_REACHED`. |
| Consumidores SSE simultáneos | **INCUMPLIMIENTO** | Máximo autorizado: **3**. Pico medido en `health_before_close`: **4** (`service=1, bff=1, browser=1, internal_benchmark=1`). El `internal_benchmark` (suscripción interna compartida BTC) se contabilizaba como consumidor adicional, llevando el pico a 4. |
| **Veredicto GLOBAL** | **NO PASS** | El incumplimiento de consumidores (4 > 3) impide que el global sea PASS, aunque la cadena de datos del gráfico/transporte sea funcional. |

El `internal_benchmark` era un doble conteo: la suscripción al benchmark BTCUSDT es **compartida** (refcount) sobre el mismo stream del símbolo BTC, no un consumidor SSE adicional del usuario. Se corrigió en `scripts/market_stream_window.py::_consumer_allocation`: el total declarado pasó de 4 a 3 (`service + bff + browser`; `internal_benchmark` queda solo como campo informativo). Con `--browser-consumer`, `sse_consumers.total = 3`.

## 2. Presupuesto REST — recálculo offline desde ledger conservado

**Regla:** no se equiparan llamadas del navegador al BFF con solicitudes a Binance. El recuento upstream se hace sobre el ledger de caché (`data/market-cache/market_fetch_ledger`), que registra cada intento HTTP con su endpoint real.

Filas del ledger dentro de la ventana (id 140–143, `at_ms` entre 1793455749 y 1793455872):

| id | `at_ms` | symbol | interval | endpoint | requests | ≤300 velas |
|----|---------|--------|----------|----------|----------|------------|
| 140 | 1793455749677 | — | — | `fapi/v1/exchangeInfo` (catálogo) | 1 | n/a (no es vela) |
| 141 | 1793455803479 | BTCUSDT | 1h | `fapi/v1/klines` | 1 | sí (300) |
| 142 | 1793455804637 | BTCUSDT | 1m | `fapi/v1/klines` | 1 | sí (299) |
| 143 | 1793455864464 | BTCUSDT | 1m | `fapi/v1/klines` | 1 | sí (300) |

**Recuento upstream a Binance (ledger, no llamadas al BFF):**
- Intentos REST totales a Binance: **4** (1 exchangeInfo + 3 klines).
- Solicitudes de velas a Binance: **3**, cada una ≤ 300 velas.
- Presupuesto autorizado del usuario: **máximo 4 intentos REST totales para toda la ejecución; máximo 300 velas cada uno**.
- **REST dentro del presupuesto autorizado: sí** (4 totales ≤ 4; 3 velas ≤ 300 c/u).

**Nota sobre el NameError del arnés:** `scripts/market_stream_local_acceptance.py` falló al construir el resumen final por `NameError: name 'rest_market_requests' is not defined` (variable ajena a la cadena de datos). Por eso `local.json` reporta `verdict=ERROR`/`rest_market_budget=null`, mientras que el veredicto autoritativo del finalizer en `run.json` es `PASS`. El NameError se corrigió: `rest_market_requests` ahora se define (0 en modo local sin Binance; None en modo public si no hay ledger, → presupuesto UNKNOWN) y `rest_market_budget` se evalúa contra el presupuesto autorizado (≤ 4 intentos), no contra las llamadas al BFF.

**`upstream_binance_requests` del arnés:** queda `None` en modo public cuando no hay registros del servicio Python (no se asume cero; es UNKNOWN, nunca se equipara con llamadas al BFF). En este addendum se sustituye por el recuento real del ledger (4).

## 3. Alcance realmente probado — sesión de ingeniería

Los checks del arnés de ventana **no acreditan la sesión de ingeniería** (no hay `session_id`, `config_hash`, runner, eventos recibidos, revisiones ni decisiones bajo mercado real en esta ventana).

**Sesión de ingeniería: NO EVALUADA.**
- No existe evidencia de una sesión de ingeniería que reciba eventos y registre decisiones bajo mercado real en la ventana 2026-10-31 (`paper-lab-sessions/` no contiene archivos de fecha 179345...; los más nuevos son ~2 días anteriores; la evidencia de ingeniería en `docs/evidence/engineering-*` es del 2026-10-28 con transporte local, sin Binance real).
- La ausencia de posiciones abiertas **no** se presenta como abstención demostrada (cero entradas es válido solo si queda acreditada la evaluación, cosa que no ocurrió bajo mercado real en esta ventana).

Se agregó una prueba focalizada `tests/test_engineering_session_local_backend.py` que acredita, con transporte local (sin red, sin Binance): `session_id`, `config_hash`, runner (engine), decisión causal (`RULE-CAUSAL-V1`) registrada con motivo y evidencia, `revision` incrementada, recepción de eventos (`step_forward` avanza `clock_ms`/`cursor`), y cero entradas válido si queda acreditada la evaluación (`position.open=False` con decisión registrada).

## 4. Cambios al arnés (transporte local, demostrado)

1. `scripts/market_stream_window.py::_consumer_allocation`: elimina el doble conteo del consumidor benchmark del total declarado (pico 4 → 3; máximo autorizado 3).
2. `scripts/market_stream_local_acceptance.py`: corrige `NameError` (`rest_market_requests` indefinida); `rest_market_budget` se evalúa contra el presupuesto autorizado (≤ 4 intentos REST a Binance), no contra llamadas al BFF; `upstream_binance_requests` nunca se asume cero sin ledger (UNKNOWN si no hay registros).
3. Prueba focalizada `tests/test_engineering_session_local_backend.py`: sesión backend que recibe eventos y registra decisiones con transporte local.

## 5. Estado final

- Servicio 8791 detenido, puerto libre; 8792 sin tocar (servicio local preexistente PID 31124); dashboard 3020 disponible en `e2243c9` (BUILD_ID `t4z0bfKQ_kIP9qv1WHCKR`), sin sesión de ensayo activa.
- Sin posiciones paper abiertas (no hubo entrada bajo mercado real en esta ventana); sin órdenes, claves privadas, pagos, móvil ni optimización.
- DBs canónicas intactas (`microprobe.db`, `historical.db` sin cambios); caché derivada aislada.

## 6. Qué falta

- Sesión de ingeniería bajo mercado real: NO EVALUADA (pendiente de ventana autorizada con transporte public y evidencia de `session_id`/`config_hash`/decisión bajo Binance real).
- Repetición de la ventana pública con el arnés corregido (consumidores ≤ 3) para pasar el veredicto global: requiere autorización explícita.
