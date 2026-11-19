# Extension previa del movimiento vs regla de solo precio

Fecha de cierre: 2026-11-19. Base al iniciar:
`91e16671ca6492316023f1c9a7ac6c06149333ee` (`research/universe-liquidez-v1`).
Predeclaracion publicada antes de calcular retornos: commit
`561d0b953cf665cab83047f90003bc37d1b28a99`.

## Veredicto

**NO APORTA.**

Medir cuanto se ha extendido el movimiento respecto a la historia del propio
contrato **no** permite evitar entradas peores en esta muestra. La mediana neta
de los episodios no extendidos supera a la de los extendidos por 2.53 bps, pero
la media empeora 10.03 bps y el intervalo bootstrap de la diferencia de medias
incluye cero. El filtro descartaria el 69.4 % de las senales, evitando
8 594 bps de perdidas y renunciando a 7 088 bps de ganancias. La **suma de los
retornos descartados** es **-1 506 bps**; abstenerse de esas entradas **cambia
la suma en +1 506 bps** en 278 episodios.

El resultado no es un empate: es una ventaja de mediana que no sobrevive a la
media, cambia de signo entre LONG y SHORT y solo aparece en 2 de 4 capturas.
Ningun grupo es rentable despues de 16 bps.

Una condicion del criterio predeclarado falla (la 2). Con una sola condicion
fallida el veredicto es `NO APORTA`; no hay margen para reinterpretarlo despues
de ver los retornos.

## 1. Pregunta y alcance

Cuando aparece una senal de continuacion, medir cuanto se ha extendido el
movimiento frente a la historia del propio contrato, permite evitar entradas
peores que las de una regla de solo precio?

- Solo lectura de capturas existentes. Sin Binance, sin capturas nuevas, sin
  ordenes, sin cambios en detector, motor, dashboard ni estrategia.
- La ventana 4 queda excluida: formula la hipotesis, no la confirma.
- Familia primaria: episodios de continuacion de **solo precio** (tres cierres
  estrictamente monotonos, corte causal), agrupados por contrato y direccion
  dentro de 5 minutos. 914 episodios.
- Familia secundaria: episodios del **patron** con flujo y profundidad. 17
  episodios; no decide.

## 2. Reglas congeladas

Definidas en `PREDECLARACION.md` y publicadas en
`561d0b953cf665cab83047f90003bc37d1b28a99`, antes de cualquier retorno:

- `avance_senal = |close(t3)/close(t1) - 1|` con los tres minutos de la senal.
- 6 bloques previos de 3 minutos contiguos y no solapados, inmediatamente
  anteriores a la senal, cada minuto `data_quality = OK`, precios positivos y
  `as_of_ms <= corte`.
- `extension = avance_senal / mediana(6 avances previos)`.
- `EXTENDIDO` si `extension > 1.0`; `NORMAL` si `<= 1.0`.
- Entrada en la apertura del minuto siguiente al corte, salida en la apertura de
  `entrada + 5 min`, coste simulado de 16 bps de ida y vuelta en ambos grupos.
- Minimo 30 episodios por grupo; cinco condiciones de conservacion; ninguna
  ajustada despues de ver resultados.

## 3. Cobertura

Episodios y motivos de exclusion (excluyentes, en orden de embudo):

| paso | episodios |
|---|---:|
| episodios de solo precio en capturas distintas de la ventana 4 | 914 |
| menos historia previa insuficiente (menos de 18 min contiguos) | -537 |
| menos mediana previa nula (6 bloques con avance 0) | -1 |
| menos vela de entrada ausente | -31 |
| menos vela de salida ausente | -67 |
| **evaluables** | **278** |

Cobertura por captura (episodios / evaluables): ventana 2 231/78, ventana 3
229/57, pilot 1105a 217/58, pilot 1106a 237/85. Ventana 1 aporta 0: su tabla
`research_flow_1m` esta vacia (0 filas) y sin flujo no hay senal ni avance.

La historia previa es la restriccion dominante (537 de 914): el grabador rota
contratos y la mediana de minutos por contrato es de 15 a 37, de modo que la
mayoria de las senales aparece antes de acumular 18 minutos contiguos.

