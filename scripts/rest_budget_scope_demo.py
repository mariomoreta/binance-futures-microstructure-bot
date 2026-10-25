"""Alcance del presupuesto REST upstream — demostracion con transporte LOCAL.

Abre un servidor HTTP en 127.0.0.1 (no conecta a Binance) y lanza procesos
reales del CLI ``scripts/market_explorer.py`` que comparten UNA cache aislada
temporaria. Cada escenario demuestra un hecho del presupuesto:

  A. Dos procesos concurrentes comparten limite=2: ambos obtienen su cupo
     (reserva transaccional del ledger compartido) y el upstream solo ve 2
     peticiones.
  A.2. Un tercer intento queda bloqueado ANTES del transporte: el upstream
     recibe 0 peticiones nuevas y el ledger registra ``budget_blocked``
     con requests=0.
  B. Los reintentos tambien consumen presupuesto: el servidor falla el
     primer intento (HTTP 500); el reintento consume el segundo cupo y el
     siguiente intento queda bloqueado antes del transporte.
  C. Los registros persistidos (despues de que cada proceso termino)
     permiten reconstruir el consumo por execution_id.

Uso:
  python scripts/rest_budget_scope_demo.py --json-out <ruta>

Salida: JSON en stdout (y --json-out si se pide).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

KLINE_BODY = json.dumps([[
    1_700_000_000_000 + i * 3_600_000, "1.0", "2.0", "0.5", "1.5", "10.0",
    1_700_000_000_000 + i * 3_600_000 + 3_599_999, "1000.0", 50, "5.0",
    "500.0", "0"]
    for i in range(2)])


class _BudgetScopeHTTPServer(ThreadingHTTPServer):
    """Servidor local de velas para pruebas del presupuesto (loopback only)."""

    allow_reuse_address = True

    def __init__(self, fail_first_request: bool = False) -> None:
        self.hits_lock = threading.Lock()
        self.hits: List[int] = []  # timestamp ms por request recibida
        self.fail_first = fail_first_request
        super().__init__(("127.0.0.1", 0), _BudgetScopeHandler)


class _BudgetScopeHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (interfaz del stdlib)
        server: _BudgetScopeHTTPServer = self.server  # type: ignore[assignment]
        with server.hits_lock:
            server.hits.append(int(time.time() * 1000))
            index = len(server.hits)
            should_fail = server.fail_first and index == 1
        body = KLINE_BODY.encode("utf-8")
        if should_fail:
            body = b'["internal error"]'
            self.send_response(500)
        else:
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return  # silencio: la evidencia queda en hits y en el ledger


def _start_server(fail_first_request: bool = False) -> _BudgetScopeHTTPServer:
    server = _BudgetScopeHTTPServer(fail_first_request)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _run_cli_bg(cache_db: Path, execution_id: str, api_base: str,
                max_upstream: int = 2) -> subprocess.Popen:
    """Proceso Python CLI real lanzado en background (como los del BFF)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "market_explorer.py"),
         "--action", "series",
         "--symbol", "DEMOUSDT",
         "--interval", "1h",
         "--bars", "60",
         "--pages", "1",
         "--page-limit", "300",
         "--max-upstream", str(max_upstream),
         "--execution-id", execution_id,
         "--api-base", api_base,
         "--cache-db", str(cache_db),
         "--history-db", str(cache_db.parent / "no-canonical-history.db")],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding="utf-8", env=env,
    )


