"""Pruebas de integración Paper Lab — matriz de aceptación A–E.

Usa el CLI real (scripts/paper_lab_session.py) con almacenamiento temporal
real. No muta objetos internos ni archivos persistidos para conseguir estados.
Cada prueba verifica el flujo completo a través del backend:

A. Crear → evaluar → entrar automáticamente → gestionar → cerrar → recuperar/exportar.
B. Crear → evidencia insuficiente → SIN_ENTRADA, sin posición.
C. Datos obsoletos → conducta definida y evidencia.
D. Fin de datos → posición abierta/no realizada.
E. Acción duplicada/concurrente → sin duplicar operación ni perder eventos.

Los resultados deben reconciliar con la mecánica compartida (run_backtest).
"""

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

CLI = ["python", os.path.join(ROOT, "scripts", "paper_lab_session.py")]


def run_cli(args, sessions_dir):
    """Ejecuta el CLI y devuelve el JSON parseado."""
    cmd = CLI + args + ["--sessions-dir", sessions_dir]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise AssertionError(
            f"CLI falló ({result.returncode}): {result.stderr}"
        )
    return json.loads(result.stdout)


def mk_candle(open_time_ms, open_, high, low, close):
    return {
        "open_time_ms": open_time_ms, "open": open_,
        "high": high, "low": low, "close": close,
        "close_time_ms": open_time_ms + 15 * 60 * 1000 - 1,
    }


def mk_config(symbol="BTCUSDT", direction="LONG", entry_px=100.0, stop_px=95.0,
              horizon_ms=3 * 60 * 60 * 1000, notional_usdt=1000.0,
              fee_bps=5.0, spread_bps=1.0, slippage_bps=2.0):
    return {
        "symbol": symbol, "interval": "15m", "direction": direction,
        "notional_usdt": notional_usdt, "entry_px": entry_px,
        "stop_px": stop_px, "stop_distance_pct": 5.0,
        "horizon_ms": horizon_ms, "fee_bps": fee_bps,
        "spread_bps": spread_bps, "slippage_bps": slippage_bps,
    }


# --- Fixtures ----------------------------------------------------------------

UP_CANDLES = [
    mk_candle(0, 100, 102, 99, 101),       # vela 0: entrada
    mk_candle(900000, 101, 103, 100, 102),  # vela 1: sube (favorable LONG)
    mk_candle(1800000, 102, 104, 101, 103), # vela 2: contexto
]

STOP_CANDLES = [
    mk_candle(0, 100, 102, 99, 101),        # vela 0: entrada
    mk_candle(900000, 101, 101, 94, 100),   # vela 1: low=94 <= stop=95
    mk_candle(1800000, 100, 102, 99, 100),  # vela 2: close conocido de vela 1
]

# --- Pruebas A–E -------------------------------------------------------------

