# Piloto Anti Slop en OpenCode (alcance local, opcional)

Estado: **piloto instalado y descubierto por OpenCode v2.0.32**; no es una
puerta de aceptación funcional, no sustituye pruebas, no evalúa economía ni
rentabilidad. Fecha: 2026-10-21.

## 1. Origen y procedencia

- Repositorio: <https://github.com/miqdadbadjuber/anti-slop>
- Commit fijado: `439a2ef5b9dd0ebe74e8113ff43f5928d0fe2a6a`
- Versión upstream (`VERSION`): `3.2.21`
- Licencia: MIT, Copyright (c) 2026 Miqdad Badjuber (antislop).
  Copia íntegra en `.opencode/skills/antislop/LICENSE` y
  `.opencode/skills/antislop-code/LICENSE`.
- Verificación previa: árbol completo del commit consultado por API de GitHub y
  contenido descargado por `raw.githubusercontent.com` en ese mismo SHA. No se
  ejecutó `npx antislop-ai`, ni el instalador, ni el asistente de primera
  ejecución, ni se modificó configuración global.

## 2. Archivos incorporados (upstream intacto)

| Archivo local | Origen | Bytes | SHA-256 |
| --- | --- | --- | --- |
| `.opencode/skills/antislop/SKILL.md` | `skills/antislop/SKILL.md` | 57.827 | `64A1FF70BAFBFB7A105083CDFF0026A6F09BAF7E19D3AA1BC3E880CF7233F90C` |
| `.opencode/skills/antislop/VERSION` | `skills/antislop/VERSION` | 7 | `849BB24C350DA9619A368892A29ABA02C699DD6C1DC087DA2B649AAFAD978B78` |
| `.opencode/skills/antislop/LICENSE` | `LICENSE` | 1.083 | `9FD83FB1FDA52CA0094B96E2ED5A3D6C42A81B95A6C6326553F5BBE570F443DE` |
| `.opencode/skills/antislop-code/SKILL.md` | `skills/antislop-code/SKILL.md` | 8.944 | `004933009D352710DCBEA7817101D5C188474A442E3ECE26A6E0C18D3223898F` |
| `.opencode/skills/antislop-code/LICENSE` | `LICENSE` | 1.083 | `9FD83FB1FDA52CA0094B96E2ED5A3D6C42A81B95A6C6326553F5BBE570F443DE` |

Archivos locales propios (no upstream):

| Archivo | Bytes | Función |
| --- | --- | --- |
| `.opencode/skills/antislop/LOCAL_CONDITIONS.md` | 1.215 | Condiciones vinculantes dentro del directorio de la skill. |
| `.opencode/commands/antislop.md` | 2.760 | Comando `/antislop` bajo demanda. |

No se incorporaron `antislop-ui`, `antislop-copywriting`, `antislop-human`,
`antislop-layoutmobile`, `contrast-check.py`, plugins ni `.claude-plugin/`.
El núcleo cita esas skills como opcionales: aquí no están y no se ofrecen.

## 3. Alcance y límites del piloto

- Solo presentación y comentarios: estilo, comentarios redundantes,
  decoraciones, texto genérico. **Nunca** lógica, nombres, imports, umbrales,
  estrategias, pruebas ni mecánica económica.
- Revisión por defecto sin modificar archivos; `during` solo con instrucción
  explícita en la invocación.
- Máximo 5 hallazgos por revisión, cada uno con ubicación, regla (`R-XX`/`C-X`),
  motivo y propuesta mínima.
- No hay barrido automático del repositorio ni carga de todas las skills.
- No se leen ni escriben preferencias globales (`%APPDATA%\antislop\settings.json`).
  No se fija modelo ni se lanzan subagentes.
- El "First-Run Install Wizard" del núcleo queda desactivado por
  `LOCAL_CONDITIONS.md` y por el propio comando: no instala skills, no toca
  `AGENTS.md` y no descarga nada.

## 4. Precedencia del proyecto

Las instrucciones del usuario y los contratos del proyecto mandan sobre el
núcleo. En particular, Antislop no puede:

- borrar explicaciones de causalidad, concurrencia, seguridad, costes,
  funding, unidades o limitaciones;
- acortar documentación técnica por reglas de longitud;
- quitar licencias, referencias, `type: ignore`, pragmas o directivas;
- cambiar lógica, nombres, imports, umbrales, estrategias o pruebas;
- rediseñar pantallas existentes sin encargo;
- prohibir elementos funcionales del gráfico (rejilla, colores direccionales,
  niveles);
- activar trabajo móvil/Flutter;
- exigir otro `DESIGN.md`: `docs/DASHBOARD_V2_DESIGN_SPEC.md` y el resto de
  documentos de diseño ya cumplen esa función.

Un PASS de Antislop **no** es prueba de causalidad, seguridad, economía ni
rentabilidad. Las pruebas y la evidencia del proyecto siguen siendo la única
acreditación.

## 5. Uso

```text
/antislop frontend/src/components/panel/ExportPanel.tsx
/antislop docs/CURRENT_STATE.md          # revisión de presentación, sin editar
/antislop during src/microstructure_probe/paper_lab_engine.py   # modo durante, explícito
```

