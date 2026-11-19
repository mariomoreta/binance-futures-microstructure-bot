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
| `limite` | `kind`, `version`, `run_id`, `symbol`, `received_ms`, `seq`, `motivo`, `filas_escritas`, `bytes_escritos` |

`event_ms` es la marca del evento y `received_ms` el reloj del piloto al
procesarlo. `bid_qty` y `ask_qty` son las cantidades **en la punta**, no la suma
de los 20 niveles.

### Cuando se escribe

- Una fila `cotizacion` por simbolo y **primer snapshot aceptado de cada segundo
  de recepcion** (`received_ms // 1000`); los demas snapshots del mismo segundo
  se descuentan en `duplicated_seconds`. Una cotizacion invalida dentro del
  mismo segundo **sí** se escribe para registrar la ruptura de cobertura.
  Cadencia: `1 000 ms`.
- Una fila `faltante` al retirar un simbolo del seguimiento por rotacion
  (`simbolo_fuera_de_seguimiento`). No modifica el selector.
- Una fila `limite` al alcanzar `max_rows` o `max_bytes`; desde entonces dejan
  de escribirse cotizaciones, pero el piloto sigue con su registro normal.

### Como se recupera

`quote_tape.leer_tape(ruta)` lee el JSONL persistido. Para cada extremo,
`seleccionar(symbol, instante, filas, run_id, max_edad_ms=5_000)` mantiene un
automa de cobertura en orden cronologico hasta el instante: una cotizacion
valida establece cobertura; una invalidez (rotacion, salto de secuencia,
perdida de calidad o fila `faltante`) la rompe; solo una cotizacion valida
posterior la restablece. Nunca se retrocede a una cotizacion previa despues de
una invalidez. Nunca se usa una fila recibida despues del instante.
`evaluar_episodio(...)` compara los dos extremos. Nada se lee del estado en
memoria ni del frontend. No se desplaza entrada ni salida para buscar precio.

**Frescura no equivale a cobertura.** Si consta que la cinta se agoto pero no
se sabe cuando (`cap_instante_ms` ausente), el lector declara
`COBERTURA_UNKNOWN` para el tramo afectado aunque la ultima cita siga fresca:
no se puede acreditar que la cita prediga al agotamiento.

`quote_tape.replay_episodio_desde_corrida(run_dir, symbol, entrada_ms,
salida_ms, lado, size, run_id=...)` es la entrada pública de replay: lee
`cotizaciones_investigacion.jsonl` y `resumen.json` del directorio de la
corrida, comprueba que pertenecen al mismo `run_id`, construye internamente la
evidencia de agotamiento (el llamador no la pasa) y reutiliza
`evaluar_episodio()`. Conserva la entrada acreditada anterior al corte; desde
el corte inclusive devuelve `LIMITE_ALCANZADO` aunque la ultima cita siga
fresca y no haya cabido la marca final en el JSONL.

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

Invalidez sin recuperacion: cotizacion valida seguida de salto de secuencia
sin libro valido posterior -> salida no evaluable con motivo `SALTO_SECUENCIA`.
Invalidez posterior al instante de entrada: no altera la cotizacion valida en
entrada (la fila invalida es posterior a T y no se usa). Cinta agotada antes de
la salida: `LIMITE_ALCANZADO`, distinguible de `SIN_COTIZACION`.
Cinta agotada pero sin instante verificable (`cap_instante_ms` ausente):
`COBERTURA_UNKNOWN` para el tramo cuya cobertura no se pueda acreditar; la
frescura de una cita no equivale a cobertura.

## 4. Topes, bytes y proyeccion

- Topes declarados: `20 000` filas de datos y `4 194 304` bytes (4 MiB).
- Medido en el archivo de las dos trazas: `3 965` bytes para `9` filas,
  `440.6 bytes/fila`. La proyeccion usa `512 bytes/fila` (conservadora).
- Prueba de limite con `max_rows=3`: exactamente 3 cotizaciones, 1 fila
  `limite` con `limite_filas`, 5 observaciones del piloto escritas igualmente,
  salida limpia. Con `max_bytes=1` no se escribe ninguna cotizacion y el motivo
  es `limite_bytes`. El piloto no se detiene en ninguno de los dos casos.
- Capacidad de la cinta: el tope que se agota PRIMERO (filas o bytes).
  Con 4 MiB y 512 B/fila el techo teorico por bytes es 8 192 filas; con
  20 simbolos a 1 fila/s son 409,6 s (~6 min 50 s) **antes de reservar espacio
  para marcas**. El techo por filas es 20 000 filas (~16,67 min). Se usa el
  minimo de ambos. Tras reservar espacio para filas de marca (una fila `limite`
  global + hasta 2 filas `faltante` por simbolo por rotacion), las filas
  efectivas son 8 151 y la cobertura es ~6,79 min con 20 simbolos a 1 s.
- Proyeccion con el universo actual (`max_symbols=20`) y cadencia de 1 s:

