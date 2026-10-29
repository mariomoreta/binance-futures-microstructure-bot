# Corrida 1 — FAIL en D1/D2/D3/D4/E1/E2/F3 (causa raiz unica, preservada)

La demo SI arranco sus recursos propios (manifest demo.json con
producer pid 23056 / market pid 6900, pid-files correctos, procesos
verificados por cmdline del SO). El criterio fallo por un DEFECTO del
producto corregido despues: `demoStatus` comparaba el campo `service` del
/health del servicio de mercado contra `market-stream/v1` (el CONTRATO),
pero el servicio declara `service = market-stream-service/v1`
(`contract_version = market-stream/v1`). Resultado: `source.available`
false durante toda la corrida -> chip `FUENTE NO DISPONIBLE` con la demo
en escucha, y la puerta previa de «Iniciar sesion» bloqueo el create
(comportamiento correcto de la puerta con flag equivocado): E1/E2 sin
sesion, F3 sin sesion que registrar, G sin boton habilitado (crash del
arnes por click en boton disabled, consecuencia de E).

D2/D3 con n=-1: la consulta WMI del arnes devolvio vacio bajo carga
(defecto del ARNES, no del producto; los procesos existian y se
verificaron aparte por cmdline). Corregido con reintentos en corrida 2.

Resultados PASS de esta corrida: A1-A3 (abrir la pagina no arranca nada),
B1-B3 (fuente ausente -> aviso previo, sin sesion huerfana),
F1-F2 (parada de la demo: manifest cerrado, productor y 8791 detenidos y
limpios). 8792 intacto durante toda la corrida.
