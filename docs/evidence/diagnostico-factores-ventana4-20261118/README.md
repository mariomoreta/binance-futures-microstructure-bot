# Factores de los cuatro casos del patrón (ventana 4)

Bloque `diagnostico-factores-ventana4-20261118` · rama `research/universe-liquidez-v1` · 2026-11-18
Base publicada: `d71543c1589d1a6d67154544976e5a1fde05ea50`.
Datos: captura `exp-v2-ventana-4-20261116a` y derivados ya publicados, **solo lectura**. Sin Binance,
sin consultas públicas, sin capturas nuevas, sin órdenes, sin cambios de patrón, umbrales, horizonte,
agrupación ni estrategia productiva.

## Pregunta

En los cuatro casos de `SECUENCIA-PRESION-V1` de la ventana 4 —STRKUSDT LONG (+44.12 bps), ARIAUSDT
LONG (−156.55), BLESSUSDT SHORT 19:30 (−99.04) y BLESSUSDT SHORT 20:06 (−142.02)—, ¿qué factores
distinguieron al ganador de los tres perdedores, y cuándo era conocible cada uno? Se contrasta con las
143 anclas comunes ya publicadas. No se prueba "esperar un minuto" como regla ni se invierte la señal
por defecto.

## Respuesta corta

1. **En el corte, los cuatro casos comparten la misma firma y ninguno separa al ganador.** En los
   cuatro, el ratio Q subió sobre todo porque creció el importe agresor (93.7–99.3 % del crecimiento
   logarítmico); la profundidad contraria cayó solo 0.99–16.81 %. La hipótesis "el ratio subió porque
   se retiró profundidad" es falsa en los cuatro, y el ganador fue justamente el de menor caída de
   profundidad (0.99 %) y mayor peso del importe (99.35 %). Eso no lo distingue: es el extremo de un
   rasgo común.
2. **El impacto marginal no separa: 3 de 4 frenan y el ganador está entre ellos.** STRK 8.64 → 7.60
   bps/1 000 (×0.88), BLESS 19:30 2.56 → 1.46 (×0.57), ARIA 9.93 → 2.72 (×0.27); solo BLESS 20:06
   acelera (0.39 → 2.05, ×5.24) y es perdedor. La "frenada de impacto" aparece en el ganador y en dos
   perdedores.
3. **Los últimos 30 s de la tercera ventana no avisan en el ganador.** STRK cerró el corte con
   +1 390 de flujo alineado y +11.77 bps a favor; el único aviso visible en el corte es BLESS 20:06
   (flujo −45 131, es decir compra, y precio −3.98 bps en contra del SHORT). En las 124 anclas
   evaluables ese giro de 30 s ocurre en el 34.7 % y no separa resultados (18 negativas / 18 positivas
   con giro; 35 / 33 sin giro).
4. **La extensión normalizada por la historia propia es la única medida del corte alineada con el
   ganador, y es la que el bot no evalúa.** STRK 3.51× su mediana de bloques de 3 minutos previos
   (7 bloques, referencia 5.87 bps); BLESS 20:06 6.73× (12 bloques) y 5.35× sus ternas previas. Pero
   BLESS 19:30 y ARIA no tienen historia contigua suficiente (0 bloques) y quedan `UNKNOWN`; en las
   143 anclas solo 56 son evaluables y la diferencia es pequeña y solapada (perdedoras mediana 1.85,
   ganadoras 1.57; máximos 17.7 y 8.2).
5. **Después del aviso sí hubo evidencia a tiempo en los tres perdedores, y no en el ganador.** El
   primer cambio sostenido por datos aparece en el minuto del corte y se conoce ~60 s después
   (mediana 60 059 ms en 131 anclas): BLESS 19:30 a las 19:31:00.252 (antes de la salida 19:36),
   BLESS 20:06 a las 20:07:04.997 (antes de 20:12), ARIA a las 20:16:00.474 (antes de 20:21). En STRK
   el minuto del corte es `PARTIAL_OK` con `as_of` 19.65 s antes de cerrar, los 4 minutos siguientes
   no tienen flujo persistido y el primer cambio observable llega a las 20:02:03.027, **3 s después**
   de la salida original (20:02:00). Es una señal de **evitar pérdida**, no de elegir ganador.
