# Addendum de reconciliación — aceptación pública Dashboard V2 (dash-v2-05)

**Fecha:** 2026-11-03
**Rama/SHA en disco:** `dash-v2-05-public-acceptance` en `c3b860090bfe7d4f48ca555288cc50d3d07b47a2` (cabeza local).
**Remoto:** `origin = https://github.com/mariomoreta/binance-futures-microstructure-bot.git`
**Estado de la rama en origin:** `dash-v2-05-public-acceptance` **no existe** en `origin`. El commit `c3b8600` sí está publicado en origin como `refs/heads/dash-v2-04-recorrido-visible`.
**Propósito:** corregir el informe anterior **sin borrar historia**. No se declara "listo para aceptación pública".

---

## 1. Qué dice el git (inventario, sin editar)

| Ítem | Valor |
|---|---|
| Ruta del repositorio | `C:\proyectos\binance-futures-microstructure-bot` |
| Remoto | `origin https://github.com/mariomoreta/binance-futures-microstructure-bot.git` (fetch + push) |
| Rama actual | `dash-v2-05-public-acceptance` |
| SHA completo (HEAD) | `c3b860090bfe7d4f48ca555288cc50d3d07b47a2` |
| `git status --short` | 3 modificados (`EngineeringSession.tsx`, `session-lab.ts`, `opencode.json`) + muchos untracked (evidencia, `fix_engine*.py`, `fix_test*.py`, `binance_case_study/`, `paper-lab-sessions/`, `_*.html/json`, `frontend/acceptance-playwright.js`, `frontend/src/app/api/v1/engineering-sessions/public/`, etc.) |
| `git diff --stat` | `EngineeringSession.tsx` (2980+/1409-), `session-lab.ts` (+38), `opencode.json` (-1). Sin staged. |
| `git diff --cached --stat` | vacío (nada staged) |
| `c3b8600` contiene | **Solo docs + evidencia** (`CURRENT_STATE.md`, `DECISIONS.md`, `FEATURE_BACKLOG.md`, `TASK_QUEUE.md`, capturas PNG, `acceptance-summary.json`, `backend-api.json` bajo `docs/evidence/dashboard-EFHI-20261103/`). **No contiene** `EngineeringSession.tsx` ni `session-lab.ts`. |
| Commits locales no publicados | No hay commit local nuevo por publicar: `c3b8600` ya está en origin (como `dash-v2-04-recorrido-visible`). La rama `dash-v2-05-public-acceptance` es local y apunta a ese SHA ya publicado. |
| `git ls-remote origin` para `dash-v2-05-public-acceptance` | No encontrado (no existe en origin). |
| `git ls-remote origin` para `dash-v2-04-recorrido-visible` | `c3b860090bfe7d4f48ca555288cc50d3d07b47a2` (existe). |

**Conclusión git:** el informe anterior atribuyó cambios a `EngineeringSession.tsx` y `session-lab.ts` como si estuvieran en `c3b8600`; es falso. Ese commit solo documenta la semántica de costes y la aceptación A-J del dashboard. El código de la "aceptación pública" vive **sin commitear** en el árbol de trabajo.

---

## 2. Inventario de capacidades (estado real)

Nota: una etiqueta, temporizador o contador en React **no acredita control efectivo del backend**. Ninguna capacidad está "implementada y publicada" contra Binance público.

