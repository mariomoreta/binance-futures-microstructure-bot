# Libro de órdenes compartido — integración futura
Fecha: 2026-11-03
ID estable: F-BOOK-SHARED-01
Base revisada: bf974f2b4c455bf1daece89f94a072ad30e6692e (dash-v2-04-recorrido-visible).
Estado: PLANIFICADO / DIFERIDO. Autorización actual: documentación y revisión solamente.

## Objetivo y límite de la decisión
Mostrar el libro de la moneda seleccionada junto al gráfico y exponer las mismas
métricas al backend para investigación de calidad de ejecución y, después de
validación separada, posibles reglas de entrada/salida. No es una señal nueva
ni una promesa de mayor rentabilidad. No se implementa ni activa ningún feed,
conexión pública, orden, dependencia o almacenamiento en este bloque.

Primero revisar la aceptación vigente del dashboard y completar lo pendiente. La captura pública,
la retención de datos y cualquier cambio de reglas requerirán alcance y
presupuesto propios. Los 7 intentos de una ventana histórica no autorizan
snapshots ni recuperación futura del libro.

## Qué existe y qué falta
Inspección de código en la base indicada:
- src/microstructure_probe/book.py contiene parse_levels, book_features y
  estado acotado para top-20: mejores precios, spread, profundidad top-1/5/10/20,
  imbalance, microprice, pendiente y concentración con cobertura.
- Su contrato documentado es una instantánea COMPLETA top-20 por actualización
  de depth20@100ms. No es un reconstructor de libro completo a partir de diffs.
  El estado marca continuidad degradada ante saltos de pu.
- src/microstructure_probe/metrics.py contiene spread_bps y
  order_book_imbalance. No duplicar las fórmulas ni asumir que ambos contratos
  son intercambiables sin revisar unidades y validaciones.
- docs/SHARED_INDICATORS_V1.md ya identifica spread/profundidad como métricas
  cuya fuente no está disponible en el canal de velas.
- No se acredita aquí un libro conectado al recorrido actual de /market-lab
  ni consumido por RULE-CAUSAL-V1.

Auditar el cableado y las pruebas existentes antes de implementar. Integrar la
autoridad Python existente; no crear otro motor en TypeScript o en el navegador.

## Topología y contrato propuesto
Proveedor Binance USD-M → transporte/normalización existentes → estado del
libro y métricas Python → publicación versionada para dashboard y evaluador.
La interfaz presenta; el backend decide. Un mismo snapshot/revisión debe poder
identificarse en ambos consumidores. La selección del navegador es una petición
de suscripción, nunca una fuente de valores ni decisiones.

Diseño propuesto, no contrato implementado: market-order-book/v1.
Campos a definir y probar antes del código:
- Identidad: venue, market_type, symbol, origen local/public, modalidad
  partial_snapshot o diff_reconstructed; no mezclar spot ni símbolos.
- Secuencia y tiempo: IDs U/u/pu cuando correspondan, event_time,
  received_at, available_at, versión del estado y referencia temporal.
- Estado: INITIALIZING, SYNCED, DEGRADED, STALE, DISCONNECTED, NO_COVERAGE,
  con motivo y cobertura. LIVE exige estado válido y frescura comprobada.
- Niveles bid/ask: precio, cantidad base, notional quote, orden declarado,
  número de niveles y límites de cobertura visibles.
- Métricas y unidades: spread absoluto/bps; profundidad base y quote;
  imbalance y ventana/corte; microprice; pendientes/concentraciones si se
  reutilizan. Ausencia de cobertura o denominador válido → UNKNOWN, nunca cero.
- Consumo causal: cada evaluación conserva la revisión del libro realmente
  disponible en su T. Un libro actual no puede decorar como evidencia histórica
  el cursor de una vela pasada. Sin snapshot de ese instante → NO_COVERAGE.
- Calidad: antigüedad, pérdidas de secuencia, invalidaciones y recuperación.

## Elección de fuente y sincronización
Primero comparar dos opciones con el inventario existente:
1. Top-20 parcial: reutilización más directa; declarar que solo cubre niveles
   visibles y no afirmar liquidez completa.
2. Diffs más snapshot: más profundidad, pero exige buffer, snapshot inicial,
   alineación de IDs, eliminación de cantidades cero y resincronización ante
   pérdida de continuidad. No aplicar diffs como snapshots ni viceversa.

La elección queda PENDIENTE de auditoría y contrato. Una discontinuidad no debe
ocultarse con el último estado como si fuese vigente. Para diffs, invalidar
hasta reconstruir; para snapshots parciales, declarar cobertura y degradación
según el contrato existente y su validación. Contabilizar cada snapshot REST,
reintento y resincronización antes del envío en el ledger común.

Referencia oficial consultada:
https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly
Revalidar endpoints y semántica del stream elegido al implementar.

## Superficie del dashboard
Junto al gráfico de la moneda seleccionada:
- Escalera de bids/asks y profundidad acumulada con cobertura explícita.
- Spread, desequilibrio, antigüedad y estado de sincronización.
- Precio medio y deslizamiento HIPOTÉTICOS para el notional indicado, si la
  profundidad visible alcanza. Si no alcanza: INSUFFICIENT_DEPTH, no extrapolar.
- Origen local simulado o público inequívoco; limpieza de valores al cambiar
  de símbolo y cancelación de respuestas tardías.
- La sesión backend conserva sus suscripciones mientras las necesite aunque
  cambie la selección visual; refcount y liberación de consumidores propios.

La estimación de recorrido del libro no es un fill ni garantiza ejecución,
posición en cola, latencia o costes futuros. Comisiones y funding son conceptos
separados. Cantidades visibles pueden cancelarse; contrastar con aggTrade para
estudiar operaciones ejecutadas. Imbalance positivo no es orden de compra.

## Secuencia futura y aceptación
1. Revisar la nueva evidencia E/F/H/I de c3b8600, cerrar lo no acreditado y verificar la identidad del build.
2. Auditar book.py/metrics.py, consumidores y transporte; fijar el contrato,
   unidades, modalidad, límites de memoria, actualización y retención.
3. Implementar solo observación con proveedor loopback y mismas métricas en
   dashboard/backend. Cubrir orden/dedup, huecos, snapshots/diffs, reinicio,
   libro insuficiente, cambio de símbolo, staleness y liberación.
4. Ventana pública separada y autorizada: snapshot/stream sincronizados,
   misma revisión en UI/backend, presupuesto y limpieza acreditados.
5. Capturar métricas junto a evaluaciones sin modificar decisiones. Definir
   dataset y retención acotada; no almacenar cada actualización sin límite.
6. Investigar aporte fuera de muestra y sensibilidad a costes/latencia.
   Solo después proponer filtros versionados y paper prospectivo.

Empezar por símbolo seleccionado y conjunto acotado de candidatos; no todos
los contratos a la vez. No reconstruir libro histórico desde OHLC ni atribuir
cobertura antes de iniciar captura. Riesgo, position manager y fuente de verdad
no se sustituyen por este panel.

## Dependencias, alcance y retirada
Dependencias: dashboard aceptado, autoridad Python, transporte estable,
referencia temporal, ledger compartido y control de consumidores.
No modifica gates de SUCCESS_GATES.md ni autoriza fases completas.
No claves, APIs privadas, órdenes, ejecución real, móvil ni optimización de
estrategia en este plan.
Retirada futura: deshabilitar suscripción/panel y bloque aditivo, liberar
recursos propios y conservar evidencia; no alterar velas, flujo, paper o
sesiones existentes.
