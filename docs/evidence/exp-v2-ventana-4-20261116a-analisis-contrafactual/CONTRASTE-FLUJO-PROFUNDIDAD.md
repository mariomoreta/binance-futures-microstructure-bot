# CONTRASTE FLUJO/PROFUNDIDAD vs CONTINUACION/REVERSION — `exp-v2-ventana-4-20261116a`

Contexto: bloque de investigacion offline autorizado el 2026-11-16
("INVESTIGACION OFFLINE DE LA SENAL, SIN MERCADO"). Sin Binance, consultas
publicas, capturas, ordenes, relanzamientos, ventanas nuevas ni cambios en la
estrategia productiva. Dataset fuente verificado contra manifiesto (10/10)
antes y despues; no modificado.

Este bloque es EXPLORATORIO. Los resultados de esta captura ya fueron
examinados en el bloque anterior: no se presenta como prueba independiente ni
como protocolo prerregistrado.

## 1. Definiciones (fijadas antes de generar agregados)

- ratio = (buy_notional - sell_notional) / (bid_notional_top20 + ask_notional_top20)
  con flujo de 60 segundos y profundidad top20 efectivamente registrada.
- ratio_alineado = signo(move_24h_pct) * ratio
  (flujo a favor del movimiento previo si > 0, contrario si < 0).
- Se exige: buy_notional y sell_notional validos, denominador finito y
  estrictamente positivo, move_24h_pct valido y distinto de cero.
- Cero o datos insuficientes: grupo separado, nunca convertido en cero.

Resultado posterior (horizonte principal 60 min, causal, precios desde cuerpos
persistidos de consultas_klines.jsonl):
- precio_inicial = ref_close: close de la ultima vela 1m plenamente conocida
  en T (close_time_ms <= decision_ms).
- precio_final = close de la vela mas reciente con close_time_ms <= T + 60 min.
- retorno = (precio_final - precio_inicial) / precio_inicial
- retorno_alineado = signo(move_24h_pct) * retorno
- continuacion: retorno_alineado > 0
- reversión: retorno_alineado < 0
- neutral: retorno_alineado == 0 exactamente

Usa TODAS las 161 observaciones aptas con datos suficientes (no solo las 124
operaciones contrafactuales). Los 37 descartes por la regla de stop no
desaparecen: se evalúan si tienen datos de flujo/profundidad y precio final.

## 2. Configuracion acreditada (sin defaults)

El analizador carga `config_inicial.json` (persistido atomicamente antes de la
primera adquisicion) y **no usa `OperativoConfig()` por defecto**. Valida los
hashes `config_sha256` y `operativo_config_sha256` (ambos OBLIGATORIOS:
ausente, vacio o discordante -> rechazo antes de reconstruir).

Configuracion de la corrida:
- `operativo_config_sha256`: d1423709f4d45207cea601f1aad11742c70f7dfdee44ee69a75701fba60be8ed
- `config_hash` (corto): d1423709f4d45207
- `git_head`: ce2af020c666956ba35a1e1d41d0007c85d581a7
- `run_id`: exp-v2-ventana-4-20261116a
- `escrito_iso`: 2026-11-16T19:26:18.038000+00:00
- fee_bps 5.0, spread_bps 1.0, slippage_bps 2.0, stop_distance_pct 0.5,
  horizon_ms 3600000, notional_usdt 1000, max_concurrent 1,
  rule_version RULE-CAUSAL-V1.

Funding: UNKNOWN donde falte cobertura (nunca cero). No se supone calendario.

## 3. Mapa campo -> fuente -> unidad -> disponibilidad

