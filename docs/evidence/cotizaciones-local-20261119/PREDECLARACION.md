# Predeclaracion: registro local de cotizaciones para coste de ejecucion

Fecha de escritura: 2026-11-19T12:53Z.
Base publicada: `e5ba321313a05ffd63b38de107592b965d95e665`
(`research/universe-liquidez-v1`).

Escrita y publicada **antes** de implementar el registro, de ejecutar la
aceptacion local y de calcular ningun retorno. El inventario historico
(`0/278` pares) queda cerrado: este bloque no lo reabre, no lo modifica y no
cambia sus numeros.

## Pregunta acotada

Reutilizando las cotizaciones que `BookEngine` ya calcula, es posible recuperar
best bid y best ask en los dos extremos de un episodio simulado, con el
recorrido real del piloto, proveedores loopback, reloj controlado y
almacenamiento temporal? No se pregunta por rentabilidad ni por cobertura
publica.

## Fuente y contenido de una fila

La unica fuente es el snapshot de libro aceptado por `BookEngine` en
`ResearchPilot.handle_message`. Se reutilizan `features` del propio motor:
`best_bid`, `best_ask`, `top_bid_qty`, `top_ask_qty`, `mid`, `spread_bps`,
`crossed`, `bid_levels`, `ask_levels`, `degraded` y el indicador de salto de
secuencia (`gap`). No se guarda el libro completo: solo la punta y la calidad.

Cada fila lleva `run_id`, `symbol`, `event_ms` (marca del evento), `received_ms`
(reloj del piloto al procesarlo), `seq` (orden de escritura), `cadencia_ms` y
los campos anteriores. Ademas se escriben filas `faltante` (simbolo retirado del
seguimiento, con motivo) y `limite` (tope alcanzado, con contadores).

## Cuando se guarda una fila (fijado antes de probar)

- El registro esta **desactivado por defecto**; requiere habilitacion explicita
  del piloto. Desactivado no escribe nada y no cambia ningun contador ni salida
  existente.
- Con el registro activo se escribe **la primer actualizacion de libro aceptada
  de cada segundo de recepcion** por simbolo (`received_ms // 1000`). Cadencia
  declarada: `1 000 ms`. Una segunda actualizacion dentro del mismo segundo no
  anade fila.
- Se escribe tambien una fila `faltante` al retirar un simbolo del seguimiento
  (`simbolo_fuera_de_seguimiento`) y una fila `limite` cuando se alcanza el tope
  de filas o de bytes. Ninguna de las dos modifica la seleccion.
- El archivo es `cotizaciones_investigacion.jsonl` dentro del `out_dir` del
  piloto, con el mismo `PilotStore` acotado que ya usa el piloto. Se contabiliza
  en el presupuesto de almacenamiento de la corrida.

## Antiguedad maxima (fijada antes de probar)

`MAX_EDAD_MS = 5 000`.

Para un instante `T` (entrada o salida) solo se admite una fila si:

1. `kind == "cotizacion"` y `simbolo` coincide;
2. `received_ms <= T` (ya recibida en ese momento; nunca del futuro);
3. `event_ms <= T` y `T - event_ms <= 5 000 ms`;
4. la fila es valida segun la calidad de abajo.

Se elige la fila admisible con mayor `received_ms`; desempate por mayor
`event_ms` y luego mayor `seq`. No se desplaza ni la entrada ni la salida para
encontrar precio.

## Calidad (fijada antes de probar)

`valida == true` exige: `best_bid > 0`, `best_ask > 0`, `best_ask > best_bid`,
precios y cantidades finitos, `top_bid_qty > 0`, `top_ask_qty > 0`,
`crossed == false`, `degraded == false`, `gap == false` y al menos un nivel por
lado. Codigos de exclusion: `LIBRO_CRUZADO`, `LIBRO_DEGRADADO`,
`SALTO_SECUENCIA`, `PRECIO_NO_VALIDO`, `CANTIDAD_NO_VALIDA`, `SIN_NIVELES`,
`COTIZACION_FUTURA` y `COTIZACION_VIEJA`.

Si un simbolo sale del seguimiento, la evaluacion del extremo correspondiente
devuelve `SIMBOLO_FUERA_DE_SEGUIMIENTO` con la fila `faltante` como origen; no
se inventa precio ni se cambia el selector.

## Tamano y suficiencia de la punta

Tamano simulado declarado: `1.0` unidad base para los episodios aceptados;
`50.0` unidades base para el caso de prueba de punta insuficiente.

- LONG: entra al `best_ask`, sale al `best_bid`.
- SHORT: entra al `best_bid`, sale al `best_ask`.
- Se exige que la cantidad visible en la punta usada en cada extremo cubra el
  tamano simulado. Si no lo cubre, `evaluable = false` con motivo
  `TAMANO_INSUFICIENTE`; **no** se atribuye el precio de la punta a toda la
  posicion.

## Descomposicion del retorno (fijada antes de probar)

- `retorno_referencia_precio_bps`: precio de referencia de solo precio
  (apertura de la vela 1m del extremo), con su signo segun LONG/SHORT.
- `retorno_referencia_mid_bps`: `(mid_salida / mid_entrada - 1) · 10 000`
  con signo segun LONG/SHORT, calculado con los mids de las mismas dos filas.
- `retorno_cruce_bps`: mismo calculo con los precios de punta cruzados
  (entrada y salida). Es retorno de **precios cotizados**, no de fills.
- `coste_spread_bps = retorno_referencia_mid_bps - retorno_cruce_bps`: una sola
  resta sobre el par de cotizaciones. Nunca se resta el spread completo dos
  veces ni se mezcla con la referencia de precio.
- `comision_bps`, `slippage_adicional_bps`, `funding_bps`: `UNKNOWN` mientras
  no haya evidencia en la corrida; nunca cero.
- `retorno_neto_bps`: `UNKNOWN` mientras falte cualquiera de los anteriores.
  No se publica un neto completo.

## Topes y proyeccion (fijados antes de probar)

- `quote_tape_max_rows = 20 000` filas.
- `quote_tape_max_bytes = 4 194 304` bytes (4 MiB).
- Si se alcanza cualquiera de los dos topes: se escribe una fila `limite` si
  cabe, dejan de escribirse cotizaciones nuevas y el piloto continua con su
  registro normal. No se aumentan cupos de simbolos, horarios ni presupuesto
  general.

La proyeccion se calcula con el universo y la rotacion actuales del piloto y se
reporta junto a los bytes medidos; si el tope no cubre una captura publica
completa, se dice explicitamente.

## Criterio de aceptacion local

Se acepta el recorrido solo si, desde filas persistidas y sin reutilizar estado
en memoria:

1. aparece una traza LONG con entrada al ask y salida al bid, y una traza SHORT
   con entrada al bid y salida al ask;
2. ambas traen `run_id`, timestamps, cantidades y calidad, con sus filas fuente;
3. los casos punta insuficiente, posterior, vieja, cruzada, calidad no valida,
   rotacion y hueco se rechazan con motivo explicito;
4. la descomposicion separa referencia, cruce y spread sin duplicarlo, con
   comision/slippage/funding `UNKNOWN`;
5. el registro desactivado no produce archivo y el activo respeta sus topes sin
   detener el piloto.

La aceptacion local **no** acredita cobertura publica: eso queda para una
captura futura con autorizacion separada.

## Declaracion

Al escribir esta predeclaracion no se ha implementado el registro, no se ha
ejecutado ninguna prueba de aceptacion y no se ha calculado retorno alguno.
