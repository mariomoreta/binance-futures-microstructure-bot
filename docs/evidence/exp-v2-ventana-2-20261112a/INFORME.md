# Ventana `exp-v2-ventana-2-20261112a` — EJECUTADA y cerrada (2026-11-14)

**Autorización:** bloque humano del 2026-11-14 — «UNA SOLA VENTANA DEL
EXPERIMENTO OPERATIVO V2» (adquisición pública, simulación operativa,
resolución de resultados, espera contable y cierre). **No** autoriza órdenes
reales, cuentas, claves privadas, fondos, nuevas ventanas ni relanzamientos.

**Veredicto de una línea:** la ventana **terminó correctamente y dentro de
plazo**, con cobertura de datos **buena** (179 observaciones aptas, 12/12
ciclos con ambos roles aptos, 537/537 resultados resueltos) y **cero
operaciones**: las **179 decisiones fueron abstenciones** por una única causa
determinista — *el precio de referencia de entrada nunca estuvo disponible* —
que se ha diagnosticado con evidencia (ver §4). El resultado económico es
**INSUFICIENTE**, no nulo: no hay P&L que reportar.

| | |
|---|---|
| `run_id` | `exp-v2-ventana-2-20261112a` (única ejecución; **no** reutilizado) |
| `git_head` | `ab97b02203cb5ac49c04bf2c9a8472f181b74a49` (local == remoto) |
| Código del lanzador | `b0fdb52f07e4fdf3f4c2b7c3aa8253b12d9b096e` |
| Directorio del dataset | `C:\proyectos\binance-futures-data\exp-v2-ventana-2-20261112a` (fuera de Git) |
| Monitor | `http://127.0.0.1:3020/market-lab?vista=piloto&run=exp-v2-ventana-2-20261112a` (solo lectura) |
| Duración | **7 803,176 s** (2 h 10 min) frente al máximo autorizado de **40 500 s** → 19,3 % del tope |
| Código del **hijo** (`exit_code.txt`) | **0** (observado) |
| Veredicto del **lanzador** (`cierre.json`) | **normal**, `cumplimiento_normal: true`, `codigo_lanzador: 0`, `exceso_maximo_total_s: 0,0`, `incumplimiento_plazo_global: false` |

Las operaciones que aparecen en el monitor son **simulaciones reconstruidas**
a partir de registros históricos; **no son órdenes enviadas** ni ejecución en
vivo. En esta ventana, además, **no hubo ninguna operación** (§3).

---

## 1. Conclusión técnica

### 1.1 Fases y plazos (todas las observadas, ninguna ampliada)

| Fase | Mecanismo | Observado | Techo autorizado |
|---|---|---|---|
| 1. Captura | `--duration-seconds 3600`, 12 ciclos de 300 s | **3 600 s**, 12/12 ciclos, 0 ciclos saltados, 20 símbolos/ciclo (12 candidatos + 8 comparadores) | 3 600 s |
| 2. Resolución (settle) | `--settle-seconds 4200` | **4 200 s**, 537/537 resultados resueltos, 0 pendientes | ≤ 4 200 s |
| 3. Espera contable | `--funding-wait-seconds 32400` | **NO se abrió** (`inicio_ms: null`, `fin_ms: null`): no había posición abierta que liquidar; 0 consultas de funding | ≤ 32 400 s |
| 4. Cierre y persistencia | margen exclusivo del lanzador | feeds cerrados, `ResearchRecorder` en `STOPPED`, manifiesto y resumen escritos | 300 s |

Duración efectiva del piloto: **7 800,552 s** (`espera_contable.duracion_total_efectiva_s`).
Duración total con persistencia del lanzador: **7 803,176 s** (`cierre.json`).
**Exceso sobre el máximo global: 0,0 s.** No hubo parada solicitada ni
terminación forzada (`parada_solicitada: false`,
`terminacion_forzada_solicitada: false`): el hijo terminó por su cuenta.

### 1.2 Recepción por feed

