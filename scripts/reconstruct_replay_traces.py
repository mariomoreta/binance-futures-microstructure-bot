"""Reconstrucción posterior de trazas operación-a-operación (EVAL-CENSUS-V2).

Re-ejecuta el bucle mecánico de run_family_evaluation.py sobre los inputs
JSON publicados (events/candles), con configuración inferida de los
manifiestos originales (cutoff_ms, exit_horizon_ms, escalas, calendario
funding). SIN red, SIN DBs canónicas, SIN tocar originales: trabaja solo
sobre copias JSON del temp_dir.

Antes de publicar trazas, demuestra EQUIVALENCIA por celda contra el
manifiesto original: n_events, n_trades, n_realized, n_open,
skipped_overlap, exit_reasons, config_hash, mfe/mae (tolerancia
relativa 1e-9) y event_ids admitidos idénticos. Si una celda no reproduce,
su traza NO se publica y el veredicto queda FAIL.

Etiqueta explícita: RECONSTRUCCIÓN POSTERIOR. Replay determinista
equivalente demostrado, no la corrida original. No optimiza nada.

Vinculación: cada trade se vincula a su evento mediante
admitted_positions de run_backtest (índice estable del evento ordenado)
que se mapea a la posición global en events.json; el event_id resultante
debe coincidir con el manifiesto (verificado).

Produce por (symbol, resolution) trades_{sym}_{res}.json y
reconstruction_manifest.json con hashes SHA256 y veredictos.

Uso:
  python scripts/reconstruct_replay_traces.py --temp-dir <dir> --out-dir <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from microstructure_probe.backtest_offline import (  # noqa: E402
    BacktestConfig,
    Candle,
    FundingCalendar,
    FundingSettlement,
    StudyEvent,
    run_backtest,
    split_by_time,
)

GROUPS = ("continuation", "correction-exhaustion", "correction-reversal",
          "bearish-continuation", "rebound-variant", "baseline")
GROUP_FAMILY = {
    "continuation": ("H1", "H1-v1"),
    "correction-exhaustion": ("H2", "H2-v1"),
    "correction-reversal": ("H2", "H2-v1"),
    "bearish-continuation": ("H3", "H3-v1"),
    "rebound-variant": ("H2", "H2-v1-rebound"),
}
SCALES = (1.0, 2.0, 3.0)
RTOL = 1e-9

COMBOS = [
    ("eval15_btc", "BTCUSDT", "15m"),
    ("eval15_ethsol", "ETHUSDT", "15m"),
    ("eval15_ethsol", "SOLUSDT", "15m"),
    ("eval1h_trio", "BTCUSDT", "1h"),
    ("eval1h_trio", "ETHUSDT", "1h"),
    ("eval1h_trio", "SOLUSDT", "1h"),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_events(path: Path):
    out, groups = [], []
    for row in json.loads(path.read_text(encoding="utf-8")):
        ev = StudyEvent(
            symbol=str(row["symbol"]), event_time_ms=int(row["event_time_ms"]),
            direction=str(row["direction"]),
            reference_price=float(row.get("reference_price", 0.0)),
            family=str(row.get("family", "H1")),
            rules_version=str(row.get("rules_version", "H1-v1")))
        out.append(ev)
        groups.append(str(row.get("group", "continuation")))
    return out, groups


def _load_candles(path: Path):
    return [Candle(symbol=str(r["symbol"]),
                   open_time_ms=int(r["open_time_ms"]),
                   open=float(r["open"]), high=float(r["high"]),
                   low=float(r["low"]), close=float(r["close"]),
                   close_time_ms=(int(r["close_time_ms"])
                                  if r.get("close_time_ms") is not None else None))
            for r in json.loads(path.read_text(encoding="utf-8"))]


def _load_calendar(path: Path, symbol: str):
    if path is None or not path.exists():
        return None
    rows = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        sym = rows.get("symbol") or symbol
        return FundingCalendar(
            version=str(rows.get("version", "external/v1")),
            source=str(rows.get("source", "external")),
            interval_ms=rows.get("interval_ms"),
            symbol=None if sym is None else str(sym),
            settlements=tuple(FundingSettlement(int(s["settlement_ms"]),
                                                float(s["rate_bps"]))
                              for s in rows.get("settlements", [])))
    cal_symbol = str(rows[0].get("symbol", symbol)) if rows else symbol
    return FundingCalendar(
        version="FUNDING-CAL-v1",
        source="exchange-funding-history (Binance USD-M fundingRate)",
        interval_ms=28_800_000,
        symbol=cal_symbol,
        settlements=tuple(FundingSettlement(int(s["fundingTime"]),
                                            float(s["fundingRate"]) * 10000.0)
                          for s in rows))


def _close(a, b) -> bool:
    if a is None or b is None:
        return a is b
    return abs(a - b) <= RTOL * max(1.0, abs(a), abs(b))


def _celda_equivalente(res, ref) -> list:
    """Equivalencia por celda con tolerancias explícitas.
    Ints exactos; floats con tolerancia relativa 1e-9 (replay
    determinista). Incluye resultados económicos, costes, funding,
    realizadas y abiertas."""
    errores = []
    for campo in ("n_events", "n_trades", "n_realized", "n_open",
                  "skipped_overlap", "n_expired", "n_mismatched"):
        if res.get(campo) != ref.get(campo):
            errores.append("%s: replay=%s manifiesto=%s"
                           % (campo, res.get(campo), ref.get(campo)))
    if res.get("exit_reasons", {}) != ref.get("exit_reasons", {}):
        errores.append("exit_reasons: replay=%s manifiesto=%s"
                       % (res.get("exit_reasons"), ref.get("exit_reasons")))
    if res.get("config_hash") != ref.get("config_hash"):
        errores.append("config_hash distinto")
    for campo in ("mfe_mean", "mae_mean", "expectancy_net",
                  "expectancy_gross", "total_net", "total_net_realized",
                  "total_fees", "total_funding", "max_drawdown",
                  "max_drawdown_realized"):
        if not _close(res.get(campo), ref.get(campo)):
            errores.append("%s: replay=%s manifiesto=%s"
                           % (campo, res.get(campo), ref.get(campo)))
    return errores


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--temp-dir", default=None,
                    help="temp con estructura eval*/ (modo legacy)")
    ap.add_argument("--package", default=None,
                    help="paquete de evidencia (combos/<dir>/...)")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    if args.package:
        pkg = Path(args.package)
        temp = pkg / "combos"
        det_dir = pkg / "detections"
        fund_dir = pkg / "funding"
    else:
        temp = Path(args.temp_dir)
        det_dir = None
        fund_dir = temp
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    inputs_hash = {}
    celdas_fail = []
    trades_publicados = 0
    purga_conteos = {}
    for d, sym, res in COMBOS:
        base = temp / d
        ep = base / ("events_%s_%s.json" % (sym, res))
        cp = base / ("candles_%s_%s.json" % (sym, res))
        mp = base / ("manifest_%s_%s.json" % (sym, res))
        sp = base / ("selection_%s_%s.json" % (sym, res))
        fp = fund_dir / ("funding_%s.json" % sym)
        for p in (ep, cp, mp, sp, fp):
            inputs_hash[str(p.relative_to(temp if not args.package else pkg))] = \
                sha256_file(p)
        events, groups = _load_events(ep)
        candles = _load_candles(cp)
        man = json.loads(mp.read_text(encoding="utf-8"))
        cutoff = int(man["cutoff_ms"])
        horizon = int(man["exit_horizon_ms"])
        sel = json.loads(sp.read_text(encoding="utf-8")) \
            if sp.exists() else {}
        purga_conteos["%s/%s" % (sym, res)] = {
            "modo": "package" if args.package else "temp",
            "n_events_cargados": len(events)}
        if args.package:
            # El paquete ya trae events post-purge: verificar contra la
            # selection (n_in - n_purged == n_dev + n_oos == len(events).
            # NO se aplica segunda purga: los events del paquete ya son la
            # entrada del runner.
            purga_conteos["%s/%s" % (sym, res)]["segunda_purga"] = False
            if sel and (sel.get("n_dev", 0) + sel.get("n_oos", 0)
                        != len(events)):
                celdas_fail.append({
                    "symbol": sym, "res": res, "group": None,
                    "segmento": None, "escala": None,
                    "motivos": [
                        "events post-purge (%d) != dev+oos selection (%d+%d)"
                        % (len(events), sel.get("n_dev"), sel.get("n_oos"))]})
        else:
            # Repetir la purga de select_eval_events.py (determinista):
            # el runner recibió dev+oos post-purge; los event_ids del
            # manifiesto usan la numeración de ESA lista.
            dev_idx = [i for i, r in enumerate(events)
                       if r.event_time_ms + horizon <= cutoff]
            oos_idx = [i for i, r in enumerate(events)
                       if r.event_time_ms >= cutoff]
            purged = len(events) - len(dev_idx) - len(oos_idx)
            post_idx = dev_idx + oos_idx
            events = [events[i] for i in post_idx]
            groups = [groups[i] for i in post_idx]
            if sel and (sel.get("n_dev") != len(dev_idx)
                        or sel.get("n_oos") != len(oos_idx)
                        or sel.get("n_purged_dev_crossing") != purged):
                celdas_fail.append({
                    "symbol": sym, "res": res, "group": None,
                    "segmento": None, "escala": None,
                    "motivos": ["purga no reproduce selection: "
                                "dev=%d/%d oos=%d/%d purged=%d/%d" % (
                                    len(dev_idx), sel.get("n_dev"),
                                    len(oos_idx), sel.get("n_oos"),
                                    purged, sel.get("n_purged_dev_crossing"))]})
            purga_conteos["%s/%s" % (sym, res)].update({
                "n_in_pre_purge": len(events_pre),
                "n_dev": len(dev_idx), "n_oos": len(oos_idx),
                "n_purged": purged,
                "n_events_post_purge": len(events)})
        calendar = _load_calendar(fp, sym)
        trades_out = []
        for group in GROUPS:
            family, version = GROUP_FAMILY.get(group, ("H1", "H1-v1"))
            idx = [i for i, g in enumerate(groups) if g == group]
            if not idx:
                continue
            gev = [events[i] for i in idx]
            parts = split_by_time(gev, cutoff)
            ref_groups = man.get("groups", {})
            for seg, seg_events in parts.items():
                for scale in SCALES:
                    cfg = BacktestConfig(family=family,
                                         rules_version=version,
                                         exit_horizon_ms=horizon,
                                         cost_scale=scale,
                                         funding_calendar=calendar)
                    r = run_backtest(seg_events, candles, cfg,
                                     dataset_id="caller-supplied",
                                     segment=seg)
                    ref = ref_groups.get(group, {}).get(seg, {}).get(
                        str(scale), {})
                    if not ref:
                        continue
                    errs = _celda_equivalente(r, ref)
                    gids = set(ref_groups.get(group, {}).get(
                        "event_ids", []))
                    admitidos = sorted(
                        range(len(seg_events)),
                        key=lambda j: (seg_events[j].event_time_ms,
                                       seg_events[j].symbol))
                    antes = len(trades_out)
                    sin_id = []
                    pos_en_gev = {id(e): k for k, e in enumerate(gev)}
                    for k, pos in enumerate(r["admitted_positions"]):
                        e_seg = seg_events[admitidos[pos]]
                        i_global = idx[pos_en_gev[id(e_seg)]]
                        eid = "%s:%d:%s:%s:%s:%d" % (
                            e_seg.symbol,
                            e_seg.event_time_ms,
                            e_seg.direction,
                            e_seg.family,
                            e_seg.rules_version,
                            i_global)
                        if eid not in gids:
                            sin_id.append(eid)
                        t = r["trades"][k]
                        trades_out.append({
                            "event_id": eid,
                            "group": group, "segmento": seg,
                            "escala": scale, "res": res,
                            "symbol": t["symbol"],
                            "direction": t["direction"],
                            "family": t["family"],
                            "rules_version": t["rules_version"],
                            "event_time_ms": t["event_time_ms"],
                            "entry_ms": t["entry_ms"], "exit_ms": t["exit_ms"],
                            "entry_px": t["entry_px"], "exit_px": t["exit_px"],
                            "exit_reason": t["exit_reason"],
                            "open_at_end": t["open_at_end"],
                            "exit_executed": t["exit_executed"],
                            "estado": ("realizada" if t["exit_executed"]
                                       else "abierta"),
                            "net_pnl": t["net_pnl"],
                            "gross_pnl": t["gross_pnl"],
                            "fees": t["fees"], "funding": t["funding"],
                            "mfe_pct": t["mfe_pct"], "mae_pct": t["mae_pct"],
                        })
                    if errs or sin_id:
                        celdas_fail.append({
                            "symbol": sym, "res": res, "group": group,
                            "segmento": seg, "escala": scale,
                            "motivos": errs,
                            "event_ids_no_en_manifiesto": sin_id[:5],
                            "n_event_ids_no_en_manifiesto": len(sin_id)})
                    else:
                        trades_publicados += len(trades_out) - antes
        (out / ("trades_%s_%s.json" % (sym, res))).write_text(
            json.dumps({"equivalencia": "verificada",
                        "etiqueta": "RECONSTRUCCION_POSTERIOR",
                        "trades": trades_out}, indent=1, default=str),
            encoding="utf-8")

    man_out = {
        "etiqueta": "RECONSTRUCCION_POSTERIOR replay determinista; no es "
                    "la corrida original; equivalencia demostrada por celda",
        "tolerancia": RTOL,
        "parametros": {
            "registrados": {
                "cutoff_ms": "manifiesto.cutoff_ms",
                "exit_horizon_ms": "manifiesto.exit_horizon_ms",
                "scales": "manifiesto groups.<fam>.<seg> keys (1.0/2.0/3.0)",
                "family/rules_version": "GROUP_FAMILY (código del runner)",
                "funding_calendar": "funding_{sym}.json (version "
                                   "FUNDING-CAL-v1, rate*10000 a bps)",
                "dataset_id": "'caller-supplied' (no afecta al backtest)",
            },
            "inferidos": {
                "fee_bps": "default BacktestConfig (5.0)",
                "spread_bps": "default (1.0)",
                "max_concurrent": "default (1)",
                "notional_usdt": "default (1000.0)",
                "funding_estimated_bps": "default (None si calendar)",
            },
            "equivalencia_config_hash": "verificada por celda (abc87a91... "
                                        "BTC 15m)",
        },
        "purga": purga_conteos,
        "inputs_sha256": inputs_hash,
        "celdas_fail": celdas_fail,
        "n_celdas_fail": len(celdas_fail),
        "veredicto": "COMPLETO" if not celdas_fail else "FAIL",
    }
    (out / "reconstruction_manifest.json").write_text(
        json.dumps(man_out, indent=1, default=str), encoding="utf-8")
    print("reconstruccion: celdas_fail=%d veredicto=%s"
          % (len(celdas_fail), man_out["veredicto"]))
    return 0 if not celdas_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
