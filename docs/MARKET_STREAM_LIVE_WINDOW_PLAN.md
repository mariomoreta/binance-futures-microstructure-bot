# Ventana viva acotada — `market-stream/v1` (PREPARADA, NO EJECUTADA)

Estado: **plan escrito; la conexión Binance continua NO se ha abierto en este
bloque.** Este documento fija qué se mediría, con qué límites y cómo se pararía.
Requiere autorización humana explícita y separada.

Contrato de referencia: [`MARKET_STREAM_CONTRACT_V1.md`](MARKET_STREAM_CONTRACT_V1.md).
Script: `scripts/market_stream_window.py` (sin `--execute` solo imprime el plan).

## 1. Objetivo de la ventana

Verificar con Binance real, en el menor tiempo y ancho posible, exactamente tres
cosas que las pruebas con transporte simulado no pueden demostrar:

1. que la ruta `wss://fstream.binance.com/market` entrega `kline` para el par
   `(símbolo, intervalo)` suscrito con la identidad y unidades esperadas;
2. la cadencia real de actualización de la vela en formación (la documentación
   pública es contradictoria: 1000–2000 ms frente a 250 ms en la referencia de
   la API) — se **mide**, no se asume;
3. que el cierre de vela llega con `x=true` y `T` coherente con
   `open_time + intervalo_ms - 1`, sin huecos en la secuencia.

No es una prueba de rentabilidad, de señal, ni de ejecución.

## 2. Alcance y presupuesto

| Parámetro | Valor |
|---|---|
| Conexiones WS | **1** (combinada, `?streams=`) |
| Streams | **2**: un contrato del trío canónico + uno elegible fuera del trío |
| Símbolos por defecto | `BTCUSDT` (trío) y `MINAUSDT` (fuera del trío, con histórico ya verificado en el explorador) |
| Intervalo | `1m` (el más exigente por cadencia sin multiplicar streams) |
| Duración máxima | **60 s** |
| Mensajes máximos | **400** |
| Reconexiones máximas | **3** |
| Persistencia | ninguna (anillo en memoria, 300 velas cerradas por stream) |
| REST de reparación | máximo 2 páginas × 500 velas, ≤ 6 peticiones/min, solo si aparece un hueco |
| Escrituras en DB | ninguna (`historical.db` y `microprobe.db` intactas; sin caché del explorador) |
| Monitor del bot | no se arranca, no se modifica, suscripción canónica intacta |
| Sesiones Paper Lab | no se crean ni se tocan |

El servicio HTTP (`scripts/market_stream_service.py`) **no** se usa en la
ventana: el script habla con el hub y el transporte directamente, así que no
queda ningún puerto escuchando ni proceso hijo.

## 3. Comando exacto (solo tras autorización)

```powershell
$env:PYTHONPATH="src"
python -X utf8 scripts/market_stream_window.py --symbols BTCUSDT,MINAUSDT `
    --interval 1m --duration 60 --max-messages 400 --max-reconnects 3 `
    --execute --out docs/evidence/market-stream-window-2026-10-21.json
```

Sin `--execute` imprime el plan y no abre ninguna conexión (verificado).

## 4. Métricas a registrar

- mensajes por stream y total; velas provisionales frente a cerradas;
- primera y última recepción (ms UTC), edad final y `last_kline_open_ms`;
- huecos detectados / reparados / parciales / fallidos (con tramos faltantes);
- reconexiones, último error de socket y motivo de parada;
- contadores `invalid`, `unrouted`, `identity_mismatch`, `late`,
  `out_of_order`, `duplicate`;
- memoria estimada del anillo por stream (`ring × 192 B`, tope 300 velas);
- cadencia medida: diferencia entre `event_ms` consecutivos de la misma vela.

## 5. Reglas de parada

Se para (y se documenta el motivo) si ocurre cualquiera de:

1. se alcanza la duración (60 s) o el número de mensajes (400);
2. reconexiones > 3;
3. error de protocolo repetido o `identity_mismatch` en un mensaje;
4. el exchange pide credenciales o el flujo requeriría una orden o cuenta
   privada (**no contemplado: se aborta el bloque**);
5. cualquier indicio de escritura en bases canónicas o de arranque del monitor.

No hay reintentos en bucle: el transporte ya aplica backoff 1 s → 30 s con
jitter y presupuesto de 20 fallos consecutivos.

## 6. Evidencia a capturar

- JSON del script (`docs/evidence/…`) con `health` inicial y final;
- `git status` antes/después mostrando que no se crearon ficheros de datos;
- mtime de `data/historical/historical.db` y `data/microprobe.db` sin cambios;
- lista de procesos Python antes/después (sin residuos);
- si se abre el dashboard durante la ventana, captura del panel de estado del
  feed con `RECIBIENDO`/`no LIVE`/`LIVE` según corresponda y el texto de
  antigüedad.

## 7. Qué NO demuestra la ventana

- No valida la frescura en producción ni el comportamiento bajo rate limits del
  exchange (solo el presupuesto local).
- No valida la UI de forma visual sin un modelo de visión disponible.
- No valida rentabilidad, señal, indicadores ni ejecución.
- Un único intervalo y dos símbolos no generalizan al universo completo: abrir
  el catálogo no debe suscribir el universo, y no se hará.

## 8. Después de la ventana

1. Parar el proceso (el script lo hace en `finally`), comprobar 0 procesos
   Python y 0 listeners en el puerto del servicio.
2. Registrar en `docs/CURRENT_STATE.md` el estado **verificado con Binance**
   (o el fallo concreto), separado de "probado con transporte controlado".
3. Dejar el servicio continuo **detenido** y el dashboard sirviendo histórico.
   El arranque es manual y explícito.
