# Comparación en condiciones iguales — filtro de flujo/profundidad vs solo precio

Bloque `anclas-comunes-ventana4-20261118` · rama `research/universe-liquidez-v1` · 2026-11-18
Datos: captura `exp-v2-ventana-4-20261116a` en solo lectura. Sin Binance, sin consultas públicas,
sin capturas nuevas, sin órdenes, sin cambios del patrón, sus umbrales ni la estrategia productiva.

## Pregunta

Sobre **las mismas 501 ternas acreditadas** y con **la misma información disponible al decidir**,
¿qué episodios retiene `SECUENCIA-PRESION-V1` (precio + flujo + profundidad) frente a una regla de
solo precio, y qué pasó después en ambos grupos?

## Qué se igualó y qué no

| Dimensión | Regla aplicada |
|---|---|
| Universo | Exactamente las 501 ternas acreditadas (1 005 ventanas, 43 símbolos). La referencia no recorre ventanas por su cuenta: itera las filas publicadas por el replay y aborta si alguna terna no existe o si el corte recalculado difiere. |
| Reloj | Corte único por terna = `max(cierre nominal de la tercera ventana, disponibilidad de las tres ventanas)`. Idéntico en ambos métodos; la referencia **no puede** evaluar antes del corte. |
| Condición de precio | Tres cierres (`aggTrade`) estrictamente ascendentes → LONG; estrictamente descendentes → SHORT. |
| Condición del patrón | La congelada: precio + Q positivo y creciente + profundidad contraria positiva y decreciente. Sin cambios. |
| Entrada | Apertura del primer minuto **estrictamente posterior** al corte: `(corte // 60 000 + 1) * 60 000`. |
| Salida | Apertura **exactamente 5 minutos** después de la entrada. Sin saltar huecos ni usar otro precio. |
| Vela faltante | El episodio queda **no resoluble** con motivo; no se rellena el hueco. |
| Episodios | Primera alerta por contrato y dirección; repeticiones con corte dentro de los 5 minutos siguientes. |
| Ancla | La primera alerta del episodio, congelada. Su clasificación (con/sin patrón) se decide **en ese instante**. |
| Alerta tardía | Una alerta del patrón posterior al ancla se registra aparte, con su propio corte; **no** reclasifica el ancla ni hereda el retorno de la entrada anterior. |
| Retorno | `signo × (open_salida / open_entrada − 1) × 10⁴`; denominador = precio de entrada. Retorno bruto, **no** P&L. |

## Fuentes y hashes

| Fuente | SHA-256 |
|---|---|
| `exp-v2-ventana-4-20261116a\research.db` | `6ad6f716889a71ceffc5ffc36ed89d904544d3a75facfe1da7c4385b9ad6a7f1` |
| `exp-v2-ventana-4-20261116a\consultas_klines.jsonl` | `4ee61463934e58dd86ec15736738965644b2511b675d92c9f75f48c30ca61874` |
| `C-cobertura-real.json` (universo acreditado) | `39652bf00d594245943ec7114c0e6933fce2e49a8caf2812915cc478f9eaf4bd` |

Hashes verificados antes y después de la corrida; el programa aborta si cambian durante el
procesamiento (`fuentes_intactas: true`). El `db_sha256` declarado en la cobertura coincide con el
de `research.db`. Ver `A-comparacion-comando.txt`.

## Embudo

```text
501 ternas acreditadas (43 símbolos, 1 005 ventanas, 501 cortes verificados idénticos)
 ├─ 290 no monótonas ............................ descartadas por ambos métodos
 └─ 211 alertas de solo precio (104 LONG, 107 SHORT) .... 42.12 % de las ternas
     └─ 143 episodios (71 LONG, 72 SHORT) ............... 68 repeticiones agrupadas
         ├─   4 anclas con patrón (2.80 %) ............... 4 resolubles, 0 no resolubles
         └─ 139 anclas sin patrón (97.20 %) .............. 111 resolubles, 28 no resolubles
```

- Los 4 episodios del patrón y las 4 alertas del patrón son los mismos que en la evaluación
  publicada; cambia el universo de comparación, no el patrón.
- No hay alertas del patrón tardías en esta muestra: las 4 son ancla de su episodio. El mecanismo
  de "tardía" está implementado y probado, pero aquí no se ejerce.
- Un episodio con patrón contiene una repetición que **no** es del patrón (BLESSUSDT SHORT, ancla
  20:06, repetición 20:07): el grupo tiene 5 alertas y 4 anclas.

## Resultado global

| Grupo | Anclas | Resolubles | Faltantes | A / F / N | Media bps | Mediana bps | IC95 media |
|---|---:|---:|---:|---:|---:|---:|---|
| Anclas **con** patrón | 4 | 4 | 0 | 1 / 3 / 0 | −88.37 | −120.53 | [−149.29, −2.42] |
| Anclas **sin** patrón | 139 | 111 | 28 | 56 / 52 / 3 | −5.37 | +2.58 | [−25.71, +13.62] |
| Referencia completa (ambas) | 143 | 115 | 28 | 57 / 55 / 3 | −8.26 | 0.00 | [−29.35, +10.83] |