6. **El giro posterior no anticipa reversión: no se invierte.** En los cuatro casos el giro se ve
   excelente (los tres perdedores con giro habrían pasado a +66.09, +14.67 y +67.32 bps), pero en las
   103 anclas comparables la reversión desde la disponibilidad del giro rinde **−2.29 bps de media y
   −5.59 de mediana** (43/103 positivas); en LONG es claramente negativa (n=50, −19.30 / −12.71) y en
   SHORT la media es +13.76 pero la mediana −4.95. Tres casos no hacen una regla.
7. **La "mejora" del primer cambio es el efecto de entrada tardía ya publicado, no una señal nueva.**
   La continuación desde el primer cambio coincide exactamente con la continuación tardía del bloque
   anterior en los 3 casos resolubles (−76.5208, −152.7897, −67.3192) porque su entrada es el minuto
   siguiente al cierre del minuto del corte. Se informa el agregado (+11.27 / +4.42 bps, n=109) como
   reproducción, no como hallazgo independiente.

## Reglas fijadas antes de calcular

| Dimensión | Regla |
|---|---|
| Casos | Las 4 anclas con patrón del universo igualado. Verificadas contra `episodios_patron_originales.jsonl`: 4/4 coinciden en símbolo, dirección, terna, corte y retorno. |
| Anclas | Las 143 de `episodios_referencia_universo_igual.jsonl`; 143/143 verificadas. |
| Bloques posteriores | Ventanas de 1 minuto alineadas al reloj: `b_k = floor(corte/60 s)·60 s + k·60 s`, `k = 0..5`. `b_0` contiene el corte (≥92 % posterior, ≤4.53 s anterior) para conservar la unidad de 1 minuto de la señal. |
| Bloque utilizable | `run_id` esperado, `data_quality = OK`, `as_of_ms ≥ bucket_end` y `bucket_start/bucket_end` coherentes; si no, `UNKNOWN` con motivo y se cuenta entre los no usables anteriores al cambio. |
| Cambio (prioridad) | Flujo alineado `= s × (compras − ventas)`. `giro`: ≤ 0. `debilitamiento`: 0 < alineado < alineado de la 3.ª ventana. `precio_sin_avance`: alineado > 0 y Δcierre ≤ 0. `profundidad_deja_de_caer`: profundidad media contraria > la de la 3.ª ventana. |
| Δcierre | Solo contra el bloque inmediatamente anterior; `b_0` contra el cierre de la 3.ª ventana. Tras un hueco queda `UNKNOWN`: no se rellena. |
| Corte del cambio | `max(bucket_end, as_of del flujo, as_of del libro si es usable)`. Entrada = apertura del primer minuto **estrictamente posterior**; salida = +5 min. |
| Reversión | Solo si el cambio es `giro`, con la misma entrada y salida que la continuación. El módulo **aborta** si la entrada del cambio iguala la entrada original. |
| Extensión 3 min | Avance alineado entre el primer y el tercer cierre de bloques de 3 minutos previos, contiguos y sin solape, que terminan exactamente al inicio de la terna. Referencia = mediana de los movimientos de esos bloques. Mínimo 6 bloques (cobertura, no umbral de señal). |
| Extensión por ternas | La medida ya publicada: mediana de ternas previas no solapadas del mismo contrato, mínimo 6. |
| Descomposición de Q | `Q = \|F\|/D`; `Δlog Q = Δlog\|F\| − Δlog D`; `aporte_importe_pct + aporte_profundidad_pct = 100`. `UNKNOWN` si algún término no es positivo o si Q no crece. |
| Impacto | `impacto_k = Δcierre alineado del tramo k (bps) / (\|F_k\|/1 000)`. `impacto_relativo = impacto_3 / impacto_2`. `frenada_impacto` = impacto_3 < impacto_2 y F3 ≥ F2. `UNKNOWN` si F2 ≤ 0 o impacto_2 ≤ 0. |
| Últimos 30 s | Los 3 buckets de 10 s finales de la 3.ª ventana; `UNKNOWN` si falta uno. `giro_30s` = flujo alineado ≤ 0. `presion_sin_avance_30s` = flujo > 0 y Δprecio ≤ 0. |
| Concentración 10 s | `max \|delta\| / \|suma delta\|` de los 6 buckets de 10 s de la 3.ª ventana; `UNKNOWN` si falta uno. |
| Mínimos | 6 bloques/ternas previos; 30 pares resolubles para la conclusión formal (heredado y fijado antes de mirar resultados). |
| Costes | Retorno bruto. Solo la sensibilidad documentada de 16 bps ida y vuelta, informada aparte. Funding `UNKNOWN`. |

