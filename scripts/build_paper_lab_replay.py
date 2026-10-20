"""Construye el artefacto versionado del primer replay visible de Paper Lab.

La fuente es exclusivamente el paquete EVAL-CENSUS-V2 versionado y las
trazas regeneradas por ``reconstruct_replay_traces.py``. No abre bases de
datos, no consulta Binance y falla cerrado ante hashes o contratos inválidos.

Regla de selección (definida sin observar P&L): primera operación por
``(event_time_ms, event_id)`` que sea 1x, no-baseline, H1/H3 con respaldo
directo único del censo, realizada por stop/horizon, sin marca abierta y con
contabilidad de funding completa en su celda. H2 se excluye porque su evento
es una confirmación derivada y esta primera entrega exige respaldo directo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DEFAULT = ROOT / "docs" / "evidence" / "eval-census-v2-package"
OUT_DEFAULT = ROOT / "frontend" / "src" / "artifacts" / "paper-lab-replay-v1.json"
ENGINE_VERSION = "backtest-offline/v4.2"
ARTIFACT_VERSION = "PAPER-LAB-REPLAY-V1"
TOLERANCE = 1e-9

COMBOS = {
    ("BTCUSDT", "15m"): ("eval15_btc", "census_btc15_detections.jsonl"),
    ("ETHUSDT", "15m"): ("eval15_ethsol", "census_ethsol15_detections.jsonl"),
    ("SOLUSDT", "15m"): ("eval15_ethsol", "census_ethsol15_detections.jsonl"),
    ("BTCUSDT", "1h"): ("eval1h_trio", "census_1h_detections.jsonl"),
    ("ETHUSDT", "1h"): ("eval1h_trio", "census_1h_detections.jsonl"),
    ("SOLUSDT", "1h"): ("eval1h_trio", "census_1h_detections.jsonl"),
}
DIRECT_DEFINITIONS = {
    "H1": {"MOMENTUM_ACCELERATION_UP", "EXTENDED_GAINER"},
    "H3": {"MOMENTUM_ACCELERATION_DOWN", "EXTENDED_LOSER"},
}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _source_label(path: Path) -> str:
    try:
        return _relative(path)
    except ValueError:
        return f"generated-traces/{path.name}"


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _load_traces(traces_dir: Path) -> list[dict]:
    manifest_path = traces_dir / "reconstruction_manifest.json"
    manifest = _load(manifest_path)
    if manifest.get("veredicto") != "COMPLETO":
        raise ValueError("reconstruction_manifest no es COMPLETO")
    if manifest.get("cobertura", {}).get("celdas_fail") != 0:
        raise ValueError("reconstruction_manifest contiene celdas fallidas")
    expected_hashes = manifest.get("trades_sha256", {})
    trades = []
    for symbol, interval in COMBOS:
        name = f"trades_{symbol}_{interval}.json"
        path = traces_dir / name
        if not path.exists() or expected_hashes.get(name) != _sha256(path):
            raise ValueError(f"traza ausente o hash inválido: {name}")
        document = _load(path)
        if document.get("equivalencia") != "verificada" or not document.get("consumible"):
            raise ValueError(f"traza no consumible: {name}")
        for trade in document.get("trades", []):
            trade = dict(trade)
            if trade.get("escala") != 1.0:
                continue
            trade["_trace_path"] = path
            trades.append(trade)
    if len(trades) != 5255:
        raise ValueError(f"se esperaban 5255 trades 1x; se obtuvieron {len(trades)}")
    return trades


def _combo_paths(package: Path, symbol: str, interval: str) -> dict[str, Path]:
    combo, detections_name = COMBOS[(symbol, interval)]
    base = package / "combos" / combo
    return {
        "events": base / f"events_{symbol}_{interval}.json",
        "candles": base / f"candles_{symbol}_{interval}.json",
        "manifest": base / f"manifest_{symbol}_{interval}.json",
        "selection": base / f"selection_{symbol}_{interval}.json",
        "detections": package / "detections" / detections_name,
        "funding": package / "funding" / f"funding_{symbol}.json",
    }


def _detections(path: Path, symbol: str, interval: str) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("symbol") == symbol and row.get("source_interval") == interval:
                rows.append(row)
    return rows


def _direct_backing(trade: dict, detections: list[dict]) -> list[dict]:
    allowed = DIRECT_DEFINITIONS.get(trade.get("family"), set())
    direction = "up" if trade.get("direction") == "LONG" else "down"
    return [
        row for row in detections
        if row.get("formation_time") == trade.get("event_time_ms")
        and row.get("definition_name") in allowed
        and row.get("direction") == direction
        and not row.get("formation_gap")
        and row.get("entry_time_same_grid") == trade.get("entry_ms")
        and _finite(row.get("available_at"))
        and row["available_at"] <= trade["entry_ms"]
    ]


def _funding_complete(trade: dict, package: Path) -> bool:
    paths = _combo_paths(package, trade["symbol"], trade["res"])
    manifest = _load(paths["manifest"])
    cell = (manifest.get("groups", {}).get(trade["group"], {})
            .get(trade["segmento"], {}).get("1.0", {}))
    quality = cell.get("funding_quality", {})
    return (
        quality.get("unknown_excluded") == 0
        and quality.get("uncovered_ms") == 0
        and quality.get("accounting_complete_trades") == cell.get("n_trades")
    )


def _select(trades: list[dict], package: Path) -> tuple[dict, dict, Counter]:
    exclusions = Counter()
    for trade in sorted(trades, key=lambda row: (row.get("event_time_ms"), row.get("event_id"))):
        reason = None
        if trade.get("escala") != 1.0:
            reason = "not_scale_1x"
        elif trade.get("group") == "baseline":
            reason = "baseline_comparator"
        elif trade.get("family") not in DIRECT_DEFINITIONS:
            reason = "no_direct_h1_h3_backing"
        elif not trade.get("exit_executed") or trade.get("open_at_end"):
            reason = "not_realized"
        elif trade.get("exit_reason") not in {"stop", "horizon"}:
            reason = "unsupported_exit_reason"
        elif not _funding_complete(trade, package):
            reason = "funding_coverage_incomplete"
        if reason:
            exclusions[reason] += 1
            continue
        paths = _combo_paths(package, trade["symbol"], trade["res"])
        backing = _direct_backing(
            trade, _detections(paths["detections"], trade["symbol"], trade["res"])
        )
        if len(backing) != 1:
            exclusions["direct_backing_not_unique"] += 1
            continue
        return trade, backing[0], exclusions
    raise ValueError("ninguna operación cumple la regla de elegibilidad")


def _event_from_inputs(trade: dict, paths: dict[str, Path]) -> dict:
    manifest = _load(paths["manifest"])
    ids = manifest["groups"][trade["group"]]["event_ids"]
    if trade["event_id"] not in ids:
        raise ValueError("event_id elegido ausente del manifiesto")
    try:
        index = int(str(trade["event_id"]).rsplit(":", 1)[1])
    except (ValueError, IndexError) as exc:
        raise ValueError("event_id elegido sin índice técnico") from exc
    events = _load(paths["events"])
    event = events[index]
    for field in ("symbol", "direction", "family", "rules_version", "group", "event_time_ms"):
        if event.get(field) != trade.get(field):
            raise ValueError(f"evento y trade discrepan en {field}")
    return event


def _context_candles(trade: dict, candles: list[dict], count: int) -> list[dict]:
    """Velas reales ANTERIORES al evento, solo como contexto visual.

    Nunca forman parte de la cinta de reproduccion, no entran en posiciones ni
    P&L, y no se rellenan si faltan: se toman exclusivamente velas cerradas del
    mismo paquete, contiguas y terminando en la vela previa a la de formacion.
    """
    if count <= 0:
        return []
    prior = [
        c for c in candles
        if c.get("close_time_ms") is not None and c["close_time_ms"] < trade["event_time_ms"]
    ]
    prior.sort(key=lambda c: c["open_time_ms"])
    window = prior[-count:]
    if window:
        # Contigüidad: sin huecos entre contexto y la primera vela del replay.
        last_close = window[-1]["close_time_ms"]
        if trade["event_time_ms"] - last_close != 1:
            raise ValueError("contexto previo no contiguo con la vela de formacion")
    spread = [
        {k: c[k] for k in ("open_time_ms", "open", "high", "low", "close", "close_time_ms")}
        for c in window
    ]
    return spread


def _window(trade: dict, backing: dict, candles: list[dict], costs: dict,
            context_candles: int = 0) -> dict:
    selected = [
        {k: candle[k] for k in ("open_time_ms", "open", "high", "low", "close", "close_time_ms")}
        for candle in candles
        if trade["event_time_ms"] <= candle["open_time_ms"] < trade["exit_ms"]
    ]
    if not selected or selected[0]["open_time_ms"] != trade["event_time_ms"]:
        raise ValueError("ventana causal sin vela de formación")
    qty = 1000.0 / trade["entry_px"]
    running_mfe = 0.0
    running_mae = 0.0
    direction = trade["direction"]

    def _position_open(mark_px: float, mark_ms: int) -> dict:
        return {
            "open": True,
            "entry_px": trade["entry_px"],
            "qty": qty,
            "mark_px": mark_px,
            "mark_ms": mark_ms,
        }

    def _position_flat() -> dict:
        return {"open": False, "entry_px": None, "qty": None, "mark_px": None, "mark_ms": None}

    def _unrealized(mark_px: float) -> dict:
        sign = 1.0 if direction == "LONG" else -1.0
        gross = sign * qty * (mark_px - trade["entry_px"])
        exit_value = qty * mark_px
        hypothetical_exit = exit_value * (5.0 + 1.0 + 2.0) / 10_000.0
        return {
            "gross": gross,
            "fees_est": costs["entry_fees"] + costs["entry_spread_slip"] + hypothetical_exit,
            "net_est": gross - costs["entry_fees"] - costs["entry_spread_slip"] - hypothetical_exit,
            "mark_px": mark_px,
        }

    # La cinta de pasos separa EVENTOS (instantáneos, en su ms exacto) de
    # VELAS (conocidas al cierre …59.999). Un evento nunca se anticipa al paso
    # que cierra una vela: una detección disponible a 21:59:59.999 NO es
    # conocida con cursor 21:44:59.999; se revela en su propio paso de evento,
    # en su instante de disponibilidad.
    #
    # formation_time_ms (a qué momento pertenece el patrón) y available_at
    # (cuándo puede conocerse) son distintos. La formación se conserva como
    # METADATO visible al revelar la detección, pero NUNCA autoriza a mostrarla
    # antes de available_at. entry_ms es la ejecución posterior, tampoco la
    # autoriza a adelantarse.
    steps: list[dict] = []
    cursor = 0

    def _emit_candle_step(candle: dict, opened: bool, final_candle: bool) -> None:
        nonlocal running_mfe, running_mae, cursor
        if opened:
            if direction == "LONG":
                running_mfe = max(running_mfe, (candle["high"] - trade["entry_px"]) / trade["entry_px"] * 100.0)
                running_mae = max(running_mae, (trade["entry_px"] - candle["low"]) / trade["entry_px"] * 100.0)
            else:
                running_mfe = max(running_mfe, (trade["entry_px"] - candle["low"]) / trade["entry_px"] * 100.0)
                running_mae = max(running_mae, (candle["high"] - trade["entry_px"]) / trade["entry_px"] * 100.0)
        mark_px = candle["close"]
        mark_ms = candle["close_time_ms"]
        steps.append({
            "step": cursor,
            "kind": "candle",
            "candle": candle,
            "known_at_ms": candle["close_time_ms"],
            "opens_at_ms": candle["open_time_ms"],
            "closed_at_ms": candle["close_time_ms"],
            "events": [],
            "position_after": _position_open(mark_px, mark_ms) if opened else _position_flat(),
            "mfe_pct": running_mfe if opened else None,
            "mae_pct": running_mae if opened else None,
            "unrealized": _unrealized(mark_px) if opened else None,
            "exit": None,
            "final_candle": final_candle,
        })
        cursor += 1

    def _emit_event_step(at_ms: int, label: str, kind: str, *, position: dict,
                         unrealized: dict | None = None,
                         exit_record: dict | None = None,
                         formation_time_ms: int | None = None) -> None:
        nonlocal cursor
        event = {"at_ms": at_ms, "label": label, "kind": kind}
        if formation_time_ms is not None:
            # Metadata: a qué momento PERTENECE el patrón (no cuándo se conoce).
            event["formation_time_ms"] = formation_time_ms
        steps.append({
            "step": cursor,
            "kind": "event",
            "candle": None,
            "known_at_ms": at_ms,
            "opens_at_ms": at_ms,
            "closed_at_ms": None,
            "events": [event],
            "position_after": position,
            "mfe_pct": running_mfe if position["open"] else None,
            "mae_pct": running_mae if position["open"] else None,
            "unrealized": unrealized,
            "exit": exit_record,
            "final_candle": False,
        })
        cursor += 1

    last_close_ms = selected[-1]["close_time_ms"]
    exit_ms = trade["exit_ms"]
    exit_record = {"reason": trade["exit_reason"], "px": trade["exit_px"], "ms": exit_ms, "executed": True}
    planned_avail = backing.get("available_at")
    avail_ms = int(planned_avail) if planned_avail is not None else None

    for index, candle in enumerate(selected):
        opened = candle["open_time_ms"] >= trade["entry_ms"]
        final_candle = index == len(selected) - 1

        # Entrada ejecutada al open de su vela: se revela ANTES del cierre de
        # esa vela, en su ms exacto (el open precede al close …59.999).
        if candle["open_time_ms"] == trade["entry_ms"]:
            _emit_event_step(trade["entry_ms"], "Entrada ejecutada al open", "entry",
                             position=_position_open(candle["open"], candle["open_time_ms"]),
                             unrealized=_unrealized(candle["open"]))

        _emit_candle_step(candle, opened, final_candle)

        # Detección: se revela SOLO en su instante de disponibilidad, nunca en
        # formation_time_ms. Si la disponibilidad coincide con el cierre de la
        # vela de formación, se emite justo después de esa vela.
        if index == 0 and avail_ms is not None and avail_ms == candle["close_time_ms"]:
            _emit_event_step(
                avail_ms,
                "Detección conocida (formación conservada como metadata)",
                "detection",
                position=_position_flat(),
                formation_time_ms=trade["event_time_ms"],
            )

    # Cierre: en su ms exacto (puede ser …00.000, posterior al cierre de vela …59.999).
    _emit_event_step(exit_ms, f"Cierre ejecutado: {trade['exit_reason']}", "exit",
                     position=_position_flat(), exit_record=exit_record)

    # Si la disponibilidad quedó pendiente (posterior al cierre de formación),
    # se emite en su instante exacto tras el resto de la cinta.
    if avail_ms is not None and avail_ms > selected[0]["close_time_ms"]:
        _emit_event_step(
            avail_ms,
            "Detección conocida (posterior al cierre de formación)",
            "detection",
            position=_position_flat(),
            formation_time_ms=trade["event_time_ms"],
        )

    if not any(step["exit"] is not None for step in steps):
        raise ValueError("la ventana no contiene el cierre realizado")
    if exit_ms < last_close_ms:
        raise ValueError("el cierre no puede preceder al último cierre de vela conocido")
    # Invariante de causalidad: ningún paso revela información con un reloj
    # anterior al instante en que esa información existe. En particular, la
    # formación NO puede revelarse antes de su disponibilidad.
    for step in steps:
        for event in step["events"]:
            if event["at_ms"] > step["known_at_ms"]:
                raise ValueError(f"evento {event['kind']} anticipado respecto a su instante")
            formation = event.get("formation_time_ms")
            if formation is not None and event["kind"] == "detection":
                if formation > event["at_ms"]:
                    raise ValueError("detección revelada antes de su formación (imposible)")
                if event["at_ms"] < avail_ms:
                    raise ValueError("detección revelada antes de su disponibilidad")
    # La formación nunca se revela antes de available_at en ningún paso:
    # no debe existir un paso con reloj < available_at que contenga la detección.
    if avail_ms is not None:
        for step in steps:
            has_detection = any(e["kind"] == "detection" for e in step["events"])
            if has_detection and step["known_at_ms"] < avail_ms:
                raise ValueError("la detección aparece antes de available_at")
    context = _context_candles(trade, candles, context_candles)
    # Instante inicial del replay: ANTES de la detección. Todo lo que se muestra
    # en la vista inicial debe ser conocido en este instante. El contexto previo
    # termina justo antes de la vela de formación, así que el instante inicial es
    # el último cierre de contexto conocido (o el open de la formación si no hay).
    if context:
        initial_cursor_ms = context[-1]["close_time_ms"]
    else:
        initial_cursor_ms = selected[0]["open_time_ms"]
    return {"symbol": trade["symbol"], "interval": trade["res"],
            "n_candles": len(selected), "n_context_candles": len(context),
            "context_candles": context,
            "initial_cursor_ms": initial_cursor_ms,
            "candles": selected, "steps": steps}


def build(package: Path, traces_dir: Path, context_candles: int = 48) -> dict:
    package_manifest = package / "package_manifest.json"
    declared = _load(package_manifest).get("archivos", {})
    for relative, metadata in declared.items():
        path = package / relative
        if not path.exists() or _sha256(path) != metadata.get("sha256"):
            raise ValueError(f"paquete inválido: {relative}")

    trades = _load_traces(traces_dir)
    trade, backing, exclusions_before_choice = _select(trades, package)
    paths = _combo_paths(package, trade["symbol"], trade["res"])
    event = _event_from_inputs(trade, paths)
    manifest = _load(paths["manifest"])
    horizon_ms = int(manifest["exit_horizon_ms"])
    qty = 1000.0 / trade["entry_px"]
    exit_value = qty * trade["exit_px"]
    costs = {
        "entry_fees": 1000.0 * 5.0 / 10_000.0,
        "exit_fees": exit_value * 5.0 / 10_000.0,
        "entry_spread_slip": 1000.0 * 3.0 / 10_000.0,
        "exit_spread_slip": exit_value * 3.0 / 10_000.0,
        "total_fees": trade["fees"],
        "total_spread_slip": None,
        "funding": trade["funding"],
        "friction": trade["gross_pnl"] - trade["net_pnl"],
    }
    costs["total_spread_slip"] = (costs["entry_spread_slip"] + costs["exit_spread_slip"])
    expected_net = trade["gross_pnl"] - costs["friction"]
    if not math.isclose(expected_net, trade["net_pnl"], rel_tol=TOLERANCE, abs_tol=TOLERANCE):
        raise ValueError("reconciliación económica final falló")

    source_paths = {
        "package_manifest": package_manifest,
        "reconstruction_manifest": traces_dir / "reconstruction_manifest.json",
        "selected_trace": Path(trade["_trace_path"]),
        **paths,
    }
    source_hashes = {_source_label(path): _sha256(path) for path in source_paths.values()}
    stop_factor = 1.0 - 0.005 if trade["direction"] == "LONG" else 1.0 + 0.005
    artifact = {
        "schema_version": 1,
        "artifact_version": ARTIFACT_VERSION,
        "label": "Paper Lab - replay historico interactivo; no simulacion prospectiva ni senal",
        "replay_id": f"PLR-{trade['symbol']}-{trade['direction']}-{trade['event_time_ms']}",
        "engine_version": ENGINE_VERSION,
        "eligibility_rule": (
            "primera operacion 1x no-baseline H1/H3 por (event_time_ms, event_id), "
            "realizada por stop/horizon, sin marca abierta, con respaldo directo unico "
            "del censo y funding completo; fijada antes de mirar P&L; no se elige por rentabilidad"
        ),
        "selection": {
            "sort": ["event_time_ms asc", "event_id asc"],
            "eligible_families": ["H1", "H3"],
            "excluded_family_reason": "H2 requiere reconstruccion de confirmacion; esta entrega exige respaldo directo",
            "exclusions_before_choice": dict(sorted(exclusions_before_choice.items())),
            "population_trades_1x": len(trades),
        },
        "chosen_at_utc": datetime.fromtimestamp(trade["event_time_ms"] / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "trade": {
            "symbol": trade["symbol"], "direction": trade["direction"],
            "family": trade["family"], "rules_version": trade["rules_version"],
            "event_time_ms": trade["event_time_ms"], "segment": trade["segmento"],
            "group": trade["group"], "entry_ms": trade["entry_ms"],
            "exit_ms": trade["exit_ms"], "exit_reason": trade["exit_reason"],
            "entry_px": trade["entry_px"], "exit_px": trade["exit_px"],
            "filled_qty": qty, "filled_cost": 1000.0,
            "gross_pnl": trade["gross_pnl"], "fees": trade["fees"],
            "entry_fees": costs["entry_fees"], "exit_fees": costs["exit_fees"],
            "funding": trade["funding"], "friction": costs["friction"],
            "net_pnl": trade["net_pnl"], "realized_net": trade["net_pnl"],
            "exit_executed": True, "open_at_end": False,
            "funding_accounting_complete": True,
        },
        "event": {
            "event_id": trade["event_id"], "event_time_ms": event["event_time_ms"],
            "direction": event["direction"], "family": event["family"],
            "rules_version": event["rules_version"], "reference_price": event["reference_price"],
            "source": _relative(paths["detections"]),
            "available_at_ms": backing["available_at"],
            "detection_id": backing["census_id"],
        },
        "levels": {
            "notional_usdt": 1000.0, "qty_base": qty,
            "entry_px": trade["entry_px"], "stop_px": trade["entry_px"] * stop_factor,
            "stop_distance_pct": 0.5, "horizon_ms": horizon_ms,
            "horizon_end_ms": trade["event_time_ms"] + horizon_ms,
            "fee_bps": 5.0, "spread_bps": 1.0, "slippage_bps": 2.0,
            "cost_scale": 1.0,
        },
        "costs": costs,
        "result": {
            "gross_pnl": trade["gross_pnl"], "net_pnl": trade["net_pnl"],
            "realized_net": trade["net_pnl"], "exit_reason": trade["exit_reason"],
            "exit_executed": True,
            "reconciled_to_engine": {
                "entry_px": True, "exit_px": True, "gross_pnl": True,
                "net_pnl": True, "fees": math.isclose(costs["entry_fees"] + costs["exit_fees"], trade["fees"], rel_tol=TOLERANCE),
                "funding": True,
            },
            "tolerance": {"relative": TOLERANCE, "absolute_usdt": TOLERANCE},
            "note": "P&L intermedio estimado sobre cierre conocido; neto final reconciliado al motor.",
        },
        "window": _window(trade, backing, _load(paths["candles"]), costs, context_candles),
        "provenance": {
            "symbol": trade["symbol"], "interval": trade["res"],
            "source_db": "NO LEIDA; derivado del paquete versionado EVAL-CENSUS-V2",
            "db_sha256": None,
            "events_file": _relative(paths["events"]),
            "candles_file": _relative(paths["candles"]),
            "manifest_file": _relative(paths["manifest"]),
            "selection_file": _relative(paths["selection"]),
            "funding_calendar": _relative(paths["funding"]),
            "engine": "scripts/reconstruct_replay_traces.py + src/microstructure_probe/backtest_offline.py",
            "engine_version": ENGINE_VERSION,
            "source_hashes": source_hashes,
            "note": "Artefacto autocontenido; runtime sin DBs, temporales ni archivos ignorados.",
        },
        "limitations": [
            "Replay historico de una operacion registrada; no seleccion automatica en vivo ni simulacion prospectiva.",
            "BTC/ETH/SOL son controles de mecanica; no validan el selector real de extremos.",
            "Velas OHLC cerradas; no se inventan ticks ni recorrido intrabar; paso discreto por vela.",
            "COST-ASSUME-v1: fee 5 bps, spread 1 bps y slippage 2 bps; supuestos, no mediciones.",
            "Sin take-profit ni trailing stop; solo niveles y cierre ejecutados por el replay.",
            "H1/H3 del estudio fueron rechazadas economicamente; esta pantalla no aprueba H1/H2/H3.",
        ],
    }
    if not all(artifact["result"]["reconciled_to_engine"].values()):
        raise ValueError("campos del artefacto no reconciliados al motor")
    return artifact


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", default=str(PACKAGE_DEFAULT))
    parser.add_argument("--traces-dir", required=True)
    parser.add_argument("--out", default=str(OUT_DEFAULT))
    parser.add_argument("--context-candles", type=int, default=48,
                        help="velas reales previas al evento solo como contexto (0 = ninguna)")
    parser.add_argument("--check", action="store_true",
                        help="compara byte a byte con --out sin escribir")
    args = parser.parse_args(argv)
    package = Path(args.package).resolve()
    traces_dir = Path(args.traces_dir).resolve()
    out = Path(args.out).resolve()
    payload = (json.dumps(build(package, traces_dir, args.context_candles), indent=2,
                          ensure_ascii=False) + "\n").encode("utf-8")
    if args.check:
        if not out.exists() or out.read_bytes() != payload:
            print("FAIL: artefacto Paper Lab no coincide con la regeneracion")
            return 1
        print(f"PASS: artefacto determinista sha256={hashlib.sha256(payload).hexdigest()}")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(payload)
    print(f"escrito {out} sha256={hashlib.sha256(payload).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