- Sin argumento el comando pide el alcance y se detiene.
- El comando carga el núcleo y, si hay comentarios de código en el alcance,
  `antislop-code`. No carga el resto del sistema antislop.
- Los hallazgos se entregan en el chat; no se crea `anti-slop/audit-*.md`
  (regla del núcleo anulada por las condiciones locales).

## 6. Verificación ejecutada

- OpenCode `v2.0.32`; skills en `.opencode/skills/` (descubrimiento automático
  documentado en `/v2/docs/skills/`).
- Descubrimiento real: tras escribir los archivos, la sesión activa recibió
  `antislop` y `antislop-code` en su lista disponible sin reiniciar.
- Registro del comando: `GET /api/command` con la cabecera
  `x-opencode-directory` del repositorio devuelve `antislop` con su descripción.
  Comprobado contra el servicio en ejecución, no inferido.
- Dos ejecuciones headless (`opencode run --standalone "/antislop <archivo>"`)
  como prueba de expansión real del comando:
  1. `scripts/paper_lab_session.py`: el agente recibió la plantilla expandida
     (la cita literalmente en su razonamiento), cargó el núcleo con la
     herramienta `skill`, no editó ningún archivo, y no terminó en 300 s:
     derivó a buscar `settings.json`/`antislop.md` y sufrió reintentos `503`.
     Se endureció el comando con la sección "Precedencia inmediata".
  2. `docs/COMMANDS.md` (con el comando endurecido): cargó el núcleo, buscó
     `antislop*.md` (el archivo real es `SKILL.md`) y terminó en error de
     proveedor (`Upstream request failed: Endpoint is unavailable`, exit 1).
     Sin ediciones.
  - Conclusión: expansión y carga verificadas; **entrega final del comando no
    verificada**. El informe piloto se ejecutó en la sesión principal siguiendo
    la plantilla.
- Revisión piloto (solo lectura, sin editar): `src/microstructure_probe/dashboard.py`
  (publicado, 1.914 líneas, sin cambios en el árbol) → 2 hallazgos y 5
  comentarios técnicos que deben conservarse (detalle en `docs/CURRENT_STATE.md`).
- Estado global intacto: `%APPDATA%\antislop\settings.json` y
  `~/.config/antislop/settings.json` **no existen**; `~/.config/opencode/opencode.json`
  conserva su fecha de modificación. Ningún archivo fuera del repositorio cambió.

### Revisión piloto (solo lectura, no aplicada)

Archivo: `src/microstructure_probe/dashboard.py` (publicado y estable; sin
cambios en el árbol tras la revisión).

1. **R-31 · banners decorativos.** Seis etiquetas de sección envueltas en
   `# -----…` (líneas 88-90, 142-144, 179-181, 523-524, 1244-1245 y
   1901-1902). Motivo: la decoración es el mensaje y la etiqueta sola basta.
   Propuesta: dejar solo la línea de etiqueta, o borrarla donde no aporte.
2. **R-31 · etiqueta de categoría sin información.** `# HTML rendering`
   (523-524) encabeza un bloque de ~700 líneas y no dice nada que el código no
   diga. Propuesta: eliminar la etiqueta o sustituirla por lo que el bloque
   garantiza (HTML servido en el servidor, sin estado de trading en el cliente).

Nota de alcance (no es hallazgo): el mismo patrón de banner aparece 12 veces en
`dashboard.py` y 6 en `control.py`; conviene decidirlo una vez, no dentro del
piloto.

Comentarios técnicos que Antislop **no** debe tocar y que la revisión conservó:
`dashboard.py:51-53` (por qué se re-exportan helpers y qué siguen resolviendo
los tests), `dashboard.py:111-113` (implementaciones movidas verbatim),
`dashboard.py:442-445` (observación pura: GET no reconcilia ni escribe),
`dashboard.py:1319-1320` (control local POST-only, localhost, nonce + Origin,
sin superficie de trading) y `dashboard.py:1404-1406` (solo dos entradas
validadas; sin shell ni passthrough, inyección imposible).

## 7. Coste de instrucciones (medido en bytes, no en tokens)

- Núcleo: 57.827 bytes (~14,5k tokens aproximados por la regla 4 bytes/token;
  **no medido** con tokenizador).
- `antislop-code`: 8.944 bytes.
- Condiciones + comando: 3.975 bytes.
- La lista de skills disponible solo muestra ID, nombre y descripción; el cuerpo
  se carga al invocar. No se promete ahorro de tokens: no se midió.

## 8. Retirada

1. Borrar `.opencode/skills/antislop/` y `.opencode/skills/antislop-code/`.
2. Borrar `.opencode/commands/antislop.md`.
3. Quitar la línea de uso opcional de `AGENTS.md`.
4. Conservar este documento y las entradas de `DECISIONS`/`CURRENT_STATE` como
   historia; marcar la retirada en `FEATURE_BACKLOG`.

No hay nada instalado fuera del repositorio, así que la retirada no toca otros
proyectos ni la configuración del usuario.

## 9. Actualización

El piloto está fijado a `439a2ef`. Para actualizar: descargar los mismos cinco
archivos desde el nuevo commit, recalcular SHA-256, revisar el diff del núcleo y
volver a medir el tamaño antes de sustituirlos. Nunca actualizar en caliente
dentro de una sesión activa sin registrar la nueva revisión aquí.
