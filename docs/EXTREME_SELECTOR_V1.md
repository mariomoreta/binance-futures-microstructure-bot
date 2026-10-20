# Selector de movimientos extremos — candidato SELECTOR-EXTREME-V1

Version: `SELECTOR-EXTREME-V1` (2026-10-17, sin corridas, sin forward,
sin optimizar umbrales). Estado: CANDIDATO (sin aprobacion de
metodologia, sin validacion, no es senal). Ranking = prioridad de
investigacion (ranking != entrada). Implementacion:
`src/microstructure_probe/extreme_selector.py`; pruebas:
`tests/test_extreme_selector.py` (9/9 con fixtures).

## 1. Auditoria previa (reutilizar; delta minimo)

| Componente | Reutilizado | Veredicto de auditoria |
|---|---|---|
| `discovery.py` | Dimensiones de elegibilidad (PERPETUAL/TRADING/USDT/floor) + tableros bilaterales (gainers/losers) + score determinista | LIVE-REST sin historial: snapshots REPLACE sin as-of retenido; universo/ranking en T pasado = UNKNOWN; mecanismo con provider inyectado + fixtures |
| `universe_manager.py` | Proteccion CORE + vocabulario de ciclo (dwell/cooldown) como etiquetas | Sin conexiones gestionadas en vivo aqui; sin replay |
| `classifier.py` v0.1.0 | Vocabulario de estados como lenguaje de escenarios | NO replayable offline: exige rows live (flow/book/OI/VWAP) inexistentes en historico; umbrales HYPOTHESIS intactos |
| `opportunity.py` v0.1.0 | Ciclo WATCH/DESCARTADO + ranking!=entrada + disciplina de frescura | NO replayable offline (mismo motivo); contrato honrado, familia EXTREME_MOVE_RESEARCH referenciada |
| `events.py formation_features` | UNICA entrada historica: todo input del selector es campo prefijo-causal suyo (incl. contexto BTC at/before T, volumen propio, gap) | Reutilizado verbatim; censo CENSUS-V1 lo demuestra 9320/9320 admitidas |

Delta entregado: solo `extreme_selector.py` (funciones puras
`select`/`rank_board`/`input_coverage`) + tests + este documento.
Ningun motor existente fue modificado.

## 2. Reglas candidatas (versionadas ANTES de evaluar)

Pisos `move_24h_min=0.05` / `move_recent_1h_min=0.005`: INHERITED-P1-11C-v1
(HYPOTHESIS, sin validar). `min_bars_for_volume=5`: IMPL reversible.
`ranking_weights` y `volume_percentile_min=0.5`: NEW-HYPOTHESIS (requieren
revision; jamas ajustados contra resultados).
Movimiento 24h separado del reciente 1h y de su ancla (anchor time
registrado en features); volumen relativo al propio token (percentil
trailing, no nominal crudo); liquidez = UNKNOWN (sin historial de
profundidad); cobertura (gap) y frescura (close_time) exigidas; BTC como
contexto sincronizado at/before T y como activo elegible con las mismas
reglas; capitalizacion = UNKNOWN siempre (prohibido "low cap" por proxy);
sin RSI/ATR ni indicadores nuevos (indisponibles -> injustificables).
Veredicto: WATCH (lado + escenarios + confirmaciones pendientes) o
DESCARTADO (motivo); tableros separados alcista/bajista.

## 3. Cobertura real del dataset (sin extrapolar)

Matriz por serie (trio 15m x2879, trio+MINA/NMR/ORCA 1h x719):
move_24h/move_1h/range/volumen-propio/notional/cobertura/frescura/BTC-ctx =
disponibles; liquidez/universo-historico/mcap/flow-book-OI-live = UNKNOWN.
Consecuencia: las 9320 detecciones del censo son como maximo
PARTIAL-input (100%); decisiones full-input imposibles en este dataset;
nada del trio se extrapola al universo Binance.

## 4. Contrato de adquisicion faltante (UNIVERSE-HISTORY-ACQ-V1, no ejecutado)

Para levantar el UNKNOWN sin inventar cobertura: persistir por scan
(`universe_snapshots`: as_of, symbol, eligible, exclusion_reasons,
change_24h_pct, quote_volume_24h, rank, dynamic_slots, state-votes;
`universe_events` ya existe para promociones) con retencion acotada,
jamas backfill retrospectivo. Ranking historico solo desde su primera
persistencia; lo anterior queda UNKNOWN para siempre. Sin autorizacion
de sesiones nuevas, este contrato queda preparado, no iniciado.

## 5. Continuacion propuesta (SOLO DOCUMENTADA; nada ejecutado aqui)

Secuencia causal propuesta, sin iniciar corridas nuevas ni cambiar
estrategia/umbrales/costes:

1. **Selector de token extremo reutilizando capacidades actuales.** Reusar
   `extreme_selector.py` (funciones puras) + `discovery.py`/`universe.py`
   para seleccionar, EN T y con `available_at` conocible, el token candidato.
   Requiere levantar el UNKNOWN de universo/ranking historico
   (`UNIVERSE-HISTORY-ACQ-V1`, ver §4). NO se aprueban umbrales nuevos.
2. **Decision versionada con evidencia conocida en T.** Emitir una decision
   trazable por instante T, con la evidencia exactamente conocible en T (sin
   informacion posterior). Versionada antes de evaluar.
3. **Paper prospectivo** (Etapa 5, NO autorizado aqui): registrar decisiones y
   sus resultados hacia adelante, sin ejecucion real ni credenciales.
4. **Evaluacion posterior** de la esperanza ajustada al riesgo, comparando
   contra placebo y contra el baseline, no contra si misma.

Restricciones: sin Binance, sin monitor, sin paper prospectivo, sin ordenes,
sin optimizacion automatica, sin cambios de estrategia/umbrales/costes/motor
economico. Esta seccion es una PROPUESTA documentada; no declara nada
evaluado ni implementado.
