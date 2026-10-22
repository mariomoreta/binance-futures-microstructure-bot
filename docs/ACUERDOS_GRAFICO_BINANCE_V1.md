# Acuerdos: gráfico Binance y Paper Lab

Fecha: 2026-10-21. Estado: requisitos acordados; implementación y aceptación pendientes. Documento integrado al repositorio canónico C:\proyectos\binance-futures-microstructure-bot. ID: F-CHART-BINANCE-01. Autoriza el objetivo documental; el código y su aceptación siguen pendientes.

## Objetivo
Buscar cualquier contrato elegible Binance USD-M disponible y mostrar su histórico y actualizaciones vivas, con indicadores compartidos y trazabilidad de decisiones. Phinvio es referencia funcional; usar la biblioteca pública Lightweight Charts, sin depender de sus precios ni de su backend.

## Flujo al buscar un símbolo
1. Backend mantiene catálogo público de contratos con identidad, estado y temporalidades soportadas. Diferenciar spot de futuros; no prometer monedas no listadas o cobertura inexistente.
2. Usuario busca y selecciona símbolo/temporalidad. Abrir gráfico no abre operación ni inicia el monitor. Si el servicio de datos autorizado está detenido, mostrar histórico y estado sin conexión.
3. Entregar tramo inicial desde caché/almacenamiento; adquirir faltantes mediante fuentes públicas solo cuando el servicio y alcance estén autorizados. Mostrar cobertura y errores, nunca fabricar velas.
4. Mientras llega el histórico, suscribir/bufferizar actualizaciones y reconciliarlas por símbolo, intervalo, tiempo y secuencia cuando exista. Evitar huecos y duplicados entre snapshot y stream.
5. Actualizar vela en formación con observaciones reales; confirmar cierre y registrar. Distinguir OHLC provisional de cerrado.
6. Al desplazar hacia atrás, paginar histórico. Cambiar símbolo descarta respuestas tardías del símbolo anterior y libera solo suscripciones de visualización sin consumidores.

## Fuente compartida y autoridad
Binance -> colectores existentes -> validación/caché/velas -> indicadores backend -> evaluador y API del dashboard -> gráfico. No crear segundo motor económico ni feed independiente por pestaña. Visualización bajo demanda y selección automática son capacidades diferentes. Cerrar pestaña no interrumpe sesiones ni suscripciones necesarias del bot.

## Indicadores y operaciones
Inventariar primero cálculos existentes. Indicadores con versión, unidades, timestamps y disponibilidad; distinguir provisional/cerrado y UNKNOWN. Mostrar señal, decisión, entrada pendiente, fill, stop, objetivo si existe y salida desde eventos backend. Ningún marcador de salida sin exit_executed. Backend valida modificaciones; stops arrastrables diferidos de la primera versión. El bot procesa valores numéricos, no imágenes. La equivalencia visual no demuestra rentabilidad.

## Almacenamiento y recuperación
No almacenar todo tick de todo símbolo por visualizar un gráfico. Catálogo ligero, caché acotada, histórico paginado, retención por componente y evidencia durable para decisiones/operaciones. Ventana en memoria para datos de alta frecuencia según política. Reconexión con detección y reparación de huecos; mostrar frescura, desconexión y cobertura. Datos usados por evaluación deben conservar procedencia y permitir reproducción; retención y exportación no deben borrar la única evidencia de una operación.

## Alcance y secuencia
Desktop web, presupuesto cero. REA opcional para investigación externa, no dependencia del bot. Cerrar defectos actuales Paper Lab; luego componente gráfico compartido validado con fixtures y contrato causal; después adaptador vivo y ventana pública limitada autorizada por separado. Este documento no autoriza colectores, Binance, órdenes ni ejecución con capital. Sin móvil, Flutter o IA/Kronos en esta fase.

## Aceptación
Búsqueda de contrato elegible; histórico y vela viva coherentes; cambio de símbolo sin contaminación; carga de histórico bajo demanda; desconexión y reconexión sin ocultar huecos; indicadores iguales a los del backend en el mismo T; marcas ligadas a session/run/event IDs; cierre de pestaña sin pérdida de sesión; presupuesto de memoria/disco medido. Pruebas visuales, de integración y financieras son estados diferentes.

## Incorporación documental pendiente
Integrar estos acuerdos con los contratos existentes y enlazarlos desde CURRENT_STATE, TASK_QUEUE, DECISIONS y FEATURE_BACKLOG. No declarar implementado por añadir documentación. El agente debe identificar capacidades ya existentes, pendientes y criterios de aceptación antes de editar; no duplicar planes ni motores.