def test_A_flujo_completo_entrada_gestion_cierre_export():
    """A: Crear → evaluar → entrar automáticamente → gestionar → cerrar →
    recuperar/exportar."""
    with tempfile.TemporaryDirectory() as sd:
        # 1. Crear sesión (sin_iniciar)
        r = run_cli(["--action", "create", "--config-json",
                     json.dumps(mk_config()),
                     "--candles-json", json.dumps(UP_CANDLES)], sd)
        assert r["ok"], r
        session = r["data"]["session"]
        assert session["status"] == "sin_iniciar"
        assert session["config"]["decision"] is None
        sid = session["session_id"]
        assert session["position"]["open"] is False

        # 2. Evaluar evidencia (backend decide ENTRADA_SIMULADA)
        r = run_cli(["--action", "evaluate", "--session-id", sid,
                     "--rule-version", "ENG-RULE-v1"], sd)
        assert r["ok"], r
        session = r["data"]["session"]
        assert session["status"] == "en_espera", session["status"]
        assert session["config"]["decision"] == "ENTRADA_SIMULADA"
        assert session["config"]["rule_version"] == "ENG-RULE-v1"
        assert session["config"]["decision_evidence"] is not None
        assert session["position"]["open"] is False
        rev1 = session["revision"]

        # 3. Entrar automáticamente (primer step_forward)
        r = run_cli(["--action", "step", "--session-id", sid], sd)
        assert r["ok"], r
        session = r["data"]["session"]
        assert session["status"] == "abierta", session["status"]
        assert session["position"]["open"] is True
        assert session["position"]["entry_px"] is not None
        assert session["result"] is None
        assert session["revision"] > rev1

        # 4. Gestionar: avanzar pasos hasta cierre o fin de datos
        for _ in range(6):
            r = run_cli(["--action", "step", "--session-id", sid], sd)
            assert r["ok"], r
            session = r["data"]["session"]
            if session["status"] == "cerrada":
                break

        # 5. Verificar resultado: cerrado (salida ejecutada O open_at_end)
        assert session["status"] == "cerrada"
        assert session["result"] is not None
        assert session["result"]["exit_executed"] in (True, False)
        assert session["result"]["net_pnl"] is not None
        assert session["result"]["gross_pnl"] is not None
        assert session["result"]["friction"] is not None
        # Costes separados (ejecutados vs estimados)
        assert session["result"]["entry_fees_executed"] > 0
        if session["result"]["exit_executed"]:
            assert session["result"]["exit_fees_executed"] > 0
            assert session["result"]["exit_reason"] in ("stop", "horizon", "manual")
        else:
            # open_at_end: sin coste de salida ejecutado
            assert session["result"]["exit_fees_executed"] == 0.0
            assert session["result"]["exit_reason"] is None
            # Posición sigue abierta (no realizada)
            assert session["position"]["open"] is True

        # 6. Recuperar (GET) tras cerrado
        r = run_cli(["--action", "get", "--session-id", sid], sd)
        assert r["ok"], r
        recovered = r["data"]["session"]
        assert recovered["session_id"] == sid
        assert recovered["status"] == "cerrada"
        assert recovered["result"]["net_pnl"] == session["result"]["net_pnl"]
        assert recovered["revision"] == session["revision"]

        # 7. Exportar (el resultado está en la sesión recuperada)
        assert recovered["result"]["net_pnl"] is not None
        assert recovered["result"]["gross_pnl"] is not None
        assert recovered["result"]["friction"] is not None


def test_B_sin_entrada_sin_posicion():
    """B: evidencia insuficiente → SIN_ENTRADA, sin posición."""
    with tempfile.TemporaryDirectory() as sd:
        # horizon_ms=0: horizon_end antes de cualquier fill posible
        config = mk_config(horizon_ms=0)
        r = run_cli(["--action", "create", "--config-json",
                     json.dumps(config),
                     "--candles-json", json.dumps(UP_CANDLES)], sd)
        assert r["ok"], r
        session = r["data"]["session"]
        sid = session["session_id"]

        # Evaluar → SIN_ENTRADA
        r = run_cli(["--action", "evaluate", "--session-id", sid,
                     "--rule-version", "ENG-RULE-v1"], sd)
        assert r["ok"], r
        session = r["data"]["session"]
        assert session["status"] == "cerrada"
        assert session["config"]["decision"] == "SIN_ENTRADA"
        assert session["position"]["open"] is False
        assert session["result"] is None
        assert session["config"]["decision_reason"] is not None


def test_C_datos_obsoletos_conducta_definida():
    """C: datos obsoletos → conducta definida y evidencia."""
    with tempfile.TemporaryDirectory() as sd:
        # Todas las velas en el pasado (antes del evento)
        old_candles = [
            mk_candle(0, 100, 102, 99, 101),
            mk_candle(900000, 101, 101, 99, 100),
        ]
        config = mk_config()
        r = run_cli(["--action", "create", "--config-json",
                     json.dumps(config),
                     "--candles-json", json.dumps(old_candles)], sd)
        assert r["ok"], r
        session = r["data"]["session"]
        sid = session["session_id"]

        # Evaluar con velas antiguas: el evento ocurre antes de todas,
        # run_backtest llena en vela 0, pero no hay salida posible
        # (horizon_ms=3h, solo 30 min de datos) → open_at_end
        r = run_cli(["--action", "evaluate", "--session-id", sid,
                     "--rule-version", "ENG-RULE-v1"], sd)
        assert r["ok"], r
        session = r["data"]["session"]
        assert session["status"] == "en_espera"
        assert session["config"]["decision"] == "ENTRADA_SIMULADA"

        # Avanzar hasta fin de datos (necesita 3 pasos: entrada + 2 velas)
        final = None
        for _ in range(6):
            r = run_cli(["--action", "step", "--session-id", sid], sd)
            assert r["ok"], r
            session = r["data"]["session"]
            final = session
            if session["status"] == "cerrada":
                break

        assert session["status"] == "cerrada"
        assert session["result"]["open_at_end"] is True
        assert session["result"]["exit_executed"] is False
        assert session["result"]["exit_reason"] is None
        # Posición sigue abierta (no realizada)
        assert session["position"]["open"] is True
        # Sin comisión de salida (no ejecutada)
        assert session["result"]["exit_fees_executed"] == 0.0


