# DETECTOR EXPERIMENTAL SECUENCIA-PRESION-V1 — documentación de implementación

Contexto: bloque de investigación offline autorizado el 2026-11-16
("PRIMER DETECTOR EXPERIMENTAL DE SECUENCIAS, LOCAL Y SIN MERCADO").
Sin Binance, consultas públicas, capturas, órdenes, relanzamientos, cambios en
la estrategia productiva, dashboard, servicios, supervisores ni dependencias
nuevas.

Este detector es EXPERIMENTAL, sin validación económica. No conecta al camino
productivo ni recibe autorización para operar. La regla operativa actual
permanece congelada como referencia.

## 1. Qué reconoce exactamente el detector

El detector SECUENCIA-PRESION-V1 reconoce una secuencia temporal de tres
ventanas consecutivas y completas de UN MINUTO en las que simultáneamente:

1. La presión agresora neta (`buy_notional - sell_notional`, USDT) es a favor
   de la dirección candidata y creciente en magnitud relativa a la profundidad;
2. La profundidad contraria (libro del lado opuesto a la posición) disminuye;
3. El precio de cierre conocido de cada ventana avanza en la dirección candidata.

### Definición mecánica (fijada antes de cualquier evaluación económica)

Para cada ventana k (1 minuto completa):

- `F_k = compras_agresoras_k - ventas_agresoras_k` (USDT, de `flujo.buy_notional - flujo.sell_notional`)
- `D_k = profundidad contraria` (USDT):
  - LONG → `ask_notional_top20` (profundidad de venta)
  - SHORT → `bid_notional_top20` (profundidad de compra)
- `Q_k = s × F_k / D_k`, con `s = +1` (LONG) / `-1` (SHORT)

Primera definición mecánica:
- `0 < Q_1 < Q_2 < Q_3`
- `D_1 > D_2 > D_3 > 0`
- los cierres conocidos de las tres ventanas avanzan en la dirección candidata
  (LONG: `precio_1 < precio_2 < precio_3`; SHORT: `precio_1 > precio_2 > precio_3`)

### Salidas del detector

| Salida | Significado |
| --- | --- |
| `LONG_EXPERIMENTAL` | Secuencia cumple el patrón para LONG |
| `SHORT_EXPERIMENTAL` | Secuencia cumple el patrón para SHORT |
| `SIN_PATRON` | Hay 3+ ventanas válidas pero ninguna dirección cumple el patrón |
| `DATOS_INSUFICIENTES` | Menos de 3 ventanas válidas (datos faltantes, huecos, integridad rota) |

Cada salida incluye: condiciones cumplidas/faltantes, las tres ventanas usadas,
F_k, D_k, Q_k, precios, timestamps, procedencia, versión y hash de
configuración, motivo explícito.

Ausentes, no finitos, importes inválidos, profundidad no positiva, ventanas
incompletas o huecos impiden acreditar el patrón. Nunca UNKNOWN → cero.
No se mezclan "no se cumple el patrón" con "no podemos evaluarlo".

## 2. Código y comando local reproducible

Archivo: `scripts/secuencia_presion_v1.py`

CLI:
```powershell
python scripts/secuencia_presion_v1.py --fuente <observaciones.jsonl> --salida <decisiones.jsonl>
```

- `--fuente`: ruta al JSONL de observaciones (formato del piloto, `kind: observacion`)
- `--salida`: ruta al JSONL de salida con una decisión por símbolo
- Trabaja sin red, genera decisiones reconstruibles desde lo persistido
- No crea motor de trading, framework de aprendizaje ni servicio

### Estructura de la configuración congelada

```json
{
  "version": "SECUENCIA-PRESION-V1",
  "ventana_ms": 60000,
  "num_ventanas": 3,
  "profundidad_niveles": 20,
  "profundidad_lado_contrario": true,
  "requiere_ventana_completa": true,
  "requiere_integridad_valida": true,
  "condiciones": {
    "q_positivo_creciente": true,
    "profundidad_contraria_decreciente": true,
    "precio_avanza_en_direccion": true
  },
  "flujo_fuente": "aggTrade",
  "profundidad_fuente": "depth20@100ms"
}
```

SHA-256 de la configuración: calculado sobre el JSON serializado con `sort_keys=True`.

## 3. Traza LONG y SHORT (datos sintéticos de prueba)

### Traza LONG (3 ventanas, capacidad 1 aislada)

| Ventana | decision_ms | buy_notional | sell_notional | F_k | ask_notional_top20 (D_k) | Q_k | precio_cierre |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | T0+0 | 100.0 | 20.0 | +80.0 | 1000.0 | +0.080 | 100.00 |
| 2 | T0+60s | 150.0 | 20.0 | +130.0 | 900.0 | +0.144 | 100.50 |
| 3 | T0+120s | 200.0 | 20.0 | +180.0 | 800.0 | +0.225 | 101.00 |

