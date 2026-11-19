# Predeclaracion — extension previa del movimiento vs regla de solo precio

Escrita y publicada el **2026-11-19T01:08Z**, antes de calcular cualquier
retorno. Base: `91e16671ca6492316023f1c9a7ac6c06149333ee`
(`research/universe-liquidez-v1`). Inventario previo: `INVENTARIO.md`
(solo conteos, sin retornos).

Una vez publicado este documento no se cambian la definicion, los grupos, el
minimo evaluable ni el criterio de decision. Si algo no se puede calcular, se
declara como faltante en lugar de redefinirlo.

## Pregunta

Cuando aparece una senal de continuacion, medir cuanto se ha extendido el
movimiento frente a la historia del propio contrato, permite evitar entradas
peores que las de una regla de solo precio?

## Familia de senales

**Primaria (decide):** episodios de continuacion de solo precio, construidos con
la regla publicada `alertas_solo_precio` (tres cierres estrictamente monotonos,
corte causal `max(fin_3, as_of_1, as_of_2, as_of_3)`) y agrupados con
`agrupar_episodios` (primera alerta por contrato y direccion dentro de 5
minutos). Es la senal de referencia del proyecto y la unica familia con
cobertura suficiente (279 episodios completos).

**Secundaria (no decide):** episodios del patron con flujo y profundidad
(`SECUENCIA-PRESION-V1`). Solo 2 episodios completos en las capturas distintas
de la ventana 4; se reportan y no se usan para el veredicto.

Capturas incluidas: `exp-v2-ventana-1-20261112a` (0 casos, sin flujo),
`exp-v2-ventana-2-20261112a`, `exp-v2-ventana-3-20261115a`,
`public-pilot-1h-20261105a`, `public-pilot-1h-20261106a`.
La ventana 4 queda excluida: formula la hipotesis, no la confirma.

## Definicion unica de extension

Para un episodio con primer minuto de senal `t1` y corte `C`:

- `avance_senal = |close(t3) / close(t1) - 1|`, donde `t1, t2, t3` son los tres
  minutos contiguos de la senal y `close` es `research_flow_1m.price_close`.
- **Bloques previos:** exactamente 6 bloques de 3 minutos contiguos y no
  solapados, inmediatamente anteriores a `t1`. El bloque `i` ocupa
  `[t1 - (7-i)*3 min, t1 - (6-i)*3 min)` para `i = 1..6`, de modo que el bloque 6
  termina donde empieza la senal y el bloque 1 es el mas antiguo. Cada minuto
  debe tener `data_quality = OK`, `price_open > 0`, `price_close > 0` y
  `as_of_ms <= C`.
- `avance_bloque_i = |close(ultimo minuto del bloque i) / close(primer minuto del
  bloque i) - 1|`.
- `extension = avance_senal / mediana(avance_bloque_1..6)`.
- Si `mediana(...) = 0` el episodio es `no_evaluable`
  (`mediana_previa_nula`), porque el cociente no esta definido.

Ningun parametro de esta definicion depende de los retornos.

## Grupos

- `EXTENDIDO` si `extension > 1.0`: el movimiento de la senal supera la mediana
  de los movimientos de 3 minutos del propio contrato en los 18 minutos previos.
- `NORMAL` si `extension <= 1.0`.

El umbral `1.0` es la mediana propia del contrato, no un valor ajustado. Como
descriptivo secundario, sin valor de decision, se reportan terciles de
`extension`.

## Retorno comparado

Mismo corte, misma entrada simulada y mismo horizonte en ambos grupos:

- entrada = apertura del minuto siguiente al corte,
  `(C // 60 s + 1) * 60 s`, con `research_flow_1m.price_open`;
- salida = apertura de `entrada + 5 min`, con `research_flow_1m.price_open`;
- `retorno_bruto_bps = signo * (salida / entrada - 1) * 10 000`, con
  `signo = +1` para LONG y `-1` para SHORT;
- `retorno_neto_bps = retorno_bruto_bps - 16`, coste simulado de ida y vuelta
  (8 bps por lado) aplicado por igual a los dos grupos;
- `funding = UNKNOWN`: no se simula ni se estima.

Los precios son aperturas simuladas, no fills acreditados.

## Comparacion y criterio

El filtro propuesto **descarta** los episodios `EXTENDIDO` y conserva los
`NORMAL`. Se informa:

- cuantos episodios descarta el filtro;
- perdidas evitadas = suma de retornos netos negativos descartados;
- ganancias dejadas pasar = suma de retornos netos positivos descartados;
- media y mediana netas de cada grupo, y su diferencia;
- desglose por direccion (LONG/SHORT), por captura y por contrato;
- concentracion: cuota del contrato con mas episodios y efecto de excluirlo.

**Minimo evaluable:** 30 episodios en **cada** grupo. Si un grupo no alcanza 30,
el veredicto es `DATOS INSUFICIENTES` y se indica fuente, campo y cuantos casos
quedan fuera.

**Criterio de conservacion (predeclarado).** La hipotesis se conserva solo si se
cumplen las cinco condiciones:

1. mediana neta de `NORMAL` > mediana neta de `EXTENDIDO`;
2. media neta de `NORMAL` > media neta de `EXTENDIDO`;
3. la condicion 1 se mantiene al excluir todos los episodios del contrato con
   mas episodios evaluables;
4. la condicion 1 se mantiene en al menos 2 capturas distintas;
5. la condicion 1 se mantiene al excluir el episodio de mayor `|retorno neto|`
   del conjunto.

Si falla cualquiera de las cinco, la hipotesis se descarta en esta muestra.

## Veredicto

Un unico veredicto, con este mapeo fijado de antemano:

- `DATOS INSUFICIENTES`: algun grupo tiene menos de 30 episodios evaluables.
- `APORTA EVIDENCIA`: se cumplen las cinco condiciones. Justifica otra
  validacion; **no** activa el filtro ni cambia el bot.
- `NO APORTA`: hay cobertura suficiente pero falla al menos una condicion.

Se reporta tambien un intervalo bootstrap descriptivo de la diferencia de medias
(1000 remuestreos, semilla 42). Es informativo: no forma parte del criterio.

## Lo que no se hace

- No se ajustan umbrales, grupos, minimo ni criterio despues de ver retornos.
- No se invierte la direccion de la senal ni se mueve la entrada.
- No se usa la ventana 4 para confirmar.
- No se abren capturas nuevas ni se consulta Binance.
- No se toca el detector, el motor, el dashboard ni la estrategia del bot.
- No se simula funding ni se estiman costes distintos de los 16 bps declarados.
- No se promueve la regla: si aporta evidencia, solo justifica otra validacion
  con `run_id` nuevo y grupos predeclarados de al menos 30 episodios cada uno.
