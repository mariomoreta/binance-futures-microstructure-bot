# Preparación reproducible de UNA medición económica — 2026-11-15

**Autorización humana (2026-11-15):** «PREPARACIÓN ACOTADA — UNA MEDICIÓN
ECONÓMICA REPRODUCIBLE». Cubre **solo** preparación local, persistencia
mínima, pruebas loopback y actualización del presupuesto/propuesta.

**NO autorizado y NO realizado:** Binance, adquisición pública, capturas,
órdenes, ventanas nuevas, relanzamientos. `exp-v2-ventana-2-20261112a` **no**
se reutiliza ni se relanza. No se creó el directorio de ninguna corrida
pública: el presupuesto se calculó en una **ruta de preparación separada**.

**Rama:** `research/universe-liquidez-v1` · **Base publicada conocida:**
`11969f95b9f2f9869e8ec3371c521f07586fe5e6` (commit concurrente del usuario,
integrado por *fast-forward*; contiene `5362baf`, la corrección temporal ya
publicada, que **se conserva sin reimplementar**).

---

## 1. Qué se resuelve

La ventana cerrada no conserva los datos necesarios para reconstruir su
resultado económico: el ledger HTTP solo guarda `response_sha256` y
`response_item_count` (un hash no sustituye a las velas) y la serie 1 m
capturada es de `aggTrade`, no la serie `klines` del venue. Este bloque
**añade la persistencia mínima que faltaba** y deja preparada **una** ventana
futura cuyos resultados se pueden reconstruir **offline**, sin volver a
consultar al proveedor.

| | Antes (publicado) | Después (preparado) |
|---|---|---|
| Cuerpo de la consulta klines de trayectoria | no persistido (solo hash) | persistido íntegro en `consultas_klines.jsonl` |
| Reconstrucción offline de la operación | imposible | `scripts/research_operativo_replay.py` (adaptador y motores existentes) |
| Verificación cuerpo ↔ hash ↔ ledger | imposible | hash del cuerpo + fila del ledger + parámetros exactos |
| Presupuesto | sin bytes de cuerpos | con los bytes de cuerpos y sus metadatos |

**No cambia** la regla operativa: ni selección, ni dirección, ni señal, ni
fill, ni stop, ni horizonte, ni notional, ni capacidad, ni prioridad, ni
costes, ni contabilidad de funding. La baseline es la de §3.

## 2. Implementación (mínima, sobre el camino productivo)

| Fichero | Cambio |
|---|---|
| `src/microstructure_probe/history_client.py` | El cliente captura el **cuerpo crudo** de la última respuesta exitosa (`last_response_body`, `last_response_sha256`, `last_response_status`), invalidado al iniciar cada petición para que un fallo nunca deje un cuerpo anterior. **No hay cliente nuevo.** |
| `scripts/research_pilot.py` | `ResearchPilot._persistir_consulta_klines` persiste cada respuesta de trayectoria en `consultas_klines.jsonl` (JSONL con el `PilotStore` y la `RunStorageBudget` existentes); se contabiliza en el almacenamiento total, en el resumen y en el manifiesto; el manifiesto publica también la configuración operativa congelada. |
| `scripts/research_operativo_replay.py` | **Nuevo.** Reconstrucción offline: lee lo persistido, reutiliza `OperativoAdapter`, `paper_lab_engine` y `backtest_offline`, y contrasta ejecución ↔ replay. Sin red, sin cliente, sin motor, sin servicio ni base de datos nuevos. |
| `tests/test_operativo_replay_offline.py` | **Nuevo.** Aceptación con CLI real, proveedores loopback, reloj manual y almacenamiento temporal. |
| `tests/test_research_pilot.py` | Parámetro `moves` (aditivo) en el arnés y expectativas de almacenamiento actualizadas. |

### 2.1 Registro persistido por respuesta

Una fila de `consultas_klines.jsonl` (`kind=consulta_klines_trayectoria`):

| Campo | Contenido |
|---|---|
| `run_id` | identidad de la corrida |
| `observation_id`, `observaciones` | vínculo con la(s) observación(es) que usaron esos datos |
| `symbol`, `interval` | símbolo e intervalo consultados |
| `params` | parámetros **exactos** (`symbol`, `interval`, `startTime`, `endTime`, `limit`) |
| `endpoint` | URL real servida (incluye la query) |
| `solicitado_ms`, `adquirido_ms` | instante de solicitud y de adquisición |
| `http_status` | estado HTTP recibido |
| `cuerpo` | **cuerpo recibido** (texto exacto) |
| `cuerpo_sha256`, `cuerpo_bytes` | hash verificable y tamaño del cuerpo |
| `filas` | número de velas devueltas |
| `reloj_ms`, `decision_ms` | corte causal de la consulta e instante de decisión |
| `consulta_numero` | nº de consulta de esa observación (1 o 2) |
| `nota` | separa conceptualmente la información disponible en T de las velas posteriores |