Comprobaciones:
- Q: 0.080 < 0.144 < 0.225 ✓ (positivo y creciente)
- D: 1000 > 900 > 800 ✓ (decreciente y positivo)
- precio: 100.00 < 100.50 < 101.00 ✓ (avanza en LONG)
→ **LONG_EXPERIMENTAL**

### Traza SHORT (3 ventanas, capacidad 1 aislada)

| Ventana | decision_ms | buy_notional | sell_notional | F_k | bid_notional_top20 (D_k) | Q_k | precio_cierre |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | T0+0 | 20.0 | 100.0 | -80.0 | 1000.0 | +0.080 | 100.00 |
| 2 | T0+60s | 20.0 | 150.0 | -130.0 | 900.0 | +0.144 | 99.50 |
| 3 | T0+120s | 20.0 | 200.0 | -180.0 | 800.0 | +0.225 | 99.00 |

Comprobaciones:
- Q: 0.080 < 0.144 < 0.225 ✓ (positivo y creciente)
- D: 1000 > 900 > 800 ✓ (decreciente y positivo)
- precio: 100.00 > 99.50 > 99.00 ✓ (avanza en SHORT)
→ **SHORT_EXPERIMENTAL**

## 4. Pruebas, resultados y códigos observados

Archivo: `tests/test_secuencia_presion_v1.py` — 13 pruebas pasando:

| Prueba | Resultado |
| --- | --- |
| secuencia LONG válida | PASSED → LONG_EXPERIMENTAL |
| secuencia SHORT válida | PASSED → SHORT_EXPERIMENTAL |
| presión creciente, profundidad no disminuye | PASSED → SIN_PATRON |
| profundidad decreciente, sin presión alineada | PASSED → SIN_PATRON |
| precio sin confirmación direccional | PASSED → SIN_PATRON |
| ventana incompleta | PASSED → DATOS_INSUFICIENTES |
| dato inválido (profundidad no positiva) | PASSED → DATOS_INSUFICIENTES |
| última fuente después del corte → no detección anticipada | PASSED → DATOS_INSUFICIENTES |
| añadir datos futuros no cambia decisión | PASSED → LONG_EXPERIMENTAL (idéntica) |
| símbolos distintos no comparten historia | PASSED → LONG + SHORT independientes |
| repetir mismo corte no duplica | PASSED → misma decisión |
| CLI real con JSONL sintético → LONG | PASSED → exit_code 0 |
| CLI real con 2 ventanas → DATOS_INSUFICIENTES | PASSED → exit_code 0 |

Todas las pruebas ejecutan el código productivo del detector (no fórmulas aisladas).
Códigos de salida observados: 0 (éxito).

## 5. Cobertura real y faltantes exactos

Se inspeccionó el dataset de la ventana 4
(`C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a`) en modo solo
lectura, sobre las 196 observaciones aptas.

### Conteo exacto

| Métrica | Valor |
| --- | --- |
| Observaciones aptas totales | 196 |
| Símbolos únicos | 34 |
| Observaciones con flujo (buy/sell notional) | 196 / 196 |
| Observaciones con libro (bid/ask top-20) | 196 / 196 |
| Observaciones con precio base | 196 / 196 |
| Observaciones con ventana de flujo completa | 183 / 196 |
| Observaciones con integridad válida | 33 / 196 |
| Observaciones con disponibilidad temporal | 196 / 196 |
| Observaciones que cumplen TODOS los requisitos | 20 / 196 |

### Símbolos con ventanas válidas

| Símbolos con ≥3 ventanas válidas | 0 |
| Símbolos con exactamente 3 válidas | 0 |
| Símbolos con 1-2 válidas | 20 |
| Símbolos con 0 válidas | 14 |

### Secuencias que podrían evaluarse

| Secuencias de 3 ventanas consecutivas por símbolo | 0 |
| Símbolos que podrían evaluarse | 0 |

### Faltantes y motivos

| Campo | Observaciones que faltan | Motivo principal |
| --- | --- | --- |
| `flujo_ventana_completa` | 13 | Ventana de flujo no completa (datos incompletos del minuto) |
| Integridad del feed/libro | 163 | `huecos_detectados_en_feed` y `libro_huecos` presentes (datos de streaming con gaps) |

### Conclusión de cobertura

**No hay ningún símbolo con 3 ventanas válidas consecutivas** en la ventana 4.
El detector SECUENCIA-PRESION-V1 no puede ejecutarse sobre esta captura
porque no hay datos suficientes para formar ni una sola secuencia de 3
ventanas válidas. Esto no es un error del detector: es una limitación de
cobertura de los datos capturados.

### Listado mínimo de campos, resolución e historia previa necesarios para futura adquisición

Para ejecutar el detector en una captura futura se requiere, por símbolo y
ventana de 1 minuto:

