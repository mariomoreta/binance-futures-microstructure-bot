# Diagnóstico de los cuatro casos del patrón (ventana 4)

Bloque `diagnostico-cuatro-casos-ventana4-20261118` · rama `research/universe-liquidez-v1` · 2026-11-18
Base publicada: `d6513e28bb499f8e39921df431f80a28d0e36a08`.
Datos: captura `exp-v2-ventana-4-20261116a` y derivados ya publicados, **solo lectura**. Sin Binance,
sin consultas públicas, sin capturas nuevas, sin órdenes, sin cambios de patrón, umbrales, horizonte,
agrupación ni estrategia productiva.

## Pregunta

En los cuatro casos de `SECUENCIA-PRESION-V1` de la ventana 4 —STRKUSDT LONG (ganador, +44.12 bps),
ARIAUSDT LONG (−156.55 bps) y dos BLESSUSDT SHORT (−99.04 y −142.02 bps)—, ¿qué distinguió al ganador,
si lo explica la extensión previa o la pérdida de presión, y qué habría cambiado esperar un minuto
antes de entrar? Se contrasta con las 143 anclas comunes ya publicadas.

## Respuesta corta

1. **Lo único que separa al ganador en la señal es que su terna fue la menos extrema**, no una
   diferencia de presión: 20.62 bps de avance (5.6–15.8× menos que las otras tres) y Q ×4.6
   (4.1–40.7× menos crecimiento), sobre el libro más profundo (295 795 frente a 2 595–7 694 de
   profundidad contraria). Los cuatro cumplieron las condiciones del patrón (Q creciente, profundidad
   contraria decreciente); ninguna de esas condiciones distingue al ganador. La escala entre
   contratos no es comparable.
2. **La extensión previa no es evaluable en 3 de 4 casos.** Con el mínimo fijado de 6 ternas previas
   no solapadas, solo BLESSUSDT 20:06 es contrastable: 5.35× la mediana previa del mismo contrato, y
   perdió 142.02 bps. Es un punto compatible con "extensión grande → agotamiento", sin valor
   probatorio. STRK (el ganador) tiene 4 ternas previas, ARIA 4 y BLESSUSDT 19:30 ninguna: sus
   comparaciones quedan `NO_RESOLUBLE`, sin inventar referencia.
3. **La pérdida de presión no explica la diferencia.** En la señal, el ganador no mostró pérdida de
   presión: fue el que menos creció en Q y el que menos avanzó. En el minuto de espera, los dos
   BLESS **confirmaron** dirección con 86.9 % y 93.0 % menos flujo que su tercera ventana y aun así
   perdieron (−76.52 y −152.79 bps); ARIA cambió de signo y es el único caso donde revertir habría
   cambiado el resultado (−67.32 → +67.32 bps). Con 1 caso de 4, es una pista, no una regla.
4. **Esperar un minuto:** evaluable en 3 de 4 casos. Mejoró BLESSUSDT 19:30 (+22.52 bps) y ARIA
   (+89.24), empeoró BLESSUSDT 20:06 (−10.77) y **no es resoluble en el ganador** (minuto incompleto
   y 4 minutos sin flujo persistido). En las 143 anclas, esperar un minuto en la misma dirección
   mejora 106 pares comparables (+11.54 bps de media, +4.18 de mediana; 62 mejoran, 43 empeoran, 1
   igual). **Pero revertir por flujo contrario no se sostiene**: en los 63 candidatos a reversión, la
   continuación desde el corte tardío rinde +5.16 bps de media (+11.56 de mediana, 39/63 positivos) y
   la reversión −5.16 (−11.56, 23/63).
5. **Consecuencia:** el diagnóstico no autoriza invertir el patrón, crear una variante operativa ni
   abrir otra captura. Deja una hipótesis acotada y dos medidas que faltan (historia previa por
   contrato y flujo completo del minuto de espera).

## Reglas fijadas antes de calcular

