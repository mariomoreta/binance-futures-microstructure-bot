# Entradas, retrocesos y salidas intradia — plan de investigacion v1

Estado: DISENO PROPUESTO. Documentacion autorizada el 2026-10-14.
Prioridad vigente: cerrar O1 bot + Dashboard V2; este estudio no cambia control,
estrategia, riesgo, ordenes ni dependencias de O1. Base revisada:
e887287d6dee00c80687ff34d432a34caeef5b63. La implementacion se pedira despues
con un prompt acotado y sera revisada independientemente.

## 1. Pregunta y objetivo
Que informacion observable permite distinguir continuacion, pausa con recuperacion
y deterioro, y como afectan distintas entradas/salidas al resultado neto y al riesgo?
No buscamos un temporizador universal ni el promedio solo de las operaciones ganadoras.
El maximo recorrido de un dia es una etiqueta retrospectiva, nunca una entrada causal.
H1 = continuacion alcista; H2 = agotamiento/reversion, incluida variante de rebote;
H3 = continuacion bajista, nunca rebote de perdedoras. Mantener familias/versiones.

## 2. Punto de partida y limites
Ver INTRADAY_EXTREME_MOVES_PILOT_20261014.md y evidencia del manifiesto.
Piloto: 10 extremos de 24h, 40 alertas ilustrativas, sin costes/fills ni OOS.
Seleccion con ranking final => sesgo retrospectivo; eventos se solapan y no son
independientes. No acredita diez low-caps ni probabilidades operativas.
2% retorno15m/3xRVOL, 1% retroceso, 2%/-1% barreras, 60min y 240min son constantes
ilustrativas del piloto, NO umbrales aprobados. La siguiente version debe congelar
reglas antes de observar sus resultados OOS. No calibrar sobre el piloto y llamarlo OOS.

## 3. Cohorte y datos
- Universe snapshot por instante T: contratos cripto perpetuos USDT elegibles entonces.
  Si no existe universo historico, etiquetar alcance y sesgo, no reconstruirlo con los
  supervivientes actuales. Seleccionar por informacion disponible en T, no por top final.
- Incluir eventos con y sin alerta y controles emparejados por simbolo/horario/regimen,
  volatilidad y actividad previa. Congelar universo, ventanas y reglas de exclusiones.
- Capitalizacion: fuente, identidad del activo (no ticker solo), circulante, moneda,
  fecha observada/disponible. UNKNOWN excluye un subgrupo low-cap certificado,
  pero puede permanecer en analisis general rotulado. No equiparar nominal Futures,
  volumen spot, capitalizacion y profundidad ejecutable.
- Precio/volumen/flujo: conservar venue, trade vs mark, unidad, horizonte, as_of,
  available_at y metodo. OI y noticias sin latencia acreditada no son confirmaciones causales.
- Spread/profundidad historicos faltantes: UNKNOWN. Un libro actual no recrea fills pasados.
- Cada barra debe estar cerrada y disponible al decidir. Features de rolling24 deben
  anclar el denominador: ticker rolling no equivale al retorno de una ventana de velas.
- Horizonte maximo de estudio 24h; warmup y seguimiento posterior fuera de la ventana
  de deteccion deben solicitarse aparte. Sin futuro suficiente, outcome censurado.

## 4. Historia causal del evento (propuesta)
DETECTED -> EXPANDING -> PULLBACK -> RECLAIMED | DETERIORATING | CENSORED.
Es vocabulario de estudio propuesto, no reemplaza classifier/opportunity ni sus estados.
Guardar: detection_T, entrada candidata, running_extreme conocido, profundidad y
duracion del retroceso, recuperacion del nivel, invalidacion y fin de seguimiento.
running_extreme usa datos <=T; peak_final/time_to_MFE usan futuro y viven SOLO en outcomes.
No recuperar un nivel dentro de 60min no demuestra una reversion estructural.

