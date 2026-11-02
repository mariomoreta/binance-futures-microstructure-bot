# Ventana pública única — veredicto y evidencia (2026-11-02)

## Veredicto global

**FAIL** — la ventana no acredita el objetivo. Se ejecutó una sola corrida
autorizada; **no hubo relanzamiento**. El arnés etiqueta `ERROR` porque la
excepción abortó antes de `_verdict()`; la clasificación correcta es **FAIL
determinista de contrato**, no `ERROR` de Binance ni `UNKNOWN` de consumo.

Causa raíz (acreditada por el rechazo del propio servicio): el arnés incluyó
en el contexto la **vela en curso (no cerrada)** del minuto actual. El
servicio de ingeniería la rechazó correctamente con
`VALIDATION_ERROR: CONTEXTO_FUTURO` y no creó sesión.

```
RuntimeError: CREATE_SESSION_FAILED: status=400
{"error": "VALIDATION_ERROR: CONTEXTO_FUTURO: BTCUSDT vela open_time
1793642700000 cierra en 1793642759999, posterior a la referencia
1793642709475; el cierre todavía no ocurrió (no se fija T desde un cierre
no acreditado)"}
```

Defecto localizado: `scripts/engineering_live_window.py`, método
`_load_recent_context` (rama `public`, líneas 952–976): añade toda fila REST
con `close_time` presente, **sin excluir** la que aún no ha cerrado en la
referencia. El texto del check `contexto_cargado` ("velas cerradas") no se
corresponde con lo enviado (598 velas, la última abierta).

## Identidad de la corrida

| Dato | Valor |
|---|---|
| Rama | `diag/recorrido-local-4f4273c` |
| HEAD | `d2ca1cbe197cd973164a701c850cea3a6e2113d0` |
| run_id | `eng-run-public-20261102b` |
| Arnés | `scripts/engineering_live_window.py` |
| SHA-256 arnés | `32429af0ec82da0e717a98793c2c8d31eb2b22428998be6f3ff7e246edc6b4e5` |
| Blob git arnés | `f49df5b527dcbc96e327a6a7d8d9fec824b143a6` |
| Servicio mercado | `scripts/market_stream_service.py` (SHA-256 `8bb45876…186a47`) |
| Servicio ingeniería | `scripts/engineering_session_service.py` (SHA-256 `1037daa0…6bd74666`) |
| Árbol frontend | `1f6f0500cb9115fa5c9d44e07be2c5524bdee690` (`git rev-parse HEAD:frontend`) |
| BUILD_ID servido | `t4z0bfKQ_kIP9qv1WHCKR` (idéntico a `frontend/.next/BUILD_ID`, presente en `/market-lab`) |
| Dashboard | `http://127.0.0.1:3020` — 200, no modificado |
| DBs canónicas | `historical.db` y `microprobe.db` con SHA-256 idéntico antes/después |

Nota de exactitud: el check `build_served` imprime un literal histórico
("árbol e2243c9") en su detalle; **no** es el árbol servido. El árbol real
del frontend es `1f6f0500cb9115fa5c9d44e07be2c5524bdee690` y el BUILD_ID
verificado es `t4z0bfKQ_kIP9qv1WHCKR`. Esta corrida no cambió el dashboard:
solo se modificó documentación y evidencia.

## Comando exacto ejecutado

```powershell
python scripts/engineering_live_window.py \
  --transport public --execute \
  --clock-source public \
  --service-port 8791 --engineering-port 8797 \
  --symbols MINAUSDT,BTCUSDT --interval 1m --bars 300 \
  --duration 180 --deadline 180 \
  --run-id eng-run-public-20261102b \
  --sessions-dir data/engineering-session/live-window-20261102b \
  --evidence-dir docs/evidence/engineering-live-public-20261102b/service_logs \
  --dashboard http://127.0.0.1:3020 \
  --build-id t4z0bfKQ_kIP9qv1WHCKR \
  --out docs/evidence/engineering-live-public-20261102b/evidence.json
```

Preflight sin conexión: `preflight.json`. Logs persistentes desde el
lanzamiento: `harness-stdout.log`, `harness-stderr.log` y
`service_logs/{service,engineering}-{stdout,stderr}.log`.

## Cronología (ms epoch)

| Hecho | ms | Detalle |
|---|---|---|
| Servicio de mercado arriba | 1793642701917 | `--transport public`, 1 WS combinada |
| `/health` de ingeniería disponible | 1793642702548 | HTTP OK, `available=false` |
| Reloj público listo | 1793642708722 | `source=public_sincronizado`, 5/5 muestras, `offset_ms=-60.398438`, `rtt_ms=368.107` |
| Contexto REST | 1793642708… | BTCUSDT 353 ms; MINAUSDT 373 ms; `retry=0`, sin paginación |
| `POST /sessions` rechazado | ~1793642709… | T de referencia 1793642709475 |
| Evidencia escrita | 1793642709561 | ventana agotada en ~7,6 s de 180 s |

