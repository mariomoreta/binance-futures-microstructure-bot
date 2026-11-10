"""Aceptacion de los dos defectos materiales del experimento operativo v2.

1. CAPACIDAD: el replay conserva los intervalos historicos de ocupacion.
   - A) dos operaciones con trayectoria completa y exposicion solapada ->
       una admitida y otra rechazada por capacidad;
   - B) una entrada posterior a la salida acreditada -> admitida;
   - C) una posicion sin salida conocida -> conserva la capacidad ocupada;
   - D) repetir observaciones -> decisiones y resultados estables, sin
       duplicados;
   - E) el rol candidate/comparator no altera prioridad ni direccion.

2. PRESUPUESTO: la politica presupuestada se contrasta con las llamadas
   REALES observadas por el proveedor loopback usando el CLI real y un reloj
   controlado. Se avanza por los intervalos que ejercitan la planificacion
   (no se salta al final del horizonte) y se comparan:
   - consultas recibidas por el proveedor,
   - consumo de la puerta de presupuesto (gate),
   - numero previsto por la politica presupuestada.

Sin Binance, sin capturas publicas, sin ordenes reales: todo el mercado es
loopback y el reloj es de prueba.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import tests.test_research_pilot as tr  # noqa: E402
from microstructure_probe.paper_lab_engine import PaperCandle  # noqa: E402
from scripts.research_operativo_adapter import (  # noqa: E402
    OperativoAdapter, OperativoConfig,
)


# ---------------------------------------------------------------------------
# Fixtures de velas 1m sinteticas (mismo criterio que el motor paper)
# ---------------------------------------------------------------------------

def _vela(open_ms: int, o: float, h: float, l: float, c: float,
          close_ms: int) -> PaperCandle:
    return PaperCandle(open_time_ms=open_ms, open=o, high=h, low=l, close=c,
                        close_time_ms=close_ms)


def _velas_stop_long() -> List[PaperCandle]:
    """V1 senal close=102.0, V2 fill open=102.0 con low <= stop 101.49."""
    return [
        _vela(0, 100.0, 101.0, 99.0, 100.0, 59_999),
        _vela(60_000, 101.6, 103.0, 101.55, 102.0, 119_000),
        _vela(120_000, 102.0, 103.0, 101.0, 102.5, 179_000),
        _vela(180_000, 102.0, 103.0, 101.0, 102.5, 239_000),
    ]


def _velas_sin_salida_conocida() -> List[PaperCandle]:
    """Fill en 120000 y datos agotados antes de acreditar la salida.

    El rango nunca toca el stop (101.49): la exposicion queda abierta
    (open_at_end) porque no hay vela que acredite la salida.
    """
    velas = [
        _vela(0, 100.0, 101.0, 99.0, 100.0, 59_999),
        _vela(60_000, 101.6, 103.0, 101.55, 102.0, 119_000),
        _vela(120_000, 102.0, 102.5, 101.6, 102.0, 179_000),
    ]
    for i in range(8):
        o = 180_000 + i * 60_000
        velas.append(_vela(o, 102.0, 102.5, 101.6, 102.0, o + 59_999))
    return velas


def _obs(symbol: str, oid: str, role: str = "candidate",
         decision_ms: int = 119_000, move: float = 2.4) -> Dict[str, Any]:
    return {
        "observation_id": oid, "symbol": symbol, "role": role,
        "decision_ms": decision_ms,
        "seleccion": {"move_24h_pct": move},
        "side": "UP" if move > 0 else ("DOWN" if move < 0 else None),
    }


def _adaptador() -> OperativoAdapter:
    return OperativoAdapter(
        store_path=Path(tempfile.mkdtemp(prefix="capacidad-")) / "op.jsonl",
        cfg=OperativoConfig(),
    )


# ---------------------------------------------------------------------------
# 1. CAPACIDAD
# ---------------------------------------------------------------------------

def test_capacidad_exposiciones_solapadas() -> None:
    """A) Dos trayectorias completas solapadas: una admitida, otra rechazada.

    AAAUSDT entra en 120000 y sale en 180000; BBBBUSDT entra en 120000 y
    sale en 180000. Con max_concurrent=1 compartido, la segunda exposicion
    se solapa con la primera y NO puede admitirse.
    """
    adapter = _adaptador()
    velas = _velas_stop_long()
    tr_a = adapter.procesar_observacion(
        _obs("AAAUSDT", "AAAUSDT|119000"), velas)
    tr_b = adapter.procesar_observacion(
        _obs("BBBUSDT", "BBBUSDT|119000"), velas)
    adapter.close()

    assert tr_a.decision == "ENTRADA_EJECUTADA", tr_a
    assert tr_a.entry_ms == 120_000 and tr_a.exit_ms == 180_000, tr_a
    assert tr_b.decision == "RECHAZADA_CAPACIDAD", tr_b
    assert tr_b.exit_executed is False, tr_b
    assert adapter.estado["rechazadas_capacidad"] == 1, adapter.estado
    assert adapter.estado["operaciones"] == 1, adapter.estado
    # El intervalo historico se conserva: la exposicion existio.
    assert adapter.intervalos_ocupados() == [
        ("AAAUSDT|119000", 120_000, 180_000)], adapter.intervalos_ocupados()
    print("  [capacidad A] admitida=AAAUSDT[120000,180000) "
          "rechazada=BBBUSDT entry=120000")


def test_capacidad_entrada_posterior_a_salida() -> None:
    """B) Una entrada posterior a la salida acreditada se admite."""
    adapter = _adaptador()
    velas = _velas_stop_long()
    tr_a = adapter.procesar_observacion(
        _obs("AAAUSDT", "AAAUSDT|119000"), velas)
    # Entrada en 240000: despues del intervalo [120000, 180000) cerrado.
    velas_post = [
        _vela(0, 100.0, 101.0, 99.0, 100.0, 59_999),
        _vela(60_000, 101.6, 103.0, 101.55, 102.0, 119_000),
        _vela(180_000, 102.0, 103.0, 102.0, 102.5, 239_000),
        _vela(240_000, 102.5, 104.0, 102.0, 103.0, 299_000),
        _vela(300_000, 103.0, 104.0, 102.0, 103.0, 359_000),
    ]
    tr_c = adapter.procesar_observacion(
        _obs("CCCUSDT", "CCCUSDT|239000", decision_ms=239_000), velas_post)
    adapter.close()

    assert tr_a.decision == "ENTRADA_EJECUTADA", tr_a
    assert tr_a.exit_ms == 180_000, tr_a
    assert tr_c.decision == "ENTRADA_EJECUTADA", tr_c
    assert tr_c.entry_ms == 240_000, tr_c
    assert adapter.estado["rechazadas_capacidad"] == 0, adapter.estado
    print("  [capacidad B] entrada posterior 240000 admitida "
          f"(intervalos={adapter.intervalos_ocupados()})")


def test_capacidad_posicion_sin_salida_conocida() -> None:
    """C) Una posicion sin salida conocida conserva la capacidad ocupada."""
    adapter = _adaptador()
    velas = _velas_sin_salida_conocida()
    tr_a = adapter.procesar_observacion(
        _obs("AAAUSDT", "AAAUSDT|119000"), velas)
    # Segunda senal con entrada dentro del intervalo abierto de la primera.
    tr_b = adapter.procesar_observacion(
        _obs("BBBUSDT", "BBBUSDT|119000"), velas)
    adapter.close()

    assert tr_a.decision == "ENTRADA_EJECUTADA", tr_a
    assert tr_a.open_at_end is True, tr_a
    assert tr_a.exit_executed is False, tr_a
    # exit_ms del resultado es la ULTIMA MARCA conocida (no una salida
    # ejecutada): la ocupacion sigue abierta porque no hay salida acreditada.
    assert tr_b.decision == "RECHAZADA_CAPACIDAD", tr_b
    assert adapter.posiciones_abiertas() != {}, adapter.posiciones_abiertas()
    assert adapter.intervalos_ocupados() == [
        ("AAAUSDT|119000", 120_000, None)], adapter.intervalos_ocupados()
    print("  [capacidad C] ocupacion abierta conservada: "
          f"{adapter.intervalos_ocupados()}")


def test_capacidad_repetir_observaciones_es_estable() -> None:
    """D) Repetir una observacion no cambia la decision ni duplica efectos."""
    adapter = _adaptador()
    velas = _velas_stop_long()
    obs_a = _obs("AAAUSDT", "AAAUSDT|119000")
    obs_b = _obs("BBBUSDT", "BBBUSDT|119000")
    primera_a = adapter.procesar_observacion(obs_a, velas)
    primera_b = adapter.procesar_observacion(obs_b, velas)
    estado_1 = dict(adapter.estado)
    intervalos_1 = adapter.intervalos_ocupados()

    segunda_a = adapter.procesar_observacion(obs_a, velas)
    segunda_b = adapter.procesar_observacion(obs_b, velas)
    tercera_a = adapter.procesar_observacion(obs_a, velas)
    adapter.close()

    # Mismas decisiones y mismos resultados.
    assert primera_a.decision == segunda_a.decision == tercera_a.decision
    assert primera_b.decision == segunda_b.decision
    assert (primera_a.entry_ms, primera_a.exit_ms) == (
        segunda_a.entry_ms, segunda_a.exit_ms)
    assert (primera_b.entry_ms, primera_b.exit_ms) == (
        segunda_b.entry_ms, segunda_b.exit_ms)
    # Sin efectos duplicados: contadores e intervalos identicos.
    assert dict(adapter.estado) == estado_1, (estado_1, adapter.estado)
    assert adapter.intervalos_ocupados() == intervalos_1
    # Un rechazo por capacidad no se convierte en admision.
    assert primera_b.decision == "RECHAZADA_CAPACIDAD"
    assert segunda_b.decision == "RECHAZADA_CAPACIDAD"
    print("  [capacidad D] repeticiones estables: "
          f"estado={adapter.estado}")


def test_capacidad_rol_no_altera_prioridad_ni_direccion() -> None:
    """E) El rol candidate/comparator no altera prioridad ni direccion."""
    velas = _velas_stop_long()
    casos = [
        [("AAAUSDT", "candidate"), ("BBBUSDT", "comparator")],
        [("BBBUSDT", "comparator"), ("AAAUSDT", "candidate")],
        [("AAAUSDT", "comparator"), ("BBBUSDT", "candidate")],
        [("BBBUSDT", "candidate"), ("AAAUSDT", "comparator")],
    ]
    for orden in casos:
        adapter = _adaptador()
        observaciones = [_obs(symbol, f"{symbol}|119000", role)
                         for symbol, role in orden]
        velas_por_obs = {o["observation_id"]: velas for o in observaciones}
        resultados = adapter.procesar_observaciones(
            observaciones, velas_por_obs)
        adapter.close()
        por_symbol = {tr.symbol: tr for tr in resultados}
        assert por_symbol["AAAUSDT"].decision == "ENTRADA_EJECUTADA", orden
        assert por_symbol["BBBUSDT"].decision == "RECHAZADA_CAPACIDAD", orden
        assert por_symbol["AAAUSDT"].direction == "LONG", orden
        assert por_symbol["BBBUSDT"].direction == "LONG", orden
    print("  [capacidad E] el rol no altera la admision ni la direccion")


# ---------------------------------------------------------------------------
# 2. PRESUPUESTO: llamadas observadas vs politica presupuestada
# ---------------------------------------------------------------------------

def test_presupuesto_cli_observado_vs_plan() -> None:
    """El CLI real no supera lo presupuestado y el plan coincide con lo observado.

    - Se avanza por los intervalos de planificacion (60 s) hasta el final
      del horizonte: no se salta al final, de modo que las consultas
      intermedias (resultados por horizonte) quedan visibles.
    - La trayectoria NO tiene stop temprano: la operacion se cierra en el
      horizonte, que es cuando la trayectoria puede estar disponible.
    """
    tmp = Path(tempfile.mkdtemp(prefix="presupuesto-cli-"))
    run = tr.PilotRun(
        tmp,
        universe=tr.UNIVERSE,
        duration_s=300,
        settle_s=4200,
        selection_s=300,
        max_symbols=5,
        cycle_s=300,
        horizons=tr.HORIZONS,
        max_http_attempts=2000,
    )
    try:
        run.wait_ready(expected_followed=5)
        e0 = tr.T0 + tr.MINUTE
        seed = list(range(e0 - 62_000, e0 + 1, 1_000))
        run.clock.set(e0 - 1_000)
        run.advance(e0 - 1_000)
        run.ws.publish(e0, depth_symbols=tr.UNIVERSE,
                       trade_events={s: seed for s in tr.UNIVERSE})
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            st = run.status()
            if (st and st.get("book_events")
                    and all(st["book_events"].get(s, 0) >= 1
                            for s in tr.UNIVERSE)
                    and all(st["flow_events"].get(s, 0) >= len(seed)
                            for s in tr.UNIVERSE)):
                break
            time.sleep(0.02)
        else:
            raise AssertionError("no se confirmaron libro/flujo")

        # Corte de decision: la barrera autoriza la evaluacion en e0.
        tmp_gate = run.gate_path.with_name(run.gate_path.name + ".tmp")
        tmp_gate.write_text(json.dumps({"decision_ms": e0, "allow": True}),
                            encoding="utf-8")
        import os
        os.replace(tmp_gate, run.gate_path)
        run.advance(e0)
        rows_obs = tr.read_rows(run.obs_path)
        obs_aptas = [r for r in rows_obs
                     if r.get("kind") == "observacion"
                     and r.get("decision_ms") == e0
                     and r.get("apto_para_evaluacion")]
        assert len(obs_aptas) == 5, obs_aptas

        # La trayectoria operativa puede estar disponible cuando el reloj
        # alcanza decision + horizonte + un paso (60 s).
        listo_ms = e0 + 3_600_000 + 60_000
        trajectory_before = 0
        paso = 60_000
        instante = e0 + paso
        while instante <= listo_ms:
            run.advance(instante)
            if instante < listo_ms:
                # Antes de que la trayectoria pueda estar disponible NO hay
                # consultas de trayectoria (no se sondea en cada tick).
                assert run.http.klines_calls_trajectory == trajectory_before, (
                    instante, run.http.klines_calls_trajectory)
            instante += paso

        # Los resultados operativos se persisten al resolver la trayectoria.
        op_path = run.out_dir / "resultado_operativo.jsonl"
        deadline = time.monotonic() + 30
        ops: List[Dict[str, Any]] = []
        while time.monotonic() < deadline:
            ops = [r for r in tr.read_rows(op_path)
                   if r.get("kind") == "resultado_operativo"]
            if len(ops) >= len(obs_aptas):
                break
            time.sleep(0.02)
        assert len(ops) == len(obs_aptas), ops
        # Una fila por observacion (sin duplicados) y una sola operacion
        # admitida: max_concurrent=1 compartido.
        assert len({o["observation_id"] for o in ops}) == len(ops), ops
        admitidas = [o for o in ops if o["decision"] == "ENTRADA_EJECUTADA"]
        rechazadas = [o for o in ops
                      if o["decision"] == "RECHAZADA_CAPACIDAD"]
        assert len(admitidas) == 1, ops
        assert len(rechazadas) == len(obs_aptas) - 1, ops

        # Consultas observadas por el proveedor.
        observadas = {
            "klines_total": run.http.klines_calls,
            "klines_trayectoria": run.http.klines_calls_trajectory,
            "klines_precio": run.http.klines_calls_precio,
            "ticker": run.http.ticker_calls,
            "catalogo": run.http.exchange_info_calls,
        }
        # Consumo de la puerta de presupuesto y plan de la corrida.
        run.stop()
        resumen = json.loads(
            (run.out_dir / "resumen.json").read_text(encoding="utf-8"))
        gate = resumen["presupuesto_http"]
        plan = resumen["presupuesto_plan"]

        base = plan["rest"]["estimacion_base"]
        previsto = {
            "preparacion": base["preparacion"]["llamadas"],
            "trayectoria": base["consultas_operativas"]["llamadas"],
            "horizontes": base["resultados_por_horizonte"]["llamadas"],
        }
        # Una consulta de trayectoria por observacion apta.
        assert observadas["klines_trayectoria"] == len(obs_aptas), observadas
        assert previsto["trayectoria"] == len(obs_aptas), previsto
        # Un precio por observacion y horizonte.
        assert observadas["klines_precio"] == len(obs_aptas) * len(
            tr.HORIZONS), observadas
        assert previsto["horizontes"] == len(obs_aptas) * len(tr.HORIZONS)
        # Preparacion: catalogo + tickers por seleccion.
        assert observadas["ticker"] == previsto["preparacion"] - 1, (
            observadas, previsto)
        assert observadas["catalogo"] == 1, observadas
        # Las tres cifras coinciden: proveedor == gate == plan.
        assert (observadas["klines_total"] + observadas["ticker"]
                + observadas["catalogo"]) == (
                    previsto["preparacion"] + previsto["trayectoria"]
                    + previsto["horizontes"]), (observadas, previsto)
        assert gate["attempts"] == (observadas["klines_total"]
                                    + observadas["ticker"]
                                    + observadas["catalogo"]), (gate, observadas)
        assert gate["weight"] == plan["rest"]["estimacion_base"]["peso"], (
            gate, plan["rest"]["estimacion_base"])
        assert gate["blocked"] is False, gate
        # Topes congelados respetados.
        assert gate["max_attempts"] == 2000 and gate["max_weight"] == 5000
        assert gate["max_retries"] == 50
        assert plan["rest"]["cabe_en_limites"] is True
        # La estimacion base no se presenta como maximo garantizado.
        assert (plan["rest"]["intentos_base_mas_reservas"]
                <= plan["rest"]["intentos_techo_efectivo"])
        assert (plan["rest"]["peso_base_mas_reservas_max"]
                <= plan["rest"]["peso_techo_efectivo"])
        print(f"  [presupuesto] observadas={observadas} "
              f"gate_attempts={gate['attempts']} gate_peso={gate['weight']} "
              f"plan_base={previsto}")
    finally:
        run.shutdown()


if __name__ == "__main__":
    test_capacidad_exposiciones_solapadas()
    print("OK: capacidad A (solapadas)")
    test_capacidad_entrada_posterior_a_salida()
    print("OK: capacidad B (entrada posterior)")
    test_capacidad_posicion_sin_salida_conocida()
    print("OK: capacidad C (salida desconocida)")
    test_capacidad_repetir_observaciones_es_estable()
    print("OK: capacidad D (repeticiones)")
    test_capacidad_rol_no_altera_prioridad_ni_direccion()
    print("OK: capacidad E (rol)")
    test_presupuesto_cli_observado_vs_plan()
    print("OK: presupuesto observado vs plan")
    print("TODAS LAS PRUEBAS DE CIERRE PASARON")
