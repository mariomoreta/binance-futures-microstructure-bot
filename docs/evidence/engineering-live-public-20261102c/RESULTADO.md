# RESULTADO — Ventana pública única `eng-run-public-20261102c`

Fecha: 2026-11-02 · Base: `a11c02e` (`diag/recorrido-local-4f4273c`) ·
Arnés: `scripts/engineering_live_window.py` SHA-256 `97bec590dc46aadde60b213afe5fdf8ae684b5dab088f59f4b6fefeab3bead9b`

## Veredicto global: **FAIL (contrato de aceptación del recorrido completo) — EVALUACION_NO_ALCANZADA**

El arnés reportó su veredicto interno **PASS** (sus checks exigidos, todos verdaderos),
pero los criterios de aceptación de esta ventana NO se acreditaron: la sesión
nunca procesó un solo evento (`eventos_procesados=0`), no hubo evaluación
(contador 0, `result=null`), ni decisión con motivo. La cadena se rompió entre el
hub SSE del servicio de mercado y el adaptador del servicio de ingeniería.

## Lo acreditado (evidencia vinculada)

| Criterio | Estado | Evidencia |
| --- | --- | --- |
| Sesión creada con identidad | ✔ | `session_id=PL-MINAUSDT-LONG-1793669229096-9d935300`, `config_hash=4a339c046cc3ad63`, regla `RULE-CAUSAL-V1` fija pre-conexión (`checks.config_validada`) |
| Referencia temporal válida (reloj público, sin fallback local) | ✔ | `clock_readiness` → `reloj_listo` a 1793669228298 con `source=public_sincronizado`, offset −7.125 ms, RTT 360 ms, 5/5 muestras válidas; transiciones completas en `evidence.json` |
| Contexto cerrado no-futuro (camino corregido en a11c02e) | ✔ | `contexto`: 600 velas, 300/símbolo, ventanas [1793651220000, 1793669160000], último cierre admitido 1793669219999 ≤ referencia 1793669228291; `contiguo=true`, `alcanza_ultima_cerrada=true` por símbolo; `parse_diag`: REST filas con cierre posterior excluidas (`cierre_no_ocurrido:0`), 0 filas almacenadas usadas, REST usadas 2/2 |
| Contexto suficiente, sin días de caché intermedia | ✔ | `contexto.motivo=null`; ventana derivada solo de la última vela cerrada; no_descarga intermedia |
| Presupuestos y ledger compartidos por run_id | ✔ | Ledger `execution_id=eng-run-public-20261102c`: exactamente 7/7 filas (5× `fapi_time` + 2× klines, `limit=300`, `endTime=1793669219999`, 0 reintentos, 0 fallos, 0 `budget_blocked`); REST del arnés 2 |
| WS pública saludable, con·límites | ✔ | `recorrido_servicio`: 237 mensajes recibidos/parsed, **3 cierres nuevos admitidos POR EL HUB** (BTCUSDT 2, MINAUSDT 1), 237 frames SSE enviados; reconexiones WS 0; consumidores máx 2 |
| Un cierre NUEVO admitido **por la sesión** | ✘ | `events=[]` (cursor 1), `eventos_procesados_final=0` |
| Avance de T por evento + evento disparador + evaluación con decisión y motivo | ✘ | Única transición de revisión: rev 0 (clock 1793669219999) → rev 2 a 1793669342370 con `clock_ms=1793669280000` y `eventos_procesados=0`; sin motivo registrado → cambio de clock **causa UNKNOWN** |
| Limpieza y preservación | ✔ | Procesos propios terminados sin fallos; 8791/8797/18799/18800 libres post-corrida; pid-files propios eliminados; pid-file 8792 intacto (pid 31124); DBs canónicas sin cambios (`historical.db` d8930ec5…, `microprobe.db` 6ea98cab…); dashboard 3020 disponible |

Posición: abierta=false, sin fills ni salidas inventadas; estado final de sesión
`sin_iniciar` (conducción detenida sin fabricar cierre, marca no realizada).

## Clasificación de la causa

- **No es fallo upstream de Binance**: la WS pública entregó 237 mensajes sin reconexiones y el hub parseó 3 cierres nuevos.
- **No es el defecto de contexto corregido en a11c02e**: el contexto cerrado funcionó exactamente como en tests locales (600 velas contiguas, no futuro, REST 2).
- **Es un fallo del arnés/servicios locales en el adaptador SSE de ingeniería**:
  `adaptador_ingenieria` = frames 60/237, desconexiones 5, reconexiones 5,
  `last_error=TimeoutError: timed out`, `connected_at_ms=1793669374186`
  (~147 s después de `started_at_ms=1793669229149`). Casi todo el tiempo de
  ventana el adaptador no estuvo conectado; los 60 frames llegados al final
  tampoco produjeron `eventos_procesados>0` (razón no registrada → UNKNOWN).
- `SIN_ENTRADA` **no aplica**: no hubo eventos procesados con los cuales
  abstenerse con motivo; la ausencia es de cadena, no de decisión.

## Presupuesto real

- HTTP upstream total: 7/7 usados (5 `/time` + 2 klines), sin reintentos.
- Velas por consulta: 300 (límite respetado). WS: 1 combinada, 0 reconexiones.
- SSE: 2 consumidores simultáneos (≤3). Deadline: adquisición 174.5 s dentro de 180 s (total 180.4 s incl. limpieza).
- Escrituras en `historical.db`/`microprobe.db`: 0 (hash-igualados antes/después).

## Estado final post-corrida

Puertos 8791/8797/18799/18800 libres; 8792 (pid 31124) y 3020 intactos y
disponibles; sin procesos/pid-files propios restantes; `opencode.json` y archivos
ajenos preservados; sin relanzamientos; comando exacto en `command.txt`.

## Anexos

- `preflight.json` — verificación previa sin red pública.
- `command.txt` — comando exacto ejecutado.
- `evidence.json` — evidencia completa del arnés (veredicto arnés PASS).
- `summary.json` — consolidación con veredicto global FAIL.
- `post_state.json`, `ledger-run-id.json` — presupuesto y estado final.
- `sessions/paper-lab-sessions/PL-…-9d935300.json` — sesión (events vacíos).
- `service_logs/*.log` — stdout/stderr de ambos servicios (sin errores en stderr).
- `harness-stdout.log` (UTF-16LE, PowerShell redirect), `harness-stderr.log` (vacío).
- Lectura legible: `harness-stdout-utf8.txt`.

## Siguiente

Investigar el adaptador SSE del servicio de ingeniería (por qué conecta a los
~147 s y por qué TimeoutError se repite 5 veces) y por qué los 60 frames tardíos
no incrementaron `eventos_procesados`. Nueva ventana pública solo con
autorización explícita y run_id NUEVO.
