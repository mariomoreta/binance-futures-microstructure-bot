# Corrección del borde de la consulta operativa — informe de tres capas

**Bloque:** corrección local y evaluación offline, sin mercado.
**Autorización humana del 2026-11-14:** «AUTORIZACIÓN — CORRECCIÓN LOCAL Y
EVALUACIÓN OFFLINE, SIN MERCADO». Cubre: corregir el borde temporal de la
consulta operativa, corregir la etiqueta económica de las abstenciones, ejecutar
pruebas locales y comprobar/aprovechar el dataset existente mediante análisis
offline. **No** autoriza Binance, consultas públicas, capturas, órdenes,
relanzamientos ni ventanas nuevas.

**Base publicada:** `3e4ad0fa15bec9c7f3c2c187fed014b2a4d5d5ec`
(`research/universe-liquidez-v1`), verificada al inicio (local == remoto,
divergencia 0/0, sin commits posteriores). El cambio ajeno `opencode.json` no
se tocó ni se incluye.

**Veredicto:** el defecto que vació la capa de ejecución de la ventana
`exp-v2-ventana-2-20261112a` **queda corregido y aceptado localmente** por el
recorrido productivo real, y el dataset existente **no permite reevaluar la
ventana económicamente**: se puede probar la corrección a nivel de consulta
(**179/179**) y se pueden cuantificar los faltantes, pero **no** hay P&L
recalculable. La corrección es de **implementación**, no de metodología: no
cambia la regla, ni `decision_ms`, ni el precio de referencia, ni el fill
causal, ni stop, horizonte, notional, capacidad, prioridad, costes ni
contabilidad de funding.

---

## Capa 1 — Defecto: antes y después (técnica)

### 1.1 Qué ocurría

El piloto pedía la trayectoria 1 m operativa con

```python
start_ms = decision_ms - step_ms          # scripts/research_pilot.py
```

y el venue filtra `openTime >= startTime`. La regla exige el **close de la
última vela 1 m plenamente cerrada en T** (`close_time_ms = open_time_ms +
step_ms - 1 <= T`). Esa vela abre en `floor((T+1)/step)*step - step`, que es
**anterior** a `T - step` salvo cuando `T` está alineado al minuto o cuando
`T mod step == step - 1` (último milisegundo del minuto). En esos casos la
vela de referencia quedaba **fuera** de la serie y la primera vela devuelta
era la que **contenía** a T, cuyo cierre es **posterior** a T: no existía
precio de referencia conocido en el instante de la decisión y la regla solo
podía abstenerse.

En la ventana real, **0/179** decisiones estaban alineadas al minuto (los
desfases observados fueron 12 527, 19 298, 12 938, 12 941, 13 428, 13 576,
13 832, 13 889, 13 934, 14 409, 14 902 y 15 396 ms), luego **179/179** filas
terminaron en abstención.

### 1.2 Qué se corrigió

| | Antes (publicado) | Después (corregido) |
|---|---|---|
| Inicio de la serie | `decision_ms - step_ms` | `floor(decision_ms/step)*step - step` (`inicio_trayectoria_operativa`) |
| Tope de filas | `horizon_ms // 60_000 + 2` = **62** | `ceil(horizon_ms/step)//step + 3` = **63** |
| Extremo final | `now + step_ms` (**sin tocar**) | `now + step_ms` (**sin tocar**) |
| `decision_ms` | instante real | **idéntico** (no se redondea ni se retrotrae) |
| Referencia en T | close de la última vela cerrada en T | **idéntica** (misma regla, ahora con el dato disponible) |
| Fill | apertura posterior a T | **idéntico** |

El inicio corregido es un **límite inferior** que siempre incluye la vela de
referencia (en `T mod step == step - 1` incluye una vela antes: es inocuo, el
adaptador elige la última cerrada en T).

### 1.3 El segundo defecto del borde: el final sí se truncaba

Corregir solo el inicio **empeoraba** el final. El motor solo acredita el
cierre por horizonte cuando la serie **pasa** del horizonte
(`backtest_offline`: `data_past_horizon = series[-1].open_time_ms >
horizon_end`); si la serie acaba dentro, marca `open_at_end` (una marca, no
una salida ejecutada). Con el inicio una fila más temprano y el tope de 62
filas, la serie acababa **exactamente** en la vela del horizonte y el cierre
por horizonte **dejaba de acreditarse**: el caso alineado al minuto pasaba de
operación cerrada a posición abierta.

