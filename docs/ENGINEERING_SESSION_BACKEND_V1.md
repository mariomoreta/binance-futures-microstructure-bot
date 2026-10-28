# Sesión de ingeniería — autonomía en backend (engineering-session-service/v1)

**Fecha:** bloque 2026-10-27/28 · **Base probada:** `0aa98f5` (branch
`feat/ingenieria-autonoma`; trabajo posterior a la base con commit en la
misma rama) · **BUILD_ID servido en 3020:** `r5poURhuj3RQc4CjC6Kyz` ·
**Estado:** documentación factual de lo implementado y probado. Alcance
desktop, presupuesto cero, **0 Binance público**, 0 upstream, 0 órdenes.

---

## 1. Distinción clave: replay-autoavance (antiguo) ≠ autonomía en backend (nueva)

| Aspecto | Modo autónomo (2026-10-27, base `9a24308`) | Autonomía en backend (este bloque, base `0aa98f5`) |
|---|---|---|
| Autoridad de avance | `setTimeout` en React dentro de la pestaña (`autonomousTick`) | hilo coordinador del servicio Python (`advance_once()`) |
| Motor de avance | 1 proceso Python por tick vía `spawnSync` en `/step` | servicio residente que reutiliza `paper_lab_engine` (un solo proceso) |
| Pérdida de la pestaña | el reloj muere con la pestaña (no hay avance) | la conducción SIGUE; al reabrir se recupera el estado correcto |
| Papel del navegador | observador que además PROGRAMABA el próximo paso | **solo observador** (`GET` cada `OBSERVER_INTERVAL_MS=800`) |
| Acciones manuales | deshabilitadas durante la autonomía, `driveRunning` condiciona canEnter/canStep | idénticas, todas vía `POST /control` (start/stop/step/stop_session/exit/evaluate/restart) |
| Transporte | HTTP BFF+spawn por paso | eventos `REVEAL` del transporte local con cadencia (700 ms en aceptación) — el evaluador solo recibe el prefijo revelado (sin OHLC en eventos de transporte, sin velas futuras en el dict público) |

El modo autónomo anterior NO se considera reemplazado retroactivamente: fue
el paso previo y su evidencia (`docs/evidence/INGENIERIA_AUTONOMA_*.png`)
sigue siendo válida para lo que probó. Este bloque cumple el objetivo que
aquél declaraba: **cerrar pestaña no detiene la sesión**.

## 2. Arquitectura

- `src/microstructure_probe/engineering_session_service.py` + CLI
  `scripts/engineering_session_service.py` (start/stop con `--pid-file`;
  `--stop --pid-file` verificado; puertos efímeros OK para tests).
- `ThreadingHTTPServer` de biblioteca estándar, contrato
  `engineering-session-service/v1`, puerto por defecto **8797**.
- Controlador = `paper_lab_engine` (motor canónico, sin motor paralelo) +
  `LocalReplayTransport` (cadencia; SOLO eventos REVEAL) + hilo coordinador
  que llama `advance_once()`. Tope de seguridad `DRIVE_MAX_EVENTS=4096`.
- PID file en `data/engineering-session/*.json`; `sessions_dir` aislado en
  pruebas (`data/engineering-session/acceptance-sessions`), fuera del
  canónico `paper-lab-sessions/`.

### Endpoints (formas uniformes)

- `GET /health` → `{service, engine_version}`.
- `POST /sessions` (create) → `{session}`.
- `GET /sessions/{id}` → `{session, drive}` (drive es hermana, no anidada).
- `POST /sessions/{id}/control` → `{session, drive}`; acciones:
  `start|stop|step|stop_session|start_drive|exit|restart|evaluate`.
- `POST /shutdown`.
- Causas de fin de conducción: `SESSION_CLOSED`, `END_OF_TRANSPORT`,
  `OPERATOR_STOP`, `SESSION_STOPPED` (stop con posición abierta → `detenida`),
  `DRIVE_EVENT_LIMIT`, `DRIVE_ERROR:*`.

## 3. Semántica de abstención (corregida y probada)

