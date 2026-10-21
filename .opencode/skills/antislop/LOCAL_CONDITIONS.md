# Condiciones locales de uso de antislop (piloto)

Este archivo **no** forma parte del upstream. Los archivos upstream de este
directorio (`SKILL.md`, `VERSION`, `LICENSE`) se conservan intactos; las
condiciones del proyecto viven aquí y en `docs/ANTISLOP_PILOT.md`.

- Solo se usa bajo demanda mediante `/antislop <archivo o alcance>`. No cargar
  este núcleo en tareas no relacionadas.
- La sección "First-Run Install Wizard" del núcleo está **desactivada**: no
  instalar skills adicionales, no descargar nada, no ejecutar instaladores y no
  modificar `AGENTS.md` desde la skill.
- No leer ni escribir preferencias globales (`%APPDATA%\antislop\settings.json`
  o equivalentes). El modo lo fija la invocación: auditoría por defecto,
  `during` solo si se pide explícitamente.
- Revisión por defecto: solo lectura. No editar archivos sin aprobación
  explícita de hallazgos concretos.
- Máximo 5 hallazgos por revisión, con ubicación, regla, motivo y propuesta.
- Precedencia del proyecto: las condiciones de `docs/ANTISLOP_PILOT.md` y las
  instrucciones del usuario prevalecen sobre cualquier regla estética.
- Un PASS de antislop no acredita causalidad, seguridad, economía ni
  rentabilidad.