| Métrica | Valor |
|---|---|
| Conexiones WS totales | **22** (2 aperturas iniciales + 10 rotaciones del conjunto × 2 feeds); techo del plan **46** → 47,8 % |
| Rotaciones del conjunto | 10 de 11 previstas (la captura terminó en el ciclo 12, sin rotación posterior) |
| Reconexiones por desconexión / errores WS | **0 / 0** (`reaperturas_tras_desconexion_tope: 20`, no consumidas) |
| Mensajes WS totales | **845 161** (`ws_messages_total`), tope 5 000 000 → 16,9 % |
| Feed final `/market` (aggTrade) | 24 639 mensajes; conexión final cerrada limpiamente, 0 errores |
| Feed final `/public` (depth20@100ms) | 31 427 mensajes; conexión final cerrada limpiamente, 0 errores |
| `ResearchRecorder` | 9 384 escrituras · 1 200 filas `book_1m` · 6 931 `flow_10s` · 1 253 `flow_1m` · **0 drops** · **0 errores** · estado final `STOPPED` |
| Duplicados (dedupe flujo/libro) | **0 / 0** |
| Rutas WS | `/public/stream` y `/market/stream` (categoría, no URL antigua) |

### 1.3 Consumos

| Recurso | Consumido | Techo | Uso |
|---|---|---|---|
| Intentos HTTP | **740** (0 reintentos, 740 × HTTP 200) | 2 000 | 37,0 % |
| Peso REST reservado | **1 208** (configurado 7 880) | 5 000 | 24,2 % |
| Peso observado `x-mbx-used-weight-1m` | máx **67**, mín 1, último **30** | — | — |
| Endpoints REST | 12 `exchangeInfo` + 12 `ticker/24hr` + 716 `klines` (179 de trayectoria `limit=62` + 537 de precio `limit=1`) | — | 309,6 s acumulados |
| Almacenamiento | **6 183 860 B** | 134 217 728 B | 4,6 % |
| Mensajes WS | 845 161 | 5 000 000 | 16,9 % |
| Consultas `fundingRate` | **0** | 500 / 5 min | 0 % |
| Capacidad | 1 posición simultánea | 1 | 0 posiciones abiertas |

### 1.4 Cierre acreditado

| Artefacto | Contenido |
|---|---|
| `exit_code.txt` | **0** — código real del proceso hijo, leído de `Popen.wait()` |
| `estado_lanzador.json` | `resultado: normal`, `causa_terminacion: terminacion_natural`, `cumplimiento_normal: true`, `codigo_lanzador: 0`, `terminacion_hijo_observada: true`, `codigo_salida_estado: observado`, `recursos_hijo: UNKNOWN`, `exceso_maximo_total_s: 0,0`, `incumplimiento_plazo_global: false`, `duracion_total_s: 7803,174` |
| `cierre.json` (definitivo) | idéntico con `duracion_total_s: 7803,176` y `fin_iso_utc: 2026-11-14T04:35:09` |

**Cierre del hijo: acreditado** (código observado y terminación observada).
**Cierre de los sockets del hijo: `UNKNOWN`** — el lanzador genérico no puede
certificarlo y no lo afirma; el estado del piloto (`feeds_closed: true` en el
monitor) se conserva como **evidencia diferenciada**. No se presenta un código
0 del hijo como cumplimiento normal por inercia: aquí **coincide** con el
veredicto del lanzador (`cumplimiento_normal: true`, sin timeout y sin exceso).

---

## 2. Conclusión de calidad

### 2.1 Embudo por rol (denominadores completos)

| Rol | Seleccionadas | Observadas | **Sin observación** | Aptas | Descartadas | % aptas / observadas | % aptas / seleccionadas |
|---|---|---|---|---|---|---|---|
| `candidate` | **144** | 138 | **6** | **131** | 7 | 94,9 % | 91,0 % |
| `comparator` | **96** | 81 | **15** | **48** | 33 | 59,3 % | 50,0 % |
| **Total** | **240** | **219** | **21** | **179** | **40** | 81,7 % | 74,6 % |

12 ciclos × 20 símbolos (12 candidatos + 8 comparadores) = 240 selecciones.
Cada selección produce **como máximo** una observación; 21 no produjeron
ninguna (por qué: §2.3).

