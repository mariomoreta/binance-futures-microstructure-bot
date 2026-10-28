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

### 9.1 Arranque manual del servicio — limitación declarada

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

### 9.3 Defecto abierto del panel de flujo

`ERR_INCOMPLETE_CHUNKED_ENCODING` en `/api/v1/market-flow/stream`
(SSE del panel de flujo, panel ajeno a este bloque) se mantiene como
DEFECTO ABIERTO: impacto observado = el stream del panel se aborta en
algunos re-render/re-poll; no se le atribuyen fallos de esta sesión (el
acceso y la conducción terminaron sin errores propios).

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
- `tests/test_engineering_session_service.py`; `tests/test_paper_lab_engine.py` (regresión);
  `frontend/src/test/engineering-session.test.tsx`; `frontend/src/test/session-lab.test.ts`.
- Código: `src/microstructure_probe/engineering_session_service.py`.
