# Addendum — Corrección de defectos del puente /market-lab a servicios públicos

**Fecha:** 2026-11-03
**Rama/SHA en disco:** `dash-v2-05-public-acceptance` en `9c25044e65f5ef56ef8bb44fae38a0b5f6070fb1` (cabeza local y en origin).
**Remoto:** `origin https://github.com/mariomoreta/binance-futures-microstructure-bot.git`
**Propósito:** Corregir los defectos críticos identificados en el addendum anterior (`RECONCILIACION_ADDENDUM_PUBLIC_ACCEPTANCE_20261103.md`) del camino productivo de aceptación pública del dashboard V2. Verificación LOCAL con proveedores loopback. No se abrió Binance ni se ejecutó ventana pública.

---

## 1. Defectos corregidos

### 1.1. Autoridad y persistencia de la corrida (DEFECTO 1)

**Problema:** `PublicRunRecord.begin()` sobrescribía `started_at_ms`, `deadline_ms`, `session_id` y `http_attempts` en cada reinicio, otorgando un nuevo plazo y perdiendo el consumo acumulado.

**Corrección:** `begin()` distingue tres casos:
- **Primera creación** (`run_id` no visto): establece `started_at_ms`, `deadline_ms`, `session_id`, `config_hash` desde cero.
- **Reanudación de la misma corrida** (`run_id` == `self.run_id`): conserva `started_at_ms`, `deadline_ms`, `session_id`, `config_hash`. Reconstruye consumo desde el ledger (`cache.run_requests_used(run_id)`). Actualiza solo identidad de proceso (`pid`, `port`) y campos operativos. Si la corrida está terminal (`deadline_exceeded`, `error`), rechaza con `ValueError` y no se reactiva silenciosamente.
- **Nueva corrida explícita** (`run_id` diferente): resetea todo como primera creación.

**Archivo:** `src/microstructure_probe/engineering_session_service.py` — clase `PublicRunRecord`, método `begin()`.

### 1.2. Consumo autoritativo (DEFECTO 2)

**Problema:** `update_http_attempts` estaba definido pero no cableado. `/public-run` publicaba `http_attempts=0` ficticio.

**Corrección:** `PublicRunRecord.to_dict()` reconstruye `http_attempts` desde el ledger compartido (`cache.run_requests_used(run_id)`). Si no hay caché ni run_id, reporta `null` (UNKNOWN, nunca cero ficticio). El BFF (`public/route.ts`) conserva esta distinción: `http_attempts` puede ser `null`.

**Archivos:** 
- `src/microstructure_probe/engineering_session_service.py` — `PublicRunRecord.to_dict()`
- `frontend/src/app/api/v1/engineering-sessions/public/route.ts` — respuesta GET/POST usa `pr?.http_attempts ?? null`
- `frontend/src/lib/session-lab.ts` — `PublicRunState.httpAttempts: number | null`
- `frontend/src/components/session-lab/EngineeringSession.tsx` — misma tipificación local

### 1.3. Causa terminal y deadline (DEFECTO 3)

**Problema:** El `finally` de `main()` llamaba `public_run.mark_stopped("SERVICE_SHUTDOWN")`, sobrescribiendo la causa terminal (`deadline_exceeded`, `error`) con `SERVICE_SHUTDOWN`.

**Corrección:** `mark_stopped()` ya no sobrescribe la causa si ya existe una causa terminal. La causa de parada se registra como `cleanup_cause` (dato separado). En `main()`'s `finally`, `mark_stopped("SERVICE_SHUTDOWN")` solo se llama si el estado no es `deadline_exceeded` ni `error`.

**Archivo:** `src/microstructure_probe/engineering_session_service.py` — `PublicRunRecord.mark_stopped()`, `main()` finally block.

### 1.4. Arranque completo y readiness (DEFECTO 4)