| Campo | Fuente | Unidad | Disponibilidad |
| --- | --- | --- | --- |
| move_24h_pct | observaciones.seleccion | puntos porcentuales | siempre (en aptas) |
| buy_notional | observaciones.flujo | USDT (compras agresoras, 60s) | siempre (en aptas) |
| sell_notional | observaciones.flujo | USDT (ventas agresoras, 60s) | siempre (en aptas) |
| bid_notional_top20 | observaciones.libro | USDT (pujas top20) | siempre (en aptas) |
| ask_notional_top20 | observaciones.libro | USDT (ofertas top20) | siempre (en aptas) |
| decision_ms | observaciones | ms epoch UTC (reloj piloto) | siempre |
| ref_close (precio inicial) | consultas_klines (close <= T) | precio | siempre |
| precio_final 60m | consultas_klines (close <= T+60m) | precio | siempre (161/161 resoluble) |
| window_ms flujo | observaciones.flujo.window_ms | ms (60000 = 60s) | siempre |
| disponibilidad | observaciones.disponibilidad | ms | siempre |
| cobertura | observaciones.cobertura | booleano | siempre |

Todos los datos son del exchange publico (WS/REST USD-M), no on-chain. No se
inventaron campos, cobertura ni disponibilidad temporal.

## 4. Resultado del contraste principal

Denominador: 161 observaciones aptas, todas evaluadas (0 insuficientes, 0
exclusiones).

| Grupo (ratio_alienado) | n | % sobre evaluadas | continuación | reversión | neutral | retorno alineado media |
| --- | --- | --- | --- | --- | --- | --- |
| flujo a favor (>0) | 73 | 45.3% | 45 (61.6%) | 28 (38.4%) | 0 | +0.0269 |
| flujo contrario (<0) | 88 | 54.7% | 61 (69.3%) | 27 (30.7%) | 0 | +0.0106 (agregado grupo) |

Nota: el retorno alineado medio del grupo "flujo contrario" agregado (incluye
continuación y reversión) es +0.0106; el de "flujo a favor" es +0.0121.
Dentro de cada grupo, las operaciones de continuación tienen retorno positivo
y las de reversión, negativo (por construcción del signo alineado).

### Regla sencilla de referencia (direccion = signo(move_24h_pct), sin flujo)
- n = 161, aciertos (retorno alineado > 0) = 106, proporcion = 65.8%.

### Comparacion
- Regla sencilla: 65.8% de continuación.
- Flujo a favor del movimiento previo: 61.6% de continuación.
- Flujo contrario al movimiento previo: 69.3% de continuación.

El flujo a favor **NO** distingue mejor continuación que la regla sencilla
(61.6% < 65.8%). De forma contraintuitiva, el grupo de flujo contrario muestra
ligeramente MAS continuación (69.3%) que el de flujo a favor y que la regla
sencilla. El retorno alineado medio es similar entre grupos (+0.0269 vs
+0.0299 en las operaciones de continuation).

## 5. Desgloses

### Por rol
| Rol | n | continuación | reversión | % continuación | retorno medio alineado |
| --- | --- | --- | --- | --- | --- |
| candidate | 130 | 90 | 40 | 69.2% | +0.0149 |
| comparator | 31 | 16 | 15 | 51.6% | +0.0011 |

### Por direccion (signo de move_24h_pct)
| Direccion | n | continuación | reversión | % continuación | retorno medio alineado |
| --- | --- | --- | --- | --- | --- |
| LONG | 87 | 59 | 28 | 67.8% | +0.0221 |
| SHORT | 74 | 47 | 27 | 63.5% | +0.0006 |

### Por ciclo (muy variable, dependencia temporal)
El porcentaje de continuación dentro de cada grupo fluctua de 0% a 100%
según el ciclo (ej. ciclo00: flujo a favor 25%, flujo contrario 64%;
ciclo02: flujo a favor 100%, flujo contrario 57%; ciclo06: flujo contrario
100%). No hay patrón estable.

### Concentracion de simbolos
- 25 simbolos unicos, 19 repetidos (>=2 apariciones, hasta 12 veces).
- Los mismos símbolos aparecen en varios ciclos => dependencia temporal,
  los escenarios NO son ensayos independientes.
- Ejemplos de repeticion con continuaión desigual: AIOTUSDT 12/12 (100%),
  BULLAUSDT 0/12 (0%), CROSSUSDT 12/12 (100%), BANKUSDT 0/4 (0%).

