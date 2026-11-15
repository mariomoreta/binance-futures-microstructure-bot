"""Reproducibilidad offline de los resultados operativos (CLI real + loopback).

Demuestra, sin mercado y con almacenamiento temporal:

1. El CLI productivo (scripts/research_pilot.py) recibe respuestas reales del
   proveedor loopback y PERSISTE el cuerpo de cada consulta klines que
   resuelve una operacion (con sus parametros, instantes, estado HTTP, hash y
   vinculo con la observacion).
2. El cuerpo persistido y su hash coinciden con lo recibido y con el ledger
   HTTP.
3. Las observaciones quedan vinculadas a sus fuentes.
4. El recorrido produce entradas y salidas LONG y SHORT con las condiciones ya
   aceptadas, y la capacidad y el orden determinista se conservan.
5. Tras detener los proveedores, la reconstruccion offline
   (scripts/research_operativo_replay.py) funciona EXCLUSIVAMENTE con los
   archivos guardados y reproduce ejecucion y replay en decision, direccion,
   cantidad, entrada, stop, salida, costes y estado del funding/neto.
6. Datos ausentes o archivos corruptos producen una limitacion explicita,
   nunca un resultado inventado; el funding desconocido sigue UNKNOWN.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import os
import shutil
import socket
import subprocess
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

# Direcciones opuestas: el signo del movimiento de 24 h fija la direccion.
MOVES_LONG = {"AAAUSDT": 1.0, "BBBUSDT": 1.2, "CCCUSDT": 1.4,
              "DDDUSDT": 1.6, "EEEUSDT": 1.8}
MOVES_SHORT = {"AAAUSDT": -1.0, "BBBUSDT": -1.2, "CCCUSDT": -1.4,
               "DDDUSDT": -1.6, "EEEUSDT": -1.8}

_CORRIDAS: Dict[str, Dict[str, Any]] = {}
_TMP: List[Path] = []


def _limpiar() -> None:
    for path in _TMP:
        shutil.rmtree(path, ignore_errors=True)


atexit.register(_limpiar)


def _leer_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _puerto_cerrado(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return False
    except OSError:
        return True


def _finales_por_oid(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Ultima fila persistida por observacion (el estado final)."""
    finales: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if row.get("kind") == "resultado_operativo":
            finales[str(row.get("observation_id"))] = row
    return finales


def _ejecutar_cli(
    moves: Dict[str, float], *,
    funding_source: Optional[str] = None,
    funding_method: Optional[str] = None,
    funding_wait_seconds: Optional[float] = None,
    funding_rows_fn=None,
) -> Dict[str, Any]:
    """Ejecuta el CLI productivo con proveedores loopback y reloj manual."""
    tmp = Path(tempfile.mkdtemp(prefix="replay-offline-"))
    _TMP.append(tmp)
    run = tr.PilotRun(
        tmp,
        universe=tr.UNIVERSE,
        duration_s=300,      # captura 300 s
        settle_s=4200,       # settle 4200 s: cubre el horizonte de 60 min
        selection_s=300,
        max_symbols=5,
        cycle_s=300,
        horizons=tr.HORIZONS,
        max_http_attempts=2000,
        moves=moves,
        funding_source=funding_source,
        funding_method=funding_method,
        funding_wait_seconds=funding_wait_seconds,
        funding_wait_max_queries=3 if funding_wait_seconds else None,
        funding_rows_fn=funding_rows_fn,
    )
    e0 = tr.T0 + tr.MINUTE
    seed = list(range(e0 - 62_000, e0 + 1, 1_000))
    try:
        run.wait_ready(expected_followed=5)
        run.step(e0,
                 depth_symbols=tr.UNIVERSE,
                 trade_events={s: seed for s in tr.UNIVERSE},
                 evaluate=True, expected_obs=5)
        capture_end = run.status()["capture_end_ms"]
        run.advance(capture_end)
        assert run.status()["phase"] == "settle", run.status()
        # Instante en el que la trayectoria del horizonte ya esta disponible.
        run.advance(e0 + 3_600_000 + tr.MINUTE * 2)
        op_path = run.out_dir / "resultado_operativo.jsonl"
        deadline = time.monotonic() + 60
        ops: List[Dict[str, Any]] = []
        while time.monotonic() < deadline:
            if op_path.exists():
                ops = [r for r in _leer_jsonl(op_path)
                       if r.get("kind") == "resultado_operativo"]
            if len(ops) >= 5:
                break
            if run.proc.poll() is not None:
                break
            time.sleep(0.02)
        if funding_wait_seconds:
            # La espera contable (metodo A) abre tras el settle: se avanza el
            # reloj hasta su fin para que la contabilidad diferida se aplique.
            settle_end = int(run.status()["settle_end_ms"])
            run.advance(settle_end)
            run.advance(settle_end + int(funding_wait_seconds * 1000) + 1000)
            run.wait_exit(timeout=120)
        else:
            run.stop(timeout=120)
        return {
            "run": run,
            "out_dir": run.out_dir,
            "http_port": run.http_port,
            "e0": e0,
            "ops": ops,
        }
    except BaseException:
        run.shutdown()
        raise


