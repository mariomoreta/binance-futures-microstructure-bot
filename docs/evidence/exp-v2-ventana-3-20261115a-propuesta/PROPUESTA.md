# Propuesta de UNA ventana operativa (vía A) — `exp-v2-ventana-3-20261115a`

**Fecha:** 2026-11-15 · **Estado:** **PREPARADA, NO EJECUTADA** · **Vía:** A
(`observed-settlements`) · **Cobertura:** PERPETUAL/TRADING/USDT

> **Alcance de esta propuesta.** Prepara **una** ventana futura que permita
> (1) evaluar la regla operativa existente, (2) conservar sus datos de entrada
> y trayectoria, y (3) reconstruir sus resultados **offline** sin volver a
> consultar al proveedor. **No autoriza la ejecución**: la apertura de mercado
> requiere una autorización humana posterior y explícita, con su propio
> `run_id`. La ventana anterior `exp-v2-ventana-2-20261112a` **sigue cerrada**
> y **no** se reutiliza ni se relanza. El directorio de la corrida **no** se
> ha creado.

## 1. Identidad de la corrida

| Elemento | Valor |
|---|---|
| `run_id` | `exp-v2-ventana-3-20261115a` (**nuevo**; verificado que **no** existe en el área de datos, ni en el repositorio, ni aparece en `docs/`) |
| Directorio de la corrida | `C:\proyectos\binance-futures-data\exp-v2-ventana-3-20261115a` (fuera de Git; **no creado**) |
| Directorio del presupuesto (esta propuesta) | `C:\proyectos\binance-futures-data\_presupuesto\exp-v2-ventana-3-20261115a-preparacion` (fuera de Git; **no** es el directorio de la corrida) |
| Monitor (solo lectura) | `http://127.0.0.1:3020/market-lab?vista=piloto&run=exp-v2-ventana-3-20261115a` |
| Presupuesto revalidado | 2026-11-15, con la **forma final** del comando (incluidas `--work-timeout-seconds 40200 --shutdown-grace-seconds 300` del lanzador), `--budget-only` y **sin red**: código real **0**, `stderr` vacío, gate **13/13**, `cabe_en_limites: true` |
| Reutilización | **ninguna**: no se reutiliza `exp-v2-ventana-1-20261112a`, `exp-v2-ventana-2-20261112a` ni ningún otro `run_id` |

El monitor resuelve el `run_id` dentro de `PILOT_MONITOR_ROOT`
(`C:/proyectos/binance-futures-data`); hasta que la corrida escriba
`estado.json` en su directorio, la vista no muestra datos.

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
| Persistencia de la trayectoria | cuerpos de las consultas `klines` de trayectoria, en `consultas_klines.jsonl` | preparación del 2026-11-15 |

**Totales:** el máximo propio del CLI es **40 200 s** (3 600 + 4 200 + 32 400).
Con el margen de cierre de **300 s** del lanzador, el total máximo efectivo es
**40 500 s**. El margen **no** amplía captura, exposición, consultas ni cupos.

## 3. Baseline evaluada (aclaración, no cambio de estrategia)

La regla que se evalúa es la **baseline de continuación** ya existente:

- **Dirección** según el **signo del movimiento de 24 h**
  (`derivar_direccion_desde_movimiento`); el rol (candidato/comparador) **no**
  determina la dirección.
- **Referencia actual** procedente **del mismo cierre** que compara la
  condición direccional: el cierre de la vela 1 m **plenamente cerrada en T**
  (`close_time <= decision_ms`).
- **Libro y flujo** actúan principalmente como **requisitos de calidad y
  contexto** de la observación (disponibilidad, frescura, cobertura).
- **No acredita** detección de patrones, anticipación de explosiones ni
  reversión: es una continuation con stop y horizonte, no un detector.

Esta aclaración **no** autoriza cambiar la estrategia. Todo lo que se
persiste y se reconstruye se hace **con esta** regla.

## 4. Pregunta económica exacta

