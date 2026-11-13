# Defectos materiales del lanzador: plazo global y cierre con evidencia

**Fecha:** 2026-11-13 · **Alcance:** corrección y pruebas **locales**
(sin mercado, sin diagnóstico público, sin ventana operativa) ·
**Base publicada auditada:** `d53d8ad9da04810363f859f72c32de3c38f4a131`

## Defecto 1 — Las esperas de terminación pueden superar el plazo global

**Reproducción (código publicado, caso de referencia del enunciado):**
trabajo 1 s, margen 4 s, total 5 s, `taskkill` que no responde y un hijo
que no confirma su salida.

| Medida | ANTES (publicado `d53d8ad`) | DESPUÉS (corregido) |
|---|---|---|
| Límite duro de limpieza (deadline) | **no existía** (`null`) | **4,0 s** (global 5 s − reserva de persistencia 1 s) |
| Inicio de la terminación forzada | 3,0 s | **2,5 s** |
| Tiempo concedido a `taskkill` | **30 s (fijo)** | **1,5 s** (el restante del deadline) |
| Tiempo concedido al reap del hijo | **10 s (fijo)** | **0 s** (el restante tras `taskkill`) |
| Acumulado con persistencia | **45 s** (3 + 30 + 10 + reserva 2 s) frente a un plazo global de 5 s | **5,0 s** = el plazo global |
| ¿Excede el plazo global? | **SÍ** | **NO** |
| Duración real de la simulación | 3,034 s (sin esperas largas reales) | 2,518 s |

La reproducción es **determinista**: se sustituyen `Popen`, `subprocess.run`
y `os.kill` por dobles que registran el tiempo **concedido** a cada espera
sin esperar de verdad. **No es una ejecución real en Windows** (la ejecución
real está en `windows_real/` y en los casos C, D y H de
`tests/test_pilot_launcher_temporal.py`).

## Defecto 2 — El lanzador acredita recursos cerrados sin evidencia

Con el código publicado y **sin** observar el código del hijo
(`exit_code.txt: UNKNOWN`), el estado seguía declarando:

| Campo | ANTES (publicado) | DESPUÉS (corregido) |
|---|---|---|
| Código del hijo | `UNKNOWN` | `UNKNOWN` |
| `proceso_hijo_terminado` | **`true`** (afirmación falsa: solo se *intentó* matar) | **eliminado**; ahora `terminacion_hijo_observada: false` |
| `alimentaciones_cerradas` | **`true`** (incondicional) | `alimentaciones_lanzador_cerradas: true` (lo propio del lanzador) + `recursos_hijo: UNKNOWN` |
| Terminación forzada | `terminacion_forzada: true` (sin distinguir solicitud de hecho) | `terminacion_forzada_solicitada: true` + `terminacion_hijo_observada: false` |

El esquema anterior mezclaba "se pidió" con "ocurrió". El nuevo separa
explícitamente:

- `parada_solicitada` / `parada_mecanismo` — **lo solicitado**;
- `terminacion_forzada_solicitada` / `terminacion_forzada_mecanismo` — **lo solicitado**;
- `terminacion_hijo_observada` — **lo observado** (solo si `Popen.wait()`
  devolvió el código);
- `codigo_salida_observado` / `codigo_salida_estado` (`observado` | `UNKNOWN`);
- `recursos_hijo: UNKNOWN` — el lanzador genérico **no puede** certificar los
  sockets del hijo; el estado del piloto se conserva como evidencia
  diferenciada (`evidencia_piloto`, solo se lista, no se interpreta).

## Comportamiento corregido (alcance real del control)

- **Un solo reloj monotónico y un solo deadline global.** Toda espera y toda
  llamada de terminación se acotan al **restante** de ese deadline. No quedan
  esperas fijas (30 s de `taskkill`, 10 s de reap, 30 s de interrupción) que
  se sumen al plazo.
- **Reparto explícito del margen:** reserva de persistencia (25 % del margen,
  máximo 5 s) + reserva de reap (máximo 2 s) + resto para la parada limpia y
  la terminación forzada. El proceso **no se mata en el último instante**.
- **La medición final incluye la persistencia:** `duracion_total_s` se mide
  después de escribir `exit_code.txt` y `launcher.json`;
  `cierre.json` publica la medición definitiva tras el veredicto. Si la
  persistencia lleva el reloj más allá del plazo global, el exceso se
  publica (`exceso_maximo_total_s > 0`,
  `incumplimiento_plazo_global: true`) y el lanzador devuelve **126**.
- **Sin promesas absolutas:** el control acota el tiempo que el lanzador
  espera y concede; **no** es una garantía del sistema operativo. Si una
  llamada del sistema ignora su propio timeout, el exceso se **mide** y se
  publica como incumplimiento (`excedio_la_concesion: true`), no se oculta
  ni se compensa reiniciando el reloj.
- **Se conservan** la parada limpia de Windows (`CREATE_NEW_PROCESS_GROUP` +
  `CTRL_BREAK_EVENT`) y la terminación forzada **solo sobre el árbol propio**
  (`taskkill /F /T /PID` sobre el PID del hijo; nunca búsquedas globales).

## Ejecución real en Windows (casos cortos, procesos locales)

| Caso | Código del lanzador | Resultado | Duración total (con persistencia) | Persistencia | Exceso | Terminación del hijo | `recursos_hijo` |
|---|---|---|---|---|---|---|---|
| normal (código 0) | **0** | `normal` | 0,056 s | 0,003 s | 0,0 s | observada | `UNKNOWN` |
| plazo + parada limpia | **124** | `timeout_trabajo_parada_limpia` | 1,074 s | 0,003 s | 0,0 s | observada | `UNKNOWN` |
| plazo + terminación forzada | **125** | `timeout_trabajo_terminacion_forzada` | 2,717 s | 0,005 s | 0,0 s | observada | `UNKNOWN` |

## Pruebas

`tests/test_pilot_launcher_temporal.py` — **19 passed** (14 previos + 5
nuevos). Casos nuevos: `taskkill` que agota su espera (se detecta y se
publica), hijo cuya salida no puede confirmarse (no se declara terminado),
persistencia que consume parte de la reserva (la duración publicada la
incluye), exceso temporal registrado honestamente (código 126) y ninguna
espera por encima del restante. Se conservan los casos de fin normal, salida
no cero, parada limpia, terminación forzada y proceso ajeno preservado.

Regresiones directamente afectadas: lanzador/rutas/diagnóstico 50 passed,
`test_research_pilot.py` 45 passed, operativo/CLI 9 passed → **123 passed**
en el conjunto afectado. Cero pruebas públicas de mercado.

## Lo que este bloque NO hace

No abre Binance, no ejecuta el diagnóstico público ni la ventana operativa;
no cambia estrategia, selección, funding, contabilidad, exposición,
presupuestos económicos ni la duración propuesta (40 200 s + 300 s); no toca
`opencode.json`, archivos ajenos, datasets, DBs, el dashboard de 3020 ni el
servicio 8792; no añade servicios, gestores ni dependencias.

## Artefactos

- `reproduccion_defectos.py` — arnés de simulación (parametrizable con la
  ruta del lanzador: publicado o corregido).
- `reproduccion_ANTES.json` — salida contra el lanzador publicado `d53d8ad`.
- `reproduccion_DESPUES.json` — salida contra el lanzador corregido.
- `ejecucion_real_windows.py` + `windows_real/` — ejecución real en Windows
  con los tres casos y sus artefactos (`launcher.json`,
  `estado_lanzador.json`, `cierre.json`, `exit_code.txt`, logs).
- `hashes.json` — hashes SHA-256 de todo lo anterior.
