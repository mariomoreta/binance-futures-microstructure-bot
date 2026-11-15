# Corrección del veredicto del replay — 2026-11-15 (local, sin mercado)

**Autorización humana (2026-11-15):** «CORRECCIÓN LOCAL ACOTADA — EVITAR
FALSOS POSITIVOS DE EQUIVALENCIA». Cubre corregir y probar localmente tres
defectos de `scripts/research_operativo_replay.py`. **NO autorizado y NO
realizado:** Binance, consultas públicas, capturas, órdenes, relanzamientos
ni ventanas nuevas.

**Rama:** `research/universe-liquidez-v1` · **Base publicada conocida:**
`12024146ddcecae0064c1be91cc740bbe0242613`.

---

## 1. Qué se resuelve

El replay publicado declaraba **EQUIVALENTE (código 0)** ante alteraciones
que invalidan la equivalencia. Tres defectos, reproducidos **antes de
corregir** contra el código publicado:

| # | Defecto | Causa |
|---|---|---|
| 1 | Un desplazamiento temporal de `entry_ms` en +1000 ms no se detectaba | la comparación usaba una **tolerancia relativa** (`1e-9 × escala`) para **todos** los campos numéricos: sobre un timestamp en ms de ~1,7×10¹² la tolerancia era ~1735 ms |
| 2 | Cambiar `run_id`, `symbol` y `startTime` de las consultas persistidas (cuerpo y hash intactos) no se detectaba | el vínculo con el ledger solo comprobaba la **existencia** del hash; el hash del cuerpo por sí solo no prueba qué petición lo produjo |
| 3 | Eliminar `operativo_config` del manifiesto no se detectaba | el replay reconstruía con `OperativoConfig()` **por defecto** de forma silenciosa |

## 2. Reproducción antes de corregir (código publicado `12024146`)

Procedimiento (`reproducir_defectos.py`): una corrida real del CLI
productivo con proveedores **loopback** (sin mercado), proveedores
**detenidos**, y copias **independientes** del dataset sintético. Se extrae
el replay publicado de Git (`replay_publicado.py`, copia UTF-8 del fichero
en `12024146`) y se ejecuta sobre cada copia:

| Caso | Alteración | Veredicto observado (antes) |
|---|---|---|
| control | copia intacta | **EQUIVALENTE (0)** |
| A | `entry_ms` del resultado de ejecución +1000 ms | **EQUIVALENTE (0)** ← falso positivo |
| A-manif | A con el hash del manifiesto recalculado (integridad «ok») | **EQUIVALENTE (0)** ← falso positivo |
| B | `run_id`→otra corrida, `symbol`→`ZZZUSDT`, `params.startTime` +123 ms (cuerpo y hash conservados) | **EQUIVALENTE (0)** ← falso positivo |
| B-manif | B con el hash del manifiesto recalculado | **EQUIVALENTE (0)** ← falso positivo |
| C | `operativo_config` eliminado del manifiesto | **EQUIVALENTE (0)** ← falso positivo |

## 3. Qué cambia (solo el replay; la persistencia, los motores, la estrategia y el presupuesto quedan intactos)

1. **Comparación por tipo de campo.** Timestamps en ms (`decision_ms`,
   `entry_ms`, `exit_ms`), identificadores, decisiones, estados y textos:
   igualdad **exacta**. Booleanos: igualdad exacta **y de tipo** (`True`
   nunca es 1). Valores económicos decimales: **única** tolerancia,
   **absoluta y justificada** (`1e-9` USDT, ruido de representación), que no
   se aplica a los campos anteriores. El desplazamiento temporal se
   detecta como **DIFERENCIAS (4)** cuando los archivos son íntegros y sus
   valores difieren, y como **LIMITACION (3)** cuando la alteración rompe la
   integridad acreditada.
2. **Identidad y procedencia de cada consulta** (antes de usarla): `run_id`
   contra la corrida del manifiesto; observación correspondiente (existente
   y apta); símbolo e intervalo; `decision_ms`; **parámetros exactos** de la
   petición; y cruce completo con la **respuesta del ledger HTTP** (hash,
   endpoint, parámetros, símbolo, intervalo, estado HTTP, instantes de
   solicitud/adquisición, bytes y nº de filas). Los campos, hashes e
   identificadores ya persistidos se reutilizan: no hay formato, servicio ni
   sistema de trazabilidad nuevos.