Por eso el tope pasa a **63**: desde la vela cerrada en T hasta la **primera
vela que abre después del horizonte**, que es lo que la regla necesita para
distinguir «la regla cerró por horizonte» de «los datos se acabaron». El
extremo final (`now + step_ms`) **no se toca**: no se resuelve el inicio
truncando la salida.

### 1.4 Clasificación del cambio

**Corrección de implementación**, no cambio de metodología:

- **No** cambia la regla: la referencia sigue siendo el close de la última
  vela 1 m **plenamente cerrada en T**; el fill sigue siendo la apertura
  posterior a T; stop, horizonte, notional, capacidad compartida, prioridad,
  costes y contabilidad de funding quedan **intactos**.
- **No** usa el cierre futuro de la vela que contiene T: la regla
  `_vela_plenamente_conocida_en` (`close_time_ms <= decision_ms`) se conserva
  sin cambios y es la que descarta esa vela.
- **No** cambia la dirección ni la selección: siguen derivando de
  `move_24h_pct` disponible en T.
- **Recupera un dato que la regla ya exigía** (la vela cerrada en T) y
  **restaura la cobertura final** que el tope publicado recortaba (la fila que
  permite acreditar el cierre por horizonte).
- **No** produce entradas por sí sola: si la referencia no existe, la regla
  sigue absteniéndose (aceptado explícitamente en las pruebas).

Si hubiera hecho falta cambiar la regla económica para obtener entradas, el
trabajo se habría detenido. No hizo falta.

### 1.5 Etiquetado honesto (`neto_motivo`)

El texto genérico «posición abierta: la salida no está ejecutada…» se aplicaba
a **toda** fila sin salida acreditada, incluidas las abstenciones con
`qty = 0` (posición **inexistente**). Ahora se distinguen cuatro estados
reales:

| Estado real | `neto_motivo` | `neto_estado` |
|---|---|---|
| Abstención sin posición | `abstencion sin posicion: no se ejecuto ninguna entrada (motivo: …)` | `UNKNOWN` |
| Rechazo por capacidad sin posición | `rechazo por capacidad sin posicion: no se abrio ninguna entrada` | `UNKNOWN` |
| Posición realmente abierta sin salida | `posicion abierta: la salida no esta ejecutada y el P&L no es realizado` | `UNKNOWN` |
| Operación cerrada con funding incompleto | `operacion cerrada con funding incompleto: …; el neto no es completo` | `CONDICIONADO_SIN_FUNDING_COMPLETO` |

`UNKNOWN` sigue siendo `UNKNOWN`: no se convierte desconocimiento en cero y
una operación cerrada sin funding acreditado **no** pasa a `COMPLETO`.

---

## Capa 2 — Aceptación local (recorrido productivo real, sin mercado)

**Método:** CLI real (`scripts/research_pilot.py`) como subproceso,
proveedores **HTTP y WS loopback**, reloj manual controlado, almacenamiento
temporal, SQLite temporal. El recorrido ejercido es el productivo completo:

```
selección → observación → consulta de trayectoria → adaptador → motor → persistencia
```

No se llama al adaptador con una lista de velas preparada por el test: las
velas las produce el proveedor loopback, que **respeta el filtrado real del
venue** (`openTime >= startTime`) y el **tope de filas** (`limit`), y devuelve
`close = null` en las velas cuyo cierre aún no ocurrió respecto al reloj.

**Comando y resultado observados:**

```
python -m pytest tests/test_pilot_operativo_consulta_temporal.py -v
9 passed in 16.47s      (código de salida observado: 0)
```

| Prueba | Qué acredita |
|---|---|
| `test_borde_publicado_excluye_la_vela_de_referencia` | aritmética del defecto con los desfases reales |
| `test_borde_corregido_no_altera_la_extremidad_final` | el inicio se corrige; el final no se toca |
| `test_proveedor_loopback_respeta_el_filtrado_por_apertura` | el proveedor emula `openTime >= startTime` y `limit` |
| `test_aceptacion_decisiones_no_alineadas_recuperan_la_referencia` | 7 instantes de decisión por el recorrido real |
| `test_recorrido_long_y_short_con_datos_sinteticos` | LONG y SHORT con datos sintéticos adecuados |
| `test_capacidad_compartida_limitada_a_una_posicion` | límite compartido de capacidad (1 posición) preservado |
| `test_datos_realmente_ausentes_producen_abstencion_explicita` | si el dato falta de verdad → abstención explícita, sin inventar |
| `test_etiqueta_economica_distingue_los_cuatro_estados` | los cuatro estados de `neto_motivo` |
| `test_persistencia_y_resumen_coherentes` | persistencia y resumen coherentes; UNKNOWN nunca es cero |

