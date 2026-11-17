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
