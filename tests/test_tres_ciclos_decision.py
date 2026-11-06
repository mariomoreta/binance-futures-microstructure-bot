"""Aceptacion: tres ciclos de decision consecutivos con conjunto estable.

CLI real como subproceso, proveedores HTTP/WS loopback, SQLite temporal y
reloj manual. Sin --decision-gate-file, sin llamadas directas a
take_decisions y sin asignacion manual de self.followed ni de datos a engines.

selection_seconds=300, cycle_seconds=300, ventana de flujo 60 s,
max_data_age_ms=5000. El conjunto de seleccion se mantiene estable durante al
menos tres ciclos; las fuentes se publican cronologicamente (event_ms <= reloj)
y se mantienen frescas. No hay eventos futuros ni historia precargada.

Comprueba:
A. Primer corte valido tras cobertura real.
B. Segundo y tercer ciclo evalúan tambien a los mismos simbolos.
C. Cada ciclo produce exactamente N observaciones, una por simbolo.
D. Total: 3 x N observaciones.
E. Reintentos dentro de un ciclo no generan duplicados.
F. No aparece una observacion adicional solo por ejecutar otra seleccion.
G. observation_id vincula simbolo + decision_ms (identidad de ciclo).
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from tests.test_recorrido_productivo import (
    PASO_MS,
    PRIMERA_RECEPCION_MS,
    VENTANA_OBSERVADA_MS,
    ProductRun,
    UNIVERSE,
    observaciones_desde,
    publicar_cronologico,
    read_rows,
    seleccion_inicial,
)
from tests.test_research_pilot import T0

CYCLE_MS = 300_000
N_CICLOS = 3
# Margen de coherencia entre cortes consecutivos respecto a cycle_seconds.
MARGEN_CICLO_MS = 60_000


def _agrupar_por_ciclo(rows):
    ciclos = {}
    for r in rows:
        if r.get("kind") != "observacion":
            continue
        ciclos.setdefault(int(r["decision_ms"]), []).append(r)
    return dict(sorted(ciclos.items()))


def test_tres_ciclos_decision_conjunto_estable():
    tmp = Path(tempfile.mkdtemp(prefix="tres-ciclos-"))
    run = ProductRun(
        tmp, universe=UNIVERSE, duration_s=900, settle_s=60,
        selection_s=300, cycle_s=300, decision_delay_s=0,
        max_symbols=20, max_candidates=12, max_comparators=8,
        run_id="tres-ciclos-decision")
    try:
        # 1. Seleccion en T0: conjunto estable (sin rotacion).
        state = seleccion_inicial(run)
        seguido = state.get("followed") or []
        n = len(seguido)
        assert 12 <= n <= 20, seguido
        roles = set((state.get("roles") or {}).values())
        assert {"candidate", "comparator"} <= roles, roles
        assert set(state.get("symbol_first_seen_ms") or {}) == set(seguido)

        seleccion_ms = state.get("symbol_first_seen_ms")
        print(f"Seleccion T0={T0}: {n} simbolos, "
              f"roles={sorted(roles)}")

        # A. Recepcion cronologica: primera en T0+1000, ventana completa en
        #    T0+61000. Corte despues del calentamiento real.
        publicar_cronologico(run, seguido)
        run.advance(T0 + 62_000)
        ciclos = _agrupar_por_ciclo(read_rows(run.obs_path))
        d1 = next(iter(ciclos))
        obs1 = ciclos[d1]
        assert T0 + 60_000 < d1 < T0 + 300_000, d1
        assert len(obs1) == n, obs1
        by_sym = {o["symbol"]: o for o in obs1}
        assert set(by_sym) == set(seguido)
        for o in obs1:
            assert o["estado"] == "observada", o
            assert o["apto_para_evaluacion"] is True, o
            assert o["motivos"] == [], o
            assert o["observation_id"] == f"{o['symbol']}|{o['decision_ms']}", o
        print(f"Ciclo 1: decision_ms={d1}, {len(obs1)} observaciones aptas")

        # Mantener ambas fuentes frescas cronologicamente hasta el tercer
        # ciclo de decision (d1 + 2 * cycle_seconds), dentro de la captura.
        hasta = d1 + (N_CICLOS - 1) * CYCLE_MS + PASO_MS + 10_000
        publicar_cronologico(
            run, seguido, desde_ms=VENTANA_OBSERVADA_MS,
            hasta_ms=hasta - T0, paso_ms=PASO_MS, base_ms=T0)
        run.advance(hasta + 10_000)

        # B, C, D: exactamente tres ciclos, cada uno con N observaciones de
        # los mismos simbolos, todos aptos.
        ciclos = _agrupar_por_ciclo(read_rows(run.obs_path))
        decision_ms = sorted(ciclos)
        assert len(decision_ms) == N_CICLOS, decision_ms

        evaluaciones_por_ciclo = {}
        seen_ids = set()
        for i, d in enumerate(decision_ms, start=1):
            obs = ciclos[d]
            assert len(obs) == n, f"ciclo {i} en {d}: {len(obs)} != {n}"
            by_sym = {o["symbol"]: o for o in obs}
            assert set(by_sym) == set(seguido), (
                f"ciclo {i}: simbolos distintos {set(by_sym) ^ set(seguido)}")
            for o in obs:
                assert o["estado"] == "observada", o
                assert o["apto_para_evaluacion"] is True, o
                assert o["motivos"] == [], o
                # G: identidad ciclo/simbolo/decision_ms vinculada.
                assert o["observation_id"] == f"{o['symbol']}|{d}", o
                key = (o["symbol"], d)
                assert key not in seen_ids, f"duplicado {key}"
                seen_ids.add(key)
                # A/C: disponibilidad coherente con el reloj de publicacion.
                disp = o["disponibilidad"]
                assert disp["seleccion_ms"] <= o["decision_ms"], o
                assert disp["libro_ms"] <= o["decision_ms"], o
                assert disp["flujo_ms"] <= o["decision_ms"], o
            evaluaciones_por_ciclo[i] = len(obs)
            print(f"Ciclo {i}: decision_ms={d}, {len(obs)} observaciones aptas")

        # Coherencia de intervalos con cycle_seconds.
        for i in range(1, N_CICLOS):
            diff = decision_ms[i] - decision_ms[i - 1]
            assert abs(diff - CYCLE_MS) <= MARGEN_CICLO_MS, (
                decision_ms[i - 1], decision_ms[i], diff)

        # D: total 3 x N.
        total = sum(evaluaciones_por_ciclo.values())
        assert total == N_CICLOS * n, total
        assert len(seen_ids) == total, seen_ids

        # E: no hay duplicados dentro ni entre ciclos (una por simbolo y ciclo).
        assert len(seen_ids) == len(
            {o["observation_id"] for o in observaciones_desde(run, T0)})

        # F: ninguna observacion adicional solo por ejecutar otra seleccion
        # (selecciones en T0+300000 y T0+600000 no son cortes de decision).
        seleccion_instantes = {T0 + CYCLE_MS, T0 + 2 * CYCLE_MS}
        por_seleccion = [o for o in observaciones_desde(run, T0)
                         if o["decision_ms"] in seleccion_instantes]
        assert not por_seleccion, por_seleccion

        estado = run.status() or {}
        assert estado.get("evaluations_run") == N_CICLOS, estado
        assert estado.get("last_cut_ms") == decision_ms[-1], estado

        # Traza compacta de aceptacion.
        traza = {
            "aceptacion": "tres-ciclos-decision-conjunto-estable",
            "run_id": "tres-ciclos-decision",
            "seleccion_t0_ms": T0,
            "simbolos": n,
            "roles": sorted(roles),
            "first_seen_ms": seleccion_ms,
            "ciclos": [
                {
                    "ciclo": i,
                    "decision_ms": d,
                    "observaciones": len(ciclos[d]),
                    "simbolos": sorted({o["symbol"] for o in ciclos[d]}),
                    "todos_aptos": all(o["apto_para_evaluacion"]
                                       for o in ciclos[d]),
                }
                for i, d in enumerate(decision_ms, start=1)
            ],
            "intervalos_ciclo_ms": [
                decision_ms[i] - decision_ms[i - 1]
                for i in range(1, N_CICLOS)
            ],
            "total_observaciones": total,
            "duplicados": 0,
            "eventos_con_fecha_futura": 0,
            "evaluations_run": estado.get("evaluations_run"),
            "codigo_salida": None,  # se rellena tras stop()
        }
        destino = os.environ.get("PILOT_EVIDENCE_PATH")
        if destino:
            path = Path(destino)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(traza, ensure_ascii=False, indent=2,
                           sort_keys=True) + "\n", encoding="utf-8")
            traza["ruta_evidencia"] = str(path)

        print(f"ACEPTACION TRES CICLOS OK: {total} observaciones "
              f"({n} x {N_CICLOS}), cortes={decision_ms}, "
              f"intervalos={traza['intervalos_ciclo_ms']}")

        # Limpieza y codigo de salida verificables.
        rc = run.stop()
        traza["codigo_salida"] = rc
        assert rc == 0, (rc, run.proc.stdout)
        resumen_path = run.out_dir / "resumen.json"
        if resumen_path.exists():
            resumen = json.loads(resumen_path.read_text(encoding="utf-8"))
            assert resumen.get("run_id") == "tres-ciclos-decision"
    finally:
        run.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
