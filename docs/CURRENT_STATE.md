# Estado vigente — ventana 4 ejecutada COMPLETA con cierre normal (2026-11-16)

## Bloque 2026-11-19 - coste de ejecucion con capturas existentes (sin mercado)

**Autorizacion humana:** sobre la base publicada
`2be0e1fcc97ff58b1db0b6e59a8684c789debd07`, rama `research/universe-liquidez-v1`,
verificar el coste de ejecucion con las capturas existentes partiendo de los 278
episodios de solo precio publicados. Contrato, direccion, entrada y salida a
cinco minutos quedan congelados. No se reabre el filtro de extension ni se
cambia la estrategia. Solo offline: sin Binance, capturas nuevas, ordenes ni
cambios al bot. `opencode.json` y archivos ajenos intactos.

**Predeclaracion:** `docs/evidence/coste-ejecucion-20261119/PREDECLARACION.md`,
publicada en el commit `d727a6d52059a31c16b8a6c33422ac49aaabf0b1` antes de
comparar retornos. Fija C0 (best bid y best ask explicitos; no valen media de
spread por minuto, mid, OHLC ni fills simulados), C1 (+/-5 s y
`received_ms <= instante`), C2 (no cruzado ni degradado y al menos un nivel por
lado), C3 (ambos extremos) y C4 (minimo 30 pares). Coste: spread una sola vez;
comision, slippage y funding `UNKNOWN`.

**Hecho:** `scripts/coste_ejecucion_inventario.py`, `INVENTARIO.md` y
`C-inventario.json` se publican en el primer commit. `research_book_1m` guarda
agregados por minuto publicados ~60 s despues del instante;
`observaciones.jsonl.libro` guarda mid y spread, no bid/ask. Barrido de 527
archivos de texto: 0 campos de precio de nivel. Buckets entrada/salida/ambos
277/273/272, 0 disponibles al instante; 2 de 278 con mid+spread a +/-5 s en
ambos extremos; 0 con bid/ask; 0 pares C3.

**Resultado:** 0 pares evaluables. Bruto descriptivo de los 278 +5.1286 bps;
maximo coste adicional antes de cero 5.1286 bps. Spread agregado mediano
4.64 bps sobre 550 buckets, solo contexto y no aplicado. Comision, slippage y
funding `UNKNOWN`. No se publica neto ajustado ni se extrapola subconjunto
alguno. Veredicto `DATOS_INSUFICIENTES`.

**Correccion de etiqueta:** -1 506.08 bps es la suma de los retornos
descartados; +1 506.08 bps es el cambio de suma al abstenerse de esas entradas
(de -3 022.24 a -1 516.16). La media retenida empeora de -10.87 a -17.84 bps.
El veredicto anterior `NO APORTA` no cambia. Se corrige la etiqueta en el
informe anterior y en los documentos vigentes; `docs/DECISIONS.md` es
append-only y se corrige con una entrada nueva.