## Los cuatro casos en el corte

| Caso | Dir. | Avance | Ext. 3 min | Ext. ternas | Q (×) | Aporte importe / prof. | Δ prof. contraria | Impacto 2 → 3 (×) | Frenada | Últimos 30 s (flujo / Δprecio) | Concentración | Retorno |
|---|---|---:|---|---|---:|---|---:|---|---|---|---:|---:|
| BLESS 19:30:01.355 | SHORT | 115.75 bps | `UNKNOWN` (1 min previo, 0 bloques) | `UNKNOWN` (0 previas) | 0.26 → 6.25 (×23.7) | 96.22 % / 3.78 % | −11.29 % | 2.56 → 1.46 (×0.57) | sí | +46 439 / +52.20 bps | 0.628 | −99.04 bps |
| STRK 19:56:04.530 | LONG | 20.62 bps | **3.51×** (7 bloques, ref. 5.87) | `UNKNOWN` (4 previas, ref. 13.20) | 0.0014 → 0.0065 (×4.6) | 99.35 % / 0.65 % | −0.99 % | 8.64 → 7.60 (×0.88) | sí (leve) | +1 390 / +11.77 bps | `UNKNOWN` | **+44.12 bps** |
| BLESS 20:06:00.464 | SHORT | 326.24 bps | 6.73× (12 bloques, ref. 48.49) | **5.35×** (6 previas, ref. 61.03) | 0.11 → 20.59 (×189.1) | 97.42 % / 2.58 % | −12.67 % | 0.39 → 2.05 (×5.24) | no (acelera) | **−45 131 / −3.98 bps** | 0.866 | −142.02 bps |
| ARIA 20:15:00.502 | LONG | 117.03 bps | `UNKNOWN` (0 bloques) | `UNKNOWN` (4 previas, ref. 166.88) | 0.64 → 12.11 (×18.9) | 93.74 % / 6.26 % | −16.81 % | 9.93 → 2.72 (×0.27) | sí | +24 496 / +83.66 bps | 0.975 | −156.55 bps |

- **Avance:** bps entre el primer y el tercer cierre de la terna, en la dirección de la señal. Las
  escalas no son comparables entre contratos: el flujo de la 3.ª ventana va de 1 937 (STRK) a 156 882
  (BLESS 20:06) y la profundidad contraria de 2 595 (ARIA) a 295 795 (STRK). Por eso se normaliza
  contra la historia del propio contrato y no se compara Q entre símbolos.
- **Extensión 3 min:** es una medida nueva de este bloque (la anterior solo usaba ternas). Requiere
  bloques contiguos: BLESS 19:30 solo tiene 1 minuto previo contiguo y ARIA 0, así que quedan
  `UNKNOWN` sin inventar referencia. STRK y BLESS 20:06 sí son evaluables.
- **Aporte importe/profundidad:** porcentaje del crecimiento de `log Q` atribuible a `log|F|` y a
  `log D`. En los cuatro domina el importe. La profundidad media puede caer porque se retiran órdenes,
  porque se ejecutan o porque se repone menos: la captura **no** permite atribuir causa.