def _replay(run_dir: Path, report_path: Path):
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "research_operativo_replay.py"),
         "--run-dir", str(run_dir), "--out", str(report_path)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    informe = None
    if report_path.exists():
        informe = json.loads(report_path.read_text(encoding="utf-8"))
    # Evidencia opcional: si se indica un directorio, el informe replay se
    # publica ahi (copia integra del generado).
    destino = os.environ.get("PILOT_REPLAY_EVIDENCE_DIR")
    if destino and report_path.exists():
        destino_path = Path(destino)
        destino_path.mkdir(parents=True, exist_ok=True)
        shutil.copy2(report_path, destino_path / report_path.name)
    return proc, informe


# ---------------------------------------------------------------------------
# 1) Ejecucion real con cuerpos persistidos y replay equivalente (LONG/SHORT)
# ---------------------------------------------------------------------------

def test_cuerpos_persistidos_y_replay_equivalente() -> None:
    """LONG y SHORT: persistencia del cuerpo, vinculo y equivalencia replay."""
    for etiqueta, moves, direccion in (
            ("long", MOVES_LONG, "LONG"),
            ("short", MOVES_SHORT, "SHORT")):
        datos = _ejecutar_cli(moves)
        run = datos["run"]
        out_dir = datos["out_dir"]
        try:
            # --- 1. El cuerpo real recibido queda persistido ---------------
            consultas_path = out_dir / "consultas_klines.jsonl"
            assert consultas_path.exists(), "no se persistieron los cuerpos"
            consultas = [r for r in _leer_jsonl(consultas_path)
                         if r.get("kind") == "consulta_klines_trayectoria"]
            assert len(consultas) >= 5, consultas

            observaciones = {r["observation_id"]: r for r in
                             _leer_jsonl(out_dir / "observaciones.jsonl")
                             if r.get("kind") == "observacion"}
            manifiesto = json.loads(
                (out_dir / "manifiesto.json").read_text(encoding="utf-8"))
            ledger = [r for r in _leer_jsonl(out_dir / "http_requests.jsonl")]
            ledger_por_sha = {r.get("response_sha256"): r for r in ledger
                              if r.get("response_sha256")}

            for fila in consultas:
                cuerpo = fila["cuerpo"]
                # Cuerpo y hash coinciden.
                sha = hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()
                assert sha == fila["cuerpo_sha256"], fila
                assert fila["cuerpo_bytes"] == len(cuerpo.encode("utf-8")), fila
                # Vinculo con la observacion que uso esos datos.
                oid = fila["observation_id"]
                assert oid in observaciones, fila
                assert fila["observaciones"] == [oid], fila
                assert fila["symbol"] == observaciones[oid]["symbol"], fila
                # Identidad de corrida, intervalo, parametros e instantes.
                assert fila["run_id"] == manifiesto["run_id"], fila
                assert fila["interval"] == "1m", fila
                assert set(fila["params"]) == {
                    "symbol", "interval", "startTime", "endTime", "limit"}, fila
                assert fila["params"]["symbol"] == fila["symbol"], fila
                assert fila["params"]["limit"] == 63, fila
                assert fila["solicitado_ms"] is not None, fila
                assert fila["adquirido_ms"] is not None, fila
                assert fila["http_status"] == 200, fila
                # El hash esta en el ledger HTTP: mismo cuerpo, misma peticion.
                entrada_ledger = ledger_por_sha.get(sha)
                assert entrada_ledger is not None, fila
                assert entrada_ledger["params"]["startTime"] == \
                    fila["params"]["startTime"], fila
                # El cuerpo es la respuesta REAL del proveedor simulado.
                filas = json.loads(cuerpo)
                assert len(filas) == fila["filas"], fila
                primera = filas[0]
                precio = tr.kline_price(fila["symbol"], int(primera[0]))
                assert abs(float(primera[1]) - precio) < 1e-8, fila

            # --- 2. La ejecucion produjo entrada y salida ------------------
            ops = [r for r in _leer_jsonl(out_dir / "resultado_operativo.jsonl")
                   if r.get("kind") == "resultado_operativo"]
            admitidas = [r for r in ops if r.get("decision") == "ENTRADA_EJECUTADA"]
            rechazadas = [r for r in ops
                          if r.get("decision") == "RECHAZADA_CAPACIDAD"]
            assert len(admitidas) == 1, ops
            assert len(rechazadas) == len(ops) - 1, ops
            admitida = admitidas[0]
            assert admitida["direction"] == direccion, admitida
            assert admitida["entry_ms"] == datos["e0"] + tr.MINUTE, admitida
            assert admitida["exit_ms"] == datos["e0"] + 3_600_000 + tr.MINUTE, \
                admitida
            assert admitida["exit_executed"] is True, admitida
            assert admitida["exit_reason"] == "horizon", admitida
            assert admitida["qty"] > 0, admitida
            assert admitida["fees"] > 0, admitida
            # Capacidad y orden determinista: la primera alfabetica entra.
            assert admitida["symbol"] == "AAAUSDT", admitida
            # Funding desconocido (sin calendario): UNKNOWN, nunca cero.
            assert admitida["funding"] is None, admitida
            assert admitida["neto_estado"] == "CONDICIONADO_SIN_FUNDING_COMPLETO", \
                admitida

            # --- 3. Se detienen los proveedores ---------------------------
            run.shutdown()
            assert _puerto_cerrado(datos["http_port"]), "el proveedor sigue vivo"

            # --- 4. Replay offline con lo YA guardado ----------------------
            report = out_dir.parent / ("replay_%s.json" % etiqueta)
            proc, informe = _replay(out_dir, report)
            assert informe is not None, (proc.returncode, proc.stdout, proc.stderr)
            assert proc.returncode == 0, (proc.stdout, proc.stderr, informe)
            assert informe["veredicto"]["estado"] == "EQUIVALENTE", informe
            assert informe["veredicto"]["coincidentes"] >= 5, informe
            assert informe["veredicto"]["diferentes"] == 0, informe
            assert informe["veredicto"]["limitadas"] == 0, informe
            assert informe["fuentes"]["consultas_klines"] >= 5, informe

            # --- 5. Contraste explicito ejecucion/replay ------------------
            comparacion = {c["observation_id"]: c
                           for c in informe["observaciones"]}
            assert admitida["observation_id"] in comparacion, comparacion
            assert comparacion[admitida["observation_id"]]["estado"] == \
                "coincidente", comparacion[admitida["observation_id"]]
            economia = informe["economia"]
            assert economia["operaciones_ejecucion"] == 1, economia
            assert economia["operaciones_replay"] == 1, economia
            assert economia["neto_completo_ejecucion"] == economia[
                "neto_completo_replay"], economia
            assert economia["neto_conditionado_ejecucion"] == economia[
                "neto_conditionado_replay"], economia
        finally:
            run.shutdown()


