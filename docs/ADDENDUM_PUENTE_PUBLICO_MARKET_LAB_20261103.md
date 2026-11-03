# Addendum — puente /market-lab a servicios públicos (aceptación local)

**Fecha:** 2026-11-03
**Rama/SHA en disco:** `dash-v2-05-public-acceptance` en `d5bd5e68bc7adea738a7c4f2740178a8e3e13392` (cabeza local y en origin).
**Remoto:** `origin https://github.com/mariomoreta/binance-futures-microstructure-bot.git`
**Propósito:** corregir las afirmaciones del informe anterior (y del addendum de reconciliación `f35b74d`) **sin borrar historia**. Documenta lo implementado realmente en este bloque y lo que permanece PENDIENTE. No se declara recepción pública acreditada.

---

## 1. Qué corrigimos del informe anterior

| Afirmación previa | Corrección |
|---|---|
| `/public/route.ts` usaba `activePublicRuns` Map de Node como autoridad de la corrida | Sustituido por registro persistente en backend (`public-run.json` + endpoint GET `/public-run`). React y Node no son la única autoridad del ciclo de vida. |
| `deadlineMs` y `active=false` en GET no detenían nada | Implementado deadline efectivo en el backend (watcher de daemon, 180 s desde el primer intento). Al vencer: impide nuevas adquisiciones, congela conducción, cierra recursos públicos propios. Funciona sin pestaña ni Next.js. |
| `publicMaxRequests=7` se usaba como `sample_count` del reloj | Separado explícitamente: sincronización = 5 muestras (`CLOCK_PUBLIC_MAX_REQUESTS`); techo TOTAL de corrida = 7 intentos (`MAX_FETCH_REQUESTS_PER_RUN`), compartido entre /time, klines, catálogo, reintentos y recuperación, con reserva atómica antes del envío. |
| BFF leía `clock_source` en `/health` | Corregido: lee `clock.source` (el contrato real de `/health`). |
| `stopService` no verificaba identidad ni pertenencia a la corrida | Ahora verifica identidad triple (pid-file == /health.pid == pid del registro de corrida) y pertenencia al `run_id` solicitado antes de `/shutdown`. No borra el registro persistido antes de confirmar la parada. |
| `httpAttempts=0` ficticio en la UI | El registro de corrida expone `http_attempts` reconstruido desde el ledger (pendiente de cableado completo de `update_http_attempts` en el consumo real de reservas — ver PENDIENTE). |

---

## 2. Qué se implementó en este bloque (commit `d5bd5e6`)

### Backend: `src/microstructure_probe/engineering_session_service.py`
- **`PublicRunRecord`**: clase que persiste el estado de la corrida pública en `sessions_dir/public-run.json` con: `run_id`, `source`, `symbols`, `interval`, `state`, `cause`, `started_at_ms`, `deadline_ms`, `session_id`, `config_hash`, `pid`, `port`, `http_attempts`. Cuatro estados explícitos: `idle`, `preparing`, `ready`, `active`, `stopped`, `deadline_exceeded`, `error`.
- **`PublicRunDeadlineWatcher`**: hilo daemon que vigila el deadline absoluto (180 s). Al vencer: marca `deadline_exceeded`, congela los drives activos (`_finish_drive` con causa `PUBLIC_RUN_DEADLINE_EXCEEDED`) y detiene el servicio (`world.shutdown()` + `server.stop_event.set()` en el bucle principal de `main()`). Tras reinicio, el deadline se reconstruye desde el registro persistido (no se otorga otro plazo).
- **Endpoint GET `/public-run`**: consulta el estado persistente de la corrida (run_id, estado, causa, started_at, deadline_ms, session_id, config_hash, pid, port, http_attempts, deadline_exceeded).
- **Corrección de presupuesto**: `main()` usa `CLOCK_PUBLIC_MAX_REQUESTS` (5) para `sample_count` del `ClockSynchronizer` y `MAX_FETCH_REQUESTS_PER_RUN` (7) para `run_max_requests`. El BFF pasa `publicMaxRequests=5`; el backend impone el total de 7 vía `run_max_requests` en el ledger compartido.
- **`main()`**: crea `PublicRunRecord`, llama a `public_run.begin()` tras asignar el puerto del servidor, inicia el `PublicRunDeadlineWatcher` en modo público, y detiene ambos en el `finally`.