### 2.2 Aptas por ciclo y rol

| Ciclo | Candidatos (obs/apta) | Comparadores (obs/apta) | Aptas del ciclo |
|---|---|---|---|
| 1 | 12/12 | 8/8 | 20 |
| 2 | 12/10 | 8/2 | 12 |
| 3 | 12/11 | 8/3 | 14 |
| 4 | 11/10 | 3/3 | 13 |
| 5 | 12/11 | 8/5 | 16 |
| 6 | 11/11 | 6/6 | 17 |
| 7 | 12/12 | 6/2 | 14 |
| 8 | 12/11 | 6/5 | 16 |
| 9 | 11/11 | 8/4 | 15 |
| 10 | 10/10 | 7/2 | 12 |
| 11 | 11/10 | 7/5 | 15 |
| 12 | 12/12 | 6/3 | 15 |
| **Total** | **138/131** | **81/48** | **179** |

**Cobertura:** `ciclos_con_ambos_roles_aptos = 12/12` (`cobertura_ciclos_ambos_roles = 1,0`).
La calidad de datos **no** fue el factor limitante de la cobertura total: sí lo
fue **para el rol comparador** (50 % de sus selecciones llegaron a ser aptas
frente al 91 % de los candidatos).

### 2.3 Motivos de descarte y de no observación

| Motivo | Observaciones descartadas |
|---|---|
| `dato_obsoleto_flujo` | 29 |
| `flujo_ventana_incompleta` | 13 |
| `dato_obsoleto_libro` | 1 |

Los 40 descartes llevan **43 etiquetas de motivo** (3 observaciones tienen más de
un motivo simultáneo); el agregado por motivo coincide con el campo
`motivos` de `resumen.json`.

Las 21 selecciones **sin observación** se concentran en los ciclos 4 (6), 6 (3),
10 (3), 7 (2), 8 (2), 11 (2), 12 (2) y 9 (1): son rotaciones de conjunto en las
que el símbolo no llegó a producir un corte evaluable dentro de su ventana.

### 2.4 Resultados y pendientes

| Métrica | Valor |
|---|---|
| Resultados escritos | **537 = 179 × 3 horizontes** (5 m / 15 m / 60 m), estado `resuelto` |
| Pendientes al cierre | **0** (`pending: 0`, `outcomes_written: 537`) |
| No evaluables | **0** |
| Desfase de resolución | media **45 567 ms**, máx **47 473 ms** |
| Motivo de todo `neto` | `UNKNOWN` — «sin supuestos de ejecución ni costes» (0 de 537 con neto) |

**Cobertura de la regla causal:** `decision_ms` es el instante real de
evaluación (reloj del piloto), todas las disponibilidades ≤ `decision_ms`,
`precio_base` = `libro_mid`, `precio_posterior` = `klines_apertura_1m`
(proxy de fuentes mixtas; no mark-to-mid), `config_hash` y versión de motor
persistidos en cada fila (`paper-lab-engine/v1.2`,
`config_hash d1423709f4d45207`).

---

## 3. Conclusión económica exploratoria

### 3.1 Embudo de decisiones

| Magnitud | Valor |
|---|---|
| Señales con dirección | **179** (LONG 88 · SHORT 91) |
| **Abstenciones (`SIN_ENTRADA`)** | **179 (100 %)** |
| Entradas simuladas | **0** |
| Rechazos por capacidad (`RECHAZADA_CAPACIDAD`) | **0** |
| Salidas ejecutadas | **0** |
| Posiciones abiertas al final | **0** |
| Posiciones cerradas | **0** |
| Exposición realizada | 0 ms |
| Neto **COMPLETO** | `n = 0`, suma/media/mediana/min/max = **null** |
| Neto **CONDICIONADO_SIN_FUNDING_COMPLETO** | `n = 0`, todos **null** |
| Neto **UNKNOWN** | 179 |
| Ganadoras / perdedoras (COMPLETO o CONDICIONADO) | 0 / 0 |
| Drawdown realizado | `null` |