3. **Integridad acreditada.** El sha256 real de cada fichero necesario se
   comprueba contra el publicado en el manifiesto (`observaciones.jsonl`,
   `resultado_operativo.jsonl`, `http_requests.jsonl`,
   `consultas_klines.jsonl`, `funding_adquisicion.jsonl`, `resumen.json`).
   Fichero alterado → `integridad_fichero_rota`; manifiesto sin hashes →
   `integridad_no_publicada`.
4. **Configuración operativa obligatoria.** Sin `operativo_config`, con
   campos necesarios ausentes o con tipos/valores incoherentes: **no se
   reconstruye nada** (nunca valores por defecto silenciosos) y se declara
   `config_operativa_ausente` / `_incompleta` / `_invalida`. Además, el hash
   de la configuración reconstruida se contrasta con el `config_hash`
   publicado en la ejecución → `config_hash_no_coincide`.
5. **Denominador completo.** El informe publica `denominador`
   (observaciones aptas / reconstruidas / limitadas, consultas persistidas /
   acreditadas / rechazadas): ninguna observación apta desaparece de la
   comparación sin quedar como **limitada** con su motivo.
6. **Veredicto estricto.** Ya no existe `EQUIVALENTE_CON_LIMITACIONES`.
   **Cualquier** limitación (de integridad, procedencia o configuración) →
   **LIMITACION (3)**. Diferencias con evidencia válida y acreditada →
   **DIFERENCIAS (4)**. EQUIVALENTE (0) exige integridad acreditada,
   procedencia acreditada de todas las consultas, configuración verificada,
   denominador completo y resultados idénticos.

## 4. Tabla antes/después (mismo dataset, mismas mutaciones)

| Caso | Antes (`12024146`) | Después (corregido) | Motivos después |
|---|---|---|---|
| control | EQUIVALENTE (0) | **EQUIVALENTE (0)** | — |
| A (integridad rota) | EQUIVALENTE (0) | **LIMITACION (3)** | `integridad_fichero_rota` |
| A-manif (integridad ok) | EQUIVALENTE (0) | **DIFERENCIAS (4)** | `entry_ms` desplazado detectado campo a campo |
| B (integridad rota) | EQUIVALENTE (0) | **LIMITACION (3)** | `consulta_run_id_distinto`, `consulta_simbolo_distinto`, `consulta_parametros_distintos`, `consulta_discrepancia_ledger`, `integridad_fichero_rota` |
| B-manif (integridad ok) | EQUIVALENTE (0) | **LIMITACION (3)** | `consulta_run_id_distinto`, `consulta_simbolo_distinto`, `consulta_parametros_distintos`, `consulta_discrepancia_ledger` — **solo** las comprobaciones de identidad: la integridad no enmascara el defecto |
| C | EQUIVALENTE (0) | **LIMITACION (3)** | `config_operativa_ausente` |

Detalle completo en `resultados_publicado.json` (antes) y
`resultados_corregido.json` (después).

## 5. Comandos y códigos observados

| Comando | Resultado |
|---|---|
| `python -m pytest tests/test_operativo_replay_offline.py -q` | **7 passed** (3 positivos conservados + 4 pruebas negativas nuevas) — `aceptacion_corregida.txt` |
| `python -m pytest tests/test_pilot_operativo_consulta_temporal.py tests/test_operativo_cli_integrado.py tests/test_operativo_adapter_local.py tests/test_operativo_funding_espera_contable.py tests/test_pilot_monitor_observabilidad.py tests/test_research_pilot.py -q` | **75 passed** — `regresiones_pytest.txt` |
| `python -m unittest tests.test_history tests.test_history_client_budget tests.test_budget_scope_shared` | **46 OK** — `regresiones_unittest_history.txt` |
| `python -m unittest tests.test_engineering_clock_budget tests.test_engineering_clock_readiness` | **32 OK** — `regresiones_unittest_engineering.txt` |
| `python -m unittest tests.test_public_run_integration tests.test_market_explorer` | **42 OK** — `regresiones_unittest_public.txt` |

**Nota de entorno (unittest):** en una shell nueva, los suites
`unittest` de la tabla exigen `PYTHONPATH=src` (los módulos de `tests` que
importan `microstructure_probe` directamente no hacen el arranque de `sys.path`
que hacen los scripts de `scripts/`). Los tres suites se ejecutaron con
`PYTHONPATH=src` y pasaron completos; la ausencia de esa variable produce
`ModuleNotFoundError` **al importar** (no es un fallo de pruebas). En el
bloque anterior la misma tabla pasó sin registrarse la variable; se documenta
aquí para reproducibilidad.

## 6. Positivos conservados (mismo comportamiento que antes)

- **LONG** y **SHORT** con CLI real y proveedores loopback: replay
  **EQUIVALENTE (0)**, 5/5 coincidentes.