# ---------------------------------------------------------------------------
# 2) Replay con funding observado (metodo A) persistido
# ---------------------------------------------------------------------------

def test_replay_offline_con_funding_observado() -> None:
    """El funding observado (metodo A) se reconstruye desde lo persistido."""
    e0 = tr.T0 + tr.MINUTE

    def funding_rows(symbol, start, end, now_ms):
        # Liquidaciones regulares cada 8 h que cubren la exposicion: una
        # dentro y otra posterior a la salida.
        base = tr.T0
        return [
            {"symbol": symbol, "fundingTime": base - 8 * 3_600_000,
             "fundingRate": "0.0001", "markPrice": str(tr.base_price(symbol))},
            {"symbol": symbol, "fundingTime": base,
             "fundingRate": "0.0002", "markPrice": str(tr.base_price(symbol))},
            {"symbol": symbol, "fundingTime": base + 8 * 3_600_000,
             "fundingRate": "0.0003", "markPrice": str(tr.base_price(symbol))},
        ]

    datos = _ejecutar_cli(MOVES_LONG,
                          funding_source="exchange",
                          funding_method="observed-settlements",
                          funding_wait_seconds=60.0,
                          funding_rows_fn=funding_rows)
    run = datos["run"]
    out_dir = datos["out_dir"]
    try:
        # La adquisicion diferida de funding queda persistida con su calendario.
        log = [r for r in _leer_jsonl(out_dir / "funding_adquisicion.jsonl")
               if r.get("kind") == "funding_adquisicion"]
        assert log, "no se persistio la adquisicion de funding"
        assert any(r.get("estado") == "OK" and isinstance(r.get("calendar"), dict)
                   for r in log), log

        ops = [r for r in _leer_jsonl(out_dir / "resultado_operativo.jsonl")
               if r.get("kind") == "resultado_operativo"]
        finales = _finales_por_oid(ops)
        admitidas = [r for r in finales.values()
                     if r.get("decision") == "ENTRADA_EJECUTADA"]
        assert len(admitidas) == 1, finales
        admitida = admitidas[0]
        # El estado final del funding queda acreditado o UNKNOWN: nunca cero.
        assert admitida["contabilidad_funding_estado"] in (
            "ACREDITADA", "PENDIENTE", "UNKNOWN"), admitida
        if admitida["contabilidad_funding_estado"] == "ACREDITADA":
            assert admitida["funding"] is not None, admitida
            assert admitida["neto_estado"] == "COMPLETO", admitida
        else:
            assert admitida["funding"] is None, admitida

        run.shutdown()
        report = out_dir.parent / "replay_funding.json"
        proc, informe = _replay(out_dir, report)
        assert informe is not None, (proc.returncode, proc.stdout, proc.stderr)
        assert proc.returncode == 0, (proc.stdout, proc.stderr, informe)
        assert informe["veredicto"]["estado"] == "EQUIVALENTE", informe
        assert informe["veredicto"]["diferentes"] == 0, informe
        # El estado del funding/neto replayado es el mismo que el ejecutado.
        replay_oid = [c for c in informe["observaciones"]
                      if c["observation_id"] == admitidas[0]["observation_id"]]
        assert replay_oid and replay_oid[0]["estado"] == "coincidente", informe
        assert informe["economia"]["neto_completo_ejecucion"] == \
            informe["economia"]["neto_completo_replay"], informe
    finally:
        run.shutdown()


