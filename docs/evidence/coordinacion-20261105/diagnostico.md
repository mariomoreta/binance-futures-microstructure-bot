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

## 8. Corrección 2026-11-06: evidencia cronológica y corte con cobertura real

**Limitación de la evidencia de 2026-11-05 (no se borra).** Las pruebas de
cadena publicaban y confirmaban los eventos con event_ms = cut estando el reloj
un segundo antes del corte, y la reincorporación recibía por lotes datos
anteriores al nuevo periodo. Eso acreditaba el orden del bucle
(seleccionar → suscribir → confirmar → evaluar), pero no una ventana construida
recibiendo durante 60 s desde una suscripción nueva. Los archivos y resultados
anteriores se conservan tal cual.

**Defecto con recepción cronológica (base 93bcecf).** Sonda de aceptación en
worktree aislado, primera recepción en T0+1000: en el corte nominal T0+60000 la
ventana observada es 55 s. El código evaluaba igualmente y escribía 18 descartes
lujo_ventana_incompleta con decision_ms = T0+60000, consumiendo la única
oportunidad del ciclo (siguiente corte en T0+360000): 0 observaciones aptas antes
de la siguiente selección. Evidencia: ntes_fix_93bcecf.txt y
ecorrido_productivo_antes_fix.txt (5 failed, 1 passed) en
docs/evidence/coordinacion-recepcion-20261106/.

**Corrección (protocolo de captura 3).** El primer corte espera cobertura
observada real:

- _coverage_ready exige ventana de flujo completa según el motor
  (warmup_complete sobre el span de eventos recibidos), libro con mid válido,
  sin degradación ni cruce y ambas fuentes dentro de max_data_age_ms (5 s).
  Misma regla para candidatos y comparadores.
- La programación usa la primera recepción efectiva por fuente
  (symbol_first_flow_ms / symbol_first_book_ms), no la suscripción.
- Si el corte nominal no tiene cobertura, se reprograma en el mismo bucle cada
  250 ms hacia primera_recepcion + ventana, con espera máxima explícita
  WARMUP_MAX_WAIT_MS = 60 s (también acotada por el fin de captura). No se
  escribe un descarte definitivo ni se consume la oportunidad.
- Al agotarse la espera, el corte se ejecuta con motivo explícito del motor
  (sin_flujo / sin_libro / dato_obsoleto_* / lujo_ventana_incompleta);
  last_cut_reason distingue cobertura_completa de espera_maxima_agotada.
- decision_ms sigue siendo el instante real de evaluación; no se extiende la
  captura ni se compensan ciclos fuera de plazo.

**Evidencia posterior (cronológica).** 	ests/test_aceptacion_coordinacion_recepcion.py:
18 símbolos (candidatos y comparadores), primera recepción en T0+1000, 468
eventos publicados con event_ms <= reloj y 0 fechas futuras; corte nominal
T0+60000, evaluación efectiva T0+62000, ventana observada 60000 ms, 18/18 aptas.
Traza: docs/evidence/coordinacion-recepcion-20261106/traza_corte_recepcion.json.
Regresiones: 	ests/test_recorrido_productivo.py 6 passed (reincorporación sin
historia precargada; fuente ausente con espera acotada y motivo) y
	ests/test_research_pilot.py 28 passed; conjunto relacionado 77 passed,
EXITCODE=0 (alidacion_final.txt).

**Qué sigue UNKNOWN.** La latencia real de Binance pública no se mide aquí: la
recepción es loopback. La espera máxima de 60 s es una cota operativa explícita,
no una medición de latencia de producción. No se declara ventaja económica.

## 8. Renovación del ciclo de decisión (2026-11-06)

**Defecto en la base 10b196b.** Tras el primer corte, los símbolos permanecen en
_symbols_evaluated_this_cycle, _pending_symbols queda vacío y el bucle solo
adelanta 
ext_decision sin volver a evaluar: con conjunto estable solo se
produce un ciclo de evaluación. Reproducido en worktree aislado de 10b196b
(sin Binance, con recepción cronológica y fuentes frescas): ciclo 1 con 18
observaciones en decision_ms = T0 + 62000 y 0 observaciones fuera del ciclo
1. Evidencia:
docs/evidence/coordinacion-recepcion-20261106/regresion_ciclos_antes_10b196b.txt.
No se atribuye a presupuesto, ausencia de datos ni selección.

**Corrección mínima en scripts/research_pilot.py.** En el limiar de cada
ciclo de decisión (
ow >= next_decision) se limpia
_symbols_evaluated_this_cycle antes de calcular los pendientes, de modo que
los símbolos seguidos recuperan la oportunidad en cada ciclo; dentro del mismo
ciclo los reintentos de calentamiento no la renuevan, y la selección no decide
si hay nueva evaluación (ciclos de selección y de decisión son distintos).
Máximo una observación por símbolo y ciclo.

**Evidencia de aceptación.** 	ests/test_tres_ciclos_decision.py: tres ciclos
consecutivos con conjunto estable (18 símbolos, candidatos y comparadores),
cortes en T0 + 62000, T0 + 366000 y T0 + 666000 (intervalos 304000 ms y
300000 ms, coherentes con cycle_seconds = 300 s), 54 observaciones =
18 símbolos × 3 ciclos, todas aptas, sin duplicados y sin observaciones
adicionales por ejecutar otra selección. Traza:
docs/evidence/coordinacion-recepcion-20261106/traza_tres_ciclos.json.

**Regresiones conservadas:** corte nominal incompleto no consume prematuramente
la oportunidad; fuente ausente con espera acotada y motivo explícito;
frescura independiente por fuente; reincorporación reinicia cobertura;
rotación conserva pendientes; presupuesto bloquea antes del envío; parada
explícita impide nuevas consultas; fin normal permite settle acotado.
Validación final: 78 passed, EXITCODE=0
(docs/evidence/coordinacion-recepcion-20261106/validacion_final.txt).

Sin Binance público, sin adquisición externa, sin datasets históricos ni DBs
canónicas modificadas, sin cambios de selección, estrategia, precios, frescura
o techos presupuestarios. No se tocan 3020, servicio 8792, opencode.json ni
archivos ajenos.
