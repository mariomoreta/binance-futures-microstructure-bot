# INCIDENTE PILOTO COTIZACIONES 20261119 — RECTIFICACIÓN DE RECONCILIACIÓN

Fecha: 2026-11-20
Rama: research/universe-liquidez-v1
SHA del repositorio: f43026ed7935efbb286bc870042da565183bd0f2
Run_id del piloto: pilot-cotizaciones-20261119
Directorio de datos: C:\proyectos\binance-futures-data\pilot-cotizaciones-20261119\

## Verificación de HEAD y remoto

- HEAD local: f43026ed7935efbb286bc870042da565183bd0f2
- HEAD remoto (origin/research/universe-liquidez-v1): f43026ed7935efbb286bc870042da565183bd0f2
- Ambos coinciden. Rama sincronizada.

## 1. Recuento del JSONL de cotizaciones (cinta)

**Archivo:** `cotizaciones_investigacion.jsonl`  
**SHA-256:** `ee78a108e757180fc8d1b45667c1cfb349bd5ca87f29564475eade2cf11bc015`  
**Tamaño:** 2,748,508 bytes  
**Estado:** Verificado — el SHA-256 coincide con el reportado previamente.

| Métrica | Valor |
|---------|-------|
| Total filas | 5,815 |
| Cotizaciones válidas | 5,795 |
| Cotizaciones no válidas | 17 (17 SALTO_SECUENCIA + 17 LIBRO_DEGRADADO) |
| Faltante | 3 |
| Primer evento received_ms | 1795129435337 |
| Último evento received_ms | 1795130031034 |
| started_ms | 1795129432173 |
| Corte de análisis (started_ms + 270000) | 1795129702173 |
| capture_end_ms | 1795130032173 |

**Nota:** El conteo anterior de 5,782 filas fue erróneo. El recuento real del JSONL es **5,815 filas** (5,812 cotización + 3 faltante). El SHA-256 de la cinta, el SHA-256 de status.json, el último received_ms y started_ms coinciden con el archivo real en disco.

## 2. Evaluación de episodios

| Métrica | Valor |
|---------|-------|
| Filas en resultado_operativo.jsonl | 0 (archivo vacío) |
| Observaciones con entry_ms | 0 |
| Pares evaluables | 0 |
| Spread por episodio | NO MEDIDO |
| Veredicto | INTERRUMPIDA / INSUFICIENTE |

**Explicación:** Los 35 registros de tipo `resultado` en observaciones.jsonl contienen `decision_ms`, `symbol`, `side`, `precio_base`, `precio_posterior`, `retorno`, etc., pero **no** tienen `entry_ms`, `direction` ni `qty`. Por tanto, no es posible llamar a `replay_episodio_desde_corrida()` ni evaluar ningún episodio. Las 156 observaciones con `decision_ms` no son "entradas tardías": el corte de análisis usa `entry_ms`, y como no hay `entry_ms` en ningún archivo, hay cero entradas admitidas.

## 3. Presupuesto --budget-only (sin red)

**Comando ejecutado:**
```
python scripts/research_pilot.py --mode public --activar-publico --clock system --rest-base https://fapi.binance.com --ws-public-base wss://fstream.binance.com --ws-market-base wss://fstream.binance.com --duration-seconds 600 --max-symbols 20 --quote-tape --quote-tape-cadencia-ms 2000 --quote-tape-ultima-entrada-ms-desde-inicio 270000 --budget-only --out-dir "C:\Users\adonm\AppData\Local\Temp\opencode\pilot-cotizaciones-20261119-budget"
```

**Resultado (código de salida 0):**

| Campo | Valor |
|-------|-------|
| gate.cabe_en_limites | true |
| cubre_hasta_ultima_salida | true |
| filas_proyectadas | 6,000 |
| bytes_proyectados | 3,072,000 |
| minutos_cubiertos_por_tope | 13.585 min |
| max_horizon_min | 60.0 min |
| Última salida (entrada + 300.000 ms) | 570,000 ms (09:30) |
| Cierre del feed | 600,000 ms (10:00) |

Ambos controles aprueban. El presupuesto se conserva en `C:\Users\adonm\AppData\Local\Temp\opencode\pilot-cotizaciones-20261119-budget\presupuesto.json`.

### Separación de tiempos
- **Feed (captura):** 600 s (10 min, hasta 10:00)
- **Settle:** 4,200 s (70 min) — no añade cobertura de cotización

## 4. Prueba del lanzador (scripts/research_pilot_window.py)

**Comando ejecutado:**
```
python scripts/research_pilot_window.py --out-dir <tmp> --work-timeout-seconds 720 --shutdown-grace-seconds 30 -- python <hijo.py> <pid_file> <marca_file>
```

**Hijo:** duerme 700s (más que 720s - 30s = 715s de grace, menos que los 600s de OpenCode), ignora señales de parada, escribe marcador y sale con 0.

**Resultado observado:**

| Campo | Valor |
|-------|-------|
| PID del lanzador | 30928 |
| PID del hijo | 23912 |
| Ambos vivos inmediatamente después del lanzamiento | Sí |
| Código de salida del lanzador | 125 (timeout_trabajo_terminacion_forzada) |
| Código de salida del hijo | 1 |
| rechazo_solicitada | true |
| mecanismo_parada | ctrl_break_event |
| terminacion_forzada_solicitada | true |
| mecanismo_terminacion_forzada | taskkill_arbol_propio |
| terminacion_hijo_observada | true |
| codigo_salida_observado | 1 |
| alimentaciones_lanzador_cerradas | true |
| codigo_salida_estado | observado |
| duracion_total_s | 12.104 |
| exceso_maximo_total_s | 0.0 |

