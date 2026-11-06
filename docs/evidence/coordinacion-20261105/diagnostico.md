# Diagnóstico de coordinación del piloto (2026-11-05)

Rama `research/universe-liquidity-v1`, HEAD de partida `0c5bccb`
(`corrección de coordinación: seleccionar -> suscribir -> acumular ventana -> evaluar`).

Alcance: solo lectura de datos y proveedores loopback. Sin Binance, sin ventana
pública, sin órdenes, sin modificar datasets históricos ni reglas económicas.

## 1. Prueba exacta que fallaba

Conjunto afectado: `tests/test_research_pilot.py::TestCadenaSincronizada`
(7 pruebas). Las siete fallaban, no solo una:

```
FAILED tests/test_research_pilot.py::TestCadenaSincronizada::test_fin_de_settle_conserva_pendientes_con_causa
FAILED tests/test_research_pilot.py::TestCadenaSincronizada::test_fin_normal_maduran_resultados_durante_el_settle
FAILED tests/test_research_pilot.py::TestCadenaSincronizada::test_frescura_por_fuente_y_ventana_en_cadena_productiva
FAILED tests/test_research_pilot.py::TestCadenaSincronizada::test_horizontes_5m_15m_60m_por_avance_controlado
FAILED tests/test_research_pilot.py::TestCadenaSincronizada::test_parada_operador_no_consulta_mas_precios
FAILED tests/test_research_pilot.py::TestCadenaSincronizada::test_presupuesto_agotado_bloquea_el_siguiente_envio
FAILED tests/test_research_pilot.py::TestCadenaSincronizada::test_rotacion_conserva_resultados_y_acumulados_ws
7 failed, 21 deselected
```

### Traceback representativo (árbol de trabajo, antes del arreglo)

Salida completa en `fallos_antes.txt`. Extracto:

```
tests\test_research_pilot.py:1060: in test_frescura_por_fuente_y_ventana_en_cadena_productiva
    self.assertEqual(by_sym[symbol]["disponibilidad"]["libro_ms"], e0,
E   AssertionError: None != 1735689660000 : [
E     { "symbol": "AAAUSDT", "observation_id": "AAAUSDT|1735689660000",
E       "decision_ms": 1735689660000, "apto_para_evaluacion": false,
E       "estado": "descartada", "motivos": ["sin_libro", "sin_flujo"],
...
```

Y en las pruebas de cierre por settle:

```
tests\test_research_pilot.py:523: in wait_status
E   AssertionError: el piloto termino esperando settle iniciado: rc=0
    status={... "evaluations_run": 1, "observations_written": 5,
            "phase": "fin", "gate_decision_ms": 1735689660000 ...}
    stdout='{"run_id": "pilot-sync", ..., "aptas": 0, "no_aptas": 5, "resultados": 0}'
```

Lectura del fallo: el piloto evaluaba en `cut = 1735689660000` sin que la
recepción de libro y flujo estuviera confirmada para ese instante. Las cinco
observaciones salían `descartada` con `motivos: ["sin_libro","sin_flujo"]`
(`aptas: 0`), y el estado final publicaba `evaluations_run=1` sobre datos
inexistentes. Es un fallo de ordenación temporal (evaluar antes de recibir),
no de cálculo.

## 2. `compute_budget` no es la causa

Aclaración explícita porque el diagnóstico previo mezclaba ambos conceptos:

- `compute_budget(cfg)` (`scripts/research_pilot.py:690`) es una función pura
  de configuración: recibe `PilotConfig` y devuelve cotas (duración, ciclos,
  selecciones, símbolos, peso REST, conexiones WS, almacenamiento). No tiene
  `self`, no toca `self.book` y no puede producir `libro_ms = None`.
- `_book_records(now)` (`scripts/research_pilot.py:1246`) es el método de la
  instancia que consulta el libro: `self.book.snapshot_all(now)`; devuelve `{}`
  si `self.book is None`.

El `libro_ms = None` observado viene de un `snapshot_all` vacío o incompleto en
el instante del corte, es decir, de recepción no confirmada, no del presupuesto.

## 3. Traza de una instancia (creación → corte)

Generada con reloj manual (clock-file) y proveedores loopback, sin
`decision-gate-file`: `traza_instancia.json`.

| Fase | `now_ms` | `cycles_run` | `evaluations_run` | Observaciones |
| --- | --- | --- | --- | --- |
| creación, selección, engines, suscripción | 1735689600000 | 1 | 0 | — |
| recepción confirmada antes del corte | 1735689659000 | 1 | 0 | libro y flujo presentes |
| evaluación automática en el corte | 1735689660000 | 1 | 1 | 18 aptas, 0 descartadas |

