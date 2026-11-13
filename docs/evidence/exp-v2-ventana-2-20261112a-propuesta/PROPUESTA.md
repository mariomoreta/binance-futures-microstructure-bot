# Propuesta de UNA ventana operativa (vía A) — `exp-v2-ventana-2-20261112a`

**Fecha:** 2026-11-12 · **Estado:** **PREPARADA, NO EJECUTADA** · **Vía:** A
(`observed-settlements`) · **Cobertura:** PERPETUAL/TRADING/USDT

En este bloque **no se ha abierto mercado**: solo se ejecutó `--budget-only`
(cálculo puro, sin red). No hay órdenes, claves, cuentas privadas, dataset de
investigación nuevo ni cambios de código.

---

## 1. Identidad de la corrida

| Elemento | Valor |
|---|---|
| `run_id` | `exp-v2-ventana-2-20261112a` (nuevo; verificado que **no** existe en el área de datos ni en el repositorio) |
| Directorio de la corrida | `C:\proyectos\binance-futures-data\exp-v2-ventana-2-20261112a` (fuera de Git; **no creado todavía**) |
| Directorio del presupuesto (esta propuesta) | `C:\proyectos\binance-futures-data\_presupuesto\exp-v2-ventana-2-20261112a` (fuera de Git) |
| Monitor | `http://127.0.0.1:3020/market-lab?vista=piloto&run=exp-v2-ventana-2-20261112a` |
| SHA de código del presupuesto | `cd788277a46f9d3ef05d8257517442368b48218b` (este bloque **no cambia código**: el presupuesto se calculó con ese árbol) |
| SHA de ejecución | el commit que publique esta propuesta; se confirmará en el momento de solicitar autorización (el manifiesto de la corrida registra `git_head`) |
| Reutilización | **ninguna**: no se reutiliza `exp-v2-ventana-1-20261112a` ni ningún otro `run_id`; este presupuesto **no** es una renovación del anterior |

El monitor es de **solo lectura** y resuelve el `run_id` dentro de
`PILOT_MONITOR_ROOT` (`C:/proyectos/binance-futures-data`); hasta que la
corrida escriba `estado.json` en su directorio, la vista no muestra datos.

## 2. Configuración congelada (no cambia respecto del protocolo)

| Parámetro | Valor | Origen |
|---|---|---|
| Captura | 3 600 s | `--duration-seconds 3600` |
| Settle (resolución de resultados) | 4 200 s | `--settle-seconds 4200` |
| Espera contable máxima | 32 400 s | `--funding-wait-seconds 32400` |
| Funding real | `exchange` + `observed-settlements`, ≤ 3 consultas por símbolo | `--funding-source exchange --funding-method observed-settlements --funding-wait-max-queries 3` |
| Selección y decisión | cada 300 s (12 selecciones, 12 ciclos) | `--selection-seconds 300 --cycle-seconds 300 --decision-delay-seconds 5` |
| Candidatos / comparadores / conjunto | 12 / 8 / 20 | `--max-candidates 12 --max-comparators 8 --max-symbols 20` |
| Frescura del dato | 5 000 ms | `--max-data-age-ms 5000` |
| Stop | 0,5 % | regla congelada (`STOP_DISTANCE_PCT = 0.5`) |
| Notional | 1 000 USDT | regla congelada (`NOTIONAL_USDT = 1000.0`) |
| Horizonte operativo | 60 min | `--horizons '5m=300000,15m=900000,60m=3600000'` |
| Capacidad global compartida | 1 posición simultánea | `MAX_CONCURRENT = 1` |
| Techos HTTP / peso / reintentos | 2 000 / 5 000 / 50 | protocolo vigente |
| Techos WS / almacenamiento | 5 000 000 mensajes de datos / 134 217 728 B | protocolo vigente |
| Rutas WS | `/public` (libro) y `/market` (flujo) | rutas corregidas (§10.9) |

## 3. Contrato temporal explícito

