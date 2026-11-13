# Diagnóstico WS de recepción — `diag-ws-recepcion-20261112a`

> ⚠ **RECTIFICADO (2026-11-12).** Este informe es el **antecedente** de la
> corrida y se conserva sin reescribir. Su afirmación de cumplimiento global
> del plazo de 60 s **queda retirada**: el plazo global **NO CUMPLE**
> (65.034 s el diagnóstico, 65.557 s el lanzador) y la configuración de 60 s no
> es una medición independiente de la duración efectiva de observación. El
> `PASS` emitido por el script se conserva como antecedente. Rectificación
> completa: [RECTIFICACION-20261112.md](RECTIFICACION-20261112.md).

**Fecha:** 2026-11-12 · **Alcance:** autorización humana acotada a **una sola**
ejecución pública de recepción. **SHA de ejecución:** `37b779c456c5aed234171bbb0fe3421b979bb150`
(local == remoto en el momento de ejecutar; incluye el código de `90ff425`).

Este informe publica **evidencia compacta** del diagnóstico. No es un dataset de
investigación, no evalúa rentabilidad y no autoriza ninguna ventana operativa.

---

## 1. Comando efectivo

```powershell
python scripts/run_pilot_window.py `
  --out-dir C:\proyectos\binance-futures-data\diag-ws-recepcion-20261112a `
  -- python scripts/diagnostico_ws_recepcion.py `
     --diagnostico-id diag-ws-recepcion-20261112a `
     --simbolo BTCUSDT `
     --duracion-seconds 60 `
     --out-dir C:\proyectos\binance-futures-data\diag-ws-recepcion-20261112a `
     --ws-public-base wss://fstream.binance.com/public `
     --ws-market-base wss://fstream.binance.com/market `
     --autorizar-publico `
     --max-messages 200000 `
     --max-bytes 1048576
```

El comando exacto que ejecutó el proceso está en `launcher.json` (campo
`comando`). Se ejecutó **una sola vez**; no hubo reintento ni relanzamiento.

**URLs efectivas** (las que el proceso construyó y abrió):

| Feed | URL |
|---|---|
| Flujo (trades) | `wss://fstream.binance.com/market/stream?streams=btcusdt@aggTrade` |
| Libro | `wss://fstream.binance.com/public/stream?streams=btcusdt@depth20@100ms` |

Símbolo en minúsculas, nombre `aggTrade` intacto, suscripción por URL en modo
`stream` (sin mensajes `SUBSCRIBE`).

## 2. Tiempos reales

| Medida | Valor | Fuente |
|---|---|---|
| Inicio | `2026-11-12T23:50:16Z` (19:50:16 −04:00) | `launcher.json` / `diagnostico.json` |
| Fin | `2026-11-12T23:51:22Z` (19:51:22 −04:00) | `launcher.json` |
| Duración del proceso (lanzador) | **65.557 s** | `launcher.json.duracion_s` |
| Duración registrada por el diagnóstico | **65.034 s** | `diagnostico.json.resultado.duracion_s` |
| Duración de observación configurada | 60 s (máximo) | `--duracion-seconds 60` |

**Exceso declarado sin maquillar:** el proceso total duró ~5 s más que los 60 s
configurados. La diferencia corresponde al **cierre de los sockets** del
transporte (`StreamFeed` abre con `close_timeout=5`), no a una ampliación de la
ventana de observación: el bucle de observación corta al vencer el plazo de 60 s
y `limite_mensajes_alcanzado` es `false`. No se relanzó, no se amplió la
duración y no se repitió la consulta.

## 3. Evidencia por feed

| Métrica | Flujo (`/market`, `aggTrade`) | Libro (`/public`, `depth20@100ms`) |
|---|---|---|
| Conexiones iniciales | 1 | 1 |
| Reconexiones | **0** | **0** |
| Errores | **0** | **0** |
| `last_error` | `null` | `null` |
| Frames totales recibidos | 773 | 552 |
| Frames de **datos** | 773 | 552 |
| Frames de **control** (ACK/ping) | **0** | **0** |
| Frames de datos fuera de `BTCUSDT` | 0 | 0 |
| Frames inválidos | 0 | 0 |
| **Eventos válidos** | **773** | **552** |
| **Eventos procesados por el motor** | `flow_events[BTCUSDT] = 773` (FlowEngine) | `book_events[BTCUSDT] = 552` (BookEngine) |

