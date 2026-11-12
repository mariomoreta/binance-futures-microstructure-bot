# PRODUCT_GOAL

## Aclaración de investigación y dashboard — decisión del usuario 2026-11-12

**Estado:** dirección documental y propuesta visual; no implementación de una
estrategia nueva. Se investiga si existe expectativa neta favorable: todavía
no hay una estrategia rentable ni entradas casi perfectas acreditadas. Esta
aclaración no sustituye el experimento operativo v2 ni cambia su tarea activa.

### Hipótesis que debe poder evaluar el producto

Tras detectar en T un contrato con un movimiento extremo ya observado, estudiar
qué condiciones disponibles en T distinguen: continuación alcista, agotamiento
y reversión tras una subida, continuación bajista, y rebote tras una caída.
Los ejemplos humanos de movimientos del 10%, 20%, 30% o 50% describen el interés
del usuario; no fijan umbrales operativos ni autorizan cambiar el selector.
Seleccionar un gran movimiento no equivale a autorizar una entrada.

El objetivo es encontrar asociaciones repetibles con utilidad predictiva fuera
de la muestra de diseño, convertirlas en reglas de LONG/SHORT/abstención y
evaluar entrada, stop, gestión y salida con costes y riesgo. Una asociación no
prueba causalidad; más datos no garantizan acierto ni rentabilidad. El criterio
final sigue siendo expectativa neta y riesgo, no un porcentaje de acierto
cercano al 100%.

### Fuentes distintas y disponibilidad

- **Exchange:** libro, spread, operaciones y flujo agresor de Binance.
- **Derivados:** interés abierto, funding, marca/índice, prima y liquidaciones
  publicadas, con sus límites de cobertura.
- **On-chain:** actividad de tokens, wallets, swaps y liquidez de pools cuando
  la fuente los cubra. La liquidez DEX no sustituye al libro de futuros.
- **Contexto externo:** anuncios y narrativas/social; no es on-chain puro.

Para incorporar una variable futura se debe acreditar identidad (venue,
contrato, tipo, cadena/dirección cuando corresponda), unidades, ventana,
instante del evento, recepción y disponibilidad efectiva antes de decidir.
Un timestamp de bloque no demuestra que el bot conociera el dato en T.
Valores ausentes o sin trazabilidad siguen UNKNOWN; la regla debe declarar
previamente si esa ausencia impide decidir o solo limita la interpretación.
No se sustituye información ausente con información posterior.

La captura iniciada al seleccionar no acredita historia previa del movimiento.
Se necesita historia verificable o seguimiento prospectivo previo acotado,
con presupuesto y autorización propios. Se conservan comparadores, descartes,
no entradas y denominadores; observaciones repetidas del mismo episodio no son
pruebas independientes. No se usa el ganador final ni el maxGain posterior
como variable de entrada conocida en T.

### Diferencia con el experimento actual

El piloto operativo v2 utiliza los motores existentes y una hipótesis de
continuación (dirección derivada del signo del movimiento de 24 h y regla
causal); no elige todavía entre estos cuatro patrones mediante datos on-chain.
La referencia documental de Binance Skills Hub no añade adquisición ni señales.
El mínimo de selección de research-selector-v2 (0.02 puntos porcentuales más
ranking y filtros) no acredita por sí solo una definición de movimiento extremo.
Se registra esta diferencia sin cambiar parámetros o resultados congelados.

Se mantiene el objetivo de perpetuos y futuros con vencimiento. La cobertura
implementada y acreditada continúa limitada a perpetuos USD-M; la propuesta
visual no declara soporte de vencimientos ni ejecución real.

### Propuesta de presentación, reutilizando Dashboard V2

| Área | Contenido objetivo | Base reutilizable / faltante |
| --- | --- | --- |
| Universo y selección | Contratos elegibles, movimiento, motivo y referencia de selección | Movers y selección del piloto; unir por identidad/corrida |
| Ficha del contrato | Gráfico y contexto del mismo contrato y tiempo | Explorador; evitar paneles independientes de BTC/MINA como si fueran el seleccionado |
| Evidencia y patrón | Exchange, derivados y contexto on-chain con edad/cobertura; hipótesis y condiciones cumplidas/faltantes | Libro/flujo existentes; on-chain y patrones validados pendientes |
| Decisión y riesgo | LONG/SHORT/esperar, motivo, capacidad, entrada/stop/salida y límites | Backend/motores existentes; sin cálculo de decisiones en el navegador |
| Operaciones y resultados | Simulación o ejecución inequívocas; costes, funding, netos completos/condicionados y pendientes | Monitor del piloto y replay; no presentar reconstrucción posterior como orden en vivo |
| Diagnóstico | Fuente, frescura, errores, ledger y almacenamiento | Mantener visibles alertas; detalles técnicos desplegables |