**Instantes de decisión probados** (T = `T0 + 60 000 + desfase`): exactamente en
el minuto (`T mod 60 000 = 0`), **un milisegundo después** (`1`), los
desfases **publicados** `12 527` y `19 298`, cerca del cierre `59 998` y
`59 999`, y **alrededor del cambio de minuto** (`60 001`).

### Antes/después observado (mismo recorrido, mismos instantes)

`antes_despues.json` (capturado ejecutando el **código publicado** y después el
corregido, con el mismo arnés):

| Caso | `T mod 60 000` | ANTES: decisión / consulta | DESPUÉS: decisión / consulta |
|---|---|---|---|
| `exacto_en_el_minuto` | 0 | `ENTRADA_EJECUTADA`, `startTime = T-60 000`, `limit 62` → **salida NO acreditada** (`open_at_end`) | `ENTRADA_EJECUTADA`, `startTime = floor(T)-60 000`, `limit 63` → salida **por horizonte** acreditada |
| `desfase_1` | 1 | `SIN_ENTRADA` — «sin vela 1m plenamente conocida en T» | `ENTRADA_EJECUTADA`, fill posterior a T, salida por horizonte |
| `desfase_12527` | 12 527 | `SIN_ENTRADA` — «sin vela 1m plenamente conocida en T» | `ENTRADA_EJECUTADA`, fill posterior a T, salida por horizonte |
| `desfase_19298` | 19 298 | `SIN_ENTRADA` — «sin vela 1m plenamente conocida en T» | `ENTRADA_EJECUTADA`, fill posterior a T, salida por horizonte |
| `desfase_59998` | 59 998 | `SIN_ENTRADA` — «sin vela 1m plenamente conocida en T» | `ENTRADA_EJECUTADA`, fill posterior a T, salida por horizonte |
| `desfase_59999` | 59 999 | `ENTRADA_EJECUTADA` | `ENTRADA_EJECUTADA`, salida por horizonte |
| `desfase_60001` | 1 (minuto siguiente) | `SIN_ENTRADA` — «sin vela 1m plenamente conocida en T» | `ENTRADA_EJECUTADA`, fill posterior a T, salida por horizonte |

**Totales:** ANTES 5/7 sin vela de referencia y 2 entradas; DESPUÉS **0/7 sin
vela de referencia, 7 entradas y 7 salidas ejecutadas**.

### Invariantes comprobadas sobre el recorrido real

- La fila operativa **no** dice «sin vela 1m plenamente conocida en T» cuando
  la referencia existe; y **sí** lo dice (abstención explícita, `qty = 0`,
  `open_at_end = false`) cuando el proveedor no tiene esa vela.
- El **fill es posterior a T**: `entry_ms` = apertura de la primera vela con
  `open_time_ms > T`.
- **Ningún dato futuro en la decisión**: la referencia usada cierra en
  `ref_open + 60 000 - 1 <= T`; el `stop_px` se deriva de ese mismo close
  (`ref × (1 ∓ 0,5 %)`); la vela que contiene a T (cierre posterior) queda
  descartada por `_vela_plenamente_conocida_en`.
- El **horizonte está cubierto sin truncar**: la serie va de la vela cerrada
  en T a la **primera vela que abre después del horizonte**, con
  `n_rows == limit == 63`.
- **LONG y SHORT** recorren el camino completo con el mismo criterio (el rol
  no altera la decisión).
- **Capacidad compartida** preservada: con dos señales en el mismo instante,
  la segunda sale como `RECHAZADA_CAPACIDAD` con `qty = 0` y etiqueta
  «rechazo por capacidad sin posicion».
- **Persistencia y resumen coherentes**: el resumen del piloto cuenta lo
  mismo que las filas persistidas; los netos COMPLETO y CONDICIONADO se
  contabilizan por separado y las filas `UNKNOWN` no entran en ninguno.

### Regresiones directamente afectadas

| Suite | Resultado |
|---|---|
| `test_research_pilot.py`, `test_experimento_operativo_local.py`, `test_recorrido_productivo.py`, `test_aceptacion_coordinacion_recepcion.py` | **57 passed** |
| `test_operativo_adapter_local.py`, `test_operativo_capacidad_presupuesto.py`, `test_operativo_cli_integrado.py`, `test_pilot_monitor_observabilidad.py`, `test_backtest_funding_coverage.py` | **50 passed** |
| Suite completa | 1 918 passed, 2 skipped, **12 failed** |

