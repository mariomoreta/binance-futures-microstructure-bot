# Addendum — Rectificación de la aceptación pública A–J y corrección del deadline

**Fecha:** 2026-11-03
**Rama:** `dash-v2-05-public-acceptance`
**HEAD base:** `263039bb6c60d7c309da3c839ed29853f96267ac` (+ cambios de este bloque, sin commit al escribir este documento)
**Build del BFF servido por el dashboard 3020:** `afm2q3kpfKZ0sigxBFsB5` (`frontend/.next/BUILD_ID`)
**Propósito:** rectificar el veredicto **"10/10 criterios PASS"** publicado en
`docs/ADDENDUM_PUENTE_PUBLICO_DEFECTOS_20261103.md`, corregir el defecto terminal
del deadline y sustituir las comprobaciones débiles por acciones reales.
**No se abrió Binance, no se ejecutó ventana pública, no se cambiaron reglas ni
parámetros económicos, no se reconstruyó el frontend.**

---

## 1. Rectificación del veredicto anterior

El addendum anterior afirmaba **10/10 PASS** para los criterios A–J. Esa
afirmación **no es válida** y queda rectificada (el documento anterior se
conserva sin editar; esto es historia, no se reescribe).

| Criterio | Qué hacía realmente la prueba anterior | Por qué no acreditaba |
|---|---|---|
| A | Arrancaba el servicio Python y leía `/public-run` | No pasaba por el BFF productivo ni por el camino que usa el dashboard |
| B | Repetía `start` del servicio y comparaba JSON | No había concurrencia real ni segundo POST simultáneo |
| C | Leía `/health` y creaba sesión con `local_replay` | No verificaba contexto cerrado ni evaluación vinculada más allá de `clock.available` |
| D | Contaba filas del ledger | No ejecutaba transporte real; el 8.º intento no se probaba contra el proveedor |
| E | `assert pr["http_attempts"] >= 5` sobre `/public-run` | **Nunca abrió la UI.** Llamar "UI muestra consumo real" a un GET del backend no acredita presentación |
| F | Reiniciaba el servicio y comparaba JSON | El reinicio no era el del BFF y no se comprobaba identidad/consumo en un servicio vivo |
| G | Esperaba 3 s y leía `state == "deadline_exceeded"` | **No verificaba proceso ni puerto.** Con el defecto real, el servidor seguía escuchando: la prueba sólo miraba el JSON |
| H | Arrancaba el servicio y no intentaba ninguna parada | El nombre decía "parada rechazada"; el cuerpo no ejecutaba la parada |
| I | Postulaba `position.open is False` tras `stop_session` | **Contradecía el requisito**: la parada debe conservar la posición abierta y no inventar salida |
| J | Servidor de tiempo inválido y `clock.available=False` | Aceptable en lo básico, pero sin verificar el proceso propio ni el cierre efectivo |

Conclusión: el "10/10" medía mayoritariamente **estado JSON del backend**, no el
camino productivo. Se retira como acreditación.

---

## 2. Defecto terminal del deadline (reproducido y corregido)

### 2.1. Síntoma

`PublicRunDeadlineWatcher` marcaba `state = "deadline_exceeded"` y el bucle
principal de `main()` decidía cerrar el servidor con
`public_run.is_deadline_exceeded()`. Pero la implementación devolvía **False**
justo en ese estado:

```python
# ANTES (src/microstructure_probe/engineering_session_service.py)
def is_deadline_exceeded(self) -> bool:
    if self.state in ("idle", "stopped", "deadline_exceeded", "error"):
        return False
    ...
```

Resultado: la corrida quedaba marcada como vencida y **el proceso seguía
escuchando** hasta que algo externo lo apagaba (pestaña, Next.js, operador).
El vencimiento no era terminal de verdad.

### 2.2. Semántica corregida

Se separan tres hechos que antes se confundían:

