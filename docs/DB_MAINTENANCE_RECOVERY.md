# Procedimiento de mantenimiento: recovery del hot journal canónico

Status: PROPUESTO — requiere autorización explícita del usuario ANTES de
aplicarse al original. Ensayado el 2026-10-15 solo sobre copia temporal
(`journal-recovery-*`, reporte en TEMP `recovery_report.json`).
Separado del arranque: no es una corrida, no toca estrategias ni gates.

## Bloqueo circular que resuelve (sin omitir readiness ni borrar nada)

- Readiness exige DB legible (check "Operational database" + storage).
- `data/microprobe.db-journal` (41552B, del aborto 00:08:33Z) es un hot
  journal: abrir readOnly exige recovery (= escritura) y SQLite lo rehúsa
  (`ERR_SQLITE_ERROR: attempt to write a readonly database`).
- La corrida no puede empezar con readiness bloqueado, y el bloqueo no se
  salta: la salida es este mantenimiento autorizado, tras el cual
  readiness se reevalúa (DB legible → verde si el resto pasa).

## Precondiciones verificadas (2026-10-15, este host)

- Cero escritores: ningún `python.exe` en pie; V2 (PID 18216) solo abre
  readOnly (falla en open, no retiene handles); watchers muertos.
- Par preservado con hashes SHA256:
  - `data/microprobe.db` 238927872B
    `df10cb35b44a37f3254fbc7234733dba2eaaa250b578787c20b66cc0e8c50b3c`
  - `data/microprobe.db-journal` 41552B
    `2822655c3e4ae9cb03ed35598ebd84218042e605450e278c8a89a35af2fc3757`
- Ensayo en copia: `integrity_check=ok`, schema 10, conteos iguales
  (1000/10000/1000/12/8195/66/228/375/500), journal consumido, diff
  pre/post recovery = 0 en todas las tablas (rollback limpio de UNA
  transacción interrumpida; cero filas comprometidas), canónico
  byte-idéntico antes/después.

## Evidencia: qué viene de logs y qué de la DB

- De logs (`logs/probe-runs/probe-20261015T000730Z.log`, 9 líneas,
  última 00:08:12Z rt=41s): cronología, conteos de mensajes por stream
  (22130 totales), rechazos 3234 por stream, latencias p50/p95/max por
  stream/símbolo, clock (-864ms/558ms), freshness, OI 3/3, discovery
  927→452, research writes=12, safety 0/0/0.
- De la DB recuperada (copia, inmutable + post-recovery): conteos
  retenidos por tabla, span de snapshots (08-oct→00:08:12Z) y de
  price_samples (00:07:30–00:08:00Z, 4/símbolo), schema 10, 22 tablas.
- Del registro (sidecar JSON, no DB): run/started/exit, supervisor (3
  ciclos, aborto 0.146136>0.05), sentinel (3 ciclos, stale-record).
- Del journal: solo su existencia/tamaño/hashes + diff 0 (contenido
  transaccional no inspeccionado a nivel fila: rollback estándar).

## Pasos concretos propuestos (aplicar SOLO con autorización)

1. Re-verificar precondiciones: cero `python.exe`, V2 solo-lectura,
   hashes del par iguales a los de arriba (abortar ante cualquier
   diferencia: el estado cambió y el ensayo ya no aplica).
2. Copia de seguridad del par a `docs/evidence/` (NO: son 239MB;
   alternativa: registrar hashes + confiar en el par intacto; este
   documento propone NO duplicar y abortar si difieren).
3. Abrir el canónico read-write UNA vez vía script auditado
   (`scripts/recover_hot_journal.py --db data/microprobe.db --out
   <temp>/recovery_canonical.json` adaptado a modo `--apply` + doble
   confirmación; el modo actual es solo-ensayo y rehúsa el original).
   NOTA: el script actual NO trae modo apply; implementarlo es parte
   de la autorización (cambio mínimo, misma verificación + backup de
   hashes pre/post en el reporte).
4. Verificar: `integrity_check=ok`, schema 10, conteos vs los del
   ensayo, journal consumido, hashes nuevos registrados.
5. Re-evaluar readiness por ruta V2 (debe pasar "Operational
   database"; el resto manda) y QA visual de /system. Sin arrancar
   ninguna corrida como parte de este mantenimiento.

## Rollback

Si cualquier verificación difiere del ensayo: NO continuar; el par
original sigue intacto salvo el paso 3 (que solo corre tras backup de
hashes). No existe restauración automática: la red de seguridad es no
haber tocado nada antes del paso 3 y abortar ante diferencias.

## Autorización requerida (texto propuesto para el usuario)

"Autorizo aplicar docs/DB_MAINTENANCE_RECOVERY.md al canónico
(data/microprobe.db + journal) SIN iniciar corridas. Entiendo que el
paso 3 escribe en el canónico (recovery estándar SQLite) y que el
resto es solo verificación."
