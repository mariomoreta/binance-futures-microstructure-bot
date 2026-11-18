# Evaluacion exploratoria del patron SECUENCIA-PRESION-V1 sobre la ventana 4 (2026-11-18)

Estado: **exploratoria, offline, solo lectura**. No es una prueba independiente
(captura ya usada en el desarrollo del detector), no declara rentabilidad y no
autoriza ninguna captura, despliegue ni ejecucion.

## 1. Pregunta

Sobre las ternas de 3 minutos ya acreditadas en la captura
`exp-v2-ventana-4-20261116a` (2026-11-16):

1. ¿El patron congelado `SECUENCIA-PRESION-V1` selecciona casos cuyo movimiento
   a 5 minutos difiere del de una referencia de solo precio?
2. ¿Cual es la cadena `ternas → alertas → episodios → resultados resolubles`
   para el patron y para la referencia?
3. ¿La evidencia permite concluir que merece una prueba independiente?

Las condiciones del detector, el umbral, el horizonte, la agrupacion y el
universo quedaron congelados antes de mirar resultados. No hubo cambios
posteriores.

## 2. Entradas y fidelidad

| Entrada | Fuente | SHA-256 |
|---|---|---|
| Universo acreditado | `docs/evidence/secuencia-presion-v1-correcciones-20261117/C-cobertura-real.json` | `39652bf0…eaf4bd` |
| Agregados flujo/libro | `research.db` (solo lectura) | `6ad6f716…6a7f1` |
| Velas 1 m | `consultas_klines.jsonl` | `4ee61463…a61874` |

El adaptador construye `VentanaPresion` directamente desde la cobertura
publicada y las filas verificadas de `research.db`; aborta si algun campo no
coincide. No se reconstruyen intervalos desde `decision_ms` ni se fabrican
filas piloto.

Universo conservado hasta la entrada del detector:

| Metrica | Publicado | En el detector | Discrepancias |
|---|---|---|---|
| Ventanas | 1 005 | 1 005 | 0 |
| Ternas | 501 | 501 | 0 |
| Simbolos | 43 | 43 | 0 |

- 1 005/1 005 ventanas con profundidad top-20 positiva y validas para el detector.
- 0 ternas acreditadas con `as_of_ms` anterior al cierre del bucket.
- Procedencia `aggTrade/depth20` en las 1 005.
- Cobertura de velas: 161 consultas, 0 rechazadas, 10 143 filas, 7 642
  duplicados identicos, 4 instantaneas contradictorias sobre **una sola** vela
  (`4USDT @1794862680000`, apertura 0.008594 vs 0.008592), excluida; no afecta a
  ningun episodio. 0 velas provisionales usadas para MAE.
- 95 de las 1 107 ternas de solo precio (8.6 %) pertenecen a 18 simbolos sin
  velas; por eso la referencia deja casos no resolubles de forma estructural.

## 3. Regla causal del corte

`corte = max(cierre nominal del ultimo bucket, disponibilidad de flujo, disponibilidad de libro)`
para el patron; `max(cierre nominal, disponibilidad de flujo)` para la
referencia de solo precio. Es tiempo reconstruido, no ejecucion en vivo.

- Entrada = apertura de la primera vela de 1 m que empieza estrictamente despues
  del corte: `(corte // 60 000 + 1) * 60 000`. Se exige esa vela exacta, sin
  saltar huecos.
- Salida = apertura exactamente 5 minutos despues. No hay stop ni salida
  intravela.
- Demora corte vs cierre nominal en las 501 ternas: min 163 ms, mediana 715 ms,
  max 53 545 ms; en los 4 casos alertados, 464–4 530 ms. En todos, el corte cae
  dentro del mismo minuto, por lo que ambos metodos comparten la misma vela de
  entrada.
- El cierre de `aggTrade` **no** se usa como precio ejecutable.

## 4. Cadena del patron

```
501 ternas evaluadas
  4 alertas brutas (2 LONG, 2 SHORT)
  4 episodios (sin repeticiones que agrupar)
  4 resolubles (0 no resolubles)
```

Detalle por alerta/episodio (corte, demora y precios):