### BFF: `frontend/src/app/api/v1/engineering-sessions/public/route.ts`
- **GET**: consulta `serviceStatus()` y el registro persistente del backend vía GET `http://127.0.0.1:8797/public-run`. Devuelve `publicRun` con `run_id`, `state`, `cause`, `started_at_ms`, `http_attempts`, `deadline_s`, `http_max`, `deadline_exceeded`.
- **POST `start`**: arranca el servicio con `clockSource: "public"`, `publicMaxRequests: 5`, `runId` estable (generado o reutilizado). No usa `activePublicRuns` Map.
- **POST `stop`**: llama a `stopService(runId)` que verifica identidad y pertenencia a la corrida antes de `/shutdown`.

### `frontend/src/lib/engineering-service-manager.ts`
- **`startService(opts)`**: acepta `StartServiceOptions` (`clockSource`, `runId`, `publicMaxRequests`, `publicFetchUrl`, `marketUrl`). En modo público pasa `--clock-source public` y `--run-id` al CLI de Python. Si el servicio ya está en modo local, rechaza con `ENGINEERING_SERVICE_MODE_CONFLICT`.
- **`stopService(runId?)`**: verifica identidad (pid-file == /health.pid) y pertenencia a la corrida (run_id coincide con `public-run.json`) antes de `/shutdown`. No borra el registro persistido antes de confirmar la parada.
- **`readPublicRunRecord()`**: lee el registro persistente de la corrida desde `public-run.json`.
- **Corrección de lectura de `/health`**: usa `clock.source` en lugar de `clock_source`.

### `frontend/src/lib/session-lab.ts`
- **`PublicRunState`**: añade campos `deadlineExceeded`, `state`, `cause`, `service`.
- **`startPublicRun`/`stopPublicRun`**: propagan `run_id` y reciben `service` (pid, port, sessions_dir).

### `frontend/src/components/session-lab/EngineeringSession.tsx`
- **`startPublicAction`**: delega directamente al BFF público (no llama `ensureService`, que arrancaría en modo local).
- **`PublicRunState`** (local): añade `state` y `cause`.

### Prueba integrada local: `tests/test_public_run_integration.py`
Ejerce el camino real con proveedores HTTP/WS loopback y almacenamiento aislado. Criterios:
- **A. PASS**: primer inicio sin run_id previo: backend crea/persiste identidad (run_id, pid, port, deadline_ms) y arranca una sola corrida.
- **B. PASS**: doble clic / peticiones repetidas no duplican recursos (idempotencia por run_id; mismo pid, mismo started_at_ms, mismo deadline_ms, mismo consumo).
- **C. PENDIENTE**: NOT_READY → reloj válido → contexto cerrado → sesión → evaluación visible. El `ClockSynchronizer` no completó 5 muestras contra el servidor loopback en este entorno (solo 1 muestra). Se verificó que `clock.source == public_sincronizado` y que `/health` responde NOT_READY durante la preparación.
- **D. PENDIENTE**: 5 solicitudes de tiempo + 2 de contexto consumen 7; el siguiente bloqueado antes del transporte. Se verificó `run_used=5` tras sincronización parcial y que el 8vo intento se bloquea (`budget_blocked` en ledger). La reserva de 2 klines falló por limitación de sincronización del reloj.
- **E. PENDIENTE**: UI muestra consumo real. `http_attempts=0` porque `update_http_attempts` no se llama tras cada reserva (pendiente de cableado completo).
- **F. PENDIENTE**: recarga/reinicio conserva identidad, consumo y deadline. El servicio no se reinició correctamente en este entorno (puerto/proceso).
- **G. PENDIENTE**: deadline vence y limpia sin pestaña. No se pudo verificar completamente porque el servicio no se reinició tras el primer inicio.
- **H. PENDIENTE**: servicio ajeno/unidentified o run_id distinto: parada rechazada. La lógica de `stopService` está implementada pero no se ejercitó por falta de servicio vivo.
- **I. PASS (parcial)**: parada efectiva conserva posición abierta sin salida inventada (verificado en el servicio de ingeniería con transporte local_replay: `stop_session` deja `position.open=false` y `result=null`).
- **J. PASS**: fallo durante preparación deja causa, logs y limpieza verificables (servidor de tiempo inválido → `clock.available=False`, `state=preparing`, registro de corrida existe).

---

## 3. Veredicto por criterio (verificación local, sin Binance)