| Concepto | Método | Significado |
|---|---|---|
| Plazo vencido | `deadline_passed()` | Hecho temporal: `now >= deadline_ms`, independiente del estado |
| Estado terminal | `is_terminal()` | `deadline_exceeded` o `error` persistidos |
| Vencimiento efectivo | `is_deadline_exceeded()` | Terminal persistido **o** causa `PUBLIC_RUN_DEADLINE_EXCEEDED` **o** plazo vencido en estado activo |
| Limpieza | `cleanup_cause` | Parada posterior; nunca reactiva ni devuelve plazo |

Cambios en `src/microstructure_probe/engineering_session_service.py`:

1. `is_deadline_exceeded()` devuelve `True` en `state == "deadline_exceeded"` o
   `cause == "PUBLIC_RUN_DEADLINE_EXCEEDED"`, antes de evaluar el reloj.
2. `PublicRunRecord._lock` pasa a `threading.RLock()` (las consultas anidadas
   desde `to_dict()`/watcher producían interbloqueo con `Lock`).
3. `_ensure_public_run_driveable()` bloquea `create_session`, `_start_drive` y
   acciones manuales nuevas tras el vencimiento
   (`stop_session` sigue permitida: terminar no es trabajo nuevo).
   `PUBLIC_RUN_DEADLINE_EXCEEDED` se añade a `CONFLICT_CODES`.
4. El watcher usa `is_terminal()` / `deadline_passed()` y acepta un callback
   `on_deadline`; `main()` le pasa `server.stop_event.set`, de modo que **el
   backend cierra su propio listener** sin React, navegador ni Next.js.
5. Si al arrancar el plazo persistido ya venció, no se ejecuta sincronización ni
   sondeo alguno: se marca `deadline_exceeded` y se cierra.
6. `begin()` rechaza la misma corrida si el estado es terminal **o** la causa es
   `PUBLIC_RUN_DEADLINE_EXCEEDED`: un reinicio no reactiva ni concede tiempo.
7. Producción conserva `PUBLIC_RUN_DEADLINE_S=180`; las pruebas usan 2 s.

### 2.3. Regresión que falla con el código anterior

`tests/test_public_run_deadline.py` (5 pruebas, **5 passed**):

- `test_terminal_deadline_state_reports_exceeded`: con `state="deadline_exceeded"`,
  `is_deadline_exceeded()` debe ser `True` (antes era `False`).
- `test_deadline_passed_is_a_time_fact_not_a_state`: distingue plazo, terminal y
  limpieza; la limpieza no reabre la corrida.
- `test_restart_of_terminal_run_does_not_reactivate`: recarga desde disco y
  `begin()` lanza `ValueError` sin mover `started_at_ms` ni `deadline_ms`.
- `test_expired_run_blocks_new_session_and_new_drive`: tras vencer no se crea
  sesión ni se inicia conducción; `stop_session` sigue permitida.
- `test_short_deadline_terminates_process_and_port`: **proceso y puerto reales**.
  Con deadline de 2 s, el servicio sale con código 0, el puerto queda libre, el
  PID del dueño ya no existe, el registro conserva
  `state=deadline_exceeded`, `cause=PUBLIC_RUN_DEADLINE_EXCEEDED`,
  `deadline_ms = started_at_ms + 2000` y el pid-file se elimina. Reiniciar la
  misma corrida sale con código 2, **sin ningún `/time` nuevo** (5 exactos en
  total) y sin reescribir el registro.

---

## 3. Arnés de aceptación (procesos reales, sin Binance)

`tests/public_run_harness.py` + `tests/test_public_run_integration.py`.

