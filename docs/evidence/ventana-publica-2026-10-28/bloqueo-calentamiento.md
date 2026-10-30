# Evidencia: Ventana pública de integración — ABORTADA antes de conectar a Binance

**Fecha:** 2026-10-29 (UTC)
**SHA fuente (HEAD):** f43346900bdf343b0fd8c3b5b266f0696faf644e
**BUILD_ID servido:** wF9Xf3Orb5Af7vgwp8_f4
**Rama:** feat/ingenieria-autonoma

## Decisión: ABORTAR antes de conectar a Binance

La ventana pública de integración no se ejecutó. Antes de conectar, se verificó
que los pre-requisitos de continuidad y calentamiento no se cumplen dentro del
presupuesto autorizado. Por decisión documentada, **no se abrió conexión WS
pública a Binance** y no se consumió ningún intento REST upstream.

## Verificaciones previas a conectar (todas realizadas)

| Verificación | Resultado | Detalle |
|--------------|-----------|---------|
| SHA fuente | `f43346900bdf343b0fd8c3b5b266f0696faf644e` | Commit `f433469` en `feat/ingenieria-autonoma` |
| BUILD_ID servido | `wF9Xf3Orb5Af7vgwp8_f4` | `frontend/.next/BUILD_ID` |
| Dashboard 3020 | UP | `GET /api/v1/engineering-sessions/demo` ok, `demo.active=False`, `eng.state=down` |
| 8792 (servicio ajeno) | UP, PID 31124 | `python scripts/market_stream_service.py --port 8792 --transport local --base-url ws://127.0.0.1:9999`. **No tocado.** |
| 8791 (servicio de mercado) | DOWN | No hay servicio de mercado levantado |
| 8797 (servicio de sesiones) | DOWN | No hay sesiones activas |
| Sesiones activas | Ninguna | 8797 DOWN → no hay sesiones de ingeniería activas |
| Navegador Playwright | OK | `http://127.0.0.1:3020/market-lab` cargado, título "Binance Futures — Research Dashboard" |
| opencode.json | No modificado | Preservado sin cambios |

## Cobertura de caché (calentamiento) — FALLA

Se consultó el caché local con `series_payload(cache=..., client=None, allow_fetch=False)` (0 peticiones upstream):

| Símbolo | Última vela cerrada (close_time_ms) | `from_ms` esperado (last_ctx_close + 1) | ¿Cobertura continua hasta `from_ms`? | Rango ausente a partir de `from_ms` |
|---------|-------------------------------------|-----------------------------------------|--------------------------------------|-------------------------------------|
| MINAUSDT 1m | 1793072999999 | 1793073000000 | **NO** | `[1793073000000, 1793325746131]` |
| BTCUSDT 1m | 1793060219999 | 1793060220000 | **NO** | `[1793060220000, 1793325746131]` |

Ambos símbolos terminan en caché días antes del presente. El `from_ms` (primera frontera de operación) cae en un rango ausente para ambos símbolos.

## Presupuesto autorizado vs. realidad del caché

| Recurso | Límite autorizado | Disponible en caché | ¿Suficiente? |
|---------|-------------------|---------------------|--------------|
| Velas MINAUSDT continuas hasta `from_ms` | — | Última: 1793072999999 | **NO** — hueco desde 1793073000000 |
| Velas BTCUSDT continuas hasta `from_ms` | — | Última: 1793060219999 | **NO** — hueco desde 1793060220000 |
| Intentos REST upstream totales | ≤ 4 | 0 (no se consumió ninguno) | N/A — no se conectó |
| Páginas de preparación | ≤ 2 (incluidas en los 4) | 0 | N/A |
| Velas por petición REST | ≤ 300 | N/A | N/A |
| Tiempo global | ≤ 180 s | 0 s (no se inició) | N/A |

La adquisición inicial acotada (máx. 2 páginas × 300 velas = 600 velas) no puede cubrir el hueco de ~6200 velas (≈4.3 días) para MINAUSDT ni el hueco de BTCUSDT. Con solo 4 intentos REST en total, no es posible establecer continuidad.

## Límites en código verificados (antes de conectar)

| Recurso | En código | Estado |
|---------|-----------|--------|
| Conexiones WS simultáneas | 1 (único `BinanceKlineTransport`) | ✓ |
| Streams | `MAX_SUBSCRIPTIONS = 6` | ✓ (2 ≤ 6) |
| Consumidores SSE simultáneos | `MAX_TOTAL_CONSUMERS = 12`, `MAX_CONSUMERS_PER_STREAM = 4` | ✓ (3 ≤ 12, 3 ≤ 4) |
| Tiempo global | `max_seconds` (se pasa `--max-seconds 180`) | ✓ |
| Cero escrituras DBs canónicas | `persistence: "MEMORY_ONLY"` | ✓ |
| Sin fallback público | `resolve_transport` falla cerrado | ✓ |
| Reconexiones ≤ 3 | Código tiene `RETRY_BUDGET = 20` | ⚠ Se monitorea manualmente |
| 300 velas/petición REST | Código tiene `RECOVERY_PAGE_LIMIT = 500` | ⚠ Se monitorea manualmente |
| 4 intentos REST totales | Sin contador global | ⚠ Se monitorea manualmente |

## Bloqueo

**Causa:** El caché local no tiene velas cerradas continuas desde `from_ms` (primera frontera de operación) para MINAUSDT ni para BTCUSDT. La adquisición inicial acotada (≤ 2 páginas REST, ≤ 300 velas/petición, ≤ 4 intentos totales) no puede cubrir el hueco de varios días de datos faltantes.

**Acción tomada:** No se conectó a Binance. No se consumió ningún intento REST upstream. No se abrió conexión WS pública. No se escribió en DBs canónicas.

**Estado final:** Dashboard 3020 UP, sin demo activa, 8792 intacto (PID 31124), 8791 DOWN, 8797 DOWN, sin conexión a Binance.

**Próximo paso (pendiente de autorización separada):** La ventana pública de integración requiere (a) cobertura de caché contigua hasta el presente o (b) autorización para una adquisición inicial REST mayor que cubra el hueco, y (c) nuevos límites de intentos REST si se requiere más de 4.
