# Salida temprana al primer cambio observable (ventana 4)

Bloque `salida-temprana-ventana4-20261118` · rama `research/universe-liquidez-v1` · 2026-11-18
Base publicada: `eac06450f0020a12fc09e51ce02e4424fae0fb9d`.
Datos: captura `exp-v2-ventana-4-20261116a` y derivados ya publicados, **solo lectura**. Sin Binance,
sin consultas públicas, sin capturas nuevas, sin órdenes, sin cambios de patrón, umbrales, horizonte,
dirección, entrada ni estrategia productiva. No se abre ninguna variante de salida: se evalúa **una
sola** alternativa.

## Pregunta

Manteniendo la entrada original de las 143 anclas congeladas, ¿cerrar en el primer cambio observable
recorta más pérdidas de las ganancias que sacrifica? Para cada ancla: qué cambio se detectó, cuándo
podía saberlo el bot, a qué precio simulado habría salido y cuánto ganó o perdió frente a conservar la
salida original a 5 minutos.

## Respuesta corta

1. **El cambio se detectó en 106 de las 143 anclas, y en 99 de ellas en el primer minuto posterior a la
   ventana de señal (`b_0`).** La regla publicada no discrimina: se cumple en el 93,4 % de los pares
   evaluables. La salida alternativa es, por tanto, la apertura de `entrada + 1 min` en 99 de 106 casos.
2. **Cuándo lo sabía el bot:** justo después de la entrada, no antes. La disponibilidad mediana del
   cambio es `entrada + 710 ms` (mínimo 149 ms, máximo 121,9 s); en 0 casos el cambio estaba disponible
   antes de la entrada. El cierre del bloque por sí solo no basta: en 7 casos la disponibilidad cae en
   un minuto posterior y retrasa la salida.
3. **A qué precio habría salido:** a la apertura exacta del primer minuto estrictamente posterior a esa
   disponibilidad, solo si es anterior a la salida original. Los precios se verificaron uno a uno contra
   `consultas_klines.jsonl` (2 801 comprobaciones independientes, 0 fallos).
4. **Cuánto ganó o perdió:** sobre los 106 pares evaluables, delta medio **+4,68 bps**, mediana
   **−2,87 bps**, suma **+495,62 bps**; 48 mejoran, 55 empeoran, 3 igualan. Recorta pérdidas por
   **+3 441,98 bps** (41 pares) pero sacrifica ganancias por **−2 860,28 bps** (44 pares), además de
   empeorar 10 pérdidas (−209,42) y añadir 6 ganancias extra (+119,32) y 2 pares neutros (+4,01).
5. **Veredicto:** `SIN_DIRECCION_CLARA`. No es `INSUFICIENTE` por conteo (106 ≥ 30), pero la media
   positiva depende de la cola derecha (máximo +452,22 bps) y la mediana es negativa. **No valida la
   regla**: describe esta ventana y nada más.

## Reglas congeladas

| Elemento | Decisión aplicada |
|---|---|
| Universo | 143 anclas publicadas; las 4 del patrón dentro de ellas, contadas una sola vez |
| Contrato, dirección, entrada | Congelados: `entrada_ms = primer minuto tras el corte`, apertura exacta |
| Salida original | `entrada_ms + 5 min`, apertura exacta |
| Cambio | Primer bloque `b_0..b_5` que cumpla la regla publicada, con la prioridad publicada `giro > debilitamiento > precio_sin_avance > profundidad_deja_de_caer`; umbrales sin ajustar |
| Disponibilidad | Máximo de los tiempos de los datos que **acreditan** el cambio; el cierre del bloque no basta |
| Salida alternativa | Apertura exacta del primer minuto **estrictamente posterior** a la disponibilidad, solo si es **estrictamente anterior** a la salida original |
| Sin salto de vela | Si la vela exacta falta o es contradictoria, `no_evaluable`; nunca se salta a una posterior |
| Hueco | Primer bloque relevante no utilizable antes de cualquier cambio ⇒ `no_evaluable`; nunca se convierte en «sin cambio» |
| Coste | 16 bps de ida y vuelta simulados, iguales en ambos lados; funding `UNKNOWN` |
| Umbral | Menos de 30 pares resolubles con salida efectivamente adelantada ⇒ `INSUFICIENTE` |

Bloques relevantes: solo `b_0..b_3`. La entrada es el final de `b_0`, de modo que `b_4` y `b_5` cierran
después de la salida original y no pueden adelantarla; se verifican igualmente para no alterar el
diagnóstico publicado.

