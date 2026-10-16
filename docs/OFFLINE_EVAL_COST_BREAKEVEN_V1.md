# Costes y punto de equilibrio — OFFLINE-EVAL-V1 (existentes, sin picking)

Version: `OFFLINE-EVAL-COST-V1` (2026-10-17, sin corridas, sin
optimizacion). Fuente: artefacto publicado
(`frontend/src/data/offline-eval-v1.json`, sha `c051e888…287b3a`).
Nocional fijo $1000 @1x por trade. Sin parametros ganadores
seleccionados: se reportan TODAS las celdas direccionales.

## 1. Presupuesto maximo de friccion (breakeven por celda)

`net = gross − friccion`; friccion escala lineal con `cost_scale`
(spread/slip + comisiones + funding todos x escala). Con
`F1` = friccion/op @1x y `G` = bruto/op (E[gross]):

- Friccion maxima que anula el bruto: `maxFric = G` (USDT/op).
- Escala de equilibrio: `s* = G / F1` (adimensional).
- En bps round-trip sobre $1000: `maxRT = G × 10`
  (1 USDT/op = 10 bps del nocional).

| Celda | n (R) | E[gross] | F1/op | E[net]@1x | s* | maxFric | maxRT | E[net]@2x | @3x |
|---|---|---|---|---|---|---|---|---|---|
| BTC H1 dev | 105 | +2.09 | 1.60 | +0.48 | 1.30 | 2.09U | 20.9bps | −1.12 | −2.72 |
| BTC H1 oos | 122 | +1.94 | 1.60 | +0.34 | 1.21 | 1.94U | 19.4bps | −1.26 | −2.87 |
| BTC H3 dev | 101 | +1.88 | 1.60 | +0.28 | 1.18 | 1.88U | 18.8bps | −1.32 | −2.92 |
| BTC H3 oos | 119 | +2.16 | 1.60 | +0.57 | 1.35 | 2.16U | 21.6bps | −1.03 | −2.63 |
| ETH H1 dev | 115 | +2.63 | 1.60 | +1.03 | 1.64 | 2.63U | 26.3bps | −0.58 | −2.18 |
| ETH H1 oos | 115 (114R) | +2.00 | 1.60 | +0.39R | 1.25 | 2.00U | 20.0bps | −1.21 | −2.81 |
| ETH H3 dev | 107 | +2.17 | 1.60 | +0.58 | 1.36 | 2.17U | 21.7bps | −1.02 | −2.62 |
| ETH H3 oos | 117 | +2.33 | 1.60 | +0.73 | 1.46 | 2.33U | 23.3bps | −0.87 | −2.46 |
| SOL H1 dev | 115 | +3.11 | 1.60 | +1.50 | 1.94 | 3.11U | 31.1bps | −0.10 | −1.70 |
| SOL H1 oos | 138 (137R) | +2.71 | 1.60 | +1.11R | 1.69 | 2.71U | 27.1bps | −0.49 | −2.09 |
| SOL H3 dev | 114 | +2.26 | 1.60 | +0.66 | 1.41 | 2.26U | 22.6bps | −0.94 | −2.54 |
| SOL H3 oos | 130 | +3.06 | 1.60 | +1.46 | 1.91 | 3.06U | 30.6bps | −0.14 | −1.74 |

H2 (fenced, INSUFFICIENT, n<=4, sin lectura): SOL
correction-dev n=4 E[net]+6.00/s*=4.74 y anecdotas n=1
(+21.67, +10.05) se REPORTAN pero no son evidencia.
Rebound/baseline: vacias (excluidas).

Lectura: las 12/12 celdas direccionales son negativas a 2x
(incluidas las de mayor margen: SOL H1-dev −0.10,
SOL H3-oos −0.14). El margen @1x (+0.28…+1.50/op) es mas
delgado que la incertidumbre de los supuestos (slippage sin
medir, tier desconocido). Fragilidad, no edge demostrado.

## 2. Desglose por lado / ida-vuelta / nocional / tamano

- Nocional/tamano: fijo $1000 @1x por trade (sin
  apalancamiento modelado mas alla de escalas de coste;
  tamano mayor escala USDT lineal, bps invariantes).
- Comisiones @1x: ~1.00 USDT/op = 5bps × 2 legs sobre
  ~$1000 (entrada sobre nocional ejecutado, salida sobre
  valor de salida qty×px — contrato v4.1; no mitades
  simetricas).
- Spread/slippage asumidos @1x: ~0.60 USDT/op = 3bps × 2
  legs (1bps spread + 2bps slippage, supuestos).
- Friccion @1x ≈ 1.60/op (comisiones ~1.00 + spread/slip
  ~0.60; funding ~0.0000–0.0008/op en celdas realizadas).
