"""Auditoria offline del ledger EVAL-CENSUS-V2 desde manifiestos ejecutados.

Lee los 6 manifiestos reales (15m + 1h, 3 símbolos) generados por
scripts/build_census_eval_inputs.py + select_eval_events.py +
run_family_evaluation.py (copias en temp/opencode, fuera de Git) y el
artefacto publicado frontend/src/data/census-eval-v2.json.

No toca la red, ni DBs canónicas, ni módulos vivos. Solo lectura de JSON.
Produce un reporte compacto en docs/evidence/audit_offline_eval_ledger.json
para revisar el flujo sin depender exclusivamente de rutas temp locales.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

TEMP = Path(r"C:\Users\adonm\AppData\Local\Temp\opencode")
ARTIFACT = Path(
    r"C:\proyectos\binance-futures-microstructure-bot\frontend\src\data\census-eval-v2.json"
)
OUT = Path(
    r"C:\proyectos\binance-futures-microstructure-bot\docs\evidence\audit_offline_eval_ledger.json"
)

# Manifiestos ejecutados: (directorio_temp, symbol, interval)
MANIFIESTOS = [
    ("eval15_btc", "BTCUSDT", "15m"),
    ("eval15_ethsol", "ETHUSDT", "15m"),
    ("eval15_ethsol", "SOLUSDT", "15m"),
    ("eval1h_trio", "BTCUSDT", "1h"),
    ("eval1h_trio", "ETHUSDT", "1h"),
    ("eval1h_trio", "SOLUSDT", "1h"),
]

H_DIRECCIONAL = {"continuation", "bearish-continuation"}   # H1 + H3
H2_FADE = {"correction-exhaustion", "correction-reversal"}   # H2 fade
BASELINE = {"baseline"}                                       # placebo


def _load_manifest(sym: str, res: str):
    for d, s, r in MANIFIESTOS:
        if s == sym and r == res:
            p = TEMP / d / ("manifest_%s_%s.json" % (sym, res))
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
    return None


def _load_selection(sym: str, res: str):
    for d, s, r in MANIFIESTOS:
        if s == sym and r == res:
            p = TEMP / d / ("selection_%s_%s.json" % (sym, res))
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
    return None


def main():
    with open(ARTIFACT, encoding="utf-8") as f:
        art = json.load(f)
    cells = art["cells"]

    ledger = []
    summary = {
        "builder_h1": 0, "builder_h3": 0, "builder_h2ex": 0,
        "builder_h2rev": 0, "builder_placebo": 0,
        "builder_excl_gap": 0, "builder_excl_no_entry": 0,
        "builder_excl_h2_nc": 0, "builder_excl_h2_rec": 0,
        "selection_n_in": 0, "selection_dev": 0, "selection_oos": 0,
        "selection_purged": 0,
        "art_events": 0, "art_trades": 0, "art_open": 0,
        "art_skipped": 0,
        "mfe_min": None, "mfe_max": None,
        "mae_min": None, "mae_max": None,
        "funding_settled_1x": 0, "funding_unknown_1x": 0,
        "funding_uncovered_ms_1x": 0, "funding_gap_ms_1x": 0,
        "cells_uncovered": 0, "cells_total": 0,
    }

    filas = []

    for sym in cells:
        for res in cells[sym]:
            man = _load_manifest(sym, res)
            sel = _load_selection(sym, res)
            for fam in cells[sym][res]:
                for split in cells[sym][res][fam]:
                    if "1.0" not in cells[sym][res][fam][split]:
                        continue
                    c = cells[sym][res][fam][split]["1.0"]
                    fam_kind = (
                        "H1/H3 direccional" if fam in H_DIRECCIONAL else
                        "H2 fade" if fam in H2_FADE else
                        "baseline/placebo" if fam in BASELINE else fam)
                    # Datos del manifiesto (escala 1.0)
                    mseg = None
                    if man:
                        g = man["groups"].get(fam, {})
                        mseg = g.get(split, {}).get("1.0", {})
                    # Datos de selection (purge) - a nivel simbolo/resolucion
                    ssel = sel or {}
                    filas.append({
                        "symbol": sym, "res": res, "familia": fam,
                        "familia_tipo": fam_kind, "segmento": split,
                        "artefacto": {
                            "n_events": c["n_events"],
                            "n_trades": c["n_trades"],
                            "n_open": c["n_open"],
                            "skipped_overlap": c["skipped_overlap"],
                            "E_net": c["E_net"],
                            "placebo_E_net": c.get("placebo_E_net"),
                            "verdict": c.get("verdict"),
                            "exit_stop": c.get("exit_stop"),
                        },
                        "manifiesto": mseg or {},
                        "selection": ssel,
                    })

                    # Acumuladores globales (solo escala 1.0)
                    summary["art_events"] += c["n_events"]
                    summary["art_trades"] += c["n_trades"]
                    summary["art_open"] += c["n_open"]
                    summary["art_skipped"] += c["skipped_overlap"]
                    summary["cells_total"] += 1
                    mfq = (mseg or {}).get("funding_quality", {})
                    summary["funding_settled_1x"] += mfq.get("settled_events", 0)
                    summary["funding_unknown_1x"] += mfq.get("unknown_excluded", 0)
                    summary["funding_uncovered_ms_1x"] += mfq.get("uncovered_ms", 0)
                    summary["funding_gap_ms_1x"] += mfq.get("gap_ms", 0)
                    if mfq.get("uncovered_ms", 0) > 0:
                        summary["cells_uncovered"] += 1
                    mm = mseg.get("mfe_mean") if mseg else None
                    ma = mseg.get("mae_mean") if mseg else None
                    if mm is not None:
                        summary["mfe_min"] = mm if summary["mfe_min"] is None \
                            else min(summary["mfe_min"], mm)
                        summary["mfe_max"] = mm if summary["mfe_max"] is None \
                            else max(summary["mfe_max"], mm)
                    if ma is not None:
                        summary["mae_min"] = ma if summary["mae_min"] is None \
                            else min(summary["mae_min"], ma)
                        summary["mae_max"] = ma if summary["mae_max"] is None \
                            else max(summary["mae_max"], ma)

    # Builder counts (de los 3 build_report.json)
    for d, sym, res in MANIFIESTOS:
        p = TEMP / d / "build_report.json"
        # build_report es por directorio (puede cubrir varios simbolos); lee una vez por dir
    build_seen = set()
    for d, sym, res in MANIFIESTOS:
        if d in build_seen:
            continue
        build_seen.add(d)
        p = TEMP / d / "build_report.json"
        br = json.loads(p.read_text(encoding="utf-8"))
        ct = br["counts"]
        summary["builder_h1"] += ct["h1"]
        summary["builder_h3"] += ct["h3"]
        summary["builder_h2ex"] += ct["h2ex"]
        summary["builder_h2rev"] += ct["h2rev"]
        summary["builder_placebo"] += ct["placebo"]
        summary["builder_excl_gap"] += ct["excluded_gap"]
        summary["builder_excl_no_entry"] += ct["excluded_no_entry"]
        summary["builder_excl_h2_nc"] += ct["excluded_h2_no_confirmation"]
        summary["builder_excl_h2_rec"] += ct["excluded_h2_reclaim"]

    # Selection counts (de los 6 selection_*.json)
    for d, sym, res in MANIFIESTOS:
        p = TEMP / d / ("selection_%s_%s.json" % (sym, res))
        s = json.loads(p.read_text(encoding="utf-8"))
        summary["selection_n_in"] += s["n_in"]
        summary["selection_dev"] += s["n_dev"]
        summary["selection_oos"] += s["n_oos"]
        summary["selection_purged"] += s["n_purged_dev_crossing"]

    # Direccionales admitidas (builder, sin baseline)
    builder_dir = (summary["builder_h1"] + summary["builder_h3"] +
                   summary["builder_h2ex"] + summary["builder_h2rev"])
    builder_excl = (summary["builder_excl_gap"] + summary["builder_excl_no_entry"] +
                    summary["builder_excl_h2_nc"] + summary["builder_excl_h2_rec"])
    # 9320 = builder_dir + builder_excl ?

    reporte = {
        "procedencia": {
            "artefacto": str(ARTIFACT),
            "artefacto_sha256": "2b74a841...d37060 (ver en commit 1385927)",
            "manifiestos_temp": [
                str(TEMP / d / ("manifest_%s_%s.json" % (s, r)))
                for d, s, r in MANIFIESTOS
            ],
            "temp_limitacion": "Manifiestos intermedios en temp/opencode (fuera de Git). "
                               "Reproducir requiere ejecutar el pipeline desde historical.db "
                               "(read-only) con reconstruct_causal_census.py + build_census_eval_inputs.py + "
                               "select_eval_events.py + run_family_evaluation.py.",
        },
        "builder": {
            "h1_direccional": summary["builder_h1"],
            "h3_direccional": summary["builder_h3"],
            "h2ex_fade": summary["builder_h2ex"],
            "h2rev_fade": summary["builder_h2rev"],
            "placebo": summary["builder_placebo"],
            "excluidos_gap": summary["builder_excl_gap"],
            "excluidos_no_entry": summary["builder_excl_no_entry"],
            "excluidos_h2_no_confirmacion": summary["builder_excl_h2_nc"],
            "excluidos_h2_reclaim": summary["builder_excl_h2_rec"],
            "total_excluidos_builder": builder_excl,
            "total_admitidas_direccionales": builder_dir,
            "total_eventos_events_json": builder_dir + summary["builder_placebo"],
        },
        "selection_purge": {
            "n_in": summary["selection_n_in"],
            "n_dev": summary["selection_dev"],
            "n_oos": summary["selection_oos"],
            "n_purged_dev_crossing": summary["selection_purged"],
        },
        "artefacto_final": {
            "eventos_total": summary["art_events"],
            "trades_total": summary["art_trades"],
            "abiertas_total": summary["art_open"],
            "skipped_overlap_total": summary["art_skipped"],
        },
        "mfe_mae_rango": {
            "mfe_min_pct": round(summary["mfe_min"], 6) if summary["mfe_min"] is not None else None,
            "mfe_max_pct": round(summary["mfe_max"], 6) if summary["mfe_max"] is not None else None,
            "mae_min_pct": round(summary["mae_min"], 6) if summary["mae_min"] is not None else None,
            "mae_max_pct": round(summary["mae_max"], 6) if summary["mae_max"] is not None else None,
        },
        "funding_resumen_1x": {
            "settled_events_total": summary["funding_settled_1x"],
            "unknown_excluded_total": summary["funding_unknown_1x"],
            "uncovered_ms_total": summary["funding_uncovered_ms_1x"],
            "gap_ms_total": summary["funding_gap_ms_1x"],
            "celdas_con_uncovered": summary["cells_uncovered"],
            "celdas_totales": summary["cells_total"],
        },
        "filas": filas,
    }

    OUT.write_text(json.dumps(reporte, indent=2, default=str), encoding="utf-8")
    print("reporte escrito en", OUT)
    print("builder_dir=%d builder_excl=%d builder_dir+excl=%d (esperado 9320)" % (
        builder_dir, builder_excl, builder_dir + builder_excl))
    print("selection_n_in=%d (esperado 14334 = 2 x 7167)" % summary["selection_n_in"])
    print("artefacto: eventos=%d trades=%d abiertas=%d skipped=%d" % (
        summary["art_events"], summary["art_trades"], summary["art_open"], summary["art_skipped"]))
    print("funding: settled=%d unknown=%d uncovered_ms=%d gap_ms=%d celdas_uncovered=%d/%d" % (
        summary["funding_settled_1x"], summary["funding_unknown_1x"],
        summary["funding_uncovered_ms_1x"], summary["funding_gap_ms_1x"],
        summary["cells_uncovered"], summary["cells_total"]))
    print("MFE rango: %s a %s" % (summary["mfe_min"], summary["mfe_max"]))
    print("MAE rango: %s a %s" % (summary["mae_min"], summary["mae_max"]))


if __name__ == "__main__":
    main()