| Dimensión | Regla |
|---|---|
| Casos | Las 4 anclas con patrón del universo igualado (501 ternas). Verificadas contra `episodios_patron_originales.jsonl` publicado: 4/4 coinciden en símbolo, dirección, terna, corte, estado y retorno. |
| Espera | Primer minuto exacto posterior a la terna: `[fin_c, fin_c + 60 s)`, con `fin_c` = cierre nominal de la tercera ventana. |
| Corte tardío | `max(corte original, fin_c + 60 s, as_of_ms del flujo de ese minuto)`. |
| Entrada / salida | Apertura del primer minuto **estrictamente posterior** al corte y apertura exactamente 5 minutos después. Sin saltar huecos, sin relleno. |
| Flujo alineado | `s × (compras − ventas)`, `s = +1` LONG, `−1` SHORT. `> 0` → continuación confirmada; `< 0` → candidato experimental a reversión; `0` → sin confirmación. |
| No resoluble | Fila ausente, `data_quality ≠ OK` o `as_of_ms` anterior al cierre del minuto. No se imputa. |
| Reversión | Mismo corte tardío y **mismos precios** que la continuación tardía; nunca reutiliza la entrada original. |
| Extensión previa | Avance alineado entre el primer y el tercer cierre. Referencia = mediana de `|c3/c1 − 1|` de ternas previas **no solapadas** del mismo contrato, estrictamente anteriores al inicio de la terna, empaquetadas desde el final en pasos de 3. Ventana histórica = la propia captura. |
| Mínimos | 6 ternas previas para la extensión; 30 pares resolubles para la conclusión estadística. Fijados antes de mirar resultados. |
| Costes | Retorno bruto. Solo la sensibilidad documentada de 16 bps ida y vuelta, informada aparte. Funding `UNKNOWN`. |

## Los cuatro casos: lo conocido al emitir

| Caso | Dir. | Cierres 1 → 3 | Avance | Q 1 → 3 (×) | Flujo alineado 3ª | Prof. contraria 3ª | Retorno original |
|---|---|---|---:|---|---:|---:|---:|
| BLESSUSDT 19:30:01.355 | SHORT | 0.018315 → 0.018103 | 115.75 bps | 0.26 → 6.25 (×23.7) | +48 073 | 7 694 | −99.04 bps |
| STRKUSDT 19:56:04.530 | LONG | 0.033950 → 0.034020 | 20.62 bps | 0.0014 → 0.0065 (×4.6) | +1 937 | 295 795 | **+44.12 bps** |
| BLESSUSDT 20:06:00.464 | SHORT | 0.018177 → 0.017584 | 326.24 bps | 0.11 → 20.59 (×189.1) | +156 882 | 7 620 | −142.02 bps |
| ARIAUSDT 20:15:00.502 | LONG | 0.208500 → 0.210940 | 117.03 bps | 0.64 → 12.11 (×18.9) | +31 424 | 2 595 | −156.55 bps |

- Las tres ventanas de cada terna son contiguas y sus filas de flujo/libro tienen `data_quality = OK`,
  `degraded = 0`, `depth_gaps = 0`, `crossed = 0` e integridad válida. No hay hueco en la señal.
- ARIA tiene la **ventana acreditada anterior no contigua** (hueco de 6 minutos): su historia previa
  utilizable es menor y su comparación de extensión queda sin resolver.
- Las escalas no son comparables entre contratos: el flujo de la tercera ventana va de 1 937 (STRK) a
  156 882 (BLESSUSDT), la profundidad contraria de 2 595 (ARIA) a 295 795 (STRK) y Q abarca tres
  órdenes de magnitud. Un Q mayor no significa "más presión" en otro contrato.

## Extensión previa (medida normalizable)

| Caso | Avance alineado | Ternas previas no solapadas | Mediana previa | Extensión normalizada | Estado |
|---|---:|---:|---:|---:|---|
| BLESSUSDT 19:30 | 115.75 bps | 0 | — | — | `NO_RESOLUBLE` (`historia_insuficiente`) |
| STRKUSDT 19:56 | 20.62 bps | 4 | 13.20 bps | — | `NO_RESOLUBLE` (4 < 6) |
| BLESSUSDT 20:06 | 326.24 bps | 6 | 61.03 bps | **5.35×** | resoluble |
| ARIAUSDT 20:15 | 117.03 bps | 4 | 166.88 bps | — | `NO_RESOLUBLE` (4 < 6) |

En las 143 anclas, solo **35** alcanzan 6 ternas previas no solapadas; 108 quedan
`historia_insuficiente`. La distribución de la extensión normalizada de esas 35 es mediana 1.60,
mínimo 0.55 y máximo 8.60. No se parte por resultado ni se elige umbral: es una distribución
descriptiva.

## El minuto de espera

| Caso | Minuto | Flujo neto | Alineado | Clasificación | Fuerza vs 3ª | Corte tardío → entrada | Continuación tardía | Δ vs original |
|---|---|---:|---:|---|---:|---|---:|---:|
| BLESSUSDT 19:30 | 19:30–19:31 | −6 298 | +6 298 | continuación confirmada | 0.131 (−86.9 %) | 19:31:00.149 → 19:32 | −76.52 bps | **+22.52** |
| STRKUSDT 19:56 | 19:56–19:57 | — | — | **no resoluble** | — | — | — | — |
| BLESSUSDT 20:06 | 20:06–20:07 | −11 002 | +11 002 | continuación confirmada | 0.070 (−93.0 %) | 20:07:04.997 → 20:08 | −152.79 bps | **−10.77** |
| ARIAUSDT 20:15 | 20:15–20:16 | −7 788 | −7 788 | **candidato a reversión** | −0.248 (−124.8 %) | 20:16:00.272 → 20:17 | −67.32 bps | **+89.24** |

