# Addendum de diagnóstico — ventana pública de integración (única)

**Fecha:** 2026-10-31
**Sesión del arnés:** `scripts/engineering_live_window.py` (commit `ac5443f`, rama `feat/ingenieria-autonoma`)
**Ejecución:** única ventana pública autorizada (`--transport public --execute`), sin relanzamientos.
**Evidencia:** `docs/evidence/ventana-publica-ingenieria-2026-10-31/run.json`

---

## 1. Objetivo

Contexto reciente de ambos símbolos → sesión identificada → eventos nuevos recibidos por la sesión → evaluación registrada → estado y decisión visibles en el dashboard. Símbolos `MINAUSDT` + `BTCUSDT`, velas `1m`.

## 2. Precondiciones verificadas ANTES de conectar

| Precondición | Resultado | Detalle |
|---|---|---|
| Arnés usa `HistoryClient`, `normalize_kline`, `LedgerAttemptGate` | ✅ | `scripts/engineering_live_window.py` L61-66; cliente construido con `attempt_gate=LedgerAttemptGate` (L487-493, 591-593); parseo con `normalize_kline` (L508, 603); cada intento REST reservado ANTES del transporte (`UpstreamBudgetExceeded` sin abrir socket). |
| Contexto vacío → no crea/inicia sesión, motivo explícito | ✅ | `LIVE_CONTEXT_REQUIRED` en `engineering_session_service.create_session` (L634-638); check `contexto_cargado` requiere `len(unicos) > 0`. |
| Contexto insuficiente / discontinuo | ⚠️ Parcial | No hay gate de cuenta mínima en creación; discontinuidad se detecta como `GRID_GAP` con causa explícita en `_grid_holes`/`_evaluation_gate` (no decisión silenciosa). En este run el contexto resultó reciente y contiguo (REST de Binance). |
| Config ≡ backend ≡ dashboard | ✅ | Config pinada en `_validate_config` (LONG, stop 5 %, horizonte 3 h, regla `RULE-CAUSAL-V1`, asserts fijos). Backend ejecutado: `market_stream_service.py --transport public --no-recovery --max-seconds` (8791, 1 WS combinada) + `engineering_session_service.py --market-url http://127.0.0.1:8791` (8797). Dashboard 3020 sirviendo BUILD_ID `t4z0bfKQ_kIP9qv1WHCKR` (presente en `/market-lab`). El arnés (Python, `ac5443f`) es distinto del build frontend (`e2243c9`); no se le atribuyen cambios del arnés. |

Estado de puertos antes de conectar: 8791 libre, 8797 libre, 8792 ocupado (pid 31124, servicio local preexistente, no tocado), 3020 arriba.

## 3. Ejecución (única ventana, 2026-10-31)

Comando:
```
python scripts/engineering_live_window.py --transport public --execute \
  --service-port 8791 --engineering-port 8797 \
  --dashboard http://127.0.0.1:3020 --build-id t4z0bfKQ_kIP9qv1WHCKR \
  --symbols MINAUSDT,BTCUSDT --interval 1m --bars 300 --duration 180 --deadline 180 \
  --out docs/evidence/ventana-publica-ingenieria-2026-10-31/run.json
```

Cronología observada (epoch ms / UTC):
- `1793461064753` / `2026-10-31T15:37:44.753Z` — creación de sesión y arranque de conducción (`drive state=running`, runner `market_stream`, mercado `http://127.0.0.1:8791`).
- `1793461079999` / `2026-10-31T15:37:59.999Z` — revisión 0 (`sin_iniciar`, decisión `null`, clock `1793461079999`, eventos 0).
- `1793461140000` / `2026-10-31T15:39:00.000Z` — revisión 2 (`sin_iniciar`, decisión `null`, clock `1793461140000`, eventos 0).
- `1793461201891` / `2026-10-31T15:40:01.891Z` — última revisión registrada.
- `1793461242597` / `2026-10-31T15:40:42.597Z` — fin (duración ~177,8 s de 180 s deadline).

### 3.1 Lo que funcionó

- Preflight: dashboard disponible (HTTP 200), BUILD_ID servido coincide, puertos 8791/8797 libres, 8792 intacto.
- Servicios iniciados: mercado PID 23056 (8791, modo `public`), ingeniería PID 32436 (8797).
- Contexto reciente de **ambos símbolos**: 598 velas cerradas (BTCUSDT + MINAUSDT), origen REST klines de Binance (`fapi.binance.com`), rango `1793443140000` → `1793461020000`.
- `rest_usadas = 2` (una por símbolo, 300 velas c/u), dentro del presupuesto de 4 intentos REST públicos totales.
- Sesión creada: `session_id=PL-MINAUSDT-LONG-1793461064753-5c5a0c62`, `config_hash=4a339c046cc3ad63`, regla `RULE-CAUSAL-V1`, símbolo `MINAUSDT`, referencia `BTCUSDT`, transporte `market_stream`.
- Conducción iniciada (`drive state=running`, runner `market_stream`).
- Límites respetados: consumidores SSE máx 2 (≤ 3), reconexiones 0 (≤ 3), 0 escrituras en DBs canónicas (`db_unchanged=true`).