| configuracion | filas proyectadas | bytes proyectados | cobertura completa |
| --- | --- | --- | --- |
| 10 min, 20 simbolos | 12 000 | 6 144 000 | no (excede 4 MiB) |
| 4 h, 20 simbolos | 288 000 | 147 456 000 | no |

Con 20 simbolos, la cobertura efectiva de la cinta es ~6,79 min (limitada por
bytes, no por filas). Los ~16,67 min corresponden solo al limite de filas y
no son vinculantes. Ademas, el gate de presupuesto de la configuracion de
4 h **ya era insuficiente antes de anadir la cinta** (`134 153 272` bytes
previstos frente al techo configurado). No se aumentaron cupos ni se relajo
ningun presupuesto: la cinta respeta el presupuesto general y se autolimita.
La configuracion corta de 10 min con cinta cierra el gate
(`cabe_en_limites: true`) pero no llega a cubrir los 10 min completos por el
tope de bytes.

- `--budget-only` distingue tres cosas independientes:
  1. `gate.cabe_en_limites`: el piloto cabe dentro de todos los presupuestos
     (HTTP, almacenamiento, WS, etc.).
  2. `cotizaciones_investigacion.minutos_cubiertos_por_tope`: duracion
     estimada de la cinta, calculada como `filas_efectivas * cadencia_s /
     simbolos / 60` (multiplicar por el intervalo entre filas, no dividir).
     Una fila cada 2 s cubre el doble de tiempo que una cada 1 s.
  3. `cotizaciones_investigacion.cubre_hasta_ultima_salida`: si la cinta
     cubre desde la ultima entrada admitida hasta su salida (entrada + 300 000 ms),
     verificando que el feed esta previsto hasta ese instante. Requiere
     `--quote-tape-ultima-entrada-ms-desde-inicio` (ms desde el inicio de la
     captura, no hora de epocha). El fin del feed se deriva de
     `duration_seconds * 1000`; un fin declarado mas tarde no puede extender
     la cobertura. Sin `ultima_entrada_ms_desde_inicio` no se declara cobertura.
  Una aprobacion del presupuesto general **no acredita** cobertura de
  cotizaciones.

## 5. Codigos y pruebas

- `scripts/quote_tape.py`: escritor/lector/evaluador y entrada pública de
  replay `replay_episodio_desde_corrida`. El lector `seleccionar`
  mantiene un automa de cobertura: una cotizacion valida establece cobertura,
  una invalidez (rotacion, salto de secuencia, perdida de calidad o fila
  `faltante`) la rompe, y solo una cotizacion valida posterior la restablece.
  Nunca se retrocede a una cotizacion previa despues de una invalidez. El
  muestreo de una fila por segundo no oculta una invalidacion dentro del
  mismo segundo: una cotizacion invalida en el mismo segundo se escribe para
  registrar la ruptura de cobertura. Dentro del mismo `run_id`, las filas se
  ordenan primero por `received_ms` y se desempata por `seq` persistido;
  `event_ms` solo se usa para disponibilidad y frescura, nunca para ordenar
  retroactivamente. Cuando el tope de bytes o filas impide escribir incluso
  la fila `limite`, el piloto persiste el instante y motivo de agotamiento
  en `resumen.json` (`cap_reached`, `cap_reason`, `cap_instante_ms`);
  el replay lee ese artefacto y, a partir de `cap_instante_ms`, devuelve
  `LIMITE_ALCANZADO` aunque el JSONL no tenga fila `limite`. Si se sabe que
  se agoto pero no cuando, declara `COBERTURA_UNKNOWN` (frescura no equivale
  a cobertura).
- `scripts/research_pilot.py`: flag, archivo, presupuesto, enganche de lectura
  y de rotacion, estado en `estado.json` y `resumen.json`.
- `tests/test_quote_tape.py`: 44 pruebas puras (cadencia, esquema, calidad,
  seleccion, limites, descomposicion, maquina de cobertura, orden de estados
  en el mismo milisegundo, agotamiento sin marca, cinta agotada distinguible
  de sin cotizacion, evaluar_episodio con agotamiento, replay desde archivos
  de corrida: agotamiento sin hora y resumen ausente).
- `tests/test_cotizaciones_local_piloto.py`: 23 pruebas de cadena completa
  (trazas LONG/SHORT, exclusiones, rotacion, limite, desactivado,
  presupuesto con/sin red, recuperacion de cobertura despues de invalidez,
  invalidez sin recuperacion, invalidez posterior a entrada, cinta agotada
  antes de salida, agotamiento por bytes sin marca en JSONL, cadencia 2 s,
  cobertura hasta ultima salida, replay publico desde archivos de corrida:
  entrada conservada/salida rechazada, episodio valido sin agotamiento,
  run_id distinto no evaluable).
- `scripts/generar_evidencia_cotizaciones_local.py`: regenera
  `C-evidencia.json` con el mismo recorrido deterministico.
- Verificacion: `64 passed` en los dos archivos de prueba del registro.
- Comandos: `python -m pytest tests\test_quote_tape.py tests\test_cotizaciones_local_piloto.py -q`
  y `python scripts\generar_evidencia_cotizaciones_local.py`.

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
