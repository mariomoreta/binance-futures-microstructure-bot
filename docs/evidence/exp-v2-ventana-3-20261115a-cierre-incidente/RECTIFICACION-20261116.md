# Rectificación del cierre por incidente — ventana `exp-v2-ventana-3-20261115a`

**Fecha:** 2026-11-16 · **Estado:** RECTIFICACIÓN VIGENTE · **Alcance:** solo
offline, sin Binance, sin relanzamientos, sin ventanas nuevas. La ventana
permanece **INTERRUMPIDA** y su `run_id` **consumido**; no se fabrican
`cierre.json`, `exit_code.txt` ni manifiesto retrospectivo.

**Método:** los antecedentes ([INFORME](INFORME.md), `resumen.json`,
`evidencia_incidente.json` y sus hashes en `hashes.json`) **se conservan
intactos**; esta rectificación los corrige identificados por fichero y campo,
con fuentes y fórmulas en
`rectificacion_datos.json` (derivados en
`C:\proyectos\binance-futures-data\exp-v2-ventana-3-20261115a-cierre-incidente`,
dataset histórico verificado 12/12 por SHA-256 antes y después del análisis).

## 1. Horas y stop — CORREGIDO

| Instante | Publicado antes (INFORME.md §5) | Correcto (de `decision_ms`/`entry_ms`/`exit_ms`) |
|---|---|---|
| Decisión | ~~17:07:47Z~~ | **2026-11-15T16:27:47.214Z** |
| Fill (entrada) | ~~17:08:00Z~~ | **16:28:00.000Z** |
| Salida por stop | ~~17:36:40Z~~ | **16:30:00.000Z** (120 s en posición) |

Causa: conversión UTC errónea en la narrativa; los ms epoch de
`resumen.json` eran correctos (corroborados por `decision_iso` de la propia
fila: `2026-11-15T16:27:47.214000+00:00`).

**Stop de referencia vs stop efectivo (sin tocar el motor):**
- `stop_px` de la fila = **0,1315545** = stop de **referencia**, derivado del
  close de referencia previo al fill (la señal, no la ejecución).
- Stop **efectivo** tras el fill SHORT @ 0,1307 con distancia 0,5 %:
  `0,1307 × 1,005` = **0,1313535** = `exit_px` **exactamente** →
  `exit_reason=stop` se activó en el stop efectivo tras el fill.

**Recálculo independiente** (fórmulas: valor = qty × precio; bruto SHORT =
valor_entrada − valor_salida; fees = (v_ent + v_sal) × 5 bps
(`fee_bps=5.0`, `backtest_offline.py`); spread_slip = (v_ent + v_sal) × 3 bps;
neto = bruto − fees − spread_slip):

| Cuenta | Recalculado | Publicado | Coincide |
|---|---|---|---|
| Valor entrada / salida | 1000,00 / 1005,00 | — | — |
| Bruto | **−5,0000** | −4,9999999999997975 | ✔ |
| Fees | **1,0025** | 1,0025 | ✔ |
| Spread/slip | **0,6015** | 0,6014999999999999 | ✔ |
| Neto **condicionado** | **−6,6040** | −6,603999999999798 | ✔ |

El **−6,604 es el resultado CONDICIONADO sin funding** (funding ausente =
**UNKNOWN, nunca cero**): no es un neto completo y **no se presenta como P&L**.

## 2. Incidente — reconciliado con incertidumbre publicada

| Elemento | Antes | Rectificado |
|---|---|---|
| Última actividad | ~~17:30:06Z~~ (evidencia_incidente.json, estimación indirecta) | **17:30:40Z** — mtime acreditado de `estado.json` en el inventario con SHA-256; la estimación 17:30:06Z **se retira** |
| Primera ausencia de procesos | implícita | **≈18:04Z** (primera consulta CIM sin procesos); ventana de muerte **(17:30:40Z, ≈18:04Z]**, instante exacto **UNKNOWN** |
| Reinicio de componentes node | causa implicada | hecho **observado** (StartTime 17:30:42–17:30:50Z); un lote node previo (17:12Z) no interrumpió al hijo |
| Correlación de ~2 s | publicada como casi-causa | **hipótesis compatible, NO causalidad** — no se atribuye a opencode sin prueba suficiente |
| Mecanismo de terminación | "terminación externa" | **UNKNOWN**: acreditado solo que el árbol desapareció sin cierre normal ni excepción registrada; la ausencia de stderr/crash **no demuestra por sí sola** una eliminación externa |

## 3. Pendientes — reclasificados

- **Resultados forward:** 182 aptas × 3 horizontes − 351 resueltos = **195
  resultados forward pendientes**. Son resolución de trayectorias, **NO
  operaciones ni posiciones**. Resueltos por horizonte: 5m 182, 15m 150,
  60m 19.
- **Trabajos operativos:** 19 filas = **19 `observation_id` únicos, 0
  duplicados, 0 actualizaciones**: 1 decisión abrió y cerró una posición
  real (la entrada); 18 rechazos por capacidad **no abrieron posición**. Las
  filas no se convierten en posiciones.
- **Contabilidad:** 1 registro con `contabilidad_funding_estado=PENDIENTE`
  (espera contable sin iniciar); funding UNKNOWN.

## 4. Descartes — reconciliados (no eran inconsistencia)

Del campo **`motivos`** (plural) de `observaciones.jsonl`:

| Métrica | Valor |
|---|---|
| Observaciones descartadas **únicas** | **36** |
| Etiquetas por motivo | `dato_obsoleto_flujo` **23**, `flujo_ventana_incompleta` **20**, `dato_obsoleto_libro` **2** → total **45** |
| Con motivos solapados (≥2 motivos) | **9** (27 × 1 + 9 × 2 = 45) |
| Filas realmente sin motivo | **0** |
| Coincide con el panel del monitor | ✔ |

**45 etiquetas sobre 36 observaciones es coherente**, no una inconsistencia;
no queda ningún UNKNOWN en los descartes.

## 5. Estado vigente tras la rectificación

El cierre por incidente (2026-11-15) sigue siendo el veredicto histórico; con
esta rectificación el estado vigente es: ventana **INTERRUMPIDA**, captura
íntegra, settle/funding/cierre truncados, replay **LIMITACION (3)** vigente,
**sin medición económica**, `run_id` consumido. Los errores corregidos aquí
eran de **narrativa y atribución**, no de datos fuente: el dataset y el replay
no cambian.