| Fase | Mecanismo | Plazo | Qué incluye | Momento medido |
|---|---|---|---|---|
| **1. Captura** | `--duration-seconds 3600` | 3 600 s | suscripción WS de los símbolos de cada ciclo; 12 selecciones y 12 cortes de decisión; captura de flujo (`aggTrade`) y libro (`depth20@100ms`); REST de preparación (`exchangeInfo` + `ticker/24hr`) y trayectorias 1 m de las observaciones aptas | `started_ms` y `capture_end_ms` en `estado.json`; `ciclos_decision` = 12 en el presupuesto |
| **2. Resolución de resultados (settle)** | `--settle-seconds 4200` | ≤ 4 200 s | madurar los horizontes 5 m/15 m/60 m de las observaciones **pendientes** y resolver sus resultados. **Solo se abre si hay trabajo pendiente**; si no hay, termina con la captura | `settle_end_ms`; `outcomes_written`; `pending` en `estado.json` |
| **3. Espera contable** | `--funding-wait-seconds 32400` | ≤ 32 400 s | consultas **diferidas** de `fundingRate` por símbolo con posición abierta, programadas con la cadencia observada de ese símbolo; ≤ 3 consultas por símbolo; nunca se prorroga | `espera_contable_inicio_ms`, `espera_contable_fin_ms`, `espera_contable_cierre`, `espera_contable_plazo_max_ms` en `estado.json`; `consultas_por_simbolo` en `resumen.json` |
| **4. Cierre y persistencia final** | (fuera de los plazos del CLI) | **margen propuesto: 300 s** | cancelar los feeds y cerrar los sockets; drenar el `ResearchRecorder` (buckets abiertos como `PARTIAL`); escribir los pendientes como `PENDING`/`UNKNOWN` **con su motivo**; escribir `resumen.json` y `manifiesto.json` (con hashes) desde lo persistido; el envoltorio persiste `stdout.log`, `stderr.log`, `exit_code.txt` y `launcher.json` | fin real del proceso: `launcher.json.duracion_s` y `fin_iso_utc`; `duracion_total_efectiva_s` en `resumen.json` |

**Totales:** el máximo propio del CLI es **40 200 s** (3 600 + 4 200 + 32 400 =
11 h 10 min). Con el margen de cierre propuesto de 300 s, el **total máximo
propuesto es 40 500 s (11 h 15 min)**.

**Sobre el margen de 300 s:** es una **propuesta no autorizada**, pensada como
tope de observación del cierre, no como una ampliación de nada. Justificación:
el diagnóstico acreditó que el cierre de sockets puede consumir ~5 s
(`close_timeout=5`) y la ventana anterior terminó ~5,4 s después del fin de
captura; 300 s es un margen finito y holgado para ese teardown más el
volcado de `resumen.json`/`manifiesto.json` con hashes de hasta 128 MiB. **No
amplía captura, ni exposición (1 posición, 1 000 USDT), ni consultas** (los
cupos HTTP son los del presupuesto, consumidos dentro de las fases). Si al
cumplirse el máximo del CLI el proceso siguiera vivo, es un **incidente
material a registrar**, no una autorización para seguir.

**Nota de expectativas:** el total real suele ser **menor**: `settle` y espera
contable solo se abren si hay trabajo pendiente (en la ventana anterior
terminaron en 3 605 s porque no hubo observaciones aptas).

## 4. Presupuesto (`--budget-only`, sin mercado)

Calculado con el comando literal de §5 y el árbol `cd788277`: artefacto
`presupuesto.json` (10 381 B) y hashes en `hashes.json`, en este mismo
directorio.

| Magnitud | Estimación base | Con reservas | Techo efectivo |
|---|---|---|---|
| Intentos HTTP | 1 004 | **1 334** | 2 000 |
| Peso REST | 1 472 | **3 752** | 5 000 |
| Almacenamiento | 4 696 872 B previstos | **52 043 648 B** reservados | 134 217 728 B |
| Funding (`fundingRate`) | 20 llamadas | 40 repetidas + 50 reintentos → **110 intentos reservados** | 500 / 5 min (máx. concentrado 110) |
| Mensajes WS de datos | — | — | 5 000 000 |
| Reaperturas WS | — | — | 20 (+ 2 de sobregiro por tick) |

**Gate:** `cabe_en_limites: true`, **13/13** comprobaciones en `true`.