El inventario conto 279 episodios con historia y precios; la definicion
predeclarada descarta uno mas porque su mediana previa es 0 y el cociente no esta
definido (`mediana_previa_nula`). De ahi los 278 evaluables. La diferencia esta
explicada y no es un ajuste posterior: la regla de la mediana nula figura en
`PREDECLARACION.md`.

Detalle completo del inventario en `INVENTARIO.md` y
`A-inventario-resumen.json`; salida integra fuera de Git en
`C:\proyectos\binance-futures-data\extension-previa-v1-inventario\inventario.json`.

## 4. Resultado principal

Retornos netos en bps tras 16 bps de coste:

| grupo | n | mediana | media | suma | positivos | bruto mediano | bruto medio |
|---|---:|---:|---:|---:|---:|---:|---:|
| `EXTENDIDO` (`extension > 1`) | 193 | **-16.00** | **-7.80** | -1 506.08 | 77 | 0.00 | +8.20 |
| `NORMAL` (`extension <= 1`) | 85 | **-13.47** | **-17.84** | -1 516.16 | 36 | +2.53 | -1.84 |
| diferencia NORMAL - EXTENDIDO | | **+2.53** | **-10.03** | | | | |

Intervalo bootstrap descriptivo de la diferencia de medias (1 000 remuestreos,
semilla 42): **[-57.04, +31.77]** bps. Incluye cero.

Sin filtro, los 278 episodios dan media -10.87 bps y mediana -16.00 bps: la
regla de solo precio no es rentable en esta muestra, con o sin filtro.

### Efecto del filtro

| concepto | valor |
|---|---:|
| episodios descartados | 193 de 278 (69.4 %) |
| perdidas evitadas (suma de netos negativos descartados) | 8 594.42 bps en 116 episodios |
| ganancias dejadas pasar (suma de netos positivos descartados) | 7 088.33 bps en 77 episodios |
| **suma de los retornos descartados** | **-1 506.08 bps** |
| **cambio de suma al abstenerse** | **+1 506.08 bps** |
| suma sin filtro -> suma retenida | -3 022.24 -> -1 516.16 bps |

Correccion de etiqueta (2026-11-19): el valor -1 506.08 bps descrito antes como
"neto del filtro" es la suma de los retornos de los 193 episodios descartados,
no el efecto de abstenerse. Al abstenerse, la suma aumenta +1 506.08 bps. Esto
no es una mejora de expectativa por operacion: el filtro conserva 85 episodios
con media -17.84 bps y mediana -13.47 bps: mejora la mediana 2.53 bps y empeora
la media 6.97 bps frente a no filtrar. El veredicto **NO APORTA** no cambia.

### Por direccion

| direccion | n | EXT n | EXT mediana | EXT media | NOR n | NOR mediana | NOR media |
|---|---:|---:|---:|---:|---:|---:|---:|
| LONG | 135 | 91 | -20.02 | -10.61 | 44 | -32.04 | -52.44 |
| SHORT | 143 | 102 | -16.00 | -5.30 | 41 | +2.51 | +19.30 |

La ventaja de mediana viene integramente de SHORT. En LONG el signo se invierte
con fuerza: los no extendidos pierden 12 bps mas de mediana y 42 bps mas de
media. Un filtro aplicado a LONG empeoraria el resultado.

### Por captura

| captura | n | EXT n | EXT mediana | NOR n | NOR mediana | NORMAL supera |
|---|---:|---:|---:|---:|---:|---|
| `exp-v2-ventana-2-20261112a` | 78 | 52 | -27.87 | 26 | +9.12 | si |
| `exp-v2-ventana-3-20261115a` | 57 | 39 | -21.43 | 18 | -24.77 | no |
| `public-pilot-1h-20261105a` | 58 | 42 | -6.83 | 16 | +13.14 | si |
| `public-pilot-1h-20261106a` | 85 | 60 | -16.00 | 25 | -22.59 | no |

Dos capturas a favor y dos en contra, en dias distintos. No hay direccion
estable entre capturas.

