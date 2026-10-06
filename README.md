# Binance Futures Microstructure Probe

Proyecto nuevo y aislado para la Fase 1 del bot de microestructura de Binance USD-M Futures. Solo consume datos publicos. No usa cuenta, API keys, endpoints privados ni envia ordenes.

## Seguridad por defecto

El proceso solo arranca con `BOT_MODE=observe` (es el valor por defecto). Si la variable contiene cualquier otro valor, el programa aborta. Esta base no contiene codigo de trading real.

```text
BOT_MODE: observe
apiKeysUsed: 0
realOrdersSent: 0
realCapitalAtRisk: 0
maxDrawdownKillSwitchActive: false
```

## Requisitos

- Python 3.11 o superior.
- Conexion a Internet capaz de abrir WebSockets TLS hacia `fstream.binance.com`.

## Instalacion en PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

## Verificacion

Primero ejecutar tests sin red:

```powershell
python -m unittest discover -s tests -v
```

Mostrar las conexiones sin abrirlas:

```powershell
python -m microstructure_probe --show-streams
```

Ejecutar un probe acotado de 60 segundos:

```powershell
python -m microstructure_probe --duration 60
```

Sin `--duration`, corre hasta `Ctrl+C`. Los logs son JSON precedidos por timestamp y nivel. El ultimo registro `final_summary` es la evidencia compacta de la ejecucion.

Para conservar una corrida sin agregar persistencia al probe, PowerShell puede capturar el log externamente:

```powershell
New-Item -ItemType Directory -Force -Path .\logs\phase1b | Out-Null
$evidenceStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
python -m microstructure_probe --duration 300 2>&1 | Tee-Object -FilePath ".\logs\phase1b\evidence-5m-$evidenceStamp.log"
```

La carpeta `logs/` esta ignorada. Los detectores no guardan estado y vuelven a hacer warm-up al reiniciar.

## Configuracion

Todos los umbrales estan en `config/probe.json`; no hay umbrales sueltos en el codigo. Los valores iniciales son hipotesis operativas, no evidencia de edge:

- Liquidacion: umbrales por simbolo, individual y acumulado en 10 segundos.
- Funding: extremos por percentiles del historial observado en memoria. No emite antes del minimo de muestras.
- Volumen: notional de buckets de 10 segundos comparado con buckets previos por z-score. No emite antes del minimo de buckets.
- Staleness y desfase temporal: configurables; los mensajes demasiado desincronizados se descartan.
- Clock sync: cinco muestras publicas de `GET /fapi/v1/time` al iniciar y aproximadamente cada 10 minutos. El offset y RTT reportados son medianas.
- Telemetria: cuantiles por stream/simbolo, procesamiento interno, near-misses, warm-up, data quality y uptime de las conexiones.

La Fase 1 no persiste eventos ni checkpoints posteriores. Eso pertenece expresamente a la Fase 2. Al reiniciar, el historial estadistico de funding y volumen vuelve a calentarse.

## Streams y ruteo

El probe usa el esquema de endpoints ruteados introducido por Binance:

- `/public`: `bookTicker` y `depth20@100ms`.
- `/market`: `aggTrade`, `!markPrice@arr@1s` y `!forceOrder@arr`.

Mantener las conexiones separadas reduce jitter y evita depender de las URLs legacy.

## Semantica de latencia Phase 1B

- `rawEventLagMs = localReceiveWallClockMs - E`.
- `correctedEventLagMs = (localReceiveWallClockMs + clockOffsetMs) - E`.
- Cuando el stream realmente ofrece un tiempo transaccional, tambien se reportan `rawTransactionLagMs`, `correctedTransactionLagMs` y `exchangeEventMinusTransactionMs = E - T`.
- En `markPrice`, `T` significa proxima hora de funding; no se usa como transaction time.
- `processingLatencyMs` usa `perf_counter_ns`, separado en parseo, metricas y detector.
- Los cuantiles conservan las ultimas 20.000 muestras por distribucion; `count`, `min`, `max` y `mean` cubren toda la corrida.

`staleStreams` solo evalua feeds con cadencia documentada (`markPrice@1s` y `depth@100ms`). `silentStreams` conserva el silencio observado de todos los feeds, incluidos los event-driven, sin afirmar perdida de mensajes.

Los samples de funding repetidos no se consideran evidencia independiente: el resumen separa muestras recibidas, tasas distintas y cambios de valor. La logica del detector no fue recalibrada.

## Estado del proyecto

Consultar `docs/PHASE_1_REPORT.md`. Un test exitoso no demuestra edge ni autoriza persistencia, paper trading o capital real.
