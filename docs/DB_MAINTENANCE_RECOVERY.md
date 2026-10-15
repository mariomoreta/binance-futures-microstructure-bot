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

## Defecto corregido 2026-10-16 (leer antes de operar)

La version anterior del script tanteaba escritores con `BEGIN
IMMEDIATE` sobre el ORIGINAL antes del backup. Forense 2026-10-16:
esa sonda abria read-write y RECUPERABA (y eliminaba) el hot journal
del original — destruia justo la evidencia a respaldar y cambiaba el
hash del DB. Eliminada por completo: antes del backup verificado el
script solo hace lecturas de bytes (stat/copy/hash) y UNA lectura
JSON del registry; cero `sqlite3.connect` con capacidad de escritura
sobre el original (regresion con espia que lo prueba: exactamente 1
apertura rw, la `_recover` final). La ventana de mantenimiento es:
estado del registry no-ACTIVO (al entrar y justo antes del write) +
re-verificacion de hashes en ambos puntos; ningun paso declara
exclusion sostenida, cada puerta la re-prueba.

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
2. Backup real obligatorio del par (DB + journal) en
   `--backup-dir` (fuera del repo; el script rehúsa destinos dentro
   de git, alias por symlink/hardlink, y existentes). Los hashes
   solos NO sustituyen al backup: el script verifica los hashes de
   AMBAS copias (origen y backup deben coincidir byte a byte) y
   ensaya la restauración copiando el backup a temporal,
   recuperándolo y comparando esquema+conteos contra el pre-estado.
   Sin backup verificado + restauración probada no hay apply.
3. Abrir el canónico read-write UNA vez vía script auditado (modo
   `--apply` YA implementado y probado en fixtures temporales; 22
   tests en `tests/test_journal_recovery.py`, rama hot probada en el
   ensayo canónico). Comando exacto propuesto (NO ejecutar sin la
   autorización de abajo):

   python scripts/recover_hot_journal.py --db data/microprobe.db --out <temp>/recovery_canonical.json --expect-schema 10 --apply --backup-dir C:\proyectos\binance-db-backups\recovery-20261015-3a55052 --expect-db-sha256 df10cb35b44a37f3254fbc7234733dba2eaaa250b578787c20b66cc0e8c50b3c --expect-journal-sha256 2822655c3e4ae9cb03ed35598ebd84218042e605450e278c8a89a35af2fc3757

   Destino verificado 2026-10-16: fuera del repo (hermano, no
   descendiente) e inexistente (nada que sobrescribir; el script
   rehusaría de todos modos). Hashes medidos 2026-10-15; re-medír
   antes de autorizar: cualquier deriva rehúsa automáticamente, y el
   script re-verifica hashes + excluye escritores vivos
   INMEDIATAMENTE antes del write (sin aplicar ante deriva).
   Secuencia: verifica hashes → excluye escritores (lock-only, cero
   escrituras) → recupera en temporal y comprueba TODO → respalda el
   par real fuera del repo con doble verificación → ensaya
   restauración DESDE ese backup → compara aplicado-vs-restaurado
   (automático, sin --expect-counts) → y solo entonces abre el
   canónico. Protecciones: --out y --backup resueltos por realpath
   (symlinks/hardlinks incluidos), rehúsa .db* y data/, jamás
   sobrescribe. Ensayo canónico publicado:
   `docs/evidence/RECOVERY_REHEARSAL_20261015.json` (hot-rollback,
   integrity ok, schema 10, consumido, canónico intacto; re-ejecutable
   con el comando `reproduce` del propio informe).
4. Verificar: `integrity_check=ok`, schema 10, aplicado-vs-restaurado
   idénticos, journal consumido, hashes nuevos registrados.
5. Re-evaluar readiness por ruta V2 (debe pasar "Operational
   database"; el resto manda) y QA visual de /system. Sin arrancar
   ninguna corrida como parte de este mantenimiento.

## Rollback (restauración desde el par real, no desde hashes)

Si cualquier verificación difiere: NO continuar. La red de seguridad
es el backup REAL del paso 2 (DB + journal byte a byte fuera del
repo, hashes verificados en ambos sentidos): restaurar es copiar
`copy.db` → `data/microprobe.db` y `copy.db-journal` →
`data/microprobe.db-journal`, re-medir hashes contra el reporte, y
re-evaluar readiness. Los hashes solos documentan; solo el par
restaura. El ensayo de restauración del propio `--apply` (stage 3)
prueba este camino en cada ejecución.

## Autorización requerida (texto propuesto para el usuario)

"Autorizo aplicar docs/DB_MAINTENANCE_RECOVERY.md al canónico
(data/microprobe.db + journal) SIN iniciar corridas. Entiendo que el
paso 3 escribe en el canónico (recovery estándar SQLite) y que el
resto es solo verificación."