- Los cuatro cortes originales caen dentro del minuto siguiente al cierre nominal, así que el minuto
  de espera coincide con el minuto de entrada original y esperar desplaza la entrada exactamente
  +60 s en los 130 casos usables (no hay ninguno con corte ya posterior).
- **Confirmar no es mantener la fuerza:** los dos BLESS conservaron el signo con 13.1 % y 7.0 % del
  flujo alineado de su tercera ventana. El signo se conservó; la fuerza no.
- **STRK no es resoluble.** El minuto 19:56–19:57 es `PARTIAL_OK` y su `as_of_ms` es 19:56:40.346,
  19.65 s **antes** de que cerrara el minuto; además no hay filas de flujo persistidas entre 19:57 y
  20:00 (4 minutos, incluido el minuto de entrada original). Sus +44.12 bps siguen medidos con velas;
  el tramo ausente queda sin explicar. No se atribuye a liquidaciones ni absorción: no se midieron.

## Lo observado después

| Caso | Original | Continuación tardía | Δ | Reversión tardía | ¿Aplica? |
|---|---:|---:|---:|---:|---|
| BLESSUSDT 19:30 SHORT | −99.04 | −76.52 | +22.52 | +76.52 | no: el flujo confirmó |
| STRKUSDT 19:56 LONG | +44.12 | — | — | — | no resoluble |
| BLESSUSDT 20:06 SHORT | −142.02 | −152.79 | −10.77 | +152.79 | no: el flujo confirmó |
| ARIAUSDT 20:15 LONG | −156.55 | −67.32 | +89.24 | **+67.32** | **sí: el flujo se opuso** |

La reversión tardía se calcula con la misma entrada y la misma salida que la continuación tardía (solo
cambia el signo), así que no reutiliza la entrada original. En los dos casos confirmados el valor de
reversión es aritmético y no se interpreta: no había señal para revertir.

## Controles: las 143 anclas comunes

**Cobertura del minuto de espera.** 143 anclas → 130 con minuto usable; 13 `flujo_espera_incompleto`
(incluido STRK); 0 ausentes, 0 sin disponibilidad, 0 incoherentes. De las 130, 108 tienen resultado
tardío resoluble; 19 quedan `sin_velas_para_simbolo`, 3 `vela_entrada_ausente` y 13 arrastran el
minuto incompleto. Cruce: 106 con original y tardía resolubles, 9 solo original, 2 solo tardía, 26
ninguno.

**Efecto de esperar, misma dirección (106 pares).**

| Conjunto | n | Original media / mediana | Tardía media / mediana | Δ media / mediana | Mejoran / empeoran / igual |
|---|---:|---|---|---|---:|
| Todas | 106 | −6.59 / +1.29 bps | +4.94 / +4.99 bps | **+11.54 / +4.18 bps** | 62 / 43 / 1 |
| LONG | 52 | — | — | +8.29 / +4.52 bps | — |
| SHORT | 54 | — | — | +14.67 / +2.91 bps | — |
| Con patrón | 3 | −132.54 | −98.88 | +33.66 / +22.52 bps | — |
| Sin patrón | 103 | −2.93 | +7.97 | +10.89 / +3.95 bps | — |

- **Pérdidas evitadas:** 37 originales negativas mejoran; 16 de ellas terminan en ≥ 0; mejora media
  +49.67 bps.
- **Oportunidades perdidas:** 29 originales positivas empeoran; empeora media −47.01 bps.
- La conclusión formal (regla de 30 pares fijada antes) es "esperar un minuto muestra mejora media y
  mediana **en esta muestra**". No es una recomendación: es un contrafactual dentro de la captura.
- La media de −6.59 es sobre los 106 pares; sobre los 115 resolubles originales la media es −8.26
  (mediana 0.00), que reproduce lo publicado.

**Candidatos a reversión (63 con resultado tardío).**

| Medida | Continuación desde el corte tardío | Reversión desde el mismo corte |
|---|---:|---:|
| Media | **+5.16 bps** | −5.16 bps |
| Mediana | **+11.56 bps** | −11.56 bps |
| Positivos | 39 / 63 | 23 / 63 |

