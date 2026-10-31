# Addendum: bloqueo de la ventana pública de sesión de ingeniería — 2026-10-31

Base: commit `22987a4` (HEAD `e2243c9`). Ejecución: `docs/evidence/window-public-2026-10-31/run.json`.
Este addendum **no modifica los originales**; solo interpreta y registra la causa del bloqueo.

## Veredicto global: BLOQUEO (no PASS, no UNKNOWN significativo)

La ventana pública autorizada (una sola, `--transport public`, símbolos `BTCUSDT`+`MINAUSDT` 1m, deadline 180 s) **no se pudo completar**.

**Causa:** no se pudo obtener un contexto reciente de velas cerradas para fijar el reloj T inicial de la sesión de ingeniería. Sin contexto, `create_session` con transporte `market_stream` rechazó con:

```
VALIDATION_ERROR: LIVE_CONTEXT_REQUIRED: la sesión live necesita contexto
(ventana de velas cerradas conocidas) para fijar el reloj T inicial
```

Por lo tanto **no se creó la sesión de ingeniería**, no hubo eventos de mercado recibidos por la sesión, no hubo revisiones ni decisiones, y no hay evidencia de ejecución que verificar. Cero entradas (válido solo si se acredita evaluación real — aquí no se acreditó).

## Qué se verificó (preflight, antes del bloqueo)

| Condición | Resultado |
|-----------|-----------|
| SHA fuente | `22987a4` (HEAD `e2243c9`, solicitado) |
| BUILD_ID servido | `t4z0bfKQ_kIP9qv1WHCKR` = árbol `e2243c9`, `/market-lab` HTTP 200 |
| Puerto 8791 | libre antes de arrancar el servicio |
| Puerto 8792 | ocupado (servicio LOCAL preexistente PID 31124, **no tocado**) |
| Puerto 3020 | dashboard disponible |
| Sesiones de ingeniería activas | ninguna antes de la ventana |
| Límites en código | hub usa 1 WS combinada; servicio MAX_BARS=1000, bars default 300; `--no-recovery` desactiva recuperación REST; el orquestador impone ≤3 consumidores SSE, ≤3 reconexiones, ≤4 REST, ≤300 velas/consulta, deadline 180 s |
| Dashboard sin sesión de ensayo | sí |

## Presupuesto REST (recalculado offline)

| Métrica | Valor | Límite autorizado | ¿Cumple? |
|---------|-------|-------------------|----------|
| Intentos REST totales a Binance | 2 (klines BTCUSDT + klines MINAUSDT) | 4 totales | sí |
| Velas por consulta klines | ≤300 cada una | 300 | sí |
| Peticiones del navegador al BFF | n/a (no hay navegador en esta ventana) | — | — |
| Escrituras en DBs canónicas | ninguna | cero | sí (`db_unchanged=true`) |

Ambas peticiones REST klines devolvieron **HTTP 200 pero 0 velas válidas** (cuerpo no parseable como lista de klines), por lo que el contexto quedó en 0 velas. La caché derivada local tampoco tenía velas recientes para el rango. Sin contexto reciente, no se puede fijar el reloj T.

## Consumidores SSE y WS

* El servicio de market-stream en 8791 (`--transport public --no-recovery`) estableció **una** conexión WS combinada a Binance (BTCUSDT+MINAUSDT 1m).
* La sesión de ingeniería **no se creó**, por lo que no se abrió consumidor SSE de ingeniería.
* Consumidores SSE máximos observados: 0 (sesión no creada). Límite 3 respetado (vacuamente).
* Reconexiones WS: el servicio de market-stream se conectó a Binance; al no poder crear la sesión, el orquestador detuvo los servicios. No se excedió el límite de 3 reconexiones (no hubo reconexiones acumuladas significativas reportadas).

## Recursos y limpieza

* Servicios propios (market-stream 8791, engineering-session 8797) detenidos tras la ejecución; puertos en TIME_WAIT, sin proceso activo.
* 8792 (servicio local preexistente PID 31124) **no tocado**.
* Dashboard 3020 disponible, sirviendo `e2243c9` (BUILD_ID `t4z0bfKQ_kIP9qv1WHCKR`), sin sesión de ensayo activa.
* DBs canónicas (`microprobe.db`, `historical.db`): **intactas**, sin escritura. Caché derivada aislada (lectura; 0 velas útiles).
* Sesión de ingeniería: **no creada** (no hay `session_id` ni `config_hash`).

## Qué falta / por qué no se repite

La causa raíz es que **no hay contexto reciente de velas cerradas disponible** para ninguna de las dos fuentes permitidas (caché derivada local ni REST klines a Binance en este entorno). Sin contexto, la sesión de ingeniería live no puede crearse (regla `LIVE_CONTEXT_REQUIRED`, causalidad: el reloj T debe fijarse sobre velas conocidas).

El usuario instruyó: **no repetir la ventana ante fallo, entregar la causa**. Por tanto esta ventana queda cerrada con veredicto BLOQUEO y causa documentada. Una futura ventana requeriría resolver primero la disponibilidad de contexto reciente (caché o REST klines con velas válidas) antes de conectar a Binance.

## Evidencia

* `docs/evidence/window-public-2026-10-31/run.json` — ejecución completa (veredicto ERROR, causa LIVE_CONTEXT_REQUIRED, 2 REST klines, 0 velas, DBs intactas, servicios detenidos).
* `docs/CURRENT_STATE.md` — sección de cierre y bloqueo (esta sesión).

Sin órdenes reales, claves privadas, pagos, móvil ni optimización. Sin cambios durante la ventana.
