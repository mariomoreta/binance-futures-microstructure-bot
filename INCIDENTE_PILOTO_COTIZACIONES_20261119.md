# INCIDENTE PILOTO COTIZACIONES 20261119 — RECTIFICACIÓN DE RECONCILIACIÓN

Fecha: 2026-11-19
Rama: research/universe-liquidez-v1
SHA del repositorio: f43026ed7935efbb286bc870042da565183bd0f2
Run_id del piloto: pilot-cotizaciones-20261119
Directorio de datos: C:\proyectos\binance-futures-data\pilot-cotizaciones-20261119\

## Verificación de HEAD y remoto

- HEAD local: f43026ed7935efbb286bc870042da565183bd0f2
- HEAD remoto (origin/research/universe-liquidez-v1): f43026ed7935efbb286bc870042da565183bd0f2
- Ambos coinciden. Rama sincronizada.

## 1. Separación de los dos conjuntos reportados

### Conjunto A (información previamente reportada en ee51fd1)

| Campo | Valor reportado | Valor real en disco | Coincide |
|-------|-----------------|---------------------|----------|
| Filas totales | 5,815 | 5,815 | SÍ |
| SHA-256 cinta | ee78a108e757180fc8d1b45667c1cfb349bd5ca87f29564475eade2cf11bc015 | ee78a108e757180fc8d1b45667c1cfb349bd5ca87f29564475eade2cf11bc015 | SÍ |
| SHA-256 status.json | dfa506fcfab5e4953e6c7282ae6b6912d83b1730cab89cec134ef47e0671c009 | dfa506fcfab5e4953e6c7282ae6b6912d83b1730cab89cec134ef47e0671c009 | SÍ |
| Último received_ms | 1795130031034 | 1795130031034 | SÍ |
| started_ms | 1795129432173 | 1795129432173 | SÍ |
| capture_end_ms | 1795130032173 | 1795130032173 | SÍ |

**Conclusión:** El recuento real del archivo es 5,815 filas (5,812 cotización + 3 faltante). El SHA-256 de la cinta, el SHA-256 de status.json, el último received_ms y started_ms coinciden con el archivo real en disco.

### Conjunto B (reportado en ee51fd1)

| Campo | Valor reportado | Valor en disco | Coincide |
|-------|-----------------|----------------|----------|
| Filas totales | 5,782 | No existe | NO |
| SHA-256 cinta | 0cbcd6e799b3fd8d9c4cc98e117346eaa08f192c225e07a5755050aef383281a | No existe | NO |
| SHA-256 status.json | fefb4243d96e566a3b8d7291d12096f037f1d03798faa9d082112eaa975ad881 | No existe | NO |
| Primer received_ms | 1795137237615 | No existe | NO |
| Último received_ms | 1795137832894 | No existe | NO |

**Conclusión:** El conjunto B **no existe en el directorio del piloto**. No hay archivo `cotizaciones_investigacion.jsonl` con ese SHA-256, ni `status.json` con ese SHA-256, ni ningún otro directorio de corrida que contenga esos archivos. La procedencia es **NO VERIFICABLE** — no se puede acreditar que exista tal conjunto. No se asume existencia de una segunda corrida ni se reutiliza ningún run_id.

## 2. Reconciliación por evidencia

### Archivos existentes en `C:\proyectos\binance-futures-data\pilot-cotizaciones-20261119\`

| Archivo | Tamaño | SHA-256 completo | run_id interno | Timestamps relevantes |
|---------|--------|------------------|----------------|-----------------------|
| config_inicial.json | 2,953 | 14cc9671b1c79d9238553ea533a39741fec323bc0a31b1e86a57eb45a5801ec2 | pilot-cotizaciones-20261119 | escrito_ms: 1795129432173 (2026-11-19T23:03:52.173Z) |
| cotizaciones_investigacion.jsonl | 2,748,508 | ee78a108e757180fc8d1b45667c1cfb349bd5ca87f29564475eade2cf11bc015 | pilot-cotizaciones-20261119 | Primer received_ms: 1795129435337; Último: 1795130031034 |
| observaciones.jsonl | 789,964 | a4b0b62802f6fb6041304086de2b4036c3dca21037b4ad0122dcef5d4656a89b | pilot-cotizaciones-20261119 | decision_ms: 1795129531054 (primera) a 1795130031054 (última) |
| resultado_operativo.jsonl | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 (SHA-256 vacío) | — | Sin contenido |
| status.json | 10,194 | dfa506fcfab5e4953e6c7282ae6b6912d83b1730cab89cec134ef47e0671c009 | pilot-cotizaciones-20261119 | started_ms: 1795129432173; capture_end_ms: 1795130032173; settle_end_ms: 1795134232173 |

### Archivos ausentes

| Archivo | Estado |
|---------|--------|
| resumen.json | NO EXISTE |
| manifiesto.json | NO EXISTE |

### Verificación de correspondencia run_id

Todos los archivos con campo `run_id` contienen `pilot-cotizaciones-20261119`:
- config_inicial.json: run_id = pilot-cotizaciones-20261119
- cotizaciones_investigacion.jsonl: cada fila con run_id = pilot-cotizaciones-20261119
- observaciones.jsonl: cada observación con observation_id = <symbol>|<decision_ms>, run_id implícito
- status.json: run_id = pilot-cotizaciones-20261119

**Conclusión:** Todos los archivos existentes pertenecen a la misma corrida (run_id `pilot-cotizaciones-20261119`). No hay evidencia de una segunda corrida (run_id distinto) en el directorio.

### Evidencia de comandos/logs de ejecución