En el conjunto de control, el flujo contrario del minuto de espera **no** anticipa reversión: la
continuación desde el corte tardío rinde más que la reversión en media y mediana. La clasificación es
descriptiva (72 reversión, 58 continuación, 0 sin confirmación sobre 130); no se usa como filtro.

## Qué explica la diferencia

Ninguna de las dos hipótesis queda sostenida con estas reglas:

- **Extensión previa:** la única medida normalizable no es contrastable en 3 de 4 casos; el único
  contrastable (BLESSUSDT 20:06, 5.35× su mediana previa) perdió 142 bps. El ganador tuvo el avance
  bruto más pequeño, pero su referencia propia no existe con el mínimo fijado.
- **Pérdida de presión:** los cuatro cumplieron las condiciones de presión en la señal. En la espera,
  los dos BLESS confirmaron con 86.9 % y 93.0 % menos flujo y perdieron; ARIA cambió de signo y es el
  único donde revertir habría ganado. No separa al ganador de los perdedores.
- **Esperar:** ayuda en 2 de 3 casos evaluables y en el agregado de 106 pares (+11.54 bps de media),
  pero el ganador no es evaluable y la reversión por flujo contrario no se sostiene en los controles.

Queda como hipótesis acotada: *las ternas menos extremas sobre libros profundos podrían continuar
mejor que las muy extendidas*, y *un cambio de signo del flujo en el minuto siguiente podría marcar
agotamiento*. Ninguna se puede probar con 4 casos ni con 35/143 extensiones resolubles; probarlas
requiere historia previa por contrato y flujo completo del minuto de espera, no otra captura de los
mismos 143 episodios.

## Limitaciones

- Muestra ya usada en el desarrollo del detector y anclas elegidas ex post por la regla de solo
  precio: hallazgo exploratorio, no prueba independiente.
- Contrafactual, no operación: el agregado del minuto solo se conoce al cerrar; la entrada es la
  apertura siguiente; sin fills, latencia ni impacto. Retorno bruto, no P&L.
- Funding `UNKNOWN`; el coste de 16 bps es solo una sensibilidad documentada y se informa aparte.
- 19 anclas sin velas del símbolo y 3 sin la vela exacta de entrada; 13 minutos de espera
  incompletos. No se rellenó ninguno.
- STRK: tramo sin flujo persistido (19:57–20:00) sin explicar; no se atribuye a ninguna causa.
- ARIA: ventana acreditada anterior no contigua (6 min); menos historia previa.
- La reversión tardía es mecánicamente el negativo de la continuación (mismos precios): solo aporta
  información cuando el flujo se opone.
- Q, notional y profundidad no son comparables entre contratos; solo la extensión está normalizada
  por la historia del propio contrato, y en 1 de 4 casos.

## Reproducción

| Evidencia | Contenido |
|---|---|
| `A-comando.txt` | Comando exacto, dos ejecuciones, exit codes, determinismo y SHA-256 de derivados y fuentes. |
| `B-pytest.txt` | 23 pruebas nuevas + 69 de regresión focalizada = 92 passed, exit 0. Cubren: desplazamiento de la entrada por un dato tardío (1 y 2 minutos), minuto ausente/incompleto/sin disponibilidad, clasificación del flujo, reversión sin reutilizar la entrada original, extensión `NO_RESOLUBLE` sin historia o con referencia cero, no solapamiento, denominadores y verificación contra lo publicado. |
| `C-resumen.json` | Resumen compacto: reglas, origen y hashes, universo, los 4 casos completos, agregados de control, conclusión formal y diagnóstico. |
| `D-verificacion.py` / `.txt` | Verificación independiente (no importa el módulo): reproduce agregados y los 4 casos desde velas, comprueba `reversion = −continuacion`, que ninguna entrada tardía reutiliza la original y que las fuentes conservan su SHA-256. 31/31 OK. |

Derivados voluminosos fuera de Git en
`C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-diagnostico-cuatro-casos-v1`:
`casos_detalle.jsonl` (4), `casos_ventanas.jsonl` (12), `casos_trayectorias.jsonl` (24),
`anclas_diagnostico.jsonl` (143) y `anclas_no_resolubles.jsonl`.

```bat
python scripts\diagnostico_cuatro_casos_ventana4.py ^
  --db "C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a\research.db" ^
  --cobertura "docs\evidence\secuencia-presion-v1-correcciones-20261117\C-cobertura-real.json" ^
  --klines "C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a\consultas_klines.jsonl" ^
  --derivados-anclas "C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-anclas-comunes-v1" ^
  --salida "C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-diagnostico-cuatro-casos-v1" ^
  --resumen "docs\evidence\diagnostico-cuatro-casos-ventana4-20261118\C-resumen.json"
```
