# CONTRASTE FLUJO/PROFUNDIDAD vs CONTINUACION/REVERSION — `exp-v2-ventana-4-20261116a`

Contexto: bloque de investigación offline autorizado el 2026-11-16
("INVESTIGACIÓN OFFLINE DE LA SEÑAL, SIN MERCADO", seguido de
"CIERRE OFFLINE DEL CONTRASTE Y DISEÑO DE LA SIGUIENTE PRUEBA"). Sin Binance,
consultas públicas, capturas, órdenes, relanzamientos, ventanas nuevas ni
cambios en la estrategia productiva. Dataset fuente verificado contra
manifiesto (10/10) antes y después; no modificado.

Este bloque es EXPLORATORIO. Los resultados de esta captura ya fueron
examinados: no se presenta como prueba independiente ni como protocolo
prerregistrado.

## 1. Qué se probó realmente (rectificación de alcance)

El contraste separó las observaciones mediante:

ratio_alineado = signo(move_24h_pct) ×
                 (buy_notional − sell_notional) /
                 (bid_notional_top20 + ask_notional_top20)

con denominador estrictamente positivo. Como la magnitud del denominador no
cambia el signo, comparar ratio_alineado > 0 frente a < 0 prueba **solo**
la alineación del flujo neto con el movimiento previo (dirección).

**No prueba** si una profundidad pequeña frente a un flujo grande anticipa
movimientos mayores (intensidad). Esa es una pregunta distinta, dejada como
hipótesis futura (ver §4). Por tanto:

- No se concluye que la hipótesis "flujo/profundidad" fue refutada.
- No se concluye que el ratio no tenga valor predictivo de magnitud.
- Solo se constata que, en esta captura de una hora, la alineación de dirección
  del flujo neto con el movimiento de 24 horas no distingue continuación de
  reversión mejor que asumir continuación por el signo del movimiento previo.

## 2. Comprobación de profundidad (propiedad del ratio)

Con el mismo flujo y el mismo movimiento previo, variar la profundidad
positiva (denominador) cambia el **valor absoluto** del ratio, pero no su
signo; por tanto, no cambia el grupo (flujo a favor / flujo contrario).
Esto se verifica aritméticamente: ratio = Δnotional / profundidad, con
profundidad > 0, el signo depende solo de Δnotional. El contraste no
necesita variar la profundidad para cambiar de grupo; el grupo está dado por
la dirección del flujo neto respecto al movimiento previo.

## 3. Acreditación del horizonte de precios (corregido)

Cada observación conserva trazabilidad completa del horizonte:

- decision_ms real (reloj del piloto).
- objetivo T + 60 min.
- open_time y close_time de la vela inicial (última vela 1m plenamente
  cerrada conocida en T) y de la vela final (última vela 1m plenamente
  cerrada conocida en T + 60 min).
- precios inicial y final; desfase de cada cierre respecto de su objetivo;
- horizonte efectivo entre ambos cierres.

Reglas de selección (aplicadas a las 161 observaciones aptas):
- Última vela 1m plenamente cerrada conocida en/antes de cada objetivo.
- No se usan cierres posteriores a cada objetivo.
- No se usa una vela antigua como sustituto silencioso del precio al
  horizonte: exige desfase = objetivo − close_time_ms no negativo y menor
  de 60 000 ms.
- Grid del minuto: open_time_ms múltiplo de 60 000 y
  close_time_ms == open_time_ms + 59 999.
- Se declara el horizonte efectivo y cualquier discrepancia.

Resultado de la acreditación en las 161 observaciones aptas:
- 161/161 con precio inicial y final válidos.
- Desfase inicial: 21 801–27 191 ms (todos < 60 000 ms).
- Desfase final: 21 801–27 191 ms (todos < 60 000 ms).
- Horizonte efectivo: 3 600 000 ms (exactamente 60 min) en todas;
  0 discrepantes.
- open_time de ambas velas múltiplo de 60 000; close = open + 59 999.

Por tanto, todas las 161 observaciones siguen siendo válidas; ninguna se
convierte en cero ni se elimina del denominador. Los resultados numéricos son
idénticos a la versión anterior del contraste (ver §7).

## 4. Resultado del contraste principal

Denominador: 161 observaciones aptas, todas evaluadas (0 insuficientes, 0
exclusiones).