La preparación **no** consumió el deadline: el fallo ocurrió a los ~7,6 s.
El límite de preparación del reloj (60 s) tampoco se alcanzó: el reloj tardó
6,17 s desde que HTTP respondió.

## Criterios de aceptación

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | `session_id`, `config_hash`, regla e identidad | **NO ACREDITADO** | `create` 400; `session_id=null`, `config_hash=null`; `drives=[]` |
| 2 | Referencia temporal válida | **ACREDITADO** | `public_sincronizado`, `available=true`, 5/5 muestras, offset −60.40 ms |
| 3 | Contexto cerrado y no futuro | **NO ACREDITADO (rechazado)** | 598 velas; última `open_time=1793642700000` cierra en `1793642759999` > T `1793642709475` |
| 4 | ≥1 cierre NUEVO admitido por la sesión | **NO ACREDITADO** | sin sesión; conducción nunca iniciada |
| 5 | T anterior/nuevo, evento disparador, contador | **NO ACREDITADO** | sin evaluaciones |
| 6 | Decisión ejecutada con motivo | **NO ACREDITADO** | sin evaluaciones (no hay `SIN_ENTRADA` ni otra decisión) |
| 7 | Presupuestos comprobados con ledger | **ACREDITADO** | 7/7 intentos, 0 bloqueos pre-envío (ver abajo) |
| 8 | Limpieza y DBs canónicas intactas | **ACREDITADO** | procesos terminados, puertos cerrados, SHA-256 de DBs idéntico |

## Consumo real y contadores de alcance

Ledger compartido (`data/market-cache/market_cache.db`, `execution_id =
eng-run-public-20261102b`): **7 filas, `requests=7`, todas `ok`**, 0 filas
`budget_blocked`. Detalle en `ledger-run-id.json`.

- `/time` (`fapi_time`): 5 intentos (5/5 muestras válidas).
- `klines`: 2 intentos — `BTCUSDT` y `MINAUSDT`, `limit=300`, rango exacto
  `1793624768722..1793642708722` (300 min), `retry=0`, sin paginación ni
  descarga de días intermedios.
- Catálogo/`exchangeInfo`: 0 intentos.
- Recuperación REST: desactivada (`--no-recovery`).
- Conexión WS: 1 combinada configurada (el hub la abre al arrancar);
  **estado de conexión durante la ventana = UNKNOWN** (no se muestreó
  `/health` del servicio tras el fallo).
- Consumidores SSE: 0 (la conducción nunca se inició; no se creó consumidor).
- Reconexiones: **UNKNOWN** (no hubo bucle de monitorización que las contara).
- Velas por petición: 300 (techo respetado).

El techo de 7 intentos quedó **agotado por la preparación**: 5 de reloj + 2
de contexto. Con el presupuesto consumido, cualquier reintento habría sido
bloqueado antes de enviar (mecanismo verificado en el ledger).

## Alcance no ejercitado

El recorrido se detuvo antes de crear la sesión, por lo que **no** se
ejercitó `WS → SSE → adaptador → evaluación` dentro de la sesión: no hubo
consumidor SSE, ni cierres admitidos, ni evaluaciones, ni decisiones. No se
abrió posición; no hay P&L, comisión ni realizado que reportar.

## Estado final

- Procesos propios terminados: ingeniería y mercado (`limpieza_resultado`),
  archivos de log cerrados.
- Puertos: 8791 y 8797 **cerrados**; 3020 y 8792 **abiertos y no tocados**.
- Sesiones de ensayo: ninguna. `data/engineering-session/live-window-20261102b/`
  solo contiene `run-id.json` y `service.json`; no hay sesión creada.
- Dashboard: 3020 sigue sirviendo `BUILD_ID t4z0bfKQ_kIP9qv1WHCKR`, sin
  ensayos activos.
- DBs canónicas: sin escrituras (SHA-256 idéntico a `preflight.json`).

### Efecto colateral en estado compartido y restauración

El servicio de mercado del arnés (8791) escribe el pid-file por defecto
`data/market-stream/service.json`, compartido con el servicio preexistente
8792. La corrida lo sobrescribió con `pid=31708, port=8791` (proceso ya
terminado). Se restauró con los valores que el propio 8792 reporta en
`/health` (`pid=31124`, `port=8792`, `started_at_ms=1793276434054`, host
`127.0.0.1`), sin reiniciar ni tocar el proceso 8792. El contenido previo
exacto del archivo es **UNKNOWN** (el preflight no lo capturó). Tras la
restauración, 8792 sigue respondiendo 200 en `/health` y 3020 sigue
sirviendo el mismo BUILD_ID.

## Siguiente acción requerida (no ejecutada aquí)

1. Corregir `_load_recent_context` para **excluir toda vela con
   `close_time_ms` posterior a la referencia** (la vela en curso nunca debe
   entrar en el contexto), y añadir una prueba local que lo fije.
2. Solicitar **nueva autorización** para otra ventana pública con un
   `run_id` nuevo: el presupuesto de este `run_id` está agotado (7/7).
3. No relanzar esta corrida ni reutilizar su `run_id` para recuperar cupos.
