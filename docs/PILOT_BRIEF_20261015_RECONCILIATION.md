# Reconciliación del cierre del piloto brief 20261015T102519Z (sin nuevas corridas)

Fecha: 2026-10-16. Alcance: solo lectura + reporte. Sin cambios de
estrategias ni umbrales. Sin nuevas corridas Binance (fixtures y procesos
de prueba aislados en los tests).

## 1. Runtime 123.957s frente a 133s del registro — sin contradicción

Tres intervalos distintos, los tres correctos en su dominio:

- `duration_seconds = 120` — duración solicitada (`--duration 120`,
  preset brief).
- `final_summary.runtimeSeconds = 123.957` — tiempo interno del probe
  (monotónico del proceso). Startup 10:25:20.298Z, último summary
  10:27:24.465Z locales→UTC (~124.17s wall, 123.957s monotónicos).
  Incluye conexión (connected 10:25:26Z), ventana útil y drenaje;
  excluye el overhead del controlador antes del registro y el
  apagado/marcado terminal después del último log.
- Registro `started_at = 2026-10-15T10:25:20+00:00`,
  `last_exit.at = 2026-10-15T10:27:33+00:00`,
  congelado `elapsed/uptime = 133.0s` — intervalo del controlador
  (commit STARTING → marca terminal). Incluye ~0.6s de spawn/
  auto-registro más ~9s de apagado y marcado terminal después del
  `final_summary` (9.043s = 133.0 − 123.957).
- `expected_end_at = 2026-10-15T10:27:20+00:00` — 120s tras
  `started_at`; el probe la supera en 3.957s por drenaje gracioso,
  comportamiento ya conocido, no una deriva.

La V2 muestra ambos sin confundirlos: el contador terminal congelado
(133s) es el intervalo del registro; el informe conserva el
`runtimeSeconds` del probe (123.957s) como medida interna. Ninguno
sustituye al otro.

## 2. Los nueve cruces de funding — identidad y aptitud como evidencia

Identidad exacta (log `probe-20261015T102519Z.log`, 9 líneas
`extreme_funding_rate`):

- 10:26:01.002Z BTC 1.485e-05 (35) · ETH 4.783e-05 (35) · SOL
  1.677e-05 (35)
- 10:26:02Z BTC 1.485e-05 (36) · ETH 4.783e-05 (36) · SOL 1.677e-05
  (36)
- 10:26:03Z BTC 1.485e-05 (37) · ETH 4.783e-05 (37) · SOL 1.677e-05
  (37)

Misma tasa por símbolo en las tres evaluaciones consecutivas, con
`history_samples` 35→36→37: primer disparo en el borde del warm-up
(30 muestras) sobre serie casi constante, repetido cada segundo al
crecer la historia en 1. Clase artefacto-hipótesis ya documentada en
P1-01/P1-05/P1-09 (no validación de señal).

Aptitud: NO son evidencia de señal, NO validan umbrales, NO admiten
conclusión económica. Su único valor probatorio es de sanidad del
pipeline (el detector evalúa y persiste sobre entrega sana con 0
rechazos). Los umbrales siguen hipótesis.

## 3. Corrección de la atribución del aborto previo (20261015T000730Z)

Corrección sobre `PILOT_BRIEF_20261015_COMPLETED.txt §Veredicto`,
que caracterizaba el aborto anterior de forma concluyente como
"episodio de transporte, no defecto del motor":

- Factual y retenido: retraso observado en la ruta de entrega al host
  (bookTicker p50 0.54–0.71s / p95 8.5–16s / max ~23s; aggTrade p50
  0.6–2.5s; 3234/22130 = 0.146136 rechazos 100% skew-guard
  `|recibido−E| > 5000ms`; E−T del exchange en ms; reloj sano
  −864ms/RTT 558ms; 0 reconnects/parse/payload). El aborto por tasa
  funcionó según diseño y el umbral 0.05 queda intacto.
- NO aislado y por tanto corregido: el ORIGEN del retraso (red de
  entrega vs proveedor vs host local) no quedó aislado en esa ventana.
  No hubo referencia independiente coincidente (netprobe P1-14B.5) ni
  prueba de CPU/cadencia local retenida para esa ventana que descarte
  el host con evidencia. Decir "transporte" como causa concluyente
  excede lo probado; lo correcto es `origen UNKNOWN` con retraso
  observado en la ruta de entrega.
- Lo que sí prueba la ventana sana posterior (0.00% rechazos, mismos
  código/config/host): la cadena completa 120s con entrega sana; no
  prueba el origen de la ventana degradada anterior.

Sin cambios de estrategia, umbrales, batches ni ejecución. Esta
corrección no reabre el aborto ni autoriza nuevas corridas.