- `SIN_ENTRADA` = **abstención temporal**: no bloquea información nueva; la
  sesión se reevalúa ante cada evento revelado. Test determinista: sin
  entrada → nuevo evento confirmatorio → entrada simulada sin intervención
  humana (`tests/test_engineering_session_service.py`).
- `DESCARTADO` = **descarte terminal**: cierra la sesión y no se reabre.
- El evaluador solo recibe el prefijo revelado (sin futuro). Corrección de
  causalidad en `session_to_public_dict` (sin velas futuras en el dict
  público) — 3 fallos preexistentes de Python corregidos en este bloque:
  suite 1530 passed / 2 skipped (antes 6 fallos en la base).

## 4. Cierre de pestaña (S2) — demostración de autonomía real

Abrir posición → cerrar pestaña → el backend siguió conduciendo
(revisión 33 → 38, `SESSION_CLOSED`) → reabrir recupera sesión `cerrada`
con panel de exportación. Red: solo `GET`. Evidencia: `eng-03..eng-08`.

## 5. Correcciones de robustez

- Windows: `save_session` (escritura + `os.replace`) y `load_session`
  reintentan 5x con backoff ascendente (20 ms) ante `OSError`/
  `PermissionError` transitorios; corrupción real sigue siendo explícita
  (`IDENTITY_UNCERTAIN`).
- BFF proxy `frontend/src/app/api/v1/engineering-sessions/**` (env
  `ENGINEERING_SERVICE_URL`, guardia de origen host 127.0.0.1:3020);
  cliente `frontend/src/lib/session-lab.ts` (`createBackendSession`,
  `fetchBackendSession`, `controlBackendSession`).
- Frontend observador `EngineeringSession.tsx`: chip de estado de
  conducción, `DRIVE_CAUSE_TEXT`, `setDrive(null)` en sesión nueva; React
  timer del navegador como autoridad de avance eliminada (tickRef/loopRef/autonomousRef retirados).
- Ruido de stderr en apagado: `handle_error` traga
  `ConnectionResetError`/`BrokenPipeError` (polish post-aceptación).

## 6. Aceptación en navegador real (PASS)

Juego de aceptación `S1..S4` contra el servicio real (estado bajo la pestaña
abierta, cerrada y reabierta; red verificada por instrumento):

| Caso | Resultado |
|---|---|
| S1 ciclo autónomo completo | entrar pendiente → fill → gestión → `cerrada`; `SESSION_CLOSED`; 1 evento de entrada |
| S2 cerrar pestaña | backend siguió conduciendo (33→38); `SESSION_CLOSED`; reabrir recupera estado correcto |
| S3 parar con posición abierta | `detenida`, posición preservada, `OPERATOR_STOP` visualizado |
| S4 prefijo B + cierre | `cerrada` por horizonte, net_pnl 4.944281, kinds protección=2/entrada=1/marca=1/salida=1; tras recuperación 24 GET / 0 POST |

Nota honesta: con la caché real de MINAUSDT ambos prefijos (A y B) admitían
entrada; NO se fabricó abstención en datos reales. La separación
abstención temporal / terminal y la confirmación posterior están probadas
determinísticamente en las suites (no en la demo de navegador).

## 7. Estado operativo de la entrega

- Suite: backend `tests/test_engineering_session_service.py` 8/8,
  frontend `engineering-session.test.tsx` 8/8; `tsc`/`eslint` 0;
  Python completo 1530 passed / 2 skipped; frontend 604 passed / 1 skipped.
- Limpieza verificada: instancia de aceptación (8797) parada y directorio
  de sesiones de prueba eliminado; dashboard canónico 3020 sirviendo con
  BUILD_ID `r5poURhuj3RQc4CjC6Kyz`; servicio de flujo preexistente en
  8792 SIN tocar.
- Error de consola NO a cargo de este trabajo: `ERR_INCOMPLETE_CHUNKED_ENCODING`
  en `/api/v1/market-flow/stream` (SSE de otro panel; preexistente).

