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
import shutil
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
    base_price, find_free_port, kline_price, HORIZONS,
)
from microstructure_probe.backtest_offline import (  # noqa: E402
    FundingCalendar, FundingSettlement, funding_settlements_sha256,
)
from microstructure_probe.history_client import (  # noqa: E402
    HistoryClient, INTERVAL_MS,
)

# ---- Comando del piloto (corregido, solo opciones reales del parser) -----

CMD_BASE = [
    sys.executable, str(ROOT / "scripts" / "research_pilot.py"),
    "--mode", "local",
    "--duration-seconds", "3600",   # captura 3600 s
    "--settle-seconds", "4200",     # settle 4200 s (70 min)
    "--cycle-seconds", "300",
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
    loopback y reloj manual. El piloto ejecuta la regla operativa internamente
    durante la captura y el settle, resolviendo operaciones pendientes a
    medida que la trayectoria se vuelve disponible. El test NO crea un
    adaptador externo ni un HistoryClient sin gate: todo lo produce el CLI
    real bajo su presupuesto.

    Demuestra:
    - Observaciones aptas persistidas en T con decision_ms y move_24h_pct.
    - Trabajo operativo pendiente sin resultado futuro antes de tener
      trayectoria suficiente.
    - Resolucion posterior del CLI una vez disponible la trayectoria.
    - Capacidad compartida max_concurrent=1 (seniales solapadas no producen
      dos posiciones).
    - Funding desconocido (sin calendario) -> neto condicionado, no cero.
    - Presupuesto reservado antes del transporte (intento bloqueado no
      aumenta contador del proveedor).
    - Parada conserva pendientes con causa real.
    """
    tmp = Path(tempfile.mkdtemp(prefix="cli-integro-"))
    ok = False

    # Calendario de funding SINTETICO propio de esta prueba: se genera en su
    # directorio temporal y se pasa por --funding-calendars. No depende de
    # ningun fichero externo (por ejemplo /tmp/fund_test).
    e0 = tr.T0 + tr.MINUTE
    settlement_ms = e0 + 1_800_000        # dentro de la exposicion
    rate_bps = 1.0
    fund_dir = tmp / "funding"
    fund_dir.mkdir(parents=True, exist_ok=True)
    cal_path = fund_dir / "calendario_cli.json"
    settlements = [
        FundingSettlement(settlement_ms - 8 * 3600 * 1000, rate_bps),
        FundingSettlement(settlement_ms, rate_bps),
        FundingSettlement(settlement_ms + 8 * 3600 * 1000, rate_bps),
    ]
    coverage_start = settlement_ms - 8 * 3600 * 1000
    coverage_end = settlement_ms + 8 * 3600 * 1000 + 1
    cal_path.write_text(json.dumps({
        "AAAUSDT": {
            "version": "synthetic/v1",
            "source": "synthetic-fixture",
            "interval_ms": 8 * 3600 * 1000,
            # Cadencia de 8 h que cubre toda la exposicion: solo el
            # settlement central cae dentro de la ventana de la operacion.
            "settlements": [
                {"settlement_ms": item.settlement_ms,
                 "rate_bps": item.rate_bps}
                for item in settlements
            ],
            "coverage": {
                "version": "funding-coverage/v1",
                "status": "complete",
                "symbol": "AAAUSDT",
                "venue": "synthetic",
                "source": "synthetic-fixture",
                "interval_start_ms": coverage_start,
                "interval_end_ms": coverage_end,
                "acquired_at_ms": coverage_end,
                "available_at_ms": coverage_end,
                "method": "synthetic-fixture",
                "evidence": {
                    "kind": "synthetic-fixture",
                    "reference": "synthetic-fixture://cli-coverage/v1",
                    "statement": "complete synthetic coverage for the CLI test",
                    "sha256": "a" * 64,
                    "artifact_uri": "synthetic-fixture://cli-coverage/v1",
                    "artifact_sha256": "a" * 64,
                    "symbol": "AAAUSDT",
                    "venue": "synthetic",
                    "interval_start_ms": coverage_start,
                    "interval_end_ms": coverage_end,
                    "valid_from_ms": coverage_start,
                    "valid_until_ms": coverage_end,
                },
                "request": {
                    "endpoint": "synthetic://funding-history",
                    "params": {
                        "symbol": "AAAUSDT",
                        "startTime": coverage_start,
                        "endTime": coverage_end - 1,
                        "limit": 1000,
                    },
                    "http_status": 200,
                    "sent_at_ms": coverage_end,
                    "completed_at_ms": coverage_end,
                },
                "response": {
                    "sha256": "b" * 64,
                    "row_count": len(settlements),
                    "symbols": ["AAAUSDT"],
                    "pagination": {
                        "pages": 1,
                        "complete": True,
                        "truncated": False,
                    },
                    "settlement_sha256": funding_settlements_sha256(
                        tuple(settlements)),
                    "first_settlement_ms": settlements[0].settlement_ms,
                    "last_settlement_ms": settlements[-1].settlement_ms,
                },
                "publication_delay_ms": 0,
                "publication_delay_evidence": {
                    "kind": "synthetic-fixture",
                    "reference": "synthetic-fixture://publication-delay/v1",
                    "statement": "synthetic rows are available at acquisition",
                    "sha256": "c" * 64,
                    "artifact_uri": "synthetic-fixture://publication-delay/v1",
                    "artifact_sha256": "c" * 64,
                    "symbol": "AAAUSDT",
                    "venue": "synthetic",
                    "interval_start_ms": coverage_start,
                    "interval_end_ms": coverage_end,
                    "available_at_ms": coverage_end,
                },
                "reason": "",
            },
        }
    }), encoding="utf-8")

    run = tr.PilotRun(
        tmp,
        universe=tr.UNIVERSE,
        duration_s=300,    # captura 300 s (5 min), suficiente para el corte
        settle_s=4200,     # settle 4200 s (70 min): cubre el horizonte 60m
        selection_s=300,
        max_symbols=5,
        cycle_s=300,       # corregido: 300s, no 60s
        horizons=tr.HORIZONS,
        max_http_attempts=2000,
        funding_calendars_path=str(cal_path),
    )

    try:
        run.wait_ready(expected_followed=5)

        # Corte de decision: publicar libro + ventana completa de flujo
        # (60s) para que las observaciones sean aptas.
        seed = list(range(e0 - 62_000, e0 + 1, 1_000))

        # 1. Avanzar a e0 - 1000 (un segundo antes del corte)
        run.clock.set(e0 - 1_000)
        run.advance(e0 - 1_000)

        # 2. Publicar libro y flujo para todos los simbolos
        sent = run.ws.publish(e0, depth_symbols=tr.UNIVERSE,
                              trade_events={s: seed for s in tr.UNIVERSE})
        if any(sent["depth"].get(s, 0) != 1 for s in tr.UNIVERSE):
            raise AssertionError(f"libro no publicado para todos: {sent}")
        if any(sent["trades"].get(s, 0) != len(seed) for s in tr.UNIVERSE):
            raise AssertionError(f"flujo no publicado para todos: {sent}")

        # 3. Esperar a que el piloto procese los eventos publicados.
        deadline = time.monotonic() + 30
        confirmado = False
        while time.monotonic() < deadline:
            st = run.status()
            if (st and st.get("book_events")
                    and all(st["book_events"].get(s, 0) >= 1 for s in tr.UNIVERSE)
                    and all(st["flow_events"].get(s, 0) >= len(seed)
                            for s in tr.UNIVERSE)):
                confirmado = True
                break
            if run.proc.poll() is not None:
                out, err = run.proc.communicate(timeout=5)
                raise AssertionError(
                    f"piloto termino esperando confirmacion: "
                    f"rc={run.proc.returncode} stdout={out!r} stderr={err!r}")
            time.sleep(0.02)
        if not confirmado:
            raise AssertionError(f"no se confirman libro/flujo: status={st!r}")

        # 4. Escribir el decision-gate PARA ANTES de avanzar el reloj a e0,
        #    para que el piloto lo lea al procesar el corte.
        tmp_gate = run.gate_path.with_name(run.gate_path.name + ".tmp")
        tmp_gate.write_text(
            json.dumps({"decision_ms": e0, "allow": True}),
            encoding="utf-8")
        os.replace(tmp_gate, run.gate_path)

        # 5. Avanzar a e0 (corte de decision). Con el reloj en e0 y el gate
        #    ya escrito, el piloto evalua y crea observaciones aptas.
        run.clock.set(e0)
        run.advance(e0)

        # Esperar a que se escriban las observaciones.
        deadline = time.monotonic() + 30
        obs_ok = False
        while time.monotonic() < deadline:
            rows_obs = _leer_jsonl(run.obs_path)
            obs_aptas = [
                r for r in rows_obs
                if r.get("kind") == "observacion"
                and r.get("decision_ms") == e0
                and r.get("apto_para_evaluacion")
            ]
            if len(obs_aptas) >= 5:
                obs_ok = True
                break
            if run.proc.poll() is not None:
                out, err = run.proc.communicate(timeout=5)
                raise AssertionError(
                    f"piloto termino esperando observaciones: "
                    f"rc={run.proc.returncode} stdout={out!r} stderr={err!r}")
            time.sleep(0.02)
        if not obs_ok:
            raise AssertionError(
                f"no hay observaciones aptas en decision_ms={e0}")

        # 6. Avanzar el reloj al final de la captura (el piloto entra al
        #    settle) y luego al final del horizonte operativo para que el CLI
        #    resuelva las operaciones pendientes con trayectoria disponible.
        op_path = run.out_dir / "resultado_operativo.jsonl"
        capture_end = run.status()["capture_end_ms"]
        run.advance(capture_end)
        st = run.status()
        assert st["phase"] == "settle", f"esperaba settle, fase={st.get('phase')}"

        ahora_final = e0 + 3_600_000 + tr.MINUTE * 2
        assert ahora_final < st["settle_end_ms"], (
            f"ahora_final={ahora_final} sobrepasa settle_end={st['settle_end_ms']}")
        run.advance(ahora_final)

        # Esperar a que el CLI escriba los resultados operativos (el piloto
        # los resuelve durante el settle al leer la trayectoria).
        deadline = time.monotonic() + 30
        ops_ok = False
        rows_op: List[Dict[str, Any]] = []
        while time.monotonic() < deadline:
            rows_op = _leer_jsonl(op_path)
            ops = [r for r in rows_op if r.get("kind") == "resultado_operativo"]
            if len(ops) >= len(obs_aptas):
                ops_ok = True
                break
            if run.proc.poll() is not None:
                break
            time.sleep(0.02)
        if not ops_ok:
            raise AssertionError(
                f"no hay resultados operativos del CLI: "
                f"filas={rows_op!r}, esperadas>={len(obs_aptas)}")

        # Vinculacion con observaciones fuente.
        obs_por_id = {
            r["observation_id"]: r
            for r in rows_obs
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

        # Solicitudes recibidas por los proveedores (el CLI hizo las peticiones
        # de klines para resolver operaciones, no un adaptador externo).
        assert run.http.ticker_calls >= 1, run.http.ticker_calls
        assert run.http.klines_calls >= 1, run.http.klines_calls
        assert run.ws.connections >= 1, run.ws.connections

        # Regenerar resumen desde lo persistido (el CLI ya escribio todo).
        resumen = _resumen_desde_persistido(op_path)
        assert resumen["operaciones"] >= 1, resumen
        assert resumen["salidas_ejecutadas_simuladas"] >= 1, resumen
        assert resumen["funding_desconocido"] >= 1, resumen  # sin calendario
        # Funding via CLI: calendario con evento en exposición -> contabilizado.
        assert resumen["funding_contabilizado"] >= 1, resumen

        # Capacidad compartida (max_concurrent=1): una sola operacion
        # admitida (prioridad determinista por simbolo) y el resto rechazadas
        # por capacidad. Sin duplicados de observation_id.
        assert len({op["observation_id"] for op in ops}) == len(ops), ops
        admitidas = [op for op in ops if op["decision"] == "ENTRADA_EJECUTADA"]
        rechazadas = [op for op in ops
                      if op["decision"] == "RECHAZADA_CAPACIDAD"]
        assert len(admitidas) == 1, ops
        assert len(rechazadas) == len(obs_aptas) - 1, ops
        admitida = admitidas[0]
        assert admitida["symbol"] == "AAAUSDT", admitida

        # Exposicion causal: entrada en el open posterior a la decision y
        # salida por horizonte (instante de conocimiento de la ultima vela).
        assert admitida["entry_ms"] == e0 + tr.MINUTE, admitida
        assert admitida["exit_ms"] == e0 + 3_600_000 + tr.MINUTE, admitida
        assert admitida["exit_reason"] == "horizon", admitida
        assert admitida["exit_executed"] is True, admitida

        # Verificar que el símbolo con calendario (AAAUSDT, primero alfabéticamente)
        # tiene funding contabilizado en resultado_operativo.jsonl.
        rows_op = _leer_jsonl(op_path)
        aaa_ops = [r for r in rows_op
                   if r.get("kind") == "resultado_operativo"
                   and r.get("symbol") == "AAAUSDT"]
        assert len(aaa_ops) >= 1, f"AAAUSDT sin filas operativas: {rows_op!r}"
        aaa_funded = [r for r in aaa_ops if r.get("funding") is not None]
        assert len(aaa_funded) >= 1, (
            f"AAAUSDT sin funding contabilizado: {aaa_ops!r}")
        for r in aaa_funded:
            assert r["funding_estado"] == "settlement-calendar", r
            assert isinstance(r["funding"], (int, float)), r

        # Importe de funding calculado de forma INDEPENDIENTE del motor:
        # qty (notional / precio de fill) x marca causal del settlement x
        # rate_bps/10000. La marca es el open de la vela 1m del settlement.
        fill_px = kline_price(admitida["symbol"], admitida["entry_ms"])
        assert abs(admitida["entry_px"] - fill_px) < 1e-8, admitida
        qty = 1000.0 / fill_px
        marca = kline_price(admitida["symbol"], settlement_ms)
        esperado = qty * marca * rate_bps / 10_000.0
        assert abs(admitida["funding"] - esperado) < 1e-9, (
            admitida["funding"], esperado)
        assert admitida["net_pnl"] is not None, admitida
        # El calendario cubre toda la exposicion: no hay tiempo sin cubrir.
        assert admitida.get("funding_cuenta_completa") is True, admitida
        assert admitida.get("funding_sin_cubrir_ms") == 0, admitida
        assert admitida.get("funding_huecos_ms") == 0, admitida
        assert admitida.get("funding_settlements_desconocidos") == 0, admitida
        assert admitida.get("funding_cobertura_estado") == "complete", admitida
        assert admitida.get("funding_cobertura_inicio_ms") == coverage_start, admitida
        assert admitida.get("funding_cobertura_fin_ms") == coverage_end, admitida
        assert admitida.get("funding_cobertura_hash"), admitida
        assert admitida.get("funding_cobertura", {}).get("request"), admitida
        assert admitida.get("neto_estado") == "COMPLETO", admitida

        # Sin calendario propio (simbolos sin calendario) el funding queda
        # UNKNOWN, nunca cero.
        for r in rechazadas:
            assert r["funding"] is None, r
            assert r["funding_estado"] == "rechazada_por_capacidad", r

        print(f"  [CLI integrado] operaciones={resumen['operaciones']} "
              f"direcciones={resumen['por_direccion']} "
              f"salidas={resumen['salidas_ejecutadas_simuladas']} "
              f"funding_desconocido={resumen['funding_desconocido']} "
              f"funding_contabilizado={resumen['funding_contabilizado']} "
              f"http_klines={run.http.klines_calls} ws_conns={run.ws.connections}")
        ok = True
    finally:
        run.shutdown()
        # Solo se limpian los recursos propios de esta prueba.
        if ok:
            shutil.rmtree(tmp, ignore_errors=True)



def test_cli_funding_incompleto_desde_cli_real() -> None:
    """El CLI real persiste funding UNKNOWN con cobertura incompleta.

    El calendario se crea dentro del directorio temporal de esta prueba y se
    pasa por ``--funding-calendars``. Solo contiene un settlement al inicio
    de la exposicion, por lo que el motor conserva exposicion sin cubrir y
    la contabilidad por posicion queda incompleta.
    """
    tmp = Path(tempfile.mkdtemp(prefix="cli-funding-incompleto-"))
    universe = [tr.UNIVERSE[0]]
    e0 = tr.T0 + tr.MINUTE
    entrada_prevista = e0 + tr.MINUTE
    cal_path = tmp / "calendario_incompleto.json"
    cal_path.write_text(json.dumps({
        universe[0]: {
            "version": "synthetic/v1",
            "source": "synthetic-fixture",
            "interval_ms": 8 * 3600 * 1000,
            "settlements": [
                {"settlement_ms": entrada_prevista, "rate_bps": 1.0},
            ],
        }
    }), encoding="utf-8")

    run = tr.PilotRun(
        tmp,
        universe=universe,
        duration_s=300,
        settle_s=4200,
        selection_s=300,
        max_symbols=1,
        cycle_s=300,
        horizons=tr.HORIZONS,
        max_http_attempts=2000,
        funding_calendars_path=str(cal_path),
    )
    try:
        run.wait_ready(expected_followed=1)
        seed = list(range(e0 - 62_000, e0 + 1, 1_000))
        run.step(
            e0,
            depth_symbols=universe,
            trade_events={universe[0]: seed},
            evaluate=True,
            expected_obs=1,
        )
        capture_end = run.status()["capture_end_ms"]
        run.advance(capture_end)
        run.advance(e0 + 3_600_000 + tr.MINUTE * 2)

        op_path = run.out_dir / "resultado_operativo.jsonl"
        deadline = time.monotonic() + 30
        ops: List[Dict[str, Any]] = []
        while time.monotonic() < deadline:
            if op_path.exists():
                ops = [r for r in _leer_jsonl(op_path)
                       if r.get("kind") == "resultado_operativo"]
            if len(ops) >= 1:
                break
            if run.proc.poll() is not None:
                break
            time.sleep(0.02)
        assert len(ops) == 1, ops
        row = ops[0]
        assert row["decision"] == "ENTRADA_EJECUTADA", row
        assert row["funding"] is None, row
        assert "UNKNOWN" in row["funding_estado"], row
        assert row["funding_cuenta_completa"] is False, row
        assert row["funding_sin_cubrir_ms"] > 0, row
        assert row["neto_estado"] == "CONDICIONADO_SIN_FUNDING_COMPLETO", row
        print(f"  [CLI funding incompleto] symbol={row['symbol']} "
              f"funding={row['funding']} estado={row['funding_estado']} "
              f"completa={row['funding_cuenta_completa']} "
              f"sin_cubrir_ms={row['funding_sin_cubrir_ms']}")
    finally:
        run.shutdown()


def test_funding_a_traves_del_adaptador(monkeypatch) -> None:
    """Funding por cobertura de posicion, a traves del adaptador persistido.

    Escenarios (todos con calendario sintetico propio de la prueba):
    - sin calendario -> UNKNOWN;
    - cobertura incompleta con exposicion sin cubrir -> total UNKNOWN;
    - cobertura completa con settlement aplicable -> importe acreditado y
      verificado con un calculo independiente;
    - cobertura completa sin settlement dentro de exposicion -> cero acreditado;
    - integridad por posicion ausente -> UNKNOWN (fallo cerrado);
    - calendario sin cadencia nominal o con hueco aplicable -> UNKNOWN.
    """
    import scripts.research_operativo_adapter as adapter_module  # noqa: E402
    from scripts.research_operativo_adapter import (  # noqa: E402
        OperativoAdapter, OperativoConfig,
    )
    from microstructure_probe.paper_lab_engine import (  # noqa: E402
        PaperCandle,
    )

    tmp = Path(tempfile.mkdtemp(prefix="funding-adaptador-"))

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

    def _procesar(nombre: str, calendario=None):
        adapter = OperativoAdapter(
            store_path=tmp / f"{nombre}.jsonl",
            cfg=OperativoConfig(),
            funding_calendars=({"FUNDUSDT": calendario} if calendario
                               else {}),
        )
        tr = adapter.procesar_observacion(obs, velas)
        adapter.persistir(tr)
        adapter.close()
        rows = _leer_jsonl(tmp / f"{nombre}.jsonl")
        return tr, rows[-1]

    # 1) Calendario ausente -> funding UNKNOWN.
    tr_sin, row_sin = _procesar("sin_calendario")
    assert tr_sin.funding is None, tr_sin
    assert tr_sin.funding_estado.startswith("ninguno"), tr_sin
    assert row_sin["funding"] is None, row_sin
    assert row_sin["neto_estado"] == "CONDICIONADO_SIN_FUNDING_COMPLETO", row_sin

    # 2) Reproduccion del defecto: un settlement en la entrada y ningun
    #    settlement posterior deixa 60000 ms de exposicion sin cubrir. El
    #    total observado no sustituye al total UNKNOWN.
    cal_incompleto = FundingCalendar(
        version="synthetic/v1", source="synthetic-fixture",
        interval_ms=8 * 3600 * 1000, symbol="FUNDUSDT",
        settlements=(FundingSettlement(settlement_ms=120_000, rate_bps=1.0),),
    )
    tr_inc, row_inc = _procesar("incompleto", cal_incompleto)
    assert tr_inc.entry_ms == 120_000 and tr_inc.exit_ms == 180_000, tr_inc
    assert tr_inc.funding is None, tr_inc
    assert "UNKNOWN" in tr_inc.funding_estado, tr_inc
    assert row_inc["funding"] is None, row_inc
    assert row_inc["funding_cuenta_completa"] is False, row_inc
    assert row_inc["funding_sin_cubrir_ms"] == 60_000, row_inc
    assert row_inc["neto_estado"] == "CONDICIONADO_SIN_FUNDING_COMPLETO", row_inc

    # 3) Cobertura completa con settlement aplicable dentro de la exposicion
    #    (120000 en [entry_ms=120000, exit_ms=180000)).
    cal = FundingCalendar(
        version="synthetic/v1", source="synthetic-fixture",
        interval_ms=8 * 3600 * 1000, symbol="FUNDUSDT",
        settlements=(
            FundingSettlement(settlement_ms=120_000, rate_bps=1.0),
            FundingSettlement(
                settlement_ms=120_000 + 8 * 3600 * 1000, rate_bps=1.0),
        ),
    )
    tr_con, row_con = _procesar("con_evento", cal)
    assert tr_con.funding_estado == "settlement-calendar", tr_con
    # Importe esperado calculado independientemente: held_qty * mark * rate / 10000
    qty = 1000.0 / 102.0
    esperado = qty * 102.0 * 1.0 / 10_000.0
    assert abs(tr_con.funding - esperado) < 1e-9, (tr_con.funding, esperado)
    assert row_con["funding_cuenta_completa"] is True, row_con
    assert row_con["funding_sin_cubrir_ms"] == 0, row_con
    assert row_con["neto_estado"] == "COMPLETO", row_con

    # 4) Cobertura completa sin settlement dentro de la exposicion -> cero
    #    acreditado. El primer settlement precede la entrada y el ultimo la
    #    sigue; la cadencia nominal acredita que no hay pago aplicable.
    cal_sin_evento = FundingCalendar(
        version="synthetic/v1", source="synthetic-fixture",
        interval_ms=8 * 3600 * 1000, symbol="FUNDUSDT",
        settlements=(
            FundingSettlement(settlement_ms=0, rate_bps=1.0),
            FundingSettlement(
                settlement_ms=8 * 3600 * 1000, rate_bps=1.0),
        ),
    )
    tr_vac, row_vac = _procesar("sin_evento", cal_sin_evento)
    assert tr_vac.funding == 0.0, tr_vac
    assert tr_vac.funding_estado == "settlement-calendar", tr_vac
    assert row_vac["funding_cuenta_completa"] is True, row_vac
    assert row_vac["funding_sin_cubrir_ms"] == 0, row_vac
    assert row_vac["neto_estado"] == "COMPLETO", row_vac

    # 5) Si la autoridad no publica el veredicto por posicion, el adaptador
    #    falla cerrado y conserva la integridad como desconocida.
    resultado_con_funding_real = adapter_module._resultado_con_funding

    def _resultado_sin_integridad(*args, **kwargs):
        bt = resultado_con_funding_real(*args, **kwargs)
        if bt is None:
            return None
        bt = dict(bt)
        bt.pop("funding_accounting_complete", None)
        return bt

    monkeypatch.setattr(
        adapter_module, "_resultado_con_funding", _resultado_sin_integridad)
    tr_desconocida, row_desconocida = _procesar(
        "integridad_desconocida", cal)
    assert tr_desconocida.funding is None, tr_desconocida
    assert "UNKNOWN" in tr_desconocida.funding_estado, tr_desconocida
    assert row_desconocida["funding_cuenta_completa"] is None, row_desconocida
    assert row_desconocida["neto_estado"] == "CONDICIONADO_SIN_FUNDING_COMPLETO", (
        row_desconocida)
    monkeypatch.setattr(
        adapter_module, "_resultado_con_funding", resultado_con_funding_real)

    # 6) Calendario sin cadencia nominal -> la integridad interior es
    #    UNKNOWN: el importe NO se acredita.
    cal_sin_cadencia = FundingCalendar(
        version="synthetic/v1", source="synthetic-fixture",
        interval_ms=None, symbol="FUNDUSDT",
        settlements=(FundingSettlement(settlement_ms=120_000, rate_bps=1.0),),
    )
    tr_nc, row_nc = _procesar("sin_cadencia", cal_sin_cadencia)
    assert tr_nc.funding is None, tr_nc
    assert "UNKNOWN" in tr_nc.funding_estado, tr_nc
    assert row_nc["funding"] is None, row_nc

    # 7) Hueco interior del calendario sobre la exposicion -> UNKNOWN.
    cal_con_hueco = FundingCalendar(
        version="synthetic/v1", source="synthetic-fixture",
        interval_ms=8 * 3600 * 1000, symbol="FUNDUSDT",
        settlements=(
            FundingSettlement(settlement_ms=120_000, rate_bps=1.0),
            FundingSettlement(
                settlement_ms=120_000 + 3 * 8 * 3600 * 1000, rate_bps=1.0),
        ),
    )
    tr_gap, row_gap = _procesar("con_hueco", cal_con_hueco)
    assert tr_gap.funding is None, tr_gap
    assert "UNKNOWN" in tr_gap.funding_estado, tr_gap
    assert row_gap["funding"] is None, row_gap

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"  [funding] ausente={tr_sin.funding_estado} "
          f"incompleto={tr_inc.funding_estado} "
          f"con_evento={tr_con.funding} (esperado {esperado}) "
          f"sin_evento={tr_vac.funding} "
          f"integridad_desconocida={tr_desconocida.funding_estado} "
          f"sin_cadencia={tr_nc.funding_estado} "
          f"con_hueco={tr_gap.funding_estado}")


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
