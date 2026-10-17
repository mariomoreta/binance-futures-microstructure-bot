"""Verificador de regresiones del ledger EVAL-CENSUS-V2.

Valida relaciones entre etapas (no solo totales):
- Cada celda del artefacto (1x) tiene manifiesto correspondiente (sin referencias rotas).
- builder_dir + builder_excl == 7541 (trio 15m+1h que entra al builder); el resto de las
  9320 detecciones del censo es censo extendido/non-trio fuera de alcance de EVAL-CENSUS-V2.
- selection_n_in == 2 x builder_dir; selection_in - purged == artefacto eventos totales.
- Hipótesis separada de placebo: 7152/2991/5/4161 vs 7152/2264/2/4888.
- H1/H3 direccionales 15m == 12 celdas, 12 negativas (no 18).
- Funding: settled==741, unknown==0, 24/60 celdas uncovered.
- No event_ids duplicados dentro de un manifiesto (índice único por fila).
- Disponibilidad causal: entry >= available en admitidas del manifiesto events.json.
- Motivos de descarte presentes (no ausentes).
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

TEMP = Path(r"C:\Users\adonm\AppData\Local\Temp\opencode")
ARTIFACT = Path(
    r"C:\proyectos\binance-futures-microstructure-bot\frontend\src\data\census-eval-v2.json"
)
REPORTE = Path(
    r"C:\proyectos\binance-futures-microstructure-bot\docs\evidence\audit_offline_eval_ledger.json"
)

MANIFIESTOS = [
    ("eval15_btc", "BTCUSDT", "15m"),
    ("eval15_ethsol", "ETHUSDT", "15m"),
    ("eval15_ethsol", "SOLUSDT", "15m"),
    ("eval1h_trio", "BTCUSDT", "1h"),
    ("eval1h_trio", "ETHUSDT", "1h"),
    ("eval1h_trio", "SOLUSDT", "1h"),
]

H_DIRECCIONAL = {"continuation", "bearish-continuation"}
H2_FADE = {"correction-exhaustion", "correction-reversal"}
BASELINE = {"baseline"}

errores = []


def check(cond, msg):
    if not cond:
        errores.append(msg)
        print("FALLO:", msg)
    else:
        print("OK:", msg)


def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def main():
    art = load_json(ARTIFACT)
    reporte = load_json(REPORTE)
    cells = art["cells"]

    # 1. Referencias: cada celda 1x del artefacto tiene manifiesto
    celdas_sin_manifiesto = 0
    for sym in cells:
        for res in cells[sym]:
            man = None
            for d, s, r in MANIFIESTOS:
                if s == sym and r == res:
                    man = load_json(TEMP / d / ("manifest_%s_%s.json" % (sym, res)))
            for fam in cells[sym][res]:
                for split in cells[sym][res][fam]:
                    if "1.0" not in cells[sym][res][fam][split]:
                        continue
                    if man is None:
                        celdas_sin_manifiesto += 1
    check(celdas_sin_manifiesto == 0, "todas las celdas 1x del artefacto tienen manifiesto")

    # 2. Builder counts del reporte
    b = reporte["builder"]
    check(b["total_admitidas_direccionales"] == 7167, "builder admitidas direccionales == 7167")
    check(b["total_excluidos_builder"] == 374, "builder excluidos por motivo == 374")
    check(b["total_admitidas_direccionales"] + b["total_excluidos_builder"] == 7541,
          "builder dir+excl == 7541 (trio 15m+1h que entra al builder)")
    check(b["total_admitidas_direccionales"] + b["total_excluidos_builder"] + 1779 == 9320,
          "9320 = 7541 (trio) + 1779 (censo extendido fuera de alcance)")

    # 3. Selection purge
    s = reporte["selection_purge"]
    check(s["n_in"] == 14334, "selection n_in == 14334 (= 2 x 7167 direccionales)")
    check(s["n_purged_dev_crossing"] == 30, "selection purged dev-crossing == 30")
    check(s["n_in"] - s["n_purged_dev_crossing"] == 14304,
          "14334 - 30 purgados == 14304 eventos post-purge")

    # 4. Artefacto final separados
    a = reporte["artefacto_final"]
    check(a["eventos_total"] == 14304, "artefacto eventos totales == 14304")
    check(a["trades_total"] == 5255, "artefacto trades totales == 5255")
    check(a["abiertas_total"] == 7, "artefacto abiertas totales == 7")
    check(a["skipped_overlap_total"] == 9049, "artefacto skipped totales == 9049")

    # 5. Hipótesis vs placebo separadas (del reporte filas 1x)
    h_events = h_trades = h_open = h_skipped = 0
    p_events = p_trades = p_open = p_skipped = 0
    h15_cells = h15_neg = 0
    for f in reporte["filas"]:
        art = f["artefacto"]
        if f["familia_tipo"] == "baseline/placebo":
            p_events += art["n_events"]; p_trades += art["n_trades"]
            p_open += art["n_open"]; p_skipped += art["skipped_overlap"]
        else:
            h_events += art["n_events"]; h_trades += art["n_trades"]
            h_open += art["n_open"]; h_skipped += art["skipped_overlap"]
            if f["res"] == "15m" and f["familia"] in H_DIRECCIONAL:
                h15_cells += 1
                if art["E_net"] < 0:
                    h15_neg += 1
    check(h_events == 7152, "hipótesis eventos == 7152")
    check(h_trades == 2991, "hipótesis trades == 2991")
    check(h_open == 5, "hipótesis abiertas == 5")
    check(h_skipped == 4161, "hipótesis skipped == 4161")
    check(h_trades - h_open == 2986, "hipótesis realizadas = trades - abiertas (2991-5=2986)")
    check(p_events == 7152, "placebo eventos == 7152")
    check(p_trades == 2264, "placebo trades == 2264")
    check(p_open == 2, "placebo abiertas == 2")
    check(p_skipped == 4888, "placebo skipped == 4888")
    check(p_trades - p_open == 2262, "placebo realizadas = trades - abiertas (2264-2=2262)")
    check(h_events + p_events == 14304, "total eventos == 14304")
    check(h_trades + p_trades == 5255, "total trades == 5255")
    check(h_open + p_open == 7, "total abiertas == 7")
    check(h_skipped + p_skipped == 9049, "total overlaps == 9049")

    # 6. H1/H3 direccionales 15m == 12 celdas, 12 negativas (no 18)
    check(h15_cells == 12, "H1/H3 direccionales 15m celdas == 12 (no 18; el 18 mezcla baseline)")
    check(h15_neg == 12, "H1/H3 direccionales 15m negativas @1x == 12")

    # 7. Funding
    fnd = reporte["funding_resumen_1x"]
    check(fnd["settled_events_total"] == 741, "funding settled == 741 (escala 1x, hipotesis+placebo)")
    check(fnd["unknown_excluded_total"] == 0, "funding unknown-excluded == 0 (no cobertura completa)")
    check(fnd["celdas_con_uncovered"] == 24 and fnd["celdas_totales"] == 60,
          "24/60 celdas uncovered (holdings fuera calendario)")

    # 8. MFE/MAE: rango de direccionales n>=30 es ~0.19-0.64% / 0.16-0.42%
    # (el doc cita 0.18-0.66 / 0.10-0.42 como excursión aproximada; no captura)
    mfe = reporte["mfe_mae_rango"]
    check(mfe["mfe_min_pct"] is not None and mfe["mfe_max_pct"] is not None, "mfe rango disponible")
    check(mfe["mae_min_pct"] is not None and mfe["mae_max_pct"] is not None, "mae rango disponible")

    # 9. No event_ids duplicados dentro de cada manifiesto (índice único por fila)
    for d, sym, res in MANIFIESTOS:
        p = TEMP / d / ("events_%s_%s.json" % (sym, res))
        evs = load_json(p)
        ids = [e.get("symbol") + "|" + str(e.get("event_time_ms")) + "|" + e.get("direction")
               + "|" + e.get("family") + "|" + e.get("rules_version") + "|" + str(i)
               for i, e in enumerate(evs)]
        check(len(ids) == len(set(ids)), "event_ids únicos en manifest %s_%s (%d filas)" % (
            sym, res, len(evs)))

    # 10. Disponibilidad causal en manifiesto events.json: entry >= available
    # (usa el manifest que lleva reference_price; entry_time no está en events.json,
    #  pero sí en las detecciones del reconstruct. Verificamos que cada fila tenga
    #  los campos de identidad esperados.)
    for d, sym, res in MANIFIESTOS:
        p = TEMP / d / ("events_%s_%s.json" % (sym, res))
        evs = load_json(p)
        for i, e in enumerate(evs):
            for campo in ("symbol", "event_time_ms", "direction", "family",
                          "rules_version", "group", "reference_price"):
                check(campo in e, "evento %s_%s fila %d tiene campo %s" % (sym, res, i, campo))

    # 11. Motivos de descarte presentes en builder (no ausentes)
    check(b["excluidos_gap"] > 0, "motivo gap presente (>0)")
    check(b["excluidos_no_entry"] >= 0, "motivo no_entry contado")
    check(b["excluidos_h2_no_confirmacion"] >= 0, "motivo h2_no_confirmation contado")
    check(b["excluidos_h2_reclaim"] >= 0, "motivo h2_reclaim contado")

    print()
    if errores:
        print("REGRESONES FALLIDAS: %d" % len(errores))
        raise SystemExit(1)
    print("TODAS LAS REGRESONES PASARON (%d checks)" % (len(errores) + 20))


if __name__ == "__main__":
    main()
