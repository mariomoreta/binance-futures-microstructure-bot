# Predeclaracion: coste de ejecucion con las capturas existentes

Fecha de escritura: 2026-11-19T12:26Z.
Base publicada: `2be0e1fcc97ff58b1db0b6e59a8684c789debd07`
(`research/universe-liquidez-v1`).

Escrita y publicada **antes** de calcular cualquier retorno ajustado por
spread. Al escribir esto no se ha comparado ningun retorno con ningun coste.

## Pregunta

Los datos ya capturados permiten respaldar un coste de ejecucion para la regla
de continuacion de solo precio, y si lo permiten, cuanto margen queda?

## Universo congelado

Los **278 episodios evaluables de solo precio** publicados en
`docs/evidence/extension-previa-20261119/C-resumen.json`
(`primaria_solo_precio.detalle`). Se congelan contrato, direccion, corte,
entrada (apertura del minuto siguiente al corte) y salida (entrada + 5 min)
exactamente como se publicaron. No se recalcula la senal, no se reabre el
filtro de extension, no se cambia la estrategia ni el horizonte.

## Que cuenta como cotizacion verificable (C0)

Un registro con **precio de mejor bid y precio de mejor ask explicitos** para el
contrato del episodio, ambos numericos, positivos, con `ask > bid`.

**No cuentan** como bid/ask:

- una media de spread por minuto (`research_book_1m.spread_min/mean/max`);
- un mid (`precio_base` / `libro_mid`);
- una vela OHLC (`research_flow_1m.price_*`, `consultas_klines.jsonl`);
- el precio de un trade o de un aggTrade;
- los fills simulados del motor de papel (`resultado_operativo.jsonl`);
- `spread_slip` del motor de papel, que es un coste configurado, no observado.

Un precio derivado como `mid * (1 +/- spread_bps / 20000)` es aritmeticamente
reconstruible, pero **no es una cotizacion observada** y no satisface C0.

## Cercania (C1)

La cotizacion debe existir en el **mismo instante** del extremo:

- `|event_ms - instante| <= 5 000 ms` (instante = `entrada_ms` o `salida_ms`);
- `received_ms <= instante` (disponible cuando se decide, sin adelanto).

## Calidad (C2)

El registro debe estar no cruzado, no degradado, con al menos un nivel por lado
y sin actualizaciones invalidas segun los contadores de integridad de la propia
captura.

## Par evaluable (C3)

Un episodio es par evaluable solo si C0, C1 y C2 se cumplen en **ambos**
extremos (entrada y salida) con la misma regla.

## Suficiencia (C4)

Minimo **30 pares** evaluables para publicar cualquier agregado ajustado por
spread. Con menos, el veredicto es `DATOS_INSUFICIENTES` y solo se publica el
faltante exacto.

## Reglas de coste

- **Spread**: se cobra una sola vez, mitad al entrar y mitad al salir, y solo
  desde bid/ask observados. Nunca dos veces. Nunca desde medias por minuto.
- **Comision**: `UNKNOWN` mientras no exista una tarifa acreditada en los
  artefactos. No se importa una tarifa externa.
- **Slippage adicional**: `UNKNOWN` sin datos de fills, cola ni consumo de
  profundidad.
- **Funding**: `UNKNOWN`. No se asume cero.
- Ningun coste desconocido se sustituye por cero.

## No extrapolacion

Si hubiera un subconjunto con cobertura, sus resultados **no** se extrapolan a
los 278. El subconjunto se reporta como subconjunto.

## Regla de respaldo, fijada de antemano

Si C4 falla:

1. se publica el faltante exacto (campo, fuente, numero de episodios afectados);
2. se conserva **+5.13 bps** como umbral bruto descriptivo de los 278, no como
   rentabilidad y no como umbral del subconjunto;
3. se informa el **maximo coste adicional** que ese umbral soporta antes de
   llegar a cero, que es su propio valor;
4. **no** se publica un neto completo.

## Correccion de etiqueta del informe anterior

En `docs/evidence/extension-previa-20261119/README.md`, el valor **-1 506.08 bps**
se etiqueto como "neto del filtro". Es la **suma de los retornos netos de los
193 episodios descartados**. El cambio de suma al abstenerse de esas entradas es
**+1 506.08 bps** (de -3 022.24 a -1 516.16 bps). No es una mejora de
expectativa por operacion: la media retenida empeora de -10.87 a -17.84 bps.
El veredicto **NO APORTA** no cambia.

## Declaracion

Ningun retorno ajustado por spread se ha calculado al escribir esta
predeclaracion. La correccion de etiqueta es aritmetica sobre numeros ya
publicados, no un resultado nuevo.