| Grupo (ratio_alienado) | n | % sobre evaluadas | continuación | reversión | neutral | retorno alineado media |
| --- | --- | --- | --- | --- | --- | --- |
| flujo a favor (>0) | 73 | 45.3% | 45 (61.6%) | 28 (38.4%) | 0 | +0.0269 |
| flujo contrario (<0) | 88 | 54.7% | 61 (69.3%) | 27 (30.7%) | 0 | +0.0121 (agregado del grupo) |

Nota: dentro de cada grupo, las operaciones de continuación tienen retorno
alineado positivo y las de reversión, negativo (por construcción del signo
alineado).

### Regla sencilla de referencia (dirección = signo(move_24h_pct), sin flujo)
- n = 161, aciertos (retorno alineado > 0) = 106, proporción = 65.8%.

### Comparación
- Regla sencilla: 65.8% de continuación.
- Flujo a favor del movimiento previo: 61.6% de continuación.
- Flujo contrario al movimiento previo: 69.3% de continuación.

El flujo a favor **NO** distingue mejor continuación que la regla sencilla
(61.6% < 65.8%). De forma contraintuitiva, el grupo de flujo contrario
muestra ligeramente MÁS continuación (69.3%) que el de flujo a favor y que
la regla sencilla. El retorno alineado medio es similar entre los grupos de
continuación (+0.0269 vs +0.0299).

## 5. Desgloses

### Por rol
| Rol | n | continuación | reversión | % continuación | retorno medio alineado |
| --- | --- | --- | --- | --- | --- |
| candidate | 130 | 90 | 40 | 69.2% | +0.0149 |
| comparator | 31 | 16 | 15 | 51.6% | +0.0011 |

### Por dirección (signo de move_24h_pct)
| Dirección | n | continuación | reversión | % continuación | retorno medio alineado |
| --- | --- | --- | --- | --- | --- |
| LONG | 87 | 59 | 28 | 67.8% | +0.0221 |
| SHORT | 74 | 47 | 27 | 63.5% | +0.0006 |

### Por ciclo (muy variable, dependencia temporal)
El porcentaje de continuación dentro de cada grupo fluctúa de 0% a 100%
según el ciclo (ej. ciclo 00: flujo a favor 25%, flujo contrario 64%;
ciclo 02: flujo a favor 100%, flujo contrario 57%; ciclo 06: flujo contrario
100%). No hay patrón estable.

### Concentración de símbolos
- 25 símbolos únicos, 19 repetidos (≥2 apariciones, hasta 12 veces).
- Los mismos símbolos aparecen en varios ciclos → dependencia temporal,
  los escenarios NO son ensayos independientes.
- Ejemplos de repetición con continuación desigual: AIOTUSDT 12/12 (100%),
  BULLAUSDT 0/12 (0%), CROSSUSDT 12/12 (100%), BANKUSDT 0/4 (0%).

## 6. Sensibilidad al mayor resultado

El mayor retorno alineado es +0.1486 (grupo flujo contrario, continuación,
ciclo 08). Este resultado extremo se conserva en el resultado principal
(n=161, incluida su contribución). No se elimina ni se ajusta ningún
resultado para volver positiva la captura.

## 7. Comparación anterior/corregido (acreditación del horizonte)