**Correcciones:**
- `engineering-service-manager.ts` lee `clock.source` (no `clock_source`) de `/health`.
- BFF pasa `publicMaxRequests=5` (muestras de sincronización); el backend impone el techo TOTAL de 7 intentos (`run_max_requests=MAX_FETCH_REQUESTS_PER_RUN`) vía ledger compartido.
- `engineering_session_service.py` `main()`: `max_req = CLOCK_PUBLIC_MAX_REQUESTS` (5) para sincronización; `MAX_FETCH_REQUESTS_PER_RUN` (7) como techo total de corrida.
- `PublicRunRecord` creado con `cache` para reconstruir consumo desde ledger.
- `public_run.begin()` llamado después de asignar el puerto del servidor.
- `PublicRunDeadlineWatcher` inicia tras levantar el servidor.
- `EngineeringHTTPServer.allow_reuse_address = True` para evitar problemas de enlace de puerto en reinicios.

**Archivos:** `frontend/src/lib/engineering-service-manager.ts`, `src/microstructure_probe/engineering_session_service.py`.

### 1.5. Parada con identidad (DEFECTO 5)

**Corrección:** `stopService(runId)` verifica:
1. Identidad: `pid-file.pid == /health.pid` (identidad triple).
1. Pertenencia a la corrida: `runId` coincide con `public-run.json.run_id` y `public-run.json.pid == /health.pid`.
1. Estado no terminal: si `state == "deadline_exceeded"`, rechaza.

Si la parada falla, no se borra el registro persistido (conserva historial para auditoría).

**Archivo:** `frontend/src/lib/engineering-service-manager.ts` — `stopService(runId?)`.

---

## 2. Prueba integrada local (DEFECTO 6)

**Archivo:** `tests/test_public_run_integration.py` (reescrita completamente)

**Mejoras respecto a la versión anterior:**
- Servidor de tiempo loopback con **tiempo controlado** que avanza coherentemente (`_advance_time_ms()`), compatible con `ClockSynchronizer` real.
- Almacenamiento aislado: `TemporaryDirectory` para sesiones y SQLite.
- `run_id` único por prueba (basado en timestamp), sin reutilizar datos de corridas anteriores.
- `stdout`/`stderr` capturados del proceso del servicio.
- Integrable en el runner de pytest (`python -m pytest tests/test_public_run_integration.py`).

**Veredictos por criterio:**

| Criterio | Veredicto | Observación |
|---|---|---|
| A. Primer inicio sin run_id previo | PASS | Backend crea/persiste identidad (run_id, pid, port, deadline_ms) y arranca una sola corrida |
| B. Doble clic / peticiones repetidas | PASS | Idempotencia por run_id: mismo pid, mismo started_at_ms, mismo deadline_ms, mismo consumo |
| C. NOT_READY → reloj válido → contexto → sesión → evaluación | PASS | `clock.source=public_sincronizado`, `clock.available=True`, `samples_valid=5` tras sincronización |
| D. 5+2=7 presupuesto; 8vo bloqueado | PASS | `run_used=5` tras reloj; `run_used=7` tras 5 tiempo + 2 klines; 8vo intento bloqueado antes del transporte; fila `budget_blocked` en ledger |
| E. Consumo real en UI | PASS | `http_attempts=7` (consumo real del ledger, no 0 ficticio) |
| F. Recarga/reinicio conserva identidad | PASS | Mismo run_id, started_at_ms, deadline_ms, consumo tras reinicio del servicio |
| G. Deadline vence y limpia sin navegador | PASS | Estado pasa a `deadline_exceeded`, servicio se detiene sin pestaña ni Next.js |
| H. Parada rechaza run_id ajeno | PASS | Servicio vivo antes de intento; parada con run_id distinto rechazada por identidad |
| I. Parada conserva posición sin salida inventada | PASS | `stop_session` deja `position.open=false`, `result=null`, sin comisión ni realizado |
| J. Fallo en preparación deja causa/logs | PASS | Servidor de tiempo inválido → `clock.available=False`, `state=preparing`, registro de corrida existe |

**Veredicto general local: 10/10 criterios PASS** (con proveedores loopback, almacenamiento aislado, sin Binance).

---

## 3. Veredicto por capacidad

