# Handoff — Reconciliación plan → proyecto actual y ruta a selección automática + Paper Lab

**Fecha:** 2026-10-20. **Presupuesto cero.** No se inicia monitor, colectores persistentes, paper prospectivo ni órdenes. Solo inspección, cálculos offline sobre copias y reconciliación documental.

## 1. SHA de referencia y rama

| Dato | Valor |
|---|---|
| Repositorio | `C:\proyectos\binance-futures-microstructure-bot` (local, sin OneDrive) |
| Rama | `review/o1-funcional-v2-observacion` (al día con `origin/review/o1-funcional-v2-observacion`) |
| Remoto | `https://github.com/mariomoreta/binance-futures-microstructure-bot.git` (fetch + push) |
| SHA inicial | `b9c27338dee21160da9a839894029c3c70b0e316` |
| SHA final | `b9c27338dee21160da9a839894029c3c70b0e316` (commit documental `b9c2733` en `PAPER_LAB_PLAN_ETAPA5.md`) |
| Compare URL | https://github.com/mariomoreta/binance-futures-microstructure-bot/compare/2a65ccfcefe66edeae889466841680cab7416f21...b9c27338dee21160da9a839894029c3c70b0e316 |
| Fetch normal | `git fetch origin` sin cambios remotos nuevos. Sin reset/clean/force. |

## 2. Estado vigente y tarea activa

**Estado vigente:** Fase 1 (Market Intelligence + Dashboard) avanzada; EVAL-CENSUS-V2 cerrado con veredicto global INCOMPLETE (residual MINA/NMR); selector extremo mecanismo probado con fixtures (no evaluado sobre censo); V2 con vistas reales (`/movers`, `/paper-lab`) y stub (`/backtest`); Paper Lab replay de ingeniería construido pero **no publicado en Git** (todo untracked).

**Tarea activa:** definida y coordinar cierre con la entrega de Paper Lab del otro agente. No se abrió otra auditoría general.

## 3. Documentos y código que son fuente de autoridad

- `docs/PRODUCT_GOAL.md` (objetivo, KPI, anti-goals; no reescrito)
- `docs/EXTREME_MOVERS_OBJECTIVE.md` (cuatro escenarios H1/H2/H3/H2-rebote; ranking ≠ entrada)
- `docs/CURRENT_STATE.md` (sección Reconciliación 2026-10-20 añadida)
- `docs/TASK_QUEUE.md` (reconciliación y próxima acción añadida)
- `docs/DECISIONS.md` (entrada 2026-10-20 añadida, append-only)
- `docs/FEATURE_BACKLOG.md` (censo corregido + entry Paper Lab añadido)
- `docs/PAPER_LAB_PLAN_ETAPA5.md` (Estado actual: 4 estados distinguidos)
- `docs/MARKET_DATA.md` (fuentes públicas Binance verificadas)
- `docs/SIGNAL_RESEARCH_PLAN.md` (contexto BTC, agotamiento, absorción — hipótesis, no señales)
- `docs/POSITION_MANAGEMENT.md` (acciones de posición, futuro)
- `docs/HANDOFF_RECONCILIACION_PAPER_LAB_20261020.md` (este informe, compacto, enlaza fuentes)

## 4. Decisiones y restricciones

- **Objetivo temprano:** detectar aceleración antes de entrar al top.
- **Objetivo post-extremo:** continuación (H1 alcista / H3 bajista), agotamiento/reversión (H2), rebote (H2 variante separada) — hipótesis separadas, no señales aprobadas.
- Ranking y volumen alto **NO** son entradas automáticas. Top mover = criterio de descubrimiento, nunca entrada.
- **Capitalización ≠ liquidez; volumen negociado ≠ entrada neta de dinero.**
- **Presupuesto cero:** sin suscripciones, trials facturables, tarjetas ni infraestructura de pago. Datos existentes + APIs públicas gratuitas oficiales de Binance prioridad.
- Historial personal de trades **no requerido**.
- IA/Kronos/REA y otras fuentes **diferidos** (F-KRONOS-01 PROPOSED, fuera de alcance).
- Selector: el censo **no sustituye** universo histórico, ranking rolling24 ni liquidez ausentes. No ejecutar evaluación completa del selector por faltar inputs.
- Dashboard muestra decisiones (WATCH / SIN_ENTRADA / DESCARTADO); **no es motor de señales**. Nunca alimentar la estrategia con estado renderizado del frontend.
- Controles del replay **separados** de Start/Stop del monitor.
- Residual MINA/NMR mantenido **separado** del replay del trío.
- No declarar vistas inexistentes ni planificadas sin inspeccionar (`/backtest` = stub).
- No repetir el mismo informe como entrega nueva; no dejar el plan solo en conversación/archivo externo.

## 5. Comandos ejecutables (solo lectura / offline, sin Binance)

```bash
# Ver identidad del repo
git status -sb
git rev-parse HEAD
git fetch origin

# Verificar determinismo del artefacto Paper Lab (solo lectura, --check no escribe)
python scripts/build_paper_lab_replay.py --package docs/evidence/eval-census-v2-package --traces-dir <traces_dir> --out frontend/src/data/paper-lab-replay-v1.json --check
# Esperado: PASS: artefacto determinista sha256=7ba452c308378c7f26a20b12761625dcace6b839ba7576d0221bba0346f41826

# Suite canonica (sin cambios de código en este alcance; ejecutar solo si se justifica)
python run_tests.py

# Confirmar que audit_public_data NO existe
git grep -l audit_public_data  # esperado: sin resultados
```

