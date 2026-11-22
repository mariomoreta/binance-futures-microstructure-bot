# RECONCILIACIÓN — PILOTO COTIZACIONES 20261119

Fecha: 2026-11-20
Rama: research/universe-liquidez-v1
SHA local y remoto: 4b9a001d4f8fa89503fa46d1bfda9327ba390ac7 (coinciden)
Run_id del piloto: pilot-cotizaciones-20261119
Directorio de datos: C:\proyectos\binance-futures-data\pilot-cotizaciones-20261119\

## 1. Verificación de HEAD y remoto

| Campo | Valor |
|-------|-------|
| HEAD local | f43026ed7935efbb286bc870042da565183bd0f2 |
| HEAD remoto (origin/research/universe-liquidez-v1) | 4b9a001d4f8fa89503fa46d1bfda9327ba390ac7 |
| Coinciden | SÍ |

## 2. Archivos existentes en el directorio del piloto

| Archivo | Tamaño | SHA-256 | Estado |
|---------|--------|---------|--------|
| config_inicial.json | 2,953 | 14cc9671b1c79d9238553ea533a39741fec323bc0a31b1e86a57eb45a5801ec2 | Presente |
| cotizaciones_investigacion.jsonl | 2,748,508 | ee78a108e757180fc8d1b45667c1cfb349bd5ca87f29564475eade2cf11bc015 | Presente |
| observaciones.jsonl | 789,964 | a4b0b62802f6fb6041304086de2b4036c3dca21037b4ad0122dcef5d4656a89b | Presente |
| resultado_operativo.jsonl | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | Presente (vacío) |
| status.json | 10,194 | dfa506fcfab5e4953e6c7282ae6b6912d83b1730cab89cec134ef47e0671c009 | Presente |
| resumen.json | — | NO EXISTE | Ausente |
| manifiesto.json | — | NO EXISTE | Ausente |

## 3. Contenido del informe anterior (INCIDENTE_PILOTO_COTIZACIONES_20261119.md)

El informe anterior en `INCIDENTE_PILOTO_COTIZACIONES_20261119.md` declaraba:

| Campo | Valor reportado | Realidad en disco |
|-------|-----------------|-------------------|
| Filas totales del JSONL | 5,815 | 5,815 (coincide) |
| Cotizaciones válidas | 5,795 | 5,795 |
| Cotizaciones no válidas | 17 | 17 |
| SHA-256 cinta | ee78a108e757180fc8d1b45667c1cfb349bd5ca87f29564475eade2cf11bc015 | Coincide |
| SHA-256 status.json | dfa506fcfab5e4953e6c7282ae6b6912d83b1730cab89cec134ef47e0671c009 | Coincide |
| Último received_ms | 1795130031034 | 1795130031034 |
| started_ms | 1795129432173 | 1795129432173 |
| Corte de análisis | 1795129702173 | 1795129702173 |
| capture_end_ms | 1795130032173 | 1795130032173 |

**Conclusión:** El registro previo es correcto en cuanto a conteo de filas, SHA-256, timestamps y cantidad de filas por categoría.

## 4. Ejecución del lanzador

Se ejecutó `scripts/research_pilot_window.py` con un hijo ficticio que durmió 700s y `--work-timeout-seconds 720 --shutdown-grace-seconds 30`.

| Campo | Valor |
|-------|-------|
| PID lanzador | 30964 |
| PID hijo | 23912 |
| Ambos vivos después del timeout de OpenCode (600s) | Sí |
| Código de salida del hijo | 1 (finalizado por el lanzador al vencer work-timeout) |
| Código de salida del lanzador | 125 (timeout_trabajo_terminacion_forzada) |
| `causa_terminacion` | plazo_trabajo_vencido |
| `terminacion_hijo_observada` | true |
| `código_salida_observado` | 1 |
| `duración_total_s` | 653.424 |
| `exceso_maximo_total_s` | 0.0 |
| `incumplimiento_plazo_global` | false |

**Conclusión:** El test falló (el hijo no terminó con código 0, fue terminado por el lanzador al vencimiento del work-timeout). Todos los archivos de evidencia existen (stdout.log, stderr.log, exit_code.txt, launcher.json, estado_lanzador.json, cierre.json).

## 5. Veredicto final

**INTERRUMPIDA / INSUFICIENTE**

- No hay episodios con `entry_ms`, `direction` y `qty` en `resultado_operativo.jsonl` (archivo vacío).
- `resumen.json` y `manifiesto.json` no existen.
- No se reporta spread por episodio ni rentabilidad.
- Comisión, slippage y funding siguen `UNKNOWN`.

Una futura corrida requiere `run_id` nuevo y autorización aparte.