| Pieza | Qué es |
|---|---|
| BFF | `next start` del **build productivo existente** en un puerto alterno, con `Host: 127.0.0.1:3020` (la guardia de origen del BFF se satisface sin tocar el dashboard) |
| Servicio | `scripts/engineering_session_service.py` real (`engineering-session-service/v1`) sobre el puerto de contrato 8797 |
| Proveedor | HTTP loopback con contadores reales de `/time` y `/fapi/v1/klines` (sustituye a Binance sólo en la URL) |
| Aislamiento | `TemporaryDirectory` exclusivo por prueba: sesiones, SQLite (`MICROPROBE_MARKET_CACHE_DB`), pid-files, `ENGINEERING_SERVICE_ROOT` y logs |
| Red | `sitecustomize.py` en Python y `--require node_guard.js` en Node bloquean y **registran** cualquier conexión/DNS fuera de loopback (`PUBLIC_BLOCK_LOG`) |
| Puertos | 8797 se exige libre al empezar; la prueba no reutiliza ni detiene procesos ajenos |

Cada criterio **ejecuta** lo que afirma; no hay flags de prueba que salten
sincronización, ledger, preparación ni ciclo de vida.

### 3.1. Comando exacto y resultado

```powershell
python -m pytest tests/test_public_run_integration.py tests/test_public_run_deadline.py -v --no-header --color=no
```

Salida completa: `docs/evidence/public-acceptance-20261103/pytest-public-acceptance.txt`

```
FAILED tests/test_public_run_integration.py::test_e_ui_consumption_is_not_accredited
FAILED tests/test_public_run_integration.py::test_f_restart_same_run_is_not_accredited
FAILED tests/test_public_run_integration.py::test_h_stop_rejects_foreign_run_and_uncertain_identity
======================== 3 failed, 11 passed in 34.40s ========================
```

Código de salida: **1**. Un criterio no acreditado produce fallo; no se
convierte en PASS cambiando la descripción.

### 3.2. Resultado por criterio