- **Funding observado (método A)**: la contabilidad diferida se reconstruye
  desde `funding_adquisicion.jsonl` y el estado final coincide.
- **Capacidad compartida**: 1 admisión + 4 rechazos por capacidad
  reproducidos; el orden determinista se conserva.
- **Replay sin proveedores activos**: funciona solo con lo persistido.
- Fichero ausente y cuerpo corrupto → **LIMITACION (3)**, sin resultados
  inventados.

## 7. Negativos detectados (pruebas nuevas, separadas)

| Prueba nueva | Comprobación que detecta SU defecto | Veredicto |
|---|---|---|
| timestamp desplazado (integridad rota) | integridad contra el manifiesto | LIMITACION (3) |
| timestamp desplazado (integridad ok) | igualdad exacta de `entry_ms` | DIFERENCIAS (4) |
| `run_id` distinto | `consulta_run_id_distinto` | LIMITACION (3) |
| símbolo distinto | `consulta_simbolo_distinto` | LIMITACION (3) |
| intervalo distinto | `consulta_intervalo_distinto` | LIMITACION (3) |
| parámetros distintos (`startTime`) | `consulta_parametros_distintos` + cruce con el ledger | LIMITACION (3) |
| vínculo con el ledger roto | `consulta_sin_vinculo_ledger`; la observación afectada queda limitada y **no** se reconstruye | LIMITACION (3) |
| configuración operativa ausente | `config_operativa_ausente` | LIMITACION (3) |
| configuración incompleta (`fee_bps` ausente) | `config_operativa_incompleta` | LIMITACION (3) |
| configuración inválida (tipo incoherente) | `config_operativa_invalida` | LIMITACION (3) |
| configuración incoherente con el hash publicado | `config_hash_no_coincide` | LIMITACION (3) |
| ledger HTTP ausente | `ledger_ausente` + `consulta_sin_vinculo_ledger`; 0 operaciones reconstruidas (antes: código 0) | LIMITACION (3) |
| `resultado_operativo.jsonl` ausente | `resultados_ausentes` + `sin_resultado_en_la_ejecucion` | LIMITACION (3) |
| manifiesto sin hashes de ficheros | `integridad_no_publicada` | LIMITACION (3) |

En las contradicciones semánticas (run_id, símbolo, intervalo, parámetros,
vínculo) las pruebas **recalculan el hash del manifiesto** en la copia de
prueba: así queda demostrado que cada comprobación detecta **su** defecto y
no un fallo incidental de integridad.

## 8. Límites reales de la equivalencia (lo que el replay sí y no acredita)

- **Sí acredita**: que el resultado económico publicado es reconstruible,
  campo a campo, desde la evidencia persistida con integridad verificada,
  procedencia acreditada por consulta y la misma configuración congelada.
- **No acredita**: la corrección de los datos del proveedor (un cuerpo
  íntegro y bien vinculado refleja lo que el proveedor devolvió, no lo que
  el venue tenía), la completitud del calendario de funding más allá del
  método aplicado, ni la calidad de la regla (equivalencia ≠ rentabilidad).
- **No se comparan** los timestamps de publicación (no son datos de
  decisión); **sí** se comparan `decision_ms`/`entry_ms`/`exit_ms` con
  igualdad exacta.
- La ventana `exp-v2-ventana-2-20261112a` sigue **INSUFICIENTE**; esta
  corrección **no** aporta evidencia económica ni reabre su análisis.
- La ventana `exp-v2-ventana-3-20261115a` sigue **propuesta y sin
  ejecutar**: requiere autorización humana explícita.

## 9. Índice de la evidencia

| Artefacto | Contenido |
|---|---|
| `INFORME.md` | este informe |
| `reproducir_defectos.py` | reproducción de los tres defectos (corrida loopback real + copias independientes) |
| `contraste_antes_despues.py` | contraste antes/después sobre las mismas copias |
| `replay_publicado.py` | replay extraído de Git en `12024146` (código "antes", UTF-8) |
| `resultados_publicado.json` | veredictos del código publicado (antes) |
| `resultados_corregido.json` | veredictos del código corregido (después) |
| `aceptacion_corregida.txt` | salida de la aceptación corregida (7 passed) |
| `regresiones_pytest.txt`, `regresiones_unittest_history.txt`, `regresiones_unittest_engineering.txt`, `regresiones_unittest_public.txt` | regresiones directamente afectadas (75 + 46 + 32 + 42) |
| `hashes.json` | hash SHA-256 de cada artefacto de esta carpeta |
