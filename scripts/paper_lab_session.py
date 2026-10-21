"""Ejecutor de sesiones Paper Lab (ingeniería) — CLI para el BFF de Next.js.

Orquesta sesiones de ingeniería sobre fixtures: crear, avanzar paso,
salida manual, reiniciar, detener, listar y recuperar. Llama al motor
``src/microstructure_probe/paper_lab_engine.py``. No hay Binance, no hay
feed vivo, no hay ordenes reales, no hay capital real.

Contrato de seguridad:
- Solo acepta acciones de una lista permitida embebida. No se aceptan
  rutas, comandos ni código arbitrarios del cliente.
- session_id validado contra traversal/alias antes de tocar el sistema
  de archivos.
- Escritura atómica (tmp + os.replace). Escritura SOLO en el directorio
  aislado de sesiones de ingeniería.
- Determinista: mismos inputs -> mismos estados y resultados.

Uso (desde la raíz del repo):
  python scripts/paper_lab_session.py --action list
  python scripts/paper_lab_session.py --action create --session-id PL-... \
      --config-json '{"symbol":"BTCUSDT",...}'
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
    list_sessions,
    load_session,
    manual_exit,
    restart_session,
    save_session,
    session_to_dict,
    step_forward,
    stop_session,
)

SESSIONS_DEFAULT = ROOT / "paper-lab-sessions"
ALLOWED_ACTIONS = {
    "list", "create", "get", "step", "exit", "restart", "stop",
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
        decision=d.get("decision"),
        decision_reason=d.get("decision_reason"),
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
                    help="list | create | get | step | exit | restart | stop")
    ap.add_argument("--session-id", default=None,
                    help="identidad de sesion (validada, sin traversal)")
    ap.add_argument("--config-json", default=None,
                    help="JSON de configuracion de sesion (solo create)")
    ap.add_argument("--candles-json", default=None,
                    help="JSON de velas de la sesion (solo create)")
    ap.add_argument("--context-json", default=None,
                    help="JSON de velas de contexto (solo create)")
    ap.add_argument("--hypothesis-id", default=None,
                    help="identidad de hipotesis experimental (solo create)")
    ap.add_argument("--hypothesis-version", default=None,
                    help="version de hipotesis (solo create)")
    ap.add_argument("--decision", default=None,
                    help="VIGILANDO | SIN_ENTRADA | DESCARTADO | ENTRADA_SIMULADA")
    ap.add_argument("--decision-reason", default=None,
                    help="motivo de la decision")
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
                decision=args.decision,
                decision_reason=args.decision_reason,
            )
            save_session(state, str(sessions_dir))
            print(json.dumps(_ok({
                "session": session_to_dict(state),
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

        if args.action == "step":
            state = load_session(args.session_id, str(sessions_dir))
            if state is None:
                print(json.dumps(_fail("SESSION_NOT_FOUND",
                                       "sesion no existe")),
                      file=sys.stderr)
                return 4
            state = step_forward(state)
            save_session(state, str(sessions_dir))
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
            state = manual_exit(state)
            save_session(state, str(sessions_dir))
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
            state = restart_session(state)
            save_session(state, str(sessions_dir))
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
            state = stop_session(state)
            save_session(state, str(sessions_dir))
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