Features candidatas:
- retorno/velocidad/aceleracion y retorno relativo BTC alineados at-or-before T;
- quote volume absoluto + RVOL robusto + denominador/ventana/sample count;
- agresion taker y respuesta del precio (volumen por si solo no identifica direccion);
- volatilidad, VWAP con ancla, estructura y OI con unidades/frescura;
- spread/profundidad, cuando exista historia disponible, nunca inventados.
Reutilizar motores existentes; medir cobertura antes de proponer indicadores nuevos.
Probar floors de volumen/liquidez: RVOL grande puede tener denominador casi cero.

## 5. Comparacion de entradas
A: continuacion tras confirmacion de ruptura del contrato H1/H3.
B: esperar retroceso y recuperacion del nivel conocido; direccion segun familia.
C: baseline reproducible con mismos eventos/riesgo/ventana; controles sin alerta aparte.
Congelar antes de OOS: definicion de nivel, confirmacion, trigger, invalidez, TTL y
latencia/fill. Las variantes que no entran se conservan como missed/expired, no se borran.
H2 se prueba por separado; no combinar short de continuacion y short de agotamiento.
Comparar primero entradas con la MISMA salida/riesgo; despues salidas con la MISMA
entrada. Evitar atribuir una mejora a un parametro cuando cambiaron varias piezas.

## 6. Comparacion de salidas
Baselines: horizontes fijos 15/30/60/120/240min, y 24h si hay cobertura.
Candidatas: invalidacion estructural; proteccion del avance; retroceso desde extremo
conocido; falta de progreso; deterioro de evidencia. Valores concretos PENDING.
Siempre distinguir PnL desde entrada y drawdown desde mejor precio conocido.
Conservar first-hit favorable/adverso, orden de barreras, MFE/MAE, tiempo al extremo,
duracion/exposicion, costes ejecutados y salida hipotetica de abiertas.
Si stop/target comparten vela OHLC sin secuencia, reportar ambiguedad o politica
conservadora versionada. Cierres de 5m no son fills a esos niveles.
Funding: usar contrato vigente del motor y separar completitud/observado/proxy/fallback;
neto con funding incompleto debe etiquetarse y excluirse del subgrupo validado.

## 7. Diseno de evaluacion
- Reutilizar backtest_offline/run_family_evaluation; no segundo motor.
- Dev/OOS temporal y agrupacion por evento/simbolo/fecha; tratar solapamiento y leakage
  entre formacion/holding/outcome mediante purga/embargo explicitamente definidos.
- Costes de venue y ejecucion medidos cuando disponibles; si asumidos, rotularlos.
  Sensibilidad 1x/2x/3x y cobertura de funding/fees/spread/slippage/latencia.
- Reportar todos eventos: entrados, descartados por causa, expirados y censurados.
- Tiempos: cuantiles y distribuciones condicionadas con n/coverage, no solo media.
  Perdida que ocurre primero es resultado competidor, no censura aleatoria que se elimina.
  Incluir fallidos y sin tocar barreras en la comparacion; intervalos de incertidumbre
  agrupados por simbolo/dia para no tratar alertas solapadas como muestras independientes.
- Registrar numero de variantes ensayadas; seleccion por dev, OOS intacto.
- Resultado: expectancy neta, distribucion/perdidas/colas, drawdown, exposicion,
  sensibilidad y estabilidad por regimen. Comparar con baseline y costes computacionales.
  Un resultado negativo tambien cierra una hipotesis; no ajustar hasta que parezca rentable.

## 8. Aceptacion del siguiente paquete (documentacion -> investigacion reproducible)
1. Identidad/hash de datos y reglas; universo/availability y exclusiones auditables.
2. Reproduccion del piloto desde evidencia versionada con mismos 10 summaries/40 alertas.
3. Fixture causal: agregar futuro no cambia decisiones/features anteriores; extremo
   final nunca aparece en features. Barriers intrabar y censura probados.
4. Corrida separada por familia/variante; manifiesto con cobertura, costes y descartes.
5. Comparacion A/B/C, fallos incluidos; OOS/solapamientos declarados; conclusion
   aceptar/rechazar/inconcluso con evidencia. No exigir resultado positivo.
6. Propuesta V2 read-only de INTRADAY_V2_RESEARCH_CONTRACT.md; UI solo despues de datos.
No promociona SUCCESS_GATES ni habilita ejecucion por existir este documento.
