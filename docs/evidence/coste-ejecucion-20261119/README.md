# Coste de ejecucion con las capturas existentes

**Pregunta unica:** los datos ya capturados, permiten respaldar un coste de
ejecucion para la regla de continuacion de solo precio? Si lo permiten, cuanto
margen queda?

## Respuesta

**No. Los datos no permiten respaldar un coste de ejecucion para esta regla.**
Cobertura verificable: **0 de 278 pares**. No hay ni un solo episodio con
precio de mejor bid y mejor ask observados en la entrada **y** en la salida.

El unico margen cuantificable es el **umbral bruto descriptivo de +5.13 bps**
de los 278 (no es rentabilidad). El coste adicional maximo que esa muestra
soporta antes de llegar a cero es **5.13 bps**. Todo lo demas —spread real,
comision, slippage adicional y funding— queda en `UNKNOWN` /
`NO_VERIFICABLE`. **No se publica un neto ajustado.**

Veredicto de cobertura: `DATOS_INSUFICIENTES`.
Veredicto anterior de la regla: **NO APORTA** (sin cambios).

## 1. Universo congelado

Los 278 episodios evaluables de solo precio ya publicados
(`docs/evidence/extension-previa-20261119/C-resumen.json`, base
`2be0e1fcc97ff58b1db0b6e59a8684c789debd07`). Contrato, direccion, corte,
entrada (apertura del minuto siguiente) y salida (entrada + 5 min) permanecen
intactos. No se reabre el filtro de extension, no se cambia la estrategia,
no se usan capturas nuevas y no se accede a Binance.

## 2. Cobertura real

| captura | episodios | bucket e/s/ambos | bucket disponible al instante | mid+spread a +/-5 s en ambos | pares bid/ask (C0) | pares evaluables (C3) |
| --- | --- | --- | --- | --- | --- | --- |
| ventana 2 | 78 | 78 / 76 / 76 | 0 / 0 | 0 | 0 | 0 |
| ventana 3 | 57 | 57 / 57 / 57 | 0 / 0 | 0 | 0 | 0 |
| 1105a | 58 | 58 / 58 / 58 | 0 / 0 | 2 | 0 | 0 |
| 1106a | 85 | 84 / 82 / 81 | 0 / 0 | 0 | 0 | 0 |
| **total** | **278** | **277 / 273 / 272** | **0 / 0** | **2** | **0** | **0** |

Detalle completo en `INVENTARIO.md`.

## 3. Por que no hay cotizaciones

- `research_book_1m` guarda **agregados por minuto** del libro `depth20@100ms`:
  spread, imbalance, micro y cantidades por nivel. **No guarda precios de nivel.**
  Se publica ~60 s despues del instante: el agregado del minuto de entrada
  **no existe en el instante de entrada**, y lo mismo ocurre en la salida.
  Usarlo seria adelanto de informacion.
- `observaciones.jsonl.libro` guarda **mid y spread** en el instante de
  decision. No guarda best bid ni best ask.
- `resultado_operativo.jsonl` son **fills simulados** del motor de papel con
  `spread_slip` configurado, no cotizaciones de mercado.
- `http_requests.jsonl` no contiene ninguna peticion de profundidad.
- Las velas OHLC no son bid/ask.

Barrido de 527 archivos de texto de las capturas: 0 coincidencias de
`bidPrice`, `askPrice`, `best_bid`, `best_ask`, `bestBid` o `bestAsk`.

Los 2 unicos episodios con snapshot instantaneo en ambos extremos son
`LYNUSDT` LONG y `HUMAUSDT` SHORT (1105a), a 3.3/1.2 s y 3.3/1.5 s de los
instantes. Tienen mid y spread, **no bid/ask**. Ademas sus brutos (+32.82 y
+34.03 bps) estan muy por encima de la media de los 278: no se extrapolan.

La distancia mediana del snapshot mas cercano al instante es **72.6 s** en la
entrada y **72.5 s** en la salida. 276 episodios quedan fuera de la ventana
de +/-5 s fijada de antemano.

## 4. Comparacion con spread (paso 2)

**No se puede realizar.** No existe ningun par con bid y ask verificables, por
lo que no hay precio cotizado con el que entrar al ask/salir al bid (LONG) o
entrar al bid/salir al ask (SHORT). No se publica retorno cruzado alguno.

