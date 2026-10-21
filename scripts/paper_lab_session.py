"""Ejecutor de sesiones Paper Lab (ingeniería) — CLI para el BFF de Next.js.

Orquesta sesiones de ingeniería sobre fixtures: crear, evaluar evidencia,
entrar automáticamente, avanzar paso, salida manual, reiniciar, detener,
listar y recuperar. Llama al motor ``src/microstructure_probe/paper_lab_engine.py``.
No hay Binance, no hay feed vivo, no hay ordenes reales, no hay capital real.

Contrato de seguridad:
- Solo acepta acciones de una lista permitida embebida.
- session_id validado contra traversal/alias antes de tocar el FS.
- Escritura atómica (tmp + os.replace) con control de revisión (optimistic
  locking) para evitar pérdida en carga→modificar→guardar.
- Escritura SOLO en el directorio aislado de sesiones de ingeniería.
- Determinista: mismos inputs -> mismos estados y resultados.
- Nunca acepta estado económico del cliente como autoridad: la decisión
  se obtiene de run_backtest sobre evidencia en T.

Uso (desde la raíz del repo):
  python scripts/paper_lab_session.py --action list
  python scripts/paper_lab_session.py --action create \
      --config-json '{"symbol":"BTCUSDT",...}' --candles-json '...'
  python scripts/paper_lab_session.py --action evaluate --session-id PL-... \
      --hypothesis-id H1-v1 --rule-version rule-v1
  python scripts/paper_lab_session.py --action step --session-id PL-...
  python scripts/paper_lab_session.py --action exit --session-id PL-...
  python scripts/paper_lab_session.py --action get --session-id PL-...
  python scripts/paper_lab_session.py --action restart --session-id PL-...
  python scripts/paper_lab_session.py --action stop --session-id PL-...

Salida: JSON en stdout con claves "ok", "data" o "error".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from microstructure_probe.paper_lab_engine import (  # noqa: E402
    ENGINE_VERSION_PAPER,
    PaperCandle,
    PaperSessionConfig,
    create_session,
    evaluate_session,
    list_sessions,
    load_session,
    manual_exit,
    restart_session,
    save_session,
    session_to_dict,
    step_forward,
    stop_session,
    SessionSaveResult,
)

SESSIONS_DEFAULT = ROOT / "paper-lab-sessions"
ALLOWED_ACTIONS = {
    "list", "create", "evaluate", "get", "step", "exit", "restart", "stop",
}


def _fail(code: str, detail: str) -> Dict[str, Any]:
    return {"ok": False, "error": code, "detail": detail}


def _ok(data: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "data": data}


def _parse_config(raw: str) -> PaperSessionConfig:
    d = json.loads(raw)
    return PaperSessionConfig(
        symbol=str(d["symbol"]), interval=str(d["interval"]),
        direction=str(d["direction"]),
        notional_usdt=float(d["notional_usdt"]),
        entry_px=float(d["entry_px"]), stop_px=float(d["stop_px"]),
        stop_distance_pct=float(d["stop_distance_pct"]),
        horizon_ms=int(d["horizon_ms"]), fee_bps=float(d["fee_bps"]),
        spread_bps=float(d["spread_bps"]),
        slippage_bps=float(d["slippage_bps"]),
        hypothesis_id=d.get("hypothesis_id"),
        hypothesis_version=d.get("hypothesis_version"),
        rule_version=d.get("rule_version"),
        # create NO acepta decision: viene de evaluate.
        decision=None,
        decision_reason=None,
        decision_evidence=None,
    )


def _parse_candles(raw: str) -> List[PaperCandle]:
    rows = json.loads(raw)
    return [PaperCandle(
        open_time_ms=int(r["open_time_ms"]), open=float(r["open"]),
        high=float(r["high"]), low=float(r["low"]),
        close=float(r["close"]),
        close_time_ms=int(r["close_time_ms"]),
    ) for r in rows]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--action", required=True,
                    help="list | create | evaluate | get | step | exit | "
                         "restart | stop")
    ap.add_argument("--session-id", default=None,
                    help="identidad de sesion (validada, sin traversal)")
    ap.add_argument("--config-json", default=None,
                    help="JSON de configuracion de sesion (solo create)")
    ap.add_argument("--candles-json", default=None,
                    help="JSON de velas de la sesion (solo create)")
    ap.add_argument("--context-json", default=None,
                    help="JSON de velas de contexto (solo create)")
    ap.add_argument("--hypothesis-id", default=None,
                    help="identidad de hipotesis experimental (create/evaluate)")
    ap.add_argument("--hypothesis-version", default=None,
                    help="version de hipotesis (create/evaluate)")
    ap.add_argument("--rule-version", default=None,
                    help="version de regla experimental (evaluate)")
    ap.add_argument("--at-ms", default=None, type=int,
                    help="reloj de simulacion T en ms para evaluacion causal (evaluate)")
    ap.add_argument("--request-id", default=None,
                    help="identidad de peticion para idempotencia (guardar/step/exit/restart/stop)")
    ap.add_argument("--sessions-dir", default=None,
                    help="directorio de sesiones (default: ./paper-lab-sessions)")
    args = ap.parse_args(argv)

    if args.action not in ALLOWED_ACTIONS:
        print(json.dumps(_fail("ACTION_NOT_ALLOWED",
                               f"accion no permitida: {args.action}")),
              file=sys.stderr)
        return 2

    sessions_dir = Path(args.sessions_dir) if args.sessions_dir \
        else SESSIONS_DEFAULT

    try:
        if args.action == "list":
            summaries = list_sessions(str(sessions_dir))
            print(json.dumps(_ok({"sessions": summaries}), indent=1))
            return 0

        if args.action == "create":
            if not args.config_json:
                print(json.dumps(_fail("CONFIG_REQUIRED",
                                       "config-json es requerido para crear")),
                      file=sys.stderr)
                return 2
            config = _parse_config(args.config_json)
            candles = _parse_candles(args.candles_json) if args.candles_json \
                else []
            context = _parse_candles(args.context_json) if args.context_json \
                else []
            state = create_session(
                config, candles, context,
                hypothesis_id=args.hypothesis_id,
                hypothesis_version=args.hypothesis_version,
                rule_version=args.rule_version,
            )
            res = save_session(state, str(sessions_dir),
                               request_id=args.request_id)
            if not res.ok:
                print(json.dumps(_fail(res.error_code or "SAVE_FAILED",
                                       res.error_detail or "fallo al guardar")),
                      file=sys.stderr)
                return 3
            state = res.state
            print(json.dumps(_ok({
                "session": session_to_dict(state),
            }), indent=1))
            return 0

        if args.action == "evaluate":
            if not args.session_id:
                print(json.dumps(_fail("SESSION_ID_REQUIRED",
                                       "session-id es requerido para evaluar")),
                      file=sys.stderr)
                return 2
            state = load_session(args.session_id, str(sessions_dir))
            if state is None:
                print(json.dumps(_fail("SESSION_NOT_FOUND",
                                       "sesion no existe")),
                      file=sys.stderr)
                return 4
            rev_before = state.revision
            state = evaluate_session(
                state,
                hypothesis_id=args.hypothesis_id,
                hypothesis_version=args.hypothesis_version,
                rule_version=args.rule_version,
                at_ms=args.at_ms,
            )
            res = save_session(state, str(sessions_dir),
                               expected_revision=rev_before,
                               request_id=args.request_id)
            if not res.ok:
                print(json.dumps(_fail(res.error_code or "SAVE_FAILED",
                                       res.error_detail or "fallo al guardar")),
                      file=sys.stderr)
                return 3
            state = res.state
            if res.idempotent_repeat:
                # Repetición idempotente: no se repiten efectos.
                pass
            print(json.dumps(_ok({
                "session": session_to_dict(state),
                "idempotent_repeat": res.idempotent_repeat,
            }), indent=1))
            return 0

        if not args.session_id:
            print(json.dumps(_fail("SESSION_ID_REQUIRED",
                                   f"session-id es requerido para {args.action}")),
                  file=sys.stderr)
            return 2

        if args.action == "get":
            state = load_session(args.session_id, str(sessions_dir))
            if state is None:
                print(json.dumps(_fail("SESSION_NOT_FOUND",
                                       "sesion no existe")),
                      file=sys.stderr)
                return 4
            print(json.dumps(_ok({"session": session_to_dict(state)}),
                              indent=1))
            return 0

        def _save_with_revision(state: PaperSessionState,
                                expected_rev: int) -> PaperSessionState:
            res = save_session(state, str(sessions_dir),
                               expected_revision=expected_rev,
                               request_id=args.request_id)
            if not res.ok:
                print(json.dumps(_fail(res.error_code or "SAVE_FAILED",
                                       res.error_detail or "fallo al guardar")),
                      file=sys.stderr)
                raise SystemExit(3)
            return res.state

        if args.action == "step":
            state = load_session(args.session_id, str(sessions_dir))
            if state is None:
                print(json.dumps(_fail("SESSION_NOT_FOUND",
                                       "sesion no existe")),
                      file=sys.stderr)
                return 4
            expected_rev = state.revision
            state = step_forward(state)
            state = _save_with_revision(state, expected_rev)
            print(json.dumps(_ok({
                "session": session_to_dict(state),
            }), indent=1))
            return 0

        if args.action == "exit":
            state = load_session(args.session_id, str(sessions_dir))
            if state is None:
                print(json.dumps(_fail("SESSION_NOT_FOUND",
                                       "sesion no existe")),
                      file=sys.stderr)
                return 4
            expected_rev = state.revision
            state = manual_exit(state)
            state = _save_with_revision(state, expected_rev)
            print(json.dumps(_ok({
                "session": session_to_dict(state),
            }), indent=1))
            return 0

        if args.action == "restart":
            state = load_session(args.session_id, str(sessions_dir))
            if state is None:
                print(json.dumps(_fail("SESSION_NOT_FOUND",
                                       "sesion no existe")),
                      file=sys.stderr)
                return 4
            expected_rev = state.revision
            state = restart_session(state)
            state = _save_with_revision(state, expected_rev)
            print(json.dumps(_ok({
                "session": session_to_dict(state),
            }), indent=1))
            return 0

        if args.action == "stop":
            state = load_session(args.session_id, str(sessions_dir))
            if state is None:
                print(json.dumps(_fail("SESSION_NOT_FOUND",
                                       "sesion no existe")),
                      file=sys.stderr)
                return 4
            expected_rev = state.revision
            state = stop_session(state)
            state = _save_with_revision(state, expected_rev)
            print(json.dumps(_ok({
                "session": session_to_dict(state),
            }), indent=1))
            return 0

    except ValueError as exc:
        print(json.dumps(_fail("VALIDATION_ERROR", str(exc))),
              file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001 - surface real failure
        print(json.dumps(_fail("INTERNAL_ERROR", str(exc))),
              file=sys.stderr)
        return 1

    print(json.dumps(_fail("ACTION_UNHANDLED",
                           f"accion no gestionada: {args.action}")),
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