## 8. Acceso operativo y semántica sesión/servicio (verificación 2026-10-28)

Verificación de acceso con 8797 detenido (evidencia
`docs/evidence/engineering-backend-2026-10-28/operational-access-2026-10-28.json`,
SHA fuente `5f24807`, BUILD_ID `r5poURhuj3RQc4CjC6Kyz`):

### 9.1 Arranque manual del servicio — limitación declarada (HISTÓRICO)

> **SUPERSEDED (2026-10-28, ver §10):** el inicio explícito completo ahora
> está integrado en «Iniciar sesión» vía el gestor del BFF; esta sección se
> conserva como registro histórico de la limitación declarada.

**Deliberado:** abrir `/market-lab` NO arranca ningún proceso (cabecera del
CLI: *«Arranque/parada explícitos; no se lanza solo porque alguien abra una
página»*). El BFF `engineering-sessions` es proxy puro (sin `child_process`).
Con el servicio detenido, «Iniciar sesion» muestra un banner de error visible
(`data-testid="session-error"`, 503 del BFF; etiqueta observada
`ENGINEERING_PROXY_ERROR`, el mapeo `ENGINEERING_SERVICE_DOWN` solo aparece
cuando el `code` top-level del fetch lo expone), sin duplicados y sin
escribir `session_id` en localStorage. El botón NO es un inicio completo:
**el operador levanta el servicio con el CLI canónico**:

```
python scripts/engineering_session_service.py --port 8797 \
  --sessions-dir data/engineering-session/sessions \
  --pid-file data/engineering-session/service.json
```

Nota de aislamiento: el default SIN `--sessions-dir` es
`paper-lab-sessions/` (compartido con el controlador anterior
`scripts/paper_lab_session.py`); el motor además anida
`paper-lab-sessions/` bajo el raíz indicado. Para acceso canónico usar el
directorio dedicado indicado arriba.

### 9.2 Semántica verificada: sesión ≠ servicio

| Acción | Qué toca | Qué NO toca | Evidencia |
|---|---|---|---|
| «Detener sesion» (control stop + stop_session) | política de posición: congela la sesión (`detenida`) y detiene la conducción | sin cierre inventado, sin evento de salida; posición queda tal cual (`entry_px`/`mark_px` preservados) | `…516fa8d8`: rev 11→12, kinds `protection=2,entry=1,mark=1` |
| Cerrar la pestaña | solo desconecta al observador | el backend sigue conduciendo (rev 7→31→38, `SESSION_CLOSED` con pestaña cerrada); reabrir recupera el estado correcto | `…49b05386` |
| Detener el servicio (`--stop` / `/shutdown`) | termina transportes/drives en memoria (causa `OPERATOR_STOP` efímera) | NUNCA muta el estado económico en disco: sin eventos nuevos, sin cierres; sesiones quedan intactas y manejables tras reinicio | `…516fa8d8` en disco: `abierta` rev 11, kinds sin salida |
| Abrir `/market-lab` | nada (solo observación) | no inicia procesos ni sesiones | banners visibles cuando el servicio falta |

### 9.3 Defecto abierto del panel de flujo (RESUELTO — ver §10)

`ERR_INCOMPLETE_CHUNKED_ENCODING` en `/api/v1/market-flow/stream`
(SSE del panel de flujo, panel ajeno a este bloque) se mantenía como
DEFECTO ABIERTO. **RESUELTO en 2026-10-28 (§10):** causa reproducida y
corregida (timeout de cuerpo del BFF + `bodyTimeout` de undici; sin
cambios al servicio preexistente 8792).

### 9.4 Recorrido completo probado (usuario real)

iniciar → sesión backend activa (`abierta`, drive `running`, 1 POST create
+ 1 POST control, resto GET) → cerrar pestaña → backend cierra solo
(`SESSION_CLOSED`) → reabrir → recuperación correcta → (segunda sesión)
detener servicio con drive corriendo → estado en disco intacto → reiniciar
servicio → recuperar → «Detener sesion» → `detenida` con posición
preservada. Al final: servicio detenido y directorios de sesiones de
ensayo eliminados; dashboard canónico servido sin sesiones de ensayo.