**La ausencia de operaciones NO se presenta como P&L cero:** todos los campos
económicos son `null` con `n = 0`, y el propio piloto marca la comparación
como **`INSUFICIENTE`**.

### 3.2 Comparación candidato / comparador

| Criterio (el del propio piloto) | Valor |
|---|---|
| Ciclos totales | 12 |
| Ciclos con ambos roles aptos | **12** (cobertura 1,0) |
| Ciclos con operaciones completas en ambos roles | **0** |
| Operaciones completas `candidate` / `comparator` | **0 / 0** |
| Diferencia paired media | `null` |
| `estado` de la comparación | **`INSUFICIENTE`** |
| Motivos | `sin_operaciones_completas_candidate`, `sin_operaciones_completas_comparator` |

**No se atribuye ninguna diferencia al selector.** Con 0 operaciones
completas en ambos roles, la comparación por pares no es interpretable; la
cobertura de datos (1,0) fue suficiente, pero **no lo fue la capa de
ejecución**. Tampoco es interpretable la capacidad compartida, que no llegó a
activarse (0 rechazos): no hay nada que repartir.

### 3.3 Contexto descriptivo (NO es P&L, NO es una comparación del selector)

Retorno **crudo** de precio (sin firmar por dirección, sin costes, sin
supuestos de ejecución; `neto: null` en las 537 filas). Se publica solo como
descripción de las trayectorias observadas:

| Horizonte | Rol | n | Media | Mediana | Mín | Máx |
|---|---|---|---|---|---|---|
| 5 m | candidate | 131 | −0,00165 | −0,00132 | −0,08934 | +0,09224 |
| 5 m | comparator | 48 | −0,00002 | +0,00085 | −0,01156 | +0,00850 |
| 15 m | candidate | 131 | −0,00624 | −0,00255 | −0,13046 | +0,10974 |
| 15 m | comparator | 48 | +0,00024 | −0,00095 | −0,01018 | +0,01102 |
| 60 m | candidate | 131 | −0,03100 | −0,01461 | −0,23224 | +0,04522 |
| 60 m | comparator | 48 | −0,00263 | −0,00301 | −0,01617 | +0,01020 |

Esto **no** es un resultado del sistema: son retornos de precio observados en
las ventanas de horizonte, con coberturas desiguales por rol (131 vs 48) y
sin ninguna operación ejecutada. Sirven para dimensionar el movimiento, no
para comparar estrategias.

### 3.4 Regla que produjo el resultado

La regla congelada (dirección común → señal → entrada con
`entry_px = close` de la vela 1 m plenamente conocida en T → stop 0,5 % →
notional 1 000 USDT → horizonte 60 min → capacidad 1) **nunca llegó a la
fase de entrada**: en las 179 observaciones la entrada no pudo fijarse
(§4). El resto de la regla (stop, gestión, salida, costes, funding) **no se
ejercitó** y, por tanto, **queda sin evidencia**.

---

## 4. Causa raíz de las 179 abstenciones (diagnosticada, no corregida)

**Síntoma:** las 179 filas operativas tienen
`decision = SIN_ENTRADA`, `qty = 0`, `entry_px = null` y
`funding_estado = "sin vela 1m plenamente conocida en T"`.

**Causa:** el piloto pide la trayectoria 1 m con
`klines(startTime = decision_ms - 60 000)`, y Binance filtra
`openTime >= startTime`. La última vela 1 m **plenamente cerrada en T** abre
en `floor(T/60000)*60000 - 60000`, que es **anterior** a ese `startTime`
cuando `decision_ms` no está alineado al minuto. **Ninguna** de las 179
decisiones lo estaba (restos `decision_ms % 60000` = 12 527 … 19 298; el
segundo del minuto fue 12, 13, 14, 15 o 19 porque la decisión se toma en el
corte + 5 s de retraso). La vela de referencia quedaba **excluida** en los
179 casos y la primera vela devuelta **cerraba después de T**: no existía
precio de referencia conocido en el instante de la decisión.

**Verificación (ledger HTTP persistido, sin re-ejecutar nada):**