- **Últimos 30 s:** cubren `[fin_c − 30 s, fin_c)`, el final de la 3.ª ventana, no el minuto posterior.
  Solo BLESS 20:06 muestra compra neta y precio en contra en ese tramo.
- **Concentración:** un solo bucket de 10 s explica el 63–97 % del flujo neto del minuto en los tres
  casos medibles. Es una propiedad descriptiva de la captura, no una señal: la mediana de las 112
  anclas evaluables es 0.94.

## Extensión previa: la medida que el bot no evalúa

| Caso | Avance | Bloques 3 min | Referencia propia | Extensión | Ternas previas | Extensión por ternas |
|---|---:|---:|---:|---:|---:|---:|
| BLESS 19:30 | 115.75 bps | 0 (1 min contiguo) | — | `UNKNOWN` | 0 | `UNKNOWN` |
| STRK 19:56 | 20.62 bps | 7 | 5.87 bps | **3.51×** | 4 | `UNKNOWN` |
| BLESS 20:06 | 326.24 bps | 12 | 48.49 bps | 6.73× | 6 | 5.35× |
| ARIA 20:15 | 117.03 bps | 0 | — | `UNKNOWN` | 4 | `UNKNOWN` |

En las 143 anclas: 56 evaluables por bloques de 3 min (87 `historia_insuficiente`), mediana 1.68,
rango 0.10–17.72; por ternas, 35 evaluables (108 `historia_insuficiente`), mediana 1.60, rango
0.55–8.60. La medida por ternas reproduce el 5.35× ya publicado para BLESS 20:06.

## Después del aviso: primer cambio sostenido por datos

| Caso | 1.er cambio (bloque, tipos) | Disponible | ¿Antes de la salida original? | Entrada | Continuación | Δ vs original | 1.er giro (bloque, disponible, entrada) | Reversión |
|---|---|---|---|---|---|---|---|---:|
| BLESS 19:30 | `b_0` 19:30, debilitamiento + precio sin avance (flujo +6 298 vs +48 073; Δcierre −36.46) | 19:31:00.252 | **sí** (salida 19:36) | 19:32 | −76.52 bps | **+22.52** | `b_1` 19:31, 19:32:00.156 → 19:33 | +66.09 bps |
| STRK 19:56 | `b_5` 20:01, debilitamiento + profundidad (flujo +1 343 vs +1 937) | 20:02:03.027 | **no** (salida 20:02:00) | 20:03 | +20.52 bps | −23.60 | ninguno | — |
| BLESS 20:06 | `b_0` 20:06, debilitamiento (flujo +11 002 vs +156 882) | 20:07:04.997 | **sí** (salida 20:12) | 20:08 | −152.79 bps | −10.77 | `b_2` 20:08, 20:09:00.451 → 20:10 | +14.67 bps |
| ARIA 20:15 | `b_0` 20:15, giro (flujo −7 788 vs +31 424) | 20:16:00.474 | **sí** (salida 20:21) | 20:17 | −67.32 bps | **+89.24** | `b_0` 20:15, 20:16:00.474 → 20:17 | +67.32 bps |

- **Ningún cambio puede mejorar la entrada original:** se mide sobre el minuto alineado que contiene
  el corte y ese minuto cierra después del corte, así que su disponibilidad es siempre posterior a la
  entrada original (campo `cambio_antes_de_entrada_original = false` en los 4). Solo puede informar
  una salida o reducción, o una entrada deliberadamente más tardía.
- **La profundidad que deja de caer** (media contraria > la de la 3.ª ventana) aparece en STRK `b_5`
  (310 092 > 295 795) y en BLESS 20:06 `b_3`/`b_4` (7 777 y 7 785 > 7 620); en BLESS 19:30 y ARIA
  ningún bloque la supera (máximos 7 666 y 2 494). No distingue: el ganador es uno de los que la
  muestran.
- **Con agregados de 1 minuto no se atribuye a un segundo exacto.** Las marcas de disponibilidad son
  el `as_of_ms` de la fila, no el instante del evento. La caída media de profundidad no demuestra que
  se retiraran o repusieran órdenes individuales.