**Elegibilidad de `b_0` (decisión explícita).** `b_0` cubre el primer minuto posterior a la ventana de
señal —se comprobó que su inicio coincide con el cierre nominal de la tercera ventana en las 143 anclas—
y su flujo solo está disponible después de la entrada. Por eso cuenta como cambio posterior a la
entrada. Se verifica que **ningún** cambio resulte disponible antes de la entrada
(`cambios_disponibles_antes_de_la_entrada = 0`), que es la condición que descartaría mirar el futuro.

## 1. Embudo de las 143

| Estado | n | Motivo |
|---|---:|---|
| Anclas publicadas | 143 | 4 con `ancla_patron` |
| Resultado original no resoluble | 28 | 23 `sin_velas_para_simbolo`, 5 `vela_entrada_ausente` |
| Resultado original resoluble | 115 | |
| → no evaluable | 9 | `hueco_antes_del_primer_cambio` (`flujo_incompleto` en `b_0`) |
| → salida original conservada | 0 | — |
| → salida adelantada resoluble | 106 | |
| Pares evaluables | 106 | adelantadas + conservadas |
| Cambios identificados | 106 | 99 en `b_0`, 5 en `b_1`, 2 en `b_2` |
| Cambios disponibles antes de la entrada | 0 | guarda de look-ahead |

Los 9 huecos, todos con `b_0` no utilizable por `flujo_incompleto`: ARIAUSDT LONG `|1794858600000`,
XLMUSDT LONG `|1794858900000`, **STRKUSDT LONG `|1794858900000` (ancla del patrón)**, BANKUSDT LONG
`|1794858900000`, ARIAUSDT SHORT `|1794860160000`, BMTUSDT SHORT `|1794860460000`, AIOTUSDT LONG
`|1794860700000`, SPACEUSDT SHORT `|1794860700000`, AGTUSDT LONG `|1794860700000`.

**No hay ninguna salida conservada.** No es un error del embudo: todo ancla con resultado original
resoluble y `b_0` utilizable cumple la regla publicada en `b_0..b_3`. La consecuencia es que «todos los
pares evaluables» y «solo los que adelantaron» coinciden (106). Se publican ambas secciones iguales para
dejar constancia y no ocultar la degeneración de la regla.

Los 3 casos que el diagnóstico publicado clasificó como `sin_cambio_en_horizonte` están dentro de las 28
anclas con resultado original no resoluble; no aportan pares evaluables.

## 2. Resultado sobre los 106 pares evaluables (= solo adelantadas)

| Métrica | Valor |
|---|---:|
| Pares | 106 |
| Delta medio | **+4,6756 bps** |
| Delta mediano | **−2,8746 bps** |
| Delta suma | **+495,6167 bps** |
| Mínimo / máximo | −278,73 / +452,2167 bps |
| Mejoran / empeoran / igualan | 48 / 55 / 3 |
| Original con retorno < 0 / > 0 / = 0 | 51 / 53 / 2 |

Retraso de disponibilidad respecto a la entrada: mediana 710 ms, mínimo 149 ms, máximo 121 918 ms; 7
casos ≥ 60 s y 2 ≥ 120 s. Los 3 «iguales» adelantaron el minuto de salida pero el precio de apertura
coincidió (BMTUSDT SHORT, STOUSDT SHORT, STRKUSDT LONG `|1794858900000`).

Delta por bloque del primer cambio (descriptivo):

| Bloque | n | Media | Mediana | Suma |
|---|---:|---:|---:|---:|
| `b_0` | 99 | +7,96 | −0,36 | +788,05 |
| `b_1` | 5 | −51,66 | −25,32 | −258,28 |
| `b_2` | 2 | −17,08 | −17,08 | −34,16 |

## 3. Pérdidas recortadas frente a ganancias sacrificadas

| Cubo | n | Media | Mediana | Suma |
|---|---:|---:|---:|---:|
| Pérdidas recortadas (original < 0, delta > 0) | 41 | +83,95 | +57,10 | **+3 441,98** |
| Ganancias sacrificadas (original > 0, delta < 0) | 44 | −65,01 | −41,16 | **−2 860,28** |
| Pérdidas empeoradas (original < 0, delta < 0) | 10 | −20,94 | −17,64 | −209,42 |
| Ganancias extra (original > 0, delta > 0) | 6 | +19,89 | +18,39 | +119,32 |
| Original neutro (original = 0, delta ≠ 0) | 2 | +2,01 | +2,01 | +4,01 |
| Iguales (delta = 0) | 3 | 0,00 | 0,00 | 0,00 |

La descomposición es exhaustiva: los cinco cubos más los iguales suman los 106 pares, y las sumas suman
exactamente +495,6167 bps. **Recorta pérdidas, pero sacrifica una cantidad comparable de ganancias**; el
neto positivo sale de la cola derecha.