**Separación conceptual exigida:** el cuerpo incluye velas posteriores a T
(son la trayectoria que resuelve la operación). La **referencia de entrada**
sigue usando solo la vela plenamente cerrada en T (`close_time <= decision_ms`)
y la reconstrucción aplica el **mismo corte causal** (`reloj_ms`) que la
ejecución. No se rellenan huecos ni se reconstruye OHLC desde retornos, libro o
`aggTrade`.

### 2.2 Mecanismo de reserva (sin ampliar cupos)

El cuerpo se escribe con el `PilotStore` y la `RunStorageBudget` existentes:
la reserva se hace **antes** de tocar disco y, si no cabe, la escritura se
rechaza, la corrida se detiene con `stop_reason = "presupuesto_bytes"` y **no
se amplía ningún tope**. Si el cuerpo no está disponible, **no se persiste
una fila**: no hay reconstrucción inventada.

## 3. Baseline de continuación (aclaración, no cambio de estrategia)

La regla evaluada es una **baseline de continuación**, no una estrategia
nueva:

- **Dirección** según el signo del movimiento de 24 h
  (`derivar_direccion_desde_movimiento`).
- **Referencia actual** procedente **del mismo cierre** que compara la
  condición direccional (cierre de la vela 1 m plenamente cerrada en T).
- **Libro y flujo** actúan principalmente como **requisitos de calidad y
  contexto** de la observación.
- **No acredita** detección de patrones, anticipación de explosiones ni
  reversión.

## 4. Demostración local de reproducibilidad (CLI real + loopback)

Recorrido: selección → observación → consulta → adaptador → motor →
persistencia, con **CLI productivo como subproceso**, proveedores HTTP/WS
**loopback** (que respetan `openTime >= startTime`), reloj manual y
almacenamiento temporal.

| Comprobación | Resultado observado |
|---|---|
| Cuerpos recibidos y persistidos | `consultas_klines.jsonl` con ≥ 5 respuestas por corrida |
| Cuerpo ↔ hash | `sha256(cuerpo) == cuerpo_sha256` y `cuerpo_bytes` exacto en todas las filas |
| Vínculo con el ledger HTTP | cada hash persistido aparece en `http_requests.jsonl` con los **mismos** `params` |
| Vínculo con las observaciones | `observation_id` presente en `observaciones.jsonl`; símbolo coherente |
| Respuesta real del proveedor | primera vela del cuerpo = precio del proveedor simulado (error < 1e-8) |
| Entradas y salidas **LONG** y **SHORT** | 1 admitida + 4 rechazos por capacidad en cada dirección; fill en el open posterior a T; salida por horizonte ejecutada |
| Capacidad y orden determinista | 1 posición simultánea; entra la primera símbolo por orden determinista (`AAAUSDT`) |
| Proveedores detenidos | el puerto HTTP del proveedor queda **cerrado** antes del replay |
| Replay **solo** con lo guardado | `scripts/research_operativo_replay.py` reconstruye desde los ficheros, sin red |
| Equivalencia ejecución ↔ replay | **EQUIVALENTE**: 5/5 observaciones coincidentes, 0 diferencias, 0 limitadas (LONG, SHORT y funding observado) |
| Funding observado (método A) | el estado final de la contabilidad (`ACREDITADA`) y su `neto_estado` se reproducen desde `funding_adquisicion.jsonl` |
| Fichero ausente | **LIMITACION** (código 3): 5 observaciones limitadas, **0** operaciones inventadas |
| Cuerpo corrupto | **LIMITACION** (código 3): hash incoherente detectado, observación limitada y diferencia explicada por la propia limitación |

Campos contrastados uno a uno entre ejecución y replay: `decision`,
`direction`, `qty`, `entry_px`, `entry_ms`, `stop_px`, `exit_px`, `exit_ms`,
`exit_reason`, `exit_executed`, `open_at_end`, `gross_pnl`, `fees`,
`spread_slip`, `funding`, `net_pnl`, `funding_estado`, `neto_estado`,
`neto_motivo`, `contabilidad_funding_estado`, `config_hash` y
`engine_version`. Los **timestamps de publicación** pueden diferir y no se
comparan.

### 4.1 Códigos observados

| Prueba | Resultado |
|---|---|
| `python -m pytest tests/test_operativo_replay_offline.py -q` | **3 passed** (`aceptacion_replay.txt`) |
| `python -m pytest tests/test_pilot_operativo_consulta_temporal.py tests/test_operativo_cli_integrado.py tests/test_operativo_adapter_local.py tests/test_operativo_funding_espera_contable.py tests/test_pilot_monitor_observabilidad.py tests/test_research_pilot.py -q` | **75 passed** |
| `python -m unittest tests.test_history tests.test_history_client_budget tests.test_budget_scope_shared` | **46 OK** (dos ejecuciones limpias consecutivas) |
| `python -m unittest tests.test_engineering_clock_budget tests.test_engineering_clock_readiness` | **32 OK** |
| `python -m unittest tests.test_public_run_integration tests.test_market_explorer` | **42 OK** |