### Terciles de extension (descriptivo, sin valor de decision)

| tercil | n | rango de extension | mediana neta | media neta |
|---|---:|---|---:|---:|
| 1 (menos extendido) | 92 | 0.11 - 1.02 | -10.97 | -13.91 |
| 2 | 93 | 1.04 - 2.15 | -21.43 | -13.22 |
| 3 (mas extendido) | 93 | 2.19 - 13.24 | -16.00 | **-5.52** |

No hay dosis-respuesta: el tercil mas extendido tiene la mejor media de los
tres. Si la extension midiera agotamiento, el orden deberia ser monotono en
sentido contrario.

### Concentracion

- 48 contratos aportan episodios evaluables.
- Maximo: `JCTUSDT` 18 (6.5 %), `BTWUSDT` 16 (5.8 %), `HUMAUSDT` 15 (5.4 %),
  `2ZUSDT` 14, `SOPHUSDT` 14, `AKEUSDT` 13.
- Sin el contrato dominante (`JCTUSDT`): mediana NORMAL -13.47 vs EXTENDIDO
  -16.00, se mantiene.
- Sin el episodio de mayor `|neto|` (`BTWUSDT` SHORT, 2026-11-14T02:51:01.679Z,
  -893.24 bps): mediana NORMAL -12.81 vs EXTENDIDO -16.00, se mantiene.

El fallo no esta causado por un contrato ni por un episodio extremo: la mediana
es robusta y aun asi no alcanza para conservar la hipotesis, porque la media y
la direccion no acompanan.

## 5. Familia secundaria (patron con flujo y profundidad)

17 episodios en 4 capturas; **2 evaluables** (14 pierden la historia previa, 1
la vela de entrada). Ambos son `EXTENDIDO`:

| contrato | direccion | corte | extension | neto bps |
|---|---|---|---:|---:|
| `MAGMAUSDT` | LONG | 2026-11-15T16:46:00.385Z | 6.567 | +2.63 |
| `AKEUSDT` | LONG | 2026-11-06T05:52:00.396Z | 1.521 | +47.32 |

Con 2 casos no hay grupo `NORMAL`: el veredicto de esta familia es
**`DATOS INSUFICIENTES`**. No decide el resultado y no se puede afirmar nada
sobre ella.

Los dos episodios del patron no coinciden con episodios de solo precio: la
agrupacion se aplica por separado a cada familia y la alerta del patron no es la
primera alerta de solo precio de su ventana de 5 minutos. Se reportan aparte y
no se suman a los 278.

## 6. Costes y funding

- Coste simulado: 16 bps de ida y vuelta (8 bps por lado), identico en ambos
  grupos. No cambia la comparacion, solo el nivel.
- Sin modelo de spread variable, slippage por tamano, latencia ni cola de
  ejecucion. Los precios son aperturas simuladas, no fills acreditados.
- **Funding: `UNKNOWN`.** No se simula ni se estima. Con horizontes de 5 minutos
  el efecto esperado es pequeno, pero no esta medido y no se usa como excusa.

## 7. Limitaciones declaradas

1. La serie de precios es `research_flow_1m.price_open` / `price_close`, un
   agregado guardado derivado de `aggTrade`. Los ticks crudos no se
   persistieron (`observaciones.jsonl` guarda el log de seleccion por ciclo, no
   los aggTrades), asi que no se puede reconstruir desde ticks.
2. Contraste con velas solo disponible en la ventana 3: 736 aperturas
   comparadas, 576 identicas, 160 distintas, diferencia relativa mediana 0 y
   maxima 0.164 %, 0 velas contradictorias. En las otras capturas no hay
   `consultas_klines.jsonl`.
3. Las ventanas se reconstruyeron con las reglas publicadas pero sin el
   contraste `C-cobertura-real.json`, que solo existe para la ventana 4.
4. Ventana 1 tiene `research_flow_1m` vacia: aporta 0 casos y se reporta, no se
   omite.
5. Los episodios se solapan en el tiempo entre contratos y las capturas son de
   tres dias distintos. No son observaciones independientes: el bootstrap es
   descriptivo, no inferencial.