## 4. Niveles con 16 bps de ida y vuelta (misma pareja entrada/salida)

| Nivel | Original | Alternativa | Delta |
|---|---:|---:|---:|
| Bruto medio | −6,5948 | −1,9192 | +4,6756 |
| Bruto mediano | +1,2912 | +3,0683 | +1,7771 |
| Neto medio | −22,5948 | −17,9192 | **+4,6756** |
| Neto mediano | −14,7088 | −12,9317 | +1,7771 |
| Pares con neto > 0 | 41 | 25 | — |

El delta es invariante al coste porque ambos lados pagan los mismos 16 bps. La salida temprana recorta el
movimiento: mejora la mediana neta pero reduce los pares con neto positivo de 41 a 25. Funding `UNKNOWN`:
no se simula ni se suma.

## 5. Por dirección

| Dirección | n | Media | Mediana | Suma | Mejoran | Empeoran | Igualan | Pérdidas recortadas | Ganancias sacrificadas |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LONG | 52 | −3,1425 | −4,3592 | −163,41 | 23 | 28 | 1 | +1 724,90 (20) | −1 908,07 (25) |
| SHORT | 54 | +12,2042 | −1,4171 | +659,02 | 25 | 27 | 2 | +1 717,08 (21) | −952,21 (19) |

**Ninguna dirección es consistente:** LONG es negativa en media y mediana; SHORT tiene media positiva
pero mediana negativa. El agregado positivo lo aporta la cola derecha de SHORT (máximo +452,22).

## 6. Por tipo de cambio (primer cambio, prioridad publicada)

| Tipo | n | Media | Mediana | Suma | Mejoran | Empeoran |
|---|---:|---:|---:|---:|---:|---:|
| `giro` | 65 | +3,56 | −4,94 | +231,12 | 29 | 35 |
| `debilitamiento` | 22 | −7,33 | −14,39 | −161,30 | 7 | 15 |
| `precio_sin_avance` | 6 | +13,54 | +7,73 | +81,25 | 3 | 3 |
| `profundidad_deja_de_caer` | 13 | +26,50 | +9,99 | +344,54 | 9 | 2 |

El tipo más frecuente (`giro`, 61 %) y el más débil (`debilitamiento`) no muestran ventaja; los dos
tipos con mediana positiva tienen n = 6 y n = 13, insuficientes para cualquier conclusión.

## 7. Las cuatro anclas del patrón

| # | Contrato | Dir. | Corte | Entrada | Cambio | Disponible | Salida alt. | Precio alt. | Salida orig. | Precio orig. | Ret. orig. | Ret. alt. | Delta |
|---|---|---|---|---|---:|---|---:|---|---:|---|---:|---:|---:|---:|
| 1 | BLESSUSDT | SHORT | 19:30:01.355 | 19:31:00 | `debilitamiento` `b_0` | 19:31:00.149 | 19:32:00 | 0,018165 | 19:36:00 | 0,018355 | −99,04 | +5,50 | **+104,54** |
| 2 | STRKUSDT | LONG | 19:56:04.530 | 19:57:00 | no identificable (`b_0` `flujo_incompleto`) | — | — | — | 20:02:00 | 0,03415 | +44,12 | — | no evaluable |
| 3 | BLESSUSDT | SHORT | 20:06:00.464 | 20:07:00 | `debilitamiento` `b_0` | 20:07:04.997 | 20:08:00 | 0,017475 | 20:12:00 | 0,017782 | −142,02 | +33,08 | **+175,10** |
| 4 | ARIAUSDT | LONG | 20:15:00.502 | 20:16:00 | `giro` `b_0` | 20:16:00.272 | 20:17:00 | 0,20945 | 20:21:00 | 0,20686 | −156,55 | −33,31 | **+123,25** |

Entrada de todas: apertura del primer minuto tras el corte. En los tres casos resolubles el bot conocía
el cambio entre 149 ms y 5 s después de entrar, y habría salido en la apertura del minuto siguiente:
cuatro minutos antes. Los tres perdedores habrían recortado la pérdida; el ganador (STRKUSDT) no es
evaluable porque el flujo de `b_0` está incompleto, así que **no se puede afirmar** cuánto habría
sacrificado. Con n = 3 resolubles, esto es una ilustración, no evidencia.

## 8. Verificación

- `verificacion.anclas_publicadas_coinciden = 143`: las 143 anclas reconstruidas coinciden con
  `episodios_referencia_universo_igual.jsonl` (terna, contrato, dirección, corte, estado y retorno).