**Pruebas:** 17 nuevas; regresion focalizada 123 passed, exit 0; verificador
independiente 10 086 comprobaciones, 0 fallos. Evidencia en
`docs/evidence/coste-ejecucion-20261119/`; derivados fuera de Git en
`C:\proyectos\binance-futures-data\coste-ejecucion-v1\`.

## Bloque 2026-11-19 — extension previa vs regla de solo precio (sin mercado)

**Autorizacion humana (2026-11-19):** sobre la base publicada
`91e16671ca6492316023f1c9a7ac6c06149333ee`, medir en capturas distintas de la
ventana 4 si medir cuanto se ha extendido el movimiento frente a la historia del
propio contrato permite evitar entradas peores que una regla de solo precio. Solo
lectura de los `research.db` de ventana 1, 2, 3 y pilotos 1105a/1106a; sin
Binance, capturas nuevas, ordenes, GARCH/PCA, cambios en
detector/motor/dashboard ni variante nueva al cierre. `opencode.json` y archivos
ajenos no se tocan.

**WORKFLOW publicado:** la seccion "Diseno y pruebas de investigacion
cuantitativa" llego al remoto durante la sesion (commit `2659b94`, solo
`docs/WORKFLOW.md`). Este bloque la cumple: decision y criterio fijados antes de
mirar retornos, disponibilidad al corte, mismo corte/entrada/horizonte en ambos
grupos, referencia historica sencilla del mismo contrato (sin GARCH ni PCA) y
comparacion previa con la regla de solo precio.

**Hecho:** `scripts/extension_previa_inventario.py` cuenta primero los casos (914
episodios de solo precio, 279 con historia y precios; 17 del patron, 2 completos)
sin calcular retornos. `PREDECLARACION.md` fija por escrito, en el commit
`561d0b953cf665cab83047f90003bc37d1b28a99` y antes de cualquier retorno, la
definicion unica (avance de la senal / mediana de 6 bloques previos de 3 min
contiguos y no solapados, conocidos al corte), los grupos (`EXTENDIDO` si
`> 1.0`), el minimo de 30 por grupo y cinco condiciones de conservacion.
`scripts/extension_previa_v1.py` reutiliza detector, ventanas y agrupacion
publicados sin tocar umbrales.

**Resultado verificable:** 914 episodios -> 278 evaluables (537 sin 18 min
contiguos, 1 con mediana previa nula, 31 sin vela de entrada, 67 sin vela de
salida). `EXTENDIDO` 193, `NORMAL` 85. Neto tras 16 bps: mediana -16.00 vs
-13.47 y media -7.80 vs -17.84. Diferencia NORMAL-EXTENDIDO: mediana +2.53,
media -10.03, IC bootstrap descriptivo [-57.04, +31.77]. El filtro descarta el
69.4 % (193), evita 8 594.42 bps de perdidas y renuncia a 7 088.33 bps de
ganancias: la suma de los retornos descartados es -1 506.08 bps y el cambio de
suma al abstenerse es +1 506.08 bps. Sin filtro: media -10.87, mediana -16.00. LONG
135: EXT -20.02/-10.61 frente a NOR -32.04/-52.44 (la ventaja se invierte);
SHORT 143: EXT -16.00/-5.30 frente a NOR +2.51/+19.30. A favor en 2 de 4
capturas. Terciles sin dosis-respuesta: el mas extendido tiene la mejor media
(-5.52). La mediana aguanta al quitar `JCTUSDT` (18 episodios) y el episodio
extremo (`BTWUSDT` SHORT -893.24 bps), pero la condicion 2 (media) falla.

**Conclusion:** `NO APORTA`. La ventaja de mediana no sobrevive a la media, se
invierte en LONG y aparece en 2 de 4 capturas; ningun grupo es rentable tras
16 bps. No se activa el filtro, no se cambia el bot y no se declara edge. La
familia del patron queda `DATOS INSUFICIENTES` (2 evaluables de 17). Ventana 1
aporta 0 casos porque `research_flow_1m` esta vacia; se reporta, no se omite.

**Pruebas:** `tests/test_extension_previa_v1.py` 20 passed; regresion focalizada
140 passed, exit 0. Verificador independiente: 3 687 comprobaciones, 0 fallos.
Determinismo: dos corridas con el mismo sha256 `2ddfec41...c3f2472`.

**Evidencias:** `docs/evidence/extension-previa-20261119/` (README, INVENTARIO,
PREDECLARACION, A comando/exit 0, B pytest, C resumen JSON, D verificacion);
derivados fuera de Git en
`C:\proyectos\binance-futures-data\extension-previa-v1\` y
`...-inventario\`. Fuentes intactas: hashes identicos antes y despues.

## Bloque 2026-11-18 — salida temprana al primer cambio observable (sin mercado)

**Autorizacion humana (2026-11-18, continuacion):** sobre la base publicada
`eac06450f0020a12fc09e51ce02e4424fae0fb9d`, medir si cerrar en el primer cambio
observable, manteniendo la entrada original de las 143 anclas congeladas, recorta
mas perdidas de las ganancias que sacrifica. Solo lectura de
`exp-v2-ventana-4-20261116a` y de los derivados publicados; sin Binance,
consultas publicas, capturas nuevas, ordenes, cambios de
patron/umbral/horizonte/entrada/direccion/agrupacion, sin variante nueva y sin
inversion del patron. `opencode.json` y archivos ajenos no se tocan.

**Hecho:** `scripts/salida_temprana_ventana4.py` (version `salida-temprana-v1`)
reutiliza `replay_patron_ventana4`, `comparar_anclas_ventana4`,
`diagnostico_cuatro_casos_ventana4` y `diagnostico_factores_ventana4` sin tocar
umbrales, y verifica 143/143 anclas y 858/858 bloques contra lo publicado. Reglas
fijadas antes de calcular: contrato, direccion y entrada congelados; salida
original a 5 min; primer cambio por la prioridad publicada; disponibilidad =
maximo de los datos que acreditan el cambio (el cierre del bloque no basta);
salida alternativa = apertura exacta del primer minuto estrictamente posterior,
solo si es estrictamente anterior a la salida original; sin saltar velas; hueco
antes del primer cambio = no evaluable, nunca "sin cambio"; 16 bps iguales en
ambos lados; funding `UNKNOWN`; menos de 30 pares adelantados = `INSUFICIENTE`.

**Resultado verificable:** 143 = 28 no evaluables por resultado original no
resoluble (23 sin velas del simbolo, 5 sin vela de entrada) + 9 no evaluables por
hueco en `b_0` (`flujo_incompleto`) + 106 adelantadas; 0 conservadas. Todo ancla
con resultado original resoluble y `b_0` utilizable cumple la regla publicada, y
en 99 de 106 el cambio aparece en `b_0` (93.4 %): la regla publicada no discrimina
y la alternativa equivale a "salir un minuto despues de entrar". Disponibilidad
mediana entrada+710 ms (min 149 ms, max 121 918 ms; 7 casos >= 60 s); 0 cambios
disponibles antes de la entrada. Sobre los 106 pares: delta medio +4.68 bps,
mediana -2.87, suma +495.62, 48/55/3, rango -278.73/+452.22. Perdidas recortadas
41 (+3 441.98 bps) frente a ganancias sacrificadas 44 (-2 860.28), mas 10
perdidas empeoradas (-209.42), 6 ganancias extra (+119.32) y 2 neutros (+4.01).
LONG 52: -3.14/-4.36; SHORT 54: +12.20/-1.42 -> ninguna direccion consistente.
Por tipo: giro 65 (+3.56/-4.94), debilitamiento 22 (-7.33/-14.39), precio sin
avance 6 (+13.54/+7.73), profundidad 13 (+26.50/+9.99). Con 16 bps: neto medio
original -22.59 y alternativo -17.92 (delta invariante); pares con neto > 0: 41
frente a 25. Las 4 anclas del patron: BLESS 19:30 +104.54, BLESS 20:06 +175.10,
ARIA +123.25 y STRK no evaluable (`flujo_incompleto` en `b_0`).

**Conclusion:** `SIN_DIRECCION_CLARA`. Recorta perdidas pero sacrifica una
cantidad comparable de ganancias; la media positiva depende de la cola derecha y
la mediana es negativa. No se declara mejora, edge ni rentabilidad y no se
autoriza promover la regla: esta ventana no valida la salida temprana.

**Pruebas:** `tests/test_salida_temprana_ventana4.py` 26 passed; regresion
focalizada 143 passed, exit 0. La suite completa conserva los fallos
preexistentes en modulos ajenos ya documentados.

**Evidencias:** `docs/evidence/salida-temprana-ventana4-20261118/` (README, A
comando/exit 0/determinismo/hashes, B 143 passed, C resumen JSON, D verificacion
independiente 2 801/2 801); derivados fuera de Git en
`C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-salida-temprana-v1\`.
Fuentes intactas: `research.db` `6ad6f716...a7f1`, `consultas_klines.jsonl`
`4ee61463...a61874`, `C-cobertura-real.json` `39652bf0...f4bd`,
`anclas_cambios.jsonl` `6ca94a94...db3ea`.

**Siguiente:** ninguna prueba automatica. Cualquier uso de la salida temprana como
regla exige autorizacion humana explicita, selectividad predeclarada y `run_id`
nuevo con >= 30 pares por grupo.

## Bloque 2026-11-18 — diagnostico de factores de los cuatro casos (sin mercado)

**Autorizacion humana (2026-11-18, continuacion):** sobre la base publicada
`d71543c1589d1a6d67154544976e5a1fde05ea50`, medir en los cuatro casos del
patron de la ventana 4 y en las 143 anclas comunes: (1) en el corte, cuanto
habia avanzado el precio frente a la conducta reciente del mismo contrato, si la
presion neta crecio en importe o el ratio subio porque cayo la profundidad
opuesta, y si cada tramo seguia desplazando el precio; (2) tras el aviso, el
primer cambio sostenido por datos (giro, debilitamiento, precio sin avance o
profundidad que deja de caer), cuando ocurrio y cuando estuvo disponible; (3)
las mismas medidas en las 143 anclas, separando LONG y SHORT y mostrando datos
faltantes. Solo lectura de `exp-v2-ventana-4-20261116a` y de los derivados
publicados; sin Binance, consultas publicas, capturas nuevas, ordenes, cambios
de patron/umbral/horizonte/agrupacion, variante operativa ni inversion del
patron. `opencode.json` y archivos ajenos no se tocan.

**Hecho:** `scripts/diagnostico_factores_ventana4.py` (version
`diagnostico-factores-v1`) reutiliza los helpers publicados
(`replay_patron_ventana4`, `comparar_anclas_ventana4`,
`diagnostico_cuatro_casos_ventana4`, `secuencia_presion_v1`) y verifica los 4
casos y las 143 anclas contra lo publicado (4/4 y 143/143). Reglas fijadas antes
de calcular: bloques posteriores de 1 minuto alineados al reloj
(`b_k = floor(corte/60 s)·60 s + k·60 s`, `k=0..5`, `b_0` contiene el corte);
bloque usable solo con `run_id` esperado, `data_quality = OK`, `as_of ≥
bucket_end` y limites coherentes; cambio = `giro` (flujo alineado ≤ 0) >
`debilitamiento` (0 < flujo < flujo de la 3.a ventana) > `precio_sin_avance`
(flujo > 0 y Δcierre ≤ 0) > `profundidad_deja_de_caer` (profundidad media
contraria > la de la 3.a ventana); Δcierre solo contra el bloque inmediatamente
anterior (`b_0` contra el cierre de la 3.a) y `UNKNOWN` tras un hueco; corte del
cambio = `max(bucket_end, as_of flujo, as_of libro usable)` y entrada en la
apertura del primer minuto estrictamente posterior; reversion solo si el cambio
es giro; extension de 3 min con bloques contiguos sin solape y minimo 6;
descomposicion `Δlog Q = Δlog|F| − Δlog D`; impacto marginal por tramo;
ultimos 30 s con 3 buckets de 10 s y concentracion `max|delta|/|suma|`.

**Resultado verificable:** 4/4 casos y 143/143 anclas. En el corte, los cuatro
comparten la firma: el ratio Q sube sobre todo por importe agresor (93.7-99.3 %
del crecimiento logaritmico) y la profundidad contraria cae solo 0.99-16.81 %;
el ganador (STRK, 20.62 bps) es el de menor caida de profundidad y mayor peso
del importe, y frena su impacto (8.64 -> 7.60 bps/1 000), igual que BLESS 19:30
y ARIA; solo BLESS 20:06 acelera (0.39 -> 2.05) y pierde. Ultimos 30 s: solo
BLESS 20:06 muestra compra neta y precio en contra; STRK cierra con +1 390 de
flujo a favor. Extension normalizada: STRK 3.51x (7 bloques, referencia 5.87
bps), BLESS 20:06 6.73x (12 bloques) y 5.35x sus ternas; BLESS 19:30 y ARIA
`UNKNOWN` (0 bloques). Primer cambio posterior: 131/143 con cambio observado (9
bloques no usables, 3 sin cambio); mediana de disponibilidad 60 059 ms; tipos
giro 79, debilitamiento 27, precio sin avance 9, profundidad 16. En los tres
perdedores el cambio se conoce ~1 minuto tras el aviso y antes de la salida de 5
minutos; en STRK los minutos 19:57-20:00 no tienen flujo y el primer cambio
llega 3 s despues de la salida. Giro como reversion (103 pares): media -2.29 bps
y mediana -5.59 (43/103 positivas); LONG -19.30/-12.71 (n=50), SHORT +13.76/-4.95
(n=53): **no muestra reversion**. Primer cambio: +11.27/+4.42 bps (n=109), pero
su entrada coincide exactamente con la entrada tardia ya publicada (-76.5208,
-152.7897, -67.3192) y reproduce el efecto de espera, no una senal nueva.

**Conclusion:** el factor que el bot no evaluaba y que apunta en la direccion
del ganador es la extension normalizada contra la historia propia en el corte,
pero es una hipotesis: 2 de 4 casos y 87 de 143 anclas quedan sin historia
contigua y la diferencia en los controles es 1.85 vs 1.57 con rangos solapados.
La evidencia posterior existio a tiempo en los tres perdedores y no en el
ganador: sirve para evitar perdida, no para elegir ganador. No se invierte el
patron, no se crea variante operativa ni se abre otra captura.

**Pruebas:** `tests/test_diagnostico_factores_ventana4.py` 39 passed; regresion
focalizada 78 passed; conjunto 117 passed, exit 0. La suite completa conserva 11
fallos preexistentes en modulos ajenos (`test_engineering_live_window_local`,
`test_market_stream_window`, `test_session_new_public_market`) y 1 error de
coleccion en `tests/test_engineering_clock_budget.py`, archivo modificado
localmente por el usuario y no por este bloque.

**Evidencias:** `docs/evidence/diagnostico-factores-ventana4-20261118/` (README,
A comando/exit 0/determinismo/hashes, B pytest, C resumen JSON, D verificacion
independiente 737/737); derivados fuera de Git en
`C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-diagnostico-factores-v1\`.
Fuentes intactas: `research.db` `6ad6f716...a7f1`, `consultas_klines.jsonl`
`4ee61463...a61874`, `C-cobertura-real.json` `39652bf0...f4bd`.

**Siguiente:** ninguna prueba automatica. La hipotesis de extension normalizada
exige autorizacion humana explicita con `run_id` nuevo, historia previa completa
por contrato y criterio de potencia fijado antes de mirar resultados.

## Bloque 2026-11-18 — diagnostico de los cuatro casos del patron (sin mercado)

**Autorizacion humana (2026-11-18, continuacion):** sobre la base publicada
`d6513e28bb499f8e39921df431f80a28d0e36a08`, diagnosticar los cuatro casos del
patron de la ventana 4 (STRKUSDT LONG +44.12 bps; ARIAUSDT LONG -156.55;
BLESSUSDT SHORT -99.04 y -142.02) y contrastarlos con las 143 anclas comunes ya
publicadas. Solo lectura de la captura y de sus derivados; sin Binance, sin
capturas nuevas, sin ordenes, sin cambios de patron/umbral/horizonte/agrupacion
ni reapertura de la auditoria de cobertura. `opencode.json` y archivos ajenos no
se tocan.

**Hecho:** `scripts/diagnostico_cuatro_casos_ventana4.py` (version
`diagnostico-cuatro-casos-v1`) reconstruye las 501 ternas, las 211 alertas de
solo precio y las 143 anclas desde la db y la cobertura (no lee los JSONL), y
verifica las 4 anclas con patron y las 143 anclas contra los derivados
publicados (4/4 y 143/143 identicos; 501/501 cortes). Reglas fijadas antes de
calcular: espera = primer minuto exacto posterior a la terna; corte tardio =
`max(corte, fin_c + 60 s, as_of del flujo)`; entrada = apertura del primer
minuto estrictamente posterior; salida = apertura a 5 minutos exactos; flujo
alineado por direccion; minuto ausente/incompleto/sin disponibilidad = no
resoluble; reversion medida desde el mismo corte tardio y los mismos precios;
extension previa normalizada por la mediana de ternas previas no solapadas del
mismo contrato, con minimo de 6 fijado antes de calcular.

**Resultado verificable:** 130/143 anclas con minuto de espera usable (13
`flujo_espera_incompleto`, incluido STRK; 0 ausentes) y 108 con resultado tardio
resoluble. Los cuatro cortes caen dentro del minuto siguiente al cierre
nominal, asi que esperar desplaza la entrada exactamente +60 s en los 130 casos
usables. Clasificacion del flujo (130): 58 continuacion, 72 reversion, 0 sin
confirmacion. Pares original+tardia (106): original -6.59 bps de media (+1.29
mediana), tardia +4.94 (+4.99), delta +11.54 (+4.18); 62 mejoran, 43 empeoran, 1
igual; LONG 52 -> +8.29/+4.52; SHORT 54 -> +14.67/+2.91. Perdidas evitadas: 37
negativas mejoran (16 terminan >= 0; +49.67 bps de mejora media); oportunidades
perdidas: 29 positivas empeoran (-47.01 bps). Candidatos a reversion (63):
continuacion +5.16 de media (+11.56 mediana, 39/63 positivos) y reversion -5.16
(-11.56, 23/63). Extension previa: 35/143 evaluables (mediana normalizada 1.60,
rango 0.55-8.60); 108 `historia_insuficiente`.

**Los cuatro casos:** STRKUSDT (ganador) no es resoluble en la espera
(`PARTIAL_OK`, `as_of` 19.65 s antes del cierre del minuto y sin filas de flujo
19:57-20:00); BLESSUSDT 19:30 confirma con 13.1 % del flujo de su tercera
ventana y pierde 76.52 bps (mejora +22.52); BLESSUSDT 20:06 confirma con 7.0 %
y pierde 152.79 (empeora -10.77); ARIAUSDT cambia de signo (-24.8 %) y es el
unico caso donde revertir habria ganado (+67.32 frente a -67.32). Extension
previa: solo BLESSUSDT 20:06 es contrastable (5.35x su mediana previa, perdio
142.02); los otros tres quedan `NO_RESOLUBLE` (0, 4 y 4 ternas previas).

**Conclusion:** ninguna de las dos hipotesis queda sostenida. El ganador fue la
terna menos extrema (20.62 bps, Q x4.6) sobre el libro mas profundo, sin
diferencia de presion en la senal; la perdida de presion no separa (los dos
confirmados perdieron con 87-93 % menos flujo) y la extension previa no es
evaluable en 3 de 4. Esperar un minuto mejora la media y la mediana en esta
muestra (regla de 30 pares), pero revertir por flujo contrario no se sostiene en
los controles. Hipotesis acotada, no regla; sin autorizacion para invertir el
patron, crear variante operativa ni abrir otra captura.

**Pruebas:** `tests/test_diagnostico_cuatro_casos_ventana4.py` 23 passed
(desplazamiento de entrada por dato tardio a 1 y 2 minutos, minuto
ausente/incompleto/sin disponibilidad, clasificacion del flujo, reversion sin
reutilizar la entrada original, extension `NO_RESOLUBLE` sin historia o con
referencia cero, no solapamiento, denominadores de control y verificacion
contra lo publicado). Regresiones focalizadas: `test_comparar_anclas_ventana4.py`
9, `test_replay_patron_ventana4.py` 6, `test_secuencia_presion_v1.py` 24,
`test_extraer_cobertura_research_db.py` 7,
`test_analisis_contrafactual_ventana4.py` 16,
`test_operativo_replay_offline.py` 7; conjunto 92 passed, exit 0.

**Evidencias:** `docs/evidence/diagnostico-cuatro-casos-ventana4-20261118/`
(README, A comando/exit 0/determinismo/hashes, B pytest, C resumen JSON, D
verificacion independiente 31/31); derivados fuera de Git en
`C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-diagnostico-cuatro-casos-v1\`.
Fuentes intactas: `research.db` `6ad6f716...a7f1`, `consultas_klines.jsonl`
`4ee61463...a61874`, `C-cobertura-real.json` `39652bf0...f4bd`.

**Publicado:** commit selectivo 549440e4ddba51045cab0bae28e5c138b0565de (script, pruebas y evidencia) y documentacion 422b1566787036aaa5e81961b2997eb372a0785c; push normal a origin/research/universe-liquidez-v1 con SHA remoto verificado.

**Siguiente:** no se ejecuta ni se propone otra captura, variante del patron ni
inversion automatica. Cualquier prueba nueva exige autorizacion humana
explicita con `run_id` nuevo y criterio de potencia fijado antes de mirar
resultados.

## Bloque 2026-11-18 — comparacion en condiciones iguales: filtro vs solo precio (sin mercado)

**Autorizacion humana (2026-11-18, continuacion del bloque anterior):** sobre la
base publicada `c83a1943830d9ad205be41bb1766407e7225cba8`, comparar
`SECUENCIA-PRESION-V1` con la regla de solo precio sobre las **mismas 501 ternas
acreditadas**, con el **mismo corte causal** (incluida la disponibilidad del
libro) y la **misma medicion**. Solo lectura de
`exp-v2-ventana-4-20261116a`; sin Binance, consultas publicas, capturas nuevas,
ordenes, cableado productivo, cambios del patron/umbral/horizonte/agrupacion ni
reapertura de la auditoria de cobertura. Dataset intacto (`research.db` SHA256
`6ad6f716...a7f1`; `consultas_klines.jsonl` `4ee61463...a61874`;
`C-cobertura-real.json` `39652bf0...f4bd`), verificado antes y despues.

**Hecho:** `scripts/comparar_anclas_ventana4.py` reutiliza
`scripts/replay_patron_ventana4.py` y se restringe al universo acreditado: itera
las 501 filas del detector, recalcula el corte
`max(cierre nominal, disponibilidad de las tres ventanas)` y aborta si no
coincide (501/501 verificados). La referencia de solo precio exige unicamente
tres cierres estrictamente monotonos, con el mismo corte, sin evaluar antes ni
incorporar ternas ajenas. Episodios con la agrupacion publicada de 5 minutos;
el ancla es la primera alerta y su clasificacion se congela; una alerta del
patron posterior se registra aparte, con su propio corte, sin reclasificar el
ancla ni heredar su retorno. Medicion identica en ambos metodos (entrada =
apertura del primer minuto estrictamente posterior al corte; salida = apertura
a 5 minutos exactos; vela exacta obligatoria; faltante o contradiccion =
no resoluble con motivo; retorno bruto, no P&L).

**Resultado verificable:** `501 ternas -> 211 alertas de solo precio (104 LONG,
107 SHORT) -> 143 episodios (71/72) -> 4 anclas con patron / 139 sin patron ->
4 / 111 resolubles`. No resolubles: 28 (23 `sin_velas_para_simbolo`, 5
`vela_entrada_ausente`), todos sin patron. Con patron: 1/3/0, media -88.37 bps,
mediana -120.53, IC95 [-149.29, -2.42], adverso medio -186.05; BLESSUSDT 2/4
(50 %). Sin patron: 56/52/3, media -5.37 bps, mediana +2.58, IC95 [-25.71,
+13.62]. Referencia completa: 57/55/3, media -8.26 bps, mediana 0.00, IC95
[-29.35, +10.83]. El filtro retiene 4/143 = 2.80 % de los episodios (4/501 =
0.80 % de las ternas) y descarta 139. Los 4 episodios del patron coinciden con
un ancla comun (0 absorbidas, 0 tardias): al restringir el universo desaparece
el ancla previa que en la evaluacion de 1107 ternas absorbia a STRKUSDT LONG.
Ese resultado de 1107 ternas se conserva como contexto secundario sin
sobrescribirlo (473 alertas, 237 episodios, 189 resolubles, media -4.85 bps).
Neto con 16 bps documentados: con patron -104.37 / -136.53; sin patron -21.37 /
-13.42; funding UNKNOWN.

**Conclusion formal (regla predeclarada, minimo 30 episodios resolubles por
grupo): datos insuficientes.** El filtro no "selecciona mejor" en el punto
observado (4 retenidos rinden peor), pero con 4 < 30 no se puede afirmar
deterioro ni mejora; la mitad de los casos depende de BLESSUSDT. No se aflojo
el patron ni se cambio el horizonte, la agrupacion o el universo.

**Pruebas:** `tests/test_comparar_anclas_ventana4.py` 9 passed (mismas ternas y
cortes en ambos metodos, fuente tardia que retrasa el corte, no incorpora
ternas ajenas, corte distinto aborta, clasificacion del patron coherente,
alerta tardia que no cambia el ancla, vela faltante no resoluble, minimo de 30
y reduccion de oportunidades). Regresiones: `test_replay_patron_ventana4.py` 6,
`test_secuencia_presion_v1.py` 24, `test_extraer_cobertura_research_db.py` 7,
`test_analisis_contrafactual_ventana4.py` 16,
`test_operativo_replay_offline.py` 7; conjunto focalizado 69 passed, exit 0.

**Evidencias:** `docs/evidence/anclas-comunes-ventana4-20261118/` (README; A
comando con exit 0, hashes antes/despues, reproducibilidad y hashes de
derivados; B pytest; C resumen JSON `67c77c72...3853`; D verificacion
independiente que recalcula 211 -> 143 -> 4/139, las anclas comunes y los 4
retornos desde el JSONL original). Derivados voluminosos fuera de Git en
`C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-anclas-comunes-v1\`.

**Publicado:** commit selectivo
`191e37db891348256f882edae768fe387be9eb53` (script, pruebas y evidencia) y
commit de documentacion posterior; push normal a
`origin/research/universe-liquidez-v1`, con SHA remoto verificado.

| | |
|---|---|
| SHA base | `c83a1943830d9ad205be41bb1766407e7225cba8` (local == remoto) |
| Dataset original | intacto, solo lectura, hash verificado antes y despues |
| Lo que NO acredita | que el filtro mejore la seleccion, edge, rentabilidad ni generalizacion (un `run_id`, una hora, 4 episodios, 50 % BLESSUSDT) |

## Bloque 2026-11-18 — evaluacion exploratoria del patron sobre las 501 ternas (sin mercado)

**Autorizacion humana (continuacion del bloque 2026-11-17, ejecutada el
2026-11-18):** replay offline de `SECUENCIA-PRESION-V1` sobre las 501 ternas
acreditadas de `exp-v2-ventana-4-20261116a` y publicacion de una evaluacion
causal exploratoria. Solo lectura de la captura; sin Binance, consultas
publicas, capturas nuevas, ordenes, cableado productivo, cambios de
patron/umbral ni reapertura de la auditoria de cobertura. Dataset intacto
(`research.db` SHA256 `6ad6f716...a7f1` antes y despues, WAL vacio;
`consultas_klines.jsonl` `4ee61463...a61874`).

**Hecho:** `scripts/replay_patron_ventana4.py` construye la entrada del detector
como `VentanaPresion` desde la cobertura publicada y las filas verificadas de
`research.db`; aborta ante cualquier discrepancia y no fabrica filas piloto ni
reconstruye intervalos desde `decision_ms`. Corte causal =
max(cierre nominal, disponibilidad de flujo, disponibilidad de libro); entrada =
apertura del primer minuto estrictamente posterior; salida = apertura a 5
minutos exactos, sin saltar huecos; el cierre de `aggTrade` nunca se usa como
precio ejecutable. Alertas brutas y episodios se cuentan por separado;
episodio = primera alerta por contrato+dir, agrupando repeticiones de la misma
direccion dentro de los 5 minutos siguientes en orden de disponibilidad.

**Resultado verificable:** universo conservado hasta el detector 1005 ventanas /
501 ternas / 43 simbolos, 0 discrepancias, 0 ternas con `as_of` anterior al
cierre. Cadena del patron: **501 -> 4 alertas (2 LONG, 2 SHORT) -> 4 episodios
-> 4 resolubles**. Referencia de solo precio (misma secuencia de tres cierres,
sin flujo ni profundidad): **1107 ternas contiguas -> 473 alertas -> 237
episodios -> 189 resolubles** (48 no resolubles: 34 por 18 simbolos sin velas,
14 por vela de entrada ausente). Patron: 1 acierto / 3 fallos, media -88.37 bps,
mediana -120.53 bps, IC95 [-149.29, -2.42], adverso medio -186.05; BLESSUSDT
aporta 2/4. Referencia: 92/94/3, media -4.85 bps, mediana -0.00, IC95 [-20.40,
+8.91]; subconjunto de referencia sin patron: 186 resolubles, media -2.79 bps.
Neto con 16 bps de coste documentado: patron -104.37 medio / -136.53 mediano;
funding UNKNOWN.

**Conclusion formal (regla predeclarada, minimo 30 episodios resolubles):
datos insuficientes.** Con 4 episodios no se puede afirmar mejora ni ausencia
de mejora; el estimador puntual observado es peor que la referencia, pero la
muestra no tiene potencia y depende de un solo simbolo. No se declara
rentabilidad: el resultado primario es retorno bruto de referencia.

**Pruebas:** `tests/test_replay_patron_ventana4.py` 6 passed (entrada real
extractor->detector, fuente tardia que retrasa el corte, agrupacion sin
duplicar episodios, precio posterior ausente no resoluble, universo no forzado,
fidelidad de la conversion). Regresiones: `test_secuencia_presion_v1.py` 24,
`test_extraer_cobertura_research_db.py` 7,
`test_analisis_contrafactual_ventana4.py` 16,
`test_operativo_replay_offline.py` 7; conjunto focalizado 60 passed, exit 0.

**Evidencias:** `docs/evidence/patron-ventana4-evaluacion-20261118/` (README con
tablas y conclusion; A comando con exit 0 y hashes antes/despues; B pytest;
C resumen JSON; D verificacion independiente que recalcula las 4 ternas y sus 8
velas sin importar el modulo). Derivados voluminosos fuera de Git en
`C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-patron-v1\`
(5 JSONL, hashes en C). Reproducibilidad: segunda corrida con resumen
byte-identico (`098a61ff...0a6c14`).

**Publicado:** commit selectivo `4e68909d0f5d8510a793d79b458bafcc6f980b33`
("Evalua el patron sobre las 501 ternas de la ventana 4 (offline)"), seguido de
un commit de documentacion con este SHA; push normal a
`origin/research/universe-liquidez-v1`.

| | |
|---|---|
| SHA base | `87d83dcff64a884c569bb5cc6348d81d2db07d36` (local == remoto) |
| Dataset original | intacto, solo lectura, hash verificado antes y despues |
| Lo que NO acredita | que el patron mejore la seleccion, edge, rentabilidad ni generalizacion (una hora, un `run_id`, dependencia de BLESSUSDT) |

## Bloque 2026-11-16 (madrugada) — contraste flujo/profundidad vs continuacion/reversion (sin mercado)

**Autorizacion humana del 2026-11-16 (madrugada):** «INVESTIGACION OFFLINE DE LA
SENAL, SIN MERCADO» y «CIERRE OFFLINE DEL CONTRASTE Y DISEÑO DE LA SIGUIENTE
PRUEBA». Contrastes exploratorios sobre datos existentes; sin Binance,
consultas publicas, capturas, ordenes, relanzamientos, ventanas nuevas ni
cambios en la estrategia productiva. Dataset fuente verificado contra
manifiesto (10/10) antes y despues; no modificado.

**Rectificacion del alcance (vigente):** el contraste prueba la **alineacion
del flujo neto con el movimiento previo** (ratio_alienado =
signo(move_24h_pct) x (buy_notional - sell_notional) /
(bid_notional_top20 + ask_notional_top20), denominador > 0). No prueba si una
profundidad pequena frente a un flujo grande anticipa movimientos mayores
(intensidad); esa es una pregunta futura distinta (hipótesis A, no ejecutada).
Con mismo flujo y movimiento, variar la profundidad cambia el valor absoluto
del ratio pero no su signo, por tanto no cambia de grupo.

**Correccion del horizonte de precios:** cada observacion conserva
decision_ms, objetivo T + 60 min, open/close de ambas velas, precios inicial
y final, desfase de cada cierre y horizonte efectivo. Seleccion: ultima vela
1m plenamente cerrada en/antes de cada objetivo; desfase no negativo y < 60
000 ms; grid del minuto; no se usan cierres futuros ni velas antiguas como
sustituto silencioso. Resultado en las 161 aptas: desfases inicial y final
21 801-27 191 ms (todos < 60 000 ms); horizonte efectivo 3 600 000 ms (exacto)
en todas, 0 discrepantes; grid verificado. Todas las 161 siguen validas;
ninguna se convierte en cero ni se elimina del denominador.

**Resultado del contraste (161 escenarios, capacidad 1 aislada):**
- Regla sencilla (signo 24h): 65.8% de continuacion (106/161).
- Flujo a favor del movimiento previo: 61.6% de continuacion (45/73).
- Flujo contrario: 69.3% de continuacion (61/88).
El flujo a favor NO distingue mejor continuacion que la regla sencilla; el
flujo contrario muestra ligeramente mas continuacion. Resultado debil,
contradictorio o concentrado. No se incorpora el ratio a la estrategia
productiva.

**Evidencia:** `docs/evidence/exp-v2-ventana-4-20261116a-analisis-contrafactual/CONTRASTE-FLUJO-PROFUNDIDAD.md`;
derivados fuera de Git en
`C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-contraste-flujo-profundidad-20261116-v3\`
(regenerados desde fuentes verificadas, resultados anteriores NO reutilizados);
`tests/test_contraste_flujo_profundidad.py` 13 passed; regresiones
`test_analisis_contrafactual_ventana4.py` 16 passed,
`test_operativo_replay_offline.py` 7 passed.

| | |
|---|---|
| SHA base | `7b658e6b466a0ce24d018488d118dc33d08697f8` (local == remoto) |
| SHA de ejecucion del analisis | commit `6a1e268` (correccion del contraste flujo/profundidad) |
| Evidencia contraste | `docs/evidence/exp-v2-ventana-4-20261116a-analisis-contrafactual/CONTRASTE-FLUJO-PROFUNDIDAD.md` |
| Dataset original | intacto, solo lectura, 10/10 ficheros verificados contra manifiesto antes y despues |
| Lo que NO acredita | rentabilidad, edge, mejora predictiva del ratio flujo/profundidad, ventaja candidato/comparador (una sola hora, dependencia temporal) |

## Bloque 2026-11-16 (tarde) — ventana `exp-v2-ventana-4-20261116a` ejecutada, cerrada NORMAL, replay DIFERENCIAS

**Autorizacion humana del 2026-11-16 (tarde):** «UNA VENTANA PUBLICA CON
OPERACIONES SIMULADAS». Una sola corrida del protocolo V2 con independencia del
anfitrion acreditada antes de abrir mercado; sin ordenes reales, cuentas,
claves, capital, otras ventanas ni relanzamientos.

**Resultado:** cierre **NORMAL completo** — el primero del protocolo V2. Hijo
19:26:18.038Z → 21:36:21.292Z (7805,2 s): captura 3600 s (12/12 ciclos), settle
4200 s, espera contable cerrada `trabajo_resuelto` (~3 s, 0 pendientes, 2
consultas). `exit_code.txt` = 0; veredicto del lanzador por separado:
`terminacion_natural`, `cumplimiento_normal: true`. Manifiesto verificado
(10/10 ficheros). Consumos dentro de todos los techos (WS 979.570 mensajes, 1
reconexion, 0 errores; HTTP 671/2000; almacenamiento 7,1 MB/134 MB).

**Operativa:** 196 observaciones / 161 aptas / 35 descartadas (42 etiquetas,
7 solapadas, 0 sin motivo) / 44 seleccionadas sin observacion (10 warmup +
34 rotacion). 161 senales con direccion, 0 abstenciones, 159 rechazos por
capacidad, **2 entradas simuladas** (ambas comparadoras): AAVEUSDT SHORT stop
(neto CONDICIONADO −6,604) y 4USDT LONG horizonte (neto CONDICIONADO −0,3194);
suma CONDICIONADO −6,9234 **con funding UNKNOWN (cadencia_ambigua, no es cero
acreditado; no es P&L)**. 0 posiciones abiertas.

**Replay offline:** DIFERENCIAS — 161 comparadas, 159 coincidentes, 2
diferentes, 0 limitaciones; las 2 diferencias son **solo de etiqueta**
(`neto_motivo` ejecucion `cadencia_ambigua` vs replay `trabajo_resuelto`),
sin diferencias numericas. Veredicto conservado sin ajustes. Comparacion por
rol: **INSUFICIENTE** (0 operaciones COMPLETO en ambos roles). Una sola
ventana no acredita rentabilidad.

**Independencia del anfitrion:** acreditada antes de abrir mercado con un
proceso inocuo bajo el lanzador real lanzado por WMI (padre `WmiPrvSE`, fuera
del arbol del agente): muerte abrupta del anfitrion -> el hijo sobrevive y
termina limpio por mecanismo propio. La corrida real se lanzo por el mismo
mecanismo y no hubo incidente.

| | |
|---|---|
| SHA base | `ce2af020c666956ba35a1e1d41d0007c85d581a7` (local == remoto al iniciar) |
| Evidencia lanzamiento | `docs/evidence/exp-v2-ventana-4-20261116a-lanzamiento/` (LANZAMIENTO.md, presupuesto gate 13/13, prueba de independencia, hashes de scripts) |
| Evidencia cierre | `docs/evidence/exp-v2-ventana-4-20261116a-cierre/` (CIERRE.md tres capas, cierre_datos.json, hashes_cierre.json) |
| Dataset original | `C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a` (manifiesto verificado, solo lectura) |
| Derivados | `C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-replay-20261116\` (replay_operativo.json) |
| Lo que NO acredita | rentabilidad, edge, comparacion por rol (INSUFICIENTE), funding completo, calidad del selector; los umbrales siguen siendo hipotesis |



## Bloque 2026-11-16 (madrugada/tarde) — detector experimental SECUENCIA-PRESION-V1 (sin mercado)

**Autorizacion humana del 2026-11-16:** «PRIMER DETECTOR EXPERIMENTAL DE SECUENCIAS,
LOCAL Y SIN MERCADO». Contrastes exploratorios sobre datos existentes; sin Binance,
consultas publicas, capturas, ordenes, relanzamientos, cambios en la estrategia
productiva, dashboard, servicios, supervisores ni dependencias nuevas. Dataset
fuente verificado contra manifiesto (10/10) antes y despues; no modificado.

**Detector implementado:** `scripts/secuencia_presion_v1.py` (SECUENCIA-PRESION-V1,
EXPERIMENTAL, sin validacion economica). Reconoce una secuencia temporal de
presion agresora creciente, reduccion de liquidez contraria y avance del precio
sobre tres ventanas consecutivas y completas de un minuto. CLI con `--fuente` y
`--salida`, trabaja sin red, no crea motor de trading ni servicio.

**Resultado del detector sobre la ventana 4:** Ningun simbolo tiene 3 ventanas
validas consecutivas en `exp-v2-ventana-4-20261116a` (de 196 observaciones aptas,
solo 20 cumplen todos los campos requeridos; 163 fallan por
`huecos_detectados_en_feed` / `libro_huecos` en la integridad, 13 por
`flujo_ventana_completa` != true). Por lo tanto, el detector no puede ejecutarse
sobre esta captura: 0 simbolos con >=3 ventanas validas, 0 secuencias
evaluables. Los datos de la ventana 4 no tienen cobertura suficiente para este
detector. Esto es una limitacion de cobertura, no un error del detector.

**Configuracion congelada:** version `SECUENCIA-PRESION-V1`, ventana 60s, 3
ventanas, profundidad top-20, lado contrario, requiere ventana completa,
requiere integridad valida, condiciones: Q positivo creciente, profundidad
contraria decreciente, precio avanza en direccion. SHA-256 de la configuracion
registrado en el modulo.

**Pruebas de aceptacion:** 	ests/test_secuencia_presion_v1.py — 18 passed:
secuencia LONG valida, secuencia SHORT valida, presion creciente sin
profundidad decreciente -> SIN_PATRON, profundidad decreciente sin
presion alineada -> SIN_PATRON, precio sin confirmacion -> SIN_PATRON, ventana
incompleta -> DATOS_INSUFICIENTES, dato invalido (profundidad no positiva) ->
DATOS_INSUFICIENTES, ultima fuente despues del corte -> no deteccion
anticipada, aniadir datos futuros no cambia decision, simbolos distintos no
comparten historia, repetir mismo corte no duplica, disponibilidad tardia de
ventana anterior, precio no disponible -> DATOS_INSUFICIENTES, conflicto de
identidad explicita, CLI real con JSONL sintetico (LONG y
DATOS_INSUFICIENTES).
SIN_PATRON, precio sin confirmacion -> SIN_PATRON, ventana incompleta ->
DATOS_INSUFICIENTES, dato invalido (profundidad no positiva) ->
DATOS_INSUFICIENTES, ultima fuente despues del corte -> no deteccion anticipada,
aniadir datos futuros no cambia decision, simbolos distintos no comparten
historia, repetir mismo corte no duplica, CLI real con JSONL sintetico.

**Cobertura real (ventana 4, solo lectura):**
- Observaciones aptas: 196; simbolos unicos: 34
- Simbolos con >=3 ventanas validas: 0; con exactamente 3: 0
- Secuencias de 3 consecutivas posibles: 0
- Simbolos con 1-2 validas: 20; con 0 validas: 14
- Campos que faltan: flujo_ventana_completa (13), integridad del feed/libro
  (163 por huecos_detectados_en_feed y libro_huecos)

**Listado minimo para futura adquisicion:** por simbolo y ventana de 1 min:
buy_notional, sell_notional (flujo aggTrade), bid_notional_top20,
ask_notional_top20 (libro depth20@100ms), precio_base (libro_mid),
ventana_completa, integridad (sin huecos/invalidos/cruce),
disponibilidad.max_ms, decision_ms, symbol, observation_id. Historia previa:
>=3 ventanas consecutivas por simbolo, cada una completa y sin huecos. No
reconstruir ventanas de 30s desde agregados de 1 min.

**Hipotesis futura (no ejecutada):** pregunta A (intensidad): si un |ratio|
mayor se asocia con un |retorno posterior| mayor en 60 min. Variable en T:
|ratio|; resultado posterior: |retorno| en 60 min; horizonte 60 min con la
misma acreditacion de precios; referencia: regresion de |retorno| sobre |ratio|;
controles de dependencia por simbolo y ciclo; datos independientes necesarios
(captura nueva con autorizacion propia).

**Evidencia:**
`docs/evidence/exp-v2-ventana-4-20261116a-secuencia-presion-v1/SECUENCIA-PRESION-V1.md`;
derivados fuera de Git en
`C:\proyectosinance-futures-data\exp-v2-ventana-4-20261116a-secuencia-presion-v1\`;
SHA base: `4a7df47e89dbd1015ad89a6f1889ebf48d156c59`;
script `scripts/secuencia_presion_v1.py`;
pruebas `tests/test_secuencia_presion_v1.py` (13 passed);
regresiones `test_analisis_contrafactual_ventana4.py` (16 passed),
`test_operativo_replay_offline.py` (7 passed).

**Lo que NO acredita:** rentabilidad, edge, mejora predictiva del ratio
flujo/profundidad, ventaja candidato/comparador, utilidad operativa (una hora de
captura, dependencia temporal, simbolos repetidos). El detector no se conecta
al camino productivo.

| | |
|---|---|
| SHA base | `4a7df47e89dbd1015ad89a6f1889ebf48d156c59` (local == remoto) |
| SHA de ejecucion del analisis | commit `4a7df47` (detector SECUENCIA-PRESION-V1) |
| Evidencia detector | `docs/evidence/exp-v2-ventana-4-20261116a-secuencia-presion-v1/SECUENCIA-PRESION-V1.md` |
| Dataset original | intacto, solo lectura, 10/10 ficheros verificados contra manifiesto antes y despues |
| Lo que NO acredita | rentabilidad, edge, mejora predictiva del detector, utilidad operativa (una hora de captura, dependencia temporal, simbolos repetidos) |


## Bloque 2026-11-16 (madrugada/tarde) — detector experimental SECUENCIA-PRESION-V1: persistencia y cobertura (sin mercado)

**Autorizacion humana del 2026-11-16:** «PRIMER DETECTOR EXPERIMENTAL DE SECUENCIAS, LOCAL Y SIN MERCADO» y «CIERRE OFFLINE DEL CONTRASTE Y DISEÑO DE LA SIGUIENTE PRUEBA». Contrastes exploratorios sobre datos existentes; sin Binance, consultas publicas, capturas, ordenes, relanzamientos, ventanas nuevas ni cambios en la estrategia productiva. Dataset fuente verificado contra manifiesto (10/10) antes y despues; no modificado.

**Detector implementado:** `scripts/secuencia_presion_v1.py` (SECUENCIA-PRESION-V1, EXPERIMENTAL, sin validacion economica). Reconoce una secuencia temporal de presion agresora creciente, reduccion de liquidez contraria y avance del precio sobre tres ventanas consecutivas y completas de un minuto **realmente contiguas**. CLI con `--fuente` y `--salida`, trabaja sin red, no crea motor de trading ni servicio.

**Persistencia y idempotencia del CLI:**
- El lanzador lee el archivo de salida existente si existe y no duplica decisiones ya persistidas (misma observation_id).
- Si una observacion_id ya tiene una decision registrada con la misma configuracion (config_hash) y mismas ventanas, no se duplica.
- Si una observacion_id existente tiene datos contradictorios (misma observation_id pero ventanas o decision diferente), el CLI termina con codigo 3 y mensaje de conflicto, sin modificar el registro previo.
- Ejecutar el CLI dos veces sobre el mismo archivo de salida produce el mismo conjunto de decisiones (idempotencia).

**Resultado del detector sobre la ventana 4:** Ningun simbolo tiene 3 ventanas validas consecutivas en `exp-v2-ventana-4-20261116a` (de 196 observaciones aptas, solo 20 cumplen todos los campos requeridos; 163 fallan por `huecos_detectados_en_feed` / `libro_huecos` en la integridad, 13 por `flujo_ventana_completa` != true). Por lo tanto, el detector no puede ejecutarse sobre esta captura: 0 simbolos con >=3 ventanas validas, 0 secuencias evaluables. Los datos de la ventana 4 no tienen cobertura suficiente para este detector. Esto es una limitacion de cobertura, no un error del detector.

**Configuracion congelada:** version `SECUENCIA-PRESION-V1`, ventana 60s, 3 ventanas, profundidad top-20, lado contrario, requiere ventana completa, requiere integridad valida, requiere ventanas contiguas, condiciones: Q positivo creciente, profundidad contraria decreciente, precio avanza en direccion. SHA-256 de la configuracion registrado en el modulo.

**Pruebas de aceptacion:** `tests/test_secuencia_presion_v1.py` — 21 passed: secuencia LONG valida, secuencia SHORT valida, presion creciente sin profundidad decreciente -> SIN_PATRON, profundidad decreciente sin presion alineada -> SIN_PATRON, precio sin confirmacion -> SIN_PATRON, ventana incompleta -> DATOS_INSUFICIENTES, dato invalido (profundidad no positiva) -> DATOS_INSUFICIENTES, ultima fuente despues del corte -> no deteccion anticipada, aniadir datos futuros no cambia decision, simbolos distintos no comparten historia, repetir mismo corte no duplica, disponibilidad tardia de ventana anterior, precio no disponible -> DATOS_INSUFICIENTES, conflicto de identidad explicita, CLI real con JSONL sintetico (LONG y DATOS_INSUFICIENTES), CLI ejecucion dos veces no duplica, conflicto de identidad por CLI, dos simbolos no mezclan historias, CLI ternas sucesivas detectan posterior.

**Cobertura real (ventana 4, solo lectura):**
- Observaciones aptas totales (observaciones.jsonl): 196
- Observaciones aptas (apto_para_evaluacion=True): 161
- Símbolos unicos en observaciones aptas: 34
- research_flow_1m: 1265 filas; research_book_1m: 1197 filas; research_flow_10s: 6633 filas
- Intervalos (symbol, bucket_start) en flujo: 1265; en libro: 1197; emparejados: 1190
- Simbolos con ventanas validas (flujo+libro+precio+integridad OK): 0
- Ventanas validas totales: 0
- Simbolos con >=3 ventanas validas: 0; Ternas contiguas de 3 ventanas validas: 0
- Campos que faltan: flujo_ventana_completa (13 observaciones), integridad del feed/libro (163 observaciones)

**Listado minimo para futura adquisicion:** por simbolo y ventana de 1 min: buy_notional, sell_notional (flujo aggTrade), bid_notional_top20, ask_notional_top20 (libro depth20@100ms), precio_base (libro_mid), ventana_completa, integridad (sin huecos/invalidos/cruce), disponibilidad.max_ms, decision_ms, symbol, observation_id. Historia previa: >=3 ventanas consecutivas por simbolo, cada una completa y sin huecos. No reconstruir ventanas de 30s desde agregados de 1 min.

**Hipotesis futura (no ejecutada):** pregunta A (intensidad): si un |ratio| mayor se asocia con un |retorno posterior| mayor en 60 min. Variable en T: |ratio|; resultado posterior: |retorno| en 60 min; horizonte 60 min con la misma acreditacion de precios; referencia: regresion de |retorno| sobre |ratio|; controles de dependencia por simbolo y ciclo; datos independientes necesarios (captura nueva con autorizacion propia).

**Evidencia:**
`docs/evidence/exp-v2-ventana-4-20261116a-secuencia-presion-v1/SECUENCIA-PRESION-V1.md`;
derivados fuera de Git en
`C:\proyectosinance-futures-data\exp-v2-ventana-4-20261116a-secuencia-presion-v1\`;
SHA base: `4a7df47e89dbd1015ad89a6f1889ebf48d156c59`;
script `scripts/secuencia_presion_v1.py`;
pruebas `tests/test_secuencia_presion_v1.py` (21 passed);
regresiones `test_analisis_contrafactual_ventana4.py` (16 passed),
`test_operativo_replay_offline.py` (7 passed).

**Lo que NO acredita:** rentabilidad, edge, mejora predictiva del ratio flujo/profundidad, ventaja candidato/comparador, utilidad operativa (una hora de captura, dependencia temporal, simbolos repetidos). El detector no se conecta al camino productivo.

| | |
|---|---|
| SHA base | `4a7df47e89dbd1015ad89a6f1889ebf48d156c59` (local == remoto) |
| SHA de ejecucion del analisis | commit `b7a1e08` (detector SECUENCIA-PRESION-V1) |
| SHA de cierre de persistencia y cobertura | SHA de este bloque (commit selectivo pendiente) |
| Evidencia detector | `docs/evidence/exp-v2-ventana-4-20261116a-secuencia-presion-v1/SECUENCIA-PRESION-V1.md` |
| Dataset original | intacto, solo lectura, 10/10 ficheros verificados contra manifiesto antes y despues |
| Lo que NO acredita | rentabilidad, edge, mejora predictiva del detector, utilidad operativa (una hora de captura, dependencia temporal, simbolos repetidos) |

## Blque 2026-11-16 (cierre de persistencia y cobertura SECUENCIA-PRESION-V1)

> **RECTIFICADO el 2026-11-17** (ver bloque final de este documento). El cierre
> de esta seccion declaraba "0 ternas evaluables" y "precio_close como
> precio_base"; la regeneracion con el extractor corregido devuelve 501 ternas
> acreditadas y distingue `price_close` (cierre del agregado aggTrade) de
> `libro_mid`. Se conserva el texto original como antecedente.

**Autorizacion:** completar el cierre del detector SECUENCIA-PRESION-V1 (persistencia, extractor real de research.db, tabla de cobertura con etapas separadas). Autorizado exclusivamente: completar los puntos pendientes y sus pruebas locales. NO autorizado: Binance, consultas publicas, capturas, ordenes, relanzamientos, cambios del patron, estrategia productiva, infraestructura ni otra auditoria general.

**Extractor real de research.db:** `scripts/extraer_cobertura_research_db.py` (CLI --db/--salida, SQLite modo=ro, cero red, cero modificacion a la base). Publica consultas exactas y mapeo de columnas (buy_notional/sell_notional en flujo; bid20_mean/ask20_mean en libro como profundidad contraria; price_close como precio_base). Aceptacion: ejecutado sobre SQLite temporal representativo (3 intervalos contiguos, 1 sin contraparte, 1 hueco, 1 ventana parcial, disponibilidad desconocida, precio ausente) y sobre research.db en modo solo lectura; hashes de originales verificados antes y despues (no modificados). Si el resultado final es cero ternas evaluables, es valido cuando la cadena de exclusiones lo demuestra.

**Tabla de cobertura con etapas separadas:**
Poblacion A (observaciones del piloto): totales=196, aptas=161, descartadas=35, simbolos=43.
Poblacion B (agregados temporales): flujo=1265 filas, libro=1197 filas, flujo_10s=6633 filas; claves unicas flujo=1265, libro=1197; parejas libro/flujo=1190; ventanas temporalmente completas: flujo=1265, libro=1197; disponibilidad acreditada=flujo 1265/libro 1197, desconocida=0; integridad acreditada: flujo data_quality OK=1188 (77 no-OK), libro degraded=0/crossed=0 (1014 OK, 183 no-OK); cobertura de precio: disponible=1265, ausente=0. Ternas contiguas: 1107 (todas ventanas flujo) → 1032 (solo parejas) → 501 (con integridad OK) → 501 (con precio). Resultado final: 0 ternas evaluables cuando la cadena de exclusiones lo demuestra (exclusiones trazables por requisito con campos y ejemplos verificables).

**Pruebas de aceptacion:** `tests/test_secuencia_presion_v1.py` — 18 passed (incluye DATOS_INSUFICIENTES persistido para salida vacia sin terna contigua, SIN_PATRON vs DATOS_INSUFICIENTEN distinguidos, CLI real, idempotencia, conflictos de identidad, dos simbolos no mezclan historias, ternas sucesivas).

| | |
|---|---|
| SHA de cierre | Pendiente (commit selectivo + push normal + verifica SHA remoto) |
| Evidencia extractor | scripts/extraer_cobertura_research_db.py + tests/test_secuencia_presion_v1.py |
| Tabla de cobertura | scripts/extraer_cobertura_research_db.py + consulta directa a research.db (modo ro) |
| opencode.json | Conservado, no tocado, no commitado |

## Bloque 2026-11-17 — correcciones SECUENCIA-PRESION-V1 y extractor de cobertura (sin mercado)

**Autorizacion:** completar las correcciones locales de `SECUENCIA-PRESION-V1` y
del extractor existente, sobre la base publicada
`619d357443ace0aa7c0b939f07b6a1457265adfd`, rama
`research/universe-liquidez-v1`. Sin acceso a Binance, capturas nuevas, ordenes,
cambios de estrategia, dashboard ni infraestructura. Dataset de la ventana 4
leido en modo solo lectura; hashes de `research.db`, `research.db-shm` y
`research.db-wal` identicos antes y despues.

**Defecto corregido en el detector:** el CLI dejaba el archivo de salida vacio
cuando el corte tenia tres ventanas individualmente validas del mismo simbolo
separadas por huecos (`test_ventanas_no_contiguas_no_se_evaluan` exigia
`r is None`). Ahora persiste **una** fila `DATOS_INSUFICIENTES` con `symbol`,
`corte_ms`, `ventanas` examinadas (con `ventana_valida` y `motivos_exclusion`),
`ventanas_examinadas`, `motivo`, `motivo_codigo` y `diagnostico` de huecos y
solapamientos. Identidad de la fila: `<symbol>|corte:<corte_ms>`, distinta de la
identidad de una terna. Repetir el mismo corte no añade fila ni altera las
anteriores. `SIN_PATRON` queda reservado a una terna contigua valida que no
cumple el patron. Deteccion deslizante, rechazo de conflictos (codigo 3) y
condiciones del patron sin cambios.

**Defecto corregido en el extractor:** calculaba motivos de exclusion que luego
se perdian, tomaba prestado `as_of_ms` de la otra fuente cuando faltaba uno,
contaba simbolos con ventanas como `simbolos_con_ternas` y no distinguia la
procedencia del precio. Ahora empareja por contrato e intervalo, valida ambos
limites, procedencia (`aggTrade`/`depth20`), `run_id` y claves duplicadas (la
clave duplicada se excluye y se cuenta, sin sustitucion silenciosa); exige
`as_of_ms` valido en **cada** fuente (si falta uno, disponibilidad conjunta
`UNKNOWN`; si ambos estan, maximo) y aplica por separado completitud, integridad
por intervalo, valores validos, precio y disponibilidad, devolviendo motivos
solapables con ejemplos (contrato e intervalo) y exclusiones unicas. Un cero
registrado (`buy_notional = 0`) es admisible; `NULL` no es cero.
`price_close` se identifica como cierre del agregado `aggTrade`, no como
`libro_mid` ni precio ejecutable.

**Cobertura regenerada (poblacion B, agregados de un minuto):** 1190 parejas
iniciales → 1107 ternas sobre flujo (referencia sin contraparte) → 1032 sobre
parejas → **501 tras integridad** → 501 tras precio → 501 tras disponibilidad.
Ventanas acreditadas: 1005. Simbolos con al menos una terna: 43. Requisito que
limita al resto: **integridad por intervalo** (185 ventanas excluidas: 183 con
`libro_degradado` y `libro_huecos_profundidad`, 2 con
`flujo_data_quality_no_ok`/`PARTIAL_OK`). Completitud, valores, precio y
disponibilidad excluyen 0 ventanas en esta captura. Sin contraparte: 75 claves
de flujo y 7 de libro. Los 29 intervalos con un lado en cero registrado son
admisibles.

**Poblacion A (observaciones del piloto, acreditada por separado):** 196
totales, 161 aptas, 35 descartadas, 34 simbolos (motivos de descarte
solapables: `dato_obsoleto_flujo` 28, `flujo_ventana_incompleta` 13,
`dato_obsoleto_libro` 1). No se suma con la poblacion B.

**Evidencias:** (A) `A-cli-caso-sin-terna.txt`: base `619d357` exit 0 con 0
bytes y 0 lineas; CLI corregido exit 0 con 1 fila `DATOS_INSUFICIENTES`
(`sin_terna_contigua`, 2 huecos); repeticion exit 0 con `nuevas=0`,
`duplicadas_omitidas=1` y SHA256 identico. (B) `B-pytest-extractor.txt`:
`pytest tests/test_extraer_cobertura_research_db.py -v` exit 0, 7 passed, con
expectativas independientes y deteccion de timestamp prestado y de simbolo sin
terna. (C) `C-cobertura-real.json` + `C-comando-y-hashes.txt`: CLI real sobre
`research.db` en modo `ro`, exit 0, hashes intactos, JSON SHA256
`39652bf00d594245943ec7114c0e6933fce2e49a8caf2812915cc478f9eaf4bd`. Todo en
`docs/evidence/secuencia-presion-v1-correcciones-20261117/`.

**Pruebas:** `tests/test_secuencia_presion_v1.py` 24 passed;
`tests/test_extraer_cobertura_research_db.py` 7 passed; regresiones
`test_analisis_contrafactual_ventana4.py` (16) y
`test_operativo_replay_offline.py` (7) exit 0.

**Horizonte:** la evaluacion futura del detector se propone a **5 minutos**; la
hipotesis de magnitud a **60 minutos** queda diferida a un bloque con
autorizacion propia. No se ejecuto ni se propone otra captura en este bloque.

**Que NO acredita:** que el patron se detecte sobre las 501 ternas, rentabilidad,
mejora predictiva, ni cobertura para futuros con vencimiento (el selector y
estas tablas siguen siendo PERPETUAL/TRADING/USDT). Cobertura acreditada no
equivale a patron detectado ni a rentabilidad.