Los **12 fallos son preexistentes y ajenos** (identicos con el código
publicado, verificado ejecutando esos ficheros con el árbol publicado):
`test_engineering_live_window_local.py` (7), `test_market_stream_window.py`
(3), `test_session_new_public_market.py` (1) y
`test_public_run_deadline.py` (1, dependiente de timing). No se amplió el
trabajo a ellos.

---

## Capa 3 — Qué permite evaluar el dataset existente (económica exploratoria)

**Naturaleza:** esto es una **reevaluación posterior a corregir un defecto de
implementación**, **no** una validación prospectiva independiente.

### 3.1 Inventario de lo que existe realmente

| Material | Estado | Utilidad |
|---|---|---|
| 219 observaciones (179 aptas) con `decision_ms`, `seleccion.move_24h_pct`, frescura de libro/flujo, `precio_base` (libro mid) | **presente** | dirección e instante de decisión |
| Ledger HTTP (`http_requests.jsonl`, 740 filas) con `params` (incluido `startTime`/`endTime`/`limit`), `response_item_count`, `response_sha256` | **presente** | reconstrucción exacta de la consulta |
| **Cuerpos de las respuestas `klines`** (las velas del venue) | **AUSENTES** | solo queda el SHA-256 y el recuento: **un hash no sustituye las velas** |
| `research_flow_1m` (1 253 filas, 47 símbolos, OHLC de **aggTrade**) | **presente pero otra fuente** | proxy de trades, no la serie `klines` del venue |
| `research_book_1m` (1 200 filas) | presente | agregados de microestructura, **sin serie OHLC** |
| `funding_adquisicion.jsonl` (**0 B**) y **0** peticiones `fundingRate` | **AUSENTE** | ninguna liquidación: el funding queda UNKNOWN |

El hash del original se verificó **antes y después**: **intacto**
(`manifiesto.json`).

### 3.2 REEvaluación A — reconstrucción a nivel de consulta (exacta, sin precios)

Para cada una de las **179** consultas de trayectoria registradas en el ledger
(`reconstruccion_consulta.jsonl`):

| Comprobación | Resultado |
|---|---|
| `startTime` registrado == `decision_ms - 60 000` (borde publicado) | **179/179** |
| `limit` registrado | **62** en 179/179 (`response_item_count = 62`) |
| Con el borde **publicado**, la vela cerrada en T queda **dentro** de la serie | **0/179** |
| Con el borde **corregido**, la vela cerrada en T queda **dentro** | **179/179** |
| Con el borde corregido, la serie **pasa del horizonte** | **179/179** |

Esto es determinista: usa solo `decision_ms`, el ledger y la semántica
documentada del proveedor (`openTime >= startTime`, tope de filas = `limit`).
Acredita que la corrección recupera la referencia en **todas** las
observaciones reales de la ventana.

### 3.3 REEvaluación B — cobertura de datos (faltantes exactos)

Trayectoria que necesita la consulta corregida: 63 velas 1 m por observación
(de la vela cerrada en T a la primera que abre tras el horizonte).

| Magnitud | Valor |
|---|---|
| Trayectorias **completas** en el dataset capturado | **0/179** |
| Referencia disponible en la serie capturada (aggTrade) | 179/179 |
| Velas necesarias | **11 277** |
| Velas disponibles en el dataset capturado | **5 006** |
| Velas **faltantes** | **6 271 (55,6 %)** |

Motivo estructural: la captura duró **60 min** y el horizonte operativo es de
**60 min** después de cada decisión; las decisiones se reparten por esos
mismos 60 min, luego **el horizonte de todas las decisiones cae fuera (o en el
borde) de la ventana capturada**. Además, la serie disponible es de **aggTrade**
y no la serie `klines` del venue: usarla cambiaría la fuente de precios y no
sería la evaluación de la regla.

### 3.4 Conclusión económica de la reevaluación

| Neto | n | Suma |
|---|---|---|
| COMPLETO | **0** | `null` |
| CONDICIONADO (sin funding completo) | **0** | `null` |
| UNKNOWN | **179** | `null` |

Comparación candidato/comparador: **`INSUFICIENTE`**.

**Qué NO permite el dataset:** recalcular entradas, stops, salidas, costes o
funding de ninguna observación; comparar candidato contra comparador; y
cualquier afirmación sobre rentabilidad, edge o ejecutabilidad. **Qué sí
permite:** probar que la corrección recupera la referencia en las 179
observaciones reales (3.2) y quantify exactamente qué falta y cuántas
observaciones (3.3).