## 9. Evidencia

- `docs/evidence/engineering-backend-2026-10-27/` — 13 piezas + `acceptance-summary.json`.
- `docs/evidence/engineering-backend-2026-10-28/` — verificación de acceso operativo (2026-10-28).
- `docs/evidence/engineering-explicit-start-2026-10-28/` — aceptación del inicio explícito + arreglo SSE (2026-10-28): `acceptance-summary.json` (casos A–G), capturas del fallo de arranque/lifecycle/recuperación, sesiones de ensayo archivadas + artefacto anómalo preservado (archivo vacío sin sufijo, causa UNKNOWN).
- `tests/test_engineering_session_service.py`; `tests/test_paper_lab_engine.py` (regresión);
  `frontend/src/test/engineering-session.test.tsx`; `frontend/src/test/market-flow-panel.test.tsx`; `frontend/src/test/session-lab.test.ts`.
- Código: `src/microstructure_probe/engineering_session_service.py`;
  `frontend/src/lib/engineering-service-manager.ts`;
  `frontend/src/app/api/v1/engineering-sessions/service/route.ts`.

## 10. Inicio explícito integrado en la UI + defecto SSE corregido (2026-10-28)

### 10.1 Arranque completo por «Iniciar sesión» (sin comandos manuales)

El botón es ahora un **inicio completo explícito**: comprueba el servicio
(GET consulta pura), y si está detenido arranca **solo la instancia
canónica del proyecto** vía BFF:

- Spawn objetivo: `scripts/engineering_session_service.py` (el controlador
  canónico ya existente; NO hay un gestor paralelo; el BFF solo lo genera
  y espera readiness).
- Readiness con límite (15 s default, `ENGINEERING_SERVICE_START_TIMEOUT_MS`)
  + **verificación de identidad**: `child.pid == pid-file
  (`data/engineering-session/service.json`) == /health.pid`. Nunca se
  reutiliza ni detiene un PID desconocido (puerto ocupado con identidad no
  verificable → `ENGINEERING_SERVICE_UNIDENTIFIED`, sin arrancar ni matar).
- En fallo de readiness el gestor termina SOLO el proceso que él generó
  (`child.kill()`); sin huérfanos. El fallo de generación (p. ej.
  intérprete inexistente) llega por el evento `error` de `child_process` y
  está manejado (el dashboard no cae; error visible
  `ENGINEERING_SERVICE_START_FAILED`).
- Nada arranca por GET ni por abrir la página: `GET
  /api/v1/engineering-sessions/service` es consulta pura; el chip de estado
  distingue `checking / starting / ready / down / error`
  (`data-testid="service-chip"`).
- Idempotente: servicio ya listo y verificado → sin nuevo spawn.
- Doble clic: guardia SÍNCRONA (`startInFlightRef`) además del
  `disabled` de React — un segundo click dentro del mismo gesto no crea una
  segunda sesión (el primer intento sin la guardia creó DOS sesiones; ver
  evidencia del artefacto anómalo).

### 10.2 Directorio de sesiones dedicado por defecto

El default del servicio era ROTO (el `ROOT` del módulo apuntaba a `src/`,
no al repo): ahora `ROOT` correcto y `SESSIONS_DEFAULT =
data/engineering-session/sessions` — **sin colisión** con el controlador
anterior `scripts/paper_lab_session.py` (cuyo raíz canónico sigue siendo
`paper-lab-sessions/`). Las sesiones existentes se conservan sin migración
ni borrado (el motor anida `paper-lab-sessions/` bajo el raíz indicado).

### 10.3 Defecto SSE del panel de flujo — causa y arreglo

Causa reproducida (dos cortes con el mismo síntoma
`ERR_INCOMPLETE_CHUNKED_ENCODING`):
1. La ruta BFF del stream pasaba `AbortSignal.timeout(30_000)` al fetch
   upstream: CADA SSE moría a los 30 s exactos (log del proceso anterior:
   ~10× "failed to pipe response" + `TimeoutError`).