Faltantes: 23 `sin_velas_para_simbolo` + 5 `vela_entrada_ausente`, todos en anclas sin patrón;
11 símbolos sin velas y 4 con la vela de entrada exacta ausente. No se forzó ningún resultado.

## Resultado por dirección

| Grupo | Dir. | Anclas | Resolubles | A / F / N | Media bps | Mediana bps | IC95 media |
|---|---|---:|---:|---:|---:|---:|---|
| Con patrón | LONG | 2 | 2 | 1 / 1 / 0 | −56.22 | −56.22 | [−156.55, +44.12] |
| Con patrón | SHORT | 2 | 2 | 0 / 2 / 0 | −120.53 | −120.53 | [−142.02, −99.04] |
| Sin patrón | LONG | 69 | 56 | 31 / 25 / 0 | +8.17 | +9.14 | [−18.05, +33.37] |
| Sin patrón | SHORT | 70 | 55 | 25 / 27 / 3 | −19.16 | 0.00 | [−53.26, +8.86] |
| Referencia | LONG | 71 | 58 | 32 / 26 / 0 | +5.95 | +9.14 | [−22.73, +32.26] |
| Referencia | SHORT | 72 | 57 | 25 / 29 / 3 | −22.72 | −1.10 | [−53.78, +5.40] |

## Los cuatro episodios del patrón frente a las anclas comunes

| Símbolo | Dir. | Corte (UTC) | Demora corte | Entrada | Salida | Open entrada | Open salida | Retorno | ¿Ancla común? |
|---|---|---|---:|---|---|---:|---:|---:|---|
| BLESSUSDT | SHORT | 19:30:01.355 | 1 355 ms | 19:31:00 | 19:36:00 | 0.018175 | 0.018355 | −99.04 bps | sí |
| STRKUSDT | LONG | 19:56:04.530 | 4 530 ms | 19:57:00 | 20:02:00 | 0.034000 | 0.034150 | +44.12 bps | sí |
| BLESSUSDT | SHORT | 20:06:00.464 | 464 ms | 20:07:00 | 20:12:00 | 0.017533 | 0.017782 | −142.02 bps | sí |
| ARIAUSDT | LONG | 20:15:00.502 | 502 ms | 20:16:00 | 20:21:00 | 0.210150 | 0.206860 | −156.55 bps | sí |

- **4 de 4 coinciden con un ancla común**; 0 absorbidas por un ancla anterior; 0 tardías.
- En el universo amplio de la evaluación anterior (1 107 ternas) la alerta LONG de STRKUSDT quedó
  **dentro** de un episodio LONG anclado antes y su resultado se publicó en el subconjunto "no
  patrón". Al restringir el universo a las 501 ternas acreditadas, ese ancla anterior desaparece y
  STRKUSDT pasa a ser ancla. Es el efecto esperado de igualar el universo, no un cambio de patrón.
- Los cuatro resultados coinciden exactamente con los publicados (mismas ternas, cortes, precios y
  bps); verificado de forma independiente en `D-verificacion-independiente.txt`.
- Demora corte → entrada: 55 470 a 59 536 ms. Demora corte sobre el cierre nominal de los 143
  episodios: mínimo 224 ms, mediana 690 ms, máximo 21 410 ms.

## Cuánto reduce el filtro y cómo rindieron los retenidos

| Medida | Valor |
|---|---|
| Ternas evaluadas | 501 |
| Alertas de solo precio | 211 (42.12 % de las ternas) |
| Episodios | 143 |
| Anclas retenidas por el filtro | 4 (**2.80 %** de los episodios) |
| Episodios descartados por el filtro | **139** (97.20 %) |
| Retención sobre ternas | 4 / 501 = 0.80 % |
| Media de las retenidas | −88.37 bps (mediana −120.53) |
| Media de las descartadas | −5.37 bps (mediana +2.58) |

El filtro no "selecciona mejor" en el punto observado: retiene 4 de 143 episodios y esos 4 rinden
peor que el conjunto descartado. Con n=4 esto **no** permite concluir deterioro ni mejora; solo
describe esta muestra.

## Concentración y horas

- Con patrón: BLESSUSDT 2/4 (50.0 %), STRKUSDT 1/4, ARIAUSDT 1/4. **Dependencia de un solo símbolo
  declarada** (la mitad de los episodios retenidos); n insuficiente para separarla.
- Sin patrón: máximo SPACEUSDT 10/111 (9.0 %); sin dependencia de un solo símbolo.
- Referencia completa: máximo SPACEUSDT 10/115 (8.7 %).
- Por hora UTC (anclas resolubles, media): con patrón 19 h → 2 episodios, −27.46 bps; 20 h → 2,
  −149.29 bps. Sin patrón 19 h → 54, −5.82 bps; 20 h → 57, −4.95 bps. Referencia 19 h → 56,
  −6.60 bps; 20 h → 59, −9.84 bps.