Una única ficha debe compartir instrumento, run_id/observation_id cuando
existan y referencia temporal; poner paneles en la misma página no establece
ese vínculo. Las probabilidades solo se mostrarán tras evaluación y calibración
adecuadas; mientras tanto: «Sin estimación validada». Las áreas futuras se
etiquetarán PROPUESTA / NO IMPLEMENTADO; la ilustración es conceptual con datos
ilustrativos y no es evidencia de un build ni de rentabilidad.

No se borra código, motores, fixtures o evidencia histórica. Se propone apartar
de la vista principal las demostraciones y controles de ingeniería, separar el
archivo histórico y reducir duplicación. La expansión de UI sigue diferida:
esta decisión autoriza documentación e ilustración, no implementación.

### Orden para avanzar sin desviar el bloque activo

1. Cerrar la recepción de flujo dentro de la tarea y autorizaciones vigentes.
2. Evaluar el experimento v2 congelado; no añadir variables durante la corrida.
3. Definir después una pregunta acotada de patrones y unas pocas variables
   adicionales, con presupuesto, comparadores y criterio de descarte.
4. Comparar la misma regla con y sin esas variables en períodos independientes,
   incluyendo pérdidas, ejecución, costes y riesgo; descartar lo que no aporte.
5. Conectar al dashboard únicamente datos y decisiones persistidos y acreditados.

No se autorizan aquí nuevas conexiones, capturas, órdenes, cuentas, claves,
presupuestos, cambios de estrategia ni capas de IA. No se avanza ningún gate.

## Dirección operativa vigente — decisión del usuario 2026-11-06

**Objetivo final:** desarrollar un bot para operar contratos de futuros de Binance,
tanto perpetuos como contratos con vencimiento, que presentan movimientos
alcistas o bajistas extremos en su ventana rolling de 24 horas. Debe explorar por sí mismo el universo elegible, seleccionar
qué monedas investigar y evaluar oportunidades de entrada, dirección, stop-loss,
gestión de posición y salida. La meta es obtener expectativa neta positiva con
riesgo controlado; no se promete rentabilidad ni se afirma que ya exista.

### Recorrido del producto

1. Descubrir todos los contratos elegibles conocidos en T; no limitar el universo
   a BTC/ETH/SOL ni elegir retrospectivamente ganadores finales del día.
2. Autoseleccionar candidatos de ambos lados con política versionada. La
   investigación profunda es acotada por recursos y conserva comparadores,
   descartes y denominadores. Candidato no significa token operable.
3. Investigar con información disponible al decidir: movimiento y volumen,
   libro/profundidad/spread y flujo agresor, con frescura y cobertura explícitas.
   La relación flujo/liquidez es una hipótesis; no un edge ya probado.
4. Aplicar una regla predefinida y evaluable: LONG, SHORT o abstención. Un gran
   cambio de 24h no basta como entrada. Continuación, reversión y rebote son
   hipótesis distintas; UP no equivale automáticamente a LONG ni DOWN a SHORT.
5. Definir antes de evaluar: disparador, primera ejecución causalmente posible,
   precio/modelo de fill, tamaño y riesgo, stop-loss, gestión, salida y vencimiento.
   Evaluar también pérdidas, no entradas y posiciones abiertas al finalizar.
6. Comprobar fuera de los datos usados para diseñar la regla su resultado neto,
   exposición y drawdown bajo supuestos explícitos de ejecución, comisiones,
   spread/slippage y funding cuando corresponda. Lo no medido sigue UNKNOWN.
7. Validar en paper con los motores existentes y riesgo no eludible. El backend
   es la autoridad; el dashboard presenta la decisión y nunca la calcula.
8. Considerar ejecución real autónoma únicamente tras las evidencias requeridas
   y autorización humana específica. Esta dirección no habilita órdenes,
   credenciales, apalancamiento ni fondos reales.

Autonomía significa ejecutar reglas, selección, investigación y gestión
versionadas dentro de límites autorizados. No significa modificar umbrales,
estrategias o presupuestos continuamente para hacer aparecer ganancias.

### Prioridad de trabajo y criterio de cierre

- **Ahora:** revisar y cerrar una sola hipótesis operativa y el experimento
  propuesto en [EXPERIMENTO_OPERATIVO_V1](EXPERIMENTO_OPERATIVO_V1.md), aprovechando
  selector, book/flow y simulación existentes; no reiniciar su diseño.
- **Captura cerrada:** `public-pilot-1h-20261106a` aporta evidencia exploratoria.
  Sus 168 resultados por horizonte ya están resueltos; 165 parejas por horizonte
  son válidas para la asociación de flujo. No repetir para «completar 60m».
- Antes de otra adquisición: fijar pregunta, regla, períodos, datos mínimos,
  métrica principal, comparador, presupuesto y criterios de continuar,
  reformular, detener o declarar insuficiencia. No extender capturas
  automáticamente ni cambiar reglas después de ver resultados.
