# INCIDENTE: PILOTO COTIZACIONES 20261119 — INTERRUMPIDO / INSUFICIENTE

## Resumen

La corrida `pilot-cotizaciones-20261119` (run_id: `pilot-cotizaciones-20261119`, SHA ejecutado: `f5a3ed65b38fe0bee04999620d695e949c4108d2`) se lanzó con proveedores públicos de Binance (USDM futures WS/REST) en modo `--mode public --activar-publico`. El proceso fue **interrumpido por el timeout de OpenCode (600 s)** durante la fase de captura, antes de completar el settle de 4.200 s.

## Estado de los artefactos

### Archivos recuperados (fuera de Git)

| Archivo | Tamaño | SHA-256 | Estado |
|---------|--------|---------|--------|
| `config_inicial.json` | 2,957 | `683d33df7daf78d1da7cd3d876b57fd34fe1a2acaa3eba5ad69593b34c6a780c` | Presente |
| `consultas_klines.jsonl` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | Presente, vacío |
| `cotizaciones_investigacion.jsonl` | 2,736,098 | `0cbcd6e799b3fd8d9c4cc98e117346eaa08f192c225e07a5755050aef383281a` | Presente |
| `funding_adquisicion.jsonl` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | Presente, vacío |
| `observaciones.jsonl` | 744,274 | `b9915be340445574696ef93cfe849f97525bf0d8cc50ca73bf611347d1b22043` | Presente |
| `resultado_operativo.jsonl` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | Presente, vacío |
| `status.json` | 10,200 | `fefb4243d96e566a3b8d7291d12096f037f1d03798faa9d082112eaa975ad881` | Presente |
| `resumen.json` | — | — | **NO EXISTE** |
| `manifiesto.json` | — | — | **NO EXISTE** |

### Estado del piloto (desde `status.json`)

| Campo | Valor |
|-------|-------|
| run_id | `pilot-cotizaciones-20261119` |
| started_ms | `1795129432173` (2026-11-19T23:03:52.173Z) |
| capture_end_ms | `1795130032173` (captura completada a los 600 s) |
| settle_end_ms | `1795134232173` (nunca alcanzó) |
| phase | `captura` |
| stop_reason | None (muerto por timeout de OpenCode) |
| mode | public |
| observations_written | 177 |
| outcomes_written | 38 |
| evaluations_run | 9 |
| cotizaciones_investigacion.cap_reached | `False` |
| cotizaciones_investigacion.cap_instante_ms | None |
| cotizaciones_investigacion.quotes_written | 5,812 |
| cotizaciones_investigacion.bytes_written | 2,736,098 |
| cotizaciones_investigacion.max_rows | 20,000 |
| cotizaciones_investigacion.max_bytes | 4,194,304 |

## Recuento del JSONL de cotizaciones

| Métrica | Valor |
|---------|-------|
| Total filas | 5,782 |
| Cotizaciones (`kind=cotizacion`) | 5,778 |
| Filas faltante (`kind=faltante`) | 4 |
| Cotizaciones válidas (`valida=true`) | 5,762 |
| Cotizaciones no válidas | 16 |
| Motivos invalidez | `SALTO_SECUENCIA`: 16, `LIBRO_DEGRADADO`: 16 |
| Primer evento received_ms | 1795137237615 |
| Último evento received_ms | 1795137832894 |
| Último instante acreditado | aprox. 598,861 ms desde started_ms |

## Evaluación de episodios

**Resultado: INSUFICIENTE**

| Métrica | Valor |
|---------|-------|
| Episodio aptos (decision_ms <= corte) | 0 |
| Episodios tardíos (decision_ms > corte) | 156 |
| Entradas con `entry_ms` en `resultado_operativo.jsonl` | 0 (archivo vacío) |
| Pares evaluables | 0 |
| Faltantes por causa: rotación | N/D (no hay episodios) |
| Faltantes por causa: antigüedad | N/D |
| Faltantes por causa: agotamiento | N/D |
| Faltantes por causa: calidad | N/D |
| Faltantes por causa: tamaño | N/D |

No hay episodios aptos para evaluar porque `resultado_operativo.jsonl` está vacío (0 bytes) — el piloto murió antes de escribir resultados operativos. Las 156 observaciones en `observaciones.jsonl` tienen `decision_ms` pero **no** tienen `entry_ms`, `direction` ni `qty`; esos campos solo existen en `resultado_operativo.jsonl`.

## Presupuesto (`--budget-only`)

| Campo | Valor |
|-------|-------|
| gate.cabe_en_limites | `true` |
| cubre_hasta_ultima_salida | `true` |
| filas_proyectadas | 6,000 |
| bytes_proyectados | 3,072,000 |
| minutos_cubiertos_por_tope | 13.585 min |
| max_horizon_min | 60.0 min |
| Última salida (entrada + 300.000 ms) | 570,000 ms (09:30) |
| Cierre del feed | 600,000 ms (10:00) |
| Margen antes del cierre del feed | 30,000 ms |

El presupuesto aprobó ambos controles. La cinta cubre la última salida (570,000 ms < 600,000 ms de cierre del feed). El settle de 4.200 s no añade cobertura de cotización.

## Conclusión

La corrida quedó **INTERRUMPIDA / INSUFICIENTE**. No hay episodios con `entry_ms`, `direction` y `qty` para evaluar (`resultado_operativo.jsonl` está vacío). No se puede calcular spread por episodio ni reportar rentabilidad. Comisión, slippage y funding siguen `UNKNOWN`.

Una futura corrida requiere `run_id` nuevo y autorización aparte.