- `verificacion.bloques_publicados_coinciden = 858`: los 143 × 6 bloques recalculados coinciden con
  `anclas_cambios.jsonl` (estado, flujo alineado, precio de cierre, Δclose, profundidad y tipos). La
  regla publicada se reutilizó sin tocar umbrales.
- `verificacion.disponibilidad_publicada_registrada = 143`, y
  `minuto_de_salida_distinto_por_definicion = 0`: la disponibilidad «solo acreditante» nunca cambia el
  minuto de salida frente a la disponibilidad amplia publicada. La diferencia se registra, no se aplica
  en silencio.
- Verificador independiente (`D-verificacion.txt`): **2 801 comprobaciones, 0 fallos**. Relee las velas
  con su propio parser, recalcula precios, retornos, deltas, medias, medianas, cubos, agregados por
  dirección y tipo, la aritmética del embudo, la guarda de look-ahead, el umbral de 30 pares y los
  hashes de las 6 fuentes.
- `origen.fuentes_intactas = true`: los SHA-256 de las fuentes son idénticos antes y después.
- `B-pytest.txt`: **143 passed** en la suite focalizada (26 tests nuevos + 117 de regresión).

## 9. Limitaciones

1. **La regla publicada no discrimina.** Se cumple en `b_0` en el 93,4 % de los pares evaluables, así que
   la alternativa evaluada es en la práctica «salir un minuto después de entrar». Eso es una propiedad
   de la regla publicada, no del diseño de este bloque; pero implica que el resultado **no** responde a
   «¿es bueno salir en un cambio?», sino a «¿qué pasa si se usa la regla publicada como disparador de
   salida?».
2. **Una sola ventana y un solo día** (2026-11-16, 19:27–20:24 UTC). Sin repetición en otra captura.
3. **Precios simulados, no fills acreditados.** Las aperturas de 1 minuto son la resolución de precio
   disponible; no hay libro ni cola que acredite ejecución. El coste de 16 bps es una sensibilidad fija,
   no una medición.
4. **Funding `UNKNOWN`** y no simulado.
5. **28 anclas sin resultado original** (23 sin velas del símbolo, 5 sin vela de entrada) y **9 con hueco
   en `b_0`**: 37 de 143 quedan fuera. No son «sin cambio»; son no evaluables por falta de datos.
6. **Cobertura de contratos:** el selector publicado solo cubre PERPETUAL/TRADING/USDT. Los futuros con
   vencimiento no están representados en esta muestra; no se afirma nada sobre ellos.
7. **Cola derecha:** media +4,68 con mediana −2,87. Cualquier lectura de la media sin la mediana sería
   engañosa.

## 10. Reproducción

```
python scripts\salida_temprana_ventana4.py ^
  --db "C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a\research.db" ^
  --cobertura "docs\evidence\secuencia-presion-v1-correcciones-20261117\C-cobertura-real.json" ^
  --klines "C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a\consultas_klines.jsonl" ^
  --derivados-anclas "C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-anclas-comunes-v1" ^
  --derivados-cambios "C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-diagnostico-factores-v1\anclas_cambios.jsonl" ^
  --salida "C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-salida-temprana-v1" ^
  --resumen "docs\evidence\salida-temprana-ventana4-20261118\C-resumen.json"

python scripts\verificar_salida_temprana_ventana4.py --resumen ... --derivados ... ^
  --anclas-publicadas ... --klines ... --db ... --cobertura ... --anclas-cambios ...

python -m pytest tests\test_salida_temprana_ventana4.py -q
```

Los comandos completos, sus salidas y los códigos de salida observados están en `A-comando.txt`; la
verificación en `D-verificacion.txt`; las pruebas en `B-pytest.txt`. El detalle por ancla está en
`C-resumen.json` y en los derivados voluminosos fuera de Git
(`exp-v2-ventana-4-20261116a-salida-temprana-v1/anclas_salida_temprana.jsonl`).

## 11. Veredicto

`SIN_DIRECCION_CLARA`. Con 106 pares resolubles con salida efectivamente adelantada (≥ 30) no se declara
`INSUFICIENTE` por conteo, pero la media y la mediana no coinciden en signo y ninguna dirección ni tipo
de cambio es consistente. **Esta ventana no valida la regla de salida temprana ni autoriza promoverla.**

Hipótesis para un bloque futuro, **no ejecutada aquí**: la regla publicada necesita selectividad antes de
servir como disparador de salida —por ejemplo exigir materialidad mínima del cambio y limitarla a los
tipos con mediana positiva— y esa selección debe predeclararse y medirse en una captura nueva con su
propio `run_id`, con ≥ 30 pares por grupo. No se abre ahora.
