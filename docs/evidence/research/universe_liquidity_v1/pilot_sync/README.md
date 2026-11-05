# Piloto prospectivo — sincronización reloj/prueba (2026-11-04)

Evidencia de la cadena productiva `scripts/research_pilot.py` ejecutada contra
proveedores HTTP/WS **loopback** y SQLite temporal. Sin conexiones públicas de
mercado, sin órdenes y sin tocar DBs canónicas.

## Comando

```text
pytest tests/test_research_pilot.py -v -k "frescura_por_fuente_y_ventana or horizontes_5m_15m_60m"
```

Salida completa: `pytest_sincronizacion.txt` (2 passed).

## Protocolo de sincronización (sin sleeps de avance)

1. El test fija el instante simulado en `--clock-file`.
2. El proveedor WS publica el burst correspondiente a ese instante.
3. El test espera confirmación explícita por `--status-file`: contadores
   aceptados por fuente y última disponibilidad de libro y flujo.
4. Solo entonces escribe `--decision-gate-file` con ese instante y el piloto
   evalúa `decision_ms = instante` (nunca retrotraído).
5. Avanza al siguiente instante cuando la fase termina.

`max_data_age_ms` se mantiene en **5000** en todas las corridas. No se ajustó la
velocidad del reloj para "hacer aptas" observaciones: los rechazos por
obsolescencia se demuestran dejando de publicar una fuente durante 60 s
simulados.

## `diagnostico_frescura_por_fuente.json` (10 observaciones)

Instantes `decision_ms = 1735689660000` (E0) y `1735689720000` (E1), separados
60 s simulados:

| símbolo | instante | apto | motivos | age libro | age flujo | ventana |
|---|---|---|---|---|---|---|
| AAAUSDT | E0 | sí | — | 0 | 0 | completa |
| BBBUSDT | E0 | sí | — | 0 | 0 | completa |
| CCCUSDT | E0 | sí | — | 0 | 0 | completa |
| DDDUSDT | E0 | no | `flujo_ventana_incompleta` | 0 | 0 | incompleta |
| EEEUSDT | E0 | no | `sin_flujo` | 0 | — | incompleta |
| AAAUSDT | E1 | sí | — | 0 | 0 | completa |
| BBBUSDT | E1 | no | `dato_obsoleto_libro` | 60000 | 0 | completa |
| CCCUSDT | E1 | no | `dato_obsoleto_flujo` | 0 | 60000 | completa |
| DDDUSDT | E1 | sí | — | 0 | 0 | completa |
| EEEUSDT | E1 | no | `sin_flujo` | 0 | — | incompleta |

Cada fila incluye además `cobertura` (`libro_presente`, `flujo_presente`,
`flujo_ventana_completa`, `libro_banda_5bps_cubierta`) y las edades de evento y
de recepción. Histograma del resumen: `dato_obsoleto_libro=1`,
`dato_obsoleto_flujo=1`, `flujo_ventana_incompleta=1`, `sin_flujo=2`.
Cero aptas no sería interpretable por sí solo: el motivo por símbolo y fuente sí
identifica la causa.

## `diagnostico_horizontes.json` + `resumen_horizontes.json`

Una observación apta en E0 = `1735689660000` madura por avance controlado del
reloj; los tres horizontes productivos se resuelven con **desfase 0**:

| horizonte | `price_ts_ms` | `horizonte_efectivo_ms` | precio posterior | retorno (fracción) | estado |
|---|---|---|---|---|---|
| 5m | 1735689960000 | 300000 | 1000.6 | 0.0006 | resuelto |
| 15m | 1735690560000 | 900000 | 1000.2 | 0.0002 | resuelto |
| 60m | 1735693260000 | 3600000 | 1000.5 | 0.0005 | resuelto |

`precio_base` = mid del libro; `precio_posterior` = apertura de la vela 1m
(`klines_apertura_1m`); `neto_estado = UNKNOWN` (sin supuestos de ejecución ni
costes). Los precios son sintéticos y deterministas: **esta evidencia no declara
ventaja, rentabilidad ni representatividad**.

## Límites

- Evidencia de mecanismo y trazabilidad temporal, no de edge económico.
- Dataset completo de cada corrida en directorio temporal; aquí se publican las
  tablas agregadas y el resumen.
- `--status-file` y `--decision-gate-file` solo se aceptan con `--clock manual`;
  con reloj de sistema el camino productivo queda intacto y no hay barrera.
