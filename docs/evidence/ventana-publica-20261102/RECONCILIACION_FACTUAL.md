# Reconciliación factual — Ventana pública de integración (eng-run-public-20261102)

## 1. Estado del veredicto

- Veredicto global: **ERROR** (no "cero operaciones válido")
- Objetivo: **no evaluado** (no se llegó a crear sesión ni a etapa de evaluación)
- Error: `GLOBAL_DEADLINE_EXCEEDED en engineering_start_wait`
- Fuente del error: orquestador (scripts/engineering_live_window.py)

## 2. Consumo agregado del ledger (reconciliación)

| Métrica | Valor | Origen |
|---|---|---|
| rest_count (contador del arnés) | 0 | evidence.json del orquestador |
| ledger_total_por_run_id | null (no alcanzado) | evidence.json del orquestador |
| Filas en market_fetch_ledger para eng-run-public-20261102 | 0 | consulta directa a data/market-cache/market_cache.db |
| Consumo agregado persistido | 0 filas | ledger |
| Distinción reservado / envío / respuesta / error | UNKNOWN | 0 filas no permiten distinguir |

**Nota crítica:** `rest_count=0` NO acredita cero intentos `/time`. `rest_count` es solo el contador de consultas de klines del arnés del orquestador. Los intentos `/time` del servicio de ingeniería (ClockSynchronizer) se reservan en `market_fetch_ledger` de forma independiente, pero el ledger tiene 0 filas para este run_id, por lo que no se puede confirmar que se haya realizado ni un solo intento. El consumo de `/time` es **UNKNOWN**.

## 3. Cronología de transiciones (timestamps y duración monotónica)

| Transición | Estado | Timestamp (ms) | Origen |
|---|---|---|---|
| Inicio del proceso (orquestador) | started_at_ms | 1793631488720 - (duración total) | evidence.json `generated_at_ms` es el fin, no el inicio |
| Preflight completado | dashboard_up, build_served, puertos libres | antes de service_started | evidence.json checks |
| Proceso de mercado creado | service_started | — | check `service_started`: PID 29820, puerto 8791, modo=public |
| Proceso de ingeniería creado | _spawn (engineering-session) | — | código: se invoca _spawn(argv2) tras service_started |
| Espera de readiness (servicio de ingeniería) | engineering_start_wait | — | NUNCA COMPLETADA: /health no respondió |
| Vencimiento del deadline | GLOBAL_DEADLINE_EXCEEDED | 1793631488720 (generated_at_ms) | error del orquestador |
| Limpieza (_cleanup) | procesos terminados | después del error | puertos 8791/8797 verificados libres tras la corrida |

Duración monotónica: el deadline de 180 s empezó en el primer acceso público (preflight al dashboard). El fallo ocurrió esperando readiness del servicio de ingeniería, consumiendo el deadline completo.

## 4. Última transición completada (diagnóstico)

**Última transición completada:** `service_started` — el servicio de mercado arrancó correctamente (PID 29820, puerto 8791, modo=public).

Tras esto, el orquestador invocó `_spawn(argv2, "engineering-session")` para lanzar el servicio de ingeniería con `--clock-source public --run-id eng-run-public-20261102`, y entró en el bucle de espera de `/health` del servicio de ingeniería (`engineering_start_wait`). Ese `/health` nunca respondió.

**No se atribuye el bloqueo exclusivamente a ClockSynchronizer.** Basándose en el código de `scripts/microstructure_probe/engineering_session_service.py` (`main()`), el flujo de arranque del servicio de ingeniería en modo `public` es:

1. `MarketCache()` + `init_db()`
2. Lectura/escritura de `run_id` (se escribió `run-id.json` correctamente)
3. Verificación de presupuesto (pasó: 0 + 5 <= 30 ventana, 0 + 5 <= 7 corrida)
4. Creación de `ClockSynchronizer` con `_make_budgeted_time_fetch`
5. `asyncio.run(synchronizer.sync())` — **bloqueante**: hace hasta 5 intentos `/time` a Binance (timeout 5 s cada uno)
6. Solo DESPUÉS del sync: creación de `EngineeringSessionController`, `EngineeringHTTPServer`, escritura de `pid_file`, impresión de JSON de inicio, `serve_forever`

Dado que el servidor HTTP del servicio de ingeniería **no se levanta hasta después** de `synchronizer.sync()`, y el sync es bloqueante contra la red pública de Binance, el servicio nunca publicó `/health`. El orquestador agotó el deadline de 180 s esperando.

La raíz del bloqueo es que el servidor HTTP se levanta **después** de la sincronización del reloj, no antes. Durante la preparación (sync en curso), `/health` no está disponible en absoluto.

## 5. Evidencia existente

- `docs/evidence/ventana-publica-20261102/evidence.json` — evidencia del orquestador (veredicto ERROR)
- `docs/evidence/ventana-publica-20261102/run-id.json` — run_id persistido (`eng-run-public-20261102`)
- `docs/evidence/ventana-publica-20261102/LEDGER_CONSULTA.json` — consulta del ledger (0 filas)
- `docs/evidence/ventana-publica-20261102/ABSENCIA_LOGS.md` — declaración de archivos de stdout/stderr ausentes

## 6. Conclusión

La ventana pública no se completó. El objetivo (sesión identificada → eventos → evaluación → correspondencia con dashboard) **no fue evaluado**. No hay consumo de `/time` verificable en el ledger (0 filas). El consumo de `/time` del servicio de ingeniería es UNKNOWN.
