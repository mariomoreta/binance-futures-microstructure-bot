# Contrato de preflight de almacenamiento

Productor: `python scripts/storage_preflight.py [--root .] [--out JSON]
[--compare PREVIO.json]` (solo lectura; jamas estima, jamas escribe DBs,
jamas inicia servicios). Consumidor pendiente: panel System/V2
(renderiza `warnings[]`; cableado UI en la linea V2, no aqui).

## Campos (todos medidos o UNKNOWN)

| Campo | Origen |
|---|---|
| `operational_db.{path,bytes,tables}` | `data/microprobe.db`: tamano + `COUNT(*)` por tabla (URI `mode=ro`) |
| `historical_db.{path,bytes,tables}` | `data/historical/historical.db`: idem |
| `logs.{bytes,files,largest[],rotation_cap}` | arbol `logs/`; tope: NONE (no existe en codigo) |
| `disk.{total,free}` | `shutil.disk_usage` del root |
| `retention_from_code` | `RESEARCH_RETENTION_DAYS` (7/90/90), caps `max_*` de `PersistenceStore`, 90d prospective (importados, no adivinados) |
| `growth` | UNKNOWN sin `--compare`; con previo, delta medido en bytes |
| `warnings[]` | DB ausente/ilegible, disco < 1GB, logs sin tope, logs ausente |

Medicion de referencia (2026-10-13, este host): microprobe 238.9MB
(observations 10000/10000, rejections 1000/1000, snapshots 1000/1000 —
retencion trabajando), historical 19.2MB, logs 117.4MB en 166 ficheros,
libres 159.3GB, 1 warning (logs sin tope). No extrapolar a otros hosts.