No se rellenó ningún hueco, no se sustituyó la serie del venue por la de
aggTrade para producir un P&L, no se abrió red y **no se propone
automáticamente otra ventana**.

### 3.5 Conclusión sobre la hipótesis económica

**Ninguna.** La ventana `exp-v2-ventana-2-20261112a` sigue siendo
**INSUFICIENTE**: 179 abstenciones, 0 entradas, 0 salidas, neto `n = 0` y
`null`. La corrección **elimina la causa artificial** de esas abstenciones, pero
**no** aporta ninguna evidencia sobre la hipótesis: el dataset no contiene lo
que hace falta para evaluarla. La diferencia entre la ventana y un resultado
económico sigue siendo **una ventana nueva con autorización propia**, y este
bloque **no** la abre.

---

## Presupuesto (sin red, ruta de preparación separada)

El cambio afecta al rango y al tope de la consulta, así que el presupuesto se
recalculó con `--budget-only` **sin red** y en una **ruta de preparación
separada** (`presupuesto_borde.json`, `presupuesto_comparacion.json`):

| Magnitud | Recalculado | Publicado |
|---|---|---|
| Gate | `cabe_en_limites: true`, **13/13** | `true`, **13/13** |
| Peso REST estimado | **1 472** | 1 472 |
| Intentos base + reservas | **1 334** | 1 334 |
| Almacenamiento reservado | 82 174 080 B | 82 174 080 B |
| **Claves distintas (comparación exhaustiva)** | **0** | — |

**No se aumentó ningún cupo.** El motivo: el número de consultas no cambia
(1 por observación apta), el peso por consulta es el del modelo de política
(independiente del `limit` en el rango aplicado) y el cuerpo de la trayectoria
no se persiste (solo su SHA-256).

---

## Alcance, límites y preservación

- **No** se abrió mercado: ni Binance, ni consultas públicas, ni capturas, ni
  ventanas, ni relanzamientos. `exp-v2-ventana-2-20261112a` **no** se reutiliza.
- **No** se tocó `opencode.json`, los ficheros ajenos sin seguimiento, las
  bases de datos canónicas, el dashboard 3020 ni el servicio 8792; no se
  añadieron dependencias, infraestructura, indicadores ni una versión paralela
  del experimento.
- **No** se cambió la regla económica, ni el selector, ni la capacidad, ni los
  presupuestos.
- La corrección **no está validada contra el venue**: solo hay evidencia local
  en loopback y la reconstrucción determinista sobre el ledger real.
- Cobertura de contrato: el selector sigue limitado a **PERPETUAL/TRADING/USDT**;
  los futuros con vencimiento siguen **sin cobertura**.
- El **funding** sigue sin ejercitarse: en la aceptación local no hay
  calendario real, luego las operaciones cerradas quedan `CONDICIONADO_SIN_
  FUNDING_COMPLETO` y nunca `COMPLETO`.

## Manifiesto

| Artefacto | Contenido |
|---|---|
| `antes_despues.json` | antes/después por instancia de decisión (recorrido real) |
| `aceptacion_local.json` · `aceptacion_pytest.txt` | pruebas, comandos y resultado observado |
| `reconstruccion_consulta.jsonl` | 179 reconstrucciones a nivel de consulta |
| `inventario_cobertura.jsonl` | 179 inventarios de cobertura y faltantes |
| `neteo_conclusion.json` · `resumen.json` | netos COMPLETO/CONDICIONADO/UNKNOWN y resumen |
| `config_reevaluacion.json` | `source_run_id`, SHA original/código, configuración |
| `presupuesto_borde.json` · `presupuesto_comparacion.json` | presupuesto recalculado y comparación |
| `manifiesto.json` · `hashes.json` | SHA-256 de la evidencia, del dataset original y de los derivados |
| `INFORME.md` | este informe |

**Fuera de Git (referenciado por hash en `manifiesto.json`):**

- Dataset original **intacto**:
  `C:\proyectos\binance-futures-data\exp-v2-ventana-2-20261112a` (16 ficheros,
  hashes antes y después verificados).
- Derivados de la reevaluación:
  `C:\proyectos\binance-futures-data\exp-v2-ventana-2-20261112a-reevaluacion-offline`
  (6 ficheros).
- Presupuesto recalculado (ruta de preparación separada):
  `C:\Users\adonm\AppData\Local\Temp\opencode\presupuesto-borde-v1`.
