# EXTREME_MOVERS_OBJECTIVE
Fecha: 2026-10-16. Base auditada: b748d22e32d707cd761e81c4601897eb5ecac72e.
Estado: objetivo de producto reafirmado por el usuario; plan de implementacion
pendiente. Documento de alcance, no estrategia aprobada ni evidencia de edge.
Trazabilidad: F-EXTREME-OBJECTIVE-01 en FEATURE_BACKLOG.

## 1. Objetivo que no debe perderse
El producto debe descubrir movimientos extremos alcistas y bajistas del universo
elegible Binance Futures, evaluar continuacion frente a agotamiento/reversion,
y finalmente gestionar entradas, duracion y salidas con evidencia y riesgo.
El KPI final sigue siendo rentabilidad neta ajustada por riesgo, no cantidad
de tokens, indicadores, episodios, pruebas verdes ni apariencia del dashboard.

BTC/ETH/SOL son cobertura de prueba y candidatos posibles; NO constituyen por
defecto el universo de estrategia ni validan otras altcoins. Las corridas
120/600s comprueban infraestructura en sus ventanas; el replay del trio no
demuestra el selector de extremos sobre todo el mercado.
Ser top mover es criterio de descubrimiento; nunca entrada automatica.

## 2. Contraste con documentos existentes
- PRODUCT_GOAL ya pide universo Futures, movers tempranos, continuacion/reversion,
  paper y salidas dinamicas. MASTER_PLAN mantiene las fases y gates.
- SIGNAL_RESEARCH_PLAN contempla contexto BTC, agotamiento y espejo perdedores.
- Los contratos H1/H2/H3 y MAP-CANDIDATE-v1 son referencias de investigacion;
  no se aprueba el mapping por reafirmar el objetivo.
- El motor offline y la evaluacion V1 existen; datos del trio, costes supuestos,
  seleccion retrospectiva y held-out no pristino limitan sus conclusiones.
- Backtest y Paper Lab tienen pantallas reservadas; resultados offline estan
  conectados a Historical Research. El paper engine no se da por implementado.
- PLAN_ETAPA5 contiene supuestos historicos (incluido funding 8h) que deben
  reconciliarse al implementar con calendarios por simbolo, no copiarse.
No se avanza SUCCESS_GATES ni se altera el alcance de la fase activa.

## 3. Cuatro escenarios, con familias conservadas
| Escenario | Hipotesis investigable | Direccion candidata |
|---|---|---|
| Ganador con aceleracion sostenible | H1 continuacion alcista | LONG |
| Ganador que agota impulso y confirma giro | H2 agotamiento/reversion | SHORT |
| Perdedor con deterioro persistente | H3 continuacion bajista | SHORT |
| Perdedor que confirma recuperacion | H2 variante rebote, separada | LONG |
Estas direcciones describen hipotesis a contrastar, no autorizan operaciones.
Sobrecompra/sobreventa o subida/caida extrema no obligan a revertir.
H2 del mapping mecanico actual NO equivale a un fade ya validado.
Cada candidato puede terminar WATCH, DESCARTADO o SIN_ENTRADA.

## 4. Selector causal y cobertura
Auditar primero discovery/universe/classifier/opportunity y sus contratos.
Reutilizar lo existente; implementar solo carencias demostradas.
En cada instante T conservar universo conocido y elegible, instrumentos
incluidos/excluidos, ranking bilateral y referencia rolling24 usada.
Separar ticker 24h de retorno entre velas cerradas y explicar cambios del ancla.
No seleccionar retrospectivamente a los ganadores finales de un dia y atribuir
su deteccion al inicio. Retener denominadores y candidatos descartados para
medir precision, falsas alarmas y latencia de deteccion.
Deslistar/incluir instrumentos segun informacion conocida en T; registrar
UNKNOWN si no existe universo historico, sin inventar cobertura retrospectiva.

## 5. Contexto y aptitud de ejecucion
Medir volumen relativo a la propia historia del token, quote notional y
agresion compradora/vendedora por horizonte, spread/profundidad y frescura.
OI: unidades base y valorado separados; funding cotizado/calendario/liquidado
separados; VWAP con ancla; BTC como contexto sincronizado.
RSI/ATR, capitalizacion y nuevas features solo si su disponibilidad y utilidad
se demuestran. Capitalizacion baja no es requisito impuesto ni proxy de liquidez:
sin fuente fechada es UNKNOWN. No extrapolar $1M de BTC a otro token.
Si hay discovery amplio pero microestructura solo del trio, mostrar ese limite;
no declarar evaluados todos los candidatos.

## 6. Tiempo y gestion de posicion
Estudiar tiempo hasta excursion favorable/adversa, MFE/MAE, primer retroceso,
reanudacion, invalidacion y censura de horizontes, hasta 24h como alcance de
investigacion intradia; horizontes operativos se fijan en protocolo versionado.
Medianas historicas no son un tiempo universal de salida.
Riesgo/tamano/stop/salida temporal o por cambio de estado deben definirse antes
de la evaluacion; capital disponible y exposicion simultanea son vinculantes.
Una entrada debe registrar decision y evidencia ANTES de conocer su resultado.
Sin costes/fills disponibles, resultado condicionado o exclusion, nunca cero.

## 7. Implementacion incremental (sin ejecutar desde este documento)
A. Completar auditoria causal, paquete reproducible y presupuesto de costes
   de la fase offline activa. No detener ni sobrescribir el trabajo de otro agente.
B. Matriz del selector: cobertura actual vs universo objetivo, discovery vs
   streams realmente evaluados; criterios y motivos versionados de inclusion.