**Observación honesta:** una primera ejecución de la tercera fila mostró
`FAILED (failures=4)` de forma **no reproducible**: las dos ejecuciones
inmediatamente posteriores pasaron **46/46** y la cuarta fila no se vio
afectada. Esas pruebas levantan procesos y transportes reales con carreras de
tiempo; el cambio en `HistoryClient` es **aditivo** (tres atributos) y no
altera la ruta de petición. Se deja constancia en lugar de ocultarlo; no se
afirma que la suite sea estable bajo carga.

No se repitieron pruebas generales ajenas al bloque.

## 5. Presupuesto efectivo (recalculado, sin red, ruta separada)

Calculado con `--budget-only` **a través del lanzador** (forma final del
comando, incluidas `--work-timeout-seconds 40200 --shutdown-grace-seconds
300`), **sin red**, en
`C:\proyectos\binance-futures-data\_presupuesto\exp-v2-ventana-3-20261115a-preparacion`
(**no** es el directorio de la corrida). Código real **0**, `stderr` vacío,
gate **13/13**, `cabe_en_limites: true`.

| Magnitud | Publicado (ventana 2) | Nuevo (preparación) | Techo |
|---|---|---|---|
| Intentos HTTP con reservas | 1 334 | **1 334** | 2 000 |
| Peso REST con reservas | 3 752 | **3 752** | 5 000 |
| Reintentos | 50 | **50** | 50 |
| Almacenamiento previsto | 4 696 872 B | **9 016 872 B** | 134 217 728 B |
| Almacenamiento reservado máx. | 52 043 648 B | **56 363 648 B** | 134 217 728 B |
| Margen reservado | 82 174 080 B | **77 854 080 B** | — |
| Cuerpos klines previstos | — | **4 320 000 B** (480 respuestas × 9 000 B) | — |
| Captura / settle / espera contable | 3 600 / 4 200 / 32 400 s | **3 600 / 4 200 / 32 400 s** | 40 200 s de trabajo |
| Cierre (margen del lanzador) | 300 s | **300 s** | total 40 500 s |

**Diferencias frente al presupuesto publicado: 10, todas del bloque de
almacenamiento** (los cuerpos persistidos y sus metadatos). No cambia ninguna
consulta, peso, reintento, límite WS, duración, exposición ni cupo. Detalle
íntegro en `presupuesto_comparacion.json`; artefactos del lanzador en
`presupuesto_launcher.json`, `presupuesto_estado_lanzador.json`,
`presupuesto_cierre.json`, `presupuesto_exit_code.txt`,
`presupuesto_stdout.txt` y `presupuesto_stderr.txt` (publicados con extensión
`.txt` porque `.gitignore` excluye `*.log`).

## 6. Propuesta (no ejecución)

La propuesta de **UNA** ventana futura queda en
[PROPUESTA](../../evidence/exp-v2-ventana-3-20261115a-propuesta/PROPUESTA.md):
pregunta económica exacta, denominadores y comparación por rol/ciclo,
tratamiento de los rechazos por capacidad, netos `COMPLETO` separados de
`CONDICIONADO`, criterios de insuficiencia, presupuesto recalculado, comando
completo aceptado por el parser, `run_id` **nuevo y verificado no utilizado**
(`exp-v2-ventana-3-20261115a`), ubicación de datos y enlace del monitor
existente. **No se crea el directorio de la corrida ni se ejecuta.**

## 7. Lo que este bloque NO hace

No abre mercado, no hace capturas, no relanza ni reutiliza
`exp-v2-ventana-2-20261112a`, no crea el directorio de una corrida pública, no
amplía duración, exposición, consultas ni cupos, no cambia estrategia,
selección, funding, contabilidad ni presupuestos económicos, no añade
indicadores, on-chain, GARCH, futuros con vencimiento, infraestructura ni
servicios, no toca el dashboard 3020 ni el servicio 8792, no lee ni modifica
`opencode.json` ni archivos ajenos, y no altera las DBs canónicas ni los
datasets originales.

## 8. Índice de la evidencia

| Artefacto | Contenido |
|---|---|
| `aceptacion_replay.txt` | salida de la aceptación nueva (3 passed) |
| `replay_long.json` / `replay_short.json` | informes de replay: **EQUIVALENTE** (5/5) |
| `replay_funding.json` | informe de replay con funding observado: **EQUIVALENTE** (5/5) |
| `replay_datos_ausentes.json` | **LIMITACION** con fichero de cuerpos ausente |
| `replay_datos_corruptos.json` | **LIMITACION** con cuerpo corrupto (hash incoherente) |
| `presupuesto.json` | presupuesto recalculado (gate 13/13) |
| `presupuesto_comparacion.json` | comparación exhaustiva con el presupuesto publicado (10 diferencias, todas de almacenamiento) |
| `presupuesto_launcher.json`, `presupuesto_estado_lanzador.json`, `presupuesto_cierre.json`, `presupuesto_exit_code.txt`, `presupuesto_stdout.txt`, `presupuesto_stderr.txt` | evidencia del lanzador en la ruta de preparación (`.txt` porque `.gitignore` excluye `*.log`) |
| `hashes.json` | hash SHA-256 de cada artefacto de esta evidencia |
