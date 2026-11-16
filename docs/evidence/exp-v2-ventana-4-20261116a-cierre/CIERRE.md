# CIERRE — `exp-v2-ventana-4-20261116a`

Única ventana pública autorizada por el usuario el 2026-11-16 (protocolo
`EXPERIMENTO_OPERATIVO_V2`). Sin órdenes reales, cuentas, claves ni capital:
todas las operaciones son SIMULADAS; los datos son públicos (WS/REST Binance
USD-M). Base de código `ce2af020c666956ba35a1e1d41d0007c85d581a7` con SHA-256
de los scripts en `../exp-v2-ventana-4-20261116a-lanzamiento/`.

Resultado de una frase: **cierre NORMAL completo del protocolo V2 (el primero),
196 observaciones / 161 aptas, 2 entradas simuladas (ambas comparadoras), ambas
cerradas (1 stop, 1 horizonte), neto CONDICIONADO agregado −6,9234 USDT con
funding UNKNOWN (no es P&L), replay DIFERENCIAS con 2 diferencias de etiqueta
sin diferencias numéricas.** Una sola ventana NO acredita rentabilidad
generalizable.

## A. Conclusión técnica

### Fases y tiempos

| Fase | Inicio | Fin | Duración |
| --- | --- | --- | --- |
| Lanzamiento (WMI, fuera del árbol del agente) | 19:26:19Z | — | lanzador PID 21376, padre `WmiPrvSE.exe` |
| Hijo (piloto) | 19:26:18.038Z | 21:36:21.292Z | 7805,2 s |
| Captura | 19:26:18Z | 20:26:18Z | 3600 s (12/12 ciclos, 0 saltados) |
| Settle | 20:26:18Z | 21:36:18Z | 4200 s |
| Espera contable | 21:36:18Z | 21:36:21Z (cierre `trabajo_resuelto`; plazo máx era 06:36:18Z) | ~3 s, 0 pendientes finales, 2 consultas (1/símbolo) |

- **Cierre:** `exit_code.txt` = **0** (código real del hijo, `Popen.wait()`).
  Veredicto del lanzador **por separado** (`cierre.json`): `terminacion_natural`,
  `cumplimiento_normal: true`, `codigo_lanzador: 0`, `exceso_maximo_total_s: 0`,
  `incumplimiento_plazo_global: false`. `stderr.log` vacío.
- **Transporte:** WS 25 conexiones, 979.570 mensajes, **1 reconexión**, 0
  errores, rutas `wss://fstream.binance.com/public` y `/market` (url_shape
  `/public/stream` y `/market/stream`). HTTP 671/2000 intentos, 0 reintentos,
  peso 1139/5000, `funding_rate_5m` 2/500, sin bloqueos.
- **Almacenamiento:** 7.097.601 B contabilizados / techo 134.217.728 B; total
  en disco 7.668.258 B. Sin presión de techos.
- **Integridad:** manifiesto verificado — 10 ficheros con bytes y SHA-256
  correctos (verificado tras el cierre). Checkpoints escritos en los 3 puntos
  del protocolo (`transicion_captura_settle`, `transicion_settle_espera_contable`,
  `lote_operativo_persistido`; 29.107 B). La recuperación parcial **no fue
  necesaria** (cierre normal): el modo quedó probado en el bloque anterior y
  esta vez no se activó.
- **Independencia del anfitrión:** acreditada antes de abrir mercado con un
  proceso inocuo reutilizando el lanzador real (muerte abrupta del anfitrión →
  el hijo sobrevive y termina limpio por mecanismo propio). Evidencia:
  `../exp-v2-ventana-4-20261116a-lanzamiento/independencia_corrida3_kill.json`.
  En esta corrida no hubo incidente y el anfitrión no murió.

### Reconstruibilidad (replay offline)

`research_operativo_replay.py --run-dir <run> --out <dir derivado separado>`,
**sin red**: **DIFERENCIAS** (código 4) — 161 comparadas, **159 coincidentes,
2 diferentes, 0 limitaciones**, config operativa y procedencia acreditadas.
Las 2 diferencias son **únicamente de etiqueta** `neto_motivo` (ejecución
`cadencia_ambigua` vs replay `trabajo_resuelto`); ambas declaran funding
incompleto y el neto CONDICIONADO es idéntico; **sin diferencias numéricas**.
Veredicto conservado tal cual: no se ajustan pruebas para obtener EQUIVALENTE.
Economía del replay: 2/2 operaciones, neto_conditionado 2/2, unknown 159/159 en
ambas fuentes.

## B. Conclusión de calidad

### Funnel global

| | seleccionadas | observadas | aptas | descartadas | sin observación |
| --- | --- | --- | --- | --- | --- |
| candidate | 144 | 135 | 130 | 5 | 9 |
| comparator | 96 | 61 | 31 | 30 | 35 |
| **total** | **240** | **196** | **161** | **35** | **44** |

### Descartes (35 filas únicas, 42 etiquetas)

`dato_obsoleto_flujo` 28, `flujo_ventana_incompleta` 13, `dato_obsoleto_libro` 1.
Solapamiento: 42 etiquetas en 35 filas → **7 filas con motivo solapado**.
**0 filas sin motivo.** Coherente (los motivos se acumulan, no son mutuamente
excluyentes).

### Seleccionadas sin observación (44) — desglose por rol y ciclo

