# Inventario de cobertura — extension previa vs solo precio

Fecha de inventario: 2026-11-19T01:08Z.
Base publicada: `91e16671ca6492316023f1c9a7ac6c06149333ee`
(`research/universe-liquidez-v1`, local == remoto al iniciar).
Modulo: `scripts/extension_previa_inventario.py` (`extension-previa-inventario-v1`).
Salida completa fuera de Git:
`C:\proyectos\binance-futures-data\extension-previa-v1-inventario\inventario.json`.

Paso 1 de la tarea. Este documento **no contiene retornos**: solo cuenta cuantos
casos existen y cuantos cumplen las tres condiciones exigidas. Los retornos se
calculan despues de publicar `PREDECLARACION.md`.

## Que se cuenta

Se reutiliza el detector y la construccion de ventanas ya publicados, sin tocar
reglas ni umbrales:

- ventanas de 1 minuto desde `research_flow_1m` + `research_book_1m`, con las
  mismas condiciones de integridad que `construir_ventanas`
  (`degraded = 0`, `depth_gaps = 0`, `crossed = 0`, `data_quality = OK`);
- `secuencia_presion_v1.detectar_secuencias` para la senal de continuacion con
  flujo y profundidad (patron `SECUENCIA-PRESION-V1`);
- `alertas_solo_precio` para la senal de continuacion de solo precio
  (tres cierres estrictamente monotonos, mismo corte causal);
- `agrupar_episodios` (primera alerta por contrato y direccion dentro de
  5 minutos) para no contar la misma senal deslizante muchas veces.

Un **caso** es un episodio, no una alerta bruta. Las alertas brutas se informan
aparte porque varias comparten el mismo episodio.

## Las tres condiciones

1. **Historia previa valida del mismo contrato.** Seis bloques de tres minutos
   contiguos y no solapados, inmediatamente anteriores al primer minuto de la
   senal. Cada minuto debe tener `data_quality = OK`, `price_close > 0`,
   `price_open > 0` y `as_of_ms <= corte`.
2. **Dato disponible al corte.** El corte es
   `max(fin_3, as_of_1, as_of_2, as_of_3)`. Ningun minuto usado puede tener
   `as_of_ms` posterior al corte. No se usa informacion posterior.
3. **Precios verificables de entrada y salida a cinco minutos.** Entrada en la
   apertura del minuto siguiente al corte (`(corte // 60 s + 1) * 60 s`) y
   salida en la apertura de `entrada + 5 min`. Se exige la fila del minuto de
   entrada y la del minuto de salida, ambas `data_quality = OK`.

## Serie de precios usada

Se usa `research_flow_1m.price_open` / `price_close` de forma uniforme en las
cinco capturas. Motivos:

- `exp-v2-ventana-2-20261112a`, `public-pilot-1h-20261105a` y
  `public-pilot-1h-20261106a` no persistieron `consultas_klines.jsonl`; la unica
  serie de precios guardada es la de flujo (`aggTrade`);
- en `exp-v2-ventana-3-20261115a` las velas solo cubren los ultimos 63 minutos y
  19 contratos, de modo que no alcanzan para la historia previa de la mayoria de
  los casos. Se usan como **contraste**, no como fuente.

Contraste disponible (ventana 3): 736 aperturas comparadas, 576 identicas,
160 distintas, diferencia relativa mediana 0 y maxima 0.164 %. Es decir, la
apertura de flujo coincide con la apertura de vela en la mayoria de los minutos
y difiere como maximo en un tick cuando difiere. `velas_contradictorias = 0`.

Limite declarado: los ticks crudos no se persistieron (`observaciones.jsonl`
guarda el log de seleccion por ciclo, no los aggTrades). El precio es un
agregado guardado y reproducible leyendo la misma base; no se puede reconstruir
desde ticks crudos.

## Resultado por captura

Episodios de solo precio (familia primaria):

