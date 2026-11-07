# Traza compacta del recorrido integrado operativo v2

**Base:** `research/universe-liquidez-v1` en `a1f7927c55faf80e2ad610537e010bd0954b565e`.
**Motor:** `paper_lab_engine` + `backtest_offline` (única autoridad económica).
**Datos:** fixture local cronológica (velas 1m), sin Binance, sin feed vivo, sin órdenes reales.

## Recorrido (ejemplo LONG, dirección derivada de información de mercado)

```
información de mercado en T (move_24h_pct = +2.4)
  -> derivar_direccion_desde_movimiento() -> LONG  (campo: move_24h_pct, unidades: %,
     instante: T, fórmula: >0 LONG / <0 SHORT / ==0 sin señal / None dato ausente)
  -> misma función y configuración para candidato y comparador (el rol no determina dirección)
  -> configuración/señal (RULE-CAUSAL-V1, entry_px=close de vela conocida en T, stop 0,5 %)
  -> motor existente (create_session → evaluate_session → step_forward)
  -> entrada (fill en open de vela siguiente, nunca open pasado)
  -> gestión/salida (stop / horizonte / agotamiento)
  -> resultado (costes contabilizados, funding UNKNOWN sin calendario)
```

| Paso | Valor | Observación |
|---|---|---|
| Dato de movimiento en T | `move_24h_pct = +2.4` (%) | Fixture aporta el dato; no se asigna LONG/SHORT por sustituto |
| Dirección derivada | `LONG` | `derivar_direccion_desde_movimiento(+2.4)` → motivo `movimiento_alcista` |
| Instante de decisión T | `119 000 ms` | close de vela de señal conocido (102.0) |
| entry_px (referencia de señal) | `102.0` | No es el fill; fill_px en T = None |
| stop_px (referencia de señal) | `101.49` | 102 × (1 − 0.005); stop_fraction = 0.5 / 100 |
| Decisión | `ENTRADA_SIMULADA` | Stop no vulnerado en T (low=101.5 > 101.49) |
| Fill | `102.0` @ `120 000 ms` | Open de vela siguiente a la señal (nunca open pasado 101) |
| qty | `9.8039215686` | notional 1000 / 102 |
| Stop efectivo (rige la operación) | `101.49` | entry ejecutada × (1 − 0,005); config.stop_px es solo referencia |
| Salida | `stop` | Toque al conocerse close de vela de entrada |
| exit_px | `101.49` | Al stop (modelo existente) |
| exit_ms | `180 000` | close_time de la vela que confirma el toque |
| exit_executed | `true` | Salida ejecutada |
| open_at_end | `false` | No es agotamiento |
| entry_fees (ejecutado) | `0.5000` | 1000 × 5 bps / 10 000 |
| exit_fees (ejecutado) | `0.4975` | 102 × 9.8039 × 5 bps / 10 000 (salida sobre valor de salida) |
| entry spread/slippage | `0.3000` | 1000 × (1+2) bps / 10 000 |
| exit spread/slippage | `0.2985` | 101.49 × 9.8039 × 3 bps / 10 000 |
| funding | `None` (UNKNOWN) | Sin calendario de funding real; nunca se convierte en cero |
| P&L bruto | `-5.0000` | (101.49 − 102) × 9.8039 |
| P&L neto | `-6.5960` | bruto − comisiones − spread/slippage (sin funding) |

## Casos acreditados en este bloque (tests/test_operativo_local_v2.py)

- Dirección común desde movimiento: LONG (+), SHORT (−), sin señal (0), dato ausente (None). Misma función para candidato y comparador.
- Entrada causal LONG y SHORT: fill en open de vela siguiente, nunca open pasado de la vela de señal.
- Salida ejecutada por horizonte: 60 min alcanzados (`exit_executed=true`, `reason=horizon`, precio y tiempo).
- Agotamiento de datos: `open_at_end=true`, `exit_executed=false`, sin salida ni realizado inventados.
- Stop intravela: toque con precio según modelo (LONG y SHORT).
- Gap auténtico: ninguna vela anterior activa el stop; la apertura posterior cruza y sale al precio disponible tras el salto (no al stop nominal).
- Abstención: dato ausente o condición no satisfecha, con motivo explícito (temporal).
- Concurrencia `max_concurrent=1`: señales simultáneas, prioridad determinista `(event_time_ms, symbol)`, una admitida, la otra rechazada por capacidad (`skipped_overlap=1`), sin elegir por retorno posterior.
- Contabilidad independiente: LONG y SHORT recalculados a mano (cantidad, bruto, comisiones, spread/slippage, funding=None, neto) sin usar el mismo helper para el esperado.