2. Además, el fetch global de Node (undici) aplica `bodyTimeout` por
   defecto (30 s sin chunk): `/flow/stream` del servicio preexistente
   (8792, no modificado) queda mudo cuando no se procesan eventos de
   flujo, y undici cortaba con `UND_ERR_BODY_TIMEOUT`.

La correlación con "re-renders" del bloque anterior era temporal (los
re-polls del observador a 800 ms coincidían en tiempo), no causal.

Arreglo (sin tocar 8792):
- `stream/route.ts`: agente undici dedicado con `bodyTimeout: 0` +
  `headersTimeout: 10 s`; sin `AbortSignal.timeout`; cancelación propagada
  por `req.signal` (cambio de símbolo/desmontaje/pestaña cerrada libera el
  consumidor upstream; un re-render sin cambio de identidad no toca la
  conexión).
- `MarketFlowPanel.tsx`: reconexión automática a los 2,5 s SIN cambiar
  identidad (reintento con la MISMA identidad); la causa visible
  («desconectado — reintentando») se conserva hasta `onopen` (sin falsa
  reconexión); desmontar o cambiar símbolo NO reabre la suscripción
  (libera su consumidor). Frescura y errores visibles intactos.

### 10.4 Aceptación (navegador real, casos A–G) — PASS

Ver `docs/evidence/engineering-explicit-start-2026-10-28/acceptance-summary.json`:
A apertura sin procesos; B doble clic → UNA sesión (tras fix de guardia
síncrona; el primer intento documentó el hallazgo + artefacto no
reproducible, causa UNKNOWN); C identidad triple verificada; D «Detener
sesion» → `detenida` rev 21, posición preservada (sin exit inventado),
servicio sigue ready; E cerrar/reabrir pestaña → recuperación íntegra; F
fallo de arranque → banner claro (`ENGINEERING_SERVICE_START_FAILED`),
0 huérfanos, 0 sesiones, dashboard íntegro; G SSE estable 78 s + 40 s
(0 errores de consola, 0 "failed to pipe" en BFF); panel marca «datos
obsoletos» honestamente (fuente aggTrade local sin inyectar ~26 h:
entorno, no defecto).

Estado final: servicio 8797 detenido (sin pid-file, sin sesiones de
ensayo en el dir dedicado); dashboard 3020 sirviendo BUILD_ID
`FQGAqw1wwcXIMQqei_fRA`; 8792 intocado.

## 11. Transporte `market_stream` en vivo: backend + frontend + aceptación local (2026-10-28, base `90b3c9b`)

### 11.1 Qué es

La sesión de ingeniería consume en vivo el MISMO `market-stream-service/v1`
(SSE loopback) que el paper-lab: el servicio de ingeniería
(`engineering_session_service.py`) avanza su contexto y sus decisiones con
los snapshots del stream en vivo (gates de feed vivo, `_consume_snapshot`,
`_consume_market_closed`, `_live_advance`) y el frontend
(`EngineeringSession.tsx` + `session-lab.ts` +
`engineering-service-manager.ts`) arranca y supervisa el runner
`market_stream`. No se creó ningún colector, motor ni gestor nuevos;
`paper_lab_engine` no se tocó.

### 11.2 Qué NO es

- No acredita recepción de Binance: todo el arnés es loopback (fake WS →
  servicio de mercado → SSE); el proveedor público permanece bloqueado
  por diseño (sitecustomize + guardia de resolución del navegador + proxy
  de registro).
- No repara huecos por REST: la reparación REST no existe en local.
- No persiste frames live (MEMORY_ONLY): el backfill del arnés no
  contamina el contexto.

### 11.3 Aceptación local PASS

Evidencia: `docs/evidence/engineering-live-local-2026-10-28/summary.json`
(corrida 379,9 s, git_sha `90b3c9b`, BUILD_ID `WDYGaWV_cUxErasQlce70`,
navegador real en 3020 con productor SSE local determinista; capturas
shot-01..06; 0 peticiones externas; `trial_sessions: []`; 3020 restaurado
al estado previo —estaba libre—; 8792 y 8797 intocables).