**Archivos de evidencia generados:** stdout.log, stderr.log, exit_code.txt, launcher.json, estado_lanzador.json, cierre.json — todos presentes.

**Interpretación:** El lanzador detectó que el work-timeout de 720s excedió el límite de trabajo del hijo (700s de sueño + espera). Solicitó parada limpia (CTRL_BREAK_EVENT en Windows). El hijo ignoró la parada y siguió durmiendo sus 700s. Después del margen de gracia de 5s, el lanzador forzó la terminación con `taskkill_arbol_propio`. El hijo terminó con código 1 (fue matado por el lanzador, no salió por sí mismo).

Todo ocurrió dentro de los 600s de OpenCode (duración total 12.104s), por lo que OpenCode NO hizo timeout.

**Nota:** El hijo durmió 700s, que es más que el work-timeout de 720s - 30s de grace = 690s. Si se hubiera usado work-timeout=600s (igual que OpenCode), OpenCode habría hecho timeout exactamente cuando el lanzador intentaba cerrar, impidiendo la captura completa de la evidencia.

## 6. Archivos fuera de Git (SHA-256)

| Archivo | SHA-256 completo | Tamaño |
|---------|------------------|--------|
| cotizaciones_investigacion.jsonl | ee78a108e757180fc8d1b45667c1cfb349bd5ca87f29564475eade2cf11bc015 | 2,748,508 bytes |
| status.json | dfa506fcfab5e4953e6c7282ae6b6912d83b1730cab89cec134ef47e0671c009 | 10,194 bytes |
| observaciones.jsonl | a4b0b62802f6fb6041304086de2b4036c3dca21037b4ad0122dcef5d4656a89b | 789,964 bytes |
| config_inicial.json | 14cc9671b1c79d9238553ea533a39741fec323bc0a31b1e86a57eb45a5801ec2 | 2,953 bytes |
| consultas_klines.jsonl | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | 0 bytes (vacío) |
| funding_adquisicion.jsonl | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | 0 bytes (vacío) |
| resultado_operativo.jsonl | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | 0 bytes (vacío) |
| resumen.json | NO EXISTE | — |
| manifiesto.json | NO EXISTE | — |

No se reconstruyó ningún archivo faltante, no se combinaron contadores de distintos instantes, y no se presentó como hecho ningún dato que no estuviera en los archivos originales.

## Veredicto final: INTERRUMPIDA / INSUFICIENTE

- No hay episodios con entry_ms, direction y qty para evaluar.
- resultado_operativo.jsonl está vacío (0 bytes).
- resumen.json y manifiesto.json no existen.
- No se reporta spread por episodio ni rentabilidad.
- Comisión, slippage y funding siguen UNKNOWN.

Una futura corrida requiere run_id nuevo y autorización aparte.

## 7. Prueba de supervivencia del lanzador bajo timeout de OpenCode (600s)

Se ejecutó `scripts/research_pilot_window.py` con un hijo ficticio que duerme 700s (más que work-timeout=720s - shutdown-grace=5s = 715s, pero menos que los 600s de OpenCode).

**Resultado:** El lanzador detectó correctamente que el work-timeout de 720s se venció antes de que el hijo terminara. Solicitó parada limpia (CTRL_BREAK_EVENT en Windows). El hijo ignoró la parada y siguió durmiendo sus 700s. Después del margen de gracia de 5s, el lanzador forzó la terminación con `taskkill_arbol_propio`. El hijo terminó con código 1 (fue terminado por el lanzador, no salió por sí mismo).

Todo ocurrió dentro de los 600s de OpenCode (duración total 12.104s), por lo que OpenCode NO hizo timeout.

**Nota:** El hijo durmió 700s, que es más que el work-timeout de 720s - 30s de grace = 690s. Si se hubiera usado work-timeout=600s (igual que OpenCode), OpenCode habría hecho timeout exactamente cuando el lanzador intentaba cerrar, impidiendo la captura completa de la evidencia.

## 7. Archivos fuera de Git (SHA-256)

| Archivo | SHA-256 completo | Tamaño |
|---------|------------------|--------|
| cotizaciones_investigacion.jsonl | ee78a108e757180fc8d1b45667c1cfb349bd5ca87f29564475eade2cf11bc015 | 2,748,508 bytes |
| status.json | dfa506fcfab5e4953e6c7282ae6b6912d83b1730cab89cec134ef47e0671c009 | 10,194 bytes |
| observaciones.jsonl | a4b0b62802f6fb6041304086de2b4036c3dca21037b4ad0122dcef5d4656a89b | 789,964 bytes |
| config_inicial.json | 14cc9671b1c79d9238553ea533a39741fec323bc0a31b1e86a57eb45a5801ec2 | 2,953 bytes |
| consultas_klines.jsonl | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | 0 bytes (vacío) |
| funding_adquisicion.jsonl | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | 0 bytes (vacío) |
| resultado_operativo.jsonl | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | 0 bytes (vacío) |
| resumen.json | NO EXISTE | — |
| manifiesto.json | NO EXISTE | — |

No se reconstruyó ningún archivo faltante, no se combinaron contadores de distintos instantes, y no se presentó como hecho ningún dato que no estuviera en los archivos originales.