| Capacidad | Estado real | Archivo / función | Commit |
|---|---|---|---|
| Selector de fuente (local vs público) | **SOLO LOCAL (UI sin commitear, sin backend público)** | `frontend/src/components/session-lab/EngineeringSession.tsx` L187 `type DataSource = "local" \| "public"`, L1102 `<option value="public">` | No está en `c3b8600`; modificación local sin commitear |
| Acción de inicio público | **SOLO LOCAL / PARCIAL** | `frontend/src/lib/session-lab.ts` `startPublicRun()` → POST `/api/v1/engineering-sessions/public`; `frontend/src/app/api/v1/engineering-sessions/public/route.ts` POST `action=start` genera `run_id = eng-public-${Date.now()}` y llama `startService()` | `public/route.ts` **untracked** (no commiteado); `session-lab.ts` modificado sin commitear |
| BFF/servicio que recibe la acción | **SOLO LOCAL** | `public/route.ts` → `startService()` (`@/lib/engineering-service-manager`) spawns `scripts/engineering_session_service.py --host 127.0.0.1 --port 8797 ...` **sin** `--clock-source public` ni `--transport public` | `engineering-service-manager.ts` modificado/local; `public/route.ts` untracked |
| Propagación de run_id y ledger | **PARCIAL (run_id efímero, sin ledger)** | `public/route.ts` guarda `activePublicRuns` (Map en memoria, se pierde al reiniciar el servidor). No persiste en `market_fetch_ledger` ni vincula run_id a ledger. | `public/route.ts` untracked |
| clock-source public | **PARCIAL (soporte en backend, no cableado al público)** | `src/microstructure_probe/engineering_session_service.py`: `--clock-source choices=["local","public"]` (L2106), `ClockSynchronizer`, `_make_budgeted_time_fetch` (L231), `clock_source_label="public_sincronizado"` (L2215). Pero `startService()` del BFF no pasa `--clock-source public`; `/health` de 8797 reporta `clock.source: local_sistema`. | Backend sí tiene soporte; BFF no lo activa |
| Presupuesto y deadline impuestos en backend | **PARCIAL (presupuesto del reloj público en backend; 7/180 solo en BFF en memoria)** | `public/route.ts`: `PUBLIC_HTTP_MAX=7`, `PUBLIC_DEADLINE_S=180` (solo ruta BFF, memoria). Backend: `reserve_fetch_attempt` + `UpstreamBudgetExceeded` "presupuesto publico agotado" (L257-259), `PUBLIC_CLOCK_BUDGET_INSUFICIENTE` (L2190-2202) — solo si se activa modo público, cosa que el BFF no hace. No hay HTTP real contra Binance en este camino. | `public/route.ts` (BFF, untracked); backend `engineering_session_service.py` (soporte no activado) |
| Parada pública | **PARCIAL / SOLO LOCAL** | `stopPublicRun()` → POST `/public` `action=stop` borra `run_id` de `activePublicRuns` (memoria). **No detiene** el servicio de ingeniería ni el drive en marcha. | `session-lab.ts` L534; `public/route.ts` L104-113 (untracked) |

**Veredicto de capacidades:** ninguna capacidad es "IMPLEMENTADA Y PUBLICADA" contra Binance público. Todas las piezas de "aceptación pública" están en el árbol de trabajo **sin commitear**, y el camino que se ejecuta arranca el servicio en **modo local** (reloj `local_sistema`, mercado `http://127.0.0.1:8791`, sin WS pública). No hay conexión real a `fstream.binance.com`.

---

## 3. Hallazgos clave (corrección al informe anterior)

1. **`c3b8600` no implementa controles públicos.** Modifica documentación y evidencia (PnLPanel semántica de costes + aceptación A-J). No toca `EngineeringSession.tsx` ni `session-lab.ts`.
2. **El informe atribuyó cambios a `EngineeringSession.tsx` y `session-lab.ts` que no aparecen en ese commit.** Esos archivos están **modificados sin commitear** en el árbol de trabajo.
3. **`dash-v2-05-public-acceptance` no está en GitHub.** Solo existe localmente; apunta a `c3b8600`, que sí está en origin bajo `dash-v2-04-recorrido-visible`.
4. **No hay 8791/8797 activos por botón deshabilitado.** Al cerrar la reconciliación: 8797 detenido (`POST /shutdown`, 200 pid 18344); 8791 ya caído (sin listener); 8792 (pid 31124, preexistente, preservado); 3020 (pid 20088, dashboard, disponible, no reiniciado).
5. **No hay posición paper abierta con fill.** La sesión más reciente (`PL-MINAUSDT-LONG-1793729090556`) tiene `position.open: false`; las decisiones `ENTRADA_SIMULADA` son señales "pendiente de fill" que nunca se materializaron (feed silencioso). No hay salida que inventar.
6. **Pid-file de 8797 desactualizado:** decía pid 17984, listener real 18344 (cadena de identidad incompleta). Se detuvo por `/shutdown` dirigida al puerto, no por pid-file ciego.

---

## 4. Estado de procesos y limpieza (final)