**Desglose REST estimado:** `exchangeInfo` 12 llamadas (peso 12) +
`ticker/24hr` 12 llamadas (peso 480) + trayectorias operativas 240 (peso 240) +
resultados por horizonte 720 (peso 720) + `fundingRate` 20 (peso 20) = **1 004
intentos / 1 472 de peso**.

**Conexiones simultáneas frente a aperturas acumuladas:** **2 conexiones
simultáneas** (una `/public` para libro, una `/market` para flujo), **2
aperturas iniciales**, 11 rotaciones previstas por cambio de conjunto → **22
aperturas por rotación**, y **46 aperturas acumuladas** como máximo (2
iniciales + 22 de rotación + 20 de reconexión + 2 de sobregiro por tick).
Pico de streams: **40** (20 por conexión, límite 1 024 por conexión).

**Naturaleza de los pesos:** son **estimaciones de la política** (tablas
oficiales de peso por endpoint), **no consumo medido por Binance**. El
`pool_referencia` del propio presupuesto advierte que es una referencia, no
una garantía de disponibilidad. El peso real se contrasta al cierre con
`presupuesto_http` y el ledger `http_requests.jsonl` (que registra el peso
reservado por la puerta y el observado en las cabeceras).

## 5. Comando literal (el que admite el parser)

Ejecutado **solo** en modo `--budget-only` (salida real **0**, `stderr` vacío).
Para la ejecución autorizada, es **el mismo comando sin `--budget-only` y con
el `--out-dir` y el `--status-file` de la corrida**:

```powershell
python scripts/run_pilot_window.py `
  --out-dir C:\proyectos\binance-futures-data\exp-v2-ventana-2-20261112a `
  --mode public --activar-publico `
  --run-id exp-v2-ventana-2-20261112a `
  --status-file C:\proyectos\binance-futures-data\exp-v2-ventana-2-20261112a\estado.json `
  --duration-seconds 3600 --settle-seconds 4200 `
  --cycle-seconds 300 --selection-seconds 300 --decision-delay-seconds 5 `
  --max-symbols 20 --max-candidates 12 --max-comparators 8 `
  --min-quote-volume 1000000 `
  --horizons '5m=300000,15m=900000,60m=3600000' `
  --price-interval 1m --price-tolerance-ms 90000 --price-delay-ms 2000 `
  --max-data-age-ms 5000 --max-observations 20000 `
  --max-bytes 134217728 --max-messages 5000000 `
  --max-http-attempts 2000 --max-http-retries 50 --max-http-weight 5000 `
  --max-ws-reconnects 20 --tick-ms 500 `
  --funding-source exchange `
  --funding-method observed-settlements `
  --funding-wait-seconds 32400 `
  --funding-wait-max-queries 3 `
  --rest-base https://fapi.binance.com `
  --ws-public-base wss://fstream.binance.com/public `
  --ws-market-base wss://fstream.binance.com/market
