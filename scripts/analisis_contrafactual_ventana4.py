# -*- coding: utf-8 -*-
"""Analisis contrafactual individual de la ventana 4 (offline, sin mercado).

Evalua cada una de las 161 observaciones aptas de `exp-v2-ventana-4-20261116a`
como un escenario independiente con capacidad 1 aislada, reutilizando el
adaptador y el motor existentes (`research_operativo_adapter`,
`paper_lab_engine`, `backtest_offline`). No rellena velas ni calendarios: usa
exclusivamente los cuerpos originales de `consultas_klines.jsonl` y la
configuracion congelada.

Etiqueta: "evaluacion contrafactual individual, posterior a la captura; no
validacion prospectiva independiente".

Salida (derivado, fuera de Git):
  C:/proyectos/binance-futures-data/exp-v2-ventana-4-20261116a-analisis-contrafactual-20261116/
    resumen_ejecutivo.json
    escenarios_por_fila.jsonl (161 filas)
    replay_historico_compartido.jsonl
"""

from __future__ import annotations

import json
import io
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

ROOT = Path(r"C:\proyectos\binance-futures-microstructure-bot")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from microstructure_probe.paper_lab_engine import PaperCandle
from research_operativo_adapter import OperativoAdapter, OperativoConfig

RUN = Path(r"C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a")
DERIVED = Path(
    r"C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-analisis-contrafactual-20261116"
)
DERIVED.mkdir(parents=True, exist_ok=True)

cfg = OperativoConfig()  # congelada: fee 5 bps, spread 1, slip 2, stop 0.5%, horizonte 60 min


def utc_iso(ms: Optional[int]) -> Optional[str]:
    if ms is None:
        return None
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()


def velas_de_klines(cuerpo_json: str) -> list:
    rows = json.loads(cuerpo_json)
    out = []
    for r in rows:
        out.append(PaperCandle(
            open_time_ms=int(r[0]), open=float(r[1]), high=float(r[2]),
            low=float(r[3]), close=float(r[4]),
            close_time_ms=int(r[6]) if r[6] is not None else None,
        ))
    return out