- Congelar expansión de dashboard, Paper Lab, gestores, nuevas features,
  conectores e IA. Reutilizar lo construido. Un arreglo solo entra en el camino
  crítico si se explica qué decisión económica o experimento desbloquea.
- Las limitaciones que no alteran la conclusión se registran sin otra ronda
  general de auditoría. Si una métrica no es acreditable, se excluye o se limita
  la conclusión; no se inicia una reparación indefinida.
- Separar tres evidencias: seleccionar movimientos diferentes; aprovecharlos con
  una regla causal; sostener resultado neto y riesgo en una comprobación
  independiente. Tests verdes y más volatilidad no acreditan las dos últimas.

Este bloque fija la dirección actual y prevalece sobre prioridades históricas
de expansión de interfaces o adquisiciones genéricas. No modifica parámetros,
SUCCESS_GATES ni autorizaciones de ejecución. La secuencia y el alcance del
agente que diseña el experimento se conservan; no es otra tarea de implementación.

### Cobertura obligatoria: perpetuos y futuros con vencimiento

Aclaración explícita del usuario, 2026-11-06: el objetivo incluye **ambos**:
contratos perpetuos (sin vencimiento) y futuros con vencimiento. No se limita
el producto final a PERPETUAL ni se presume que cada moneda disponga de ambos.
La elegibilidad se determina por instrumentos realmente listados y conocidos
en T, con tipo, familia/producto, moneda de margen/liquidación, tamaño de
contrato, estado y vencimiento identificados.

**Cobertura implementada hoy:** `research_selector.py` filtra PERPETUAL,
TRADING y USDT. La captura y resultados actuales corresponden a ese subconjunto;
no acreditan cobertura de contratos con vencimiento. Ese soporte es un faltante
explícito de producto, no una capacidad que se pueda declarar por cambiar texto.

El diseño del experimento debe separar cobertura y resultado por tipo de
contrato, identificar datos/componentes reutilizables y qué falta para incluir
vencimientos. No extrapolar automáticamente fills, funding, comisiones,
liquidación, roll/vencimiento o unidades de P&L entre productos. Toda evaluación
que cubra un solo tipo debe declararlo; no acepta como cumplido el objetivo de
ambos. Esta aclaración modifica el alcance documental, no filtros, código,
presupuestos ni autorizaciones de adquisición u operación.

Build a Binance Futures market-intelligence system that can:

1. Monitor the Futures universe in real time.
2. Identify rapidly moving symbols before/while they become major gainers or losers.
3. Understand the market conditions associated with those moves.
4. Classify market state.
5. Study continuation vs exhaustion/reversal.
6. Persist event snapshots.
7. Calculate forward outcomes statistically.
8. Discover evidence-backed strategies.
9. Paper trade them.
10. Dynamically manage position duration and exits.
11. Only after proven paper profitability, consider controlled automated execution.

## Final KPI

**Profitability and risk-adjusted expectancy.** Nothing else counts as success.

Explicitly NOT success metrics:

- Code volume
- Number of indicators
- Number of detected signals
- Dashboard polish without statistical backing
- Backtest returns without costs, slippage, and out-of-sample validation

## Anti-goals (until proven)

- A large 24h move alone must NEVER be treated as an entry signal.
- Never promise a fixed future profit such as "$30 expected". Future projections must be probabilistic distributions grounded in historical similar cases.
- No fixed holding time (e.g. "always hold 20 minutes"). Trade duration must be evidence-driven and market-state-driven.

## Human strategy hypothesis (unproven)

The user's historical manual approach involved trading unusually strong movers and
holding positions dynamically — roughly several minutes to sometimes around one hour —
depending on how the move evolved.

Status: `HUMAN_STRATEGY_HYPOTHESIS`. It informs what to measure (forward outcomes at
30s→60m, MFE/MAE, time-to-peak/trough, continuation vs reversal), but it is NOT
evidence and NOT an approved strategy. See `docs/STRATEGY_THESIS.md` and
`docs/EVENT_LABELING.md`.

## Objetivo de movimientos extremos reafirmado — 2026-10-16
El universo objetivo NO se restringe al trio de pruebas BTC/ETH/SOL.
Ganadores/perdedores son candidatos a continuacion, agotamiento/reversion
y rebote confirmado (H2 variante; H3 sigue continuacion bajista).
Ver docs/EXTREME_MOVERS_OBJECTIVE.md para selector causal, cobertura,
recorrido V2 y aceptacion. Objetivo reafirmado, implementacion parcial;
no constituye aprobacion de mapping ni umbrales ni lanzamiento de sesiones.
(Integracion 2026-10-17 desde review/extreme-movers-objective-20261016
hasta 7a4e872: portado selectivo sobre la evolucion actual; soportes,
stops dinamicos y Paper Lab conservan su secuencia.)
