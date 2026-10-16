# OFFLINE-EVAL-V1 — paquete reproducible (manifiesto)

Version: `OFFLINE-EVAL-PACKAGE-V1`. Status: manifest + isolated
reproduction evidence. No live trading, no forward window, no threshold
work. Kronos/IA diferidos (no dependen de este paquete).

Entradas exactas de OFFLINE-EVAL-V1 preservadas: velas, eventos,
seleccion, calendarios y configuracion. Exportacion aislada (solo
lectura del canonico, escritura solo en temp). Agregacion del
artefacto != replay desde datos crudos (distincion §7).

## 1. Componentes del paquete (fuera de Git)

Ubicacion local (no publicada):
`C:\Users\adonm\AppData\Local\Temp\opencode\oev_pkg\`
Zip de transferencia:
`C:\Users\adonm\AppData\Local\Temp\opencode\OFFLINE-EVAL-PACKAGE-V1.zip`
(sha256 `c747bb08690bfe76b44c54acadc7e35fa00cd89deeb313ce1d2ec05261622d07`,
314830 bytes).

| Archivo | SHA256 completo | Bytes |
|---|---|---|
| `btc/candles.json` | `195f18064b6c3322059e204116b730cfd41ff580fe7e590c353ed03ee48db97e` | 477914 |
| `btc/events.json` | `0678cda151902e3cdabc978770812347cfbea4698bf6bae9f3bde45134746aa0` | 106912 |
| `btc/meta.json` | `666cd47f09d88dd2cf9adfeb5f34bb02490ee5db8a313cf636501368453f2982` | 2112 |
| `btc/selection.json` | `59a40347f9eb0418f16781d109b9d2e6889d01a14bdef52c92e330067fc43352` | 236 |
| `btc/admitted.json` | `c4c1bdec7877469ccb00ef65361ddf76e77b8bfefb8ff44f2d91256c545241eb` | 106912 |
| `btc/manifest.json` | `a07e86b21492bb3cd96e1ace361af84e3817a2f326228cb9b50dc58f46e9bc9d` | 73006 |
| `btc/event_ids.json` | `bafdbd62491b94d7efeb5412b7b841249d187188f5b032a50f32fd02629ce78f` | 341764 |
| `eth/candles.json` | `cb708a44fa9140852f0de74c44aa44a0e283d3eabf9f5aa9da25fdad4511d126` | 466398 |
| `eth/events.json` | `b2ea24d115f29b3246515a898f37fe9671e56a5f546020e4409eba5d9b18cff8` | 111578 |
| `eth/meta.json` | `21cd4d6ee32fa2e66880bde27f01304a130fd09c1a7bd37670ba6a08e3e98ea3` | 2112 |
| `eth/selection.json` | `3a07a08cd695b7b045c27951d99dc6021ac99c81e18cc7fe5778582dac041f18` | 236 |
| `eth/admitted.json` | `065256c5cd30f8cfd7d81f57a695fc8517eb13a8a1099f42828b26a792fd0709` | 111367 |
| `eth/manifest.json` | `dbaca2ea2b731b4399b41995349eed2b86995b6bf46eefe66c6c6914aeb4e0f5` | 73339 |
| `eth/event_ids.json` | `e6d17259716ccebba99e323f4523d916eaab57e935b7e18da00102b394c61d85` | 357102 |
| `sol/candles.json` | `ce911d2f4117eec81ee0052c88a5b364ecd7eb32d79925ed230ff555e7961a7d` | 476757 |
| `sol/events.json` | `523c9aa121003138b13a7588e4965a321b4e7a319278cda1b566133f93fa3313` | 129720 |
| `sol/meta.json` | `f0d41213a36439c826e8267a5fbdd2cb21693fad5be343974ebd3ec030788fdb` | 2112 |
| `sol/selection.json` | `addfc7b89e67632e28d246de4d056e563dcf1cdfe6c89120d875b0d4672dcb7f` | 236 |
| `sol/admitted.json` | `1da597d55c8b73612a9d057a15a9314ff91aa2a37d8a1e4205377c5483fe3683` | 129720 |
| `sol/manifest.json` | `80844748a250e202952b2c7e7f15267ffe39ae2eef20476fdd90d380664a594e` | 78022 |
| `sol/event_ids.json` | `c9163445152b1c3de1d2a23d3c76ea972198fc530aa8f08e8a277026530392f9` | 417351 |
| `rebuilt.json` (artefacto reagregado) | `c051e88841754668a02a6d92db02ccdcb97fd16e45a08671022a370576287b3a` | 114195 |
| `inputs.json` | `b25743951ae243ee1f884b767a268efd429cfacc21b10565dd750175b0057290` | 1108 |

Artefacto canonico publicado (en Git, force-added):
`frontend/src/data/offline-eval-v1.json`, sha256
`c051e88841754668a02a6d92db02ccdcb97fd16e45a08671022a370576287b3a`
(114195 bytes) — identico al rebuilt byte a byte.

## 2. Versiones

- Motor: `backtest-offline/v4.2`
  (`src/microstructure_probe/backtest_offline.py`, `ENGINE_VERSION`).
- Runner: `scripts/run_family_evaluation.py` (grupos + `GROUP_FAMILY`,
  split por cutoff, escalas 1.0/2.0/3.0).
- Exportador: `scripts/export_engine_inputs.py`
  (mapping `PROPOSED-P1-11C-map-v1`, caller-declared, NO aprobado).
- Seleccion: `scripts/select_eval_events.py` (purga pre-runner).
- Agregador: `scripts/aggregate_offline_eval.py` (bundling
  determinista, fail-closed).
- Mapping candidato: `MAP-CANDIDATE-v1`
  (`docs/HYPOTHESIS_ENTRY_MAPPING_CANDIDATE.md`, NO aprobado).
- Costes: `COST-ASSUME-v1` (fee 5bps + spread 1bps + slippage
  2bps, supuestos versionados, engine defaults intactos).
- Funding: `FUNDING-CAL-v1` por simbolo (venue realizado, 90
  liquidaciones/simbolo).
- Diseno: `docs/OFFLINE_EVAL_DESIGN_V1.md` (fijado antes de
  resultados). Reproductor: `scripts/reproduce_offline_eval.py`.
- Python 3.14.3 (Windows). Git base `b748d22e32d707cd761e81c4601897eb5ecac72e`.

## 3. Unidades (vinculantes)

- Tiempos: milisegundos epoch (`open_time_ms`, `close_time_ms`,
  `event_time_ms`, `cutoff_ms`, `settlement_ms`).
- Precios: USDT por unidad base (quote currency per base).
- Volumenes: NO exportados (el `Candle` del motor no lleva volumen).
- Economia: USDT por operacion sobre nocional fijo $1000 @1x
  (`expectancy_net`, `total_net_realized`; sufijo R = solo
  realizadas, marcas `open_at_end` excluidas).
- Funding: `rate_bps` por liquidacion venue (signo por direccion);
  importes en USDT sobre cantidad x mark causal.

## 4. Cobertura y huecos

- Velas: trio 15m x2879/simbolo (8637 total),
  ventana 1788816600000 → 1791407699999
  (2026-09-07..2026-10-07 aprox).
- `null_close_time` 0/simbolo; `close_chain_violations` 0
  (cadena intacta; `close_time` = siguiente open − 1ms).
- Eventos fuente: 1558 (BTC 476 = 251/220/5; ETH 498 =
  260/235/3; SOL 584 = 321/257/6 por H1/H3/H2).
  Descarte `symbol-filtered` contra la tabla completa de 2831
  filas (BTC 2355, ETH 2333, SOL 2247); `unmapped`,
  `bad-direction`, `bad-price`, `bad-time` todos 0.
- Seleccion (cutoff global 1790010000000, horizonte 1h):
  BTC 224+252/0; ETH 256+241/1 (purga: continuation LONG
  @1790007300000); SOL 297+287/0. Admitidas 1557 = 1558 − 1.
- Replay @1x: 1557 − 145 solapes (`max_concurrent=1`
  intra-celda) − 0 expiradas − 0 mismatched = 1412 trades
  (BTC 452 + ETH 457 + SOL 503) = 1410 realizadas + 2 marcas
  `open_at_end` (ETH/SOL continuation-oos, excluidas de
  metricas realizadas).
- Funding: 90 liquidaciones/simbolo, 1788825600004 →
  1791388800000, cadencia nominal 8h sin huecos interiores.
  Cobertura de holdings: 1403 cubiertas quietas + 1 liquidada
  (+0.0894 USDT) + 8 UNKNOWN (`uncovered_ms=2700000` c/u:
  6 colas cerradas + 2 marcas abiertas). Total 1404/1412
  `accounting_complete`.
- `input_hash` (motor, 16 hex): BTC `31c100e2de5a05b1`,
  ETH `7643681e65483162`, SOL `d784680b973bea6e` —
  identicos entre manifiesto re-ejecutado y artefacto.

## 5. Procedencia

- Velas/eventos: `data/historical/historical.db` (solo
  lectura `mode=ro`), sha256
  `d8930ec5d4c4415e748859f426d0a9e9c39de5ceb17367efd3d626fdf56f8b19`
  (19181568 bytes, a 2026-10-15). Tablas `historical_klines`
  (regular, con volumen aunque no exportado) y
  `event_instances` (2831 filas, estudios piloto P1-11C).
- Calendarios: `docs/evidence/FUNDING_CALENDAR_*_V1.json` (en
  Git) construidos con `scripts/build_funding_calendar.py`
  desde 3 GET venue `fapi/v1/fundingRate` (2026-10-16, 90
  filas/simbolo). `provenance.response_sha256`: BTC
  `ce0d64a0…52f2e0cab3`, ETH `ddbe3376…03bbde2d8730d5df`,
  SOL `271557db…521d670086ef2b6a65b132ae267d`
  (ver `docs/evidence/FUNDING_ACQUISITION_V1.md`).
- IDs originales: `event_ids.json` por simbolo conserva el
  `event_id`/`run_id`/`definition_version`/`reference_timestamp`/
  ventana de formacion/`data_quality` de cada fila canonica:
  476/498/584 exportadas con 0 faltantes y 0 multiples
  (mapeo 1:1 exacto; direccion `up`→LONG, `down`→SHORT).
- Disponibilidad temporal: `available_at_ms` = `close_time`
  de la vela de formacion (cadena intacta, gap 1ms uniforme);
  tripleta por operacion en
  `docs/evidence/OFFLINE_EVAL_AUDIT_V1.json`
  (1412/1412 `entry >= available`, 0 violaciones). La
  disponibilidad de senal VIVA sigue UNKNOWN (sin prueba de
  formacion en streaming).

## 6. Comandos (reproduccion exacta)

```text
python scripts/export_engine_inputs.py --symbols BTCUSDT --interval 15m --out-dir <tmp_btc>
python scripts/export_engine_inputs.py --symbols ETHUSDT --interval 15m --out-dir <tmp_eth>
python scripts/export_engine_inputs.py --symbols SOLUSDT --interval 15m --out-dir <tmp_sol>
python scripts/select_eval_events.py --events <tmp>/events.json --cutoff-ms 1790010000000 --horizon-ms 3600000 --dev-out <tmp>/dev.json --oos-out <tmp>/oos.json --report <tmp>/selection.json   # x3
# admitted = dev+oos concatenados (purge-clean)
python scripts/run_family_evaluation.py --events <tmp>/admitted.json --candles <tmp>/candles.json --calendar docs/evidence/FUNDING_CALENDAR_<SYM>_V1.json --cutoff-ms 1790010000000 --out <tmp>/manifest.json --formation-method PROPOSED-P1-11C-map-v1   # x3
python scripts/aggregate_offline_eval.py --inputs <inputs.json> --out <artefacto>
```

Atajo verificado: `python scripts/reproduce_offline_eval.py --out-dir <tmp>`
(export+seleccion+runner+agregado+verificacion) o
`--check-only` (solo artefacto, sin DB).

## 7. Agregacion != replay (distincion)

- REPLAY (esta seccion): export desde la DB canonica +
  seleccion con purga + runner por familia (motor v4.2) +
  calendarios realizados. Re-ejecutado 2026-10-16/17 en temp:
  trades 452+457+503=1412, `input_hash` identicos,
  artefacto reagregado byte-identico al publicado.
- AGREGACION (`aggregate_offline_eval.py`): solo empaqueta
  manifiestos + metas + selecciones + calendarios ya
  existentes en `offline-eval-v1.json` (fail-closed ante
  cutoff/seleccion/calendario inconsistentes; pooled = sumas
  aritmeticas). Verificada en checkout limpio sin canonico
  (test `test_offline_eval_aggregation.py` 6/6 + adapter +
  suite frontend): prueba determinismo del empaquetado, NO
  regenera desde datos crudos.

## 8. Checkout limpio (sin canonico)

`git worktree` sin `data/`/`logs/`: el artefacto publicado
parsea (`--check-only` OK, sha fijado), el agregador es
determinista desde fixtures, el adapter/ruta/UI consumen solo
el artefacto (frontend 310/310 + typecheck + build en la
imagen base). La DB canonica esta ausente en limpio: comandos
+ hashes NO reconstruyen sus 8637 velas + 2831 filas. La
regeneracion desde cero exige la DB (o este paquete).

## 9. Recuperacion del paquete y transferencia

Datos voluminosos fuera de Git por politica (DBs, JSON de
velas/eventos, zip). Mecanismo concreto:

1. Regeneracion local (preferida): comandos §6 contra la DB
   canonica + `scripts/reproduce_offline_eval.py` (verifica
   hashes §1 + `input_hash` §4 + sha del artefacto).
2. Transferencia del zip: fichero §1 (314830 bytes,
   sha `c747bb08…16e0cab3`) en el host del proyecto;
   entrega por copia directa o medio acordado a peticion
   (no adjuntado a Git por tamano/politica).
3. Reproduccion externa: PENDIENTE — declarada
   explicitamente. Un tercero con solo el repo (sin DB ni
   zip) puede verificar artefacto/agregacion/UI pero NO
   re-ejecutar el replay. Con el zip, verifica hashes §1 y
   reagrega (`aggregate_offline_eval.py`) sin la DB.

Sin nuevas corridas Binance, sin ventana forward, sin paper,
sin ordenes. Umbrales intactos.