## Regresiones ejecutadas

`tests/test_paper_lab_engine.py`, `tests/test_experimento_operativo_local.py`,
`tests/test_backtest_offline.py`, `tests/test_operativo_local_v2.py` → **73 passed**.

## Recorrido conectado ejecutado (dato de movimiento -> motor)

El camino se ejecuta realmente desde un dato de mercado en T, no desde una
dirección escrita a mano en la fixture:

```
dato de movimiento en T (move_24h_pct)
  -> derivar_direccion_desde_movimiento()  (misma funcion para candidato y
     comparador; el rol no determina la direccion)
  -> direccion -> PaperSessionConfig.direction  (procede de la funcion)
  -> evaluate_session (senal causal) -> step_forward (fill en open de vela
     siguiente) -> gestion/salida -> resultado
```

Resultado del recorrido conectado generado por ejecución (ejemplo LONG):

| Campo | Valor | Origen |
|---|---|---|
| Dato original | `move_24h_pct = +2.4` (%) | Fixture de mercado en T |
| Dirección derivada | `LONG` | `derivar_direccion_desde_movimiento(+2.4)` |
| Dirección usada en config | `LONG` | Procede de la función, no de una constante |
| Decisión | `ENTRADA_SIMULADA` | `evaluate_session` en T=119000 |
| Fill | `102.0` @ `120 000 ms` | Open de vela siguiente a la señal |
| qty | `9.8039` | notional 1000 / 102 |
| Stop efectivo | `101.49` | entry ejecutada × (1 − 0,005) |
| Salida | `stop` @ `101.49` | Toque al conocerse close de vela de entrada |
| exit_executed | `true` | Salida ejecutada |
| P&L neto | `-6.596` | bruto − comisiones − spread/slippage |
| funding | `None` | Sin calendario de funding real |

**Presentación honesta de funding:** cuando `funding=None`, el importe neto
mostrado es un **resultado condicionado / sin funding conocido**, no un neto
completo. El desconocimiento del funding nunca se convierte en cero.

Resultado equivalente para movimiento negativo (`move_24h_pct = -1.8`):
dirección `SHORT`, fill `98.0` @ `120 000 ms`, salida `stop` @ `98.49`,
neto `-6.604`, funding `None` (sin funding conocido).

Casos de abstención conectados: dato ausente (`None`) → motivo
`dato_ausente: move_24h_pct no disponible en T`; movimiento sin señal (`0.0`)
→ motivo `sin_senal: move_24h_pct==0 (sin direccion)`. En ambos, sin fill ni
salida.

El mismo recorrido se ejecuta para candidato y comparador con idéntica regla y
configuración de costes/horario/stop; el rol candidate/comparator no influye
en la dirección.

## JSON de traza completa

`docs/evidence/operativo_local_v2/traza_recorrido_conectado.json` (traza del
recorrido conectado ejecutado: LONG, SHORT, dato ausente, sin señal) y
`docs/evidence/operativo_local_v2/traza_recorrido_integrado.json`
(estado de sesión del recorrido integrado anterior).

## Declaración de cierre

Esta prueba local acredita la **mecánica del recorrido** (causalidad, dirección común, entrada/fill, stop, gap, horizonte, agotamiento, abstención, concurrencia, contabilidad). **No acredita rentabilidad** y **no autoriza** las tres ventanas de captura pública ni ejecución real. Queda pendiente para una futura captura: datos de velas 1m con open/close conocidos causalmente, calendario de funding por símbolo, y autorización separada de presupuesto para ejecutar el protocolo v2 en ventanas separadas.
