# Traza de captura pública public-pilot-1h-20261106a (resumen antes/despues)

run_id: public-pilot-1h-20261106a
SHA efectiva: f122fbc898821f4a985d071d5fd6efc1f469d9c4
Directorio: C:\proyectos\binance-futures-data\public-pilot-1h-20261106a (fuera de Git)

Configuracion ejecutada:
  mode=public, activar_publico=true
  rest_base=https://fapi.binance.com
  ws_public_base=wss://fstream.binance.com/public
  ws_market_base=wss://fstream.binance.com/market
  duration_seconds=3600, settle_seconds=4200
  selection_seconds=300, cycle_seconds=300, decision_delay_seconds=0
  max_symbols=20, max_candidates=12, max_comparators=8
  max_data_age_ms=5000, capture_protocol_version=3
  max_http_attempts=2000, max_http_weight=5000, max_http_retries=50
  max_ws_reconnects=20, max_messages=5000000, max_bytes=134217728
  horizons=5m/15m/60m, max_observations=20000

Inicio del periodo de seguimiento: 2026-11-06T05:17:36.629Z (T0=1793942256629)
Fin de captura: 2026-11-06T07:14:10.655Z (duracion)
Fin de settle: 1793950056629

Suscripciones/feeds acreditadas:
  feeds: market (depth20@100ms) + public (aggTrade), 2 conexiones simultaneas
  20 simbolos seguidos (candidatos + comparadores, research-selector-v2)
  primer evento de flujo por simbolo despues de la suscripcion (no se precarga historia)

Primera recepcion por fuente: evento_ms <= reloj en cada publicacion (protocolo v3, 0 fechas futuras)
Corte nominal: T0 + 60 s (ventana de flujo 1m). Si la ventana observada era < 60 s, el corte no se consumo.
Espera maxima acotada: WARMUP_MAX_WAIT_MS = 60 s. Al agotarse, se evalua con motivo explícito del motor.

Corte nominal y evaluacion efectiva:
  Ciclo 1: decision_ms = T0 + 62000 (cobertura_completa)
  Ciclos 2-12: decision_ms = T0 + k*300000 (espera_maxima_agotada para simbolos sin ventana completa)
  3 x N observaciones por ciclo: 12 ciclos x 20 simbolos = 240 esperadas, 216 escritas (simbolos rotados entran/salen)

Resultados:
  observaciones: 216 (168 aptas, 48 descartadas)
  resultados: 504 (5m: 168 resueltos, 15m: 168 resueltos, 60m: 168 resueltos)
  pendientes: 0 (todos resueltos en settle)

Motivos de descarte (explícitos, nada falso apto):
  dato_obsoleto_flujo: 47
  dato_obsoleto_libro: 4
  flujo_ventana_incompleta: 1

Consumo real vs limites:
  HTTP: attempts=641/2000, weight=1109/5000, retries=0/50, blocked=false
  WS: connections_total=20, messages=960114/5000000, reconnects=0/20
  Almacenamiento: 5,225,620 / 134,217,728 bytes (3.9%)

Causa de parada: duracion (captura agotada, settle completado)
Codigo de salida: 0
Limpieza: feeds WS cancelados, recorder drenado, manifiesto y resumen escritos desde lo persistido

Evidencia de archivos (manifiesto.json):
  observaciones.jsonl: sha256=43cc26e529b38e97494217d3015f4a42f826bf515f0df34898d9a764a54a1165
  resumen.json: sha256=cf03be4dffb9930ae81d0bd157dcbb1de2889cc8a3d3679d473d75def0c5a59b

Comparacion descriptiva con public-pilot-1h-20261105a:
  no se atribuye toda diferencia al arreglo; son momentos de mercado distintos.
  No se presentan retornos brutos como P&L ni se declara ventaja economica.