C. Replay del selector con informacion disponible en T y comparadores pertinentes.
   Si faltan ranking/universo/as-of historicos, preparar protocolo prospectivo;
   no fabricar un backtest de seleccion.
D. Llevar los resultados existentes a Backtest con fuentes/versiones visibles.
E. Construir Paper Lab sobre feed/ledger/riesgo/posiciones aislados segun contratos.
   Separar pausa de nuevas entradas, cierre de posiciones y fin de sesion.
F. Protocolo prospectivo precomprometido; adquirir o iniciar solo tras autorizacion
   correspondiente. Evaluar costes, fill, exposicion y divergencia backtest-paper.
G. Ejecucion controlada solo con gates y autorizacion explicita. El objetivo final
   es operar; cada bloqueo debe tener trabajo, evidencia y criterio de cierre.

## 8. Recorrido V2 y autoridad
| Vista | Funcion |
|---|---|
| Movers | Candidatos extremos de ambos lados, universo y calidad |
| Detalle token | Escenario, evidencia favorable/contraria, frescura y UNKNOWN |
| Oportunidades | WATCH/confirmacion/descarte; no confundir ranking con entrada |
| Backtest | Replay, seleccion, costes, entradas/salidas, cobertura y evaluacion |
| Paper Lab | Posiciones ficticias, riesgo, fills, abiertas/cerradas y decisiones |
| System/barra global | Monitor/feed/supervision; controles separados de paper |
El backend decide; el dashboard visualiza y solicita acciones al controlador.
Nunca alimentar la estrategia con estado renderizado del frontend.
La implementacion UI sigue la skill local dashboard-v2 cuando corresponda.

## 9. Aceptacion objetiva antes de declarar este objetivo cubierto
- Evidencia de descubrimiento de ganadores Y perdedores elegibles en T.
- Contar todos los candidatos, evaluados, descartados y causas, con denominadores.
- Demostrar cobertura de movimientos extremos mas alla del trio de infraestructura;
  cuantificar simbolos/episodios/regimenes y no inventar un minimo estadistico.
- Cada decision vinculada a version, dataset/run, disponibilidad y precios causales.
- Separar continuacion alcista, bajista, correccion y rebote; datos insuficientes
  no equivalen a resultado negativo ni escenario implementado.
- Simulacion con exposicion/costes/funding/fills y abiertas/cerradas separados.
- V2 muestra procedencia, incertidumbre y limites; dedup no implica independencia.
- Resistencia a costes y evaluacion reservada, sin ajustar retrospectivamente.
Sin esas evidencias: implementacion parcial; explicar el faltante concreto.
No convertir estas condiciones en nuevos SUCCESS_GATES sin su proceso formal.

## 10. Handoff al agente en curso
Este documento es suplemento del objetivo, no reemplaza su tarea autorizada.
Leer PRODUCT_GOAL, MASTER_PLAN y este archivo antes del siguiente plan.
Contrastar el selector real, proponer delta minimo y actualizar backlog/contratos
donde corresponde. No lanzar corridas, paper, ordenes ni calibracion por leerlo.
Reconciliar documentos con cambios selectivos; no sobrescribir archivos
concurrentes ni aplicar snapshots completos de una rama documental antigua.

## 11. BTC: activo elegible y contexto transversal (aclaracion 2026-10-16)
BTC tiene dos roles independientes: (a) candidato operable si cumple la misma
aptitud/hipotesis/riesgo que corresponda; (b) referencia de regimen y fuerza
relativa para cada altcoin. ETH/SOL pueden aportar contexto adicional cuando
se justifique; su pertenencia al trio no les da automaticamente el mismo peso.
Esto preserva SIGNAL_RESEARCH_PLAN (retorno relativo, correlacion, beta y lead/lag).

La observacion del usuario sobre co-movimiento es una hipotesis medible por
horizonte y regimen, no una ley: no se asume correlacion constante, causalidad
ni que BTC anticipe a cada altcoin. Tampoco se asume que los movimientos
contrarios sean pocos o pequenos; frecuencia y magnitud requieren medicion
sobre el universo observado en cada instante.

Para cada decision alt en T registrar contexto BTC at/before T, retorno,
velocidad/aceleracion y volatilidad en horizontes comparables (por ejemplo
1m/5m/15m/1h, a fijar y versionar), staleness y cobertura.
Medir retorno relativo R_alt(h)-R_BTC(h), correlacion/beta sobre prefijos
historicos y residual ajustado cuando haya muestras suficientes.
Sin datos suficientes: UNKNOWN, no relacion supuesta.
Distinguir:
- alineada: alt y BTC avanzan en igual direccion;
- fuerza relativa: alt supera a BTC, incluso cayendo menos;
- divergente: direccion contraria, hipotesis propia a investigar.
Alineacion no suma automaticamente evidencia independiente: precio alt,
ranking y contexto BTC pueden reflejar el mismo factor de mercado.

La estrategia candidata debe comparar con/sin contexto BTC fuera del conjunto
de ajuste, controlando costes, cobertura y seleccion, antes de usarlo como
filtro, ponderacion o regla de riesgo. Sin esa evidencia no bloquear por defecto
divergencias ni convertir cada subida/caida BTC en entrada/salida alt.

V2: contexto de mercado en Overview; en Movers retorno alt + BTC + relativo
con horizonte; en detalle/Oportunidades evidencia BTC favorable/contraria/UNKNOWN
y hora de observacion; Backtest comparacion condicionada; Paper Lab registra
el contexto BTC de la entrada y su evolucion, separado del motivo de salida.
Aceptacion: demostrar sincronizacion causal, casos alineados/divergentes,
missing/stale y valor incremental sobre el baseline sin BTC. No codigo ni
umbrales aprobados por esta aclaracion; fase activa y gates intactos.
