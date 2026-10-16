# Protocolo prospectivo — preparacion (NO ejecutado)

Version: `PROSPECTIVE-PROTOCOL-V1` (2026-10-17, preparacion
previa a adquirir datos; ejecucion NO autorizada por este
documento). Cubre la ventana de evaluacion futura, separada
del desarrollo. Reajustar sobre la ventana de evaluacion:
PROHIBIDO.

Bloqueador actual: NINGUNA hipotesis es elegible hoy
(matriz causal `docs/OFFLINE_EVAL_CAUSAL_AUDIT_V2.md`: H1/H3
mecanica causal pero seleccion retrospectiva sin
disponibilidad live; H2 insuficiente + convencion no-fade;
rebote sin definir; costes supuestos; ventana no pristina).
Este protocolo fija las condiciones que levantarian el
bloqueo. No promete que muestra alguna demostrara
rentabilidad.

## 1. Hipotesis elegibles y reglas (congeladas pre-datos)

- Elegibles candidatas (solo si cumplen §8): H1 continuacion
  alcista LONG (`continuation`/H1-v1) y H3 continuacion
  bajista SHORT (`bearish-continuation`/H3-v1), con mapping
  APROBADO (version `MAP-APPROVED-v1` pendiente de aprobacion
  humana; hasta entonces rige `MAP-CANDIDATE-v1` NO aprobado
  y nada es elegible).
- Reglas congeladas: motor `backtest-offline/v4.2` (o version
  fijada aqui antes de empezar), runner por grupo,
  `max_concurrent=1` intra-celda, entrada siguiente-open,
  stop 0.5% gap-first (placeholder declarado), salida
  horizonte 1h, nocional fijo $1000 @1x, escalas 1x/2x/3x,
  calendarios funding realizados pinned por simbolo.
- H2 legs: solo descriptivas (n esperado insuficiente);
  rebote: excluido hasta definicion bounce aprobada.
  H3 jamas redefinido como recuperacion; direccion jamas
  elegida por rendimiento posterior.

## 2. Universo y seleccion sin mirar futuro

- Universo pre-registrado: BTCUSDT/ETHUSDT/SOLUSDT 15m
  (o lista fijada con criterios de inclusion antes del
  primer dato: liquidez, continuidad de klines, calendario
  funding disponible).
- Detectores: definiciones P1-11C versionadas + prueba de
  disponibilidad en vivo (formacion computable en streaming
  al `close_time`; query != tradable declarado con
  medicion de latencia de formacion).
- Corte/purga pre-comprometidos: `cutoff_ms` + `horizon_ms`
  fijados antes de adquirir; purga de ventanas dev que
  crucen el corte (harness, motor intacto); sin embargo
  mas alla de la purga (declarado).
- Seleccion ciega: eventos admitidos = salida mecanica del
  detector + purga; sin filtrado por resultado, sin
  re-mapeo tras ver outcomes.

## 3. Datos y costes necesarios

- Velas cerradas con `close_time` intacto (cadena
  verificada, 0 violaciones exigidas; si hay huecos,
  gap-first y reporte, nunca interpolacion).
- Calendario funding REALIZADO venue por simbolo cubriendo
  TODA la ventana (sin cobertura → posicion UNKNOWN, nunca
  cero; 8 UNKNOWN de V1 no repetibles como aceptables sin
  justificacion).
- Costes: tier de comision del venue documentado para la
  cuenta de referencia (o escenarios maker/taker/BNB
  pre-fijados con fuente oficial); spread/slippage SOLO si
  hay historial venue de profundidad (si no: UNKNOWN y
  analisis de sensibilidad, nunca "medido").
- IDs originales + `available_at` conservados por operacion
  (paquete §5 del manifiesto como plantilla).

## 4. Duracion/cobertura minima y horizontes

- Ventana forward NUEVA, jamas resumida antes del primer
  replay (pristina): minimo 30 dias de 15m trio
  (o justificacion de potencia con N esperado >= 100
  eventos admitidos por familia elegible; H2 queda
  descriptiva por debajo de 30).
- Horizontes: salida 1h primaria (comparabilidad con V1);
  secundarios solo si se pre-registran (p. ej. 15m/4h) con
  correccion por multiplicidad declarada (sin p-hacking:
  criterio primario unico).
- Cobertura: >= 95% velas esperadas por simbolo o reporte
  de huecos con tratamiento gap-first auditable.

## 5. Criterio de entrada/salida y exposicion

- Entrada/salida/stop del §1, sin cambios intra-ventana.
- Exposicion: single-position por celda como en V1
  (comparabilidad) + reporte de solapes intra y CROSS-celda
  (simultaneidad observada, P&L simultaneo NO reclamado
  sin modelo de cartera). Competencia capital/exposicion:
  reportada, no optimizada.

## 6. Errores, ausencias y exclusiones

- Velas ausentes/tardias: evento excluido de estadistica
  (contado, nunca imputado); `formation_gap` fuera de
  estadistica, nunca borrado.
- Funding sin cobertura: UNKNOWN Zukunft (nunca 0).
- Costes sin medir: supuestos versionados + sensibilidad;
  prohibido presentar supuesto como medido.
- Fallos de adquisicion: ventana extendida o evento
  abortado pre-registrado (criterio escrito antes),
  nunca re-corte post-hoc.

## 7. Metricas, baseline y aceptacion/rechazo

- Metricas primarias: E[net]R y total_net_realized @1x por
  celda elegible + s* (breakeven) + E[net] @2x/@3x
  (fragilidad). Realizadas separadas de abiertas; pooled
  solo referencia aritmetica (no cartera, no predictivo).
- Baseline comparable pre-fijado: `TIME-PLACEBO-v1` (§5 del
  doc de costes): misma cadencia, mismos costes,
  seed fijado; aceptacion = E[net]R H1/H3 supera al
  placebo fuera del intervalo de su distribucion con
  costes 1x Y sobrevive a 2x (criterio de robustez;
  fallarlo = RECHAZO aunque @1x sea positivo).
- Rechazo: s* < 2 en todas las celdas elegibles, o
  placebo indistinguible, o cobertura < minima, o
  violacion causal (entry < available), o reajuste
  detectado → hipotesis RECHAZADA para operacion
  (sigue descriptiva).

## 8. Separacion desarrollo/evaluacion + congelamiento

- Desarrollo (mapping, reglas, codigo) CONGELADO antes del
  primer dato forward (hash de codigo + configs
  registrados). La ventana de evaluacion no se usa para
  nada salvo el replay unico pre-registrado.
- Un solo replay por celda (re-ejecuciones solo por bug
  demostrado, con informe y version nueva, nunca por
  resultado). Thresholds intactos durante la evaluacion.

## 9. Siguiente accion exacta (no ejecutada)

1. Aprobacion humana del mapping (`MAP-APPROVED-v1`) o
   constancia de que sigue NO aprobado (bloqueo vigente).
2. Prueba de disponibilidad live del detector (formacion
   en streaming) en ventana corta autorizada.
3. Autorizacion separada para adquirir la ventana forward
   pristina (sin trading, solo datos publicos) con este
   protocolo como contrato.
4. Replay unico + informe contra criterios §7.

Sin estos pasos, NADA avanza gates (G9/P2/P3 intactos).