`<traces_dir>`: directorio con `reconstruction_manifest.json` y `trades_*.json` (ej. `C:\proyectos\binance-temp\paper_lab_audit_20261019_codex\traces` o el paquete). No iniciar Binance ni paper prospectivo.

## 6. Matriz: corregido / pendiente / dependencia de otro agente

| Ítem | Estado | Detalle / respaldo |
|---|---|---|
| `audit_public_data` localizada | **No localizable** | No existe en checkout ni Git. Mantener como NO LOCALIZADA. |
| 39 tests entrega | Real, ajena | `tests/test_p14b_validation.py` (P1-14B.1–.11), no es audit_public_data. |
| Esquema operativo vigente | **Corregido** | Operativo v10 (22 tablas) + histórico v3 (16 tablas). `docs/DECISIONS.md`, `DASHBOARD_V2_27B7AF5_READ_HANDOFF.md`. |
| Trades 5255 desglose | **Corregido** | Hipótesis 2991 (5 abiertas → 2986 realizadas); Placebo 2264 (2 abiertas → 2262 realizadas); total 5255 (7 abiertas → 5248 realizadas). `docs/ADDENDUM_CENSUS_EVAL_V2_CORRECCION.md`. |
| MFE/MAE | **Corregido** | Excursión por posición, NO ganancia capturada por la salida. `docs/CURRENT_STATE.md`, `BACKTEST_READ_CONTRACT_V1.md`. |
| V2 vistas | **Verificado** | `/movers` real; `/paper-lab` componente real; `/backtest` stub (FutureWorkspace). |
| Paper Lab publicado en Git | **Pendiente (otro agente)** | Ningún archivo publicado (todos untracked). Artefacto determinista `--check` PASS sha256 `7ba452c3...`. |
| Paper Lab servido/revisado visual | **Pendiente (otro agente)** | No confirmado por este agente; no URL local verificada. |
| Selector automático (protocolo) | **Pendiente** | Sobre EVAL-CENSUS-V2, info en T, sin lookahead, ventana incompleta → UNKNOWN. |
| Adquisición escalonada | **Pendiente (protocolo solo)** | Universo ligero → candidatos → detalle limitado; fuentes gratuitas; sin colectores iniciados. |
| Residual MINA/NMR | **Pendiente (otro agente / build_report)** | Falta build_report MINAUSDT/1h y NMRUSDT/1h. Separado del replay del trío. |

## 7. Estado verificable de Paper Lab (cuatro estados)

| Estado | Qué existe | Qué NO existe / no se afirma |
|---|---|---|
| Trabajo local en curso | Componentes, page.tsx, format.ts, build script, tests (otro agente) | Todo **untracked / no publicado en Git** |
| Código publicado en Git | Ninguno | — |
| Probado | Artefacto determinista `--check` PASS; tests existen | Suite frontend no ejecutada por este agente; archivos no publicados |
| Servido y revisado visualmente | — | No servido; no URL local verificada; monitor :3020 detenido |

**SHA/build/URL solo si comprobados:** sha256 del artefacto `7ba452c308378c7f26a20b12761625dcace6b839ba7576d0221bba0346f41826` (verificado con `--check`). **No hay URL local verificada por este agente** (no se sirvió next).

## 8. Pendientes con responsable / dependencia

| Pendiente | Responsable | Dependencia |
|---|---|---|
| Publicar artefacto, parser, componentes, tests de Paper Lab en Git | Otro agente (Paper Lab) | — |
| Servir y revisar visualmente Paper Lab; URL local verificada | Otro agente | Artefacto publicado |
| Selección independiente del P&L + reconciliación P&L/costes al cierre | Otro agente | Artefacto determinista |
| Capturas antes de entrada / abierta / cerrada | Otro agente | Sesión de replay servida |
| SHA/build servido y URL local verificada | Otro agente | next build/start sobre la rama |
| Cerrar residual MINA/NMR (build_report) | Otro agente / censo | build_report MINAUSDT/1h y NMRUSDT/1h |
| Protocolo de selección automática offline sobre EVAL-CENSUS-V2 | Este agente | Ninguna (datos existentes) |
| Protocolo de adquisición escalonada (solo documento, sin colectores) | Este agente | Ninguna |

## 9. Próxima acción única hacia la simulación automática

Definir y ejecutar (offline, sobre copia, presupuesto cero, sin órdenes ni capital) el protocolo de selección automática sobre EVAL-CENSUS-V2, usando solo información disponible en T (sin lookahead; ventana incompleta → UNKNOWN), emitiendo para cada candidato `WATCH` / `SIN_ENTRADA` / `DESCARTADO` con motivo versionado. Es la dependencia previa al motor paper completo (Etapa 5). Tras ello, coordinar cierre con la entrega de Paper Lab del otro agente.

## 10. Vínculos (fuentes, no sustituto de código/evidencias)

- `docs/PAPER_LAB_PLAN_ETAPA5.md` — Paper Lab estado actual y aceptación de entrega.
- `docs/CURRENT_STATE.md` — correcciones al informe previo y hechos de identidad.
- `docs/TASK_QUEUE.md` — reconciliación y próxima acción.
- `docs/DECISIONS.md` — decisión 2026-10-20 (append-only).
- `docs/FEATURE_BACKLOG.md` — censo corregido + entry Paper Lab.
- `docs/ADDENDUM_CENSUS_EVAL_V2_CORRECCION.md` — desglose trades 2991/2264.
- `docs/HANDOFF_RECONCILIACION_PAPER_LAB_20261020.md` — este informe.