Se compararon los derivados anteriores (`...-v2\`) con los corregidos
(`...-v3\`) por observation_id:

| Dimensión | Resultado |
| --- | --- |
| Identificadores, estados, timestamps | Igualdad exacta en las 161 filas |
| Importes económicos | Tolerancia absoluta 1e-6; **0 diferencias numéricas** |
| Desfases / horizonte | v2 no los acreditaba; v3 los declara (todos < 60 000 ms, horizonte = 3 600 000 ms) |
| Denominador total | 161 (v1) = 161 (v2) |
| Observaciones válidas | 161 (v1) = 161 (v2) |
| Observaciones limitadas | 0 (v1) = 0 (v2) |
| Grupos y conteos | idénticos (73/88/0) |
| Cambios de clasificación | ninguno |

Las 161 observaciones siguen siendo válidas; los resultados se conservan.
No se cambiaron cortes, horizonte ni definición. No se invirtió el filtro
porque el grupo contrario mostró más continuación.

## 8. Decisión final

**Resultado débil, contradictorio o concentrado.**

Evidencia que determina la conclusión:
- El flujo a favor del movimiento previo **no** produce más continuación que
  el flujo contrario (61.6% vs 69.3%). La hipótesis exploratoria de que el
  flujo a favor predice mejor continuación **no se confirma**.
- La regla sencilla (signo 24h, sin flujo) obtiene 65.8%, superior al grupo
  de flujo a favor (61.6%). El ratio flujo/profundidad no aporta información
  predictiva de dirección superior en esta muestra.
- Alta variación por ciclo y símbolo (dependencia temporal, escenarios
  solapados, símbolos repetidos hasta 12 veces). No se pueden tratar las
  observaciones como ensayos independientes.
- No hay neutrales (todos los retornos alineados son ≠ 0).

No se puede concluir que el ratio flujo/profundidad distinga continuación de
reversión mejor que asumir continuación por el signo del movimiento de 24
horas. Asociación ≠ causalidad; mejora descriptiva ≠ predictividad; retorno
≠ P&L. El análisis económico del bloque anterior sigue condicionado por
costes simulados y funding UNKNOWN.

## 9. Hipótesis futura (no ejecutada en este bloque)

**Pregunta principal seleccionada: A (intensidad y tamaño del flujo neto
respecto a la profundidad).**

Justificación: la dirección (pregunta B) ya se probó en este bloque y resultó
débil/contradictoria. La intensidad —si un flujo neto grande relativo a la
profundidad disponible se asocia con un movimiento posterior **mayor**
(independiente de dirección)— es más informativa para la operativa, porque
permite dimensionar posición o decidir operar/no operar, no solo elegir
dirección.

- **Hipótesis falsable:** Cuanto mayor sea el valor absoluto del ratio
  (buy_notional − sell_notional) / (bid_notional_top20 + ask_notional_top20)
  observado en T, mayor será el valor absoluto del retorno posterior alineado
  en el horizonte de 60 min.
- **Variable en T:** ratio flujo/profundidad (adimensional), y su valor
  absoluto.
- **Resultado posterior:** |retorno| en 60 min (causal, desde klines
  persistidos).
- **Horizonte:** 60 minutos, con la misma acreditación de precios de este
  bloque (desfase < 60 000 ms, grid del minuto).
- **Referencia de comparación:** regresión de |retorno| sobre |ratio|;
  comparar contra la media de |retorno| sin condicionar al ratio.
- **Controles de dependencia:** agrupar por símbolo y ciclo; no tratar
  observaciones como independientes; reportar concentración de símbolos.
- **Criterio:** continuar si la asociación es clara y robusta a símbolos;
  descartar si no hay asociación; declarar insuficiencia si los datos no
  alcanzan (ej. horizonte no resuelto para muchas observaciones).
- **Datos independientes necesarios:** esta captura ya fue examinada y **no**
  puede convertirse en validación independiente; se requeriría una captura
  nueva con su propia autorización.

**No se calculan nuevos agregados de magnitud ni se exploran umbrales sobre
esta captura.** Esta hora ya fue examinada y no puede convertirse en
validación independiente.

## 10. Artefactos

- Fuente (solo lectura, intacta): `C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a\` (manifiesto 10/10 verificado antes y después).
- Derivados (fuera de Git, directorio nuevo, resultados anteriores NO
  reutilizados como prueba):
  `C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-contraste-flujo-profundidad-20261116-v3\`
  (`contraste_flujo_profundidad.json`, `contraste_filas.jsonl`).
- Ejecución: SHA base `6a1e2683aa482738e777e802d9565e0b08d6f8a6`;
  script `scripts/contraste_flujo_profundidad.py` (CLI `--run-dir`/`--out-dir`,
  sin rutas fijas en código);
  `scripts/desgloses_contraste.py` (desgloses por rol, dirección, ciclo,
  concentración, mapa de campos);
  `tests/test_contraste_flujo_profundidad.py` (13 passed: denominador 161,
  grupos suman 161, ratio denominador finito > 0, horizonte 60 min resuelto,
  regla sencilla 106/161, descartes de stop no desaparecen, selección de
  precios: trayectoria completa, vela posterior no usada, falta final,
  truncada, objetivo alineado, grid no alineado).
- Regresiones: `test_analisis_contrafactual_ventana4.py` 16 passed,
  `test_operativo_replay_offline.py` 7 passed.

## 11. Lo que NO acredita

Rentabilidad, edge, mejora predictiva del ratio flujo/profundidad, ventaja de
candidato sobre comparador, generalización (una sola hora de captura,
dependencia temporal, símbolos repetidos). El análisis económico del bloque
anterior sigue condicionado por costes simulados y funding UNKNOWN.
