# Aceptacion local: cotizaciones de best bid/ask para episodios simulados

Fecha: 2026-11-19. Base: `e5ba321313a05ffd63b38de107592b965d95e665`.
Predeclaracion publicada **antes** de implementar o probar:
`43e1238ef19b2dfcd8f41f5e7bb7e12d42ca70c0`
([`PREDECLARACION.md`](PREDECLARACION.md)).

**Resultado: ACEPTADO LOCALMENTE.** No se abre una captura publica, no se
conecta a Binance, no se cambia la estrategia, el horizonte, el selector ni el
motor de trading. El inventario historico de `0/278` pares con bid/ask en ambos
extremos permanece cerrado y sin modificaciones.

## 1. Que se anadio

`scripts/quote_tape.py` (nuevo): escritor acotado y lector/evaluador.
`scripts/research_pilot.py`: un flag opt-in `--quote-tape` (por defecto
**desactivado**) que crea `cotizaciones_investigacion.jsonl` en el `out_dir` con
el mismo `PilotStore` presupuestado del piloto. Sin el flag no se crea el
archivo, no se consume presupuesto y el resumen declara `enabled: false`.

La unica fuente es el snapshot que `BookEngine` ya acepta y del que ya se
calculan features para `observaciones.jsonl`. No se guarda el libro completo:
solo la punta, cantidades visibles, timestamps y calidad.

### Esquema (campos congelados)

| tipo | campos |
| --- | --- |
| `cotizacion` | `kind`, `version`, `run_id`, `symbol`, `event_ms`, `received_ms`, `seq`, `best_bid`, `best_ask`, `bid_qty`, `ask_qty`, `bid_levels`, `ask_levels`, `mid`, `spread_bps`, `degraded`, `gap`, `crossed`, `valida`, `motivos_invalidez`, `cadencia_ms` |
| `faltante` | los anteriores de identificacion mas `motivo`, `detalle` |
| `limite` | `kind`, `version`, `run_id`, `seq`, `motivo`, `filas_escritas`, `bytes_escritos` |

`event_ms` es la marca del evento y `received_ms` el reloj del piloto al
procesarlo. `bid_qty` y `ask_qty` son las cantidades **en la punta**, no la suma
de los 20 niveles.

### Cuando se escribe

- Una fila `cotizacion` por simbolo y **primer snapshot aceptado de cada segundo
  de recepcion** (`received_ms // 1000`); los demas snapshots del mismo segundo
  se descuentan en `duplicated_seconds`. Cadencia: `1 000 ms`.
- Una fila `faltante` al retirar un simbolo del seguimiento por rotacion
  (`simbolo_fuera_de_seguimiento`). No modifica el selector.
- Una fila `limite` al alcanzar `max_rows` o `max_bytes`; desde entonces dejan
  de escribirse cotizaciones, pero el piloto sigue con su registro normal.

### Como se recupera

`quote_tape.leer_tape(ruta)` lee el JSONL persistido. Para cada extremo,
`seleccionar(symbol, instante, filas, run_id, max_edad_ms=5_000)` elige la ultima
fila valida con `received_ms <= instante`, `event_ms <= instante` y
`instante - event_ms <= 5 000 ms` (desempate: `received_ms`, `event_ms`, `seq`).
`evaluar_episodio(...)` compara los dos extremos. Nada se lee del estado en
memoria ni del frontend. No se desplaza entrada ni salida para buscar precio.

En el recorrido de prueba `PilotRun.step` publica `E = T` con el reloj controlado
en `T - 1 000 ms`; por diseno de la sincronizacion determinista del harness.
La regla de no futuro se aplica al instante de decision (`received_ms <= T`),
que es lo que impide adelantar una cotizacion.

## 2. Trazas LONG y SHORT (recuperadas de lo persistido)

Recorrido real del piloto con HTTP/WS loopback, reloj manual y `tmp_path`.
`decision_ms=1735689660000`, `entrada_ms=1735689720000` (apertura del minuto
siguiente), `salida_ms=1735690020000` (entrada + 5 min). Tamano simulado `1.0`
unidad base; cantidad visible en punta `10.0` en los cuatro extremos.

| lado | simbolo | entra | sale | ref. precio (bps) | ref. mid (bps) | cruce (bps) | spread (bps) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LONG | AAAUSDT | ask `1000.3` | bid `999.9` | -1.9996 | -1.9996 | -3.9988 | +1.9992 |
| SHORT | BBBUSDT | bid `1010.102` | ask `1010.1` | +1.9996 | +1.9996 | +0.0198 | +1.9798 |

Filas fuente de LONG (seq, `event_ms`, `received_ms`, bid, ask, qty bid, qty ask):

- `6`, `1735689720000`, `1735689719000`, `1000.1`, `1000.3`, `10.0`, `10.0`
- `7`, `1735690020000`, `1735690019000`, `999.9`, `1000.1`, `10.0`, `10.0`

Filas fuente de SHORT:

- `8`, `1735689720000`, `1735689719000`, `1010.102`, `1010.302`, `10.0`, `10.0`
- `9`, `1735690020000`, `1735690019000`, `1009.9`, `1010.1`, `10.0`, `10.0`

`comision_bps`, `slippage_adicional_bps`, `funding_bps` y `retorno_neto_bps` son
`UNKNOWN` en ambas trazas. `precios_son_fills: false`: son precios cotizados,
no ejecuciones. `coste_spread_bps` es una sola resta
(`retorno_referencia_mid_bps - retorno_cruce_bps`), no un doble cargo. El
retorno de referencia de precio (velas 1m del mismo proveedor loopback) se
reporta separado. Los numeros completos, con las filas fuente, estan en
[`C-evidencia.json`](C-evidencia.json).

