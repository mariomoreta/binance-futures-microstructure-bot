# Estado vigente — ventana 4 ejecutada COMPLETA con cierre normal (2026-11-16)

## Bloque 2026-11-16 (noche) — analisis offline de la ventana 4 (sin mercado)

**Autorizacion humana del 2026-11-16 (noche):** «ANALISIS OFFLINE DE LA VENTANA 4».
Rectificacion documental y analisis de los datos existentes exclusivamente
offline; sin Binance, consultas publicas, capturas, ordenes, relanzamientos,
cambios de estrategia ni aumento de capacidad. Dataset fuente
`C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a` verificado
contra su manifiesto (10/10, bytes y SHA-256) antes y despues; no modificado.

**Rectificacion documental (vigente):**
- Las 2 operaciones se contrastaron fila a fila con `observaciones.jsonl`,
  `consultas_klines.jsonl` (cuerpo OHLC original) y `resultado_operativo.jsonl`.
  Los valores de `cierre.md` son correctos: AAVE SHORT entrada 107,180,
  salida stop 107,7159 (19:56:00Z), neto CONDICIONADO −6,604; 4USDT LONG
  entrada 0,008583, salida horizon 0,008594 (20:58:00Z), neto CONDICIONADO
  −0,3194.
- **Stop: referencia de senal vs stop de posicion (corregido).** El motor
  distingue dos niveles. El `stop_px` persistido (107.6556 para AAVE;
  0,00852715 para 4USDT) es el stop de **REFERENCIA** desde `ref_close`
  (close de la ultima vela 1m plenamente conocida en T), usado solo para la
  senal en T y la admision de riesgo. El stop **EFECTIVO aplicado durante la
  posicion** se calcula en `backtest_offline._stop_px(avg)` desde el **fill**:
  AAVE fill 107,18 × 1,005 = **107,7159** (gobierna la salida por stop a
  107,7159); 4USDT fill 0,008583 × 0,995 = **0,008540085** (salio por horizon,
  no se toco). El campo `stop_px` persistido NO representa necesariamente el
  nivel aplicado durante la posicion. Motor sin modificar.
- Horarios: AAVE 19:29:00 → 19:56:00 = **27 minutos** (1.620 s); 4USDT
  19:58:00 → 20:58:00 = 60 minutos.
- Capacidad: replay compartido reproduce 2 entradas (AAVE [19:29,19:56),
  4USDT [19:58,20:58)) y 159 rechazos por capacidad. Admision por tiempo y
  desempate por simbolo, no por calidad de senal.

**Analisis contrafactual individual (161 escenarios, capacidad 1 aislada):**
- 124 entradas simulables, 37 descartes (stop vulnerado en T), 0 abstenciones,
  0 sin salida acreditada. Neto CONDICIONADO agregado n=124: suma −63,42,
  media −0,51, mediana −6,60, ganadoras 22 / perdedoras 102. Bruto: suma +135,
  media +1,09. Funding: UNKNOWN para todas (n=124), neto COMPLETO n=0.
- Control de coherencia: 2/2 operaciones historicas conservan valores
  exactamente (0 diferencias numericas).
- Capacidad oculto 122 senales que entraban aisladas: 22 positivas, 100
  negativas (ambas). Las 2 admitidas fueron perdedoras.
- Comparacion candidato/comparador: INSUFICIENTE (cobertura desigual, sin
  funding, 1 hora).

**Evidencia:** `docs/evidence/exp-v2-ventana-4-20261116a-analisis-contrafactual/`
(`RECTIFICACION-ANALISIS.md`); derivados fuera de Git en
`C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-analisis-contrafactual-20261116-v2\`
(regenerados desde fuentes verificadas, resultados anteriores NO reutilizados);
`tests/test_analisis_contrafactual_ventana4.py` 11 passed; regresiones
`test_operativo_replay_offline.py` 7 passed.

| | |
|---|---|
| SHA base | `7b658e6b466a0ce24d018488d118dc33d08697f8` (local == remoto) |
| SHA de ejecucion del analisis | commit `26fdf86` (ventana 4) + script `scripts/analisis_contrafactual_ventana4.py` (corregido) |

## Bloque 2026-11-16 (madrugada) — contraste flujo/profundidad vs continuacion/reversion (sin mercado)

**Autorizacion humana del 2026-11-16 (madrugada):** «INVESTIGACION OFFLINE DE LA
SENAL, SIN MERCADO». Rectificacion del hash de configuracion (obligatorio) y
contraste exploratorio flujo/profundidad vs continuacion/reversion. Sin
Binance, consultas publicas, capturas, ordenes, relanzamientos, ventanas nuevas
ni cambios en la estrategia productiva. Dataset fuente verificado contra
manifiesto (10/10) antes y despues; no modificado.

**Correccion del hash:** `operativo_config_sha256` (y `config_sha256`) ahora son
OBLIGATORIOS en `scripts/analisis_contrafactual_ventana4.py`: ausente, vacio,
mal formado o distinto del calculado -> rechazo explicito antes de reconstruir.
Se adicionaron 5 pruebas focalizadas (hash valido, ausente, vacio, invalido,
discordante).

**Contraste principal (definiciones fijadas antes de los agregados):**
ratio = (buy_notional - sell_notional) / (bid_notional_top20 +
ask_notional_top20); ratio_alienado = signo(move_24h_pct) * ratio; horizonte 60
min causal; precio inicial = ref_close en T; precio final = close conocida en
T + 60 min; retorno alineado = signo(move_24h_pct) * retorno. Usa las 161
observaciones aptas (no solo las 124 operaciones contrafactuales).

**Resultado:** regla sencilla (signo 24h) = 65.8% de continuación (106/161).
Flujo a favor del movimiento previo = 61.6% de continuación (45/73). Flujo
contrario = 69.3% de continuación (61/88). El flujo a favor NO distingue mejor
continuación que la regla sencilla; de forma contraintuitiva, el flujo contrario
muestra ligeramente más continuación. Desgloses por rol (candidate 69.2%,
comparator 51.6%), direccion (LONG 67.8%, SHORT 63.5%) y ciclo (muy variable,
0%-100%, dependencia temporal). 25 símbolos únicos, 19 repetidos hasta 12 veces
(escenarios no independientes).

**Decision:** resultado débil, contradictorio o concentrado. No se incorpora el
ratio a la estrategia productiva. No se optimizan umbrales ni se cambian
entradas, stops ni capacidad.

**Evidencia:** `docs/evidence/exp-v2-ventana-4-20261116a-analisis-contrafactual/CONTRASTE-FLUJO-PROFUNDIDAD.md`;
derivados fuera de Git en
`C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-contraste-flujo-profundidad-20261116-v2\`;
`tests/test_contraste_flujo_profundidad.py` 6 passed; regresiones
`test_analisis_contrafactual_ventana4.py` 16 passed,
`test_operativo_replay_offline.py` 7 passed.

| | |
|---|---|
| SHA base | `7b658e6b466a0ce24d018488d118dc33d08697f8` (local == remoto) |
| SHA de ejecucion del analisis | commit `509b5ba` (correccion del cierre del analisis contrafactual) |
| Evidencia contraste | `docs/evidence/exp-v2-ventana-4-20261116a-analisis-contrafactual/CONTRASTE-FLUJO-PROFUNDIDAD.md` |
| Dataset original | intacto, solo lectura, 10/10 ficheros verificados contra manifiesto antes y despues |
| Lo que NO acredita | rentabilidad, edge, mejora predictiva del ratio flujo/profundidad, ventaja candidato/comparador (una sola hora, dependencia temporal) |