| Simbolo | Dir | Terna (3.ª ventana) | Corte UTC | Demora vs cierre | Entrada (ms) | Salida (ms) | P. entrada | P. salida | Retorno |
|---|---|---|---|---|---|---|---|---|---|
| BLESSUSDT | SHORT | 1794857340000 | 19:30:01.355 | 1 355 ms | 1794857460000 | 1794857760000 | 0.018175 | 0.018355 | −99.04 bps |
| STRKUSDT | LONG | 1794858900000 | 19:56:04.530 | 4 530 ms | 1794859020000 | 1794859320000 | 0.034000 | 0.034150 | +44.12 bps |
| BLESSUSDT | SHORT | 1794859500000 | 20:06:00.464 | 464 ms | 1794859620000 | 1794859920000 | 0.017533 | 0.017782 | −142.02 bps |
| ARIAUSDT | LONG | 1794860040000 | 20:15:00.502 | 502 ms | 1794860160000 | 1794860460000 | 0.210150 | 0.206860 | −156.55 bps |

Demora total corte → entrada: 55.5–59.5 s (incluye el resto del minuto del corte).

Embudo de condiciones congeladas (`_evaluar_terna` real, solo diagnostico):

| Direccion | Ternas | Precio avanza | + Q positivo/creciente | + profundidad | Alertas |
|---|---|---|---|---|---|
| LONG | 501 | 104 | 5 | 2 | 2 |
| SHORT | 501 | 107 | 11 | 2 | 2 |

La condicion limitante es **Q** (flujo agresivo neto sobre profundidad
contraria, positivo y estrictamente creciente): `q_positivo_finito` descarta
440 ternas LONG y 419 SHORT.

## 5. Referencia de solo precio

Misma secuencia monotona de tres cierres, sin flujo ni profundidad; mismos
cortes, misma agrupacion de episodios, mismos precios y mismo horizonte.

```
1 107 ternas contiguas de solo precio
  473 monotonas = 473 alertas (236 LONG, 237 SHORT)
  237 episodios (117 LONG, 120 SHORT)   [236 repeticiones agrupadas]
  189 resolubles, 48 no resolubles
```

No resolubles: 34 `sin_velas_para_simbolo` (18 simbolos) y 14
`vela_entrada_ausente` aun teniendo velas. Ninguna se relleno ni se salto.

## 6. Resultados por grupo y direccion

Retorno bruto alineado (LONG: +, SHORT: −), en bps. MAE = excursion adversa
media, solo con trayectoria completa.

### Patron (4 episodios)

| Grupo | Dir | Ternas | Alertas | Episodios | Resolubles | No res. | Aciertos | Fallos | Neutros | Media | Mediana | MAE |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Patron | LONG | 501 | 2 | 2 | 2 | 0 | 1 | 1 | 0 | −56.22 | −56.22 | −95.97 |
| Patron | SHORT | 501 | 2 | 2 | 2 | 0 | 0 | 2 | 0 | −120.53 | −120.53 | −276.14 |
| **Patron** | **Total** | **501** | **4** | **4** | **4** | **0** | **1** | **3** | **0** | **−88.37** | **−120.53** | **−186.05** |

IC 95 % bootstrap de la media: **[−149.29, −2.42] bps**.

### Referencia de solo precio

| Grupo | Dir | Ternas | Alertas | Episodios | Resolubles | No res. | Aciertos | Fallos | Neutros | Media | Mediana | MAE |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Referencia | LONG | 1 107 | 236 | 117 | 92 | 25 | 49 | 43 | 0 | +10.78 | +8.13 | −71.55 |
| Referencia | SHORT | 1 107 | 237 | 120 | 97 | 23 | 43 | 51 | 3 | −19.68 | −2.94 | −90.43 |
| **Referencia** | **Total** | **1 107** | **473** | **237** | **189** | **48** | **92** | **94** | **3** | **−4.85** | **−0.00** | **−81.24** |

("Ternas" = ternas contiguas evaluadas; de ellas 473 son monotonas y generan
una alerta cada una.)

IC 95 % bootstrap de la media: **[−20.40, +8.91] bps**.

### Particion de la referencia

| Subconjunto | Episodios | Resolubles | Aciertos/Fallos/Neutros | Media | Mediana | IC 95 % |
|---|---|---|---|---|---|---|
| Referencia que **tambien** es patron (ancla alertada) | 3 | 3 | 0/3/0 | −132.54 | −142.02 | [−156.55, −99.04] |
| Referencia **sin** patron | 234 | 186 | 92/91/3 | −2.79 | −0.00 | [−17.02, +11.46] |

La particion usa el ancla del episodio. Los 4 episodios del patron se reducen a
3 en la particion porque la alerta LONG de STRKUSDT (19:56, +44.12 bps) cayo
dentro de un episodio LONG de solo precio anclado antes; su resultado queda en
el subconjunto "sin patron" y no se duplica. Esto es consecuencia de la regla de
agrupacion, no de una seleccion posterior.

