# Inventario: cotizaciones disponibles en los extremos de los 278 episodios

Version `coste-ejecucion-inventario-v1`. Base `2be0e1f`. Solo lectura.
Criterios fijados en `PREDECLARACION.md` (2026-11-19T12:26Z), escritos antes
de calcular cualquier retorno ajustado por spread.

## 1. Que se buscaba

Un registro con **precio de mejor bid y precio de mejor ask explicitos** para
el contrato del episodio, en la entrada (`entrada_ms`, apertura del minuto
siguiente al corte) y en la salida (`salida_ms = entrada_ms + 5 min`).

## 2. Fuentes revisadas y lo que contienen

| fuente | contenido | campos de precio de nivel |
| --- | --- | --- |
| `research.db` / `research_book_1m` | agregado por minuto del libro `depth20@100ms` | **ninguno**: `spread_min/mean/max`, `imb_*`, `micro_*`, `bid5_mean`, `ask5_mean`, `bid20_mean`, `ask20_mean` (cantidades), `depth_gaps`, `degraded`, `crossed` |
| `observaciones.jsonl` (`libro`) | snapshot en el instante de decision | **ninguno**: `spread_bps`, `bid_levels`, `ask_levels`, `bid_base_top20`, `ask_base_top20` (cantidades); el precio es `precio_base` = **mid** |
| `resultado_operativo.jsonl` | ejecuciones simuladas del motor de papel | `entry_px`/`exit_px` simulados y `spread_slip` configurado; no son cotizaciones |
| `http_requests.jsonl` | peticiones REST | solo `exchangeInfo`, `ticker/24hr` y `klines`; ninguna peticion de profundidad |
| `consultas_klines.jsonl` | velas OHLC (solo ventana 3) | OHLC; no es bid/ask |
| `funding_adquisicion.jsonl` | funding | 0 bytes en ventanas 1-3; ausente en 1105a y 1106a |

Barrido adicional sobre los 527 archivos de texto de las capturas (todos los
formatos, < 40 MB): **0 coincidencias** de `bidPrice`, `askPrice`, `best_bid`,
`best_ask`, `bestBid`, `bestAsk`.

`research_book_1m` guarda **un agregado por minuto**, no el precio de nivel. El
`libro` de `observaciones.jsonl` guarda **mid y spread**, no bid/ask. Un precio
derivado como `mid * (1 +/- spread_bps / 20000)` es reconstruible pero **no es
una cotizacion observada** y no cumple C0.

## 3. Cobertura por captura

| captura | episodios | bucket entrada | bucket salida | ambos | bucket disponible al instante (e/s) | obs. a +/-5 s en ambos (calidad ok) | C0 | C3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `exp-v2-ventana-2-20261112a` | 78 | 78 | 76 | 76 | 0 / 0 | 0 (0) | 0 | 0 |
| `exp-v2-ventana-3-20261115a` | 57 | 57 | 57 | 57 | 0 / 0 | 0 (0) | 0 | 0 |
| `public-pilot-1h-20261105a` | 58 | 58 | 58 | 58 | 0 / 0 | 2 (2) | 0 | 0 |
| `public-pilot-1h-20261106a` | 85 | 84 | 82 | 81 | 0 / 0 | 0 (0) | 0 | 0 |
| **total** | **278** | **277** | **273** | **272** | **0 / 0** | **2 (2)** | **0** | **0** |

`bucket` = existe fila de `research_book_1m` para el simbolo y el minuto exacto.
`bucket disponible al instante` = `as_of_ms <= instante`. Es **0 en los dos
extremos**: el agregado del minuto se publica ~60 s despues del instante.

## 4. Cuando estuvo disponible el dato

Latencia `as_of_ms - instante` del bucket, por captura (mediana):

| captura | entrada | salida |
| --- | --- | --- |
| ventana 2 | 61 252 ms | 61 284 ms |
| ventana 3 | 60 409 ms | 60 410 ms |
| 1105a | 60 366 ms | 60 384 ms |
| 1106a | 60 289 ms | 60 313 ms |