> ¿Produce la baseline un **neto esperado favorable por unidad de riesgo**
> (operaciones con stop 0,5 %, horizonte 60 min y notional 1 000 USDT) tras
> **costes defensibles** (comisión 5 bps, spread 1 bp, deslizamiento 2 bps) y
> **funding acreditado**, y —si lo produce— es el efecto **atribuible a la
> regla** y no a la **cobertura desigual** de símbolos/roles ni al **rechazo
> por capacidad**?

La pregunta se responde con el embudo completo y con **denominadores
explícitos**, nunca con un número suelto.

### 4.1 Denominadores que se publicarán

| Nivel | Magnitudes |
|---|---|
| Embudo | símbolos seleccionados → observados → **aptos** → descartados; por rol y por ciclo |
| Decisión | `ENTRADA_EJECUTADA`, `SIN_ENTRADA`, `RECHAZADA_CAPACIDAD`, `DESCARTADO`, `PENDIENTE` (por rol y por ciclo) |
| Operaciones | cerradas con salida ejecutada; abiertas (sin salida); por dirección y por rol |
| Neto | `COMPLETO` (funding acreditado por posición) y `CONDICIONADO_SIN_FUNDING_COMPLETO`, **en tablas separadas** |
| Ciclos | ciclos con ambos roles **aptos**; ciclos con ambos roles con **operación cerrada** (pares comparables) |
| Datos | velas de trayectoria disponibles frente a las necesarias; liquidaciones de funding observadas frente a las esperadas |

### 4.2 Comparación por rol y por ciclo

- La comparación **candidato vs comparador** se publica **solo en los ciclos
  comparables**: ambos roles aptos **y** ambos con al menos una operación
  cerrada.
- Si la cobertura de roles es desigual en un ciclo, ese ciclo **no** entra en
  la comparación por rol: la diferencia **no** se atribuye al selector.
- El resultado por rol se publica **junto a su denominador** (operaciones
  cerradas de ese rol) y, si la capacidad shared impone el orden de entrada,
  también **por posición admitida**, para que el efecto de la prioridad
  determinista no se confunda con el efecto de la regla.

### 4.3 Tratamiento de los rechazos por capacidad

- Un rechazo por capacidad **no** es una operación: **no** tiene entrada,
  salida, costes ni P&L, y **no** suma al denominador de resultados
  económicos.
- **Sí** cuenta en el embudo de decisiones (desglosado por rol y ciclo) y se
  publica como tal, con su motivo.
- La capacidad (1 posición simultánea) **sí** puede sesgar qué rol entra
  primero; por eso el resultado por rol se reporta con su denominador y, si
  procede, **por posición admitida**.

### 4.4 Netos `COMPLETO` frente a `CONDICIONADO`

- `COMPLETO`: operación cerrada **y** funding acreditado por posición con
  cobertura completa.
- `CONDICIONADO_SIN_FUNDING_COMPLETO`: operación cerrada cuyo funding **no**
  pudo acreditarse; su número **no** es un neto completo y **no** se suma con
  los `COMPLETO`.
- `UNKNOWN` (sin posición, sin salida o sin dato) **nunca** se convierte en
  cero.
- Se publican **dos tablas** (y dos denominadores), no un total único.

### 4.5 Criterios de insuficiencia

| Situación | Resultado publicado |
|---|---|
| 0 observaciones aptas | `INSUFICIENTE` (embudo vacío) |
| 0 operaciones cerradas | `INSUFICIENTE` (no hay desenlace que evaluar) |
| 0 netos `COMPLETO` | neto completo `INSUFICIENTE`; el condicionado se publica aparte |
| Pares por rol no comparables | comparación por rol `INSUFICIENTE` (con el recuento de pares) |
| Trayectorias incompletas o archivos corruptos | replay `LIMITACION`; nunca un resultado inventado |
| Funding no observado | funding `UNKNOWN`; el neto completo no se acredita |

**Cero operaciones y falta de comparabilidad son resultados válidos.**