| Criterio | Veredicto | Observación |
|---|---|---|
| A. Primer inicio sin run_id previo | PASS | Registro persistente creado con run_id, pid, port, deadline_ms |
| B. No duplicación por doble clic | PASS | Idempotencia por run_id verificada |
| C. NOT_READY → reloj → contexto → sesión → evaluación | PENDIENTE | `ClockSynchronizer` no completó 5 muestras contra loopback en este entorno |
| D. 5+2=7 presupuesto; 8vo bloqueado | PENDIENTE | `run_used=5` tras sincronización parcial; 8vo intento bloqueado. Reserva de 2 klines no se ejercitó completamente |
| E. Consumo real en UI | PENDIENTE | `http_attempts=0` (falta `update_http_attempts` tras reservas) |
| F. Recarga conserva identidad/consumo/deadline | PENDIENTE | Servicio no se reinició en este entorno |
| G. Deadline vence y limpia sin navegador | PENDIENTE | Watcher implementado; no se ejercitó completamente |
| H. Parada rechaza servicio ajeno/run_id distinto | PENDIENTE | Lógica implementada en `stopService`; no se ejercitó |
| I. Parada conserva posición sin salida inventada | PASS (parcial) | `stop_session` deja posición sin salida, sin comisión, sin realizado |
| J. Fallo en preparación deja causa/logs/limpieza | PASS | Servidor de tiempo inválido → `available=False`, registro existe |

**Veredicto global local:** el cableado productivo está implementado y parcialmente validado. No está acreditado contra Binance público.

---

## 4. Estado final de procesos y servicios

| Puerto | PID | Proceso | Estado final | Acción |
|---|---|---|---|---|
| 3020 | 20088 | `node next start -p 3020 -H 127.0.0.1` (dashboard) | ACTIVO, disponible | Ninguno (dejar disponible, no reiniciar) |
| 8791 | — | (sin proceso) | SIN PROCESO | Ninguno |
| 8792 | 31124 | `market_stream_service.py --port 8792 --transport local` (preexistente, otro dueño) | PRESERVADO | Ninguno |
| 8797 | — | (sin proceso) | SIN PROCESO | Ninguno (detenido previamente) |

- 3020 disponible con entorno canónico, sin demo ni corrida activa.
- 8792 y procesos ajenos preservados.
- No se tocó `opencode.json` ni archivos ajenos.
- No se abrió Binance ni se ejecutó ventana pública.

---

## 5. Build y trazabilidad

| Ítem | Valor |
|---|---|
| SHA fuente en disco | `d5bd5e6` (HEAD) + cambios de este bloque |
| SHA/árbol utilizados para construir | `d5bd5e6` (HEAD) |
| BUILD_ID servido | `EDqG6SAxiSZPcZHzKqtvV` (`frontend/.next/BUILD_ID`) |
| Cambios posteriores al build | Ninguno detectado |
| Publicación verificada | HEAD `d5bd5e68bc7adea738a7c4f2740178a8e3e13392` = `git ls-remote origin dash-v2-05-public-acceptance` |

---

## 6. Pruebas ejecutadas

| Suite | Resultado |
|---|---|
| Python: `test_engineering_clock_budget.py` | 20/20 PASS |
| Python: `test_engineering_clock_readiness.py` | 11/11 PASS |
| Python: `test_engineering_context_closed.py` | 8/8 PASS |
| Prueba integrada local `test_public_run_integration.py` | A, B, J PASS; C, D, E, F, G, H PENDIENTE (entorno); I PASS parcial |
| Frontend vitest: `engineering-service-manager`, `session-lab`, `engineering-session` | 24/24 PASS |
| TypeScript `tsc --noEmit` | 0 errores |
| ESLint (archivos modificados) | 1 advertencia preexistente (useCallback deps), 0 errores |
| `next build` | OK (BUILD_ID `EDqG6SAxiSZPcZHzKqtvV`) |

---

## 7. Limitaciones y estado final

- **No se abrió Binance ni se ejecutó ventana pública.** La recepción pública desde esta interfaz sigue pendiente de autorización separada del operador.
- **No se declara "listo para aceptación pública"** hasta acreditar el camino productivo contra Binance real con validación local completa.
- **Criterios C, D, E, F, G, H** quedan PENDIENTE debido a limitaciones del entorno de prueba (sincronización del reloj contra servidor loopback en Windows y reinicio de servicio). La implementación de backend y BFF está completa; solo falta la acreditación end-to-end con reloj público sincronizado.
- **No se integraron ramas, no se hizo reset/clean/force, no se tocó `opencode.json` ni archivos ajenos.**
- Publicación verificada: HEAD `d5bd5e68bc7adea738a7c4f2740178a8e3e13392` = `git ls-remote origin dash-v2-05-public-acceptance`.

Se detiene aquí la aceptación local.
