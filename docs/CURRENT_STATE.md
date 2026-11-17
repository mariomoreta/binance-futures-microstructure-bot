# Estado vigente — ventana 4 ejecutada COMPLETA con cierre normal (2026-11-16)

## Bloque 2026-11-16 (madrugada) — contraste flujo/profundidad vs continuacion/reversion (sin mercado)

**Autorizacion humana del 2026-11-16 (madrugada):** «INVESTIGACION OFFLINE DE LA
SENAL, SIN MERCADO» y «CIERRE OFFLINE DEL CONTRASTE Y DISEÑO DE LA SIGUIENTE
PRUEBA». Contrastes exploratorios sobre datos existentes; sin Binance,
consultas publicas, capturas, ordenes, relanzamientos, ventanas nuevas ni
cambios en la estrategia productiva. Dataset fuente verificado contra
manifiesto (10/10) antes y despues; no modificado.

**Rectificacion del alcance (vigente):** el contraste prueba la **alineacion
del flujo neto con el movimiento previo** (ratio_alienado =
signo(move_24h_pct) x (buy_notional - sell_notional) /
(bid_notional_top20 + ask_notional_top20), denominador > 0). No prueba si una
profundidad pequena frente a un flujo grande anticipa movimientos mayores
(intensidad); esa es una pregunta futura distinta (hipótesis A, no ejecutada).
Con mismo flujo y movimiento, variar la profundidad cambia el valor absoluto
del ratio pero no su signo, por tanto no cambia de grupo.

**Correccion del horizonte de precios:** cada observacion conserva
decision_ms, objetivo T + 60 min, open/close de ambas velas, precios inicial
y final, desfase de cada cierre y horizonte efectivo. Seleccion: ultima vela
1m plenamente cerrada en/antes de cada objetivo; desfase no negativo y < 60
000 ms; grid del minuto; no se usan cierres futuros ni velas antiguas como
sustituto silencioso. Resultado en las 161 aptas: desfases inicial y final
21 801-27 191 ms (todos < 60 000 ms); horizonte efectivo 3 600 000 ms (exacto)
en todas, 0 discrepantes; grid verificado. Todas las 161 siguen validas;
ninguna se convierte en cero ni se elimina del denominador.

**Resultado del contraste (161 escenarios, capacidad 1 aislada):**
- Regla sencilla (signo 24h): 65.8% de continuacion (106/161).
- Flujo a favor del movimiento previo: 61.6% de continuacion (45/73).
- Flujo contrario: 69.3% de continuacion (61/88).
El flujo a favor NO distingue mejor continuacion que la regla sencilla; el
flujo contrario muestra ligeramente mas continuacion. Resultado debil,
contradictorio o concentrado. No se incorpora el ratio a la estrategia
productiva.