## Controles: las 143 anclas comunes

**Cobertura por medida del corte.** 143 anclas: 56 evaluables en extensión de 3 min; 35 en extensión
por ternas; 32 en descomposición de Q (111 `UNKNOWN`: 91 con presión o profundidad no positiva y 20
con Q que no crece); 81 en impacto (62 con F2 ≤ 0); 124 en últimos 30 s (19 sin los 3 buckets); 112 en
concentración (31 sin los 6 buckets). No se imputa ninguna.

**Separación por dirección y datos faltantes** (71 LONG / 72 SHORT):

| Medida del corte | LONG: n / mediana | SHORT: n / mediana | Sin dato LONG / SHORT |
|---|---|---|---|
| Extensión 3 min | 29 / 1.99 | 27 / 1.41 | 42 / 45 |
| Extensión por ternas | 14 / 1.79 | 21 / 1.60 | 57 / 51 |
| Aporte del importe a Q | 14 / 100.59 % | 18 / 100.72 % | 57 / 54 |
| Impacto relativo (3/2) | 41 / 0.90 | 40 / 1.23 | 30 / 32 |
| Flujo alineado de 30 s | 62 / +1 238 | 62 / +386 | 9 / 10 |
| Concentración 10 s | 59 / 0.97 | 53 / 0.92 | 12 / 19 |

| Medida | n | Resultado |
|---|---:|---|
| Aporte del importe al crecimiento de Q | 32 | mediana **100.72 %** (rango −0.58 a 265.07); la profundidad cae mediana 0.77 % |
| Impacto relativo (3/2) | 81 | mediana **0.91**; 33 con frenada, 48 sin frenada |
| Flujo alineado de los últimos 30 s | 124 | mediana +1 016; 43 con giro (34.7 %), 15 con presión sin avance (12.1 %) |
| Concentración de 10 s | 112 | mediana **0.94** (rango 0.24–182.16; >1 solo con signos mezclados) |

**Primer cambio posterior.** 131 de 143 con cambio observado (9 `UNKNOWN` por falta de bloques
usables, 3 `sin_cambio`). El primer cambio cae en `b_0` en la mayoría (k mediana 0, media 0.21) y su
disponibilidad llega una mediana de **60 059 ms** después del corte (mínimo 43 759). Tipos: giro 79,
debilitamiento 27, precio sin avance 9, profundidad 16. Primer giro: 123 anclas, disponibilidad mediana
63 644 ms.

| Conjunto | n | Original media / mediana | Continuación media / mediana | Δ media / mediana | Mejoran / empeoran / igual |
|---|---:|---|---|---|---:|
| Primer cambio, todas | 109 | −5.84 / +2.58 bps | +5.42 / +5.31 bps | **+11.27 / +4.42 bps** | 65 / 43 / 1 |
| Primer cambio, LONG | 55 | +12.66 / +9.17 | +20.22 / +11.78 | +7.56 / +4.42 | 32 / 23 / 0 |
| Primer cambio, SHORT | 54 | −24.69 / −1.25 | −9.65 / +5.05 | +15.04 / +4.80 | 33 / 20 / 1 |

De las 143 anclas, 111 tienen resultado de cambio resoluble y 32 no: 12 `sin_cambio_en_horizonte`
(los 9 bloques no usables más 3 sin cambio en el horizonte), 17 `sin_velas_para_simbolo` y 3
`vela_entrada_ausente`. De las 111, 2 no tienen resultado original resoluble (`vela_entrada_ausente`
en una ancla de STRK y otra de ARIA), así que el pareo usa 109. Ninguna entrada de cambio reutiliza
la original (`reutiliza = 0`).

**Giro como señal de reversión (la prueba que importa).** 103 pares con giro resoluble.

