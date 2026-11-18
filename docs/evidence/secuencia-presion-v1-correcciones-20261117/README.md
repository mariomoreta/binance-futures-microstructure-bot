# Correcciones locales SECUENCIA-PRESION-V1 y extractor de cobertura — 2026-11-17

Base publicada: `619d357443ace0aa7c0b939f07b6a1457265adfd`.
Rama: `research/universe-liquidez-v1`.
Alcance autorizado: completar las correcciones locales del detector
`SECUENCIA-PRESION-V1` y del extractor `scripts/extraer_cobertura_research_db.py`.
Sin acceso a Binance, sin capturas nuevas, sin ordenes, sin cambios de
estrategia, sin dashboard ni infraestructura. No se abre otra auditoria general.

Este bloque **rectifica** dos defectos de la base publicada:

1. El CLI del detector dejaba el archivo de salida **sin decision** cuando el
   corte tenia tres ventanas individualmente validas del mismo simbolo
   separadas por huecos.
2. El extractor de cobertura calculaba motivos de exclusion que luego se
   perdian, tomaba prestado `as_of_ms` de la otra fuente cuando faltaba uno,
   contaba simbolos sin ternas y no distinguia procedencia del precio.

La cobertura acreditada **no** equivale a patron detectado ni a rentabilidad.

---

## 1. Detector: caso sin terna

### Defecto reproducido con el CLI real

Tres ventanas validas de `GAPUSDT` (`decision_ms` separadas por 180 s, mismo
simbolo, misma `ventana_ms`) sobre el CLI **publicado** (`git show
619d357:scripts/secuencia_presion_v1.py`):

```
EXIT CODE: 0
{"estado": "ok", "symboles_procesados": 0, ..., "datos_insuficientes": 0, "nuevas": 0, ...}
ARCHIVO DE SALIDA: 0 bytes, 0 lineas
```

El archivo quedaba vacio: no se podia distinguir "no se ejecuto" de "no se
pudo evaluar".

### Correccion

`detectar_secuencias()` persiste **una** fila `DATOS_INSUFICIENTES` por corte
sin terna contigua con:

- `symbol` y `corte_ms` (ultima ventana examinada),
- `ventanas` examinadas con `ventana_valida` y `motivos_exclusion` por ventana,
- `ventanas_examinadas`,
- `motivo` y `motivo_codigo` (`sin_terna_contigua` o
  `ventanas_validas_insuficientes`),
- `diagnostico` con pares no contiguos clasificados (huecos / solapamientos),
- `instante_deteccion_ms` = maximo de disponibilidad acreditada de lo examinado
  (nunca se inventa si no hay disponibilidad).

Identidad de la fila: `<symbol>|corte:<corte_ms>`. No colisiona con la identidad
de una terna (`observation_id` de su tercera ventana), de modo que un corte
insuficiente no bloquea una terna posterior. Repetir el mismo corte produce la
misma fila: el CLI no añade otra linea ni reescribe las anteriores.

`SIN_PATRON` queda **reservado** a una terna contigua y valida que no cumple las
condiciones del patron. La deteccion deslizante (1-2-3, 2-3-4, ...) y el rechazo
de conflictos de identidad (codigo 3, sin sustitucion silenciosa) se conservan
sin cambios. Las condiciones del patron no se tocaron.

### Pruebas

`tests/test_secuencia_presion_v1.py` — **24 passed**:

- `test_ventanas_no_contiguas_persisten_datos_insuficientes` (antes exigia
  `r is None`, que era el defecto): ahora exige `DATOS_INSUFICIENTES` con
  simbolo, corte, ventanas examinadas, motivo, diagnostico de huecos e
  idempotencia del mismo corte.
- `test_solapamiento_no_forma_terna`: ventanas solapadas 30 s → se nombra el
  solapamiento y no se evalua.
- Recuperadas de la version retirada: `test_ventana_incompleta`,
  `test_dato_invalido_profundidad_no_positiva`,
  `test_precio_sin_confirmacion_direccional`.
- `test_cli_terna_valida_sin_patron_persiste_sin_patron`: la distincion
  `SIN_PATRON` vs `DATOS_INSUFICIENTES` se prueba por CLI real.
- `test_cli_huecos_persiste_datos_insuficientes_y_no_duplica`: repetir el corte
  no añade fila ni cambia un byte; un corte nuevo añade fila **sin alterar** el
  registro previo.

---

## 2. Extractor: acreditar lo que cuenta

`scripts/extraer_cobertura_research_db.py` conserva `--db` y `--salida`, abre
SQLite con `file:...?mode=ro` y no usa red. Añade `--observaciones` (opcional)
para acreditar la poblacion del piloto **por separado**, sin derivarla de
`research.db` ni mezclarla con los agregados de un minuto.

Lo que ahora se exige antes de contar:

