# RECTIFICACION DOCUMENTAL — analisis offline de `exp-v2-ventana-4-20261116a`

Contexto: bloque de analisis offline autorizado el 2026-11-16 (despues de la
ventana 4). Sin Binance, sin consultas publicas, sin capturas, sin ordenes,
sin relanzamientos, sin cambios de estrategia ni de capacidad productiva.
Dataset fuente: `C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a`
(solo lectura, no modificado). Derivados:
`C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-analisis-contrafactual-20261116-v2\`.
Etiqueta de los derivados: "evaluacion contrafactual individual, posterior a
la captura; no validacion prospectiva independiente".

Integridad de los originales: verificada contra `manifiesto.json` (10/10
ficheros, bytes y SHA-256 correctos) antes y despues del analisis. Ningun
fichero fuente fue modificado.

## 1. Rectificacion del stop: referencia de senal vs stop de posicion

El codigo publicado (`paper_lab_engine` y `backtest_offline`) distingue dos
niveles distintos, y el campo `stop_px` persistido en la fila resultado NO
representa necesariamente el nivel aplicado durante la posicion:

- **Stop de REFERENCIA** (`config.stop_px`, calculado desde `ref_close` =
  close de la ultima vela 1m plenamente conocida en T). Se usa SOLO para la
  senal de entrada en T (¿el stop ya esta vulnerado en T? -> descarte) y para
  la admision de riesgo. Es el valor que se persiste como `stop_px` en la
  fila resultado (observabilidad).
- **Stop EFECTIVO aplicado durante la posicion**, calculado en
  `backtest_offline._stop_px(avg)` desde el precio de llenado (fill):
  `LONG: fill × (1 − stop_distance_pct/100)`;
  `SHORT: fill × (1 + stop_distance_pct/100)`.
  Es el nivel que gobierna la salida real por stop (gap en open o rango con
  close conocido).

La rectificacion anterior (que afirmaba que el motor nunca calcula el stop
desde el fill) **se corrige**: el motor SÍ calcula el stop aplicado desde el
fill. No se modifica el motor para ajustarlo al informe.

### Operación 1 — AAVEUSDT | SHORT | comparator | `AAVEUSDT|1794857301800`

| Campo | Valor fuente (verificado) |
| --- | --- |
| decisión | 2026-11-16T19:28:21.800Z (`decision_ms` 1794857301800) |
| dirección | SHORT (`move_24h_pct` -0.668, side DOWN) |
| ref_close (referencia en T) | 107.120 (close de vela abierta 1794857220000, close_time 1794857279999 ≤ T) |
| **stop de REFERENCIA** (`stop_px` persistido) | **107.6556** (= 107.120 × 1,005) — solo señal en T |
| entrada (fill) | 107.180 (open de primera vela post-T, `entry_ms` 1794857340000 = 19:29:00Z) |
| **stop EFECTIVO aplicado** (desde el fill) | **107.7159** (= 107.180 × 1,005) — gobierna la salida |
| salida | 19:56:00Z (`exit_ms` 1794858960000), motivo `stop`, `exit_px` 107.7159 |
| exposición realizada | 19:29:00 → 19:56:00 = **27 minutos** (1.620 s, no 170 s) |
| cantidad | 9.3301 (notional 1000 / 107.180) |
| bruto | −5,0000 |
| comisiones | 1,0025 |
| spread/slip | 0,6015 |
| neto | **CONDICIONADO −6,604** |
| funding | **UNKNOWN, no cero** (`cadencia_ambigua`, `interval_ms: null`) |

La salida por stop a 107.7159 coincide exactamente con el stop EFECTIVO
calculado desde el fill (107.7159), no con el stop de referencia (107.6556).
Esto confirma que el nivel aplicado durante la posicion se deriva del fill.

### Operación 2 — 4USDT | LONG | comparator | `4USDT|1794859045223`

| Campo | Valor fuente (verificado) |
| --- | --- |
| decisión | 2026-11-16T19:57:25.223Z (`decision_ms` 1794859045223) |
| dirección | LONG (`move_24h_pct` 4.412, side UP) |
| ref_close (referencia en T) | 0.008570 (close de vela abierta 1794858960000, close_time 1794859019999 ≤ T) |
| **stop de REFERENCIA** (`stop_px` persistido) | **0,00852715** (= 0,008570 × 0,995) — solo señal en T |
| entrada (fill) | 0.008583 (open de primera vela post-T, `entry_ms` 1794859080000 = 19:58:00Z) |
| **stop EFECTIVO aplicado** (desde el fill) | **0,008540085** (= 0,008583 × 0,995) — no se tocó |
| salida | 20:58:00Z (`exit_ms` 1794862680000), motivo `horizon`, `exit_px` 0,008594 |
| exposición realizada | 19:58:00 → 20:58:00 = 60 minutos (3.600 s) |
| cantidad | 116.509,38 (notional 1000 / 0,008583) |
| bruto | +1,2816 |
| comisiones | 1,0006 |
| spread/slip | 0,6004 |
| neto | **CONDICIONADO −0,3194** |
| funding | **UNKNOWN, no cero** (`cadencia_ambigua`, `interval_ms: null`) |

4USDT salió por horizonte (no tocó el stop), por lo que el stop efectivo
0,008540085 (desde el fill) se calcularon pero no se aplicaron en la salida.

### Fórmulas y coherencia bruto/costes (verificadas)

- `qty = notional / entry_px` (entry_px = fill).
- Bruto SHORT = (entry_px − exit_px) × qty; bruto LONG = (exit_px − entry_px) × qty.
- `fees = (entry_valor + exit_valor) × fee_bps` (fee_bps 5.0, sobre valor de entrada y salida).
- `spread_slip = (entry_valor + exit_valor) × (spread_bps + slippage_bps)` (1 + 2 = 3 bps).
- `neto CONDICIONADO = bruto − fees − spread_slip` (funding nunca acreditado: UNKNOWN).
- AAVE: (107.18 − 107.7159) × 9.3301 = −5,0000; −5,0000 − 1,0025 − 0,6015 = −6,604 ✓.
- 4USDT: (0,008594 − 0,008583) × 116509,38 = +1,2816; 1,2816 − 1,0006 − 0,6004 = −0,3194 ✓.

El motor **no se modificó** para hacer coincidir la narrativa.

## 2. Configuración operativa congelada, verificada (sin defaults)

El analisis carga `config_inicial.json` (persistido atomicamente antes de la
primera adquisicion) y **no usa `OperativoConfig()` por defecto**. Valida el
hash `operativo_config_sha256` contra el recalculado sobre `operativo_config`;
rechaza si falta, esta incompleta, es invalida o contradictoria (salida no
exitosa, sin reconstruccion economica).

Configuración acreditada de la corrida:
- `operativo_config_sha256`: `d1423709f4d45207cea601f1aad11742c70f7dfdee44ee69a75701fba60be8ed`
- `config_hash` (corto, el que publican las filas): `d1423709f4d45207`
- `git_head`: `ce2af020c666956ba35a1e1d41d0007c85d581a7`
- `run_id`: `exp-v2-ventana-4-20261116a`
- `escrito_iso`: 2026-11-16T19:26:18.038000+00:00 (antes de la primera adquisicion)
- `pilot_version`: `research-pilot-v2`; `policy_version`: `research-selector-v2`; `protocolo`: `prospective-protocol-v1`

Parametros congelados (reutilizados en cada escenario aislado, capacidad 1):
fee_bps 5.0, spread_bps 1.0, slippage_bps 2.0, stop_distance_pct 0.5,
horizon_ms 3600000 (60 min), notional_usdt 1000, max_concurrent 1,
rule_version RULE-CAUSAL-V1, max_candidates 12, max_comparators 8, max_symbols 20.

Funding: UNKNOWN donde falte cobertura (método `observed-settlements`,
`cal=None` en la resolución, `interval_ms: null`). Nunca se convierte en cero;
no se supone un calendario.

## 3. Reconstrucción de la asignación de capacidad (historial compartido)

Replay del recorrido real con el adaptador existente
(`OperativoAdapter`, `max_concurrent=1`), orden efectivo
`(decision_ms, symbol, observation_id)`, capacidad compartida sobre
intervalos `[entry_ms, exit_ms)`.

Resultado histórico confirmado: **2 entradas, 159 rechazos por capacidad, 0 abstenciones**.

| Posición | Símbolo | Rol | Entrada | Salida | Intervalo ocupado | Motivo salida |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | AAVEUSDT | comparator | 19:29:00Z | 19:56:00Z | [19:29:00, 19:56:00) | stop (nivel efectivo desde fill) |
| 2 | 4USDT | comparator | 19:58:00Z | 20:58:00Z | [19:58:00, 20:58:00) | horizon (stop efectivo no tocado) |

Mecanismo de bloqueo: AAVE ocupa [19:29, 19:56) y 4USDT [19:58, 20:58). Todas
las demás 159 señales aptas tienen su `entry_ms` dentro de uno de esos dos
intervalos (ciclos 1–5 dentro de AAVE; resto del ciclo 6 y ciclos 7–11 dentro
de 4USDT), por lo que se rechazan por capacidad y **nunca se re-admiten**
(rechazo terminal). Tras la salida de 4USDT (20:58:00Z, ya en settle) no hay
más decisiones (captura cerró 20:26:18Z), así que la capacidad nunca vuelve a
liberarse para una nueva entrada.

Conclusión de la reconstrucción: la admisión de AAVEUSDT y 4USDT provino del
**tiempo y del desempate por símbolo** en el orden `(decision_ms, symbol,
observation_id)`, no de una mayor calidad de señal. AAVE fue la primera señal
del ciclo 0; 4USDT fue la primera señal del ciclo 6 con entrada después de que
AAVE liberara capacidad. Todas las demás aptas quedaron bloqueadas por una
posición ajena.

## 4. Evaluación contrafactual individual (161 escenarios, capacidad 1 aislada)

Cada una de las 161 observaciones aptas se evaluó como escenario independiente
con su propia instancia de capacidad 1, reutilizando `OperativoAdapter` +
`paper_lab_engine` sobre los cuerpos originales de
`consultas_klines.jsonl`. Datos fuente sin modificar; no se rellenaron velas
ni calendarios. Financiación desconocida para todos (método
`observed-settlements`, `cal=None` en la resolución → `funding UNKNOWN`,
nunca cero → todos los netos son CONDICIONADO).

| Métrica | Valor |
| --- | --- |
| Observaciones aptas (denominador) | 161 (todas evaluadas, 0 pierden el denominador, 0 se convierten en cero) |
| Entradas simulables (aislado) | 124 |
| Descartes (stop ya vulnerado en T) | 37 |
| Abstenciones | 0 |
| Posiciones sin salida acreditada (`open_at_end`) | 0 |
| Salidas por stop | 96 |
| Salidas por horizonte | 28 |
| Entradas que el historial rechazó por capacidad y sí entran aisladas | 122 |
| De esas 122, resultado positivo | 22 |
| De esas 122, resultado negativo | 100 |
| Entradas que sí entraron en el historial | 2 (AAVE −6,604; 4USDT −0,3194) |

### Resultado agregado contrafactual (neto CONDICIONADO, n=124)

| | Bruto (antes de costes) | Neto CONDICIONADO (tras comisiones + spread/slip) |
| --- | --- | --- |
| n | 124 | 124 |
| suma | +135,1896 | −63,4242 |
| media | +1,0902 | −0,5115 |
| mediana | −5,0000 | −6,5960 |
| min | −5,0000 | −6,6040 |
| max | +155,4039 | +153,6796 |
| ganadoras | 25 | 22 |
| perdedoras | 99 | 102 |
| comisiones totales | — | 124,1337 |
| spread/slip total | — | 74,4802 |

Funding completo: n = 0. Funding desconocido: n = 124. Neto COMPLETO: n = 0 (no se acredita funding como cero).

### Por rol (descriptivo, sin ventaja demostrada)

| Rol | Aptas | Simulables | Entradas hist. | Neto COND. media | Ganadoras / perdedoras |
| --- | --- | --- | --- | --- | --- |
| candidate | 130 | 93 | 0 | −0,1178 | 12 / 81 |
| comparator | 31 | 31 | 2 (AAVE, 4USDT) | −1,6925 | 10 / 21 |

### Por dirección (descriptivo)

| Dirección | Aptas | Simulables | Entradas hist. | Neto COND. media | Ganadoras / perdedoras |
| --- | --- | --- | --- | --- | --- |
| LONG | 87 | 64 | 1 (4USDT) | +1,5422 | 11 / 53 |
| SHORT | 74 | 60 | 1 (AAVE) | −2,7021 | 11 / 49 |

### Concentración y dependencia temporal

25 símbolos únicos, 19 repetidos (hasta 12 veces). Los mismos símbolos se
evalúan en varios ciclos → los 124 escenarios no son independientes
(dependencia temporal y repetición de símbolos). No se presenta como cartera
ejecutable ni se construye drawdown de cartera.

## 5. Control de coherencia (anterior vs corregido)

Se compararon los derivados anteriores (`exp-v2-ventana-4-20261116a-analisis-contrafactual-20261116\`) con los regenerados (`...-v2\`) por `observation_id`:

| Dimensión | Resultado |
| --- | --- |
| Identificadores, estados, timestamps | Igualdad exacta en las 161 filas |
| Importes económicos | Tolerancia absoluta 1e-6; **0 diferencias numéricas** |
| UNKNOWN vs cero | UNKNOWN se preserva (funding n=124, neto completo n=0) |
| Entradas simulables | 124 (v1) = 124 (v2) |
| Descartes | 37 (v1) = 37 (v2) |
| Abstenciones | 0 (v1) = 0 (v2) |
| Neto CONDICIONADO agregado | −63,4242 (v1) = −63,4242 (v2) |
| Bruto agregado | +135,1896 (v1) = +135,1896 (v2) |
| Coherencia numérica 2 operaciones históricas | 2/2 (0 diferencias) |

Los números anteriores se confirman. La única diferencia estructural es el
denominador (v2 usa "reconstruidas" y "sin_fuente_klines" en vez de
"evaluadas", valores equivalentes: 161 aptas, 161 reconstruidas, 0 sin fuente).

Las dos operaciones históricamente admitidas conservan sus valores
exactamente al evaluarse individualmente (AAVE: entrada 107,180, stop de
referencia 107,6556, stop aplicado 107,7159, salida stop 107,7159, neto
−6,604; 4USDT: entrada 0,008583, stop de referencia 0,00852715, stop
efectivo 0,008540085, salida horizon 0,008594, neto −0,3194). Diferencias
numéricas: 0.

El replay histórico `DIFERENCIAS` (2 discrepancias de etiqueta `neto_motivo`,
sin diferencias numéricas) se conserva sin modificarse y no se declara
EQUIVALENTE. Los 161 identificadores se publican con estado y motivo en
`escenarios_por_fila.jsonl`; ninguno desaparece del denominador ni se
convierte en cero.

El historial real (2 entradas y 159 rechazos) se mantiene separado de los
escenarios contrafactuales individuales; estos últimos **no** se suman como
una cartera ejecutable.

## 6. Respuestas a las preguntas del encargo

**A. ¿Qué produjo la regla sencilla antes y después de costes conocidos?**
Antes de costes (bruto, n=124): media +1,09, 25 ganadoras / 99 perdedoras,
mediana −5,0 (la operación típica pierde el stop completo). Después de costes
conocidos (comisiones + spread/slip, funding desconocido, neto CONDICIONADO):
media −0,51, 22 ganadoras / 102 perdedoras, mediana −6,60. Los costes
convierten la esperanza bruta ligeramente positiva en negativa. La regla
produce muchas paradas completas (−6,604) y pocas ganancias por horizonte
(28 de 124, incluidas las dos mayores: +153,68 y +92,81).

**B. ¿Los candidatos se diferenciaron de los comparadores en estas condiciones?**
Solo una diferencia descriptiva: candidate media −0,12 (12/81) vs comparator
media −1,69 (10/21). No es una ventaja demostrada: cobertura desigual (130 vs
31 aptas), las únicas 2 entradas históricas fueron comparadores y ambas
perdedoras, sin financiación completa y con una sola hora de captura.
Comparación candidato/comparador: **INSUFICIENTE**.

**C. ¿La capacidad ocultó oportunidades positivas, negativas o ambas?**
Ambas. La capacidad bloqueó 122 señales que, evaluadas aisladamente, habrían
entrado: 22 con resultado positivo y 100 con resultado negativo. Las dos
señales que sí entraron en el historial fueron perdedoras (−6,604 y −0,3194).
La capacidad actuó como filtro temporal/cola, no como filtro de calidad.

**D. ¿Qué puede concluirse y qué sigue sin poder concluirse?**
Puede concluirse: en esta muestra de 1 hora, la regla sencilla tiene esperanza
neta negativa tras costes conocidos (mediana −6,60, stop completo); los costes
son materiales; la capacidad compartida ocultó señales de ambos signos; las
dos operaciones ejecutadas fueron perdedoras y no representan el conjunto de
señales.
No puede concluirse: rentabilidad generalizable, edge, ventaja de candidato
sobre comparador, ni que bloquear por capacidad evitara pérdidas (bloqueó 22
ganadoras). Los umbrales siguen siendo hipótesis; ninguna conclusión económica
se extrae de una sola ventana. Se usa "media observada en esta muestra",
nunca "esperanza verdadera de la estrategia".

### Sensibilidad al mayor resultado

El mayor bruto (+155,40 en ciclo 08, LONG) supera el bruto agregado de todos
los demás escenarios juntos antes de costes (que es negativo). Este resultado
extremo se conserva siempre en el resultado principal (n=124, incluida su
contribución). Sin él, la media bruta y condicionada serían aún más negativas.
No se elimina ni se ajusta para volver positiva la captura.

## 7. Artefactos

- Fuente (solo lectura, intacta): `C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a\` (manifiesto 10/10 verificado antes y despues del analisis).
- Derivados (fuera de Git, directorio nuevo, resultados anteriores NO reutilizados):
  `C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-analisis-contrafactual-20261116-v2\`
  (`resumen_ejecutivo.json`, `escenarios_por_fila.jsonl`,
  `replay_historico_compartido.jsonl`).
- Ejecución: SHA base `7b658e6b466a0ce24d018488d118dc33d08697f8`;
  script `scripts/analisis_contrafactual_ventana4.py` (corregido: config
  validada, CLI fuente/salida, stop referencia vs efectivo); 11 pruebas
  `tests/test_analisis_contrafactual_ventana4.py`.