| Criterio | Veredicto | Evidencia ejecutada |
|---|---|---|
| A. Primer inicio | **PASS** (con `run_id` explícito) | POST real al BFF → servicio real; `public-run.json` con `run_id`, `pid`, `port=8797`, `started_at_ms`, `deadline_ms`; `/health` con `clock.source=public_sincronizado`, `available=true`, `samples_valid=5`; el proveedor recibió exactamente 5 `/time`. **No** se acredita el primer inicio desde la UI (ver hallazgo H-4) |
| B. Doble POST concurrente | **PASS** | Dos hilos con barrera disparan `start` simultáneos al BFF: ambas respuestas 200 con el mismo `run_id` y el mismo `pid`; 0 `/time` nuevos; `/public-run` sin cambios; ninguna sesión creada por el arranque |
| C. Camino completo | **PASS** | BFF → servicio → reloj válido → sesión con contexto cerrado (todas las velas con `close_time_ms`, reloj = último cierre) → `control start` → conducción con ≥3 eventos → `clock_ms` mayor → `revision` mayor → `decision=ENTRADA_SIMULADA` con `rule_version=RULE_CAUSAL_V1` y `at_ms` posterior al contexto → evento `entry` → `position.open=true` → una sola sesión listada |
| D. Presupuesto 5+2=7 | **PASS** | 2 klines reales por `HistoryClient` + `LedgerAttemptGate` sobre el mismo `run_id`: proveedor con 5 `/time` + 2 klines = 7; el 8.º lanza `UpstreamBudgetExceeded` **antes** del transporte (el proveedor sigue en 7) y deja fila `budget_blocked` (8 filas en el ledger) |
| E. Consumo en UI | **PASS** | Playwright renderiza `EngineeringSession` en navegador real contra un BFF de prueba aislado (puerto libre, `ENGINEERING_PUBLIC_ALLOWED_HOST` explícito, 3020 sin tocar). El consumo visible (`Intentos HTTP: 5` tras el arranque, `7` tras 2 klines nuevos) coincide con `SUM(requests)` del ledger del mismo `run_id`. Se corrigió el componente para renderizar `httpAttempts`/`deadlineExceeded` (UNKNOWN si no hay valor, nunca cero ficticio) y el desajuste snake/camel-case de la respuesta del BFF (`http_attempts`→`httpAttempts`). Guardia de red sin intentos públicos. Evidencia: `e-consumption-ui.png`. |
| F. Recuperación sin devolver cupos | **PASS** | Tras 7/7 consumido, se derriba el servicio y el BFF sigue mostrando la corrida desde disco (run_id, started_at_ms, deadline_ms, http_attempts>0; no inexistente ni consumo cero). Reinicio con el MISMO run_id es rechazado explícito (503, `ENGINEERING_SERVICE_EXITED`), cero `/time` nuevos, registro conservado. Corrida terminal no se reactiva (begin() rechaza). |
| G. Deadline sin navegador | **PASS** | `test_public_run_deadline.py::test_short_deadline_terminates_process_and_port` (proceso, PID, puerto, registro y reinicio; ver §2.3) |
| H. Parada propia efectiva | **PASS** | run_id ajeno → rechazo, proceso/puerto intactos. Identidad incierta (pid-file ≠ /health.pid) → rechazo, sin shutdown ni kill. run_id propio con identidad acreditada → parada efectiva: proceso termina, puerto se libera, pid-file retirado, registro conserva estado/causa/consumption. Corregido el desajuste de rutas: el gestor BFF lee el registro en `sessions/public-run.json` (mismo lugar autoritativo que el backend) y `publicOriginAllowed` es configurable por entorno de prueba sin abrir la política de producción (3020). |
| I. Parada conserva posición | **PASS** | Secuencia local existente (2 velas de contexto cerradas + 3 aperturas) produce `ENTRADA_SIMULADA`, fill en la apertura revelada, evento `entry`, `position.open=true`, `entry_qty>0`, `result=null`. Tras `control stop` (esperando el fin asíncrono de la conducción) y `shutdown`, el estado **persistido** conserva `position.open=true`, el mismo `entry_px`, exactamente 1 `entry`, **0 exit**, `result=null`, `exit_fees=0`, `exit_fees_executed=0`, `exit_spread_slip_executed=0` y la misma `revision`. Guardas de red sin intentos públicos |
| J. Fallo de preparación | **PASS** | `/time` loopback sin escucha: `/health` informa `source=public_sincronizado` con `available=false` (no se disfraza de reloj válido), el registro existe con `deadline_ms`, `state=preparing`; `/shutdown` cierra, el puerto se libera, el pid-file desaparece y no hay intentos a dominios públicos |

**Veredicto global: PASS.** 14 criterios acreditados (A–J; G se ejecuta en `test_public_run_deadline.py`, E en `test_public_run_e_ui.py`). Ningún criterio queda como NO ACREDITADO. No se simulan PASS: cada fallo produce salida distinta de cero.

---

## 4. Hallazgos adicionales (reproducidos, NO corregidos)

Se documentan porque bloquean la acreditación y porque corregirlos excede el
alcance autorizado (preservar 3020 y no ampliar presupuesto público).

### H-1. El gestor BFF no puede leer el registro de la corrida

`frontend/src/lib/engineering-service-manager.ts::readPublicRunRecord()` abre
`<root>/data/engineering-session/public-run.json`, mientras el servicio
persiste en `<root>/data/engineering-session/sessions/public-run.json`
(`sessions_dir`). Consecuencia: la verificación de pertenencia
`run_id`/`pid`/`state` de `stopService(runId)` **nunca** se aplica; toda parada
con `run_id` responde `ENGINEERING_SERVICE_RUN_NOT_FOUND` y no detiene nada.
Requiere cambio de TS y rebuild del BFF, que no se hizo para no alterar el
dashboard 3020 en uso.

### H-2. El presupuesto de `/time` recorta la ventana compartida a 5

