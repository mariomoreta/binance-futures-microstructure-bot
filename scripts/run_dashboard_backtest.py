"""Ejecutor offline acotado para el Backtest de Dashboard V2.

Ejecuta UNA evaluacion historica reproducible sobre el paquete versionado
EVAL-CENSUS-V2 usando el motor existente ``backtest_offline`` (via el mismo
bucle mecanico de ``scripts/run_family_evaluation.py``). No hay motor
paralelo, no hay busqueda de parametros, no hay red ni DBs canonicas.

Contrato de seguridad:
- Solo acepta un ``--experiment`` de una LISTA PERMITIDA embebida. No se
  aceptan rutas, comandos ni codigo arbitrarios del cliente.
- Verifica hashes del paquete contra ``package_manifest.json`` ANTES de
  ejecutar; un paquete alterado falla cerrado sin escribir resultados.
- Escribe resultados SOLO en ``--out-dir`` (aislado, fuera de datos
  operacionales y de DBs canonicas). No abre ningun archivo en modo
  escritura fuera de ese directorio.
- Determinista: mismos inputs -> mismos trades y mismos hashes.

Resultados (en ``--out-dir``):
- ``job_state.json``  — estado persistido (pendiente/ejecutando/completado/fallido).
- ``summary.json``    — agregados por (simbolo, resolucion, grupo, segmento, escala).
- ``trades.json``     — operaciones individuales (con identidad de experimento).
- ``reconciliation.json`` — reconciliacion con el motor (totales vs trades).

Etiqueta explicita: "Evaluacion historica de reglas candidatas sobre dataset
conocido", NO validacion del selector completo de extremos.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from microstructure_probe.backtest_offline import (  # noqa: E402
    BacktestConfig,
    Candle,
    FundingCalendar,
    FundingSettlement,
    StudyEvent,
    input_hash,
    run_backtest,
    split_by_time,
)

ENGINE_VERSION = "backtest-offline/v4.2"
EXECUTOR_VERSION = "dashboard-backtest-executor/v1"
PACKAGE_DEFAULT = ROOT / "docs" / "evidence" / "eval-census-v2-package"
SCALES = (1.0, 2.0, 3.0)

GROUPS = ("continuation", "bearish-continuation", "correction-exhaustion",
          "correction-reversal", "rebound-variant", "baseline")
GROUP_FAMILY = {
    "continuation": ("H1", "H1-v1"),
    "correction-exhaustion": ("H2", "H2-v1"),
    "correction-reversal": ("H2", "H2-v1"),
    "bearish-continuation": ("H3", "H3-v1"),
    "rebound-variant": ("H2", "H2-v1-rebound"),
}
GROUP_LABEL = {
    "continuation": "H1 continuacion alcista (LONG)",
    "bearish-continuation": "H3 continuacion bajista (SHORT)",
    "correction-exhaustion": "H2 agotamiento (SHORT) - HIPOTESIS NUEVA",
    "correction-reversal": "H2 reversion (LONG) - HIPOTESIS NUEVA",
    "rebound-variant": "H2 variante rebote (SIN DEFINICION - 0 eventos)",
    "baseline": "Baseline agrupado (referencia, NO estrategia)",
}
PLACEBO_NOTE = ("TIME-PLACEBO-v1 (seed 42): una realizacion sintetica; "
                "referencia separada de las hipotesis, nunca sumada a ellas.")

# Combo -> (dir dentro de combos/, simbolo, resolucion). Solo estos existen
# en el paquete publicado; cualquier otra combinacion es rechazada.
COMBOS = {
    ("BTCUSDT", "15m"): "eval15_btc",
    ("ETHUSDT", "15m"): "eval15_ethsol",
    ("SOLUSDT", "15m"): "eval15_ethsol",
    ("BTCUSDT", "1h"): "eval1h_trio",
    ("ETHUSDT", "1h"): "eval1h_trio",
    ("SOLUSDT", "1h"): "eval1h_trio",
}

# Lista permitida de experimentos. El cliente NUNCA envia rutas ni simbolos
# libres: envia un experiment_id y esta constante decide que se ejecuta.
EXPERIMENTS = {
    "eval-census-v2-trio": {
        "label": "Evaluacion historica de reglas candidatas sobre dataset conocido",
        "not_label": "NO es un backtest completo del descubrimiento de extremos",
        "package": "docs/evidence/eval-census-v2-package",
        "package_version": "EVAL-CENSUS-V2",
        "combos": [("BTCUSDT", "15m"), ("ETHUSDT", "15m"), ("SOLUSDT", "15m"),
                   ("BTCUSDT", "1h"), ("ETHUSDT", "1h"), ("SOLUSDT", "1h")],
        "scales": list(SCALES),
        "groups": list(GROUPS),
    },
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _load_events(path: Path):
    out, groups = [], []
    for row in _load(path):
        out.append(StudyEvent(
            symbol=str(row["symbol"]), event_time_ms=int(row["event_time_ms"]),
            direction=str(row["direction"]),
            reference_price=float(row.get("reference_price", 0.0)),
            family=str(row.get("family", "H1")),
            rules_version=str(row.get("rules_version", "H1-v1"))))
        groups.append(str(row.get("group", "continuation")))
    return out, groups


def _load_candles(path: Path):
    return [Candle(symbol=str(r["symbol"]), open_time_ms=int(r["open_time_ms"]),
                   open=float(r["open"]), high=float(r["high"]),
                   low=float(r["low"]), close=float(r["close"]),
                   close_time_ms=(int(r["close_time_ms"])
                                  if r.get("close_time_ms") is not None else None))
            for r in _load(path)]


def _load_calendar(path: Path):
    rows = _load(path)
    if isinstance(rows, dict):
        sym = rows.get("symbol")
        return FundingCalendar(
            version=str(rows.get("version", "external/v1")),
            source=str(rows.get("source", "external")),
            interval_ms=rows.get("interval_ms"),
            symbol=None if sym is None else str(sym),
            settlements=tuple(FundingSettlement(int(s["settlement_ms"]),
                                                float(s["rate_bps"]))
                              for s in rows.get("settlements", [])))
    cal_symbol = str(rows[0].get("symbol")) if rows else None
    return FundingCalendar(
        version="FUNDING-CAL-v1",
        source="exchange-funding-history (Binance USD-M fundingRate)",
        interval_ms=28_800_000, symbol=cal_symbol,
        settlements=tuple(FundingSettlement(int(s["fundingTime"]),
                                            float(s["fundingRate"]) * 10000.0)
                          for s in rows))


def verify_package(package: Path, declared: dict) -> dict:
    """Verifica cada archivo declarado contra su sha256. Falla cerrado."""
    verified = {}
    for relative, metadata in declared.items():
        path = package / relative
        if not path.exists():
            raise ValueError(f"paquete alterado: falta {relative}")
        actual = sha256_file(path)
        if actual != metadata.get("sha256"):
            raise ValueError(f"paquete alterado: hash distinto en {relative}")
        verified[relative] = actual
    return verified


def _trade_row(t: dict, *, symbol: str, res: str, group: str, segment: str,
               scale: float, event_id: str, idx_global: int) -> dict:
    return {
        "trade_id": f"{symbol}:{res}:{group}:{segment}:{scale:g}:{idx_global}",
        "event_id": event_id,
        "symbol": symbol, "res": res, "group": group, "segment": segment,
        "scale": scale,
        "direction": t["direction"], "family": t["family"],
        "rules_version": t["rules_version"],
        "event_time_ms": t["event_time_ms"],
        "entry_ms": t["entry_ms"], "exit_ms": t["exit_ms"],
        "entry_px": t["entry_px"], "exit_px": t["exit_px"],
        "exit_reason": t["exit_reason"],
        "exit_executed": bool(t["exit_executed"]),
        "open_at_end": bool(t.get("open_at_end", False)),
        "status": "realizada" if t["exit_executed"] else "abierta",
        "gross_pnl": t["gross_pnl"], "fees": t["fees"],
        "funding": t["funding"], "net_pnl": t["net_pnl"],
        "realized_net": t.get("realized_net"),
        "mfe_pct": t.get("mfe_pct"), "mae_pct": t.get("mae_pct"),
        "holding_ms": t["exit_ms"] - t["entry_ms"],
        "funding_accounting_complete": t.get("funding_accounting_complete"),
        "coverage": ("completa" if t.get("funding_accounting_complete") is True
                     else "UNKNOWN/parcial"),
    }


def run_experiment(experiment_id: str, out_dir: Path, context_candles: int = 48,
                   run_id: str | None = None, executor_token: str | None = None,
                   budget_ms: int = 600_000) -> int:
    spec = EXPERIMENTS.get(experiment_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = out_dir / "job_state.json"
    started = time.time()
    effective_run_id = run_id or experiment_id
    deadline = started + max(1, budget_ms) / 1000.0

    def write_state(status: str, **extra) -> None:
        payload = {
            "job_id": effective_run_id,
            "run_id": effective_run_id,
            "experiment_id": experiment_id,
            "status": status,
            "executor_version": EXECUTOR_VERSION,
            "engine_version": ENGINE_VERSION,
            "executor_token": executor_token,
            "executor_pid": os.getpid(),
            "started_at_ms": int(started * 1000),
            "updated_at_ms": int(time.time() * 1000),
            "duration_ms": int((time.time() - started) * 1000),
            "identity": "verified",
        }
        payload.update(extra)
        tmp = state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
        os.replace(tmp, state_path)

    write_state("ejecutando")
    if spec is None:
        write_state("fallido", error="EXPERIMENT_NOT_ALLOWED",
                    detail="experiment_id fuera de la lista permitida")
        return 2

    package = (ROOT / spec["package"]).resolve()
    if time.time() > deadline:
        write_state("fallido", error="TIMEOUT",
                    detail="Presupuesto agotado antes de verificar el paquete.")
        return 5
    try:
        pkg_manifest = _load(package / "package_manifest.json")
        declared = pkg_manifest.get("archivos", {})
        verified = verify_package(package, declared)
    except Exception as exc:  # noqa: BLE001 - fail-closed reporting
        write_state("fallido", error="PACKAGE_VERIFICATION_FAILED",
                    detail=str(exc))
        return 3

    try:
        combos_out = []
        all_trades = []
        recon_rows = []
        for symbol, res in spec["combos"]:
            if time.time() > deadline:
                write_state("fallido", error="TIMEOUT",
                            detail="Presupuesto de ejecucion agotado durante el bucle.")
                return 5
            combo_dir = spec["combos"] and COMBOS[(symbol, res)]
            base = package / "combos" / combo_dir
            events_path = base / f"events_{symbol}_{res}.json"
            candles_path = base / f"candles_{symbol}_{res}.json"
            manifest_path = base / f"manifest_{symbol}_{res}.json"
            selection_path = base / f"selection_{symbol}_{res}.json"
            funding_path = package / "funding" / f"funding_{symbol}.json"
            events, groups = _load_events(events_path)
            candles = _load_candles(candles_path)
            man = _load(manifest_path)
            sel = _load(selection_path) if selection_path.exists() else {}
            cutoff = int(man["cutoff_ms"])
            horizon = int(man["exit_horizon_ms"])
            calendar = _load_calendar(funding_path)
            symbol_trades = 0
            for group in spec["groups"]:
                family, version = GROUP_FAMILY.get(group, ("H1", "H1-v1"))
                idx = [i for i, g in enumerate(groups) if g == group]
                if not idx:
                    combos_out.append({
                        "symbol": symbol, "res": res, "group": group,
                        "label": GROUP_LABEL.get(group, group),
                        "status": "sin_operaciones", "n_trades_1x": 0,
                        "note": "grupo sin eventos en esta combinacion"})
                    continue
                gev = [events[i] for i in idx]
                parts = split_by_time(gev, cutoff)
                pos_en_gev = {id(e): k for k, e in enumerate(gev)}
                ref_ids = set(man.get("groups", {}).get(group, {}).get("event_ids", []))
                for seg, seg_events in parts.items():
                    admitidos = sorted(
                        range(len(seg_events)),
                        key=lambda j: (seg_events[j].event_time_ms,
                                       seg_events[j].symbol))
                    for scale in spec["scales"]:
                        cfg = BacktestConfig(family=family, rules_version=version,
                                             exit_horizon_ms=horizon,
                                             cost_scale=scale,
                                             funding_calendar=calendar)
                        r = run_backtest(seg_events, candles, cfg,
                                         dataset_id="caller-supplied", segment=seg)
                        for k, pos in enumerate(r["admitted_positions"]):
                            e_seg = seg_events[admitidos[pos]]
                            # Índice global estable = posición del evento en la
                            # lista del grupo, mapeada al índice del fichero de
                            # eventos (misma identidad que reconstruct_replay_traces).
                            idx_global = idx[pos_en_gev[id(e_seg)]]
                            eid = "%s:%d:%s:%s:%s:%d" % (
                                e_seg.symbol, e_seg.event_time_ms, e_seg.direction,
                                e_seg.family, e_seg.rules_version, idx_global)
                            # Cross-check de identidad contra el manifiesto
                            # original: la operación debe vincularse a un
                            # event_id admitido. Si no, se rechaza el run.
                            if eid not in set(ref_ids):
                                raise ValueError(
                                    "event_id fuera del manifiesto: %s" % eid)
                            row = _trade_row(r["trades"][k], symbol=symbol,
                                             res=res, group=group, segment=seg,
                                             scale=scale, event_id=eid,
                                             idx_global=idx_global)
                            all_trades.append(row)
                            if scale == 1.0:
                                symbol_trades += 1
                        if scale == 1.0:
                            n_realized = r["n_realized"]
                            n_open = r["n_open"]
                            combos_out.append({
                                "symbol": symbol, "res": res, "group": group,
                                "label": GROUP_LABEL.get(group, group),
                                "segment": seg, "scale": scale,
                                "n_events": r["n_events"],
                                "n_trades": r["n_trades"],
                                "n_realized": n_realized, "n_open": n_open,
                                "skipped_overlap": r["skipped_overlap"],
                                "n_expired": r["n_expired"],
                                "n_mismatched": r["n_mismatched"],
                                "exit_reasons": r["exit_reasons"],
                                "expectancy_net": r["expectancy_net"],
                                "expectancy_gross": r["expectancy_gross"],
                                "total_net": r["total_net"],
                                "total_net_realized": r["total_net_realized"],
                                "total_fees": r["total_fees"],
                                "total_funding": r["total_funding"],
                                "max_drawdown": r["max_drawdown"],
                                "max_drawdown_realized": r["max_drawdown_realized"],
                                "mfe_mean": r["mfe_mean"], "mae_mean": r["mae_mean"],
                                "config_hash": r["config_hash"],
                                "config_hash_1x": r["config_hash"],
                                "n_trades_1x": r["n_trades"] if scale == 1.0 else None,
                                "status": ("sin_operaciones" if r["n_trades"] == 0
                                           else "con_operaciones"),
                            })
                            # Reconciliation for this exact cell (1x).
                            net_from_trades = sum(t["net_pnl"] for t in r["trades"])
                            recon_rows.append({
                                "symbol": symbol, "res": res, "group": group,
                                "segment": seg, "scale": scale,
                                "config_hash": r["config_hash"],
                                "total_net": r["total_net"],
                                "sum_trades_net": net_from_trades,
                                "match": abs(r["total_net"] - net_from_trades) <= 1e-9,
                                "n_trades": r["n_trades"],
                            })
            # Balance: solo @1x cuenta como operaciones del experimento.
            combos_out.append({
                "symbol": symbol, "res": res, "group": "__combo__",
                "label": "total realizado @1x", "n_trades_1x": symbol_trades,
                "input_hash": man.get("input_hash"),
                "funding_calendar": man.get("funding_calendar")})

        # Orden inicial cronologico (no por beneficio), como exige el contrato.
        all_trades.sort(key=lambda t: (t["event_time_ms"], t["symbol"],
                                       t["res"], t["group"], t["scale"]))
        recon_all = all(x["match"] for x in recon_rows)
        summary = {
            "experiment_id": experiment_id,
            "experiment_version": spec["package_version"],
            "label": spec["label"],
            "not_label": spec["not_label"],
            "executor_version": EXECUTOR_VERSION,
            "engine_version": ENGINE_VERSION,
            "package": spec["package"],
            "package_version": spec["package_version"],
            "package_files_verified": len(verified),
            "package_manifest_sha256": sha256_file(package / "package_manifest.json"),
            "combos": spec["combos"],
            "scales": spec["scales"],
            "groups": [{"group": g, "label": GROUP_LABEL.get(g, g)}
                       for g in spec["groups"]],
            "placebo_note": PLACEBO_NOTE,
            "horizon_rule": "HORIZON-GRID4-V1 (15m->1h, 1h->4h)",
            "mapping": "MAP-CANDIDATE-v2 (NO aprobado)",
            "cost_model": "COST-ASSUME-v1 fee 5bps / spread 1bps / slippage 2bps (supuestos, no medidos); 1x/2x/3x son ESCENARIOS DE COSTES, no apalancamiento",
            "cells": combos_out,
            "n_trades_total": len(all_trades),
            "n_trades_1x": sum(1 for t in all_trades if t["scale"] == 1.0),
            "reconciliation_ok": recon_all,
            "reconciliation_rows": len(recon_rows),
            "generated_at_ms": int(time.time() * 1000),
            "duration_ms": int((time.time() - started) * 1000),
            "limitations": [
                "Evaluacion historica de reglas candidatas sobre dataset conocido; NO es un backtest completo del descubrimiento de extremos.",
                "Seleccion retrospectiva: la ventana coincide con estudios previos; held-out NO pristino (mismo cutoff, sin purga adicional).",
                "Costes supuestos (COST-ASSUME-v1); spread/profundidad reales no medidos.",
                "Sin universo elegible conocido en T ni ranking rolling24/liquidez: el descubrimiento de extremos NO es evaluable aqui.",
                "Las celdas son por (simbolo, resolucion, grupo, segmento, escala); NO se suman como cartera (exposicion conjunta no modelada).",
                "H1/H3/H2 fueron RECHAZADAS o FENCED en estudios previos; esta pantalla no aprueba ninguna.",
                "El placebo (TIME-PLACEBO-v1) es una referencia, nunca una hipotesis estrategica.",
            ],
        }
        reconciliation = {
            "ok": recon_all,
            "cells": recon_rows,
            "note": ("sum_trades_net recompone total_net celda por celda con "
                     "tolerancia 1e-9; es la reconciliacion con el motor."),
        }
        (out_dir / "summary.json").write_text(
            json.dumps(summary, indent=1, default=str), encoding="utf-8")
        (out_dir / "trades.json").write_text(
            json.dumps({"experiment_id": experiment_id,
                        "n_trades": len(all_trades),
                        "trades": all_trades}, indent=1, default=str),
            encoding="utf-8")
        (out_dir / "reconciliation.json").write_text(
            json.dumps(reconciliation, indent=1, default=str), encoding="utf-8")
        result_hashes = {
            "summary.json": sha256_file(out_dir / "summary.json"),
            "trades.json": sha256_file(out_dir / "trades.json"),
            "reconciliation.json": sha256_file(out_dir / "reconciliation.json"),
        }
        write_state("completado", n_trades=len(all_trades),
                    reconciliation_ok=recon_all, result_hashes=result_hashes)
        print("backtest: %s completado; trades=%d reconciliacion=%s"
              % (experiment_id, len(all_trades), recon_all))
        return 0
    except Exception as exc:  # noqa: BLE001 - surface real failure
        write_state("fallido", error="EXECUTION_FAILED", detail=str(exc),
                    traceback=traceback.format_exc())
        print("backtest FALLIDO: %s" % exc, file=sys.stderr)
        return 4


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--experiment", required=True,
                    help="experiment_id de la lista permitida embebida")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--context-candles", type=int, default=48)
    ap.add_argument("--run-id", default=None,
                    help="identidad de ejecucion unica (separada del experimento)")
    ap.add_argument("--executor-token", default=None,
                    help="token de propiedad de la ejecucion (prueba identidad)")
    ap.add_argument("--budget-ms", type=int, default=600_000,
                    help="presupuesto de ejecucion efectivo")
    args = ap.parse_args(argv)
    return run_experiment(args.experiment, Path(args.out_dir).resolve(),
                          args.context_candles, run_id=args.run_id,
                          executor_token=args.executor_token,
                          budget_ms=args.budget_ms)


if __name__ == "__main__":
    raise SystemExit(main())
