# Reconciliación de WS y transportes — public-pilot-1h-20261106a

run_id: public-pilot-1h-20261106a

## 1. Límites autorizados para esta corrida

| Parámetro | Valor autorizado |
|-----------|-----------------|
| Conexiones WS simultáneas | 2 |
| Símbolos máximos simultáneos | 20 |
| Streams totales máximos | 40 (20 símbolos × 2 feeds) |
| max_ws_reconnects | 20 |
| max_messages | 5 000 000 |

## 2. Contadores persistidos (resumen.json / status.json)

| Contador | Valor | Tipo | Nota |
|----------|-------|------|------|
| ws_connections_total | 20 | CUMULATIVE | Aperturas acumuladas de WS a lo largo de toda la corrida. NO es simultáneo. |
| ws_messages_total | 960 114 | CUMULATIVE | Mensajes acumulados (incluye feeds reemplazados por rotación; no es igual a suma de feeds actuales porque los feeds se reinician al rotar). |
| ws_reconnects_total | 0 | CUMULATIVE | Reconexiones tras fallo/desconexión. |
| ws.market.messages | 55 265 | Per-feed (actual) | Mensajes del feed /market (aggTrade) en la conexión activa al final. |
| ws.public.messages | 26 192 | Per-feed (actual) | Mensajes del feed /public (depth20@100ms) en la conexión activa al final. |
| ws.market.connections | 1 | Per-feed (actual) | Conexión activa del feed market al final. |
| ws.public.connections | 1 | Per-feed (actual) | Conexión activa del feed public al final. |
| ws.market.disconnects | 1 | Per-feed | Desconexión normal al finalizar. |
| ws.public.disconnects | 1 | Per-feed | Desconexión normal al finalizar. |
| ws.market.reconnects | 0 | Per-feed | Sin reconexiones por fallo. |
| ws.public.reconnects | 0 | Per-feed | Sin reconexiones por fallo. |

## 3. Corrección: "20 conexiones" ≠ "20 simultáneas"

El valor **20** (ws_connections_total) es el **número acumulado de aperturas de WS** a lo largo de toda la corrida, NO el pico de conexiones simultáneas.

- **Pico de conexiones simultáneas: 2.** El piloto mantiene exactamente 2 feeds simultáneos en todo momento: 1 conexión /public (depth20@100ms) + 1 conexión /market (aggTrade). Esto es estructural del código y se confirma con ws.market.connections = 1 y ws.public.connections = 1 (una conexión por feed). Nunca hay más de 2 conexiones abiertas al mismo tiempo.
- **Aperturas acumuladas: 20.** Cada rotación de símbolos que cambia el conjunto seguido vuelve a abrir ambos feeds (2 aperturas por rotación). Con 12 selecciones hay hasta 11 rotaciones → 2 iniciales + hasta 22 por rotación = hasta 24, pero el valor real es 20 porque algunas rotaciones no cambiaron el conjunto de símbolos seguido (no reabren feeds si los símbolos son los mismos).
- **Reconexiones tras fallo/desconexión: 0.** ws_reconnects_total = 0. Las únicas desconexiones son las 2 normales al finalizar (una por feed), no por fallo.
- **Símbolos y streams simultáneos:** hasta 20 símbolos seguidos a la vez, 40 streams totales (20 símbolos × 2 feeds), dentro del límite de 40.

## 6. Procedencia de cada contador

| Contador | Origen en el código | ¿Simultáneo o acumulado? |
|----------|--------------------|--------------------------|
| ws_connections_total | self.ws_total_connections + sum(f.connections) | Acumulado |
| ws.messages (por feed) | f.messages (contador del feed activo) | Per-feed actual |
| ws_messages_total | self.ws_messages_total + sum(f.messages) | Acumulado (incluye feeds reemplazados) |
| ws_reconnects_total | self.ws_reconnects_total + sum(f.reconnects) | Acumulado |
| ws.reconnects (por feed) | f.reconnects | Per-feed acumulado |

## 7. Conclusiones

- **Pico simultáneo: 2 conexiones** (1 /public + 1 /market), dentro del límite de 2. **ACREDITADO.**
- **Aperturas acumuladas: 20**, dentro del límite implícito (máximo teórico 24). **ACREDITADO.**
- **Reconexiones: 0**, dentro del límite de 20. **ACREDITADO.**
- **Streams simultáneos: hasta 40** (20 símbolos × 2), dentro del límite de 40. **ACREDITADO.**
- No se infieren conexiones simultáneas a partir del total acumulado (20 ≠ 20 simultáneas).
