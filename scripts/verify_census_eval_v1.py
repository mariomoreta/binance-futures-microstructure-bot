"""Verificación reproducible de EVAL-CENSUS-V2 desde census-eval-v2.json.

Recalcula celdas 1x separando:
  - H1/H3 direccionales (continuation + bearish-continuation)
  - H2 fade (correction-exhaustion + correction-reversal)
  - baseline/placebo (comparator, NO direccional)

No mezcla placebo en los conteos de hipótesis. No modera umbrales ni reglas.
Lee solo el artefacto publicado en frontend/src/data/census-eval-v2.json.
"""
import json
from collections import defaultdict
from pathlib import Path

ARTIFACT = Path(__file__).resolve().parents[1] / "frontend" / "src" / "data" / "census-eval-v2.json"

H_DIRECCIONAL = {"continuation", "bearish-continuation"}   # H1 + H3
H2_FADE = {"correction-exhaustion", "correction-reversal"}   # H2 fade
BASELINE = {"baseline"}                                       # placebo comparator


def fam_label(g):
    if g in H_DIRECCIONAL:
        return "H1/H3 direccional"
    if g in H2_FADE:
        return "H2 fade"
    if g in BASELINE:
        return "baseline/placebo"
    return g


def main():
    with open(ARTIFACT, encoding="utf-8") as f:
        d = json.load(f)

    cells = d["cells"]
    stats = defaultdict(lambda: {
        "n_events": 0, "n_trades": 0, "n_open": 0,
        "skipped": 0, "cells": 0, "neg_cells": 0,
    })

    for sym in cells:
        for res in cells[sym]:
            for fam in cells[sym][res]:
                for split in cells[sym][res][fam]:
                    if "1.0" not in cells[sym][res][fam][split]:
                        continue
                    c = cells[sym][res][fam][split]["1.0"]
                    k = (sym, res, fam_label(fam), split)
                    s = stats[k]
                    s["n_events"] += c["n_events"]
                    s["n_trades"] += c["n_trades"]
                    s["n_open"] += c["n_open"]
                    s["skipped"] += c["skipped_overlap"]
                    s["cells"] += 1
                    if c["E_net"] < 0:
                        s["neg_cells"] += 1

    print("=== TABLA 1x POR SIMBOLO / RES / FAMILIA / SEGMENTO ===")
    print(f"{'Symbol':<10} {'Res':<5} {'Familia':<22} {'Segmento':<6} {'Events':>7} {'Trades':>7} {'Open':>5} {'Skipped':>8} {'Cells':>5} {'NegCells':>8}")

    tot_h = {"events": 0, "trades": 0, "open": 0, "skipped": 0}
    tot_p = {"events": 0, "trades": 0, "open": 0, "skipped": 0}

    for k in sorted(stats.keys()):
        s = stats[k]
        print(f"{k[0]:<10} {k[1]:<5} {k[2]:<22} {k[3]:<6} "
              f"{s['n_events']:>7} {s['n_trades']:>7} {s['n_open']:>5} "
              f"{s['skipped']:>8} {s['cells']:>5} {s['neg_cells']:>8}")
        dst = tot_p if k[2] == "baseline/placebo" else tot_h
        dst["events"] += s["n_events"]
        dst["trades"] += s["n_trades"]
        dst["open"] += s["n_open"]
        dst["skipped"] += s["skipped"]

    print("\n=== HIPOTESIS (1x, excluye baseline/placebo) ===")
    print(f"eventos={tot_h['events']} trades={tot_h['trades']} abiertas={tot_h['open']} "
          f"skipped_overlap={tot_h['skipped']} realizadas={tot_h['trades']-tot_h['open']}")

    print("\n=== PLACEBO/BASELINE (1x) ===")
    print(f"eventos={tot_p['events']} trades={tot_p['trades']} abiertas={tot_p['open']} "
          f"skipped_overlap={tot_p['skipped']} realizadas={tot_p['trades']-tot_p['open']}")

    print("\n=== TOTAL COMBINADO ===")
    print(f"eventos={tot_h['events']+tot_p['events']} "
          f"trades={tot_h['trades']+tot_p['trades']} "
          f"abiertas={tot_h['open']+tot_p['open']} "
          f"overlaps={tot_h['skipped']+tot_p['skipped']}")

    # H1/H3 direccionales 15m @1x
    h15_cells = h15_neg = 0
    h15_e = h15_t = h15_o = h15_s = 0
    for sym in cells:
        if "15m" not in cells[sym]:
            continue
        for fam in cells[sym]["15m"]:
            if fam not in H_DIRECCIONAL:
                continue
            for split in cells[sym]["15m"][fam]:
                if "1.0" not in cells[sym]["15m"][fam][split]:
                    continue
                c = cells[sym]["15m"][fam][split]["1.0"]
                h15_cells += 1
                h15_e += c["n_events"]; h15_t += c["n_trades"]
                h15_o += c["n_open"]; h15_s += c["skipped_overlap"]
                if c["E_net"] < 0:
                    h15_neg += 1

    print("\n=== H1/H3 DIRECCIONALES 15m @1x (SIN baseline) ===")
    print(f"celdas={h15_cells} negativas={h15_neg} eventos={h15_e} "
          f"trades={h15_t} abiertas={h15_o} skipped={h15_s}")

    # Verificaciones automáticas de sumas
    assert tot_h["events"] == 7152, f"hipótesis eventos {tot_h['events']} != 7152"
    assert tot_h["trades"] == 2991, f"hipótesis trades {tot_h['trades']} != 2991"
    assert tot_h["open"] == 5, f"hipótesis abiertas {tot_h['open']} != 5"
    assert tot_h["skipped"] == 4161, f"hipótesis skipped {tot_h['skipped']} != 4161"
    assert tot_p["events"] == 7152, f"placebo eventos {tot_p['events']} != 7152"
    assert tot_p["trades"] == 2264, f"placebo trades {tot_p['trades']} != 2264"
    assert tot_p["open"] == 2, f"placebo abiertas {tot_p['open']} != 2"
    assert tot_p["skipped"] == 4888, f"placebo skipped {tot_p['skipped']} != 4888"
    assert tot_h["events"] + tot_p["events"] == 14304, "total eventos != 14304"
    assert tot_h["trades"] + tot_p["trades"] == 5255, "total trades != 5255"
    assert tot_h["open"] + tot_p["open"] == 7, "total abiertas != 7"
    assert tot_h["skipped"] + tot_p["skipped"] == 9049, "total overlaps != 9049"
    assert h15_cells == 12, f"H1/H3 15m celdas {h15_cells} != 12"
    assert h15_neg == 12, f"H1/H3 15m negativas {h15_neg} != 12"

    print("\n=== TODAS LAS COMPROBACIONES AUTOMÁTICAS PASARON ===")


if __name__ == "__main__":
    main()
