# Handoff futuro — investigacion entradas/salidas intradia
Estado: PREPARADO para un prompt posterior. NO interrumpir O1.
Base de esta documentacion: e887287d6dee00c80687ff34d432a34caeef5b63.
Leer antes AGENTS + CURRENT_STATE/TASK_QUEUE/MASTER_PLAN/DECISIONS/SUCCESS_GATES/
WORKFLOW/FEATURE_BACKLOG y el inventario operativo publicado en 207186d7 si aun no
fue reconciliado. No reemplazar estado operativo reciente por versiones de esta rama.

## Material listo
- INTRADAY_EXTREME_MOVES_PILOT_20261014.md: observacion y limites.
- INTRADAY_ENTRY_EXIT_STUDY_PLAN.md: comparacion y criterios de aceptacion.
- INTRADAY_V2_RESEARCH_CONTRACT.md: propuesta de lectura/presentacion.
- ../evidence/INTRADAY_PILOT_MANIFEST.json: hashes y procedencia.
- ../evidence/intraday_raw_20261014.json: muestra publica compacta (30h x 11 series).
- ../evidence/analyze_intraday_20261014.py: calculo offline stdlib.
- ../evidence/intraday_analysis_20261014.json: salida reproducible completa.
Reproducir en COPIA TEMPORAL de los tres archivos intraday_raw, analyze e intraday_analysis
para no sobrescribir evidencia versionada: python analyze_intraday_20261014.py.
Comparar summaries/episodes/alert_stats semanticamente; raw/full outputs ya contrastados.
No pedir de nuevo ZIP para reproducir esta muestra. El original completo sigue aparte.

## Primer paquete cuando el usuario lo solicite
1. Verificar HEAD/ramas y preservar trabajo activo; incorporar solo documentos/evidencia
   de esta revision. No merge global ni checkout/reset sobre trabajo ajeno.
2. Reproducir piloto, auditar sesgos/cobertura y mapear features existentes/faltantes.
3. Preparar pre-registro de una comparacion acotada por familia A/B/C; valores PENDING
   se resuelven con dev y decision versionada, antes de OOS. No activar reglas del piloto.
4. Implementar estudio con motor existente y pruebas causales, costes y censura.
5. Proponer DTO read-only y validar en V2 solo tras existir datos; sin calculo en UI.
6. Commits selectivos y publicacion normal con SHA/compare y evidencias.
Entregar capacidad ganada, resultado (incluido negativo), limites y siguiente experimento.
El revisor contrastara prompt, fuentes exactas, resultados y omisiones.
Sin IA/Kronos/noticias nuevas; no ordenes, cuenta privada ni cambios a Start por este paquete.
