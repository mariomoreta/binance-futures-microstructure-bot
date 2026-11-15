# Cierre por incidente — ventana `exp-v2-ventana-3-20261115a` — INTERRUMPIDA

**Fecha:** 2026-11-15 · **Estado:** **EJECUTADA PARCIALMENTE, INTERRUMPIDA POR
INCIDENTE EXTERNO** · **Resultado global:** sin medición económica; dataset
parcial preservado.

**Alcance de esta autorización.** La autorización humana del 2026-11-15 cubría
**una única ejecución** (`exp-v2-ventana-3-20261115a`): adquisición pública,
simulación, persistencia, resolución, espera contable, replay offline y cierre.
**No** autorizaba órdenes reales, cuentas, claves, ventanas adicionales ni
relanzamientos. Tras la interrupción, la decisión humana posterior acotó el
cierre: cerrar la ventana como **INTERRUMPIDA POR INCIDENTE**, ejecutar el
replay offline v2 **solo sobre lo persistido** en derivados separados, y
publicar. **No** autoriza relanzamientos ni un `run_id` nuevo; el `run_id`
`exp-v2-ventana-3-20261115a` **queda consumido** y no se reutiliza.

## 1. Incidente (qué pasó, con evidencia)

| Hora (UTC) | Evento observado |
|---|---|
| 16:25:43.500 | Lanzamiento único (preflight completo; ver §2) |
| 17:25:43.500 | **Captura completa** (3600 s, terminada por duración, como estaba previsto) |
| 17:30:40 | Última escritura del hijo (`estado.json`, fase settle/resolución en curso) |
| 17:30:42 | Muerte del árbol de procesos (envoltorio → lanzador → hijo), sin cierre |
| — | Fin de settle previsto era 18:35:43Z; la espera contable y el cierre nunca llegaron |

**Causa final:** terminación **externa** del árbol de procesos, coincidente
con el reinicio en bloque de procesos `node` (componentes de opencode) a las
13:30:42–13:30:50 locales (= 17:30:42–17:30:50Z) — correlación de ~2 s con la
última escritura del hijo. El **mecanismo exacto de eliminación queda
UNKNOWN**. Un reinicio previo de `node` (13:12 local) no interrumpió al hijo.

**Evidencia negativa (lo que NO fue):** sin reinicio del sistema
(`LastBootUpTime` 2026-11-11; sin eventos System 1074/6006/6008/41 en 3 h);
sin eventos de crash de python (Application 1000/1001/1002, 3 h);
`stderr.log` y `lanzador_stderr.txt` con **0 bytes** (ninguna excepción
volcada). **Código de salida observado: UNKNOWN** — no existe `cierre.json`,
`exit_code.txt` ni `estado_lanzador.json`; **no se fabricaron
retrospectivamente**.

**Integridad de lo persistido:** 12 ficheros inventariados con SHA-256
(`inventario_completo.json` en el directorio de derivados). Todas las líneas
JSONL terminan con `\n` y su última línea es JSON válido: **sin escrituras
partidas**.

## 2. Preflight (lo que SÍ quedó acreditado antes del lanzamiento)

- Rama `research/universe-liquidez-v1`; HEAD = remoto =
  **`bc635e7d4a34c82f794ad7a9d76f78960f9d0794`**, 0/0 divergencia, sin commits
  posteriores; el código ejecutable (lanzador, piloto, adaptador, `src`)
  **idéntico** al commit `12024146` donde se validó el presupuesto.
- Sin otro piloto activo; `run_id` y directorio libres.
- Revalidación `--budget-only` **sin red** en ruta de preparación separada:
  código 0, **gate 13/13**, intentos 1 334, peso 3 752, reintentos 50,
  reservado 56 363 648 B, cuerpos 4 320 000 B — idéntico al presupuesto
  vigente, **ningún techo ampliado**.
- Comando literal de [PROPUESTA](../exp-v2-ventana-3-20261115a-propuesta/PROPUESTA.md)
  §7 sin `--budget-only`, con `--work-timeout-seconds 40200` y
  `--shutdown-grace-seconds 300`.

## 3. Capa A — Técnica (limitada a lo observado)

| Elemento | Observado |
|---|---|
| SHA ejecutado | `bc635e7` (local == remoto) |
| Captura | **COMPLETA**: 3600 s, 12/12 ciclos, 20 símbolos, feeds `/market` y `/public` conectados (1 conexión c/u durante la captura) |
| Frescura (observada al inicio y al corte del panel) | edades de libro 30–840 ms; flujo 160–4 600 ms, dentro de `max-data-age-ms 5000` |
| Settle/resolución | **INTERRUMPIDA** ~5 min después del fin de captura: 351 resultados escritos (5m 182 · 15m 150 · 60m 19); pendientes al corte no cuantificables |
| Adquisición de funding | **NO INICIADA** (`funding_adquisicion.jsonl` 0 B) → funding **UNKNOWN**, nunca cero |
| Espera contable | **NO INICIADA** (195 operativos y 1 contabilidad pendientes al corte) |
| Consumos al corte (panel del monitor) | 394 intentos HTTP (techo 2 000), peso 862 (techo 5 000), 0 reintentos, 0 bloqueos; almacenamiento contabilizado 53 587 575 B de 134 217 728 B |
| Mensajes WS finales | **UNKNOWN** (el resumen del hijo no llegó a escribirse; solo hay conteos parciales del panel en vivo) |
| Código real del hijo | **UNKNOWN** (sin `exit_code.txt`; no se infiere ni se fabrica) |
| Veredicto del lanzador | **NO PRODUCIDO** (sin `cierre.json`) |

