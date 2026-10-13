# Inventario y ruta hacia operacion — 2026-10-13

## Mandato actual
El objetivo aprobado por el usuario es operar con el bot desde Dashboard V2.
V2 sera la interfaz principal; Python SSR queda como legado/rollback.
Muse, Jev, Laya, AnyJev, Jebadiah, noticias mediante agentes y Kronos quedan
exclusivamente como investigacion futura. No son dependencias del trabajo actual.
Esta entrega actualiza plan/documentacion; no implementa funciones ni habilita servicios.

## Bases y limites de la auditoria
- Backend publicado: 3cbbb1c9290e252ee18d6f0a466898f2f7b7dfee, review/entrega-nueve-archivos-6fd6091.
- Frontend: 27b7af59cb1e313169f49655161d66e043b5412d, dash-v2-03-token-detail.
- Otra rama V2 d4df766aae70116aa1afe8561618b065c3b4fe96 es antecesora:
  comparacion GitHub d4df766...27b7af5 = ahead 24 / behind 0.
- main d6801a5855bdac9d6620c69363b298b6881da5f7; phase1 bc327f1992b247e63069c0c8964af711a2862a7c.
- Inventario de codigo/documentos y pruebas offline; no acceso a bases de la PC,
  ninguna corrida de mercado en esta auditoria y ninguna certificacion visual nueva.
- Cada entrega posterior debe volver a verificar SHAs; no asumir ramas congeladas.
- Implementado, probado mecanicamente, comprobado en corrida y validado economicamente
  son columnas separadas. El destino es operar; los bloqueadores tienen tareas de cierre.

## Inventario de capacidades
| Capacidad | Evidencia de codigo/contrato | Estado observado | Brecha / cierre |
|---|---|---|---|
| Captura y universo | probe.py, discovery.py, universe_manager.py | Implementados | Reprobar cobertura, gaps/frescura y recursos en corrida conjunta V2 |
| Indicadores | returns/momentum/flow/book/open_interest/market_structure.py | Implementados | Contrastar unidades, horizontes, disponibilidad y paridad V2; no asumir todos los tokens tienen profundidad |
| Clasificacion y oportunidades | classifier.py, opportunity.py | Implementados como investigacion | No confundir candidatos con entradas ejecutables; conservar evidencia y version |
| Prospectivos y casos | prospective.py, events.py; CASE_STUDY_WUSDT_LUMIA_v1.md | Seguimiento e investigacion existentes | Dataset limpio, disponibilidad/run linkage, costes y OOS; W/LUMIA descriptivo |
| Persistencia | persistence.py v10; history_store.py v3 | Implementada | Compatibilidad V2, aislamiento, limites globales y medicion de crecimiento |
| Replay offline | backtest_offline.py; run_family_evaluation.py | Motor mecanico + runner | Calidad funding por trade/manifest, proxy vs mark real y version de implementacion |
| Control Python | control.py, host_process.py | Control/supervision existentes | launch_supervised_transaction existe pero SUPERVISED_LAUNCH_ENABLED=False; corregir suite e integrar ruta segura |
| V2 datos/BFF | frontend src/app/api/v1; canonical-market.ts y lectores | Lecturas/rutas existentes, integracion parcial | system-evidence exige operacional 9; historical-coverage exige historico 2 frente a backend 10/3 |
| V2 arranque | runtime/start/route.ts; launch-readiness.ts | Start rechazado, readiness bloqueada | Cablear lanzamiento atomico verificado y estado/parada; no usar start_probe como atajo |
| V2 backtest/paper | app/backtest/page.tsx, app/paper-lab/page.tsx, FutureWorkspace | Superficies futuras, no motores integrados | Conectar resultados versionados; implementar paper y portfolio |
| Estrategia ejecutable | RESEARCH_BACKTEST_CONTRACT_ETAPA3.md H1/H2/H3 | Contratos de estudio | Elegir una familia y congelar decision/entrada/invalidacion/salida/size/costes por version |
| Gestor de posiciones | POSITION_MANAGEMENT.md | Diseno, sin motor de posiciones verificado | Ciclo apertura/parciales/proteccion/cierre, reinicio y reconciliacion |
| Riesgo de trading | RISK_RULES.md | Diseno; observe-only actual no equivale a riesgo de posiciones | Limites, reserva de exposicion, bloqueo de entradas, proteccion y kill-switch no eludible |
| Ordenes Binance | Arbol src completo + AGENTS; no adaptador de ordenes verificado | Pendiente de implementar/verificar | Contrato de ejecucion, mocks/testnet, idempotencia, fills/rechazos y reconciliacion antes de capital |

