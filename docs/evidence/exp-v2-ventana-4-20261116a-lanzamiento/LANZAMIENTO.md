# LANZAMIENTO — `exp-v2-ventana-4-20261116a`

Única ventana pública autorizada por el usuario el 2026-11-16 bajo el
protocolo `EXPERIMENTO_OPERATIVO_V2` (una sola corrida; sin órdenes reales,
cuentas, claves, capital, otras ventanas ni relanzamientos).

## Verificación previa (acotada)

| Comprobación | Resultado |
| --- | --- |
| Rama / HEAD / remoto | `research/universe-liquidez-v1` = `ce2af020c666956ba35a1e1d41d0007c85d581a7` (local == remoto) |
| Cambios locales | solo `opencode.json` (ajeno, preexistente; sin commit) |
| `run_id` sin usar | directorio `C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a` inexistente antes del lanzamiento |
| Piloto activo | ninguno (sin procesos python del piloto) |
| Rutas WS vigentes | `--ws-public-base wss://fstream.binance.com/public` y `--ws-market-base wss://fstream.binance.com/market` en el comando; la antigua `/stream` está retirada en el código (`research_pilot.py:1281`) |
| Config inicial + checkpoints | habilitados en el código vigente (`_persistir_config_inicial` en 4101; `_escribir_checkpoint` en transición captura→settle 4237, transición settle→espera contable 3531 y lote operativo persistido 3677) |
| Cuerpos de consultas operativas | persistidos en `http_requests.jsonl` (ledger en vivo) |
| Monitor | dashboard 3020 vivo; URL del piloto: `http://127.0.0.1:3020/market-lab?vista=piloto&run=exp-v2-ventana-4-20261116a` |
| Servicio ajeno 8792 | preservado (no se toca; sin listener antes del lanzamiento) |
| Espacio disponible en C: | 133,9 GB (almacenamiento previsto 9.016.872 bytes; reservado máx 56.363.648 bytes) |

## Presupuesto (`--budget-only`, sin red, forma final del comando)

Ejecutado 2026-11-16T19:25:00Z en directorio de preparación aparte
(`...preparacion-presupuesto`, sin tocar el directorio de la corrida):
**gate 13/13**, `cabe_en_limites: true`, peso total estimado 1472, plan con
reservas 1334 intentos / peso 3752, funding máx concentrado 5m = 110.
Código del hijo **0**; veredicto del lanzador **normal**. Detalle en
`presupuesto.json`.

## Independencia del anfitrión de lanzamiento (acreditada antes de abrir mercado)

Mecanismo: lanzamiento del lanzador real (`scripts/run_pilot_window.py`)
mediante WMI `Win32_Process.Create` (nativo de Windows), que crea el proceso
**fuera del árbol del agente**. Tres corridas inocuas con un hijo de latido:

- **Corridas 1–2** (`independencia_corridas12.json`): ciclo completo normal con
  el lanzador real bajo linaje `WmiPrvSE.exe (3908) → lanzador (7444) → hijo`;
  la shell del agente (9380) NO está en el linaje. Parada por el mecanismo
  propio del hijo → `exit_code.txt` = 0, `cierre.json`: `normal`.
- **Corrida 3** (`independencia_corrida3_kill.json`): con el hijo ejecutando,
  se mata de forma abrupta SOLO al anfitrión de lanzamiento
  (`Stop-Process -Force`, PID 21632, padre WmiPrvSE 3908). El hijo
  **sobrevive**: su latido sigue avanzando a +10 s y +16 s tras la muerte del
  anfitrión, y termina limpio (código 0) por su mecanismo propio de parada.
  Sin veredicto del lanzador (murió antes del cierre), como es esperable.

Límite de la acreditación: no se cerró OpenCode (prohibido reiniciarlo); la
independencia del agente se acredita por linaje observado — el lanzador es
hijo de `WmiPrvSE.exe`, ajeno al árbol del agente, y la muerte del anfitrión
de lanzamiento no propaga la terminación al hijo (demostrado). Los
checkpoints mitigan la pérdida de evidencia; no resucitan la corrida.

## Comando efectivo de la corrida (congelado)

Lanzador + piloto, una sola ejecución:

```powershell
python scripts/run_pilot_window.py `
  --out-dir C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a `
  --work-timeout-seconds 40200 `
  --shutdown-grace-seconds 300 `
  --mode public --activar-publico `
  --run-id exp-v2-ventana-4-20261116a `
  --status-file C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a\estado.json `
  --duration-seconds 3600 --settle-seconds 4200 `
  --cycle-seconds 300 --selection-seconds 300 --decision-delay-seconds 5 `
  --max-symbols 20 --max-candidates 12 --max-comparators 8 `
  --min-quote-volume 1000000 `
  --horizons '5m=300000,15m=900000,60m=3600000' `
  --price-interval 1m --price-tolerance-ms 90000 --price-delay-ms 2000 `
  --max-data-age-ms 5000 --max-observations 20000 `
  --max-bytes 134217728 --max-messages 5000000 `
  --max-http-attempts 2000 --max-http-retries 50 --max-http-weight 5000 `
  --max-ws-reconnects 20 --tick-ms 500 `
  --funding-source exchange `
  --funding-method observed-settlements `
  --funding-wait-seconds 32400 `
  --funding-wait-max-queries 3 `
  --rest-base https://fapi.binance.com `
  --ws-public-base wss://fstream.binance.com/public `
  --ws-market-base wss://fstream.binance.com/market
```

Parámetros congelados: captura 3600 s; settle hasta 4200 s; espera contable
hasta 32400 s; trabajo máximo del lanzador 40200 s; margen exclusivo de
cierre 300 s; selección y decisión cada 300 s; 12 candidatos + 8 comparadores
(máx 20); frescura 5000 ms; dirección LONG/SHORT, entrada causal, stop 0,5 %,
notional 1000 USDT, horizonte 60 min; capacidad global 1 y prioridad
determinista; costes y funding `observed-settlements` con máximo 3 consultas
por símbolo; todos los techos HTTP/WS/almacenamiento existentes. Cobertura:
solo perpetuos USD-M (no se declara soporte de futuros con vencimiento).

## SHAs de ejecución

Commit `ce2af020c666956ba35a1e1d41d0007c85d581a7` (scripts sin modificar en el
working tree). SHA-256 en `hashes_scripts.json`:

- `scripts/research_pilot.py` = `1280819812f66c19f859a7173314d419868fbacfc7d892455cff8211e6862c11`
- `scripts/run_pilot_window.py` = `0cde016bb2a37d782fc46ef8bc82e8a7d33273dae33003aac5f8e4aaaf0255f5`
- `scripts/research_operativo_replay.py` = `df522800a206c5bb0987fcc142c558cbb78287a2b391ca41063ed026c03c3d91`

## Metadatos excluidos del contador de captura

El contador de almacenamiento del presupuesto cubre los artefactos de captura
del piloto (9.016.872 bytes previstos). Quedan fuera por ser metadatos, igual
que `manifiesto.json` y `estado*.json`: `config_inicial.json`,
`checkpoints.jsonl`, la instantánea del ledger HTTP incluida en el
checkpoint, `exit_code.txt`, `estado_lanzador.json`, `cierre.json`,
`launcher.json`, `stdout.log`/`stderr.log` del hijo y esta evidencia de
lanzamiento. Ningún techo se amplía.