| Ciclo | candidate | comparator | | Ciclo | candidate | comparator |
| --- | --- | --- | --- | --- | --- | --- |
| 00 | 0 | 2 | | 06 | 2 | 7 |
| 01 | 1 | 5 | | 07 | 1 | 7 |
| 02 | 2 | 6 | | 08 | 2 | 1 |
| 03 | 1 | 5 | | 09 | 2 | 2 |
| 04 | 0 | 6 | | 10 | 1 | 0 |
| 05 | 0 | 3 | | 11 | 1 | 7 |

(atribución: 10 de 44 seleccionadas el mismo ciclo de su entrada al seguimiento
— warmup, sin datos suficientes aún; 34 de 44 seleccionadas a nivel universo
pero no seguidas en la decisión — rotación; la observación exige streams
activos del símbolo. Detalle fila a fila en `cierre_datos.json`.)

### Comparación por rol

**INSUFICIENTE** (0 operaciones COMPLETO en candidate y comparator; 11/12
ciclos con ambos roles aptos). El denominador no permite comparación: de las
2 operaciones ejecutadas ambas son comparadoras y ambas quedan CONDICIONADO
(funding incompleto), y ningún candidato ejecutó. No se extrae conclusión de
rendimiento por rol.

## C. Conclusión operativa / económica

- **Señales:** 161 señales con dirección (todas las aptas produjeron dirección);
  **0 abstenciones**; **159 rechazos por capacidad** (`RECHAZADA_CAPACIDAD`,
  sin posición; `qty=0`, neto UNKNOWN por rechazo); **2 entradas simuladas
  ejecutadas** (capacidad global 1, prioridad determinista).
- **Posiciones:** 2 cerradas (1 por STOP, 1 por HORIZONTE), **0 abiertas al
  final**; exposición realizada 5.220.000 ms (87 min).
- **Resultado agregado (NO es P&L acreditado):** bruto −3,7184; comisiones
  2,0031; spread/slip 1,2019; **neto COMPLETO n=0** (ningún funding acreditado
  completo; `funding_completamente_acreditado: null` → nunca se contabiliza
  funding como cero); **neto CONDICIONADO n=2: suma −6,9234** (min −6,604,
  media −3,4617, max −0,3194). Ganadoras 0; perdedoras 2; breakeven 0/0.

### Operaciones publicadas (simuladas)

**Op 1 — AAVEUSDT | SHORT | comparator** (`AAVEUSDT|1794857301800`)

| Campo | Valor |
| --- | --- |
| Decisión | 19:43:38Z (1943) |
| Entrada | 19:46:40Z @ **107.18** (qty 9.3301 ≈ 1000 USDT) |
| Stop efectivo | **107.6556** (+0,5 % sobre entrada, SHORT) |
| Salida | 20:13:40Z @ **107.7159**, motivo **stop** |
| Bruto / fees / spread+slip | −5,0000 / 1,0025 / 0,6015 |
| Neto | **CONDICIONADO −6,604** |
| Funding | **UNKNOWN, no cero**: motivo `cadencia_ambigua`; sin settlements en la ventana de posición; 1.620.000 ms sin cubrir; 0 huecos; 0 settlements desconocidos |

**Op 2 — 4USDT | LONG | comparator** (`4USDT|1794859045223`)

| Campo | Valor |
| --- | --- |
| Decisión | 19:57:25Z |
| Entrada | 19:58:00Z @ **0.008583** (qty 116.509,38 ≈ 1000 USDT) |
| Stop efectivo | **0.00852715** (−0,5 % sobre entrada, LONG) |
| Salida | 20:58:00Z @ **0.008594**, motivo **horizon** (60 min) |
| Bruto / fees / spread+slip | +1,2816 / 1,0006 / 0,6004 |
| Neto | **CONDICIONADO −0,3194** |
| Funding | **UNKNOWN, no cero**: motivo `cadencia_ambigua`; 1 settlement cubierto (20:00:00Z, rate 2,11 bps `settled`, mark 0.008599, importe +0,21139); 3.479.998 ms sin cubrir; 0 huecos; 0 settlements desconocidos |

Funding de las consultas: `/fapi/v1/fundingRate` (método `observed-settlements`,
1 consulta por símbolo, máx 3 ✓; 13 settlements regulares para 4USDT con
cadencia observada ~4 h, 0 para la ventana de AAVEUSDT). En ambos casos
`interval_ms: null` (el endpoint de historia no acredita el intervalo vigente
del símbolo) → calendario no acreditado → **funding UNKNOWN, nunca cero**.
Los netos quedan CONDICIONADO y **no son P&L**.

### Denominador y limitación

Capacidad global 1: de 161 señales aptas, solo 1 slot por decisión → 159
rechazos por capacidad. **Una sola ventana con 2 operaciones simuladas no
acredita rentabilidad generalizable ni permite comparar candidatos vs
comparadores (INSUFICIENTE).** No se concluye edge; los umbrales siguen siendo
hipótesis. `exp-v2-ventana-2-20261112a` sigue INSUFICIENTE; la ventana 3 sigue
INTERRUMPIDA (su `run_id` consumido); esta ventana 4 queda **COMPLETA con
DIFERENCIAS de etiqueta en el replay**.

## Artefactos

- Dataset original (solo lectura): `C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a` (manifiesto verificado).
- Derivados separados: `C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-replay-20261116\replay_operativo.json`.
- Datos compactos de este cierre: `cierre_datos.json` (fases, funnel por ciclo,
  sin-observación fila a fila, decisiones, operaciones, consumos, replay).
- Hashes de cierre: `hashes_cierre.json`. Lanzamiento: `../exp-v2-ventana-4-20261116a-lanzamiento/`.