Guion verificado de punta a punta: backfill multi-frontera sin señal
(1.0490) → abstención → pausa de 95 s → vela M tardía → puerta
FEED_SILENCE (vela fusionada; reevaluaciones SIN_ENTRADA en M+1/M+2) →
señal close(M+2)=1.0520 al conocerse → fill open(M+4)=1.0525
(fill_basis=model_approximation) → reinicio del servicio de mercado
(15 s) → salida por stop con close(M+4)=1.0300 ≤ 1.03425 → cerrada.
Net −16,59 (simulado). 12/12 checks autoritativos (status cerrada,
ENTRADA_SIMULADA, salida por stop, 3 relojes, bloques indicators +
context_btc, runner market_stream, 8 reconexiones con watermark,
market_url loopback).

Verificación de código: 92 passed (41+1 `test_market_explorer.py`,
`test_engineering_service_market_stream.py`,
`test_engineering_session_service.py`, `test_paper_lab_engine.py`);
arnés `scripts/engineering_live_local_acceptance.py` compila; frontend
verificado previamente sin cambios pendientes (tsc/eslint 0, vitest OK).
`shot-05` y `shot-06` tienen bytes idénticos: cierre instantáneo tras la
salida (`cerrada_s` 0.006), honesto.

### 11.4 Defecto del explorador canónico descubierto y corregido

- Síntoma: smoke HTTP PASS contra el servicio de mercado, pero el create
  live en navegador fallaba la puerta live (GRID_GAP/DATA_STALE) sin
  decisión falsa. El repro CLI contra el cache temporal confirmó la
  causa.
- Causa: `market_explorer.read_stored` con rango amplio (`from_ms=0` +
  `to_ms` enorme) leía ASC con `LIMIT 5000` (MAX_SERIES_LIMIT) y
  devolvía la CABEZA del rango (velas más antiguas) cuando el cache
  supera 5000 velas: el contexto del create live quedaba días atrasado.
- Arreglo: lectura por COLA (newest-first + reversa en canónico y cache;
  `bars[-limit:]` tras la fusión). Semántica idéntica con ≤limit;
  regresión nueva
  `test_limit_keeps_the_most_recent_bars_of_the_range`.
- Efecto colateral corregido: el gráfico canónico con caches grandes
  mostraba silenciosamente datos viejos.

### 11.5 Ajustes del arnés y gaps declarados para feed público

- `LIMITS["entrada"]` 130→200 s: cadencia real del guion (tras la puerta
  FEED_SILENCE la señal llega con la vela M+3, ~2 fronteras, ~141 s
  reales); no fue compensar un fallo.
- Limpieza del directorio de sesiones de ensayo al inicio de cada corrida
  del arnés: el workdir efímero reutilizado acumulaba sesiones
  (SESSION_COUNT_UNEXPECTED). NO reutilizar el workdir sin esa limpieza.
- Gaps para público (declarados, NO acreditados): recepción Binance no
  acreditada (todo loopback); reparación REST inexistente en local;
  churn WS ~9 s tolerado; ciclo SSE de 10 s del adaptador en silencio.

### 11.6 Identidad de la evidencia y entrega utilizable (2026-10-28, cierre `efa7700`)

**Identidad de la evidencia (honesto):** la aceptación de §11.3 se ejecutó
sobre un árbol de trabajo SIN commitear encima de `90b3c9b`; el arnés
capturó `git_sha=90b3c9b` (HEAD al arrancar la corrida), que NO contiene la
implementación probada. Ese árbol sin commitear es exactamente el que hoy
publican los commits `b85f389` (backend live), `5c9f409` (frontend live) y
`557a1a8` (fix del explorador), con arnés y evidencia en `e775cfd`. No se
atribuye código nuevo a la base: la prueba valida el contenido publicado
en esos commits. SHA fuente del árbol final: **`efa7700`**.