| Verificacion | Regla |
| --- | --- |
| Pareja | `(symbol, bucket_start)` en ambas tablas; ambos limites enteros; `bucket_end` de flujo == de libro |
| Procedencia | `price_source` de flujo `aggTrade`, de libro `depth20` |
| Corridas | mismo `run_id` no vacio en ambas fuentes; corridas distintas no se mezclan |
| Claves duplicadas | la clave queda excluida y el conflicto se cuenta; la fila contradictoria no sustituye a la anterior |
| Completitud | intervalo de 60 000 ms, inicio alineado al minuto, `bucket_size_s = 60`, eventos dentro del intervalo en ambas fuentes |
| Integridad por intervalo | flujo `data_quality = OK`; libro `degraded = 0`, `crossed = 0`, `depth_gaps = 0`, `sample_count > 0` |
| Valores validos | `buy_notional`/`sell_notional` finitos y `>= 0`; `bid20_mean`/`ask20_mean` finitos y `> 0` |
| Precio | `price_close` finito y `> 0` |
| Disponibilidad | `as_of_ms` valido en **cada** fuente; si falta uno → `UNKNOWN` (no se toma prestado el de la otra); si ambos estan, se usa el maximo |

Un cero **registrado** por la fuente (`buy_notional = 0`) es admisible; un dato
ausente (`NULL`) no es cero y excluye la ventana.

El JSON devuelve, para cada requisito, entrada / excluidas / supervivientes,
**motivos solapables** con conteo y ejemplos con contrato e intervalo,
exclusiones **unicas**, parejas iniciales, sin contraparte y ternas que
sobreviven a cada etapa. `simbolos_con_ternas` cuenta solo simbolos con al menos
una terna acreditada.

`price_close` se identifica como **cierre del agregado de operaciones
(`aggTrade`)**, no como `libro_mid` ni como precio ejecutable; y
`disponibilidad_ms` se identifica como el maximo de `as_of_ms` de ambas fuentes,
no como cierre nominal (`bucket_end`) ni como instante efectivo de deteccion.

---

## 3. Evidencias

### (A) CLI real: caso sin terna

Archivo: `A-cli-caso-sin-terna.txt`.

| Paso | Comando | Exit | Resultado |
| --- | --- | --- | --- |
| A.1 base `619d357` | `python <base>/secuencia_presion_v1.py --fuente observaciones.jsonl --salida decisiones_base.jsonl` | 0 | 0 bytes, 0 lineas (defecto reproducido) |
| A.2 corregido | `python scripts/secuencia_presion_v1.py --fuente observaciones.jsonl --salida decisiones.jsonl` | 0 | 1 linea `DATOS_INSUFICIENTES` (`sin_terna_contigua`, 2 huecos) |
| A.3 repeticion | mismo comando que A.2 | 0 | `nuevas=0`, `duplicadas_omitidas=1`, SHA256 identico |

SHA256 del archivo de decisiones: `95679060090dfa610cfae179d665aae95708024f885cf2c7970b54711c860619`
(mismo valor tras A.2 y A.3: no se añadio fila ni se altero el registro previo).

### (B) Extractor contra SQLite temporal

Archivo: `B-pytest-extractor.txt`.

```
python -m pytest tests/test_extraer_cobertura_research_db.py -v
EXIT CODE: 0
7 passed
```

La prueba construye la SQLite dentro de `tmp_path` y fija expectativas
calculadas a mano: 29 parejas iniciales → 27 acreditadas → 23 ventanas → 2
ternas en 2 simbolos, con 4 exclusiones unicas y motivos solapables. Incluye
hueco, falta de contraparte, ventana parcial (90 s), precio ausente, un lado con
cero registrado, `as_of_ms` ausente en flujo y en libro por separado, clave
duplicada contradictoria, corrida distinta y simbolo sin ternas. Si el extractor
tomara prestado el `as_of_ms` de la otra fuente, habria 3 ternas en vez de 2 y
la prueba fallaria. Tambien falla si cuenta como `simbolos_con_ternas` un
simbolo con ventanas pero sin terna.

Regresiones directas en el mismo archivo: `test_secuencia_presion_v1.py` +
`test_analisis_contrafactual_ventana4.py` + `test_operativo_replay_offline.py`
→ exit 0.

### (C) Cobertura real regenerada

Archivos: `C-cobertura-real.json` (salida exacta del CLI) y
`C-comando-y-hashes.txt`.

```
python scripts/extraer_cobertura_research_db.py \
  --db C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a\research.db \
  --salida docs/evidence/secuencia-presion-v1-correcciones-20261117/C-cobertura-real.json \
  --observaciones C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a\observaciones.jsonl
EXIT CODE: 0
```

Hashes de los originales, antes y despues (identicos):

