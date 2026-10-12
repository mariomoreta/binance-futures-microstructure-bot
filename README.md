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

Primero ejecutar tests sin red (comando canonico desde la raiz del repo):

```powershell
python run_tests.py
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

Para conservar una corrida, el probe persiste evidencia por construcción:
registro en `logs/probe_runtime.json`, log fusionado UTF-8 en `logs/probe-runs/`
y filas en `data/microprobe.db` (observaciones, snapshots, eventos,
prospectiva) más `data/historical/historical.db` (investigación). Para
capturar además la consola, PowerShell puede redirigirla externamente:

```powershell
New-Item -ItemType Directory -Force -Path .\logs\phase1b | Out-Null
$evidenceStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
python -m microstructure_probe --duration 300 2>&1 | Tee-Object -FilePath ".\logs\phase1b\evidence-5m-$evidenceStamp.log"
```

La carpeta `logs/` esta ignorada. Los detectores no guardan estado; los
motores restauran continuidad desde la base (returns/flow/OI rehidratan
buckets y muestras al iniciar) y vuelven a hacer warm-up donde no hay
continuidad persistida.

## Configuracion

Todos los umbrales estan en `config/probe.json`; no hay umbrales sueltos en el codigo. Los valores iniciales son hipotesis operativas, no evidencia de edge:

- Liquidacion: umbrales por simbolo, individual y acumulado en 10 segundos.
- Funding: extremos por percentiles del historial observado en memoria. No emite antes del minimo de muestras.
- Volumen: notional de buckets de 10 segundos comparado con buckets previos por z-score. No emite antes del minimo de buckets.
- Staleness y desfase temporal: configurables; los mensajes demasiado desincronizados se descartan.
- Clock sync: cinco muestras publicas de `GET /fapi/v1/time` al iniciar y aproximadamente cada 10 minutos. El offset y RTT reportados son medianas.
- Telemetria: cuantiles por stream/simbolo, procesamiento interno, near-misses, warm-up, data quality y uptime de las conexiones.

La persistencia operativa (P1-02: observaciones, snapshots, universo) y la
de investigación (P1-11B/C: klines históricas, event studies con outcomes
MFE/MAE sin lookahead; P1-13A/14A: oportunidades y prospectiva) existen y
están validadas; el detalle vive en `docs/CURRENT_STATE.md` y
`docs/TASK_QUEUE.md`. El boceto temprano "observar sin persistir en Fase 1"
quedó superado por decisión documentada (ver `docs/DECISIONS.md`); lo que
sigue perteneciendo a fases posteriores es paper trading y ejecución.

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

Consultar `docs/PHASE_1_REPORT.md`. Un test exitoso no demuestra edge ni autoriza paper trading, órdenes o capital real. La persistencia local de investigación (P1-02/P1-11B/C) es la vía autorizada para datos; nunca credenciales ni fondos.