## Contexto secundario: evaluación publicada de 1 107 ternas

No se sobrescribe ni se usa como comparador válido: su referencia se construyó sobre **ternas de
filas de flujo** (1 107), no sobre las 501 ternas acreditadas, y su corte no incorporaba la
disponibilidad del libro.

| Conjunto | Ternas | Alertas | Episodios | Resolubles | Media bps | Mediana bps |
|---|---:|---:|---:|---:|---:|---:|
| Publicado 2026-11-18 (contexto) | 1 107 | 473 | 237 | 189 | −4.85 | 0.00 |
| Esta comparación (universo igual) | 501 | 211 | 143 | 115 | −8.26 | 0.00 |

La diferencia de medias no es una mejora ni un deterioro del patrón: cambia el universo, el reloj
de corte y por tanto el conjunto de episodios. Se conserva como referencia histórica, con
`sha256 098a61ff818a86e5aba453e6637dd4dca7710e0d78533989cfc453d5160a6c14`.

## Costes (solo sensibilidad)

16 bps de ida y vuelta (fee 5 bps por lado + spread 1 + slippage 2 por lado); **funding UNKNOWN**.

| Grupo | Neto medio | Neto mediano |
|---|---:|---:|
| Con patrón | −104.37 bps | −136.53 bps |
| Sin patrón | −21.37 bps | −13.42 bps |
| Referencia completa | −24.26 bps | −16.00 bps |

## Veredicto

Regla predeclarada: mínimo **30 episodios resolubles por grupo**.

> **datos insuficientes**

4 anclas resolubles con patrón frente a 111 sin patrón. No se puede afirmar mejora ni ausencia de
mejora; el estimador puntual observado es desfavorable (−88.37 vs −5.37 bps de media) y se apoya en
la mitad de los casos de un solo símbolo. No se aflojó el patrón, no se cambió el horizonte ni la
agrupación, y no se buscó otro subconjunto.

## Limitaciones

- La captura ya se usó durante el desarrollo del detector: hallazgo **exploratorio**, no prueba
  independiente.
- Corte reconstruido: la captura no ejecutó el detector en vivo; la entrada es una apertura
  posterior al corte, no un fill, y no incluye latencia real.
- Salida a 5 minutos por apertura, sin stop ni salida intravela; el adverso solo se informa con
  trayectoria completa (aquí no se usa para el veredicto).
- Funding `UNKNOWN`; los costes son sensibilidad documentada.
- Anclas de distintos símbolos pueden solaparse en el tiempo: no son observaciones independientes.
- Cobertura de velas limitada a los símbolos y minutos consultados durante la captura: 28 de 143
  episodios quedan estructuralmente sin resolver.
- El universo sigue siendo PERPETUAL / TRADING / USDT; futuros con vencimiento no están cubiertos.

## Reproducción

```text
python scripts/comparar_anclas_ventana4.py ^
  --db C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a\research.db ^
  --cobertura docs\evidence\secuencia-presion-v1-correcciones-20261117\C-cobertura-real.json ^
  --klines C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a\consultas_klines.jsonl ^
  --salida C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-anclas-comunes-v1 ^
  --resumen docs\evidence\anclas-comunes-ventana4-20261118\C-resumen.json ^
  --contexto docs\evidence\patron-ventana4-evaluacion-20261118\C-resumen.json
```

- `A-comparacion-comando.txt`: comando, stdout, `exit 0`, hashes antes/después, reproducibilidad
  (segunda corrida idéntica salvo el campo de ruta de salida) y hashes de derivados.
- `B-pytest.txt`: 69 pruebas focalizadas, `exit 0` (`test_comparar_anclas_ventana4.py` 9 +
  `test_replay_patron_ventana4.py` 6 + `test_secuencia_presion_v1.py` 24 +
  `test_extraer_cobertura_research_db.py` 7 + `test_analisis_contrafactual_ventana4.py` 16 +
  `test_operativo_replay_offline.py` 7).
- `C-resumen.json`: resumen completo (embudo, grupos, direcciones, concentración, horas, costes,
  contexto, limitaciones, hashes).
- `D-verificacion-independiente.txt`: recálculo sin importar el módulo (211 alertas → 143 episodios
  → 4/139; los 4 episodios del patrón son ancla común; los 4 retornos recalculados desde el JSONL
  original coinciden; coherencia del embudo).
- Derivados voluminosos fuera de Git en
  `C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-anclas-comunes-v1\`
  (alertas, episodios, anclas con/sin patrón, episodios del patrón; hashes en `A` y `C`).

## Qué no autoriza

Este bloque termina aquí. No autoriza otra captura, otra variante del patrón, cambios de umbral,
cableado productivo, Paper Lab, dashboard ni ejecución real.