## 7. Concentracion

Patron: 3 simbolos; BLESSUSDT aporta 2/4 episodios (50 %) y ambos SHORT.
Por hora UTC: 19 h → 2 episodios (−27.46 bps de media); 20 h → 2 (−149.29).

Referencia: 25 simbolos con episodios resolubles; maximo SPACEUSDT 15/189
(7.9 %), HUMAUSDT 14, BULLAUSDT/CROSSUSDT 13. Por hora: 19 h → 101 episodios
(+6.20 bps); 20 h → 88 (−17.54).

La muestra del patron depende de un solo simbolo. Con n=4 no es posible separar
senal de concentracion.

## 8. Sensibilidad de coste (documentada, no P&L)

Coste de ida y vuelta supuesto: 16 bps (fee 5 bps por lado + spread 1 bp +
slippage 2 bps por lado). **Funding: UNKNOWN**. No se modela impacto ni
profundidad de ejecucion.

| Grupo | Media bruta | Media neta | Mediana neta |
|---|---|---|---|
| Patron | −88.37 | −104.37 | −136.53 |
| Referencia | −4.85 | −20.85 | −16.00 |
| Referencia sin patron | −2.79 | −18.79 | −16.00 |
| Referencia tambien patron | −132.54 | −148.54 | −158.02 |

## 9. Conclusion

Regla declarada de antemano: minimo 30 episodios resolubles por grupo; si no se
alcanza, o si el signo se invierte al excluir el simbolo dominante, la
conclusion es "datos insuficientes".

- Patron: 4 episodios resolubles < 30. Punto de vista observado: media
  −88.37 bps, mediana −120.53 bps, 1 acierto / 3 fallos, peor que la referencia
  (−4.85 media, −0.00 mediana) y que el subconjunto de referencia sin patron
  (−2.79).
- La referencia tampoco muestra ventaja clara: su IC 95 % cruza cero.

**Conclusion formal: datos insuficientes.**

No se puede afirmar que el patron mejore la seleccion ni que la empeore: 4
observaciones, 50 % de ellas en un simbolo y sin potencia estadistica. No
"merece una prueba independiente" con esta evidencia (el criterio exigia ≥30
episodios resolubles y ventaja robusta en media y mediana); tampoco se declara
"no muestra mejora" como hallazgo, porque el tamano de muestra no permite
distinguir un efecto real de un artefacto de concentracion.

## 10. Limitaciones

- Captura ya usada en el desarrollo del detector: hallazgo exploratorio, no
  prueba independiente.
- Corte reconstruido; no hubo detector en vivo. La entrada es la apertura de la
  vela siguiente, no un fill; no incluye latencia de red ni de decision.
- Sin stop ni salida intravela; no se evalua gestion de posicion.
- Funding UNKNOWN; costes solo como sensibilidad.
- Episodios de distintos simbolos pueden solaparse en el tiempo (no son
  independientes).
- Cobertura de velas limitada a los simbolos consultados durante la captura
  (18 simbolos sin velas).
- Universo PERPETUAL/TRADING/USDT unicamente; futuros con vencimiento no
  soportados por el selector actual.
- Un solo `run_id` y ~1 hora de mercado: no hay estabilidad temporal.

## 11. Reproduccion

```
$env:PYTHONIOENCODING='utf-8'
python scripts\replay_patron_ventana4.py `
  --db "C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a\research.db" `
  --cobertura "docs\evidence\secuencia-presion-v1-correcciones-20261117\C-cobertura-real.json" `
  --klines "C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a\consultas_klines.jsonl" `
  --salida "C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-patron-v1" `
  --resumen "docs\evidence\patron-ventana4-evaluacion-20261118\C-resumen.json"
```

- `A-replay-comando.txt`: comando, salida, exit 0, hashes antes/despues y
  reproducibilidad byte a byte (hash de resumen identico en dos corridas).
- `B-pytest.txt`: 6 pruebas nuevas y 60 pruebas focalizadas, exit 0.
- `C-resumen.json`: resumen completo (universo, embudo, grupos, IC, costes,
  cobertura de velas, hashes de derivados).
- `D-verificacion-independiente.txt`: recalculo de las 4 ternas y de sus 8 velas
  sin importar el modulo de replay; retornos identicos a los publicados.

Derivados voluminosos (fuera de Git):
`C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-patron-v1`
(`ternas_patron`, `alertas_patron`, `episodios_patron`,
`alertas_referencia`, `episodios_referencia`; hashes en `C-resumen.json`).
