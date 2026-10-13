# Ciclo de uso — corridas de observacion con Dashboard V2 principal

Status: CONTRACT (research/prep). Nada aqui inicia corridas reales,
habilita Start, autoriza supervision ni avanza gates. Implementado,
probado y comprobado-en-corrida-real son estados DISTINTOS (ver §5).

## 1. V2 como interfaz principal; dashboard Python como legado

- **Principal**: Dashboard V2, checkpoint `27b7af5`
  (`dash-v2-03-token-detail`, rama a continuar; no modificarla desde
  aqui). Todas las funciones de la matriz
  (`docs/OBSERVATION_RUN_MATRIX.md`) se consumen por sus rutas BFF.
- **Legado**: dashboard Python SSR (`dashboard.py`, `/overview`,
  `/movers`, `/symbol/:symbol`, `/system`). Sigue funcional para
  lectura local, pero NO es la interfaz de referencia: ante cualquier
  discrepancia con V2, manda el contrato versionado, no la pantalla
  antigua. No se mantienen dos semanticas: ambos leen los mismos
  stores y comparten vocabulario (LIVE/WARMING/DISCOVERY ONLY/STALE/
  DEGRADED/UNKNOWN); el legado no recibe funciones nuevas.
- F-KRONOS-01 (agentes IA + Kronos) NO forma parte del ciclo: diferido,
  sin dependencias, nunca requisito de arranque.

## 2. Ciclo de uso (unico orden admitido)

1. **Iniciar la interfaz**: `cd frontend && npm run dev`
   (o `npm run build` + `npm start` para la compilacion revisada).
   Solo levanta la UI; no toca el bot, no abre streams, no escribe DBs.
2. **Comprobar requisitos**: abrir `/system` + `/api/v1/runtime/readiness`
   (DASH-V2-45/46/47): evidencia del controlador, lease/heartbeat,
   esquemas soportados. Sin requisitos en verde, no hay arranque.
3. **Arrancar una corrida de observacion AUTORIZADA**: solo mediante la
   transaccion supervisada (`launch_supervised_transaction`) tras
   autorizacion explicita + revision del SHA exacto. Hoy esta DISABLED:
   rechaza con cero efectos (probado en `test_supervised_launch.py` y
   `tests/test_observation_cycle.py`). No existe otro camino admitido.
4. **Confirmar proceso, identidad, heartbeat y frescura**: `status`
   (PID verificado + create_time), `supervise` (lease/heartbeat),
   freshness watchdog (aceptacion por presupuesto, jamas por defecto).
5. **Detener y registrar**: `control stop` (solo PID verificado) +
   resultado en registry/manifiesto con run_id y versiones. `stop` sin
   corrida es inocuo (`no-active-probe`).

**Abrir el dashboard NO es arrancar el bot** (probado:
`status_readonly` repetido no crea registry, procesos ni DBs).
**Start no se habilita omitiendo requisitos del supervisor.**
Primero procesos y bases aislados (`MICROPROBE_RUNTIME_FILE` temporal,
DBs temporales); ninguna corrida real durante la implementacion.

## 3. Comandos exactos

```text
cd frontend && npm run dev        # UI V2 (principal), solo lectura
cd frontend && npm run build      # compilacion revisada
cd frontend && npm start          # UI compilada (principal)
python -m microstructure_probe.control status        # estado read-only
MICROPROBE_RUNTIME_FILE=<tmp> python -m ...         # ciclo aislado (tests)
python scripts/storage_preflight.py --root .        # preflight medido
python scripts/run_family_evaluation.py --demo      # evaluacion mecanica
```

Legado (lectura local, no primario):
`python -m microstructure_probe.dashboard start|status|stop`,
`python -m microstructure_probe.control start|stop` (observe-only).

## 4. Preflight de almacenamiento (antes de cada corrida)

`python scripts/storage_preflight.py --root . [--compare previo.json]`
mide (jamas estima): rutas/tamanos/conteos de `microprobe.db` e
`historical.db`, arbol `logs/` (sin tope de rotacion en codigo:
crecimiento no acotado, podar manual), caps de retencion del codigo,
espacio libre, y crecimiento medido entre snapshots. Contrato:
`docs/STORAGE_PREFLIGHT_CONTRACT.md`. V2 muestra `warnings[]`
(pendiente de cableado UI en la linea V2 con este contrato).

## 5. Lista de aceptacion (estados distintos)

- **IMPLEMENTADO**: codigo + tests dirigidos verdes en rama de revision.
- **PROBADO**: barrera + suite pertinente verdes (o fallos ajenos
  contrastados en base), evidencia publicada.
- **COMPROBADO EN CORRIDA REAL**: solo tras autorizacion explicita +
  ciclo §2 completo con resultado registrado. NO ALCANZADO aqui.

Permite una corrida: requisitos §2 en verde + preflight sin bloqueos
del supervisor + autorizacion + SHA revisado. Bloquea: requisitos en
rojo, Start DISABLED sin habilitacion, schemas no declarados (gates
2/9 del frontend citado), preflight con disco insuficiente, o falta de
autorizacion. Nada de esto es paper, ordenes ni gates.
