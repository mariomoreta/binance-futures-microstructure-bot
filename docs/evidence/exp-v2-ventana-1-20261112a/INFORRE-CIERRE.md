# Cierre de la ventana única `exp-v2-ventana-1-20261112a`

**Vía A** (`observed-settlements`) del experimento operativo v2, sobre
perpetuos USD-M. Una sola corrida, un solo `run_id`, un solo presupuesto
acumulado.

- **SHA de ejecución:** `4b83498def6ae303795d50b2d8fe5276159312e5`
  (rama `research/universe-liquidez-v1`, local == remoto).
- **Inicio:** 2026-11-12T09:11:30.871Z · **Fin:** 2026-11-12T10:11:36.302Z
  · **Duración efectiva:** 3605.431 s (solo la captura).
- **Directorio de la corrida (fuera de Git):**
  `C:\proyectos\binance-futures-data\exp-v2-ventana-1-20261112a`.
- **Monitor:** `http://127.0.0.1:3020/market-lab?vista=piloto&run=exp-v2-ventana-1-20261112a`.
- **Presupuesto plan (`--budget-only`, comando efectivo):**
  `cabe_en_limites: true`, 13/13 comprobaciones, 1334/2000 intentos con
  reservas, 3752/5000 peso, 110/500 funding en 5 min, 52 043 648 B
  reservados de 134 217 728 B. SHA-256 de `presupuesto.json`:
  `37ac0041b9093d2ec2563597488a9257e7ae55cf1d1fbe17c2124ae38e3aa950`.

> Una ejecución simulada no acredita ejecuciones reales ni rentabilidad
> generalizable. Cobertura limitada a PERPETUAL/TRADING/USDT.

---

## Capa 1 — Funcionamiento técnico

**La ventana se ejecutó y terminó por la ruta de éxito del CLI.**

| Comprobación | Resultado |
|---|---|
| Terminación | `phase=fin`, `stop_reason=duracion`, `espera_contable.cierre=null` |
| Resumen final del CLI (stdout) | `estado=completo`, `observaciones=232`, `aptas=0`, `no_aptas=232`, `resultados=0` |
| stderr | vacío (0 bytes) |
| Artefactos completos | `resumen.json`, `manifiesto.json`, `http_requests.jsonl`, `estado.json`, `observaciones.jsonl` (2.77 MB), `research.db` |
| Ciclos de selección | 12 (uno cada 300 s), `ciclos_saltados=0` |
| Símbolos | 32 distintos observados; `seguidos_peak=20` |
| Peticiones HTTP | 24 (12 `exchangeInfo` + 12 `ticker/24hr`), **0 fallos**, **0 reintentos** |
| Peso | reservado 492 / 5000; configurado en respuestas OK 720 |
| Almacenamiento | 53 100 224 B contabilizados de 134 217 728 B; 2 768 576 B usados |
| WS | 16 conexiones acumuladas (8 generaciones de feeds × 2), 467 764 mensajes, 0 reconexiones |
| Feed `/public` (`depth20@100ms`) | 149 742 mensajes en la última generación |
| Feed `/market` (`aggTrade`) | **0 mensajes** |
| Consulta de funding | 0 (no había posiciones que liquidar) |

**Limitación del envoltorio de supervisión (declarada, no ocultada):** el
exit code numérico **no quedó persistido** (`exit_code.txt` vacío, 0 bytes).
La causa es el envoltorio `Start-Process -PassThru` + `WaitForExit()`, que no
puebla `ExitCode` sin `Refresh()`. La evidencia de terminación limpia es
indirecta pero consistente: el CLI reached su `return 0` (línea 4374) porque
imprimió el resumen de éxito por stdout, la ruta de error habría escrito un
JSON `{"error": ...}` en stderr y devuelto 2 (stderr está vacío), y el
manifiesto con hashes se escribió al final. **No se declara un exit code
observado: se declara la evidencia de la ruta de terminación.**

**Fases effectively ejecutadas:** solo `captura` (3600 s). El `settle` y la
`espera_contable` no llegaron a abrirse porque su disparador es la existencia
de trabajo pendiente: con 0 observaciones aptas no había horizontes que
madurar ni posiciones que liquidar. No es una interrupción: `stop_reason` es
`duracion`, no un error ni un tope.

---

## Capa 2 — Calidad y suficiencia de los datos

**La ventana es INSUFICIENTE en la capa de datos.** El embudo se vació en el
primer filtro.

| Métrica | Valor |
|---|---|
| Observaciones registradas | 232 (140 `candidate`, 92 `comparator`) |
| Aptas para evaluación | **0** |
| Descartadas | **232** |
| Motivos de descarte | `sin_flujo` 232; `dato_obsoleto_libro` 3 (solapados) |
| Cobertura `libro_presente` | 232/232 |
| Cobertura `libro_banda_5bps_cubierta` | 215/232 |
| Cobertura `flujo_presente` | **0/232** |
| Antigüedad del libro en la decisión | min 443 ms, mediana 567 ms, max 9019 ms; 3 por encima del límite de 5000 ms |
| `research_flow_10s` / `research_flow_1m` (base local) | **0 filas / 0 filas** |
| `research_book_1m` (base local) | 1200 filas (20 símbolos × 60 min), 0 drops, 0 errores |
| Comparación candidate vs comparator (propia del piloto) | **INSUFICIENTE** — motivos: `sin_operaciones_completas_candidate`, `sin_operaciones_completas_comparator`, `cobertura_de_ciclos_ambos_roles_bajo_50pct` (cobertura 0.0) |

