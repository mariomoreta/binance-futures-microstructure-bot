---
description: Revisión estilística opcional (Anti Slop) de un archivo o alcance acotado; no corrige función
---

Revisión Anti Slop (piloto local: solo presentación y comentarios) sobre: $ARGUMENTS

## Precedencia inmediata
- Las condiciones de este comando y de `docs/ANTISLOP_PILOT.md` mandan sobre el núcleo, incluidas sus secciones de instalación y de resolución de modo.
- No busques `antislop.md`, `settings.json` ni rutas globales del sistema; no preguntes el modo (ya está fijado abajo) y no instales nada.

## Alcance
- Revisa únicamente el archivo o alcance indicado arriba.
- Si no hay alcance, pide el archivo o el alcance y termina. No explores el repositorio ni revises "todo" por iniciativa propia.
- Carga solo `.opencode/skills/antislop/SKILL.md` (núcleo) y, si el alcance incluye comentarios de código, `.opencode/skills/antislop-code/SKILL.md`. Ninguna otra skill de antislop.
- No fijes modelo, no lances subagentes, no guardes preferencias globales y no ejecutes el instalador ni el "First-Run Install Wizard" del núcleo.

## Modo
- Por defecto: auditoría (`after`), sin modificar archivos.
- Modo `during` solo si esta invocación lo pide explícitamente ("during", "mientras escribo", "aplica mientras construyo").
- No leas ni escribas `%APPDATA%\antislop\settings.json` ni equivalentes; no persistas el modo.
- Anuncia una sola vez `antislop activo: after (por defecto de la invocación).` o, si se pidió durante, `antislop activo: during (override de sesión).`

## Salida
- Máximo 5 hallazgos. Formato: ubicación (`archivo:línea`), regla (`R-XX`/`C-X`), motivo en una línea y propuesta concreta y mínima.
- Si no hay hallazgos que superen el umbral, dilo en una línea y no inventes trabajo.
- Separa "estilístico" de "funcional": lo funcional se reporta como nota; nunca se corrige en esta revisión.
- No reescribas archivos completos, no reformatees y no apliques cambios sin aprobación de números concretos.

## Precedencia del proyecto (prevalece sobre el núcleo)
- No elimines comentarios que explican causalidad, concurrencia, seguridad, costes, funding, unidades o limitaciones.
- No acortes documentación técnica por una regla de longitud; no quites licencias, referencias, `type: ignore`, pragmas ni directivas de herramientas.
- No cambies lógica, nombres, imports, umbrales, estrategias ni pruebas para "limpiar".
- No rediseñes pantallas sin encargo y no prohíbas elementos funcionales (rejilla, colores direccionales, niveles).
- No actives trabajo móvil/Flutter. No exijas otro `DESIGN.md`: los documentos de diseño existentes cumplen esa función.
- Un PASS de Antislop no acredita causalidad, seguridad, economía ni rentabilidad.
- Condiciones completas: `docs/ANTISLOP_PILOT.md`.