| Conjunto | n | Continuación media / mediana | Reversión media / mediana | Reversión positiva |
|---|---:|---|---|---:|
| Todas | 103 | +2.29 / +5.59 bps | **−2.29 / −5.59 bps** | 43 / 103 |
| LONG | 50 | +19.30 / +12.71 | **−19.30 / −12.71** | 19 / 50 |
| SHORT | 53 | −13.76 / +4.95 | +13.76 / −4.95 | 24 / 53 |

La conclusión formal (regla de 30 pares fijada antes) es "el giro **no** muestra reversión en esta
muestra": la media y la mediana de la reversión son negativas. En LONG la reversión es claramente
perdedora; en SHORT la media es positiva pero la mediana negativa, señal de colas y no de ventaja
sostenida. Por tipo de primer cambio: giro (n=67) Δ +12.90 / +7.94; debilitamiento (n=23) +20.36 /
+2.29; precio sin avance (n=6) +10.68 / +6.16; profundidad (n=13) continuación −24.94 / −4.25.

**Diferencia visible en el corte vs explicación posterior.** Para cada factor medible en el corte se
comparó el resultado original (negativo vs positivo):

| Factor visible en el corte | Original negativo | Original positivo |
|---|---|---|
| Giro de 30 s = sí | 18 | 18 |
| Giro de 30 s = no | 35 | 33 |
| Presión sin avance 30 s = sí | 7 | 5 |
| Presión sin avance 30 s = no | 46 | 46 |
| Frenada de impacto = sí | 13 | 9 |
| Frenada de impacto = no | 18 | 22 |
| Extensión 3 min, mediana | 1.85 (n=27) | 1.57 (n=27) |
| Concentración 10 s, mediana | 0.99 (n=50) | 0.90 (n=45) |
| Aporte del importe, mediana | 94.78 (n=11) | 100.15 (n=12) |

Ninguno separa: los recuentos son casi simétricos, la frenada es más frecuente entre las perdedoras
(lo contrario de "frenar es bueno"), y las diferencias de extensión, concentración y aporte son
pequeñas y con rangos solapados. La única dirección consistente con el ganador (menos extensión) es
también la más incompleta: 87 de 143 anclas no tienen historia contigua suficiente.

## Conclusión

**Qué no evaluaba el bot.** El detector solo mira tres ventanas contiguas de 1 minuto: profundidad
contraria del top-20 estrictamente decreciente, `Q` estrictamente creciente y precio avanzando en la
dirección. No evaluaba: (1) el tamaño del avance contra la historia del propio contrato; (2) si `Q`
crecía por importe o por caída de profundidad; (3) el impacto marginal por tramo y su frenada; (4) los
últimos 30 s y la distribución intra-minuto; (5) nada posterior al aviso.

**Si había evidencia observable a tiempo.** En el corte, sí había datos, pero **ningún factor del
corte separa al ganador** con esta muestra: el único alineado (menor extensión normalizada) está
`UNKNOWN` en 2 de 4 casos y en 87 de 143 anclas, y su diferencia en los controles es 1.85 vs 1.57 con
rangos que se solapan. Después del aviso, la evidencia de que "algo cambió" existió y fue conocida a
tiempo en los **tres perdedores** (~60 s tras el aviso, ~5 min antes de la salida de 5 min) y **no**
en el ganador (4 de 6 minutos sin flujo; primer cambio 3 s después de la salida). Es decir: el cambio
posterior sirve para **evitar pérdida**, no para **elegir ganador**.

**Qué hipótesis merece una prueba aparte.** La **extensión normalizada contra la historia propia en
el corte** como posible discriminante de continuación frente a agotamiento, porque es la única medida
pre-entrada, es barata de calcular y apunta en la misma dirección en los cuatro casos y en los
controles. No está probada: falta cobertura (61 % de las anclas sin historia contigua), el contraste
es 1 caso contra 1 entre los cuatro, y las diferencias de control son pequeñas. Probarla exige una
captura con historia previa completa por contrato, umbrales declarados antes de mirar y ≥30 pares por
grupo, midiendo desde un corte posterior a la disponibilidad y sin reutilizar precios de entrada.
Hipótesis secundaria y separada (gestión, no selección): el giro intra-minuto a 10 s como aviso más
temprano de salida (en ARIA habría estado visible ~30 s antes que la fila de 1 minuto; en BLESS 20:06
el detalle de 10 s muestra solo un frenazo de la venta, no un giro).