def _wait_cli(proc: subprocess.Popen, timeout: float = 90.0
              ) -> Dict[str, Any]:
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        return {"execution_id": None, "exit_code": proc.returncode,
                "output": {"ok": False, "timeout": True}}
    try:
        payload = json.loads((out or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        payload = {"ok": False, "parse_error": (out or "")[-400:],
                   "stderr": (err or "")[-400:], "exit_code": proc.returncode}
    return {"exit_code": proc.returncode, "output": payload}


def _run_cli(cache_db: Path, execution_id: str, api_base: str,
             max_upstream: int = 2,
             timeout: float = 90.0) -> Dict[str, Any]:
    """La misma linea del BFF: un proceso CLI por peticion."""
    proc = _run_cli_bg(cache_db, execution_id, api_base, max_upstream)
    result = _wait_cli(proc, timeout)
    result["execution_id"] = execution_id
    return result


def _ledger_rows(cache_db: Path, execution_id: Optional[str] = None
                 ) -> List[Dict[str, Any]]:
    from microstructure_probe.market_cache import MarketCache

    cache = MarketCache(cache_db)
    cache.init_db()
    if execution_id is not None:
        return cache.fetch_rows_by_execution(execution_id)
    return cache.fetch_ledger(limit=200)


def _window_summary(cache_db: Path) -> Dict[str, Any]:
    from microstructure_probe.market_cache import (
        MAX_FETCH_REQUESTS_PER_WINDOW, ROLLING_WINDOW_MS, MarketCache,
    )

    cache = MarketCache(cache_db)
    cache.init_db()
    return cache.window_usage(window_ms=ROLLING_WINDOW_MS,
                              max_requests=MAX_FETCH_REQUESTS_PER_WINDOW)


def _reconstruction(cache_db: Path, execution_ids: List[str]) -> List[Dict[str, Any]]:
    out = []
    for eid in execution_ids:
        rows = _ledger_rows(cache_db, eid)
        out.append({
            "execution_id": eid,
            "rows": [{
                "id": r["id"],
                "at_ms": r["at_ms"],
                "symbol": r["symbol"],
                "requests": r["requests"],
                "status": r["status"],
                "detail": r["detail"],
            } for r in rows],
            "requests_sum": sum(int(r["requests"] or 0) for r in rows),
        })
    return out


def run_demo() -> Dict[str, Any]:
    started_at_ms = int(time.time() * 1000)

    # ---- Escenario A: limite=2 compartido entre dos procesos concurrentes ----
    with tempfile.TemporaryDirectory(prefix="budget-scope-") as tmp:
        cache_a = Path(tmp) / "shared.db"
        server_a = _start_server(fail_first_request=False)
        api_a = f"http://127.0.0.1:{server_a.server_port}"
        try:
            # Dos procesos CONCURRENTES comparten ventana y ledger.
            bg_p1 = _run_cli_bg(cache_a, "demo-A-P1", api_a)
            bg_p2 = _run_cli_bg(cache_a, "demo-A-P2", api_a)
            p1 = _wait_cli(bg_p1); p1["execution_id"] = "demo-A-P1"
            p2 = _wait_cli(bg_p2); p2["execution_id"] = "demo-A-P2"
            hits_a1 = list(server_a.hits)
            # Tercer intento: debe quedar bloqueado ANTES del transporte.
            p3 = _run_cli(cache_a, "demo-A-P3", api_a)
        finally:
            server_a.shutdown()
            server_a.server_close()
        scenario_a = {
            "limit": 2,
            "concurrent_processes": True,
            "p1": p1["output"],
            "p2": p2["output"],
            "p3": p3["output"],
            "upstream_hits_p1_p2": len(hits_a1),
            "upstream_hits_total": len(server_a.hits),
            "window_after": _window_summary(cache_a),
            "reconstruction": _reconstruction(
                cache_a, ["demo-A-P1", "demo-A-P2", "demo-A-P3"]),
        }

        # ---- Escenario B: el reintento tambien consume presupuesto ----
        cache_b = Path(tmp) / "retry.db"
        server_b = _start_server(fail_first_request=True)
        api_b = f"http://127.0.0.1:{server_b.server_port}"
        try:
            p4 = _run_cli(cache_b, "demo-B-P4", api_b)
            hits_b1 = len(server_b.hits)
            p5 = _run_cli(cache_b, "demo-B-P5", api_b)
        finally:
            server_b.shutdown()
            server_b.server_close()
        scenario_b = {
            "limit": 2,
            "retry_process": True,
            "p4": p4["output"],
            "upstream_hits_after_retry": hits_b1,
            "p5": p5["output"],
            "upstream_hits_total": len(server_b.hits),
            "window_after": _window_summary(cache_b),
            "reconstruction": _reconstruction(
                cache_b, ["demo-B-P4", "demo-B-P5"]),
        }

    return {
        "what": "presupuesto REST upstream compartido entre procesos"
                " (reserva por intento antes del transporte)",
        "transport": "local: 127.0.0.1 (server HTTP temporario); no se abrio Binance",
        "binance_calls": 0,
        "started_at_ms": started_at_ms,
        "finished_at_ms": int(time.time() * 1000),
        "scenario_a_shared_limit": scenario_a,
        "scenario_b_retry_budget": scenario_b,
        "cli": "scripts/market_explorer.py --action series ... --max-upstream 2"
               " --execution-id ... --api-base http://127.0.0.1:<port>",
        "ledger_table": "data/market-cache/market_cache.db ->"
                        " market_fetch_ledger (execution_id, detail JSON)",
        "notes": [
            "Reserva transaccional BEGIN IMMEDIATE: chequeo+insercion en una"
            " transaccion, de modo que procesos concurrentes no pasan de"
            " limite.",
            "Un intento bloqueado NO consume cupo (fila requests=0) y nunca"
            " abre conexion (upstream_hits no crece).",
            "Filas historicas del ledger sin execution_id quedan NULL"
            " (= UNKNOWN, no se reescriben).",
        ],
    }


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json-out", default=None,
                    help="ruta opcional para guardar el JSON de evidencia")
    args = ap.parse_args(argv)
    report = run_demo()
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
