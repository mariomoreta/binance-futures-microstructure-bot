"""Aceptacion: primer corte automatico con recepcion cronologica real.

CLI real como subproceso, proveedores HTTP/WS loopback, SQLite temporal y reloj
manual. Sin ``--decision-gate-file``, sin llamadas directas a
``take_decisions`` y sin asignaciones directas a los motores: el corte lo decide
el bucle automatico del piloto.

Invariante de esta aceptacion: cada evento se publica con
``event_ms <= reloj`` en el momento de publicarlo. No hay fechas futuras ni
historia precargada: la ventana de 60 s se construye recibiendo eventos durante
ese minuto, empezando por una primera recepcion posterior a la suscripcion.
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


def _resumen_publicaciones(run):
    """Agregado compacto y verificable de la cronologia de publicaciones."""
    por_reloj = {}
    for pub in run.published:
        por_reloj[pub["clock_ms"]] = por_reloj.get(pub["clock_ms"], 0) + 1
    futuros = [p for p in run.published if p["event_ms"] > p["clock_ms"]]
    return {
        "total_eventos": len(run.published),
        "eventos_por_reloj": {str(k): v for k, v in sorted(por_reloj.items())},
        "primer_evento": run.published[0] if run.published else None,
        "ultimo_evento": run.published[-1] if run.published else None,
        "eventos_con_fecha_futura": len(futuros),
        "paso_ms": PASO_MS,
        "primera_recepcion_ms": T0 + PRIMERA_RECEPCION_MS,
        "ventana_observada_ms": VENTANA_OBSERVADA_MS - PRIMERA_RECEPCION_MS,
    }


def _escribir_traza(traza):
    destino = os.environ.get("PILOT_EVIDENCE_PATH")
    if not destino:
        return None
    path = Path(destino)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(traza, ensure_ascii=False, indent=2,
                               sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def test_aceptacion_primer_corte_automatico_cronologico():
    """Seleccion en T0; primera recepcion en T0+1 s; corte con cobertura real.

    A T0+60 s la ventana observada es 55 s: el piloto no la admite como
    completa ni consume la oportunidad. Al completarse la ventana (60 s reales
    entre primera y ultima recepcion) evalua automaticamente, antes de la
    siguiente seleccion en T0+300 s.
    """
    tmp = Path(tempfile.mkdtemp(prefix="aceptacion-corte-"))
    run = ProductRun(
        tmp, universe=UNIVERSE, duration_s=900, settle_s=60,
        selection_s=300, cycle_s=300, decision_delay_s=0,
        max_symbols=20, max_candidates=12, max_comparators=8,
        run_id="aceptacion-corte-automatico")
    try:
        # 1. Seleccion y suscripcion en T0, sin datos previos.
        state0 = seleccion_inicial(run)
        seguido = state0.get("followed") or []
        assert 12 <= len(seguido) <= 20, seguido
        assert {"candidate", "comparator"} <= set(
            (state0.get("roles") or {}).values())
        assert state0.get("symbol_first_flow_ms") == {}, state0
        assert state0.get("symbol_first_book_ms") == {}, state0
        assert set(state0.get("symbol_first_seen_ms") or {}) == set(seguido)
        assert any("--decision-gate-file" in str(arg) for arg in run.cmd) is False

        # 2. Recepcion cronologica: primera en T0+1000, no en T0.
        publicar_cronologico(run, seguido, hasta_ms=60_000)
        run.advance(T0 + 60_000)

        # 3. A T0+60000 la ventana observada (55 s) no es completa.
        estado_60 = run.status() or {}
        assert not observaciones_desde(run, T0 + 60_000), (
            "evaluo sin cobertura observada real")
        assert estado_60.get("evaluations_run") == 0, estado_60
        assert estado_60.get("last_nominal_cut_ms") == T0 + 60_000, estado_60
        assert estado_60.get("warmup_deferrals", 0) >= 1, estado_60
        assert estado_60.get("warmup_pending"), estado_60
        assert (estado_60.get("next_decision_ms") or 0) > T0 + 60_000, estado_60
        assert not estado_60.get("symbols_evaluated_this_cycle"), estado_60

        # 4. Completar la ventana observada y dejar que el corte automatico
        #    decida; no se exige un instante exacto, solo cobertura y cota.
        publicar_cronologico(run, seguido, desde_ms=VENTANA_OBSERVADA_MS,
                             hasta_ms=VENTANA_OBSERVADA_MS)
        run.advance(T0 + 62_000)
        obs = run.wait_first_cut(T0 + 60_000, len(seguido), T0 + 300_000)

        by_sym = {o["symbol"]: o for o in obs}
        assert set(by_sym) == set(seguido), (set(by_sym) ^ set(seguido))
        decisiones = {o["decision_ms"] for o in obs}
        assert len(decisiones) == 1, decisiones
        decision = decisiones.pop()
        assert T0 + 60_000 < decision < T0 + 300_000, decision

        # 5. Cobertura real, frescura y una sola observacion por simbolo.
        for o in obs:
            assert o["estado"] == "observada", o
            assert o["apto_para_evaluacion"] is True, o
            assert o["motivos"] == [], o
            cobertura = o["cobertura"]
            assert cobertura["libro_presente"] is True, o
            assert cobertura["flujo_presente"] is True, o
            assert cobertura["flujo_ventana_completa"] is True, o
            disp = o["disponibilidad"]
            for clave in ("seleccion_ms", "libro_ms", "flujo_ms"):
                assert disp[clave] <= o["decision_ms"], o
            assert "evento_de_libro_posterior_al_reloj" not in o["motivos"], o
            assert "evento_de_flujo_posterior_al_reloj" not in o["motivos"], o

        conteo = {}
        for r in read_rows(run.obs_path):
            if r.get("kind") == "observacion":
                key = (r["symbol"], r["decision_ms"])
                conteo[key] = conteo.get(key, 0) + 1
        assert all(c == 1 for c in conteo.values()), conteo
        assert {o["role"] for o in obs} == {"candidate", "comparator"}

        estado = run.status() or {}
        assert estado.get("last_cut_ms") == decision, estado
        assert estado.get("last_cut_reason") == "cobertura_completa", estado
        assert estado.get("last_cut_deadline_ms") is not None, estado
        assert estado.get("warmup_deferrals", 0) >= 1, estado

        # 6. Ningun evento de esta aceptacion se publico con fecha futura y la
        #    ventana observada cubre los 60 s requeridos.
        assert run.published, "no se registro ninguna publicacion"
        assert all(p["event_ms"] <= p["clock_ms"] for p in run.published)
        primera = min(estado["symbol_first_flow_ms"].values())
        ultima = max((o["disponibilidad"]["flujo_ms"] for o in obs))
        assert ultima - primera >= 60_000, (primera, ultima)
        assert primera >= T0 + PRIMERA_RECEPCION_MS, primera

        # 7. Traza compacta de la aceptacion.
        traza = {
            "aceptacion": "primer-corte-automatico-cronologico",
            "run_id": "aceptacion-corte-automatico",
            "inicio_seguimiento_ms": T0,
            "suscripcion": {
                "simbolos": seguido,
                "first_seen_ms": state0["symbol_first_seen_ms"],
                "cycles_run": state0.get("cycles_run"),
                "feeds_conectados": {
                    nombre: feed.get("connected_now")
                    for nombre, feed in (state0.get("feeds") or {}).items()},
            },
            "primera_recepcion": {
                "libro_ms": estado.get("symbol_first_book_ms"),
                "flujo_ms": estado.get("symbol_first_flow_ms"),
            },
            "publicaciones": _resumen_publicaciones(run),
            "corte": {
                "nominal_ms": estado.get("last_nominal_cut_ms"),
                "espera_maxima_ms": estado.get("last_cut_deadline_ms"),
                "efectivo_ms": decision,
                "reprogramaciones": estado.get("warmup_deferrals"),
                "motivo": estado.get("last_cut_reason"),
            },
            "cobertura": {
                o["symbol"]: o["cobertura"] for o in obs},
            "decisiones": [
                {
                    "symbol": o["symbol"],
                    "role": o["role"],
                    "decision_ms": o["decision_ms"],
                    "estado": o["estado"],
                    "apto_para_evaluacion": o["apto_para_evaluacion"],
                    "motivos": o["motivos"],
                    "disponibilidad": o["disponibilidad"],
                    "cobertura": o["cobertura"],
                }
                for o in obs
            ],
            "eventos_con_fecha_futura": 0,
        }
        destino = _escribir_traza(traza)
        print(f"ACEPTACION OK: corte nominal {estado.get('last_nominal_cut_ms')} "
              f"-> evaluacion efectiva {decision} "
              f"({len(obs)} simbolos, ventana observada "
              f"{ultima - primera} ms, traza={destino})")

        # 8. Cierre limpio y verificable.
        rc = run.stop()
        assert rc == 0, (rc, run.proc.stdout)
        final = json.loads(run.out_dir.joinpath("resumen.json").read_text(
            encoding="utf-8"))
        assert final.get("run_id") == "aceptacion-corte-automatico"
    finally:
        run.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