| Archivo | SHA256 |
| --- | --- |
| `research.db` | `6ad6f716889a71ceffc5ffc36ed89d904544d3a75facfe1da7c4385b9ad6a7f1` |
| `research.db-shm` | `fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb` |
| `research.db-wal` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

JSON regenerado: `39652bf00d594245943ec7114c0e6933fce2e49a8caf2812915cc478f9eaf4bd`
(1 147 573 bytes).

---

## 4. Cobertura: publicada vs regenerada

| Etapa | Publicada (2026-11-16) | Regenerada (2026-11-17) |
| --- | --- | --- |
| Parejas iniciales | — | 1190 |
| Ternas sobre ventanas de flujo (referencia) | 1107 | 1107 |
| Ternas sobre parejas | 1032 | 1032 |
| Ternas tras integridad por intervalo | 501 | 501 |
| Ternas tras precio | 501 | 501 |
| Ternas tras disponibilidad | — | 501 |
| **Ternas evaluables al cierre** | **0 declaradas** | **501** |
| Ventanas acreditadas | 0 declaradas | 1005 |
| Simbolos con ternas | 0 declarados | 43 |

La cadena `1107 → 1032 → 501 → 501` se reproduce exactamente. El **0 final
publicado era incorrecto**: no habia ningun requisito posterior a precio que
eliminara las 501; la afirmacion de "0 ternas evaluables" contradecia su propia
cadena. La regeneracion lo demuestra con los mismos datos.

El requisito que limita al resto: **integridad por intervalo**. Excluye 185
ventanas de las 1190 parejas:

- 183 ventanas con `libro_degradado` y `libro_huecos_profundidad` (los mismos
  183 intervalos, dos motivos solapables cada uno),
- 2 ventanas con `flujo_data_quality_no_ok` (`PARTIAL_OK`).

Completitud, valores validos, precio y disponibilidad excluyen **0** ventanas
en esta captura. Las 75 claves de flujo sin contraparte y las 7 de libro sin
contraparte no llegan a pareja; los 29 intervalos con un lado en cero
registrado son admisibles y no se excluyen.

Poblacion A (observaciones del piloto), acreditada por separado desde
`observaciones.jsonl`: 196 totales, 161 aptas, 35 descartadas, 34 simbolos
(motivos solapables de descarte: `dato_obsoleto_flujo` 28,
`flujo_ventana_incompleta` 13, `dato_obsoleto_libro` 1). No es la misma
poblacion que los agregados de un minuto y no se suma con ellos.

---

## 5. Respuesta verificable del bloque

**¿Cuantas ternas podemos evaluar con los datos que ya tenemos y que requisito
limita al resto?**

**501 ternas** sobre 1005 ventanas acreditadas y 43 simbolos, con
`price_close` = cierre del agregado `aggTrade` y disponibilidad = maximo de
`as_of_ms` de flujo y libro (ambos acreditados). El requisito que limita al
resto es la **integridad por intervalo**: 185 ventanas y 531 de las 1032 ternas
sobre parejas caen por `libro_degradado`/`libro_huecos_profundidad` (183) y
`flujo_data_quality_no_ok` (2). Despues de integridad no cae ninguna terna mas
por completitud, valores, precio ni disponibilidad.

Que una terna sea evaluable **no** significa que el patron se detecte ni que la
hipotesis sea rentable. Este bloque no ejecuta el detector sobre las ternas
reales ni calcula retornos.

---

## 6. Lo que este bloque NO acredita

- Ninguna deteccion de patron sobre las 501 ternas reales ni rentabilidad.
- Ninguna mejora predictiva del flujo/profundidad.
- Cobertura para futuros con vencimiento: el selector y estas tablas siguen
  siendo PERPETUAL/TRADING/USDT.
- Nada sobre una captura nueva: no se ejecuto ni se propone otra captura en
  este bloque. Cualquier ventana nueva requiere autorizacion humana explicita
  con `run_id` nuevo.

## 7. Artefactos

| Artefacto | Ruta |
| --- | --- |
| Detector | `scripts/secuencia_presion_v1.py` |
| Pruebas detector | `tests/test_secuencia_presion_v1.py` (24 passed) |
| Extractor | `scripts/extraer_cobertura_research_db.py` |
| Pruebas extractor | `tests/test_extraer_cobertura_research_db.py` (7 passed) |
| Evidencia A | `docs/evidence/secuencia-presion-v1-correcciones-20261117/A-cli-caso-sin-terna.txt` |
| Evidencia B | `docs/evidence/secuencia-presion-v1-correcciones-20261117/B-pytest-extractor.txt` |
| Evidencia C | `docs/evidence/secuencia-presion-v1-correcciones-20261117/C-cobertura-real.json` |
| Evidencia C (comandos y hashes) | `docs/evidence/secuencia-presion-v1-correcciones-20261117/C-comando-y-hashes.txt` |
