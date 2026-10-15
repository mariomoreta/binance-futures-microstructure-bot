# Addendum correctivo — RUN_OBS10M_20261015_COMPLETED (solo lectura, sin nuevas corridas)

Corrige tres puntos del informe publicado (commit 67472e0), con
evidencia retenida. Nada más cambia: umbrales, estrategias, código y
conclusiones quedan intactos. Evidencia estructurada:
`RUN_OBS10M_20261015_RECONCILIATION.json`.

## 1. UUID correcto: 893f24029cba4cff96eaba7c0af094d0

El informe publicó `893f24029cba4cff888c33f89c566630`: ese valor NO
existe en la evidencia (0 filas) y su cola coincide con el UUID del
piloto brief (`6c2b922e95314bff888c33f89c566630`) — quimera de
transcripción al redactar, no dato medido.

Verificación exacta (no atribución temporal):
- 20/20 filas telemetry con timestamp dentro de la ventana del run
  llevan `893f24029cba4cff96eaba7c0af094d0` (span 23:07:04Z–23:16:34Z).
- `final_summary.run_id` leído del propio
  `logs/probe-runs/probe-20261015T230630Z.log` es idéntico.
- Las filas vecinas llevan otros UUID (piloto, aborto, 13-oct):
  separación por run_id, no por reloj.
- Correspondencia con `probe-20261015T230630Z`: el resumen final se
  leyó de ese fichero de log (stem del registro), su `run_id`
  coincide con las filas, y `research_flow/book` suman 246 filas con
  el mismo UUID (183+33+30, ver §2).

Donde el informe dice `...888c33f89c566630`, léase
`...96eaba7c0af094d0`.

## 2. Los 246 writes fueron a historical.db (no a microprobe.db)

Corrección a "historical.db sin cambios": el fichero no cambió de
tamaño (19181568B, reutilización de páginas), pero SÍ recibió las
246 filas. Ruta efectiva (código): `ResearchRecorder` se construye
sin `db_path` ni store inyectado en `probe.py:355-360`, luego
`_resolve_history()` (`research_recorder.py:249-259`) devuelve el
`HistoryStore` por defecto = `data/historical/historical.db`; cada
flush suma `_writes += 1` (`:406-425`, con dedup y omisión de
buckets vacíos).

Significado del contador: filas bucket volcadas (no bytes ni
batches): 183 flow_10s + 33 flow_1m + 30 book_1m = 246, todas con el
UUID del run (linkage exacto). Totales actuales 4215/1909/1818.
Delta por tabla: UNKNOWN (sin baseline por tabla pre-run y con
limpieza de retención concurrente posible). microprobe.db sí quedó
byte-idéntico (238927872B, caps con REPLACE). Sin journal en
ninguna DB: nada que recuperar, nada recuperado.

## 3. Funding: 245 eventos = 13 episodios independientes

Regla de episodio: mismo símbolo+tasa, huecos ≤5s, samples+1/s.
BTC 118 eventos en 6 episodios (tasas 5.583→5.332e-05),
SOL 118 en 6 (4.958→4.883e-05), ETH 9 en 1 (7.718e-05 constante).
Condición: la tasa salta a un nuevo extremo percentil y el detector
re-dispara ~1/s mientras permanece constante (inicios en samples
144/204/324/384/444/564, simétricos BTC/SOL). Repetición sin
información nueva dentro del episodio; dedup honesto: 13, no 245.
Clase artefacto-hipótesis (como los 9 del piloto, aquí con deriva
de tasa a lo largo de 600s). Sin valor de señal; umbrales y
estrategias intactos.

## Pendientes

- Baseline por tabla pre-run en el protocolo de la próxima ventana
  (para deltas exactos sin depender del contador).
- Nada que re-ejecutar: la ventana queda cerrada; no relanzar.