# ---------------------------------------------------------------------------
# 3) Datos ausentes o corruptos: limitacion explicita, nunca resultado
# ---------------------------------------------------------------------------

def test_replay_offline_datos_ausentes_o_corruptos() -> None:
    """Fichero ausente o cuerpo corrupto: limitacion explicita, sin inventar."""
    datos = _ejecutar_cli(MOVES_LONG)
    run = datos["run"]
    out_dir = datos["out_dir"]
    try:
        run.shutdown()

        # (a) Fichero de cuerpos ausente.
        copia = Path(tempfile.mkdtemp(prefix="replay-ausente-"))
        _TMP.append(copia)
        destino = copia / "run"
        shutil.copytree(out_dir, destino)
        (destino / "consultas_klines.jsonl").unlink()
        proc, informe = _replay(destino, copia / "replay_datos_ausentes.json")
        assert proc.returncode == 3, (proc.stdout, proc.stderr)
        assert informe is not None, proc.stderr
        assert informe["veredicto"]["estado"] == "LIMITACION", informe
        motivos = {l["motivo"] for l in informe["limitaciones"]}
        assert "consultas_klines_ausentes" in motivos, informe
        # Sin trayectorias no hay operaciones: no se inventa ninguna.
        assert informe["economia"]["operaciones_replay"] == 0, informe

        # (b) Cuerpo corrupto: el hash ya no coincide.
        copia2 = Path(tempfile.mkdtemp(prefix="replay-corrupto-"))
        _TMP.append(copia2)
        destino2 = copia2 / "run"
        shutil.copytree(out_dir, destino2)
        path = destino2 / "consultas_klines.jsonl"
        filas = [json.loads(line) for line in
                 path.read_text(encoding="utf-8").splitlines() if line.strip()]
        filas[0]["cuerpo"] = filas[0]["cuerpo"].replace("1", "2", 1)
        path.write_text(
            "".join(json.dumps(f, ensure_ascii=False, sort_keys=True) + "\n"
                    for f in filas), encoding="utf-8", newline="\n")
        proc, informe = _replay(destino2, copia2 / "replay_datos_corruptos.json")
        assert proc.returncode == 3, (proc.stdout, proc.stderr)
        assert informe is not None, proc.stderr
        assert informe["veredicto"]["estado"] == "LIMITACION", informe
        motivos = {l["motivo"] for l in informe["limitaciones"]}
        assert "consulta_corrupta_hash" in motivos, informe
        # La limitacion es reconstructiva: no se publica un resultado inventado
        # para la observacion cuyo cuerpo no es verificable.
        assert informe["veredicto"]["limitaciones_reconstructivas"] >= 1, informe
        limitadas = [c for c in informe["observaciones"]
                     if c["estado"] == "limitada"]
        assert limitadas, informe
    finally:
        run.shutdown()
