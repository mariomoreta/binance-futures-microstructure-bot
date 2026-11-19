# WORKFLOW

## Active scope override (2026-10-20)

`docs/DESKTOP_FIRST_SCOPE_20261020.md` governs current delivery: desktop web
only. Visual verification remains required for desktop changes. Mobile
layouts, 360/390 px QA/captures and Flutter are deferred and must not block
acceptance or create tasks. Preserve historical mobile evidence.


For every engineering task:

```text
AUDIT → IMPLEMENT (minimal) → targeted tests → static/type checks
  → safe live verification (when applicable)
  → update CURRENT_STATE → update DECISIONS (if methodology changed)
  → update TASK_QUEUE → selective Git commit
  → evaluate phase gate → choose next authorized task
```

For every Dashboard V2 slice, the binding expansion is:

```text
AUDIT → PLAN → IMPLEMENT → TEST → VISUAL VERIFY
  → DOCUMENT → CHECKPOINT → NEXT
```

`VISUAL VERIFY` means a fresh render/capture compared with the approved
reference at the required viewport(s). It is mandatory for visual changes and
may be marked `NOT APPLICABLE` only for documentation-only or nonvisual work.
Tests do not substitute for visual evidence. See
`docs/DASHBOARD_V2_MIGRATION_PLAN.md` and
`.agents/skills/dashboard-v2/SKILL.md`.

## Step details

1. **AUDIT** — read the actual files/config/tests involved. State what exists
   before touching it. No assumptions from filenames.
2. **IMPLEMENT** — smallest change that completes the task. Extend the
   baseline; don't restructure speculatively. Thresholds go in config, not code.
3. **Tests** — add/extend targeted unit tests (known-value style). Full suite
   must pass via the canonical command from the repo root:
   `python run_tests.py` (see `docs/COMMANDS.md`).
4. **Static/type checks** — available tooling as configured; keep imports and
   public behavior clean.
5. **Safe live verification** — public streams only, bounded `--duration`,
   logs via external capture. The probe itself stays stateless; durable
   storage goes through the P1-02 persistence foundation, never ad-hoc files.
6. **Document** — `CURRENT_STATE` reflects reality; `DECISIONS` gets
   methodology changes; `TASK_QUEUE` advances. Never describe intent as done.
7. **Checkpoint** — selective `git add` of the coherent unit; evidence-backed
   message. Never blind bulk staging when unrelated work exists.
8. **Gate** — check `docs/SUCCESS_GATES.md`: did this move a gate? Say which,
   with evidence link.
9. **Next** — pick the next authorized task in the current phase only.

For Dashboard V2, `PLAN` records the bounded slice, contracts, acceptance
criteria, and rollback boundary before implementation. `TEST` includes
contract and regression checks. `VISUAL VERIFY` follows those checks and
precedes factual documentation.

## Diseño y pruebas de investigación cuantitativa

Esta guía complementa [SUCCESS_GATES](SUCCESS_GATES.md). Aplica al diseñar
pruebas nuevas o interpretar resultados; no reabre bloques cerrados ni cambia
criterios, parámetros o autorizaciones ya congelados.

1. **Fijar la decisión antes de mirar resultados.** Registrar qué queremos
   mejorar (selección, entrada, salida o riesgo), la hipótesis, la regla de
   referencia, la única diferencia a probar, el universo, el horizonte y
   los criterios de evaluación e insuficiencia. Si una variante nació al
   mirar resultados, marcarla como exploratoria y reservar datos distintos
   para confirmarla. Un mínimo de casos no garantiza evidencia suficiente.
2. **Reproducir lo que se podía saber.** Separar el instante del evento de
   cuándo quedó disponible cada dato. Usar exclusivamente información
   disponible al decidir (velas cerradas cuando la regla lo requiera).
   Aplicar la misma cobertura al comparar. Conservar faltantes, motivos
   y denominadores; un hueco no es un cero ni prueba que nada cambió.