No existe archivo `comando_efectivo.txt`, `comando.txt`, `launcher.json`, `estado_lanzador.json` ni `cierre.json` en el directorio. El piloto se ejecutó directamente (no a través del lanzador `run_pilot_window.py`), por lo que no hay registro de comando ni de lanzamiento separado. El estado se puede reconstruir parcialmente desde `status.json` y `config_inicial.json`.

## 3. Rectificación del informe

### Correcciones al informe publicado en ee51fd1

| Campo | Reportado anteriormente | Valor corregido | Motivo |
|-------|------------------------|-----------------|--------|
| Filas totales del JSONL | 5,815 | 5,815 | Se corrigió el conteo; el valor real en disco es 5,815 filas (5,812 cotización + 3 faltante) |
| SHA-256 cinta | ee78a108e757180fc8d1b45667c1cfb349bd5ca87f29564475eade2cf11bc015 | ee78a108e757180fc8d1b45667c1cfb349bd5ca87f29564475eade2cf11bc015 | Sin cambio (coincide) |
| SHA-256 status.json | dfa506fcfab5e4953e6c7282ae6b6912d83b1730cab89cec134ef47e0671c009 | dfa506fcfab5e4953e6c7282ae6b6912d83b1730cab89cec134ef47e0671c009 | Sin cambio (coincide) |
| Último received_ms | 1795130031034 | 1795130031034 | Sin cambio (coincide) |
| Conjunto B (5,782 filas, SHA-256 0cbcd6e7…3281a) | Reportado como existente | No existe en disco | Procedencia NO VERIFICABLE; no hay archivo con ese SHA-256 en el directorio |

### Reconciliación de filas por conjunto

| Conjunto | Filas totales | Cotización válidas | Cotización no válidas | Faltante | SHA-256 cinta | run_id | Estado |
|----------|---------------|-------------------|----------------------|----------|---------------|--------|--------|
| A (real, en disco) | 5,815 | 5,795 | 17 (SALTO_SECUENCIA + LIBRO_DEGRADADO) | 3 | ee78a108e757180fc8d1b45667c1cfb349bd5ca87f29564475eade2cf11bc015 | pilot-cotizaciones-20261119 | Verificada |
| B (reportada, no en disco) | 5,782 | — | — | — | 0cbcd6e799b3fd8d9c4cc98e117346eaa08f192c225e07a5755050aef383281a | No verificada | NO VERIFICABLE — archivos ausentes |

### Recuento de episodios

| Métrica | Valor |
|---------|-------|
| Episodios en `resultado_operativo.jsonl` | 0 (archivo vacío, 0 bytes) |
| Observaciones con `entry_ms` | 0 (ninguna observación tiene este campo) |
| Observaciones con `decision_ms` | 156 |
| Observaciones aptas (`apto_para_evaluacion=true`) | 119 |
| Observaciones no aptas | 37 |
| Episodios admitidos (decision_ms <= 1795129702173) | 0 |
| Episodios tardíos (decision_ms > 1795129702173) | 156 |

**No hay episodios con `entry_ms` ni `direction` ni `qty` en ninguno de los archivos.** Los 35 registros de tipo `resultado` en `observaciones.jsonl` contienen `decision_ms`, `symbol`, `side`, `precio_base`, `precio_posterior`, `retorno`, etc., pero **no** `entry_ms`, `direction` ni `qty`. Por tanto, no es posible llamar a `replay_episodio_desde_corrida()` ni evaluar ningún episodio.

### Veredicto: INTERRUMPIDA / INSUFICIENTE

- La cinta de cotizaciones tiene 5,815 filas (5,812 cotización + 3 faltante), cubriendo desde `received_ms=1795129435337` hasta `1795130031034`.
- No hay episodios con `entry_ms` ni `direction` ni `qty` para evaluar.
- `resultado_operativo.jsonl` está vacío (0 bytes).
- `resumen.json` y `manifiesto.json` no existen.
- **No se reporta spread por episodio ni rentabilidad.** Comisión, slippage y funding siguen `UNKNOWN`.

### Sobrevivencia al timeout de OpenCode

**NO ACREDITADA.** La prueba del lanzador con `--work-timeout-seconds 600` y un hijo que duerme 700s fue ejecutada, pero OpenCode hizo timeout en 600s y mató todo el árbol de procesos (lanzador + hijo) antes de que el hijo pudiera terminar. No fue posible demostrar que el lanzador y el hijo sobrevivieran al timeout de OpenCode. Esto queda como no acreditado.

### Archivos fuera de Git (SHA-256)

| Archivo | SHA-256 completo | Tamaño |
|---------|------------------|--------|
| `cotizaciones_investigacion.jsonl` | ee78a108e757180fc8d1b45667c1cfb349bd5ca87f29564475eade2cf11bc015 | 2,748,508 bytes |
| `status.json` | dfa506fcfab5e4953e6c7282ae6b6912d83b1730cab89cec134ef47e0671c009 | 10,194 bytes |
| `observaciones.jsonl` | a4b0b62802f6fb6041304086de2b4036c3dca21037b4ad0122dcef5d4656a89b | 789,964 bytes |
| `config_inicial.json` | 14cc9671b1c79d9238553ea533a39741fec323bc0a31b1e86a57eb45a5801ec2 | 2,953 bytes |
| `consultas_klines.jsonl` | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | 0 bytes (vacío) |
| `funding_adquisicion.jsonl` | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | 0 bytes (vacío) |
| `resultado_operativo.jsonl` | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | 0 bytes (vacío) |
| `resumen.json` | NO EXISTE | — |
| `manifiesto.json` | NO EXISTE | — |

No se reconstruyó ningún archivo faltante, no se combinaron contadores de distintos instantes, y no se presentó como hecho ningún dato que no estuviera en los archivos originales.