Descomposicion del coste:

| componente | estado | motivo |
| --- | --- | --- |
| spread | `NO_VERIFICABLE` | no existen best bid/ask; la media de spread por minuto no es una cotizacion y ademas se publica tarde |
| comision | `UNKNOWN` | no hay tarifa acreditada en los artefactos de estas capturas |
| slippage adicional | `UNKNOWN` | no hay fills, cola ni consumo de profundidad |
| funding | `UNKNOWN` | `funding_adquisicion.jsonl` vacio o ausente en las 4 capturas |

Ningun desconocido se sustituye por cero. El spread no se cobra dos veces.

## 5. Cuanto margen queda (paso 3)

- Pares evaluables: **0** (minimo predeclarado: 30).
- Retorno bruto medio de los 278: **+5.1286 bps**, solo descriptivo.
- **Coste adicional maximo soportado antes de cero: 5.1286 bps.**
- El unico spread observado disponible es el agregado por minuto: mediana
  **4.64 bps** sobre 550 buckets (42.9 % superan 5.13 bps). Es del mismo orden
  que todo el presupuesto bruto, pero **no es una cotizacion** y se publica
  ~60 s despues del instante: no se aplica al retorno ni se convierte en un
  neto.
- **Margen verificable restante: UNKNOWN.** La muestra no demuestra margen
  positivo tras un coste de ejecucion real. El valor +5.13 bps no se usa como
  rentabilidad ni como umbral del subconjunto.

## 6. Correccion de etiqueta del informe anterior (paso 4)

En `docs/evidence/extension-previa-20261119/README.md` se etiqueto
**-1 506.08 bps** como "neto del filtro". La etiqueta correcta es:

- **-1 506.08 bps** = suma de los retornos netos de los **193 episodios
  descartados** (`-1506.0839` sin redondear).
- **+1 506.08 bps** = cambio de la suma al **abstenerse** de esas entradas
  (`+1506.0839`), de `-3022.2391` a `-1516.1552` bps.

Esto **no** implica mejora de expectativa por operacion: la media retenida
empeora de -10.87 a -17.84 bps. El veredicto **NO APORTA** se mantiene.

El campo `neto_del_filtro_bps` del `C-resumen.json` anterior queda intacto para
no alterar la salida publicada ni su hash; su significado real se documenta
aqui y se recalcula en `correccion_etiqueta` del nuevo inventario.

## 7. Reproduccion

```
python scripts\coste_ejecucion_inventario.py --salida C:\proyectos\binance-futures-data\coste-ejecucion-v1\inventario.json
python scripts\coste_ejecucion_inventario.py --compacto --salida docs\evidence\coste-ejecucion-20261119\C-inventario.json
python scripts\verificar_coste_ejecucion.py --inventario <inventario.json> --compacto docs\evidence\coste-ejecucion-20261119\C-inventario.json
python -m pytest <7 archivos> -q
```

Evidencia: `A-comando.txt`, `B-pytest.txt`, `C-inventario.json`,
`D-verificacion.txt`, `INVENTARIO.md`, `PREDECLARACION.md`.

sha256 salida completa (dos ejecuciones identicas):
`6946d10bd313f2379ab6b120273ac5f45b91dbe5020ffe0cbfd1e5626e7a7a8c`

sha256 `C-inventario.json`:
`85cf9fd3e941a0dadc1164c4b538e001ef56a4bfb827b3c050d34b2224d65385`

Verificador independiente: **10 086 comprobaciones, 0 fallos**.
Pruebas enfocadas: **123 passed**.

## 8. Limitaciones

- `research_flow_1m.price_open` es un agregado derivado de aggTrade, no un
  fill ni una cotizacion; no se puede reconstruir bid/ask a partir de el.
- Reconstruir `mid +/- spread_bps/2` seria aritmetica, no una cotizacion
  observada; la predeclaracion lo excluye.
- Solo 4 capturas con episodios (ventana 4 queda fuera por diseno).
- 91 de 556 buckets usados estan marcados `degraded`; 0 `crossed`.
- No se activa filtro ni se cambia el bot. Este resultado solo justifica, en
  su caso, una futura captura que registre best bid/ask con timestamp; no
  autoriza ni una sola entrada real.