**Evidencia:** `docs/evidence/exp-v2-ventana-4-20261116a-analisis-contrafactual/CONTRASTE-FLUJO-PROFUNDIDAD.md`;
derivados fuera de Git en
`C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-contraste-flujo-profundidad-20261116-v3\`
(regenerados desde fuentes verificadas, resultados anteriores NO reutilizados);
`tests/test_contraste_flujo_profundidad.py` 13 passed; regresiones
`test_analisis_contrafactual_ventana4.py` 16 passed,
`test_operativo_replay_offline.py` 7 passed.

| | |
|---|---|
| SHA base | `7b658e6b466a0ce24d018488d118dc33d08697f8` (local == remoto) |
| SHA de ejecucion del analisis | commit `6a1e268` (correccion del contraste flujo/profundidad) |
| Evidencia contraste | `docs/evidence/exp-v2-ventana-4-20261116a-analisis-contrafactual/CONTRASTE-FLUJO-PROFUNDIDAD.md` |
| Dataset original | intacto, solo lectura, 10/10 ficheros verificados contra manifiesto antes y despues |
| Lo que NO acredita | rentabilidad, edge, mejora predictiva del ratio flujo/profundidad, ventaja candidato/comparador (una sola hora, dependencia temporal) |

## Bloque 2026-11-16 (tarde) — ventana `exp-v2-ventana-4-20261116a` ejecutada, cerrada NORMAL, replay DIFERENCIAS

**Autorizacion humana del 2026-11-16 (tarde):** «UNA VENTANA PUBLICA CON
OPERACIONES SIMULADAS». Una sola corrida del protocolo V2 con independencia del
anfitrion acreditada antes de abrir mercado; sin ordenes reales, cuentas,
claves, capital, otras ventanas ni relanzamientos.

**Resultado:** cierre **NORMAL completo** — el primero del protocolo V2. Hijo
19:26:18.038Z → 21:36:21.292Z (7805,2 s): captura 3600 s (12/12 ciclos), settle
4200 s, espera contable cerrada `trabajo_resuelto` (~3 s, 0 pendientes, 2
consultas). `exit_code.txt` = 0; veredicto del lanzador por separado:
`terminacion_natural`, `cumplimiento_normal: true`. Manifiesto verificado
(10/10 ficheros). Consumos dentro de todos los techos (WS 979.570 mensajes, 1
reconexion, 0 errores; HTTP 671/2000; almacenamiento 7,1 MB/134 MB).

**Operativa:** 196 observaciones / 161 aptas / 35 descartadas (42 etiquetas,
7 solapadas, 0 sin motivo) / 44 seleccionadas sin observacion (10 warmup +
34 rotacion). 161 senales con direccion, 0 abstenciones, 159 rechazos por
capacidad, **2 entradas simuladas** (ambas comparadoras): AAVEUSDT SHORT stop
(neto CONDICIONADO −6,604) y 4USDT LONG horizonte (neto CONDICIONADO −0,3194);
suma CONDICIONADO −6,9234 **con funding UNKNOWN (cadencia_ambigua, no es cero
acreditado; no es P&L)**. 0 posiciones abiertas.

**Replay offline:** DIFERENCIAS — 161 comparadas, 159 coincidentes, 2
diferentes, 0 limitaciones; las 2 diferencias son **solo de etiqueta**
(`neto_motivo` ejecucion `cadencia_ambigua` vs replay `trabajo_resuelto`),
sin diferencias numericas. Veredicto conservado sin ajustes. Comparacion por
rol: **INSUFICIENTE** (0 operaciones COMPLETO en ambos roles). Una sola
ventana no acredita rentabilidad.

**Independencia del anfitrion:** acreditada antes de abrir mercado con un
proceso inocuo bajo el lanzador real lanzado por WMI (padre `WmiPrvSE`, fuera
del arbol del agente): muerte abrupta del anfitrion -> el hijo sobrevive y
termina limpio por mecanismo propio. La corrida real se lanzo por el mismo
mecanismo y no hubo incidente.

| | |
|---|---|
| SHA base | `ce2af020c666956ba35a1e1d41d0007c85d581a7` (local == remoto al iniciar) |
| Evidencia lanzamiento | `docs/evidence/exp-v2-ventana-4-20261116a-lanzamiento/` (LANZAMIENTO.md, presupuesto gate 13/13, prueba de independencia, hashes de scripts) |
| Evidencia cierre | `docs/evidence/exp-v2-ventana-4-20261116a-cierre/` (CIERRE.md tres capas, cierre_datos.json, hashes_cierre.json) |
| Dataset original | `C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a` (manifiesto verificado, solo lectura) |
| Derivados | `C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-replay-20261116\` (replay_operativo.json) |
| Lo que NO acredita | rentabilidad, edge, comparacion por rol (INSUFICIENTE), funding completo, calidad del selector; los umbrales siguen siendo hipotesis |



## Bloque 2026-11-16 (madrugada/tarde) — detector experimental SECUENCIA-PRESION-V1 (sin mercado)

**Autorizacion humana del 2026-11-16:** «PRIMER DETECTOR EXPERIMENTAL DE SECUENCIAS,
LOCAL Y SIN MERCADO». Contrastes exploratorios sobre datos existentes; sin Binance,
consultas publicas, capturas, ordenes, relanzamientos, cambios en la estrategia
productiva, dashboard, servicios, supervisores ni dependencias nuevas. Dataset
fuente verificado contra manifiesto (10/10) antes y despues; no modificado.

**Detector implementado:** `scripts/secuencia_presion_v1.py` (SECUENCIA-PRESION-V1,
EXPERIMENTAL, sin validacion economica). Reconoce una secuencia temporal de
presion agresora creciente, reduccion de liquidez contraria y avance del precio
sobre tres ventanas consecutivas y completas de un minuto. CLI con `--fuente` y
`--salida`, trabaja sin red, no crea motor de trading ni servicio.

**Resultado del detector sobre la ventana 4:** Ningun simbolo tiene 3 ventanas
validas consecutivas en `exp-v2-ventana-4-20261116a` (de 196 observaciones aptas,
solo 20 cumplen todos los campos requeridos; 163 fallan por
`huecos_detectados_en_feed` / `libro_huecos` en la integridad, 13 por
`flujo_ventana_completa` != true). Por lo tanto, el detector no puede ejecutarse
sobre esta captura: 0 simbolos con >=3 ventanas validas, 0 secuencias
evaluables. Los datos de la ventana 4 no tienen cobertura suficiente para este
detector. Esto es una limitacion de cobertura, no un error del detector.

**Configuracion congelada:** version `SECUENCIA-PRESION-V1`, ventana 60s, 3
ventanas, profundidad top-20, lado contrario, requiere ventana completa,
requiere integridad valida, condiciones: Q positivo creciente, profundidad
contraria decreciente, precio avanza en direccion. SHA-256 de la configuracion
registrado en el modulo.

**Pruebas de aceptacion:** 	ests/test_secuencia_presion_v1.py — 18 passed:
secuencia LONG valida, secuencia SHORT valida, presion creciente sin
profundidad decreciente -> SIN_PATRON, profundidad decreciente sin
presion alineada -> SIN_PATRON, precio sin confirmacion -> SIN_PATRON, ventana
incompleta -> DATOS_INSUFICIENTES, dato invalido (profundidad no positiva) ->
DATOS_INSUFICIENTES, ultima fuente despues del corte -> no deteccion
anticipada, aniadir datos futuros no cambia decision, simbolos distintos no
comparten historia, repetir mismo corte no duplica, disponibilidad tardia de
ventana anterior, precio no disponible -> DATOS_INSUFICIENTES, conflicto de
identidad explicita, CLI real con JSONL sintetico (LONG y
DATOS_INSUFICIENTES).
SIN_PATRON, precio sin confirmacion -> SIN_PATRON, ventana incompleta ->
DATOS_INSUFICIENTES, dato invalido (profundidad no positiva) ->
DATOS_INSUFICIENTES, ultima fuente despues del corte -> no deteccion anticipada,
aniadir datos futuros no cambia decision, simbolos distintos no comparten
historia, repetir mismo corte no duplica, CLI real con JSONL sintetico.

**Cobertura real (ventana 4, solo lectura):**
- Observaciones aptas: 196; simbolos unicos: 34
- Simbolos con >=3 ventanas validas: 0; con exactamente 3: 0
- Secuencias de 3 consecutivas posibles: 0
- Simbolos con 1-2 validas: 20; con 0 validas: 14
- Campos que faltan: flujo_ventana_completa (13), integridad del feed/libro
  (163 por huecos_detectados_en_feed y libro_huecos)

**Listado minimo para futura adquisicion:** por simbolo y ventana de 1 min:
buy_notional, sell_notional (flujo aggTrade), bid_notional_top20,
ask_notional_top20 (libro depth20@100ms), precio_base (libro_mid),
ventana_completa, integridad (sin huecos/invalidos/cruce),
disponibilidad.max_ms, decision_ms, symbol, observation_id. Historia previa:
>=3 ventanas consecutivas por simbolo, cada una completa y sin huecos. No
reconstruir ventanas de 30s desde agregados de 1 min.

**Hipotesis futura (no ejecutada):** pregunta A (intensidad): si un |ratio|
mayor se asocia con un |retorno posterior| mayor en 60 min. Variable en T:
|ratio|; resultado posterior: |retorno| en 60 min; horizonte 60 min con la
misma acreditacion de precios; referencia: regresion de |retorno| sobre |ratio|;
controles de dependencia por simbolo y ciclo; datos independientes necesarios
(captura nueva con autorizacion propia).

**Evidencia:**
`docs/evidence/exp-v2-ventana-4-20261116a-secuencia-presion-v1/SECUENCIA-PRESION-V1.md`;
derivados fuera de Git en
`C:\proyectosinance-futures-data\exp-v2-ventana-4-20261116a-secuencia-presion-v1\`;
SHA base: `4a7df47e89dbd1015ad89a6f1889ebf48d156c59`;
script `scripts/secuencia_presion_v1.py`;
pruebas `tests/test_secuencia_presion_v1.py` (13 passed);
regresiones `test_analisis_contrafactual_ventana4.py` (16 passed),
`test_operativo_replay_offline.py` (7 passed).

**Lo que NO acredita:** rentabilidad, edge, mejora predictiva del ratio
flujo/profundidad, ventaja candidato/comparador, utilidad operativa (una hora de
captura, dependencia temporal, simbolos repetidos). El detector no se conecta
al camino productivo.

| | |
|---|---|
| SHA base | `4a7df47e89dbd1015ad89a6f1889ebf48d156c59` (local == remoto) |
| SHA de ejecucion del analisis | commit `4a7df47` (detector SECUENCIA-PRESION-V1) |
| Evidencia detector | `docs/evidence/exp-v2-ventana-4-20261116a-secuencia-presion-v1/SECUENCIA-PRESION-V1.md` |
| Dataset original | intacto, solo lectura, 10/10 ficheros verificados contra manifiesto antes y despues |
| Lo que NO acredita | rentabilidad, edge, mejora predictiva del detector, utilidad operativa (una hora de captura, dependencia temporal, simbolos repetidos) |


## Bloque 2026-11-16 (madrugada/tarde) — detector experimental SECUENCIA-PRESION-V1: persistencia y cobertura (sin mercado)

**Autorizacion humana del 2026-11-16:** «PRIMER DETECTOR EXPERIMENTAL DE SECUENCIAS, LOCAL Y SIN MERCADO» y «CIERRE OFFLINE DEL CONTRASTE Y DISEÑO DE LA SIGUIENTE PRUEBA». Contrastes exploratorios sobre datos existentes; sin Binance, consultas publicas, capturas, ordenes, relanzamientos, ventanas nuevas ni cambios en la estrategia productiva. Dataset fuente verificado contra manifiesto (10/10) antes y despues; no modificado.

**Detector implementado:** `scripts/secuencia_presion_v1.py` (SECUENCIA-PRESION-V1, EXPERIMENTAL, sin validacion economica). Reconoce una secuencia temporal de presion agresora creciente, reduccion de liquidez contraria y avance del precio sobre tres ventanas consecutivas y completas de un minuto **realmente contiguas**. CLI con `--fuente` y `--salida`, trabaja sin red, no crea motor de trading ni servicio.

**Persistencia y idempotencia del CLI:**
- El lanzador lee el archivo de salida existente si existe y no duplica decisiones ya persistidas (misma observation_id).
- Si una observacion_id ya tiene una decision registrada con la misma configuracion (config_hash) y mismas ventanas, no se duplica.
- Si una observacion_id existente tiene datos contradictorios (misma observation_id pero ventanas o decision diferente), el CLI termina con codigo 3 y mensaje de conflicto, sin modificar el registro previo.
- Ejecutar el CLI dos veces sobre el mismo archivo de salida produce el mismo conjunto de decisiones (idempotencia).

**Resultado del detector sobre la ventana 4:** Ningun simbolo tiene 3 ventanas validas consecutivas en `exp-v2-ventana-4-20261116a` (de 196 observaciones aptas, solo 20 cumplen todos los campos requeridos; 163 fallan por `huecos_detectados_en_feed` / `libro_huecos` en la integridad, 13 por `flujo_ventana_completa` != true). Por lo tanto, el detector no puede ejecutarse sobre esta captura: 0 simbolos con >=3 ventanas validas, 0 secuencias evaluables. Los datos de la ventana 4 no tienen cobertura suficiente para este detector. Esto es una limitacion de cobertura, no un error del detector.

**Configuracion congelada:** version `SECUENCIA-PRESION-V1`, ventana 60s, 3 ventanas, profundidad top-20, lado contrario, requiere ventana completa, requiere integridad valida, requiere ventanas contiguas, condiciones: Q positivo creciente, profundidad contraria decreciente, precio avanza en direccion. SHA-256 de la configuracion registrado en el modulo.

**Pruebas de aceptacion:** `tests/test_secuencia_presion_v1.py` — 21 passed: secuencia LONG valida, secuencia SHORT valida, presion creciente sin profundidad decreciente -> SIN_PATRON, profundidad decreciente sin presion alineada -> SIN_PATRON, precio sin confirmacion -> SIN_PATRON, ventana incompleta -> DATOS_INSUFICIENTES, dato invalido (profundidad no positiva) -> DATOS_INSUFICIENTES, ultima fuente despues del corte -> no deteccion anticipada, aniadir datos futuros no cambia decision, simbolos distintos no comparten historia, repetir mismo corte no duplica, disponibilidad tardia de ventana anterior, precio no disponible -> DATOS_INSUFICIENTES, conflicto de identidad explicita, CLI real con JSONL sintetico (LONG y DATOS_INSUFICIENTES), CLI ejecucion dos veces no duplica, conflicto de identidad por CLI, dos simbolos no mezclan historias, CLI ternas sucesivas detectan posterior.

**Cobertura real (ventana 4, solo lectura):**
- Observaciones aptas totales (observaciones.jsonl): 196
- Observaciones aptas (apto_para_evaluacion=True): 161
- Símbolos unicos en observaciones aptas: 34
- research_flow_1m: 1265 filas; research_book_1m: 1197 filas; research_flow_10s: 6633 filas
- Intervalos (symbol, bucket_start) en flujo: 1265; en libro: 1197; emparejados: 1190
- Simbolos con ventanas validas (flujo+libro+precio+integridad OK): 0
- Ventanas validas totales: 0
- Simbolos con >=3 ventanas validas: 0; Ternas contiguas de 3 ventanas validas: 0
- Campos que faltan: flujo_ventana_completa (13 observaciones), integridad del feed/libro (163 observaciones)

**Listado minimo para futura adquisicion:** por simbolo y ventana de 1 min: buy_notional, sell_notional (flujo aggTrade), bid_notional_top20, ask_notional_top20 (libro depth20@100ms), precio_base (libro_mid), ventana_completa, integridad (sin huecos/invalidos/cruce), disponibilidad.max_ms, decision_ms, symbol, observation_id. Historia previa: >=3 ventanas consecutivas por simbolo, cada una completa y sin huecos. No reconstruir ventanas de 30s desde agregados de 1 min.

**Hipotesis futura (no ejecutada):** pregunta A (intensidad): si un |ratio| mayor se asocia con un |retorno posterior| mayor en 60 min. Variable en T: |ratio|; resultado posterior: |retorno| en 60 min; horizonte 60 min con la misma acreditacion de precios; referencia: regresion de |retorno| sobre |ratio|; controles de dependencia por simbolo y ciclo; datos independientes necesarios (captura nueva con autorizacion propia).

**Evidencia:**
`docs/evidence/exp-v2-ventana-4-20261116a-secuencia-presion-v1/SECUENCIA-PRESION-V1.md`;
derivados fuera de Git en
`C:\proyectosinance-futures-data\exp-v2-ventana-4-20261116a-secuencia-presion-v1\`;
SHA base: `4a7df47e89dbd1015ad89a6f1889ebf48d156c59`;
script `scripts/secuencia_presion_v1.py`;
pruebas `tests/test_secuencia_presion_v1.py` (21 passed);
regresiones `test_analisis_contrafactual_ventana4.py` (16 passed),
`test_operativo_replay_offline.py` (7 passed).

**Lo que NO acredita:** rentabilidad, edge, mejora predictiva del ratio flujo/profundidad, ventaja candidato/comparador, utilidad operativa (una hora de captura, dependencia temporal, simbolos repetidos). El detector no se conecta al camino productivo.

| | |
|---|---|
| SHA base | `4a7df47e89dbd1015ad89a6f1889ebf48d156c59` (local == remoto) |
| SHA de ejecucion del analisis | commit `b7a1e08` (detector SECUENCIA-PRESION-V1) |
| Evidencia detector | `docs/evidence/exp-v2-ventana-4-20261116a-secuencia-presion-v1/SECUENCIA-PRESION-V1.md` |
| Dataset original | intacto, solo lectura, 10/10 ficheros verificados contra manifiesto antes y despues |
| Lo que NO acredita | rentabilidad, edge, mejora predictiva del detector, utilidad operativa (una hora de captura, dependencia temporal, simbolos repetidos) |