| Comprobación | Resultado |
|---|---|
| Decisiones totales / alineadas al minuto | 179 / **0** |
| Decisiones con la vela de referencia excluida por `startTime` | **179 / 179** |
| Consultas `klines` de trayectoria (`limit=62`) | **179** (una por observación) |
| Consultas `klines` de precio de horizonte (`limit=1`) | 537 |
| Ejemplo | `2ZUSDT`, `decision_ms=1794623179298` → `startTime=1794623119298` → vela de referencia abre `1794623100000` (excluida); la primera devuelta abre `1794623160000` y cierra `1794623219999` **> T** |

Código implicado: `scripts/research_pilot.py::_consultar_trayectoria_operativa`
(`start_ms = decision_ms - step_ms`) y
`scripts/research_operativo_adapter.py::_vela_plenamente_conocida_en`
(exige `close_time_ms <= decision_ms`).

**Naturaleza:** es un **defecto determinista del borde de la consulta**, no
una ausencia de datos de mercado, no un límite de presupuesto, no la
capacidad compartida y no una restricción del selector. La recepción WS, la
cobertura de datos y el presupuesto estaban en condiciones de sostener la
ventana: el resultado nulo nace de esta frontera de tiempo.

**Qué NO se hace en este bloque:** la ventana queda cerrada y **no se
relanza**. La corrección del borde de la consulta es un **cambio de
metodología** que requiere autorización humana explícita y una ventana nueva;
aquí solo se registra el diagnóstico con evidencia.

**Defecto secundario de etiquetado (no afecta al resultado):** las filas de
abstención (`qty = 0`, `entry_px = null`, `open_at_end = false`) llevan
`neto_motivo = "posicion abierta: la salida no esta ejecutada y el P&L no es
realizado"`. El texto es genérico y describe una posición abierta que **no
existe** en esas filas; el `neto_estado = UNKNOWN` sí es correcto. Se reporta
como defecto de etiquetado a corregir junto con la causa raíz.

---

## 5. Lo que esta ventana NO acredita

1. **No acredita rentabilidad, edge ni ejecutabilidad.** 0 entradas, 0
   salidas, 0 P&L: el resultado económico es **INSUFICIENTE** con
   denominadores completos.
2. **No acredita la comparación candidato/comparador** (`INSUFICIENTE` por
   falta de operaciones completas, no por falta de cobertura de datos).
3. **No ejercita** stop, gestión, salida, costes, spread/deslizamiento ni
   funding: la espera contable **no se abrió** (0 consultas) porque no había
   posición abierta.
4. **No cubre** futuros con vencimiento: el selector sigue limitado a
   PERPETUAL/TRADING/USDT.
5. **No sustituye** la revalidación de la regla con datos que sí alcancen la
   entrada; la comparación con y sin el defecto require autorización aparte.
6. **No hay P&L cero**: `n = 0` y `null` en todos los campos económicos.

## 6. Artefactos

| Fichero | Contenido |
|---|---|
| `manifiesto.json` | manifiesto del piloto con SHA-256 de cada artefacto del dataset y `git_head` |
| `resumen.json` | resumen completo del piloto (incluye `economia_operativa_v2`) |
| `exit_code.txt`, `estado_lanzador.json`, `cierre.json` | los tres artefactos de cierre del lanzador, **por separado** |
| `causa_raiz_verificacion.json` | verificación machine-checkable de la causa raíz |
| `muestra_resultado_operativo.jsonl` | 25 filas operativas de muestra (el fichero completo, 179 filas, queda en el dataset) |
| `hashes.json` | SHA-256 de lo publicado + hashes por artefacto del dataset fuera de Git |

**Dataset (fuera de Git):** `C:\proyectos\binance-futures-data\exp-v2-ventana-2-20261112a`
(`observaciones.jsonl` 3 154 325 B / 768 filas · `http_requests.jsonl` 632 139 B
/ 740 filas · `resultado_operativo.jsonl` 144 596 B / 179 filas ·
`research.db` 2 252 800 B · `funding_adquisicion.jsonl` 0 B · `stdout.log`
240 B · `stderr.log` 0 B). Sus hashes están en `manifiesto.json` y en
`hashes.json`.