## 5. Datos que se conservarán (y su por qué)

| Artefacto | Contenido |
|---|---|
| `observaciones.jsonl` | observación completa con la información disponible **en T** (selección, libro, flujo, frescura, `decision_ms`) |
| `consultas_klines.jsonl` | **cuerpo real recibido** de cada consulta de trayectoria, con parámetros exactos, instantes, estado HTTP, hash y vínculo con la observación; incluye el corte causal (`reloj_ms`) |
| `resultado_operativo.jsonl` | resultados operativos (decisión, entrada, stop, salida, costes, funding y estado del neto) |
| `funding_adquisicion.jsonl` + `funding/*.json` | liquidaciones de funding realmente observadas (método A) y su calendario |
| `http_requests.jsonl` | ledger HTTP (parámetros, estado, hash, peso) |
| `resumen.json`, `manifiesto.json` | embudo, economía, hashes y **configuración operativa congelada** |

Con esos archivos, `scripts/research_operativo_replay.py` reconstruye la
operación **offline** (adaptador y motores existentes, sin red) y contrasta
ejecución ↔ replay en decisión, dirección, cantidad, entrada, stop, salida,
costes y estado del funding/neto. La equivalencia está **acreditada
localmente** (CLI real + loopback): ver
[INFORME](../exp-v2-preparacion-reproducible-20261115/INFORME.md).

**No se añaden consultas para guardar datos**, no se rellenan huecos y **no**
se reconstruye OHLC desde retornos, libro o `aggTrade`.

## 6. Presupuesto efectivo (recalculado con `--budget-only`, sin red)

Ruta de preparación:
`C:\proyectos\binance-futures-data\_presupuesto\exp-v2-ventana-3-20261115a-preparacion`.
Artefactos: `presupuesto.json` (10 524 B), `launcher.json`,
`estado_lanzador.json`, `cierre.json`, `exit_code.txt`, `stdout.log`,
`stderr.log`; copia publicada y hashes en
[`exp-v2-preparacion-reproducible-20261115`](../exp-v2-preparacion-reproducible-20261115/).

| Magnitud | Estimación base | Con reservas | Techo efectivo |
|---|---|---|---|
| Intentos HTTP | 1 004 | **1 334** | 2 000 |
| Peso REST | 1 472 | **3 752** | 5 000 |
| Almacenamiento | 9 016 872 B previstos | **56 363 648 B** reservados | 134 217 728 B |
| Cuerpos `klines` persistidos | 4 320 000 B (480 respuestas × 9 000 B) | incluidos arriba | — |
| Margen reservado | — | **77 854 080 B** | — |
| Funding (`fundingRate`) | 20 llamadas | 40 repetidas + 50 reintentos → **110 intentos reservados** | 500 / 5 min (máx. concentrado 110) |
| Mensajes WS de datos | — | — | 5 000 000 |
| Reaperturas WS | — | — | 20 (+ 2 de sobregiro por tick) |

**Gate:** `cabe_en_limites: true`, **13/13** comprobaciones en `true`.

**Diferencias frente al presupuesto publicado de la ventana 2: 10, todas de
almacenamiento** (los cuerpos persistidos). No cambia ninguna consulta, peso,
reintento, límite WS, duración, exposición ni cupo.

**Desglose REST estimado:** `exchangeInfo` 12 llamadas (peso 12) +
`ticker/24hr` 12 llamadas (peso 480) + trayectorias operativas 240 (peso 240) +
resultados por horizonte 720 (peso 720) + `fundingRate` 20 (peso 20) = **1 004
intentos / 1 472 de peso**.

**Conexiones simultáneas frente a aperturas acumuladas:** 2 conexiones
simultáneas, 2 aperturas iniciales, 11 rotaciones previstas → 22 aperturas por
rotación y **46 aperturas acumuladas** como máximo. Pico de streams: **40**.

## 7. Comando literal (el que admite el parser)

El **mismo** comando con el que se calculó el presupuesto, **sin**
`--budget-only` y con el `--out-dir` y el `--status-file` de la corrida:

```powershell
python scripts/run_pilot_window.py `
  --out-dir C:\proyectos\binance-futures-data\exp-v2-ventana-3-20261115a `
  --work-timeout-seconds 40200 `
  --shutdown-grace-seconds 300 `
  --mode public --activar-publico `
  --run-id exp-v2-ventana-3-20261115a `
  --status-file C:\proyectos\binance-futures-data\exp-v2-ventana-3-20261115a\estado.json `
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
`--out-dir` (directorio de **preparación**, para no crear ni contaminar el
directorio de la corrida) y el flag `--budget-only`. Las opciones
`--work-timeout-seconds` y `--shutdown-grace-seconds` son **del lanzador** y
nunca llegan al parser del piloto (verificado en la revalidación: el
`comando` que el lanzador registra para el hijo no las contiene).

**Interpretación del resultado al cerrar:** leer `exit_code.txt` (código real
del hijo) y, por separado, `estado_lanzador.json` y `cierre.json` (veredicto
del lanzador: `resultado`, `causa_terminacion`, `cumplimiento_normal`,
`codigo_lanzador`, `cierre.*`, `tiempos.exceso_maximo_total_s`,
`tiempos.incumplimiento_plazo_global`). Un código 0 del hijo **no** significa
cumplimiento normal si el plazo de trabajo se agotó (el lanzador devuelve
**124** o **125** y lo declara); un exceso del máximo total devuelve **126**.

## 8. Lectura al cerrar

1. **Embudo**: seleccionados → observados → aptos → descartados, por rol y
   ciclo.
2. **Decisiones**: `ENTRADA_EJECUTADA` / `SIN_ENTRADA` /
   `RECHAZADA_CAPACIDAD` / `DESCARTADO` / `PENDIENTE`, con los rechazos por
   capacidad **en tabla propia**.
3. **Economía**: netos `COMPLETO` y `CONDICIONADO` **en tablas separadas**,
   con sus denominadores; coste por operación (comisión, spread,
   deslizamiento) y funding acreditado.
4. **Comparación por rol**: solo en ciclos comparables; el recuento de pares
   se publica aunque sea cero.
5. **Reconstrucción offline**: `scripts/research_operativo_replay.py` sobre el
   directorio de la corrida; su veredicto (`EQUIVALENTE` /
   `LIMITACION` / `DIFERENCIAS`) se publica **junto al** resultado económico.
6. **Veredicto**: `INSUFICIENTE` es un resultado admisible y se explica con
   sus denominadores.

## 9. Bloqueos reales que quedan

1. **Falta autorización humana explícita** para ejecutar esta ventana (y su
   margen de cierre). El control temporal del lanzador ya está implementado y
   probado: lo pendiente es la decisión de ejecutar.
2. La economía sigue **sin evaluarse** en ninguna corrida: la ventana cerrada
   no conserva los datos necesarios y esta propuesta **no** aporta evidencia
   de rentabilidad.
3. Puede volver a terminar `INSUFICIENTE` (0 observaciones aptas o 0
   operaciones): es un resultado válido, no un fallo de la preparación.
4. La espera contable puede terminar en `UNKNOWN` si no se observan
   liquidaciones: su cobertura no se presupone.
5. **Cobertura de contrato:** solo PERPETUAL/TRADING/USDT; los futuros con
   vencimiento no están cubiertos por el selector y quedan fuera.
6. Restricciones permanentes: sin órdenes, claves ni cuentas; dataset fuera de
   Git; monitor en 3020; el servicio 8792 no se toca.

## 10. Fuera de alcance

On-chain, indicadores nuevos, GARCH, patrones nuevos, futuros con vencimiento
y cambios de dashboard quedan como líneas futuras documentadas
([PRODUCT_GOAL](../PRODUCT_GOAL.md), F-PATRONES-EXTREMOS-CONTEXTO-20261112).
No forman parte de esta ventana ni de este bloque.