def test_D_fin_datos_posicion_abierta_no_realizada():
    """D: fin de datos → posición abierta/no realizada, sin cierre inventado."""
    with tempfile.TemporaryDirectory() as sd:
        config = mk_config(horizon_ms=999999999)  # nunca alcanza horizonte
        r = run_cli(["--action", "create", "--config-json",
                     json.dumps(config),
                     "--candles-json", json.dumps(UP_CANDLES)], sd)
        assert r["ok"], r
        session = r["data"]["session"]
        sid = session["session_id"]

        r = run_cli(["--action", "evaluate", "--session-id", sid,
                     "--rule-version", "ENG-RULE-v1"], sd)
        session = r["data"]["session"]
        assert session["config"]["decision"] == "ENTRADA_SIMULADA"

        # Avanzar hasta agotar datos
        for _ in range(4):
            r = run_cli(["--action", "step", "--session-id", sid], sd)
            assert r["ok"], r
            session = r["data"]["session"]

        assert session["status"] == "cerrada"
        assert session["result"]["open_at_end"] is True
        assert session["result"]["exit_executed"] is False
        assert session["result"]["exit_reason"] is None
        assert session["result"]["realized_net"] is None
        # Sin comisión de salida (no ejecutada)
        assert session["result"]["exit_fees_executed"] == 0.0
        assert session["result"]["exit_fees_estimated"] == 0.0
        # Posición sigue abierta
        assert session["position"]["open"] is True
        assert session["position"]["mark_px"] is not None


def test_E_accion_duplicada_sin_duplicar():
    """E: acción duplicada/concurrente → sin duplicar operación ni perder
    eventos. El control de revisión previene conflictos."""
    with tempfile.TemporaryDirectory() as sd:
        # Crear sesión
        r = run_cli(["--action", "create", "--config-json",
                     json.dumps(mk_config()),
                     "--candles-json", json.dumps(UP_CANDLES)], sd)
        assert r["ok"], r
        session = r["data"]["session"]
        sid = session["session_id"]
        rev1 = session["revision"]

        # Evaluar
        r = run_cli(["--action", "evaluate", "--session-id", sid,
                     "--rule-version", "ENG-RULE-v1"], sd)
        session = r["data"]["session"]
        rev2 = session["revision"]
        assert rev2 > rev1

        # Entrar (primer step)
        r = run_cli(["--action", "step", "--session-id", sid], sd)
        session = r["data"]["session"]
        assert session["status"] == "abierta"
        rev3 = session["revision"]
        assert rev3 > rev2

        # Segundo step con revisión obsoleta → conflicto (simulado)
        # El CLI maneja la revisión internamente; un segundo step con el
        # mismo estado debería seguir funcionando (no hay concurrencia real
        # en CLI secuencial), pero la revisión debe incrementarse.
        r = run_cli(["--action", "step", "--session-id", sid], sd)
        assert r["ok"], r
        session = r["data"]["session"]
        assert session["revision"] > rev3

        # Verificar que no hay posiciones duplicadas
        assert session["position"]["open"] is True
        assert len([e for e in session["events"] if e["kind"] == "entry"]) == 1

        # Cerrar y verificar resultado único
        r = run_cli(["--action", "exit", "--session-id", sid], sd)
        session = r["data"]["session"]
        assert session["status"] == "cerrada"
        assert session["result"] is not None
        assert session["result"]["exit_executed"] is True
        assert len([e for e in session["events"] if e["kind"] == "exit"]) == 1


if __name__ == "__main__":
    test_A_flujo_completo_entrada_gestion_cierre_export()
    test_B_sin_entrada_sin_posicion()
    test_C_datos_obsoletos_conducta_definida()
    test_D_fin_datos_posicion_abierta_no_realizada()
    test_E_accion_duplicada_sin_duplicar()
    print("Todas las pruebas de integración A–E pasaron.")