Cadena verificada: `run_cycle()` selecciona y registra `cycle_id`, abre feeds,
el reloj avanza a `T0+59 s` con libro (`book_events`) y flujo
(`flow_events`, 60 trades por símbolo) ya recibidos, y a `T0+60 s` el corte
automático evalúa una vez. Observación resultante: `decision_ms = 1735689660000`,
`disponibilidad = {seleccion_ms: T0, libro_ms: T0+59 s, flujo_ms: T0+59 s,
max_ms: T0+60 s}`, `apto_para_evaluacion: true`, `ventana_completa: true`.

## 4. Reproducción en base aislada

Para descartar que el fallo fuera introducido por trabajo sin commitear, se
reprodujo el conjunto sobre un checkout aislado de `0c5bccb`
(`C:\Users\adonm\AppData\Local\Temp\opencode\base-0c5bccb`, detached HEAD), sin
tocar el árbol de trabajo ni hacer stash:

- Resultado: `7 failed, 21 deselected in 217.81s` (`base_aislada_0c5bccb.txt`).
- Causa allí: timeout esperando observaciones, porque el calentamiento se medía
  con `selection_seconds` (`timeout 30.0s esperando 5 observaciones con
  decision_ms=1735689660000`).
- Conclusión: el conjunto ya fallaba en la base publicada, con otro modo de
  fallo. No se usa como excusa: el modo de fallo del árbol de trabajo
  (evaluar antes de recibir) también se corrige.

## 5. Causa raíz y corrección

Causa raíz doble:

1. El calentamiento por símbolo se derivaba de `selection_seconds`, una cadencia
   de selección, no de la ventana de datos que la decisión necesita.
2. El corte de evaluación no esperaba a la recepción: se programaba en el
   instante de decisión y evaluaba con libro/flujo vacíos.

Corrección en `scripts/research_pilot.py`:

- `DECISION_FLOW_HORIZON = "1m"` y `symbol_warmup_ms =
  FLOW_HORIZONS_MS[DECISION_FLOW_HORIZON]` (60 s), independiente de
  `selection_seconds`.
- Solo símbolos nuevos o reincorporados renuevan `symbol_first_seen_ms`; los que
  continúan conservan su marca.
- `_ready_symbols(now)` y `_earliest_ready_ms()` calculan readiness por
  `first_seen + warmup`; `_symbols_evaluated_this_cycle` limita a una
  observación por símbolo y ciclo.
- Bucle automático (`ProductRun`/CLI, sin barrera manual): corte en
  `max(corte_actual, min(first_seen) + warmup)`; después avanza
  `cycle_seconds`; si no se escribió ninguna observación se reprograma a
  `siguiente_calentamiento`. Un símbolo listo a mitad de ciclo se evalúa antes
  de la siguiente selección.
- `decision-gate-file` queda solo como control explícito de las pruebas de
  cadena; la ruta productiva no tiene barrera.
- Estado publicado: `symbol_warmup_ms`, `symbol_first_seen_ms`,
  `symbols_evaluated_this_cycle`.

Protocolo de prueba adaptado: se publica y confirma la recepción con
`event_ms = cut` estando el reloj un segundo antes del corte, y luego el reloj
avanza hasta el corte. Los controles de cada prueba (rotación, presupuesto,
parada de operador, settle, frescura por fuente) se conservan.

## 6. Evidencia posterior

| Comando | Resultado | Archivo |
| --- | --- | --- |
| `pytest tests/test_research_pilot.py::TestCadenaSincronizada -q` | 7 passed | `fallos_despues.txt` |
| `pytest tests/test_research_pilot.py tests/test_recorrido_productivo.py -q` | 34 passed | `suite_completa.txt` |
| conjunto relacionado (6 archivos) | 76 passed | `suite_relacionada.txt` |
| validación final, mismo conjunto (6 archivos) | 76 passed, `EXITCODE=0` | `validacion_final.txt` |
| subconjunto research completo (9 archivos) | 119 passed, `EXITCODE=0` | `suite_research.txt` |
| `pytest tests/test_recorrido_productivo.py -q` | 6 passed | `recorrido_despues.txt` |

Conteos: `tests/test_research_pilot.py` 28 passed (7 de cadena),
`tests/test_recorrido_productivo.py` 6 passed (incluye
`test_recorrido_productivo_reincorporacion_nuevo_periodo`).

## 7. Qué queda UNKNOWN

- La latencia real de Binance pública no se mide aquí: la recepción se simula
  por loopback. El calentamiento de 60 s es una cota derivada de la ventana de
  flujo, no una medición de latencia de producción.
- No se afirma ventaja económica alguna; este trabajo solo restaura la
  coherencia temporal selección → suscripción → recepción → evaluación.
- Los 33 descartes `permanece` (`dato_obsoleto_flujo`) del embudo público
  siguen sin atribución causal (ver §9.7 de
  `docs/RESEARCH_UNIVERSE_LIQUIDITY_V1.md`).