**BUILD_ID literales:**
- BUILD_ID de la corrida de aceptación (build del arnés sobre el árbol sin
  commitear): `WDYGaWV_cUxErasQlce70`.
- BUILD_ID de la entrega en 3020 (build de producción de `next build`
  desde el árbol `efa7700`, sin cambios de código): `0-HCAplwLhRPpYHuuAPC2`.

**Estado de entrega (dashboard disponible, servicios verificados, nada
tocado):**
- Dashboard canónico `http://127.0.0.1:3020` activo (producción, BUILD_ID
  `0-HCAplwLhRPpYHuuAPC2`); sin sesiones de ensayo
  (`data/engineering-session/sessions/` sin sesiones).
- 8797 (pid 29096): servicio de ingeniería canónico
  (`scripts/engineering_session_service.py`, dir dedicado). Identidad
  verificada. Su pid-file (`data/engineering-session/service.json`,
  gitignored) estaba CORRUPTO por una corrida efímera posterior
  (pid 10112/puerto 18797); reconciliado al valor real (29096/8797) con el
  mismo schema que escribe el servicio: el proceso NO fue detenido ni
  reiniciado.
- 8792 (pid 33104): servicio de mercado preexistente, identidad verificada
  por línea de comandos: `market_stream_service.py --port 8792 --transport
  local --base-url ws://127.0.0.1:9999` → modo LOCAL (no Binance), sin
  consumidores. NO se usa como fuente de la sesión: el backend 8797
  apunta a su fuente configurada `http://127.0.0.1:8791` y no hay fallback
  silencioso.
- 8791 (fuente de mercado de 8797): CAÍDO. Arrancarlo exige
  `--transport local` (WS loopback propio, p. ej. productor del arnés) o
  `--transport public` (WS público de Binance, activación EXPLÍCITA no
  autorizada en este bloque). Sin fuente local activa, no hay 8791
  legítimo.

**Recorrido del operador (lo que hay hoy):**
1. URL: `http://127.0.0.1:3020/market-lab` (símbolo MINAUSDT, intervalo 1m,
   fijos en la página).
2. Opción: ventana de contexto — prefijo «A (ventana de contexto 20)» o
   «B (ventana de contexto 35)» (fija `entry_px` distinto con igual
   config; no es un escáner).
3. Botón: «Iniciar sesión» (`btn-iniciar-sesion`), con chip de servicio
   (`service-chip`) mostrando ready/down/error.
4. Fuente del contexto: cache local vía `/api/v1/market-series`
   (market-explorer, 0 peticiones upstream). Fuente de la ventana de
   operación: feed SSE del servicio de mercado que 8797 tiene configurado
   (`http://127.0.0.1:8791`).
5. Qué inicia el botón: (a) comprobar 8797 y, si está down, arrancar la
   instancia canónica vía BFF con identidad verificada; (b) crear la
   sesión en el backend con transporte `market_stream` (solo contexto en
   el create); (c) conducción autónoma: el backend avanza con los eventos
   SSE.
6. Condición actual explícita: con 8791 caído, la sesión se crea y la
   conducción queda bloqueada con error VISIBLE
   (`CONNECT_ERROR`/puertas de feed/`TRANSPORT_LOST`); no hay decisión
   falsa ni uso silencioso de 8792. Para una demo local viva hay que
   arrancar primero una fuente loopback propia (p. ej. el productor del
   arnés `scripts/engineering_live_local_acceptance.py`) y luego 8791 con
   `--transport local --base-url ws://<ese puerto>`.
7. Pendiente para Binance público (REQUIERE autorización y presupuesto
   separados): activación explícita de 8791 con `--transport public`,
   acreditación de recepción Binance real, reparación REST, tratamiento
   del churn WS ~9 s y del ciclo SSE de 10 s del adaptador.

**Próximo objetivo concreto (no es «todo completo»):** adaptar y verificar
este MISMO recorrido con datos públicos (8791 `--transport public`),
presupuesto y autorización separados. Sigue pendiente y NO está completo:
selector multiactivo, riesgo completo, paper prospectivo y estrategia
rentable.