### Causa raíz del hueco

El feed `/market` (`aggTrade`) **no recibió ni un solo frame** en toda la hora:

- `connections=1`, `messages=0`, `errors=0`, `last_error=null`,
  `disconnects=1` (el cierre final), `reconnects=0`.
- El contador se incrementa **por cada frame recibido**, antes del handler
  (`scripts/research_pilot.py:1242`). Con 0 mensajes, 0 errores y sin
  reconexiones, la conexión estuvo abierta y **silenciosa**: no es que los
  mensajes llegaran y fueran descartados.
- En paralelo y sobre el mismo host, `/public` recibió 467 764 frames. El
  silencio es específico del stream de trades.
- La URL reconstruida localmente (sin abrir conexión) es
  `wss://fstream.binance.com/stream?streams=<símbolo>@aggTrade/...` (20
  símbolos por generación), la forma correcta del endpoint combinado.
- La forma de la URL no es el problema; el problema es que no llegó ningún
  frame de ese stream.

**Causa raíz: UNKNOWN.** Aislar si el silencio es del venue o del cliente
exigiría abrir una conexión pública adicional. No se abrió ninguna: el
tráfico de la ventana autorizada no se contamina con diagnóstico, y una
prueba de venue nueva no está cubierta por la autorización vigente. Las dos
hipótesis vivas (silencio del endpoint de trades para esta forma de
suscripción, o comportamiento del cliente en esa conexión concreta) quedan
abiertas y registradas, no resueltas.

### Limitaciones secundarias observadas (no bloqueantes, pero reales)

- La selección registró `exclusion_reasons` `move_1h_desconocido` (144/144)
  y `volumen_percentil_desconocido` (144/144) en los candidatos, y
  `liquidity_spread_depth: UNKNOWN (no historia de libro)` en el resumen de
  ciclo: en el instante de la selección todavía no había historia de libro ni
  de velas de 1 h. El ranking no pudo apoyarse en el movimiento de 1 h ni en
  el percentil de volumen.
- El libro sí se capturó bien (mediana de frescura 567 ms) y su banda de 5
  bps estuvo cubierta en 215/232 observaciones; al cierre de la captura la
  antigüedad era de 5648–6570 ms en los 20 símbolos, por encima del límite de
  5000 ms.

---

## Capa 3 — Resultado económico exploratorio

**No hay resultado económico que evaluar.** La capa 3 está vacía, no en cero.

| Magnitud | Valor |
|---|---|
| Entradas simuladas | 0 |
| Salidas ejecutadas | 0 |
| Posiciones abiertas al final | 0 |
| Operaciones con neto COMPLETO | 0 |
| Operaciones con neto CONDICIONADO | 0 |
| Operaciones con neto UNKNOWN | 0 |
| P&L bruto / costes / funding / neto | sin datos (no se presentan como 0) |
| Máxima concurrencia observada | 0 (configurado 1) |
| Tiempo en mercado | 0 ms |
| Distancia al stop observada | sin datos (regla congelada: 0,5 %) |
| Decisiones: entradas / abstenciones / rechazos por capacidad | 0 / 0 / 0 |

Comparación de roles: **no se hace**. No hay operaciones completas en ningún
rol, luego no existe base para comparar; el propio piloto la marca
`INSUFICIENTE`. No se fuerza ninguna operación ni se infiere resultado desde
precios, señales ni suposiciones.

**Lectura honesta:** esta ventana **no aporta evidencia sobre la hipótesis
económica** ni a favor ni en contra. Un embudo vacío no es un resultado
negativo: es un resultado no informativo. La mérito o demérito de la regla
sigue sin evaluarse.

---

## Consecuencias y límites de esta ventana

1. `INSUFICIENTE` es un resultado válido y **no autoriza otra ventana**. La
   insufficiency se origina en la capa de datos (ausencia total de flujo), no
   en la contabilidad de funding: la vía A **no llegó a ejercitarse** en su
   parte esencial (espera contable, liquidaciones observadas, neto
   completo vs. condicionado). Es un dato sobre la cobertura de la vía, no
   sobre su validez.
2. No se relanzó, no se creó otro `run_id`, no se ampliaron plazos ni cupos,
   no se modificó código ni configuración durante la captura.
3. No hubo órdenes reales, cuentas privadas, claves, cambios de apalancamiento
   ni fondos reales. El servicio ajeno de 8792 no se tocó ni se arrancó.
4. La siguiente acción requiere **autorización humana nueva** para cualquier
   ventana adicional, y la ventana actual **no puede reutilizarse** para
   obtener flujo: la captura agotó su duración sin datos de trades.

## Artefactos publicados

| Fichero | Contenido |
|---|---|
| `cierre-compacto.json` | Cierre en tres capas, reconstruido desde los registros persistidos |
| `diagnostico-flujo.json` | Hechos del silencio del feed `/market` y sus consecuencias |
| `manifiesto.json` | Manifiesto con `git_head` de ejecución y hashes SHA-256 de los artefactos |
| `resumen.json` | Resumen nativo del piloto |
| `estado-final.json` | Snapshot atómico final (`--status-file`) |
| `http_requests.jsonl` | Ledger HTTP completo (24 filas) |
| `02-monitor-ventana-final.png` | Monitor sobre la corrida real en su estado final |
| `hashes.json` | SHA-256 de todo lo publicado aquí |

El dataset y los derivados voluminosos (`observaciones.jsonl` 2.77 MB,
`research.db`) permanecen **fuera de Git**, en el directorio de la corrida.