## 6. Sensibilidad al mayor resultado

El mayor retorno alineado es +0.1486 (grupo flujo contrario, continuación,
ciclo 08). Este resultado extremo se conserva en el resultado principal
(n=161, incluida su contribucion). El bruto agregado de todos los demas
escenarios ya es positivo gracias a varias ganancias por horizonte; no hay
un único resultado que domine de forma indebida, pero la variacion por ciclo
y simbolo es alta. No se elimina ni se ajusta ningun resultado.

## 7. Decision final

**Resultado debil, contradictorio o concentrado.**

Evidencia que determina la conclusion:
- El flujo a favor del movimiento previo NO produce mas continuation que el
  flujo contrario (61.6% vs 69.3%). La hipotesis exploratoria
  ("el primer grupo presenta mas continuacion que el segundo") NO se confirma.
- La regla sencilla (signo 24h, sin flujo) obtiene 65.8%, superior al grupo
  de flujo a favor (61.6%). El ratio flujo/profundidad no aporta informacion
  predictiva superior en esta muestra.
- Alta variacion por ciclo y simbolo (dependencia temporal, escenarios
  solapados, simbolos repetidos hasta 12 veces). No se pueden tratar las
  observaciones como ensayos independientes.
- No hay neutrales (todos los retornos alineados son != 0), lo que limita la
  interpretacion de "neutral".

No se puede concluir que el ratio flujo/profundidad distinga continuación de
reversión mejor que asumir continuación por el signo del movimiento de 24
horas. **No se incorpora el ratio a la estrategia productiva.** No se
optimizan umbrales, no se invierten senales, no se cambian entradas, stops ni
capacidad.

Asociacion vs causalidad: incluso la ligera diferencia descriptiva entre
grupos no implica causalidad, y una mejora descriptiva no es predictividad.
El retorno no es P&L; el analisis economico anterior sigue condicionado por
costes simulados y funding UNKNOWN.

## 8. Artefactos

- Fuente (solo lectura, intacta): `C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a\` (manifiesto 10/10 verificado antes y despues).
- Derivados (fuera de Git, directorio nuevo, resultados NO reutilizados de bloques previos):
  `C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-contraste-flujo-profundidad-20261116-v2\`
  (`contraste_flujo_profundidad.json`, `contraste_filas.jsonl`).
- Ejecucion: SHA base `509b5bacf8a099fc553e201f18674985a2889866`;
  script `scripts/contraste_flujo_profundidad.py` (CLI `--run-dir`/`--out-dir`,
  sin rutas fijas en codigo);
  `scripts/desgloses_contraste.py` (desgloses por rol, direccion, ciclo,
  concentracion, mapa de campos);
  `tests/test_contraste_flujo_profundidad.py` (6 passed: denominador 161,
  grupos suman 161, ratio denominador finito > 0, horizonte 60m resoluble,
  regla sencilla 106/161, descartes de stop no desaparecen).
- Regresiones: `test_analisis_contrafactual_ventana4.py` 16 passed,
  `test_operativo_replay_offline.py` 7 passed.

## 9. Comparacion anterior/corregido (hash de configuracion)

El bloque anterior (`26fdf86`) ya validaba `operativo_config_sha256` pero solo
cuando estaba presente (`if hash_declarado:`). Este bloque lo hace OBLIGATORIO:
ausente, vacio o mal formado -> rechazo explícito antes de reconstruir
resultados economicos, y se valida tambien `config_sha256`. Se añadieron 5
pruebas focalizadas (hash valido, ausente, vacio, invalido, discordante).
Los resultados numericos del contraste son independientes de esta correccion
(el hash del run real es valido y coincide).

## 10. Lo que NO acredita

Rentabilidad, edge, mejora predictiva del ratio flujo/profundidad, ventaja de
candidato sobre comparador, generalizacion (una sola hora de captura,
dependencia temporal, simbolos repetidos). El analisis economico del bloque
anterior sigue condicionado por costes simulados y funding UNKNOWN.