```

Diferencias con el comando de presupuesto realmente ejecutado: solo
`--out-dir` (directorio de presupuesto propio, para **no** crear ni
contaminar el directorio de la corrida) y el flag `--budget-only`. El comando
efectivo del presupuesto está en `launcher.json`.

## 6. Criterios de parada y tratamiento de pendientes

**Paradas (todas cierran la corrida y se registran):** duración de captura
agotada; `max_observations` alcanzado; tope de bytes alcanzado; `max_messages`
WS alcanzado; reconexiones WS acumuladas agotadas; presupuesto HTTP agotado
(intentos/peso/reintentos); señal externa (SIGINT/SIGTERM).

**Limpieza:** cancelar los feeds WS y cerrar las conexiones; drenar el
`ResearchRecorder` (los buckets abiertos quedan como `PARTIAL`); escribir los
resultados pendientes como `PENDING` **con su motivo**; escribir manifiesto y
resumen **desde lo persistido** (no se inventan precios ni liquidaciones).

**Pendientes de la espera contable:** posición con cobertura acreditable →
`ACREDITADA` (neto `COMPLETO`); posición cuya cobertura **todavía puede
mejorar** → `PENDIENTE` con motivo y **sin acreditar importe**; defecto
definitivo (hueco interior, cadencia ambigua, marca inservible) o consultas
agotadas → `UNKNOWN` con motivo; **una parada del operador o un presupuesto
agotado conservan el pendiente** (no se degradan a `UNKNOWN` de evidencia).

## 7. Qué deberá evaluar la futura ventana (fijado antes de ejecutarla)

1. **Cadena completa:** selección → datos aptos → señal o abstención → entrada
   simulada → gestión y salida, con la regla causal y el horizonte congelados.
2. **Identidad y causalidad verificables:** cada operación persistida lleva
   `observation_id`, símbolo, rol, decisión, instantes de entrada y salida,
   `config_hash` y versión de motor; la causalidad se reconstruye desde los
   registros, no desde una atribución retrospectiva.
3. **Capacidad global respetada:** como máximo **1** posición simultánea; los
   rechazos por capacidad (`RECHAZADA_CAPACIDAD`) se cuentan, no se ocultan.
4. **Costes y funding conocidos o `UNKNOWN`:** comisión, spread y deslizamiento
   según la regla congelada; el funding se acredita **por posición** con
   liquidaciones observadas; lo que no se acredite queda `UNKNOWN` y **nunca se
   suma como cero**.
5. **Netos completos separados de condicionados:** `COMPLETO` (funding acreditado
   por posición) frente a `CONDICIONADO_SIN_FUNDING_COMPLETO`, sin mezclarlos
   en un único número.
6. **Denominadores:** por rol (candidato/comparador): seleccionados,
   observados, aptos, descartados; por decisión: `ENTRADA_EJECUTADA`,
   `SIN_ENTRADA`, `RECHAZADA_CAPACIDAD`; y cobertura por ciclo con ambos roles
   aptos.
7. **Resultado económico reconstruible desde lo persistido:** `resumen.json`
   (con `economia_operativa_v2`), `manifiesto.json` con hashes de cada
   artefacto, y las filas de `observaciones.jsonl`,
   `resultado_operativo.jsonl` y `funding_adquisicion.jsonl`.

**Resultados posibles y honestos:** **cero operaciones o cobertura
insuficiente son resultados válidos**. No se fuerzan entradas y **la ausencia
de operaciones no se presenta como P&L cero**: se publica como embudo vacío o
`INSUFICIENTE`, con sus denominadores.

**El monitor presenta artefactos**; las operaciones reconstruidas después son
**simulaciones**, no órdenes en vivo. La ventana no acredita ejecuciones
reales ni rentabilidad generalizable.

## 8. Bloqueos reales que quedan

1. **Falta autorización humana explícita** para ejecutar esta ventana (y para
   el margen de cierre propuesto).
2. La **causa raíz histórica** de la ventana anterior sigue `UNKNOWN` (no se
   abre la URL antigua) y su **exit code histórico** sigue `UNKNOWN`.
3. **La economía sigue sin evaluarse** en ninguna corrida: el diagnóstico
   acreditó recepción, no embudo ni resultado.
4. **No hay garantía de datos aptos**: el precedente `public-pilot-1h-20261106a`
   produjo 168 observaciones aptas de 216 con las rutas por categoría; la
   ventana anterior produjo 0 por la URL antigua. Esta ventana puede volver a
   terminar `INSUFICIENTE`.
5. **La espera contable puede terminar en `UNKNOWN`**: depende de liquidaciones
   de funding realmente observadas; su cobertura no se presupone.
6. **Riesgo residual de estabilidad**: la recepción está acreditada para 60 s;
   esta ventana exige 1 h con 11 rotaciones (reaperturas de ambos feeds) y
   hasta 46 aperturas acumuladas, y el gasto REST previsto es una estimación,
   no un consumo medido.
7. **Cobertura de contrato:** solo PERPETUAL/TRADING/USDT; los futuros con
   vencimiento no están cubiertos por el selector y quedan fuera.
8. Restricciones permanentes: sin órdenes, claves ni cuentas; dataset fuera de
   Git; monitor en 3020; el servicio 8792 no se toca.

## 9. Fuera de alcance de esta ventana

On-chain, indicadores nuevos, GARCH, patrones nuevos, futuros con vencimiento
y cambios de dashboard quedan como **líneas futuras documentadas**
([PRODUCT_GOAL](PRODUCT_GOAL.md), F-PATRONES-EXTREMOS-CONTEXTO-20261112). No
forman parte de esta ventana ni de este bloque.