- Por lado (ida): ~0.80 USDT (~8bps: 5 fee + 3 drag);
  ida/vuelta: ~1.60 (~16bps) antes de funding.
- Funding con signo y cobertura: +0.0894 USDT aplicada en
  1 trade (ETH H1-dev LONG, settlement 1790006400002,
  signo paga/recibe por direccion; SHORT recibe a tasa
  positiva). 1403 cubiertas quietas (0 por ausencia de
  liquidacion, correcto). 8 UNKNOWN (`uncovered_ms`
  2700000 c/u) NUNCA valen cero: 6 colas cerradas + 2 marcas
  abiertas. Sensibilidad sin calendario: ETH H1-dev funding
  0.0894 → 0.0000 (delta +0.0894 total, ~0.0008/trade);
  resto identico. Magnitud despreciable Y cobertura
  incompleta en 8: "inmaterial" NO concluido para ese set.
- Realizadas vs abiertas: metricas-R excluyen las 2 marcas
  `open_at_end` (costes de salida hipoteticos separados en
  `costs_exit_hypothetical`; jamas citados como ejecutados).

## 3. Comisiones: escenarios con fuentes oficiales

Cuenta desconocida → tier jamas asumido como aplicable.
Fuente oficial: pagina de comisiones USDⓈ-M
(`binance.com/en/fee/futureFee`) + FAQ de estructura
(`support/faq/detail/360033544231`): regular maker 0.02%
(2bps) / taker 0.05% (5bps); VIP 1–9 descuentos; BNB
10% en futuros (0.018%/0.045%); market = siempre taker.

Escenarios ida/vuelta sobre $1000 (solo comisiones):

| Escenario | Ida/vuelta | USDT/op |
|---|---|---|
| Taker+taker (market, regular) | 5+5bps | ~1.00 (= supuesto V1) |
| Maker+maker (limit, regular) | 2+2bps | ~0.40 |
| Mixto | 2+5bps | ~0.70 |
| Taker+taker con BNB | 4.5+4.5bps | ~0.90 |

V1 supone taker+taker regular (coherente con fills a mercado
al open siguiente). Un escenario maker exigiria prueba de
ejecucion limit (ausente). VIP/BNB exigirian tier/saldo
(inciertos): se reportan como escenarios, nunca como
"comision aplicable".

## 4. Spread/slippage: UNKNOWN declarado

Sin historial venue de spread/profundidad (no ingerido;
`FUNDING_ACQUISITION_V1.md` §"Que NO contiene"). Slippage
es drag SUPUESTO (2bps), jamas "medido". Prohibido: llamar
"medido" a un supuesto; derivar slippage historico del
spread actual (no se hizo; el spread actual ni siquiera se
muestreo en esta tarea). Sensibilidad publicada: 1x/2x/3x
por celda (§1 + artefacto); el punto de equilibrio s*
1.18–1.94 muestra que duplicar la friccion supuesta anula
todo el bruto direccional.

## 5. Exposicion y comparacion (no cartera)

`max_concurrent=1` rige DENTRO de una celda
(symbol-run, grupo, segmento, escala): los 145 solapes son
estrictamente intra-celda (peor caso SOL H1-dev 52/167 =
31%). Simbolos/grupos/segmentos replayan en procesos y
ledgers separados con calendarios pinned (extranjero
RECHAZADO fail-closed): solapes H1-LONG vs H3-SHORT o
BTC vs SOL JAMAS compiten — ambos operan. Pooled es suma
aritmetica sobre replays independientes de posicion unica:
NO es cartera (puede implicar posiciones concurrentes
multi-simbolo/grupo sin margen cruzado, sin limite de
concurrencia, sin P&L de exposicion simultanea — no
modelado). No se presenta como cartera ni como baseline
predictivo.

Que cambia con competencia real (capital + exposicion
simultanea): fills reducidos (mas `skipped_overlap`
cross-grupo/simbolo), friccion por trade igual o mayor
(jamas menor por diversificar), curva pooled actual
invalida como P&L simultaneo, drawdown realizado
subestimado (suma de curvas independientes ignora
solape temporal). Sin modelo de posiciones/margen/fills,
cualquier "cartera" seria inventada: no se implementa.

Baseline comparable propuesto (NO implementado en V1,
regla para el protocolo): `TIME-PLACEBO-v1` — mismas
celdas, entradas en timestamps pseudoaleatorios con igual
cadencia/densidad por simbolo (seed fijado), identicos
horizonte/stop/costes/calendarios; compara distribucion
de E[net]R contra H1/H3 bajo la misma friccion supuesta.
Justificacion: aisla "estar expuesto 1h trasalla" del
contenido de la senal sin inventar fills/margen. Buy-and-hold
se descarta como comparable (horizonte/tenencia distintos;
responde otra pregunta). Ningun pooled demuestra valor
predictivo por si solo.