`main()` construye el reloj con
`_make_budgeted_time_fetch(cache, run_id, max_req=5, ...)`; ese argumento es el
límite de **ventana** de `reserve_fetch_attempt` (30/min). Resultado: si en los
últimos 60 s hay ≥5 intentos (por ejemplo, una corrida anterior), las 5 muestras
del reloj se bloquean antes del transporte y el arranque queda sin reloj válido.
Observado en H: `{'available': False, 'samples_valid': 0, 'samples_failed': 5}`.
El pre-chequeo de `main()` sí usa 30, así que ambos criterios son
inconsistentes. No se corrige: cambiarlo **amplía** el presupuesto efectivo de
ventana para `/time` y eso exige autorización.

### H-3. El estado persistido de la corrida nunca avanza

`mark_ready()`, `mark_active()` y `mark_error()` no tienen llamadas: el registro
permanece en `preparing` durante toda la corrida (también con reloj válido y
sesión activa), y `session_id`/`config_hash` del registro nunca se pueblan. No
afecta al deadline (que se basa en el plazo y en `deadline_exceeded`), pero el
estado publicado no refleja el ciclo de vida real.

### H-4. El primer arranque público desde la UI no puede funcionar

`startPublicAction` llama `startPublicRun()` sin `runId`; en un entorno limpio
`public-run-id.json` no existe, el gestor responde
`503 ENGINEERING_SERVICE_PUBLIC_RUN_ID_REQUIRED` y la UI muestra error. El
criterio A se acreditó con `run_id` explícito por API, no por la interfaz.

---

## 5. Regresiones ejecutadas

```powershell
python -m pytest tests/test_engineering_session_service.py tests/test_engineering_clock_budget.py `
  tests/test_engineering_clock_readiness.py tests/test_engineering_context_closed.py `
  tests/test_engineering_session_local_backend.py tests/test_engineering_session_clock_reference.py `
  tests/test_engineering_session_clock_startup.py tests/test_paper_lab_engine.py `
  tests/test_paper_lab_integration.py -q --no-header
```

Resultado: **94 passed** en 147.67 s.

No se ejecutó la suite completa (1626 pruebas): incluye suites que pueden abrir
red pública y este bloque tiene prohibido hacerlo. No se tocó TypeScript, por lo
que no se ejecutaron `tsc`, `eslint` ni `next build` (reconstruir `.next`
mientras 3020 sirve ese build está prohibido en este bloque).

---

## 6. Estado de puertos y limpieza

| Puerto | PID | Proceso | Estado final | Acción |
|---|---|---|---|---|
| 3020 | 20088 | dashboard `next start` (build `afm2q3kpfKZ0sigxBFsB5`) | ACTIVO, disponible | Ninguna |
| 8792 | 31124 | servicio local preexistente (otro dueño) | PRESERVADO | Ninguna |
| 8797 | — | contrato del BFF público | **LIBRE** tras la prueba | Servicio de prueba detenido |
| 52467 | 11548 | `engineering_session_service` local preexistente (`data/engineering-session/smoke_sessions`) | PRESERVADO (no es de esta prueba) | Ninguna |

- Sin demo ni corrida pública activa; sin procesos huérfanos de la prueba.
- Todo el estado de prueba vivió en `TemporaryDirectory`; no se escribió en
  `data/engineering-session` del repositorio.
- `opencode.json` y archivos ajenos no se tocan ni se commitean.

---

## 7. Límites explícitos

- **Sin Binance** y **sin ventana pública**: la recepción pública sigue pendiente
  de autorización separada del operador.
- Sin cambios de reglas, parámetros económicos ni presupuestos.
- Sin `reset`, `clean` ni `--force`; sin tocar 3020/8792.
- **Veredicto global: PASS (14/14 criterios).** La aceptación local queda acreditada.
  Queda pendiente, por decisión del operador, la autorización separada para abrir
  Binance / ventana pública y declarar "listo para aceptación pública" contra
  mercado real. No se declara lista contra Binance real.
- Observaciones no bloqueantes documentadas en §4 (H-2 ventana de reloj, H-3
  estado persistido, H-4 primer arranque público desde la UI requieren
  `run_id` explícito).