## 3. Casos excluidos

| caso | simbolo | codigo observado |
| --- | --- | --- |
| recibida 2 s despues del instante | AAAUSDT | `COTIZACION_FUTURA` |
| recibida 20 s antes (maximo 5 s) | BBBUSDT | `COTIZACION_VIEJA` |
| bid 2000.0 >= ask 1999.0 | DDDUSDT | `LIBRO_CRUZADO` |
| `pu` incorrecto tras lectura previa | EEEUSDT | `SALTO_SECUENCIA` (con `LIBRO_DEGRADADO`) |
| punta visible 0.5 < size 1.0 | CCCUSDT | `TAMANO_INSUFICIENTE`, sin retorno de cruce |

Rotacion: al cambiar el conjunto seguido en `T0+2min` se escribieron 4 filas
`faltante`, una por simbolo retirado (`ROT0..ROT3USDT`); la evaluacion de
cualquiera de ellos devuelve `SIMBOLO_FUERA_DE_SEGUIMIENTO` con su fila como
origen. No se inventa precio ni se altera la seleccion.

## 4. Topes, bytes y proyeccion

- Topes declarados: `20 000` filas de datos y `4 194 304` bytes (4 MiB).
- Medido en el archivo de las dos trazas: `3 965` bytes para `9` filas,
  `440.6 bytes/fila`. La proyeccion usa `512 bytes/fila` (conservadora).
- Prueba de limite con `max_rows=3`: exactamente 3 cotizaciones, 1 fila
  `limite` con `limite_filas`, 5 observaciones del piloto escritas igualmente,
  salida limpia. Con `max_bytes=1` no se escribe ninguna cotizacion y el motivo
  es `limite_bytes`. El piloto no se detiene en ninguno de los dos casos.
- Proyeccion con el universo actual (`max_symbols=20`) y cadencia de 1 s:

| configuracion | filas proyectadas | bytes proyectados | cobertura completa |
| --- | --- | --- | --- |
| 10 min, 20 simbolos | 12 000 | 6 144 000 | no (excede 4 MiB) |
| 4 h, 20 simbolos | 288 000 | 147 456 000 | no |

Con 20 simbolos el tope de 20 000 filas cubre ~16.67 min. Ademas, el gate de
presupuesto de la configuracion de 4 h **ya era insuficiente antes de anadir la
cinta** (`134 153 272` bytes previstos frente al techo configurado). No se
aumentaron cupos ni se relajo ningun presupuesto: la cinta respe ta el
presupuesto general y se autolimita. La configuracion corta de 10 min con cinta
si cierra el gate (`cabe_en_limites: true`) pero no llega a cubrir los 10 min
completos por el tope de bytes.

## 5. Codigos y pruebas

- `scripts/quote_tape.py`: escritor/lector/evaluador.
- `scripts/research_pilot.py`: flag, archivo, presupuesto, enganche de lectura y
  de rotacion, estado en `estado.json` y `resumen.json`.
- `tests/test_quote_tape.py`: 29 pruebas puras (cadencia, esquema, calidad,
  seleccion, limites, descomposicion).
- `tests/test_cotizaciones_local_piloto.py`: 7 pruebas de cadena completa
  (trazas, exclusiones, rotacion, limite, desactivado, presupuesto con/sin red).
- `scripts/generar_evidencia_cotizaciones_local.py`: regenera
  `C-evidencia.json` con el mismo recorrido deterministico.
- Verificacion: `36 passed` en los dos archivos nuevos; `105 passed` en el
  bloque focalizado (`test_research_pilot`, ambos nuevos, `test_coste_ejecucion`
  y `test_operativo_replay_offline`). En una de las corridas del bloque dos
  pruebas preexistentes de `test_operativo_replay_offline` fallaron por la
  sincronizacion de reloj del harness al compartir proceso; pasaron aisladas y
  en la corrida seguinte del bloque completo. No afectan al registro nuevo ni
  a la evidencia publicada. `test_engineering_clock_budget.py` no se incluye:
  tiene un error de sintaxis preexistente en la linea 881 en archivo ajeno.
- Comandos: `python -m pytest tests\test_quote_tape.py tests\test_cotizaciones_local_piloto.py -q`
  y `python scripts\generar_evidencia_cotizaciones_local.py`. Dos regeneraciones
  consecutivas dieron el mismo SHA-256
  `c02b4ca4a3d71c2d48a7b95851d9941a60f979a92b6385ed49e45374feb93bff`.

## 6. Lo que esto acredita y lo que no

**Acredita localmente:** que la idea es implementable reutilizando `BookEngine`
y el almacenamiento del piloto; que se pueden recuperar dos cotizaciones
validas en entrada y salida a 5 min desde el JSONL persistido; que LONG y SHORT
tienen sentidos de cruce distintos; que los casos invalidos se rechazan con
motivo; que la descomposicion no duplica el spread; que el registro es acotado,
opcional y no detiene al piloto.

**No acredita:** cobertura en una captura publica; que los precios sean fills;
comision, slippage adicional ni funding; rentabilidad; ni ningun cambio de
estrategia. Para cualquier captura publica haria falta autorizacion separada y
una decision explicita sobre el tamano de la cinta y el presupuesto.
