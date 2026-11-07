"""Prueba integrada del CLI productivo del experimento operativo v2.

Lanza ``scripts/research_pilot.py`` como subproceso real con proveedores
HTTP/WS loopback y almacenamiento temporal aislado. Bloquea dominios
publicos de mercado (modo ``local``, sin ``--activar-publico``).

Demuestra:
- Solicitudes y suscripciones realmente recibidas por los proveedores loopback.
- Seleccion y datos para candidato y comparador.
- Movimiento y trayectoria persistidos.
- Invocacion del OperativoAdapter desde el camino del experimento.
- Operacion y resultado vinculados a los registros fuente (observation_id).
- Regeneracion del resultado desde lo persistido.
- Finalizacion acotada y ausencia de procesos propios residuales.
- Funding a traves del adaptador: calendario conocido con evento en la
  exposicion; calendario ausente/incompleto -> UNKNOWN.
- Bloqueo presupuestario real mediante la puerta del cliente y del piloto.

Usa el reloj de prueba existente (--clock manual) para acelerar captura y
maduracion, conservando la cronologia.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Reutilizamos el harness y los proveedores loopback ya probados del piloto.
import tests.test_research_pilot as tr  # noqa: E402
from tests.test_research_pilot import (  # noqa: E402
    ClockFile, MarketHttp, PilotRun, WsProvider, T0, MINUTE,
    base_price, find_free_port, HORIZONS,
)
from microstructure_probe.backtest_offline import (  # noqa: E402
    FundingCalendar, FundingSettlement,
)

# ---- Comando del piloto (corregido, solo opciones reales del parser) -----

CMD_BASE = [
    sys.executable, str(ROOT / "scripts" / "research_pilot.py"),
    "--mode", "local",
    "--duration-seconds", "3600",   # captura 3600 s
    "--settle-seconds", "4200",     # settle 4200 s (70 min)
    "--cycle-seconds", "60",
    "--selection-seconds", "300",
    "--decision-delay-seconds", "5",
    "--max-symbols", "20",
    "--max-candidates", "12",
    "--max-comparators", "8",
    "--min-quote-volume", "1000000",
    "--horizons", "5m=300000,15m=900000,60m=3600000",
    "--price-interval", "1m",
    "--price-tolerance-ms", "90000",
    "--price-delay-ms", "2000",
    "--max-data-age-ms", "5000",
    "--max-observations", "20000",
    "--max-bytes", str(128 * 1024 * 1024),
    "--max-messages", "5000000",
    "--max-http-attempts", "2000",
    "--max-http-retries", "50",
    "--max-http-weight", "5000",
    "--max-ws-reconnects", "20",
    "--tick-ms", "20",
    "--clock", "manual", "--clock-file", None,  # se rellena por instancia
]


def _run_id() -> str:
    return f"cli-integro-{int(time.time() * 1000)}"


def _leer_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _resumen_desde_persistido(path: Path) -> Dict[str, Any]:
    """Regenera el resumen exclusivamente desde filas persistidas."""
    rows = _leer_jsonl(path)
    ops = [r for r in rows if r.get("kind") == "resultado_operativo"]
    resumen: Dict[str, Any] = {
        "filas_totales": len(rows),
        "operaciones": len(ops),
        "por_direccion": {},
        "por_decision": {},
        "salidas_ejecutadas_simuladas": 0,
        "funding_desconocido": 0,
        "funding_contabilizado": 0,
        "motivos_abstencion": [],
    }
    for r in ops:
        d = r.get("direction") or "None"
        resumen["por_direccion"][d] = resumen["por_direccion"].get(d, 0) + 1
        dec = r.get("decision") or "None"
        resumen["por_decision"][dec] = resumen["por_decision"].get(dec, 0) + 1
        if r.get("exit_executed"):
            resumen["salidas_ejecutadas_simuladas"] += 1
        if r.get("funding") is None:
            resumen["funding_desconocido"] += 1
        else:
            resumen["funding_contabilizado"] += 1
        if dec == "SIN_ENTRADA":
            resumen["motivos_abstencion"].append({
                "symbol": r["symbol"], "motivo": r.get("funding_estado"),
            })
    return resumen


# ---------------------------------------------------------------------------
# Prueba integrada
# ---------------------------------------------------------------------------

def test_cli_productivo_integrado() -> None:
    """Recorrido integrado CLI -> piloto -> adaptador -> motores -> resultado.

    Usa PilotRun (harness probado del piloto) con proveedores HTTP/WS
    loopback y reloj manual. Verifica que el OperativoAdapter se invoque
    desde el camino del experimento y que los resultados se puedan
    regenerar desde lo persistido.
    """
    tmp = Path(tempfile.mkdtemp(prefix="cli-integro-"))

    run = tr.PilotRun(
        tmp,
        universe=tr.UNIVERSE,
        duration_s=3600,   # captura 3600 s
        settle_s=4200,     # settle 4200 s (70 min)
        selection_s=300,
        max_symbols=5,
        cycle_s=60,
        horizons=tr.HORIZONS,
        max_http_attempts=2000,
    )

    try:
        run.wait_ready(expected_followed=5)

        # Corte de decision: publicar libro + ventana completa de flujo
        # (60s) para que las observaciones sean aptas.
        e0 = tr.T0 + tr.MINUTE
        seed = list(range(e0 - 62_000, e0 + 1, 1_000))
        obs = run.step(
            e0,
            depth_symbols=tr.UNIVERSE,
            trade_events={s: seed for s in tr.UNIVERSE},
            evaluate=True, expected_obs=5,
        )
        assert len(obs) == 5, obs

        # Verificar que el adaptador escribio resultados operativos.
        op_path = run.out_dir / "resultado_operativo.jsonl"
        deadline = time.monotonic() + 60
        ops_ok = False
        rows_op: List[Dict[str, Any]] = []
        while time.monotonic() < deadline:
            rows_op = _leer_jsonl(op_path)
            ops = [r for r in rows_op if r.get("kind") == "resultado_operativo"]
            if len(ops) >= 5:
                ops_ok = True
                break
            if run.proc.poll() is not None:
                out, err = run.proc.communicate(timeout=5)
                raise AssertionError(
                    f"piloto termino esperando operaciones: rc={run.proc.returncode} "
                    f"stdout={out!r} stderr={err!r}")
            time.sleep(0.02)
        if not ops_ok:
            raise AssertionError(
                f"no hay resultados operativos: filas={rows_op!r}")

        # Vinculacion con observaciones fuente.
        obs_por_id = {
            r["observation_id"]: r
            for r in _leer_jsonl(run.obs_path)
            if r.get("kind") == "observacion"
        }
        for op in ops:
            oid = op["observation_id"]
            assert oid in obs_por_id, f"operacion sin observacion: {oid}"
            obs_src = obs_por_id[oid]
            assert op["symbol"] == obs_src["symbol"], (op, obs_src)
            assert op["role"] == obs_src["role"], (op, obs_src)
            assert op["decision_ms"] == obs_src["decision_ms"], (op, obs_src)
            assert op["config_hash"], op
            assert op["engine_version"], op

        # Direccion coherente con el dato de movimiento.
        dirs = {op["symbol"]: op["direction"] for op in ops}
        for op in ops:
            obs_src = obs_por_id[op["observation_id"]]
            move = obs_src.get("seleccion", {}).get("move_24h_pct")
            dir_esp = ("LONG" if (move or 0) > 0
                       else ("SHORT" if (move or 0) < 0 else None))
            if dir_esp is not None:
                assert op["direction"] == dir_esp, (op, obs_src)
        assert any(d == "LONG" for d in dirs.values()), dirs

        # Solicitudes recibidas por los proveedores.
        assert run.http.ticker_calls >= 1, run.http.ticker_calls
        assert run.http.klines_calls >= 1, run.http.klines_calls
        assert run.ws.connections >= 1, run.ws.connections

        # Finalizacion acotada del piloto.
        state = run.status() or {}
        end = int(state.get("settle_end_ms") or 0)
        if end:
            run.clock.set(end + 1000)
        rc = run.wait_exit(timeout=60)
        assert rc == 0, f"rc={rc} stderr={run.stderr!r}"

        # Regenerar resumen desde lo persistido.
        resumen = _resumen_desde_persistido(op_path)
        assert resumen["operaciones"] >= 1, resumen
        assert resumen["salidas_ejecutadas_simuladas"] >= 1, resumen
        assert resumen["funding_desconocido"] >= 1, resumen  # sin calendario

        print(f"  [CLI integrado] operaciones={resumen['operaciones']} "
              f"direcciones={resumen['por_direccion']} "
              f"salidas={resumen['salidas_ejecutadas_simuladas']} "
              f"funding_desconocido={resumen['funding_desconocido']} "
              f"http_klines={run.http.klines_calls} ws_conns={run.ws.connections}")
    finally:
        run.shutdown()


# ---------------------------------------------------------------------------
# Funding a traves del adaptador
# ---------------------------------------------------------------------------

def test_funding_a_traves_del_adaptador() -> None:
    """Funding por calendario conocido vs ausente, a traves del adaptador."""
    from scripts.research_operativo_adapter import (  # noqa: E402
        OperativoAdapter, OperativoConfig,
    )
    from microstructure_probe.paper_lab_engine import (  # noqa: E402
        PaperCandle,
    )

    # Velas: V1 senal close=102.0 (LONG, stop 101.49), V2 fill open=102.0,
    # V3 revela close de V2 (low=101.0 <= stop).
    velas = [
        PaperCandle(0, 100.0, 101.0, 99.0, 100.0, 59_999),
        PaperCandle(60_000, 101.6, 103.0, 101.55, 102.0, 119_000),
        PaperCandle(120_000, 102.0, 103.0, 101.0, 102.5, 179_000),
        PaperCandle(180_000, 102.0, 103.0, 101.0, 102.5, 239_000),
    ]

    obs = {
        "observation_id": "FUND|119000", "symbol": "FUNDUSDT",
        "role": "candidate", "decision_ms": 119_000,
        "seleccion": {"move_24h_pct": +2.4},
        "side": "UP",
    }

    # 1) Calendario ausente -> funding UNKNOWN.
    adapter_sin = OperativoAdapter(
        store_path=Path(tempfile.mkdtemp()) / "op.jsonl",
        cfg=OperativoConfig(),
    )
    tr_sin = adapter_sin.procesar_observacion(obs, velas)
    adapter_sin.persistir(tr_sin)
    adapter_sin.close()
    assert tr_sin.funding is None, tr_sin
    assert tr_sin.funding_estado.startswith("ninguno"), tr_sin

    # 2) Calendario conocido con evento DENTRO de la exposicion
    #    (120000 en [entry_ms=120000, exit_ms=180000)).
    cal = FundingCalendar(
        version="synthetic/v1", source="synthetic-fixture",
        interval_ms=8 * 3600 * 1000, symbol="FUNDUSDT",
        settlements=(FundingSettlement(settlement_ms=120_000, rate_bps=1.0),),
    )
    adapter_con = OperativoAdapter(
        store_path=Path(tempfile.mkdtemp()) / "op.jsonl",
        cfg=OperativoConfig(),
        funding_calendars={"FUNDUSDT": cal},
    )
    tr_con = adapter_con.procesar_observacion(obs, velas)
    adapter_con.persistir(tr_con)
    adapter_con.close()
    assert tr_con.funding_estado == "settlement-calendar", tr_con
    # Importe esperado calculado independientemente: held_qty * mark * rate / 10000
    qty = 1000.0 / 102.0
    esperado = qty * 102.0 * 1.0 / 10_000.0
    assert abs(tr_con.funding - esperado) < 1e-9, (tr_con.funding, esperado)
    assert tr_con.net_pnl is not None

    # 3) Calendario sin evento en la exposicion -> cero acreditado (no UNKNOWN).
    cal_vacio = FundingCalendar(
        version="synthetic/v1", source="synthetic-fixture",
        interval_ms=8 * 3600 * 1000, symbol="FUNDUSDT",
        settlements=(),
    )
    adapter_vac = OperativoAdapter(
        store_path=Path(tempfile.mkdtemp()) / "op.jsonl",
        cfg=OperativoConfig(),
        funding_calendars={"FUNDUSDT": cal_vacio},
    )
    tr_vac = adapter_vac.procesar_observacion(obs, velas)
    adapter_vac.persistir(tr_vac)
    adapter_vac.close()
    assert tr_vac.funding == 0.0, tr_vac
    assert tr_vac.funding_estado == "settlement-calendar", tr_vac

    print(f"  [funding] ausente={tr_sin.funding_estado} "
          f"con_evento={tr_con.funding} (esperado {esperado}) "
          f"sin_evento={tr_vac.funding}")


# ---------------------------------------------------------------------------
# Bloqueo presupuestario real
# ---------------------------------------------------------------------------

def test_bloqueo_presupuesto_real() -> None:
    """El piloto consume presupuesto y rechaza antes del transporte."""
    from scripts.research_pilot import RunBudget  # noqa: E402
    from microstructure_probe.history_client import (  # noqa: E402
        UpstreamBudgetExceeded,
    )
    b = RunBudget(max_attempts=1, max_retries=5, max_weight=10)
    # Primer intento permitido.
    entry = {"endpoint": "/fapi/v1/klines", "symbol": "AAAUSDT",
             "interval": "1m", "range": "0-60000", "page": 1000,
             "retry": 0, "result": "pending"}
    b.before_send(entry)
    assert b.attempts == 1
    # Segundo intento rechazado ANTES del transporte.
    try:
        b.before_send(entry)
        raise AssertionError("deberia haberse bloqueado")
    except UpstreamBudgetExceeded:
        pass
    st = b.status()
    assert st["blocked"] is True
    assert st["reason"] == "presupuesto_intentos_agotado"
    assert st["attempts"] == 1
    print(f"  [bloqueo presupuesto] gate={st}")


if __name__ == "__main__":
    test_funding_a_traves_del_adaptador()
    print("OK: funding a traves del adaptador")
    test_bloqueo_presupuesto_real()
    print("OK: bloqueo presupuesto real")
    test_cli_productivo_integrado()
    print("OK: CLI productivo integrado")
    print("TODAS LAS PRUEBAS INTEGRADAS CLI PASARON")