## Fuente de referencia e interoperabilidad
Inspección pública 2026-10-21: Phinvio (https://phinvio.com/) sirve Lightweight Charts 5.2.1 y módulos separados de datos, gráfico, tiempo real y práctica. Su cliente usa EventSource/SSE; el comentario del cliente describe WebSockets de exchanges en servidor, no inspeccionado. No se comprobó su contabilidad ni operación autenticada. La implementación propia usará fuentes Binance y biblioteca oficial, sin depender de endpoints Phinvio ni copiar su código propietario. Conservar NOTICE/atribución de Lightweight Charts y revisar licencia de la versión fijada. Referencias: https://tradingview.github.io/lightweight-charts/docs y https://github.com/tradingview/lightweight-charts. REA: https://github.com/morluto/rea, opcional para investigación, sin instalación en este bloque.

## Contrato mínimo a definir antes de implementar
Identidad: venue, tipo de contrato, símbolo canónico, intervalo y IDs de sesión/run/evento. Tiempos UTC con unidad explícita: evento/venue, recepción, disponibilidad, cierre y reloj de simulación. Velas con estado abierto/cerrado y procedencia; indicadores con nombre/versión/unidades/validez/warm-up; estado de conexión con última actualización y cobertura. Eventos distinguen señal, solicitud/entrada pendiente, fill ejecutado, cambio de protección aceptado y salida ejecutada. Controles de avance vienen del backend y no de la longitud de la respuesta pública. No interpolar precios como observaciones ni tomar decisiones desde el dibujo.

El adaptador debe mapear milisegundos internos a las unidades del gráfico explícitamente, evitar duplicados/actualizaciones fuera de orden y descartar respuestas tardías tras cambiar símbolo. SSE o WebSocket es decisión de implementación pendiente basada en el camino existente; no adoptar un segundo canal de adquisición de Binance por cada navegador.

## Secuencia y dependencia actual
1. Resolver los bloqueos observados en 2a17088: _run_backtest_on_prefix pasa todas las velas al motor pese al nombre; canStep no permite vigilancia y onDecide está vacío; _finalize_stop_exit vuelve a calcular salida/costes sin política gap canónica. Corregir y demostrar con fixtures/controles reales antes de declarar cerrado.
2. Inventariar productores actuales de velas/indicadores y sus límites. El probe y Backtest ya existen; no reconstruirlos.
3. Implementar gráfico compartido y contrato causal con fixtures, revisión visual de escritorio y eventos reconciliados.
4. Implementar búsqueda de contratos, histórico paginado y adaptación del feed existente; probar desconexión, cambio de símbolo y recuperación con datos controlados.
5. Preparar preflight, duración, símbolos y presupuesto de almacenamiento; una ventana pública Binance requiere autorización separada. Comprobar gráfico y paper de extremo a extremo.
6. Completar selector causal de extremos, gestión/riesgo/caja/funding paper y evaluación prospectiva versionada. Rentabilidad no demostrada; ninguna animación, indicador o fixture sustituye esta evaluación.

## Estado y evidencia del registro
Base documental revisada: 2a170887a5b232bba4930daa15437764160dea31. La lectura del checkout confirma ausencia de lightweight-charts en frontend/package.json a esta base. Este bloque modifica solo documentación; no instala paquetes, inicia servicios, prueba una nueva corrida ni valida visualmente el dashboard. Los tres bloqueos citados son revisión de código, no reproducción de pruebas realizada aquí. El informe anterior declara pruebas y HTTP integrado; eso no resuelve las discrepancias de código por sí solo.

## Actualización 2026-10-21 — implementación parcial sobre fixtures

Sobre la base `ac716d3`, los pasos 2–3 de la secuencia se ejecutaron **solo para Paper Lab y solo con fixtures**: se inventariaron los productores existentes, se fijó el contrato `paper-chart/v1` (`docs/PAPER_CHART_CONTRACT_V1.md`) y se implementó el gráfico interactivo con `lightweight-charts@5.2.1` (Apache-2.0, TradingView) en `/paper-lab-live`. No se ejecutó corrida Binance, adquisición, feed vivo, búsqueda de contratos, histórico paginado ni indicadores (el backend no produce volumen ni indicadores para Paper Lab). Los estados implementado/probado/servido/visual y la aceptación A–H con controles reales están en `docs/CURRENT_STATE.md`, `docs/DECISIONS.md` y `docs/FEATURE_BACKLOG.md`. La inspección visual por modelo no estuvo disponible: no se declara PASS visual. Los pasos 4–6 de la secuencia siguen sin ejecutarse.
