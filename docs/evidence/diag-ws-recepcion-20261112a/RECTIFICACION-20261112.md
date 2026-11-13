# RECTIFICACIÓN del veredicto temporal — `diag-ws-recepcion-20261112a`

**Fecha:** 2026-11-12 · **Naturaleza:** aclaración documental del veredicto de
una ejecución ya cerrada. **No se repite el diagnóstico, no se abre ningún
socket y no se abre la URL antigua.**

Esta rectificación **no toca** los artefactos originales ni sus hashes:
`diagnostico.json`, `launcher.json`, `stdout.log`, `stderr.log` y
`exit_code.txt` se conservan byte a byte, **incluido el `PASS` que emitió el
script** en `stdout.log` (`"veredicto": "PASS"`). Ese `PASS` se conserva como
** antecedente**: es lo que el script calculó según sus propios criterios, no
una certificación de cumplimiento del plazo global.

---

## 1. Qué se retira de las conclusiones vigentes

El informe de cierre de esta corrida y el bloque de estado vigente afirmaban
**cumplimiento global sin reservas** (entre otras cosas, «Límites respetados»
y una fila de criterio marcada como *Cumplido con exceso declarado* para el
plazo de 60 s). **Esa afirmación se retira.**

Motivo: el plazo global de 60 s **no se cumple**, y la configuración de 60 s
**no es una medición independiente** de la duración efectiva de observación.

## 2. Veredicto rectificado, punto por punto

| Elemento | Veredicto rectificado | Evidencia |
|---|---|---|
| **Recepción y procesamiento** | **PASS** | trades `/market`: 773 eventos de flujo válidos y **773 procesados por `FlowEngine`**; libro `/public`: 552 eventos de libro válidos y **552 procesados por `BookEngine`** |
| **Mensajes** | Dentro de límites observados | 1 325 frames de datos de 200 000 (`limite_mensajes_alcanzado: false`) |
| **Almacenamiento** | Dentro de límites observados | 2 360 B de 1 048 576 B (3.41 KB el directorio completo) |
| **Conexiones** | Dentro de límites observados | 2 conexiones simultáneas (1 por feed), 2 aperturas iniciales, 0 reconexiones |
| **Errores** | Dentro de límites observados | 0 errores, `last_error: null` en ambos feeds, `stderr.log` vacío |
| **Código de salida** | **0 acreditado** | `exit_code.txt` = 0 y `launcher.json.returncode` = 0, leídos de `Popen.wait()` |
| **Plazo global de 60 s** | **NO CUMPLE** | diagnóstico **65.034 s**; lanzador **65.557 s** |
| **Economía** | **NO EVALUADA** | sin señales, decisiones, operaciones, órdenes ni cuentas |
| **Causa raíz histórica** | **UNKNOWN** | no se abrió la URL antigua contra el venue; no se demuestra ni se atribuye el fallo a Binance |
| **Exit code histórico** (`exp-v2-ventana-1-20261112a`) | **UNKNOWN** | su `exit_code.txt` continúa con 0 bytes, sin rellenar |

## 3. Precisiones obligatorias sobre el plazo

1. **El plazo global de 60 s no se cumple.** El proceso duró 65.034 s
   (diagnóstico) y 65.557 s (lanzador). La diferencia se declara, no se
   maquilla ni se convierte retroactivamente en cumplimiento.
2. **La configuración de 60 s no constituye una medición independiente de la
   duración efectiva de observación.** `--duracion-seconds 60` es un parámetro
   de configuración; no es un cronómetro independiente que acredite cuánto
   duró la observación. Los dos únicos valores medidos son los que constan en
   `diagnostico.json` (`resultado.duracion_s` = 65.034 s) y `launcher.json`
   (`duracion_s` = 65.557 s), y ambos superan el plazo.
3. **El cierre de sockets es compatible con el exceso, pero no lo convierte en
   cumplimiento.** Es compatible (y plausible) que el exceso corresponda al
   cierre de las conexiones (`StreamFeed` abre con `close_timeout=5`), pero esa
   es una **explicación compatible**, no una medición: el artefacto no separa
   el tiempo de observación del tiempo de cierre. Por tanto el plazo global de
   60 s queda **NO CUMPLE**, y no se sustituye por un plazo distinto que el
   script no midió.
4. **Sin reintento ni relanzamiento.** La ejecución fue única; el exceso no se
   corrigió repitiendo la consulta.

## 4. Lo que la rectificación NO cambia

- La recepción y el procesamiento **quedan acreditados** (773 y 552 eventos
  válidos y procesados, con 0 frames de control: un ACK no acreditó flujo).
- El bloqueo material de datos que vació el embudo de
  `exp-v2-ventana-1-20261112a` **sigue resuelto para el transporte**: con la
  ruta por categoría vigente hay flujo real.
- La **causa raíz histórica** sigue **UNKNOWN** y el **exit code histórico**
  sigue **UNKNOWN**.
- El **resultado económico no se evalúa**: 60 s de un símbolo no acreditan
  cobertura de universo, ciclos, horizontes, estabilidad prolongada ni
  capacidad de operar.
- Este diagnóstico **no habilita** ninguna ventana operativa.

## 5. Reproducibilidad

Los artefactos publicados (`diagnostico.json`, `launcher.json`, `stdout.log`,
`stderr.log`, `exit_code.txt`) y sus hashes siguen siendo los de
`hashes.json`, sin cambios. La presente rectificación es un documento
adicional del mismo directorio de evidencia y no altera ninguna de esas
huellas.