| captura | ventanas validas | ternas | alertas brutas | episodios | con historia >= 6 bloques | con precios entrada+salida | completos |
|---|---:|---:|---:|---:|---:|---:|---:|
| `exp-v2-ventana-1-20261112a` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `exp-v2-ventana-2-20261112a` | 1033 | 1091 | 477 | 231 | 106 | 164 | 78 |
| `exp-v2-ventana-3-20261115a` | 1049 | 1066 | 462 | 229 | 81 | 159 | 57 |
| `public-pilot-1h-20261105a` | 1012 | 1054 | 433 | 217 | 78 | 146 | 58 |
| `public-pilot-1h-20261106a` | 1037 | 1103 | 448 | 237 | 112 | 177 | 86 |
| **total** | 4131 | 4314 | 1820 | **914** | 377 | 646 | **279** |

Episodios del patron con flujo y profundidad (familia secundaria):

| captura | alertas brutas | episodios | con historia >= 6 bloques | completos |
|---|---:|---:|---:|---:|
| `exp-v2-ventana-1-20261112a` | 0 | 0 | 0 | 0 |
| `exp-v2-ventana-2-20261112a` | 3 | 3 | 0 | 0 |
| `exp-v2-ventana-3-20261115a` | 5 | 5 | 1 | 1 |
| `public-pilot-1h-20261105a` | 2 | 2 | 0 | 0 |
| `public-pilot-1h-20261106a` | 7 | 7 | 2 | 1 |
| **total** | 17 | **17** | 3 | **2** |

## Motivos de exclusion (no excluyentes entre si)

Un mismo episodio puede fallar por historia y por precios a la vez, por eso los
motivos suman mas que `914 - 279 = 635`.

| captura | historia insuficiente | vela de entrada ausente | vela de salida ausente |
|---|---:|---:|---:|
| `exp-v2-ventana-2-20261112a` | 125 | 19 | 48 |
| `exp-v2-ventana-3-20261115a` | 148 | 23 | 47 |
| `public-pilot-1h-20261105a` | 139 | 26 | 45 |
| `public-pilot-1h-20261106a` | 125 | 21 | 39 |
| **total** | **537** | **89** | **179** |

El motivo dominante es la historia previa insuficiente: el grabador rota
contratos y la mediana de minutos por contrato es de 15 a 37, de modo que la
mayoria de las senales aparece antes de acumular 18 minutos contiguos del mismo
contrato.

Distribucion de bloques previos disponibles (solo precio, 914 episodios):
0 bloques 193, 1-2 bloques 165, 3-5 bloques 179, 6-9 bloques 137, 10-14 bloques
136, 15 o mas 104. El maximo observado es 19 bloques, coherente con la rotacion
del grabador. 377 episodios (41.2 %) alcanzan los 6 bloques exigidos; la
cobertura no es marginal, pero la mayoria de las senales aparece antes de
acumular 18 minutos contiguos del mismo contrato.

## Concentracion

- 48 contratos distintos aportan episodios completos.
- Maximo por contrato: `JCTUSDT` 18, `BTWUSDT` 16, `HUMAUSDT` 15, `2ZUSDT` 14,
  `SOPHUSDT` 14, `AKEUSDT` 13.
- Por captura, el contrato dominante aporta entre 8 y 10 episodios de 57 a 86
  (maximo 12 % de la captura).
- Cuatro capturas en tres dias distintos (5, 6 y 14-15 de noviembre).

## Capturas revisadas y descartadas

- `diag-ws-recepcion-20261112a`: diagnostico de recepcion WS, sin
  `research.db` con flujo ni velas. 0 casos.
- `_presupuesto`: presupuesto, no captura de mercado. 0 casos.
- Derivados de la ventana 4 (`exp-v2-ventana-4-20261116a-*`): excluidos por
  instruccion; la ventana 4 formula la hipotesis, no la confirma.
- `exp-v2-ventana-1-20261112a`: `research_flow_1m` y `research_flow_10s` estan
  vacias (0 filas); solo hay libro (`research_book_1m`, 1200 filas). Sin flujo no
  hay senal de continuacion ni avance de precio. 0 casos. Campo faltante:
  `research_flow_1m.*`.

## Compuerta

- Familia de solo precio: **279 episodios completos** (>= 30). Hay cobertura
  suficiente para fijar la definicion y comparar grupos.
- Familia del patron (flujo + profundidad): **2 episodios completos** (< 30).
  No hay cobertura para esa familia; se reporta como secundaria y no decide.

Ningun umbral se ajusta a los retornos: la definicion y el criterio se publican
en `PREDECLARACION.md` antes de calcular cualquier retorno.