6. La cobertura de historia previa (41.2 % de los episodios con 6 bloques) la
   fija la rotacion de contratos del grabador, no un criterio de calidad.
7. El mismo contrato aparece en varias capturas; el leave-one-symbol-out se
   aplico al conjunto, no por captura.
8. No se usa la ventana 4 para confirmar y no se abre ninguna captura nueva.

## 8. Que haria falta para reabrir

No se activa ningun filtro y no se cambia el bot. Para volver a examinar la
hipotesis haria falta:

- una captura nueva, con `run_id` propio, que mantenga al menos 18 minutos
  contiguos por contrato para >= 30 episodios en **cada** grupo;
- al menos dos dias de captura independientes que sostengan el signo;
- un modelo de coste de ejecucion real (spread, slippage, funding) en lugar de
  16 bps fijos.

El criterio y la definicion tendrian que republicarse antes de mirar retornos,
igual que aqui.

## 9. Reproduccion

```
python scripts/extension_previa_inventario.py --salida <fuera-de-git>/inventario.json
python scripts/extension_previa_v1.py --salida <fuera-de-git>/resumen.json
python scripts/extension_previa_v1.py --salida docs/evidence/extension-previa-20261119/C-resumen.json --compacto
python scripts/verificar_extension_previa_v1.py <fuera-de-git>/resumen.json
python -m pytest tests/test_extension_previa_v1.py tests/test_secuencia_presion_v1.py \
  tests/test_replay_patron_ventana4.py tests/test_salida_temprana_ventana4.py \
  tests/test_comparar_anclas_ventana4.py tests/test_diagnostico_factores_ventana4.py \
  tests/test_analisis_contrafactual_ventana4.py -q
```

Codigos de salida observados: inventario 0, evaluacion 0, compacto 0,
verificador 0, pytest 0. Salidas en `A-comando.txt`, `B-pytest.txt` y
`D-verificacion.txt`.

Verificacion independiente: `scripts/verificar_extension_previa_v1.py`
reimplementa con solo la biblioteca estandar el embudo, la definicion y los
retornos leyendo cada `research.db` en modo solo lectura. **3 687
comprobaciones, 0 fallos**, incluidas las 914 asignaciones de motivo, las 278
extensiones, los 278 grupos y los 278 retornos netos.

Determinismo: dos corridas consecutivas producen el mismo `sha256`
(`2ddfec419c855d04aa0d4f74850b12c4ec7465b0c765143b50705c214c3f2472`).

Hashes SHA-256 de las fuentes, identicos antes y despues de la publicacion:

```
23c6c5d513ce037b5b8f21cd6efb067df902357fbc62c65f512d9dd2e2e14f5e  exp-v2-ventana-1-20261112a/research.db
4885370c1628216dff7414194fe8b68770e51e1982710bb8cf5f4393d98a4760  exp-v2-ventana-2-20261112a/research.db
7f3c0e49550fcd56f500b8df649f3b42cd8ca8e1c6fc52193aef88291811cd52  exp-v2-ventana-3-20261115a/research.db
e5911be9162eaafdd5193a6191720802ab6e3566a8548427900a234f1e617edf  exp-v2-ventana-3-20261115a/consultas_klines.jsonl
706d0741783ef7d77d0170faa92d17ec267952b34a4cf4edf91797f95820923a  public-pilot-1h-20261105a/research.db
b54551dcc31792f04ee60f663e84ee46ba4b38c020a47e41ec03d9525ec11068  public-pilot-1h-20261106a/research.db
```

## 10. Archivos

| archivo | contenido |
|---|---|
| `PREDECLARACION.md` | definicion, grupos, minimo y criterio, publicados antes de los retornos |
| `INVENTARIO.md` | paso 1: cobertura por captura y motivos de exclusion, sin retornos |
| `A-inventario-resumen.json` | conteos del inventario por captura |
| `C-resumen.json` | agregados completos y detalle minimo de los 278 episodios |
| `A-comando.txt` | comandos y codigos de salida observados |
| `B-pytest.txt` | pruebas enfocadas |
| `D-verificacion.txt` | verificador independiente |