**Lo que no se autoriza.** Invertir el patrón por el giro posterior: los cuatro casos lo hacen
atractivo, pero las 103 anclas lo rechazan (reversión −2.29 / −5.59 bps; LONG −19.30 / −12.71).
Crear una variante operativa, cambiar umbrales o abrir otra captura tampoco se autoriza con este
diagnóstico.

## Limitaciones

- Captura ya usada en el desarrollo del detector: hallazgo exploratorio, no prueba independiente.
- Los cuatro casos formulan hipótesis; no validan una regla.
- Los agregados de 1 minuto y de 10 s no se atribuyen a un segundo exacto.
- Una caída o subida de la profundidad media no demuestra retirada ni reposición de órdenes.
- Entrada y salida son aperturas de velas: no son fills ni incluyen latencia ni impacto.
- Cobertura de velas limitada a los símbolos consultados durante la captura.
- Flujo intermedio ausente no se rellena ni se atribuye a una causa (STRK 19:57–20:00; ARIA desde
  20:18).
- Funding `UNKNOWN`; 16 bps es solo sensibilidad documentada. Retorno bruto, no P&L.
- La descomposición de Q solo es evaluable con presión alineada positiva en las ventanas 1 y 3; 111
  de 143 anclas quedan fuera. Ese recorte es en sí un dato: el patrón no exige presión positiva, solo
  `|F|` creciente.
- La extensión de 3 min usa cierres de `research_flow_1m`, no velas externas; el histórico previo a la
  captura no existe (`historical_klines` vacía).

## Reproducción

| Evidencia | Contenido |
|---|---|
| `A-comando.txt` | Comando exacto, tres ejecuciones, exit codes, determinismo y SHA-256 de derivados, código y datos. |
| `B-pytest.txt` | 39 pruebas nuevas + 78 de regresión focalizada = 117 passed. Cubren: bloques de 3 min sin solape y sin relleno, referencia cero, descomposición de Q, frenada/aceleración de impacto, últimos 30 s y concentración, `b_0` en el minuto del corte, bloque incompleto saltado con motivo, prioridad giro > debilitamiento > precio sin avance > profundidad, dato tardío que desplaza la entrada, minuto ausente que no se rellena, reversión solo en giro y aborto si se reutiliza la entrada original, y la regla formal de 30 pares. |
| `C-resumen.json` | Resumen compacto: reglas, origen y hashes, universo, los 4 casos, agregados de control, cruce visible vs resultado, conclusiones formales y limitaciones. |
| `D-verificacion.txt` | Verificación independiente (`scripts/verificar_factores_ventana4.py`, no importa el módulo): 737 checks, 0 fallos. Recalcula desde SQL y velas las 4 ternas y las 143 anclas. |

Derivados voluminosos fuera de Git en
`C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-diagnostico-factores-v1`:
`casos_factores.jsonl` (4), `casos_ventanas.jsonl` (12), `casos_bloques.jsonl` (24),
`casos_detalle_10s.jsonl`, `anclas_factores.jsonl` (143), `anclas_cambios.jsonl` (143) y
`anclas_no_resolubles.jsonl`.

```bat
python scripts\diagnostico_factores_ventana4.py ^
  --db "C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a\research.db" ^
  --cobertura "docs\evidence\secuencia-presion-v1-correcciones-20261117\C-cobertura-real.json" ^
  --klines "C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a\consultas_klines.jsonl" ^
  --derivados-anclas "C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-anclas-comunes-v1" ^
  --salida "C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-diagnostico-factores-v1" ^
  --resumen "docs\evidence\diagnostico-factores-ventana4-20261118\C-resumen.json" ^
  --run-id exp-v2-ventana-4-20261116a
```
