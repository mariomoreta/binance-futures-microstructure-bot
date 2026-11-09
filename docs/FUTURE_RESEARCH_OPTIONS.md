# Opciones de investigacion futura

## Alcance vigente — 2026-11-09

Este documento conserva propuestas, no capacidades operativas. El registro de
aprobacion e implementacion es [FEATURE_BACKLOG](FEATURE_BACKLOG.md).
La prioridad sigue siendo el experimento operativo vigente y sus bloqueos
materiales; ver [TASK_QUEUE](TASK_QUEUE.md) y
[EXPERIMENTO_OPERATIVO_V2](EXPERIMENTO_OPERATIVO_V2.md).
Las prioridades de Dashboard V2 del registro inicial inferior son historicas.
Ninguna opcion de esta lista autoriza nuevas capturas, dependencias, cambios de
regla, presupuestos ni ejecucion real.

## F-GARCH-01 — Volatilidad y riesgo (propuesta diferida)

**Estado:** registro documental autorizado por el usuario el 2026-11-09;
evaluacion futura PROPOSED/DIFERIDA, integracion NOT IMPLEMENTED para esta
propuesta y utilidad en nuestros datos NO EVALUADA. No es requisito del
experimento operativo v2 ni modifica su regla congelada.

**Pregunta:** un GARCH(1,1), considerando errores Student-t como especificacion
candidata, mejora la estimacion de volatilidad frente a volatilidad historica
movil y EWMA lo suficiente para justificar su uso posterior en el riesgo del bot?

GARCH estima volatilidad condicional; por si solo no proporciona una entrada
LONG/SHORT, no anticipa cada salto y no acredita rentabilidad. El GARCH estandar
no sustituye libro/profundidad, flujo agresor, spread, slippage ni funding.
Usos candidatos: contextualizar movimientos extremos, dimensionar posiciones,
evaluar stops y abstencion. Son hipotesis separadas, no mejoras demostradas.

**Evaluacion minima antes de integrar:**

1. Cerrar el bloque operativo actual. Antes de ejecutar este estudio, fijar
   datos, frecuencia, horizontes, ventanas, metricas y criterio de descarte.
   Reutilizar datos/componentes existentes; faltantes no autorizan adquisicion.
2. Usar solo retornos de velas cerradas disponibles al ajustar/predecir,
   por instrumento y tipo de contrato. Separar entrenamiento y prueba
   cronologicamente, con ventanas moviles y varios periodos/regimenes;
   una captura de una hora no acredita generalizacion. Historia insuficiente,
   huecos o ajuste fallido => UNKNOWN, sin completar con datos futuros.
3. Comparar GARCH(1,1) con ambos baselines bajo las mismas muestras y horizontes.
   Evaluar error de pronostico de varianza (p. ej., QLIKE con proxy de varianza
   realizada explicitado), calibracion y estabilidad fuera de muestra.
4. Solo si mejora de forma consistente, proponer una prueba operativa separada,
   cambiando un unico uso inicial (preferentemente tamano de posicion), con
   mismas entradas/salidas, costes y presupuesto de riesgo comparable.
   Medir resultado neto condicionado a datos/costes conocidos, exposicion y
   drawdown; una mejor prediccion de volatilidad no demuestra beneficio neto.
5. No integrar si no supera los baselines, la mejora depende de un unico
   token/periodo o no justifica el coste de datos, computo y mantenimiento.
   Insuficiencia de datos no renueva automaticamente capturas ni autorizaciones.

**Cobertura:** el objetivo final incluye perpetuos y futuros con vencimiento.
La captura/seleccion vigente cubre solo perpetuos USD-M. Una evaluacion futura
debe separar instrumentos y tratar discontinuidades por vencimiento/roll;
GARCH no implementa ese soporte ni reemplaza sus costes especificos.

**Fuentes primarias (consultadas 2026-11-09; no validacion en nuestro bot):**

- [arch: modelos GARCH y errores Student-t](https://arch.readthedocs.io/en/stable/univariate/univariate_volatility_modeling.html).
- [arch: pronosticos y ventanas moviles](https://arch.readthedocs.io/en/stable/univariate/univariate_volatility_forecasting.html).
- [NYU V-Lab: alcance y limites de modelos de volatilidad](https://vlab.stern.nyu.edu/help/volatility_analysis).

## Registro inicial — 2026-10-13 (contexto historico)
Estado: DIFERIDO por instruccion del usuario. No implementar en el alcance actual.
Prioridad actual: bot operativo mediante Dashboard V2; ver OPERATIONAL_READINESS_INVENTORY.md.

| Opcion | Pregunta futura | Condicion de prueba |
|---|---|---|
| Muse/agente persistente | Aporta informes verificables o mejores experimentos? | Solo snapshots de lectura; comparar con baseline; sin ordenes ni cambios autonomos |
| Jev/Laya/AnyJev/Jebadiah | Mejora clasificacion/abstencion a coste razonable? | Identidad exacta, licencia, hardware/API, latencia y calibracion en nuestros datos |
| Noticias | Aporta informacion recibida antes del movimiento? | Fuente/identidad, published_at/received_at, duplicados/rumores, sesgo temporal y OOS |
| Kronos | Complementa features/modelos propios? | Baseline sin Kronos, cobertura compatible, costes, leakage, OOS y mejora incremental |

Fuentes consultadas (existencia, no equivalencia ni validacion de trading):
https://github.com/facebookincubator/muse-gadget-sdk
https://typesafe.ai/
https://github.com/NandhaKishorM/laya
https://github.com/nokia-applied-research/AnyJev
https://github.com/getainode/jebadiah
https://github.com/shiyu-coder/Kronos

No dependencias instaladas, cuentas conectadas, APIs contratadas ni implementacion
en esta entrega. Antes de considerar Muse verificar plataforma Windows y diferencia
entre agente, modelo y SDK; SDK abierto no implica modelo local ni acceso API gratis.
Estas opciones no son requisitos de O1-O5 y no desplazan sus bloqueadores.