### 3.2 Lo que falló

- `eventos_procesados_final = 0`: durante toda la ventana (~180 s) no llegó **ninguna vela cerrada nueva** del feed WS en vivo de Binance, aunque el siguiente cierre de vela 1m ocurría a los ~15 s de arranque (y posteriores a ~75 s y ~135 s).
- Como no hubo eventos de mercado, el motor no avanzó por velas nuevas ni registró decisión: todas las revisiones muestran `decisión=null`, `decision_reason=null`.
- No se alcanzó "estado y decisión visibles en el dashboard" porque no hubo decisión que registrar.
- El deadline global (180 s) se consumió esperando eventos; al llamar `_stop_drive` ya se había excedido → error `GLOBAL_DEADLINE_EXCEEDED en stop_drive`.
- Veredicto del arnés: **`ERROR`** (no `PASS` ni `FAIL` ni `UNKNOWN`).

### 3.3 Causa de raíz (diagnóstico)

Las 2 peticiones REST de klines sí tuvieron respuesta (598 velas recientes de Binance), por lo que el acceso público HTTPS a `fapi.binance.com` funcionó. El feed **WS en vivo** (`wss://fstream.binance.com/market/stream`, modo `public`) no entregó velas cerradas a la sesión de ingeniería dentro de la ventana. No se pudo distinguir, desde la evidencia recogida, si la causa fue:
- no establecimiento del socket WSS desde este entorno,
- suscripción del hub al símbolo `MINAUSDT@kline_1m` no propagada al socket combinado, o
- ausencia de cierres de vela en el window observado.

Esto no se corregirá aquí: no hay relanzamiento ni ampliación de alcance (instrucción del operador).

## 4. Presupuestos (usuarios) — contabilidad real

| Límite | Usado | Estado |
|---|---|---|
| Conexiones WS simultáneas | 1 (hub del servicio) | ✅ dentro |
| Reconexiones WS (máx 3) | 0 | ✅ dentro |
| Consumidores SSE simultáneos (máx 3, todos los componentes) | 2 (máximo visto) | ✅ dentro |
| Intentos REST públicos totales (máx 4) | 2 (contexto BTC + MINA) | ✅ dentro |
| Velas por consulta de klines (máx 300) | 300 | ✅ dentro |
| Deadline global (180 s) | ~177,8 s | ✅ respetado (error al parar, no por exceder en ejecución de eventos) |
| Escrituras en DBs canónicas (0) | 0 (`db_unchanged=true`) | ✅ dentro |

## 5. Veredicto global

**`ERROR` — meta NO alcanzada.**

Se identificó la sesión y se cargó contexto reciente de ambos símbolos, pero no se recibieron eventos nuevos de mercado vivo, por tanto no se registró evaluación con decisión ni se mostró estado/decisión en el dashboard. La cadena `contexto → sesión → eventos → evaluación → dashboard` se interrumpió en "eventos nuevos recibidos por la sesión".

Cero entradas válidas sin evaluación real no aplica: no hubo evaluación real con mercado vivo.

## 6. Limpieza y no repetición

- Servicios de mercado (8791) e ingeniería (8797) detenidos por el `finally` del orquestador; puertos en `TimeWait`, sin LISTEN; solo queda el proceso python preexistente de 8792 (intocado).
- Dashboard 3020 sigue disponible, sin sesión de ensayo activa.
- Sesión de ingeniería escrita en directorio aislado bajo `TEMP/opencode` (no DB canónica).
- **No se repite la ventana** (instrucción: ante fallo, conserva evidencia, limpia y no repites).

## 7. Archivos de evidencia publicados

- `docs/evidence/ventana-publica-ingenieria-2026-10-31/run.json` — salida íntegra del orquestador (session_id, config_hash, regla, origen del contexto, timestamps, eventos, revisiones, decisiones, motivos, presupuestos, DBs).
- `docs/evidence/ventana-publica-ingenieria-2026-10-31/ADDENDUM_DIAGNOSTICO.md` — este documento.

Commit selectivo de estos dos archivos; push normal a `origin feat/ingenieria-autonoma`.
