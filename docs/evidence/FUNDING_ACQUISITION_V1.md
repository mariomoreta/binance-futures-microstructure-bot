# Funding realizado — contrato de adquisición V1 (FUNDING-CAL-v1)

Status: REALIZED venue data attached. Quoted/next estimates were never
fetched and never substitute settlements (engine `funding_estimated_bps`
stays null in every run of this task).

## Fuente oficial

- Venue: Binance USD-M Futures, endpoint público
  `GET https://fapi.binance.com/fapi/v1/fundingRate` (spot de la familia
  usada por el probe para clock sync y resto público; sin credenciales).
- Campos usados: `symbol`, `fundingTime` (liquidación realizada),
  `fundingRate` (tasa realizada). `markPrice`/`rateType` conservados en el
  crudo, no contabilizados.
- Documentación de referencia: Binance USD-M Futures market-data only
  (developers.binance.com inalcanzable desde este entorno; contratos
  verificados en vivo como en P1-05/P1-11B).

## Peticiones (3, carga trivial)

| Símbolo | URL (params) | Respuesta |
|---|---|---|
| BTCUSDT | `?symbol=BTCUSDT&startTime=1788816600000&endTime=1791406800000&limit=1000` | 200, 11351 B, sha256 `c67a2a68…41290db7` |
| ETHUSDT | `?symbol=ETHUSDT&...` (idem) | 200, 11263 B, sha256 `0b755aba…949a31f2` |
| SOLUSDT | `?symbol=SOLUSDT&...` (idem) | 200, 11177 B, sha256 `3db3ab2e…a00a25ad82` |

- Adquirido: 2026-10-16T05:30:00Z (UTC). Límite de peticiones: 3 GET
  (1/símbolo, `limit=1000` cubre la ventana en una sola página).
- Crudos completos: `C:\Users\adonm\AppData\Local\Temp\opencode\funding_<SYM>.json`
  (fuera de Git; hashes arriba para verificar re-adquisición).

## Cobertura e intervalo

- 90 liquidaciones/símbolo, `fundingTime` 1788825600004 → 1791388800000.
- Cadencia nominal 8h (mediana 28800000ms; min/max ±15ms por alineación de
  ms del venue). Sin huecos interiores: 90 puntos sobre 89 intervalos
  exactos. `interval_ms = 28800000` es cadencia NOMINAL informativa; la
  contabilidad usa cada liquidación con su timestamp y tasa (contrato v4.2).
- Cobertura vs velas trio 15m (1788816600000 → 1791406800000): la primera
  liquidación (…255600004) cae dentro de la primera vela; holdings con
  entrada anterior a la primera liquidación reportan `uncovered` en cabeza
  (UNKNOWN, jamás cero). Ningún holding termina tras la última liquidación
  con exposición no cubierta salvo `open_at_end` (marcas, sin ejecución).

## Artefactos versionados (en Git)

- `docs/evidence/FUNDING_CALENDAR_BTCUSDT_V1.json`
- `docs/evidence/FUNDING_CALENDAR_ETHUSDT_V1.json`
- `docs/evidence/FUNDING_CALENDAR_SOLUSDT_V1.json`
- Constructor: `scripts/build_funding_calendar.py` (offline, determinista;
  probado en `tests/test_eval_selection_calendar.py`).

## Qué NO contiene

- Sin tasa cotizada/próxima estimada (no sustituida, no almacenada).
- Sin spread/profundidad históricos (slippage declarado supuesto, no medido).
- Sin comisiones de cuenta (tier desconocido; supuesto versionado
  COST-ASSUME-v1 + sensibilidad 1x/2x/3x).
