# HISTORICAL_STRUCTURE_AND_EXIT_PLAN
Fecha: 2026-10-16. Estado: REQUISITO DE INVESTIGACION/DISENO, NO implementacion.
Base documental: bb99974. F-STRUCTURE-EXIT-01.
No aprueba parametros, estrategia, sesiones paper ni ordenes.

## Objetivo y contraste
El usuario solicita contexto historico amplio para reconocer zonas previamente
negociadas (soporte/resistencia), rupturas, retrocesos y continuaciones, y estudiar
salidas dinamicas que protejan resultado sin estrechar stops arbitrariamente.
MARKET_DATA ya documenta klines publicos con open/close_time; POSITION_MANAGEMENT
ya define HOLD/LET_WINNER_RUN/RAISE_STOP/PROTECT_PROFIT/PARTIAL_EXIT/FULL_EXIT.
Falta verificar/implementar su conexion multihorizonte con niveles, riesgo,
backtest y Paper Lab. No se declara completa por existir precio/estructura local.

## 1. Procedencia y cobertura
Historia disponible del contrato Binance no equivale a historia desde creacion
del token. Futures, spot, mark e index tienen inicios y precios diferentes:
guardar venue, instrumento/contrato, price_source, intervalo, open/close_time,
as_of, listing conocido, gaps, hash y version.
No empalmar spot/otro exchange, redenominaciones o tokens migrados sin politica
explicita. MAX/MIN historicos solo son del periodo/fuente cubiertos, nunca ATH/ATL
globales por defecto. Listado reciente o cobertura insuficiente => UNKNOWN.
Las velas abiertas son provisionales; no alimentan pivotes confirmados.

## 2. Historial compacto, bajo demanda
Reutilizar HistoryStore/ingestion/limiter existentes tras auditar su implementacion.
Resoluciones gruesas para contexto largo, finas para entrada/salida reciente;
no descargar anos de ticks o libros para graficar una curva.
Ejemplo de presupuesto candidato, NO retencion aprobada: por token,
5 anos diarios (~1826 filas) + 1 ano 4h (~2190) + 90 dias 1h (2160) +
14 dias 5m (4032) ~= 10208 filas. Para 10 tokens ~= 102080 filas.
Comparacion: un ano 1m ~= 525600 filas POR token.
Filas no equivalen a bytes: medir SQLite real, indices, journals/WAL y logs
antes de fijar limites. Caps por tabla y total, presupuesto disco, limpieza y
logs con rotacion. Tokens activos/candidatos con cache prioritaria; otros LRU.
Paginar al desplazar/zoom del grafico; indice unico por contrato+intervalo+open.
Descarga incremental desde ultima vela cerrada, solapes dedup y huecos contados.
No borrar datasets fijados para estudio: export/archivo inmutable separado con
manifiesto. Compactar datos operacionales sin destruir evidencia de investigacion.
Retencion elimina detalle: mostrar lo que ya no puede reproducirse.

## 3. Zonas descriptivas causales, no techos garantizados
Candidatos iniciales a auditar: max/min previo diario/semanal, rangos y pivotes
confirmados multihorizonte, VWAP anclado con ancla objetiva conocida en T.
Extremos de todo el historial cubierto son contexto, no objetivo automatico.
Pivotes que requieren velas a la derecha solo estan disponibles al confirmarse:
registrar pivot_time Y confirmed_at. Nunca reescribir decisiones anteriores.
Representar zona [low,high], no precio exacto inevitable; tolerancia versionada,
basada en volatilidad/spread/tick cuando haya datos, no ajustada al resultado.
Medir toques/rechazos/ruptura/retest con reglas causales y sin contar ruido como
confirmaciones independientes. Duracion, horizonte, frescura y gaps visibles.
Un perfil de volumen por precio exige fuente adecuada: volumen OHLC por vela
NO permite reconstruir por si solo volumen exacto por nivel o liquidez actual.
Oferta/libro actual no demuestra ordenes que seguiran alli ni soporte garantizado.
Si rompe el maximo conocido no existe otro techo historico observado por encima:
escenarios/extension de volatilidad, UNKNOWN en vez de inventar resistencia.

