# PRODUCT_GOAL

## Dirección operativa vigente — decisión del usuario 2026-11-06

**Objetivo final:** desarrollar un bot para operar contratos perpetuos de Binance
USD-M que presentan movimientos alcistas o bajistas extremos en su ventana
rolling de 24 horas. Debe explorar por sí mismo el universo elegible, seleccionar
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