## 4. Capa B — Calidad (embudo parcial)

| Métrica | Observado |
|---|---|
| Ciclos completados | 12/12 (selección y decisión cada 300 s) |
| Última selección | 12 candidatos (mov. 24 h de −45,19 % a +38,12 %) + 8 comparadores (−13,75 % a −0,55 %) |
| Observaciones | **218** emitidas: **182 aptas** (`observada`) + **36 descartadas** |
| Motivos de descarte | en el fichero quedan `motivo = null` en las 36; el panel del monitor declaró `dato_obsoleto_flujo` 23, `flujo_ventana_incompleta` 20, `dato_obsoleto_libro` 2 (45 eventos, no reconciliable con las 36 del fichero) → la atribución completa queda **UNKNOWN** |
| Resultados | 351 resueltos (5m 182, 15m 150, 60m 19), todos `neto_estado=UNKNOWN` (la resolución de 15m/60m quedó incompleta por la interrupción) |
| Comparación candidato/comparador | **INSUFICIENTE** (sin resolución completa ni operaciones comparables) |

## 5. Capa C — Económica exploratoria (parcial, sin medición válida)

| Métrica | Observado |
|---|---|
| Filas operativas | **19**: 1 `ENTRADA_EJECUTADA` + 18 `RECHAZADA_CAPACIDAD` (capacidad compartida de 1 posición) |
| Entrada única | `0GUSDT` SHORT (candidate), decisión 17:07:47Z, fill 17:08:00Z @ 0,1307, qty 7 651,11; **salida por stop ejecutada** 17:36:40Z @ 0,13135 (stop_px 0,13155) |
| Cuenta del motor (sin funding) | `gross_pnl` −5,00; fees 1,0025; spread/slip 0,6015; `net_pnl` **−6,604** |
| Estado del neto | `CONDICIONADO_SIN_FUNDING_COMPLETO` — funding `null` (**UNKNOWN, no cero**); contabilidad `PENDIENTE` |
| Netos | COMPLETO `n = 0`; CONDICIONADO `n = 1`; UNKNOWN `n = 18`; abiertas al final 0 |
| **Medición económica** | **NO HAY**: una sola operación, sin funding, sin resolución completa y sin replay acreditado. **No se reporta P&L**; la cifra del motor es una cuenta intermedia sin liquidaciones de funding, presentada tal cual y sin atribuirle validez económica |

**La regla sigue siendo una baseline de continuación.** Este incidente no
aporta evidencia a favor ni en contra de la hipótesis económica.

## 6. Replay offline v2 sobre lo persistido — LIMITACION (3)

Ejecutado `scripts/research_operativo_replay.py` (`research-operativo-replay/v2`)
en **solo lectura** sobre el dataset original, informe en derivados separados:

| Campo | Valor |
|---|---|
| Código de salida | **3** |
| Veredicto | **LIMITACION** |
| Motivos | `manifiesto_ausente` (sin manifiesto no hay configuración congelada ni hashes de integridad) → `config_operativa_ausente` (sin configuración congelada no se reconstruye con el mismo contrato y **no se usan valores por defecto**) |
| Denominador | 182 aptas → 182 comparadas → **182 limitadas**; 0 coincidentes, 0 diferentes; **nada desaparece del denominador sin quedar limitado con motivo** |
| Procedencia / config acreditadas | **false / false** |
| Interpretación | LIMITACIÓN **coherente con el incidente**: el lanzador murió antes de publicar `manifiesto.json` (presente en la ventana 2); el replay v2 se niega a reconstruir sin configuración congelada e integridad acreditada y **no inventa nada** |

## 7. Límites reales de este cierre

- La ventana quedó **sin fases**: settle incompleto (resolución 15m/60m
  trunca), funding sin adquirir, espera contable sin abrir, cierre del
  lanzador sin producir.
- `exit_code` del hijo y veredicto del lanzador: **UNKNOWN / NO EXISTEN**.
- El replay **no puede** acreditar EQUIVALENTE ni DIFERENCIAS: sin
  manifiesto no hay configuración congelada; LIMITACION es el resultado
  correcto, no un fallo del replay.
- Motivos de descarte en el fichero sin atribución completa (UNKNOWN).
- Mensajes WS finales y pendientes de resolución al corte: UNKNOWN.
- Una sola operación sin funding **no evalúa** la regla ni la comparación por
  rol (INSUFICIENTE).
- El incidente se atribuye a terminación externa coincidente con el reinicio
  de componentes de opencode; el mecanismo exacto queda UNKNOWN.

## 8. Artefactos

- Dataset original (fuera de Git, **intacto**, solo lectura):
  `C:\proyectos\binance-futures-data\exp-v2-ventana-3-20261115a`
  (inventario + SHA-256 en `inventario_completo.json` de los derivados).
- Derivados separados:
  `C:\proyectos\binance-futures-data\exp-v2-ventana-3-20261115a-cierre-incidente`
  (`resumen.json`, `replay_informe.json`, `replay_ejecucion.txt`,
  `evidencia_incidente.json`, `inventario_completo.json`, copias de
  `estado.json`/`lanzador_comando.json`/`lanzador_pid.txt`,
  `hashes_derivados.json`).
- Evidencia compacta en el repo: este INFORME + `resumen.json` +
  `replay_informe.json` + `evidencia_incidente.json` + `hashes.json`.
- Ruta de la revalidación de presupuesto:
  `C:\proyectos\binance-futures-data\_presupuesto\exp-v2-ventana-3-20261115a-revalidacion-20261115`.