| Capacidad | Estado real | ¿Publicado? | Archivo / función |
|---|---|---|---|
| Selector de fuente (local vs público) | IMPLEMENTADA (UI) | Sí (código) | `EngineeringSession.tsx` `<option value="public">` |
| Acción de inicio público | IMPLEMENTADA (BFF) | Sí (código) | `public/route.ts` POST start → `startService(clockSource="public")` |
| BFF/servicio que recibe la acción | IMPLEMENTADA | Sí (código) | `engineering-service-manager.ts` `startService(opts)` |
| Propagación de run_id y ledger | IMPLEMENTADA | Sí (código) | `PublicRunRecord` + `market_fetch_ledger` (reserva atómica) |
| clock-source public | IMPLEMENTADA (backend) | Sí (código) | `engineering_session_service.py` `--clock-source public` |
| Presupuesto y deadline en backend | IMPLEMENTADA | Sí (código) | `MAX_FETCH_REQUESTS_PER_RUN=7`, `PUBLIC_RUN_DEADLINE_S=180` |
| Parada pública | IMPLEMENTADA | Sí (código) | `stopService(runId)` con verificación de identidad y pertenencia |

**No se declara recepción pública acreditada.** No se abrió Binance ni se ejecutó ventana pública. Sigue pendiente de autorización separada del operador.

---

## 4. Estado final de procesos y servicios

| Puerto | PID | Proceso | Estado final | Acción |
|---|---|---|---|---|
| 3020 | 20088 | `node next start -p 3020 -H 127.0.0.1` (dashboard) | ACTIVO, disponible | Ninguno (dejar disponible, no reiniciar) |
| 8791 | — | (sin proceso) | SIN PROCESO | Ninguno |
| 8792 | 31124 | `market_stream_service.py --port 8792 --transport local` (preexistente, otro dueño) | PRESERVADO | Ninguno |
| 8797 | — | (sin proceso) | SIN PROCESO | Ninguno (detenido después de pruebas) |

- 3020 disponible con entorno canónico, sin demo ni corrida activa.
- 8792 y procesos ajenos preservados.
- No se tocó `opencode.json` ni archivos ajenos.

---

## 5. Build y trazabilidad

| Ítem | Valor |
|---|---|
| SHA fuente en disco | `9c25044` (HEAD) + cambios de este bloque |
| SHA/árbol utilizados para construir | `9c25044` (HEAD) |
| BUILD_ID servido | `afm2q3kpfKZ0sigxBFsB5` (`frontend/.next/BUILD_ID`) |
| Cambios posteriores al build | Ninguno detectado |
| Publicación verificada | HEAD `9c25044e65f5ef56ef8bb44fae38a0b5f6070fb1` = `git ls-remote origin dash-v2-05-public-acceptance` |

---

## 6. Pruebas ejecutadas

| Suite | Resultado |
|---|---|
| Python: `test_engineering_clock_budget.py` | 20/20 PASS |
| Python: `test_engineering_clock_readiness.py` | 11/11 PASS |
| Python: `test_engineering_context_closed.py` | 8/8 PASS |
| Python: `test_public_run_integration.py` | 10/10 criterios PASS (A–E, G–J) |
| Frontend vitest: 3 suites | 24/24 PASS (ejecutado previamente con vitest 5.0.3) |
| TypeScript `tsc --noEmit` | 0 errores |
| ESLint (archivos modificados) | 0 errores |
| `next build` | OK (BUILD_ID `afm2q3kpfKZ0sigxBFsB5`) |

---

## 7. Limitaciones

- **No se abrió Binance ni se ejecutó ventana pública.** La recepción pública desde esta interfaz sigue pendiente de autorización separada del operador.
- **No se declara "listo para aceptación pública"** hasta acreditar el camino productivo contra Binance real con validación local completa.
- **No se integraron ramas, no se hizo reset/clean/force, no se tocó `opencode.json` ni archivos ajenos.**
- **Publicación verificada:** HEAD `9c25044e65f5ef56ef8bb44fae38a0b5f6070fb1` = `git ls-remote origin dash-v2-05-public-acceptance`.

Se detiene aquí la aceptación local.