3. **Aislar el efecto.** Para probar una salida, mantener entrada, dirección
   y límite del horizonte; comparar ambas salidas por operación. El cambio
   observado dispara la alternativa; la frecuencia del dato determina cuándo
   se puede medir. Distinguir un precio simulado de un fill. Informar cuántas
   decisiones cambiaron, cuánto se recortaron pérdidas y qué ganancias se
   sacrificaron. Un coste fijo igual se cancela en el delta; mostrar bruto y
   resultado condicionado por separado, sin tratar funding desconocido como
   cero ni confundir esa sensibilidad con costes de ejecución comprobados.
4. **Separar exploración de confirmación.** Comparar primero con una regla
   sencilla (p. ej., solo precio en el mismo universo y corte). Publicar
   cobertura, tamaño de muestra y concentración por contrato y periodo.
   Tratar señales repetidas o con horizontes solapados como dependientes.
   Si se ajustan parámetros o modelos, separar cronológicamente el ajuste
   de la evaluación y evitar horizontes solapados entre ambos. Una sola
   ventana puede orientar la siguiente pregunta, no justificar promoción.

### Referencias y cuándo aplicarlas

| Referencia oficial | Uso previsto |
|---|---|
| [MIT 18.S096: clases 3, 6 y 8](https://ocw.mit.edu/courses/18-s096-topics-in-mathematics-with-applications-in-finance-fall-2013/pages/lecture-notes/) | Probabilidad, regresión y series temporales para diseñar controles y evaluar evidencia incremental. No hace falta ajustar una regresión para la prueba de salida actual. |
| [MIT 18.S096: clase 9](https://ocw.mit.edu/courses/18-s096-topics-in-mathematics-with-applications-in-finance-fall-2013/video_galleries/video-lectures/) | Volatilidad. Si se autoriza estudiar extensión, empezar con una referencia histórica sencilla del mismo contrato, calculada con datos disponibles. Una posible comparación con GARCH sigue el estudio diferido [F-GARCH-01](FUTURE_RESEARCH_OPTIONS.md#f-garch-01--volatilidad-y-riesgo-propuesta-diferida); estimar volatilidad no da dirección LONG/SHORT. PCA también queda como opción de investigación. |
| [MIT 15.401: Finance Theory I](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/) | Futuros, riesgo y exposición conjunta entre contratos. Para reglas de funding y tipos de contrato, usar las fuentes específicas del mercado. |
| [Stanford EE364A](https://see.stanford.edu/Course/EE364A) y [Multi-Period Trading via Convex Optimization](https://web.stanford.edu/~boyd/papers/cvx_portfolio.html) | Asignación de capital cuando haya señales evaluadas que compitan por capacidad y existan restricciones y costes defendibles. El optimizador no produce la señal. |

### Ejemplo: salida temprana en la ventana 4

La [comparación publicada](evidence/salida-temprana-ventana4-20261118/README.md)
mantuvo la misma entrada y adelantó la salida en 106 de 106 pares evaluables;
37 anclas quedaron sin evaluar. En 99 de 106 se activó en el primer bloque.
La media del delta fue +4,68 bps y la mediana −2,87 bps. El resultado
`SIN_DIRECCION_CLARA` no respalda activar la regla ni elegir subgrupos después
de ver sus resultados. Si se estudia otra vez un disparador que actúa casi
siempre al mismo tiempo, compararlo también con una salida por tiempo fijo
para separar el valor del dato del efecto de recortar el horizonte. Esto no
abre otra captura ni cambia el experimento cerrado.

## Autonomous loop

`LOOP PHASE <n>` repeats the above across tasks already authorized in phase n.
It MUST STOP when: human authorization is required; live/account mutation
would be needed; methodology or strategy change is required; evidence
contradicts the plan; tests fail unresolved; external dependency blocks;
destructive migration required; secrets needed; or the phase gate is reached.
Never "keep coding until something looks profitable."