Las columnas de transporte (`messages`) y de eventos procesados por motor
coinciden exactamente y son consistentes entre sí: **cada frame de datos
recibido fue un evento válido y fue aceptado por su motor**. Ningún frame de
control participated en el criterio.

## 4. Criterios de aceptación, contrastados con los artefactos

| Criterio | Exigido | Observado | Estado |
|---|---|---|---|
| aggTrade válidos **y** procesados por FlowEngine | > 0 | 773 válidos / 773 procesados | **Cumplido** |
| Libro válido **y** procesado por BookEngine | > 0 | 552 válidos / 552 procesados | **Cumplido** |
| Dos aperturas iniciales | 2 | 1 + 1 = 2 | **Cumplido** |
| Cero reconexiones | 0 | 0 + 0 | **Cumplido** |
| Cero errores | 0 | 0 + 0 (`last_error: null`) | **Cumplido** |
| Límite de mensajes | ≤ 200 000 | 1 325 frames; `limite_mensajes_alcanzado: false` | **Cumplido** |
| Límite de almacenamiento | ≤ 1 048 576 B | 2 360 B (`diagnostico.json`); 3.41 KB el directorio | **Cumplido** |
| Duración de observación | ≤ 60 s | 60 s configurados (exceso de ~5 s solo de cierre, declarado arriba) | **Cumplido con exceso declarado** |
| Cierre efectivo de recursos | sockets cerrados | `connected_now: false`, `disconnects: 1` por feed, proceso terminado, sin proceso propio vivo | **Cumplido** |
| Cero REST / órdenes / dataset | 0 | `rest: "ninguna peticion REST"`, `ordenes: "ninguna"`, `dataset_investigacion: "no se genera"`; el directorio solo contiene los 5 artefactos | **Cumplido** |

**Veredicto: PASS** (el script lo imprime y los artefactos lo corroboran; el
PASS **no** se acepta solo por la salida del script).

## 5. Código de salida observado

`exit_code.txt` = **`0`**; `launcher.json.returncode` = **`0`**; fuente:
`Popen.wait()` (código real del proceso), no inferido de stdout ni de stderr.
`stderr.log` está **vacío**. El envoltorio devolvió 0 a la consola.

## 6. Lo que este diagnóstico permite concluir

- El transporte productivo (`StreamFeed` + `build_stream_url`) **recibe y
  procesa** datos reales del venue USD-M en las rutas vigentes: `aggTrade` →
  `FlowEngine` y `depth20@100ms` → `BookEngine`, con eventos válidos y
  procesados en la misma proporción (773 y 552).
- Las URLs por categoría (`/public`, `/market`) **funcionan hoy** contra
  `fstream.binance.com` con suscripción por URL en modo `stream`.
- El bloqueo material de datos que vació el embudo de la ventana anterior
  **está resuelto para el transporte**: con la ruta correcta hay flujo real.

## 7. Lo que este diagnóstico NO permite concluir

- **No demuestra la causa histórica.** No se abrió la URL antigua contra el
  venue, así que la causa raíz del silencio de `exp-v2-ventana-1-20261112a`
  sigue **UNKNOWN** (no se reclasifica como demostrada). La coherencia con la
  hipótesis documentada es un indicio adicional, no una prueba.
- **No acredita una ventana completa de flujo ni observaciones aptas** para la
  estrategia: 60 s y un símbolo no son cobertura de universo, ni ciclo de
  selección, ni horizontes, ni evidencia económica.
- **No evalúa rentabilidad, estabilidad prolongada ni capacidad de operar.**
  No se generaron señales, decisiones, operaciones, órdenes ni cuentas.
- **No habilita ninguna ventana operativa.** El exit code histórico de
  `exp-v2-ventana-1-20261112a` sigue **UNKNOWN**.
- Cobertura de contrato: solo PERPETUAL/TRADING/USDT (el selector y el
  diagnóstico no cubren futuros con vencimiento).

## 8. Preservación

No se modificaron `opencode.json`, archivos ajenos, datasets históricos, DBs
canónicas, el dashboard 3020 (HTTP 200 al cierre) ni el servicio 8792 (sin
listener antes y después). El directorio de la corrida
(`C:\proyectos\binance-futures-data\diag-ws-recepcion-20261112a`, 3.41 KB)
queda fuera de Git; aquí solo se publica la evidencia compacta con sus hashes
(`hashes.json`).
