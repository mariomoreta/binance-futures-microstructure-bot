# Nota de integracion al repositorio — 2026-10-14
Investigacion descriptiva preparada en rama documental independiente, sin desplazar O1.
Evidencia local al repo: ../evidence/intraday_raw_20261014.json conserva 30h por serie,
las 24h estudiadas mas 6h de baseline; ../evidence/analyze_intraday_20261014.py reproduce
summaries/episodes/alert_stats identicos al original. BTC es una serie descargada;
NO se ha realizado comparacion condicionada a BTC ni analisis de beta/correlacion.
El snapshot de seleccion incluye 523 contratos elegibles para reproducir el ranking
actual. No reconstruye el universo historico. El informe original bajo esta nota
cita la descarga completa de 16500 velas; la muestra compacta versionada tiene 3960.
No confundir estos conteos. Ver INTRADAY_ENTRY_EXIT_AGENT_HANDOFF.md para siguiente tarea.

# Estudio piloto intradia — 10 perpetuos Binance USD-M

Corte: 2026-10-14T10:20:00+00:00; ventana: 2026-10-13T10:20:00+00:00 hasta corte exclusivo.
Fecha local del usuario: 14 oct 2026, 06:20 UTC-4.

## Alcance y calidad
Consulta directa mediante herramientas Binance: ticker24, exchangeInfo y 1500 velas 5m por contrato. Universo elegible: 523 perpetuos cripto USDT TRADING. Seleccion: cinco mayores variaciones positivas y cinco negativas; BTC como control. Se excluyen TradFi, otros quotes y contratos no perpetuos. No son diez tokens acreditados como low-cap: capitalizacion al corte UNKNOWN. Las paginas publicas consultadas tienen distintas fechas/monedas e identidad ambigua; no se mezclan con datos venue.

16500 velas cerradas en once series; 1500 por serie, 288 por simbolo en ventana final. Checks: timestamps unicos, intervalos de 5m continuos, close_time < cutoff, OHLC coherentes y taker-buy quote <= quote. exchangeInfo.serverTime de la respuesta es anterior al ticker: sirve solo para elegibilidad al consultar, no para sincronizar precios. El corte comun se fija desde closeTime de tickers seleccionados.

El ticker rolling24 tiene limites diferentes a la ventana comun de velas. Sus variaciones no tienen por que coincidir. 5m no proporciona el instante exacto intrabar.

## Recorridos retrospectivos
Extremos encontrados a posteriori en cierres: minimo previo->maximo para ganadores; maximo previo->minimo para perdedores. El recorrido no es una entrada alcanzable ni un tiempo recomendado de posicion. Las filas bajistas muestran magnitud positiva de caida.

|Token|Ticker24 %|Movimiento direccional maximo %|Duracion min|Contramovimiento 2% desde extremo, min|RVOL de mayor volumen 5m|
|---|---:|---:|---:|---|---:|
|TRUTHUSDT|+47.37|49.87|1380|5|8.84x|
|WALUSDT|+36.10|40.50|1380|UNKNOWN/censurado|4.14x|
|BTWUSDT|+35.29|45.90|890|30|12.40x|
|ARCUSDT|+18.45|40.88|475|40|6.53x|
|PONSUSDT|+17.57|22.63|1040|30|28.98x|
|1000RATSUSDT|-22.14|26.32|1380|UNKNOWN/censurado|21.27x|
|OGNUSDT|-20.00|21.17|1420|UNKNOWN/censurado|2.51x|
|WUSDT|-20.00|20.07|1400|UNKNOWN/censurado|5.62x|
|EPICUSDT|-17.65|19.34|1065|5|442.70x|
|GTCUSDT|-17.22|20.71|1130|UNKNOWN/censurado|9.27x|

UNKNOWN no significa que nunca corrige: WAL y OGN acaban en el extremo, sin observacion posterior; los demas casos incompletos tienen entre 25 y 45 min tras el extremo. No se les imputa una duracion de espera.

## Alerta ilustrativa, calculada sin futuro en sus features
Regla preespecificada para ilustracion: retorno 15m >= +2% o <= -2%, RVOL quote 5m >=3x mediana de 72 velas previas (6h), cooldown por simbolo 60m. LONG-study en ganadores y SHORT-study en perdedores: la seleccion retrospectiva introduce sesgo aunque el calculo de features use pasado. Entrada mecanica siguiente apertura; sin prueba de fills/latencia/costes. No son reglas calibradas ni sustituyen H1/H2/H3 del bot.

Barreras ilustrativas: primer CIERRE +2% direccional frente a -1%, hasta 240m. No son stops/fills intrabar. Adversidad intrabar puede haber sido mayor y anterior. No extrapolar tasas a precision de ejecucion.