## 4. Uso en seleccion y entrada
Para cada candidato extremo evaluar recorrido disponible hasta zona contraria,
distancia a invalidacion, costes/fills/exposicion y contexto BTC (§11 de
EXTREME_MOVERS_OBJECTIVE). Zona cercana puede justificar esperar o descartar;
no compra/venta automatica. Registrar evidencia favorable/contraria/UNKNOWN.
Objetivos son escenarios condicionados con invalidacion y horizonte, no promesas.
Comparar reglas con/sin estructura; no asumir valor predictivo por dibujar niveles.

## 5. Gestion dinamica y riesgo
Comparar offline y despues en paper politicas predefinidas:
stop inicial estructural, ajuste con nuevo pivot confirmado, trailing de
volatilidad y salida por invalidacion/agotamiento; baseline temporal existente.
ATR/multiplicadores solo si implementados/verificados; valores son candidatos,
no parametros elegidos aqui.
Para LONG un stop de proteccion se mueve hacia arriba, para SHORT hacia abajo;
no ampliar riesgo para evitar una salida. Tamano deriva de riesgo, distancia al
stop y limites de cartera. Actualizar con evidencia nueva disponible, no cada tick
por reflejo. Registrar stop viejo/nuevo, hora efectiva, regla y datos usados.
Puede proteger parcialmente/realizar parcial si politica y costes lo permiten.
No existe stop que garantice conservar ganancia y no salir antes de continuar.
Stop estrecho => mas salidas; ancho => mas devolucion del beneficio; medir ambos.
Precio de trigger (contract/mark) y fuente del grafico separados, con politica
explicita. Stops no garantizan precio de fill: gaps, slippage, liquidez y latencia.
No usar el maximo futuro de una vela para subir stop y luego su minimo para
declarar salida sin conocer secuencia. OHLC ambiguo => regla conservadora declarada
o datos mas finos; nunca asumir trayectoria favorable. Orden real no autorizada.
Break-even en precio de entrada no es break-even neto por comisiones/funding.

## 6. Medicion
Por familia/simbolo/regimen: MFE/MAE, tiempo a zona/stop, beneficio retenido,
devolucion desde MFE, stops seguidos de continuacion a horizontes fijados,
costes por churn, drawdown, abiertas y resultados netos. Un stop seguido de
subida no prueba que fue una mala decision ex ante.
Definir censura/gaps y separar desarrollo/evaluacion reservada; no mover niveles
o stops a posteriori para mejorar P&L.

## 7. V2
Detalle del token: selector 5m/15m/1h/4h/1d (candidatos de UI), OHLC + zonas
con horizonte/confirmed_at/fuente, cobertura desde/hasta y contexto BTC.
Separar capas contexto historico vs intradia para no saturar grafico.
Backtest: entrada, stop inicial y trayectoria causal de ajustes, salidas y costes.
Paper Lab: posicion virtual, stop vigente/propuesto, riesgo, objetivo condicionado,
decision y motivo; supervisor del monitor separado del gestor de posiciones.
Backend calcula/persiste; frontend solo muestra, nunca decide reglas.

## 8. Entrega incremental y aceptacion
Primero terminar fase causal/costes actual; este suplemento no cambia su alcance.
Luego auditar deltas de datos/grafico/estructura/position manager y presupuesto.
1. Dataset multihorizonte versionado y medicion de almacenamiento.
2. Zonas causales con pruebas de prefijo, pivote tardio, fuente incompatible/gaps.
3. Replay de politicas fijas sin calibracion en evaluacion.
4. UI segun skill V2 y contrato; no muestra implementacion inexistente.
5. Paper con autorizacion, riesgo y ledger; real segun gates.
Sin codigo, descargas historicas nuevas ni ejecucion por este documento.

## Referencias consultadas
- MARKET_DATA.md, POSITION_MANAGEMENT.md, EXTREME_MOVERS_OBJECTIVE.md.
- https://www.binance.com/en/academy/articles/the-basics-of-support-and-resistance-explained
- https://www.binance.com/en/support/faq/detail/360042299292
La pagina antigua de klines de developers redirigio a portada en esta revision;
los detalles REST del repo requieren re-verificacion oficial al implementar.