| Campo | Origen | Unidades | Resolución | Nota |
| --- | --- | --- | --- | --- |
| `buy_notional` | flujo (aggTrade) | USDT | 1 min | Compras agresoras en la ventana |
| `sell_notional` | flujo (aggTrade) | USDT | 1 min | Ventas agresoras en la ventana |
| `bid_notional_top20` | libro (depth20@100ms) | USDT | 1 min | Profundidad de compra top-20 |
| `ask_notional_top20` | libro (depth20@100ms) | USDT | 1 min | Profundidad de venta top-20 |
| `precio_base` (mid del libro) | libro | precio | 1 min | Precio de cierre conocido de la ventana |
| `ventana_completa` | flujo | booleano | 1 min | La ventana de 1 min está completa |
| `integridad` (sin huecos, sin invalidos, sin cruce) | flujo/libro | booleano | 1 min | Datos de streaming integridad |
| `disponibilidad.max_ms` | disponibilidad | ms | 1 min | Instante en que toda la evidencia estaba disponible |
| `decision_ms` | observación | ms | 1 min | Instante real de evaluación (reloj del piloto) |
| `symbol` | observación | ticker | — | Identidad del contrato |
| `observation_id` | observación | id | — | Identificador único de la ventana |

**Historia previa necesaria:** al menos 3 ventanas consecutivas por símbolo
(orden cronológico por `decision_ms`), cada una con los campos anteriores
completos y sin huecos en el feed.

**No se deben reconstruir ventanas de 30 segundos desde agregados de 1
minuto.** Cada ventana debe ser una ventana de 1 minuto completa y
independiente, con su propio flujo, libro y precio.

## 6. Qué queda preparado para la siguiente validación

Se deja una ficha breve para la prueba independiente posterior:

- **Observación de un minuto:** cada ventana representa 1 minuto de datos de flujo agresor y profundidad top-20, capturada en un ciclo de decisión.
- **Horizonte principal propuesto:** 5 minutos (investigación de corto plazo). El detector opera sobre 3 ventanas de 1 minuto; el horizonte de evaluación del retorno posterior se dejaría para la validación económica posterior.
- **Precio y momento de entrada causal:** `precio_base` (libro_mid) en `decision_ms`, el instante real de evaluación del piloto. No se usa `bucket_end` ni precios retrotrados.
- **Tratamiento de alertas repetidas del mismo episodio:** una vez emitida una decisión (LONG_EXPERIMENTAL o SHORT_EXPERIMENTAL) sobre una secuencia de 3 ventanas, datos futuros no la cambian. El detector emite una decisión por símbolo basada en las primeras 3 ventanas válidas que cumplan (o las primeras 3 válidas si ninguna cumple → SIN_PATRON).
- **Comparación con referencia sencilla:** comparar contra una regla de dirección por signo de `move_24h_pct` (sin confirmación de flujo), con controles del mismo universo (mismos símbolos, mismos ciclos).
- **Costes, pérdidas, movimiento adverso y abstenciones:** no aplicable en esta fase (no hay entradas, posiciones ni P&L). El detector solo emite detecciones mecánicas.
- **Criterio económico para continuar, descartar o declarar insuficiencia:** si una captura futura tiene ≥3 ventanas válidas por símbolo con patrones detectables, proceder a validación económica con horizonte de 5 min. Si no hay cobertura suficiente (como en esta captura), declarar insuficiencia y no operar.

**Distingue reconocimiento mecánico de utilidad predictiva y operativa:** el detector reconoce un patrón mecánico (presión creciente, profundidad decreciente, precio avance). Esto no implica utilidad predictiva ni rentabilidad. La validación económica requiere una captura nueva con autorización propia.

## 7. Lo que NO acredita

Rentabilidad, edge, mejora predictiva, ventaja de candidato sobre comparador,
generalización (una hora de captura, dependencia temporal, símbolos repetidos).
El detector no se conecta al camino productivo. No se presentan detecciones
sintéticas como oportunidades reales.

## 8. Artefactos

- Código: `scripts/secuencia_presion_v1.py`
- Pruebas: `tests/test_secuencia_presion_v1.py` (13 passed)
- Regresiones: `test_analisis_contrafactual_ventana4.py` (16 passed), `test_operativo_replay_offline.py` (7 passed)
- Evidencia de cobertura: este documento (sección 5) — basado en `observaciones.jsonl` de la ventana 4, leído en modo solo lectura
- SHA base: `4a7df47e89dbd1015ad89a6f1889ebf48d156c59`
- SHA del análisis: commit `4a7df47` (detector SECUENCIA-PRESION-V1)

## 9. Lo que NO se hizo

No se creó motor de trading, framework de aprendizaje, servicio, supervisor,
dashboard ni dependencias nuevas. No se conectó a Binance. No se hicieron
capturas. No se cambiaron entradas, stops, notional ni capacidad del
experimento vigente. No se calculó rentabilidad ni se exploraron umbrales
sobre esta captura.
