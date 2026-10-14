# V2 — propuesta de lectura de episodios intradia v1
Estado: PROPUESTO, no implementado; no nuevo endpoint activo ni migracion.
Depende del estudio INTRADAY_ENTRY_EXIT_STUDY_PLAN.md; no bloquea cierre O1.
Python produce features/decisiones/outcomes; V2 presenta. Ninguna decision sale del DOM.

## Envolvente propuesta
schema_version, study_id, study_version, dataset_id, input_hash, engine_version,
implementation_revision, generated_at, cutoff_ms, selection_method, in_sample,
coverage, exclusions, warnings y capability.
Por registro: event_id, run_id, symbol, family, rules_version, event_time_ms,
available_at_ms, as_of_ms, source/price_source, quality y cohort_id.
Campos numericos desconocidos: null + quality_reason. Cero sigue siendo un valor real.
Timestamps UTC ms; moneda/unit explicitas (USDT notional != token quantity).

## Separacion imprescindible
features_at_T: retornos, RVOL y su denominador, flujo, volatilidad, VWAP,
running_extreme, edad del impulso, retroceso actual y evidencia disponible.
outcomes_after_T: first-hit, MFE/MAE/time_to_extreme, recuperacion, retorno por horizonte,
censura y precios/costes posteriores. Nunca alimentar entrada con outcomes.
comparables: metodo de seleccion SOLO con features, n independiente, fechas/dev/OOS,
coverage, cuantiles con incertidumbre y eventos competidores. No probabilidad de
ganancia desde un softmax ni tiempos historicos presentados como cuenta regresiva.

## Presentacion futura
- Detalle token: timeline deteccion/expansion/pausa/recuperacion/invalidacion.
- Precio y volumen con misma escala temporal, fuente y ancla; alertas como eventos,
  sin confundirlas con fills. Mostrar volumen absoluto y denominador de RVOL.
- Tarjeta comparables: n, definicion de cohorte, tiempos favorables/adversos,
  profundidad retroceso y cobertura/censura. Sin comparables: UNKNOWN.
- Research/Backtest: A/B/C, neto y costes, descartes, version y segmento.
- Posiciones: requiere el gestor/riesgo real o paper existente; este estudio no crea
  botones de compra/venta ni targets operativos.

## Compatibilidad y QA posteriores
Lectura con adaptador existente y snapshots versionados; ausencia/incompatibilidad
=> unavailable/UNKNOWN. Validar tablas/columnas y versiones, sin migrar en GET.
Pruebas de null/zero, futuro, fuente/horizonte, coverage parcial y snapshots estables.
Si hay cambios visuales: capturas frescas desktop/mobile, interacciones y errores;
HTTP200/tests no sustituyen QA visual. Esta entrega documental: VISUAL NOT APPLICABLE.
