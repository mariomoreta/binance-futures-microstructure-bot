# Diagnóstico de la corrida pública 1 h + 70 min

- **run_id:** `public-pilot-1h-20261105a`
- **Rama / base:** `research/universe-liquidity-v1` en `7916c49d5b49d5993a62901f2d2262d6231a153d`
- **Estado:** `corrida_interrumpida_o_cierre_no_acreditado`
- **Causa de parada:** `UNKNOWN` (no hay código de salida, ni logs de consumo, ni archivos de control de fin)
- **Proceso vivo:** No. Único Python activo: `market_stream_service.py` (puerto 8792, servicio ajeno, no se toca).

## Reconstrucción offline (solo lectura de archivos persistidos)

- Total líneas JSONL: 458
- Ciclos de selección completados: 12 (de 12 esperados)
- Observaciones totales: 240 (aptas: 128, descartadas: 112)
- Resultados totales: 206 (resueltos: 206)
- Resultados esperados (aptas × 3 horizontes): 384
- Resultados generados: 206
- Resultados pendientes sin generar: 178
- Resultados 60m resueltos: 0 (pendientes de settle: 128)

### Observaciones por estado
- descartada: 112
- observada: 128

### Descartadas por motivo
- sin_libro: 66
- sin_flujo: 66
- dato_obsoleto_flujo: 37
- dato_obsoleto_libro: 15

### Observaciones por rol
- candidate: 144
- comparator: 96

### Símbolos observados (top 15)
- 2ZUSDT: 12
- ATUSDT: 12
- CAPUSDT: 12
- CLANKERUSDT: 12
- GWEIUSDT: 12
- HUMAUSDT: 12
- JCTUSDT: 12
- LYNUSDT: 12
- THEUSDT: 12
- EVAAUSDT: 10
- ONUSDT: 8
- AUSDT: 8
- BANUSDT: 8
- CUSDT: 8
- DRIFTUSDT: 8

### Resultados por horizonte y estado
- 15m / resuelto: 91
- 5m / resuelto: 115

### Último evento acreditado
- decision_ms máximo: 1793902799028 (2026-11-05T18:19:59.028000+00:00 UTC)
- Última escritura de research.db: 2179072 bytes, SHA-256 706d0741783ef7d77d0170faa92d17ec267952b34a4cf4edf91797f95820923a

### Consumos (no recuperables)
- Intentos HTTP: UNKNOWN
- Peso HTTP: UNKNOWN
- Aperturas WS: UNKNOWN
- Reconexiones WS: UNKNOWN
- Mensajes WS: UNKNOWN
- Almacenamiento research.db: 2179072 bytes

## Archivos conservados (fuera de Git)
- observaciones.jsonl: 2942444 bytes, SHA-256 e01280703c19a98b4bb8e738a9f3824d1c24dbf2192a28ad94fa6f78cf8fb466
- research.db: 2179072 bytes, SHA-256 706d0741783ef7d77d0170faa92d17ec267952b34a4cf4edf91797f95820923a
- presupuesto.json: 4712 bytes, SHA-256 511cdd2d3d6ba96d6a70a63b8916552c64b83e9183476ff4a744ed828e227318
- stdout.log: 0 bytes, SHA-256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- stderr.log: 0 bytes, SHA-256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855

## Veredicto por dimensión
- **A. Integración técnica:** Transporte y selección funcionaron (12 ciclos, 240 observaciones, universo real). Cierre no acreditado; causa UNKNOWN.
- **B. Calidad y cobertura del dataset:** 206 resultados resueltos (5m: 115, 15m: 91, 60m: 0). 128 observaciones aptas con resultados pendientes de maduración (60m sin generar). Suficiencia limitada para 60m.
- **C. Resultados descriptivos:** neto_estado = UNKNOWN en todos los resultados (sin supuestos de ejecución ni costes). No se presentan como P&L.