| Puerto | PID | Línea de comandos | Identidad /health | pid-file | Estado final | Acción |
|---|---|---|---|---|---|---|
| 3020 | 20088 | `node next start -p 3020 -H 127.0.0.1` | Dashboard Next.js | n/a | **ACTIVO, preservado** | Ninguna (dejar disponible, no reiniciar) |
| 8791 | — | (sin proceso) | No escucha | — | **CAÍDO** | Ninguna (no hay proceso propio) |
| 8792 | 31124 | `python market_stream_service.py --port 8792 --transport local --base-url ws://127.0.0.1:9999` | Preexistente, otro dueño | `data/market-stream/service.json` (intacto) | **PRESERVADO** | Ninguna |
| 8797 | 18344 (ya no existe) | `python engineering_session_service.py --host 127.0.0.1 --port 8797 --sessions-dir data/engineering-session/sessions --pid-file data/engineering-session/service.json` | `engineering-session-service/v1`, `clock.source: local_sistema`, `market.url: http://127.0.0.1:8791` | `data/engineering-session/service.json` **desactualizado** (pid 17984 ≠ 18344) | **DETENIDO** | `POST /shutdown` → 200 `{"ok":true,"pid":18344}`; puerto libre, proceso finalizado |

- 8791: sin servicio (no escucha), por tanto transporte local/public **N/A** (no hay proceso que confirme transporte). 8797 intentaba conectar a 8791 (`SYN_SENT`, fallado, WinError 10061).
- 8797: proceso propio de ensayo, identidad acreditada (cmdline + `/health` pid coinciden). Detenido por el mecanismo canónico (`POST /shutdown`), no por pid-file ciego.
- No se tocó 8792 ni procesos ajenos. No se reinició el dashboard. No se abrió conexión externa para diagnóstico (salvo `GET /health` local de identificación y `POST /shutdown` local, autorizados por el usuario).
- Limpieza registrada: 8797 detenido; 3020 y 8792 intactos; 8791 sin proceso.

---

## 5. Build y trazabilidad

| Ítem | Valor | Acreditación |
|---|---|---|
| SHA/árbol fuente en disco | `c3b8600` + árbol de trabajo con modificaciones sin commitear (`EngineeringSession.tsx`, `session-lab.ts`, `opencode.json`) | `git rev-parse HEAD` / `git status` |
| SHA/árbol utilizados para construir | No hay SHA de build registrado (`.next` está gitignorado). El build en disco (`.next/BUILD_ID` mtime 1:17:10pm) es posterior a las ediciones de fuentes (`EngineeringSession.tsx` 1:15:54pm, `session-lab.ts` 12:48:09pm, `public/route.ts` 12:48:27pm), por lo que el árbol servido incluye las modificaciones locales. **Sin SHA de build acreditado como tal.** | mtime de archivos (indicio, no registro de build) |
| BUILD_ID servido | `IP0rAspzDtEWfLsu6uzos` | `frontend/.next/BUILD_ID` (coincide con carpeta de chunks estáticos y con PID 20088) |
| Cambios locales posteriores al build | Ninguno detectado en fuentes de build (todas las ediciones preceden al build) | Comparación de mtimes |
| Fuente servida | No se declara UNKNOWN: se sirve `c3b8600` + modificaciones locales, BUILD_ID `IP0rAspzDtEWfLsu6uzos`. No se infiere contenido por HTTP 200. | Evidencia de mtime + BUILD_ID en disco |

---

## 6. Veredicto

**No listo para aceptación pública.** El camino productivo (selector fuente → acción pública → BFF → servicio con clock público + presupuesto/deadline impuestos en backend → parada efectiva) **no está acreditado**:
- el código de aceptación pública no está commiteado ni publicado;
- el servicio se arranca en modo local (`local_sistema`), sin WS pública a Binance;
- run_id es efímero en memoria, sin ledger;
- presupuesto 7 HTTP / deadline 180 s solo existen en la ruta BFF (memoria), no contra Binance real;
- la parada pública no detiene el servicio ni el drive;
- no se ejecutó ventana pública en esta reconciliación (por decisión del usuario: no ejecutar otra ventana pública).

Se publica únicamente la reconciliación documental (este addendum). No se commitea ni se publica código parcial de este bloque (evitar mezclar con archivos ajenos: `fix_engine*.py`, `fix_test*.py`, `opencode.json`, evidencias, capturas, etc.).

---

## 7. Estado final de servicios y sesiones

- Servicios: 3020 disponible (PID 20088), 8792 preservado (PID 31124), 8791 sin proceso, 8797 detenido.
- Sesiones: drives en `state: running` pero congelados por `FEED_SILENCE` (8791 caído); `position.open: false` en la sesión más reciente; ninguna posición paper abierta con fill; sin salida inventada.
- Rama/SHA publicados: `c3b8600` ya en origin (como `dash-v2-04-recorrido-visible`); `dash-v2-05-public-acceptance` solo local hasta este addendum.
