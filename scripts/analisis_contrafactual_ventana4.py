# -*- coding: utf-8 -*-
"""Analisis contrafactual individual de la ventana 4 (offline, sin mercado).

Evalua cada observacion apta de `exp-v2-ventana-4-20261116a` como un
escenario independiente con capacidad 1 aislada, reutilizando el adaptador y
el motor existentes (`research_operativo_adapter`, `paper_lab_engine`,
`backtest_offline`). Usa exclusivamente los cuerpos originales de
`consultas_klines.jsonl` y la configuracion persistida de la corrida.
No rellena velas ni calendarios; no usa OperativoConfig() por defecto.

Etiqueta de los derivados:
"evaluacion contrafactual individual, posterior a la captura; no
validacion prospectiva independiente".

Distincion de stops (verificada contra el motor):
- stop de REFERENCIA (config.stop_px, desde ref_close = close de la ultima
  vela 1m plenamente conocida en T). Se usa solo para la senal de entrada en
  T y la admision de riesgo. Persiste como stop_px en la fila resultado.
- stop EFECTIVO aplicado durante la posicion, calculado en
  backtest_offline._stop_px(avg) desde el precio de llenado (fill):
    LONG:  fill * (1 - stop_distance_pct/100)
    SHORT: fill * (1 + stop_distance_pct/100)
  Es el nivel que gobierna la salida real por stop; el campo stop_px
  persistido NO representa necesariamente el nivel aplicado durante la
  posicion.

Uso:
    python scripts/analisis_contrafactual_ventana4.py \
        --run-dir /proyectos/binance-futures-data/exp-v2-ventana-4-20261116a \
        --out-dir  /.../exp-v2-ventana-4-20261116a-analisis-contrafactual-20261116-v2
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
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

# Campos de OperativoConfig que se cargan desde operativo_config persistida.
CONFIG_FIELDS = [
    "version", "rule_version", "stop_distance_pct", "notional_usdt",
    "horizon_ms", "fee_bps", "spread_bps", "slippage_bps",
    "max_concurrent", "funding_calendar", "funding_estimated_bps",
    "max_symbols", "max_candidates", "max_comparators",
]


def utc_iso(ms):
    if ms is None:
        return None
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()


def sha256_json(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def velas_de_klines(cuerpo_json):
    rows = json.loads(cuerpo_json)
    out = []
    for r in rows:
        out.append(PaperCandle(
            open_time_ms=int(r[0]), open=float(r[1]), high=float(r[2]),
            low=float(r[3]), close=float(r[4]),
            close_time_ms=int(r[6]) if r[6] is not None else None,
        ))
    return out


def ref_close_desde_klines(cuerpo_json, decision_ms):
    """Close de la ultima vela 1m plenamente conocida en T (close_time <= T)."""
    mejor = None
    for r in json.loads(cuerpo_json):
        ct = int(r[6]) if r[6] is not None else None
        if ct is not None and ct <= decision_ms:
            if mejor is None or ct > mejor[0]:
                mejor = (ct, float(r[4]))
    return mejor[1] if mejor else None


def stop_efectivo_desde_fill(entry_px, direccion, stop_distance_pct):
    """Stop efectivo aplicado durante la posicion, desde el fill."""
    pct = stop_distance_pct / 100.0
    if direccion == "LONG":
        return entry_px * (1.0 - pct)
    if direccion == "SHORT":
        return entry_px * (1.0 + pct)
    return None


def _verificar_hash_declarado(declarado, valor, campo):
    """Valida que el hash declarado coincida con el recalculado.

    El hash es OBLIGATORIO: ausente, vacio o mal formado -> rechazo.
    Discordante -> rechazo. Nunca se reconstruye sin hash verificado.
    """
    if not declarado or not isinstance(declarado, str) or not declarado.strip():
        raise ValueError(
            f"configuracion invalida: {campo} ausente o vacio "
            "(hash obligatorio no presente)")
    hash_calculado = sha256_json(valor)
    if hash_calculado != declarado:
        raise ValueError(
            f"configuracion invalida: hash de {campo} no coincide "
            f"(declarado {declarado}, calculado {hash_calculado})")


def cargar_config_operativa(run_dir):
    """Carga y valida la configuracion persistida (config_inicial.json).

    Nunca usa OperativoConfig() por defecto. Valida los hashes de
    config y operativo_config contra sus campos sha256, ambos OBLIGATORIOS.
    Devuelve (OperativoConfig, info_config) o lanza ValueError.
    """
    cfg_path = run_dir / "config_inicial.json"
    if not cfg_path.exists():
        raise ValueError(
            "configuracion ausente: config_inicial.json no existe en el run-dir")
    with io.open(cfg_path, encoding="utf-8") as f:
        datos = json.load(f)
    if not isinstance(datos, dict):
        raise ValueError("configuracion invalida: config_inicial.json no es un objeto")
    config = datos.get("config")
    operativo_config = datos.get("operativo_config")
    if not isinstance(config, dict):
        raise ValueError("configuracion invalida: config ausente")
    if not isinstance(operativo_config, dict):
        raise ValueError("configuracion invalida: operativo_config ausente")
    # Hashes OBLIGATORIOS: ausente, vacio o discordante -> rechazo.
    _verificar_hash_declarado(datos.get("config_sha256"), config, "config")
    _verificar_hash_declarado(datos.get("operativo_config_sha256"),
                              operativo_config, "operativo_config")
    faltantes = [k for k in CONFIG_FIELDS if k not in operativo_config]
    if faltantes:
        raise ValueError(
            "configuracion incompleta: faltan campos "
            + ", ".join(faltantes))
    valores = {k: operativo_config[k] for k in CONFIG_FIELDS}
    cfg = OperativoConfig(**valores)
    info = {
        "config_sha256": datos.get("config_sha256"),
        "operativo_config_sha256": datos.get("operativo_config_sha256"),
        "operativo_config_hash": datos.get("operativo_config_hash"),
        "git_head": datos.get("git_head"),
        "run_id": datos.get("run_id"),
        "escrito_iso": datos.get("escrito_iso"),
        "pilot_version": datos.get("pilot_version"),
        "policy_version": datos.get("policy_version"),
        "protocolo": datos.get("protocol_version"),
    }
    return cfg, info


# ---------------------------------------------------------------------------
# Analisis
# ---------------------------------------------------------------------------

def analizar(run_dir: Path, out_dir: Path) -> dict:
    if not run_dir.exists():
        raise ValueError(f"run-dir inexistente: {run_dir}")
    for nombre in ("observaciones.jsonl", "consultas_klines.jsonl",
                   "config_inicial.json", "resultado_operativo.jsonl"):
        if not (run_dir / nombre).exists():
            raise ValueError(f"fuente necesaria ausente o corrupta: {nombre}")

    cfg, info_config = cargar_config_operativa(run_dir)

    observaciones = {}
    for line in io.open(run_dir / "observaciones.jsonl", encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        if (o.get("kind") == "observacion"
                and o.get("apto_para_evaluacion") is True):
            observaciones[o["observation_id"]] = o

    klines = {}
    for line in io.open(run_dir / "consultas_klines.jsonl", encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        klines[o["observation_id"]] = o

    resultado_historico = {}
    for line in io.open(run_dir / "resultado_operativo.jsonl", encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        if o.get("kind") == "resultado_operativo":
            resultado_historico.setdefault(o["observation_id"], []).append(o)

    T0 = 1794857178038  # started_ms de config_inicial de la ventana 4

    escenarios = []
    for oid, o in observaciones.items():
        if oid not in klines:
            # Fuente necesaria ausente para esta senal: limitacion, se cuenta
            # pero no se reconstruye economicamente.
            escenarios.append({
                "observation_id": oid, "symbol": o["symbol"],
                "role": o.get("role"), "decision_ms": int(o["decision_ms"]),
                "ciclo": int((int(o["decision_ms"]) - T0) // 300000),
                "limitacion": "fuente_klines_ausente",
                "reconstruido": False,
            })
            continue
        velas = velas_de_klines(klines[oid]["cuerpo"])
        store = out_dir / f"escenario_{oid.replace('|', '_')}.jsonl"
        if store.exists():
            store.unlink()
        ad = OperativoAdapter(store_path=store, cfg=cfg)
        try:
            tr = ad.procesar_observacion(o, velas, funding_calendar=None)
        finally:
            ad.close()
        filas_hist = resultado_historico.get(oid, [])
        hist = filas_hist[0] if filas_hist else None
        direccion = tr.direction
        # Stop de referencia (config.stop_px, desde ref_close) vs
        # stop efectivo aplicado durante la posicion (desde el fill).
        if direccion and tr.entry_px is not None:
            stop_efectivo = stop_efectivo_desde_fill(
                tr.entry_px, direccion, cfg.stop_distance_pct)
        else:
            stop_efectivo = None
        # Para salida por stop, el stop aplicado coincide con exit_px.
        stop_aplicado_en_salida = None
        if (direccion and tr.exit_executed
                and tr.exit_reason == "stop"
                and tr.exit_px is not None):
            stop_aplicado_en_salida = tr.exit_px
        escenarios.append({
            "observation_id": oid,
            "symbol": o["symbol"],
            "role": o.get("role"),
            "decision_ms": int(o["decision_ms"]),
            "decision_iso": o.get("decision_iso"),
            "side_selector": o.get("side"),
            "move_24h_pct": (o.get("seleccion") or {}).get("move_24h_pct"),
            "precio_base": o.get("precio_base"),
            "ciclo": int((int(o["decision_ms"]) - T0) // 300000),
            "reconstruido": True,
            # Contrafactual aislado
            "decision_cf": tr.decision,
            "direction": tr.direction,
            "entry_px_cf": tr.entry_px,
            "entry_ms_cf": tr.entry_ms,
            "stop_referencia_cf": tr.stop_px,  # config.stop_px (ref_close), observabilidad
            "stop_efectivo_aplicado_cf": stop_efectivo,  # desde el fill
            "stop_aplicado_en_salida_cf": stop_aplicado_en_salida,
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
            # Historico (para control de coherencia)
            "decision_hist": (hist.get("decision") if hist else None),
            "entry_px_hist": (hist.get("entry_px") if hist else None),
            "stop_px_hist": (hist.get("stop_px") if hist else None),
            "exit_px_hist": (hist.get("exit_px") if hist else None),
            "exit_reason_hist": (hist.get("exit_reason") if hist else None),
            "net_pnl_hist": (hist.get("net_pnl") if hist else None),
            "coherente_numerico": None,
        })

    # Control de coherencia: las operaciones historicas admitidas deben
    # conservar valores numericos al evaluarse individualmente.
    for esc in escenarios:
        if esc.get("reconstruido") and esc["decision_hist"] == "ENTRADA_EJECUTADA":
            ok = (
                esc["entry_px_cf"] == esc["entry_px_hist"]
                and esc["stop_px_hist"] == esc["stop_referencia_cf"]
                and esc["exit_px_cf"] == esc["exit_px_hist"]
                and esc["exit_reason_cf"] == esc["exit_reason_hist"]
                and abs((esc["net_pnl_cf"] or 0) - (esc["net_pnl_hist"] or 0)) < 1e-9
            )
            esc["coherente_numerico"] = bool(ok)

    # Escritura de escenarios fila a fila
    out_dir.mkdir(parents=True, exist_ok=True)
    esc_jsonl = out_dir / "escenarios_por_fila.jsonl"
    with io.open(esc_jsonl, "w", encoding="utf-8", newline="\n") as f:
        for esc in escenarios:
            f.write(json.dumps(esc, ensure_ascii=False, sort_keys=True) + "\n")

    # Agregados
    red = [e for e in escenarios if e.get("reconstruido")
           and e["decision_cf"] == "ENTRADA_EJECUTADA"]
    rej = [e for e in escenarios if e.get("reconstruido")
           and e["decision_cf"] == "RECHAZADA_CAPACIDAD"]
    abst = [e for e in escenarios if e.get("reconstruido")
            and e["decision_cf"] == "SIN_ENTRADA"]
    desc = [e for e in escenarios if e.get("reconstruido")
            and e["decision_cf"] == "DESCARTADO"]
    sin_fuente = [e for e in escenarios if not e.get("reconstruido")]

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
            if not e.get("reconstruido"):
                continue
            grupos.setdefault(clave_fn(e), []).append(e)
        out = {}
        for k, items in sorted(grupos.items()):
            ent = [e for e in items if e["decision_cf"] == "ENTRADA_EJECUTADA"]
            netos_g = [e["net_pnl_cf"] for e in ent if e["net_pnl_cf"] is not None]
            out[k] = {
                "aptas": len(items),
                "entradas_simulables": len(ent),
                "entradas_hist": sum(
                    1 for e in items if e["decision_hist"]
                    == "ENTRADA_EJECUTADA"),
                "neto_conditionado": stats(netos_g),
            }
        return out

    resumen = {
        "source_run_id": "exp-v2-ventana-4-20261116a",
        "origen": ("evaluacion contrafactual individual posterior a la captura; "
                   "no validacion prospectiva independiente"),
        "metodo": ("cada senal apta evaluada en aislamiento con capacidad 1, "
                   "reutilizando OperativoAdapter y paper_lab_engine; datos "
                   "fuente sin modificar"),
        "config_acreditada": info_config,
        "config_operativa": {
            "fee_bps": cfg.fee_bps, "spread_bps": cfg.spread_bps,
            "slippage_bps": cfg.slippage_bps,
            "stop_distance_pct": cfg.stop_distance_pct,
            "horizon_ms": cfg.horizon_ms, "notional_usdt": cfg.notional_usdt,
            "max_concurrent": cfg.max_concurrent,
            "rule_version": cfg.rule_version,
        },
        "denominador": {
            "observaciones_aptas": len(escenarios),
            "reconstruidas": sum(1 for e in escenarios if e.get("reconstruido")),
            "sin_fuente_klines": len(sin_fuente),
        },
        "contrafactual_aislado": {
            "entradas_simulables": len(red),
            "rechazadas_por_capacidad_en_historial_pero_simulables_aisladas": len(
                [e for e in escenarios if e.get("reconstruido")
                 and e["decision_cf"] == "ENTRADA_EJECUTADA"
                 and e["decision_hist"] == "RECHAZADA_CAPACIDAD"]),
            "ocultadas_por_capacidad_con_resultado_positivo": len(
                [e for e in escenarios if e.get("reconstruido")
                 and e["decision_cf"] == "ENTRADA_EJECUTADA"
                 and e["decision_hist"] == "RECHAZADA_CAPACIDAD"
                 and (e["net_pnl_cf"] or 0) > 0]),
            "ocultadas_por_capacidad_con_resultado_negativo": len(
                [e for e in escenarios if e.get("reconstruido")
                 and e["decision_cf"] == "ENTRADA_EJECUTADA"
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
            "neto_completo": {"n": 0, "suma": None, "media": None,
                              "mediana": None, "min": None, "max": None},
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
                for e in escenarios if e.get("reconstruido")
                and e["decision_hist"] == "ENTRADA_EJECUTADA"],
        },
    }
    with io.open(out_dir / "resumen_ejecutivo.json", "w", encoding="utf-8",
                 newline="\n") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=1, sort_keys=True)
    return resumen


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Analisis contrafactual individual de la ventana 4 (offline).")
    parser.add_argument("--run-dir", required=True,
                        help="directorio fuente de la corrida (observaciones, "
                             "klines, config_inicial, resultado)")
    parser.add_argument("--out-dir", required=True,
                        help="directorio de derivados (se crea si no existe)")
    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir)
    out_dir = Path(args.out_dir)
    try:
        resumen = analizar(run_dir, out_dir)
    except ValueError as exc:
        print(json.dumps({"limitacion": str(exc)}), file=sys.stderr)
        return 3
    print(json.dumps({"estado": "ok", "out_dir": str(out_dir),
                      "resumen": resumen}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