# ---------- 1. Cargar fuentes ----------
observaciones = {}  # observation_id -> obs (kind=observacion, apta)
for line in io.open(RUN / "observaciones.jsonl", encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    o = json.loads(line)
    if o.get("kind") == "observacion" and o.get("apto_para_evaluacion") is True:
        observaciones[o["observation_id"]] = o

klines = {}  # observation_id -> cuerpo klines
for line in io.open(RUN / "consultas_klines.jsonl", encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    o = json.loads(line)
    klines[o["observation_id"]] = o

resultado_historico = {}  # observation_id -> fila resultado (todas, para comparar)
for line in io.open(RUN / "resultado_operativo.jsonl", encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    o = json.loads(line)
    if o.get("kind") == "resultado_operativo":
        resultado_historico.setdefault(o["observation_id"], []).append(o)

print(f"observaciones aptas: {len(observaciones)}")
print(f"consultas_klines: {len(klines)}")
print(f"filas resultado historico: {sum(len(v) for v in resultado_historico.values())} "
      f"(observation_id unicos: {len(resultado_historico)})")

# ---------- 2. Replay historico compartido (capacidad 1, orden real) ----------
# Orden efectivo del recorrido: (decision_ms, symbol, observation_id).
orden_historico = sorted(
    observaciones.values(),
    key=lambda o: (int(o["decision_ms"]), str(o["symbol"]), str(o["observation_id"])),
)

ad_hist = OperativoAdapter(
    store_path=DERIVED / "replay_historico_compartido.jsonl", cfg=cfg)
resultados_hist = {}
for o in orden_historico:
    oid = o["observation_id"]
    velas = velas_de_klines(klines[oid]["cuerpo"])
    tr = ad_hist.procesar_observacion(o, velas, funding_calendar=None)
    resultados_hist[oid] = tr
ad_hist.close()

n_ent_hist = sum(1 for tr in resultados_hist.values() if tr.decision == "ENTRADA_EJECUTADA")
n_rech_hist = sum(1 for tr in resultados_hist.values()
                  if tr.decision == "RECHAZADA_CAPACIDAD")
n_abst_hist = sum(1 for tr in resultados_hist.values()
                  if tr.decision == "SIN_ENTRADA")
print(f"\nReplay historico compartido: entradas={n_ent_hist} rechazos_capacidad={n_rech_hist} "
      f"abstenciones={n_abst_hist} total={len(resultados_hist)}")

# Intervalos de ocupacion del replay historico (para la reconstruccion de capacidad)
intervalos_hist = ad_hist.intervalos_ocupados()
print("Intervalos de ocupacion historico (oid, entry_ms, exit_ms):")
for oid, e, x in intervalos_hist:
    print(f"  {oid}: entrada {utc_iso(e)} -> salida {utc_iso(x)}")

# ---------- 3. Evaluacion contrafactual individual (aislada, capacidad 1 cada una) ----------
escenarios = []
for oid, o in observaciones.items():
    velas = velas_de_klines(klines[oid]["cuerpo"])
    store = DERIVED / f"escenario_{oid.replace('|', '_')}.jsonl"
    if store.exists():
        store.unlink()
    ad = OperativoAdapter(store_path=store, cfg=cfg)
    try:
        tr = ad.procesar_observacion(o, velas, funding_calendar=None)
    finally:
        ad.close()

    # fila historica correspondiente (para control de coherencia)
    filas_hist = resultado_historico.get(oid, [])
    hist = filas_hist[0] if filas_hist else None

    escenarios.append({
        "observation_id": oid,
        "symbol": o["symbol"],
        "role": o.get("role"),
        "decision_ms": int(o["decision_ms"]),
        "decision_iso": o.get("decision_iso"),
        "side_selector": o.get("side"),
        "move_24h_pct": (o.get("seleccion") or {}).get("move_24h_pct"),
        "precio_base": o.get("precio_base"),
        "ciclo": int((int(o["decision_ms"]) - 1794857178038) // 300000),
        # resultado contrafactual (aislado)
        "decision_cf": tr.decision,
        "direction": tr.direction,
        "entry_px_cf": tr.entry_px,
        "entry_ms_cf": tr.entry_ms,
        "stop_px_cf": tr.stop_px,
        "exit_px_cf": tr.exit_px,
        "exit_ms_cf": tr.exit_ms,
        "exit_reason_cf": tr.exit_reason,
        "exit_executed_cf": tr.exit_executed,
        "open_at_end_cf": tr.open_at_end,
        "qty_cf": tr.qty,
        "gross_pnl_cf": tr.gross_pnl,
        "fees_cf": tr.fees,
        "spread_slip_cf": tr.spread_slip,
        "net_pnl_cf": tr.net_pnl,
        "funding_estado_cf": tr.funding_estado,
        # resultado historico (para comparar)
        "decision_hist": (hist.get("decision") if hist else None),
        "entry_px_hist": (hist.get("entry_px") if hist else None),
        "stop_px_hist": (hist.get("stop_px") if hist else None),
        "exit_px_hist": (hist.get("exit_px") if hist else None),
        "exit_reason_hist": (hist.get("exit_reason") if hist else None),
        "net_pnl_hist": (hist.get("net_pnl") if hist else None),
        "coherente_numerico": None,  # se rellena abajo
    })

# Control de coherencia: las 2 operaciones historicas deben conservar valores
for esc in escenarios:
    if esc["decision_hist"] == "ENTRADA_EJECUTADA":
        ok = (
            esc["entry_px_cf"] == esc["entry_px_hist"]
            and esc["stop_px_cf"] == esc["stop_px_hist"]
            and esc["exit_px_cf"] == esc["exit_px_hist"]
            and esc["exit_reason_cf"] == esc["exit_reason_hist"]
            and abs((esc["net_pnl_cf"] or 0) - (esc["net_pnl_hist"] or 0)) < 1e-9
        )
        esc["coherente_numerico"] = bool(ok)

# ---------- 4. Escritura de escenarios fila a fila ----------
esc_jsonl = DERIVED / "escenarios_por_fila.jsonl"
with io.open(esc_jsonl, "w", encoding="utf-8", newline="\n") as f:
    for esc in escenarios:
        f.write(json.dumps(esc, ensure_ascii=False, sort_keys=True) + "\n")

# ---------- 5. Agregados ----------
def usd(x):
    return None if x is None else round(float(x), 6)

red = [e for e in escenarios if e["decision_cf"] == "ENTRADA_EJECUTADA"]
rej = [e for e in escenarios if e["decision_cf"] == "RECHAZADA_CAPACIDAD"]
abst = [e for e in escenarios if e["decision_cf"] == "SIN_ENTRADA"]
desc = [e for e in escenarios if e["decision_cf"] == "DESCARTADO"]

netos = [e["net_pnl_cf"] for e in red if e["net_pnl_cf"] is not None]
brutos = [e["gross_pnl_cf"] for e in red if e["gross_pnl_cf"] is not None]

def stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"n": 0, "suma": None, "media": None, "mediana": None,
                "min": None, "max": None, "ganadoras": 0, "perdedoras": 0}
    gan = sum(1 for v in vals if v > 0)
    per = sum(1 for v in vals if v < 0)
    return {
        "n": len(vals),
        "suma": round(sum(vals), 6),
        "media": round(sum(vals) / len(vals), 6),
        "mediana": round(median(vals), 6),
        "min": round(min(vals), 6),
        "max": round(max(vals), 6),
        "ganadoras": gan,
        "perdedoras": per,
    }

def agrupar(clave_fn):
    grupos = {}
    for e in escenarios:
        grupos.setdefault(clave_fn(e), []).append(e)
    out = {}
    for k, items in sorted(grupos.items()):
        ent = [e for e in items if e["decision_cf"] == "ENTRADA_EJECUTADA"]
        netos_g = [e["net_pnl_cf"] for e in ent if e["net_pnl_cf"] is not None]
        out[k] = {
            "aptas": len(items),
            "entradas_simulables": len(ent),
            "rechazos_capacidad_hist": sum(
                1 for e in items if e["decision_hist"] == "RECHAZADA_CAPACIDAD"),
            "entradas_hist": sum(
                1 for e in items if e["decision_hist"] == "ENTRADA_EJECUTADA"),
            "neto_conditionado": stats(netos_g),
        }
    return out

resumen = {
    "source_run_id": "exp-v2-ventana-4-20261116a",
    "origen": "evaluacion contrafactual individual posterior a la captura (no validacion prospectiva)",
    "metodo": "cada senal apta evaluada en aislamiento con capacidad 1, reutilizando OperativoAdapter y paper_lab_engine; datos fuente sin modificar",
    "config_operativa": {
        "fee_bps": cfg.fee_bps, "spread_bps": cfg.spread_bps,
        "slippage_bps": cfg.slippage_bps, "stop_distance_pct": cfg.stop_distance_pct,
        "horizon_ms": cfg.horizon_ms, "notional_usdt": cfg.notional_usdt,
        "max_concurrent": cfg.max_concurrent, "rule_version": cfg.rule_version,
    },
    "denominador": {
        "observaciones_aptas": len(escenarios),
        "evaluadas": len(escenarios),
        "sin_observacion_no_entran_en_denominador": True,
    },
    "replay_historico_compartido": {
        "entradas": n_ent_hist,
        "rechazos_capacidad": n_rech_hist,
        "abstenciones": n_abst_hist,
        "total": len(resultados_hist),
        "intervalos_ocupacion": [
            {"observation_id": oid, "entrada_ms": e, "salida_ms": x,
             "entrada_iso": utc_iso(e), "salida_iso": utc_iso(x)}
            for oid, e, x in intervalos_hist],
    },
    "contrafactual_aislado": {
        "entradas_simulables": len(red),
        "rechazadas_por_capacidad_en_historial_pero_simulables_aisladas": len(
            [e for e in escenarios if e["decision_cf"] == "ENTRADA_EJECUTADA"
             and e["decision_hist"] == "RECHAZADA_CAPACIDAD"]),
        "ocultadas_por_capacidad_con_resultado_positivo": len(
            [e for e in escenarios if e["decision_cf"] == "ENTRADA_EJECUTADA"
             and e["decision_hist"] == "RECHAZADA_CAPACIDAD"
             and (e["net_pnl_cf"] or 0) > 0]),
        "ocultadas_por_capacidad_con_resultado_negativo": len(
            [e for e in escenarios if e["decision_cf"] == "ENTRADA_EJECUTADA"
             and e["decision_hist"] == "RECHAZADA_CAPACIDAD"
             and (e["net_pnl_cf"] or 0) < 0]),
        "abstenciones": len(abst),
        "descartes": len(desc),
        "sin_salida_acreditada_open_at_end": len(
            [e for e in red if e["open_at_end_cf"]]),
    },
    "resultado_usdt_contrafactual": {
        "neto_conditionado": stats(netos),
        "bruto": stats(brutos),
        "comisiones_totales": round(sum(e["fees_cf"] or 0 for e in red), 6),
        "spread_slip_total": round(sum(e["spread_slip_cf"] or 0 for e in red), 6),
        "neto_completo": {"n": 0, "suma": None, "media": None, "mediana": None,
                          "min": None, "max": None},
        "funding_completo_n": 0,
        "funding_desconocido_n": len(red),
    },
    "por_rol": agrupar(lambda e: e["role"]),
    "por_direccion": agrupar(lambda e: e["direction"] or "sin_direccion"),
    "por_ciclo": agrupar(lambda e: f"ciclo{e['ciclo']:02d}"),
    "control_coherencia": {
        "operaciones_historicas_admitidas": 2,
        "coherentes_numericamente": sum(
            1 for e in escenarios if e["coherente_numerico"] is True),
        "con_diferencia_numerica": sum(
            1 for e in escenarios if e["coherente_numerico"] is False),
        "detalle": [
            {"observation_id": e["observation_id"], "symbol": e["symbol"],
             "net_pnl_cf": e["net_pnl_cf"], "net_pnl_hist": e["net_pnl_hist"],
             "coherente": e["coherente_numerico"]}
            for e in escenarios if e["decision_hist"] == "ENTRADA_EJECUTADA"
        ],
    },
}

with io.open(DERIVED / "resumen_ejecutivo.json", "w", encoding="utf-8",
             newline="\n") as f:
    json.dump(resumen, f, ensure_ascii=False, indent=1, sort_keys=True)

print("\n=== RESUMEN EJECUTIVO ===")
print(json.dumps(resumen, ensure_ascii=False, indent=1)[:6000])
print("\nEscritos:", esc_jsonl, DERIVED / "resumen_ejecutivo.json")