El bucket del minuto de entrada cubre `[entrada, entrada + 60 s)` y se publica
al cerrar el minuto. En el instante de entrada **no existe**. Lo mismo ocurre
en la salida. Usarlo como coste del instante seria adelanto de informacion.

Los snapshots de `observaciones.jsonl` si estan disponibles en el instante
(`received_ms <= instante`), pero son **mid + spread**.

## 5. Que tan lejos queda el snapshot mas cercano

Distancia `|event_ms - instante|` del snapshot del mismo simbolo mas proximo
(278 episodios):

| extremo | min | p25 | mediana | p75 | max |
| --- | --- | --- | --- | --- | --- |
| entrada | 3 261 ms | 47 150 ms | **72 638 ms** | 116 726 ms | 253 007 ms |
| salida | 1 155 ms | 47 165 ms | **72 528 ms** | 129 506 ms | 347 365 ms |

Solo **2 de 278** episodios tienen un snapshot a +/-5 s en ambos extremos.

## 6. Los dos unicos candidatos (no evaluables por C0)

| captura | simbolo | dir. | dist. entrada | dist. salida | spread entrada | spread salida | bruto publicado |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1105a | `LYNUSDT` | LONG | 3 349 ms | 1 155 ms | 4.683 bps | 4.670 bps | +32.82 bps |
| 1105a | `HUMAUSDT` | SHORT | 3 261 ms | 1 529 ms | 2.275 bps | 2.276 bps | +34.03 bps |

Ambos pasan C1 y C2, y ambos **fallan C0**: el registro tiene mid y spread, no
bid/ask. Ademas son dos episodios con retorno bruto muy superior a la media de
los 278 (+5.13 bps); aunque se derivara una cotizacion, no serian
representativos y no se extrapolarian.

## 7. Faltantes exactos

| faltante | cantidad |
| --- | --- |
| campo `best_bid` (precio) en cualquier fuente | **ausente en las 5 fuentes** |
| campo `best_ask` (precio) en cualquier fuente | **ausente en las 5 fuentes** |
| episodios sin bucket de entrada | 1 (`SPACEUSDT`, 1106a) |
| episodios sin bucket de salida | 5 (`ZESTUSDT`, `TACUSDT`, `CYBERUSDT`, `UAIUSDT`, `HUMAUSDT`) |
| episodios sin par de buckets | 6 |
| episodios sin cotizacion instantanea a +/-5 s en ambos extremos | **276** |
| episodios con mid+spread instantaneo a +/-5 s en ambos extremos | 2 |
| funding | `UNKNOWN` en las 4 capturas |
| comision | `UNKNOWN`: no hay tarifa acreditada en los artefactos |
| slippage adicional | `UNKNOWN`: sin fills, cola ni consumo de profundidad |

Nota: `SPACEUSDT` (1106a) falta solo en la entrada y `HUMAUSDT` (1106a) solo en
la salida; por eso el total de episodios afectados es 6 y no 7.

## 8. Calidad del agregado (solo contexto)

- 91 de 556 buckets (16.4 %) marcados `degraded`; 0 `crossed`.
- `sample_count`: min 23, mediana 436, max 585 por minuto.
- Spread agregado por minuto (bps): entrada mediana 4.77 (n=277, min 0.98,
  max 19.49); salida mediana 4.58 (n=273, min 0.97, max 13.63); combinado
  mediana 4.64 (n=550).
- 42.9 % de los buckets tienen `spread_mean > 5.13 bps`.

Estos valores son **descriptivos**. Una media por minuto no es una cotizacion y
no se usa para calcular retornos.

## 9. Reproduccion

```
python scripts/coste_ejecucion_inventario.py \
  --salida C:\proyectos\binance-futures-data\coste-ejecucion-v1\inventario.json
```

Salida completa (539 KB) fuera de Git. Copia compacta publicada en
`C-inventario.json`.