```json
{
  "LONG-study": {
    "alerts": 26,
    "plus2_first": 10,
    "minus1_first": 16,
    "neither_full": 0,
    "censored": 0,
    "winner_time_median_min": 20.0,
    "winner_time_q25_min": 15.0,
    "winner_time_q75_min": 42.5,
    "pullbacks": {
      "n": 23,
      "reclaimed": 14,
      "not_reclaimed_60m": 9,
      "censored": 0,
      "reclaim_time_median_min": 20.0
    }
  },
  "SHORT-study": {
    "alerts": 14,
    "plus2_first": 6,
    "minus1_first": 7,
    "neither_full": 0,
    "censored": 1,
    "winner_time_median_min": 45.0,
    "winner_time_q25_min": 16.25,
    "winner_time_q75_min": 88.75,
    "pullbacks": {
      "n": 12,
      "reclaimed": 6,
      "not_reclaimed_60m": 4,
      "censored": 2,
      "reclaim_time_median_min": 25.0
    }
  }
}
```

Medianas de 20 min LONG y 45 min SHORT se calculan SOLO entre casos que llegaron a +2% antes que -1%. No son tiempo promedio recomendado de operacion. LONG: 10 favorables primero/16 adversos primero. SHORT: 6/7 y 1 censurado. Los episodios pueden solaparse y no son independientes.

## Descanso frente a continuacion
Tras alerta, se busca primero avance direccional >=1% y posterior retroceso >=1% desde mejor cierre conocido. Continuacion descriptiva = recuperar/superar ese extremo por 0.1% en 60m. LONG: 23 retrocesos, 14 recuperaciones y 9 sin recuperar en 60m; mediana de las recuperaciones 20min. SHORT: 12 retrocesos, 6 recuperaciones direccionales, 4 sin recuperar y 2 censurados; mediana 25min. No recuperar en 60m no demuestra reversion estructural. Puede continuar despues. El follow-up se limita a las 4h desde alerta.

## Ejemplos que importan
- TRUTH: primera alerta 13 oct 12:34:59.999 UTC, RVOL8.09x; retorno bruto siguiente60m +4.94%. Alerta13:34:59.999 UTC RVOL9.85x: primero -1% en5min, aunque despues alcanza+2% en90min.
- BTW: alerta14oct00:14:59.999 UTC RVOL24.06x; primero -1% en45min, +2% en55min. Mirar solo retorno60m +5.42% ocultaria el recorrido adverso.
- EPIC: maximo volumen5m 2.21M USDT y RVOL442.70x; alerta06:04:59.999 UTC. En estudio SHORT el siguiente retorno15m es -14.37% (precio subio contra el short), primero adversidad -1% en5min. Un denominador previo diminuto puede inflar RVOL.

## Aplicacion propuesta, no implementada
1. Bot: volumen quote absoluto + RVOL robusto multihorizonte + agresion taker + respuesta del precio; separar spot/perpetuo/OI y units. Cada transaccion tiene compra y venta: volumen total no mide predominio direccional.
2. Timeline de evento: deteccion causal, maximo/minimo conocido, edad del impulso, primera pausa, profundidad/duracion del retroceso, recuperacion del extremo e invalidacion. Guardar run_id, version, as_of, symbol, fuente y disponibilidad.
3. Estudios por familia: tiempo a MFE/MAE, barreras, distribuciones25/50/75/90, censura y costes; estratificar liquidez/spread/volatilidad/volumen base. No mezclar todas monedas en un promedio.
4. V2: curva y marcas temporales, RVOL+denominador, volumen absoluto, profundidad de retroceso, estado continuation/unknown, horizonte observado, n de comparables y tiempos condicionados. Sin cuenta regresiva inventada hasta vender.
5. Primera integracion: investigacion separada de O1, anexar evidencia y registrar propuesta. No cambiar reglas de entrada/salida ni desplazar compatibilidad/control V2. Ampliar muestra con universo historico, eventos repetidos, regimenes/OOS, costes reales y un conjunto control sin alerta.

## Fuentes
Binance: endpoints /fapi/v1/ticker/24hr, /fapi/v1/exchangeInfo, /fapi/v1/klines; datos completos en intraday_raw_20261014.json.
Documentacion oficial: https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data
Metadatos explorados, NO usados como market cap sincronizada: https://www.binance.com/en/price/gitcoin ; https://www.binance.com/en/price/origin-protocol ; https://www.binance.com/en/price/swarm-network-ai/AUD

## Reproduccion
python docs/evidence/analyze_intraday_20261014.py
Salida: intraday_analysis_20261014.json. Script stdlib; grafico separado usa matplotlib. Mismos datos/corte/reglas producen mismos resultados. No se tocaron codigo del bot, ramas GitHub, DBs, procesos, configuracion ni se enviaron ordenes.