## Hallazgos que siguen abiertos en 3cbbb1c
68/68 pruebas dirigidas y 10/10 del comparador reproducidas en copia Linux.
Log Windows publicado: 1029 ejecutados, 1F+8E, sin skips indicados => 1020 aprobados;
1011 en el cierre es inconsistente. Barrera registra 0 bloqueados/efectivos y hashes
iguales, pero la suite termina exit 1. Falta publicar log comparable de la base.
Un calendario continuo 12/16/20/24h con velas cada 12h, entrada 12h y holding hasta
24h devuelve funding_complete=True y funding_unknown=1: completitud de calendario
no es completitud contable. Un proxy de apertura de 4h se etiqueta fresh porque
cadencia=4h. El runner pierde unknown/gap/uncovered por grupo. Cambio de comisiones
mantiene engine_version=v4 y mismos input/config hashes: base fees=2.0/net=198.0,
nuevo fees=2.2/net=197.8. Se necesita revision/identidad de implementacion.
No reabrir correcciones verificadas: symbol, rechazo monocontrato, fee por pierna,
abiertas fuera de realizadas y cap uncovered.

## Secuencia con entregables y aceptacion
| Paquete | Dependencias | Entregable y prueba de cierre |
|---|---|---|
| O1 Integracion V2 + captura | Suite/aislamiento, schemas y control | V2 lee copias v10/v3 sin migrar; arranque atomico/status/stop, run_id y salud; screenshots reales y errores/UNKNOWN; corrida acotada conjunta autorizada |
| O2 Estrategia y replay | Calidad dataset/costes; correcciones motor | Una familia congelada, causabilidad de inputs, dev/OOS con tratamiento de solapamientos, sensibilidad y distribuciones; no elegir por resultado retrospectivo |
| O3 Paper + posiciones + riesgo | Contrato O2; feed O1 | signal->decision->risk->order intent->fill simulado->posicion->proteccion->exit->ledger; saldo/costes, parciales/rechazos, fallos y recuperacion comprobados |
| O4 Adaptador de ejecucion | Contratos riesgo/posiciones | Implementacion aislada con mocks; verificar API Binance oficial vigente, precision/minimos, reduce-only y proteccion, idempotencia, reconciliacion; prueba de entorno de exchange con limites explicitados |
| O5 Operacion controlada | Evidencia economica y tecnica O1-O4 | Configuracion de capital/riesgo revisada, autorizacion concreta de cuenta/capital/limites, primera operacion supervisada y auditoria completa |

O3/O4 pueden preparar contratos/pruebas aisladas en paralelo sin esperar investigacion
perfecta. No activan cuenta/ordenes ni cambian SUCCESS_GATES por existir.
H1 es candidato de primer piloto, NO seleccion metodologica cerrada; H2/H3 siguen
familias separadas. El rebote de perdedor pertenece a variante H2, no redefine H3.

## Paridad y corte V2
Migrar informacion necesaria, no duplicar funciones ciegamente: overview, movers,
detalle token, oportunidades/prospectivos, archivo/cobertura, system/runtime,
backtest y paper/performance segun sus motores. Cada campo lleva fuente, unidad,
horizonte, as_of, disponibilidad, version y calidad.
La preferencia por V2 queda aprobada; el corte funcional requiere evidencia de paridad,
seguridad, screenshots y corrida. Conservar SSR sin usarlo como sustituto de completar V2.
Backend decide; V2 presenta y solicita acciones al controlador, nunca calcula senales
operativas a partir de componentes renderizados ni crea un segundo supervisor.

## Almacenamiento y corridas
Ya hay retencion parcial: operacional snapshots 1000/observaciones 10000/rechazos 1000,
precio ~25.5h; research flow_10s 7d y flow_1m/book_1m 90d. No extrapolar esto a
todos los archivos/tablas. Medir bytes DB/indices/WAL/logs, filas por simbolo,
crecimiento por hora y colas descartadas. Probar rotacion, cuotas globales,
espacio insuficiente, backups consistentes y recuperacion.
Disco externo/archivo es futuro opcional; no depende de comprar hardware.
El DB activo requiere una ruta configurada y falla explicita si no esta disponible.

## Donde se documenta cada cosa
MASTER_PLAN: destino y arquitectura; ROADMAP: dependencias O1-O5; CURRENT_STATE:
inventario factual/evidencias/bloqueadores; TASK_QUEUE: proximo paquete; DECISIONS:
mandato aprobado y decisiones versionadas; FEATURE_BACKLOG: IDs/estados.
RESEARCH_BACKTEST_CONTRACT_ETAPA3/STRATEGY_THESIS: metodo; BACKTEST_READ_CONTRACT_V1:
resultados; PAPER_TRADING/POSITION_MANAGEMENT/RISK_RULES: motores;
DASHBOARD_V2_API_CONTRACTS/MIGRATION_PLAN/AGENT_HANDOFF: integracion/paridad/control;
COMMANDS: instrucciones comprobadas; SUCCESS_GATES: evidencia de promocion, sin cambios
en esta entrega. FUTURE_RESEARCH_OPTIONS: agentes, noticias y Kronos diferidos.
No guardar una decision vigente solo en cierres historicos.

## Protocolo de entrega
Ramas de revision y publicacion normal; SHA base/final, URL/compare, archivos acotados,
pruebas y logs completos, capturas cuando hay UI, capacidad operativa ganada,
bloqueador siguiente y prueba para cerrarlo. Revision independiente contra el pedido,
codigo exacto y omisiones. Si un gate falla, corregir o demostrar la causa: no convertir
el proceso en rondas infinitas de documentacion ni afirmar exito por conteos de tests.
