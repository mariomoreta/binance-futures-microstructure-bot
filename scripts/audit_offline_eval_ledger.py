"""Ledger de auditoría offline EVAL-CENSUS-V2 — portable.

Lee el artefacto versionado en Git (frontend/src/data/census-eval-v2.json)
y, si están disponibles, los manifiestos temporales fuera de Git
(temp/opencode/eval*_*/). No toca la red, ni DBs canónicas, ni módulos vivos.

Rutas: raíz del repo para el artefacto; argumentos explícitos o variable de
entorno para inputs externos. Sin rutas absolutas de usuario.

Calcula SHA256 de cada input utilizado. Separa hipotésis y placebo en
circuitos distintos. Valida esquema, familias permitidas, campos requeridos
y valores numéricos finitos. Rechaza inputs incompletos: si faltan inputs
críticos, el informe se marca INCOMPLETE y devuelve exit != 0.

Produces:
  docs/evidence/audit_offline_eval_ledger.json
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from argparse import ArgumentParser
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DEFAULT = ROOT / "frontend" / "src" / "data" / "census-eval-v2.json"
OUT_DEFAULT = ROOT / "docs" / "evidence" / "audit_offline_eval_ledger.json"

ALLOWED_FAMILIES = {"continuation", "bearish-continuation",
                     "correction-exhaustion", "correction-reversal",
                     "baseline", "rebound-variant"}
ALLOWED_SCALES = {"1.0", "2.0", "3.0"}
REQUIRED_ARTIFACT_FIELDS = ("n_events", "n_trades", "n_open",
                             "skipped_overlap", "E_net", "verdict")

H_DIRECCIONAL = {"continuation", "bearish-continuation"}   # H1 + H3
H2_FADE = {"correction-exhaustion", "correction-reversal"}   # H2 fade
BASELINE = {"baseline"}                                       # placebo


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _ruta_repo(p: Path) -> str:
    """Ruta relativa al repo si es posible; si no, absoluta (fixtures
    externos). Nunca rutas del usuario adonm en published defaults."""
    p = Path(p)
    try:
        return str(p.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(p)


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def finite_number(v) -> bool:
    return isinstance(v, (int, float)) and math.isfinite(float(v))


def family_kind(fam: str) -> str:
    if fam in H_DIRECCIONAL:
        return "H1/H3 direccional"
    if fam in H2_FADE:
        return "H2 fade"
    if fam in BASELINE:
        return "baseline/placebo"
    return fam


# ===========================================================================
# Verificaciones puras (testeables con fixtures; sin I/O ni efectos)
# Contrato causal real: MAP-CANDIDATE-v2 / ENTRY-SAME-GRID-v1
#   formation_time <= available_at <= entry_time_same_grid
#   H1/H3: evento @ formation_time. H2: evento @ barra de confirmación.
#   Placebo TIME-PLACEBO-v1: identidad propia, NO es detección original.
# ===========================================================================
H1_SRC_DEFS = {"MOMENTUM_ACCELERATION_UP", "EXTENDED_GAINER"}
H3_SRC_DEFS = {"MOMENTUM_ACCELERATION_DOWN", "EXTENDED_LOSER"}

CENSUS_DIRS = [("census_btc15", ("BTCUSDT",), "15m"),
               ("census_ethsol15", ("ETHUSDT", "SOLUSDT"), "15m"),
               ("census_1h", ("BTCUSDT", "ETHUSDT", "SOLUSDT",
                             "MINAUSDT", "NMRUSDT", "ORCAUSDT"), "1h")]
CENSUS_DETECTIONS_NAME = "detections.jsonl"


def verificar_causalidad_deteccion(d: dict) -> tuple[str, str | None]:
    """Contrato causal ENTRY-SAME-GRID-v1 por detección.
    Devuelve (estado, motivo); estado en OK | VIOLACION | UNKNOWN.
    UNKNOWN cuando faltan campos temporales o no son finitos: nunca
    PASS implícito."""
    f_ = d.get("formation_time")
    a_ = d.get("available_at")
    e_ = d.get("entry_time_same_grid")
    if f_ is None or a_ is None:
        return "UNKNOWN", "campos temporales ausentes"
    if not (finite_number(f_) and finite_number(a_)):
        return "UNKNOWN", "tiempos no finitos"
    if e_ is None:
        return "UNKNOWN", "entry_time_same_grid NULL (excluida no_entry)"
    if not finite_number(e_):
        return "UNKNOWN", "entry_time_same_grid no finito"
    if f_ > a_:
        return "VIOLACION", "formation_time > available_at"
    if a_ > e_:
        return "VIOLACION", "available_at > entry_time_same_grid"
    return "OK", None


def verificar_causalidad_poblacion(detecciones: list) -> dict:
    """Agrega causalidad sobre detecciones (lista de dicts).
    UNKNOWN cuando no hay datos (inputs ausentes)."""
    if not detecciones:
        return {"total": 0, "ok": 0, "unknown": 0, "violaciones": 0,
                "detalle": [], "estado": "UNKNOWN",
                "motivo": "sin detecciones (inputs externos ausentes)"}
    ok = unk = vio = 0
    detalle = []
    for d in detecciones:
        est, mot = verificar_causalidad_deteccion(d)
        if est == "OK":
            ok += 1
        elif est == "UNKNOWN":
            unk += 1
        else:
            vio += 1
            detalle.append({"symbol": d.get("symbol"),
                            "interval": d.get("source_interval"),
                            "formation_time": d.get("formation_time"),
                            "motivo": mot})
    return {"total": len(detecciones), "ok": ok, "unknown": unk,
            "violaciones": vio, "detalle": detalle[:50],
            "estado": ("COMPLETO" if vio == 0
                       else "COMPLETO_CON_DISCREPANCIAS"),
            "motivo": None if vio == 0 else "%d violaciones causales" % vio}


def verificar_censo_duplicados(filas: list) -> dict:
    """Agrupa filas de censo por (symbol, interval, formation_time).
    PERMITIDO: misma formación en familias/definiciones distintas
    (observaciones correlacionadas: 594 grupos/616 filas). Se reportan
    también formaciones con la MISMA definición repetida (posible
    duplicado real del censo; no se elimina ni se oculta)."""
    grupos = Counter((f["symbol"], f["interval"], f["formation_time"])
                     for f in filas)
    dup = {k: c for k, c in grupos.items() if c > 1}
    extra = sum(c - 1 for c in dup.values())
    por = defaultdict(lambda: {"grupos": 0, "extra": 0})
    misma_def = 0
    defs_por_grupo = defaultdict(list)
    for f in filas:
        defs_por_grupo[(f["symbol"], f["interval"], f["formation_time"])].append(
            f["definition_name"])
    for k, defs in defs_por_grupo.items():
        if len(defs) > 1 and len(set(defs)) < len(defs):
            misma_def += 1
    for (s, i, _), c in dup.items():
        por[(s, i)]["grupos"] += 1
        por[(s, i)]["extra"] += c - 1
    return {"total_filas": len(filas), "grupos_unicos": len(grupos),
            "grupos_duplicados": len(dup), "filas_extra": extra,
            "mismas_definiciones_grupos": misma_def,
            "desglose": [{"symbol": k[0], "interval": k[1], **v}
                         for k, v in sorted(por.items())]}


def clave_semantica_evento(e: dict) -> tuple:
    """Clave semántica (sin índice técnico): identifica el evento como
    observación, no como fila. El índice de fila diferencia filas; la
    clave semántica detecta duplicados."""
    return (e.get("symbol"), e.get("event_time_ms"), e.get("direction"),
            e.get("family"), e.get("rules_version"), e.get("group"))


def clasificar_duplicados_semanticos(eventos: list,
                                    origenes: dict | None = None) -> dict:
    """Clasifica claves semánticas repetidas en events.json.
    origenes: dict clave -> lista de original_event_id | 'placebo'.
    - ERROR: eventos no-placebo cuya clave repite el MISMO
      original_event_id (misma detección admitida 2 veces) o con más
      filas que orígenes conocidos.
    - PERMITIDO: misma clave con >=2 detecciones distintas (redundancia
      del censo) o colisión interna del placebo (identidad sintética
      propia; las colisiones rng son esperadas por construcción).
    Sin origenes: solo reporta la repetición, sin clasificar."""
    reps = Counter(clave_semantica_evento(e) for e in eventos)
    dup = {k: c for k, c in reps.items() if c > 1}
    out = {"claves_unicas": len(reps), "claves_duplicadas": len(dup),
           "filas_extra": sum(c - 1 for c in dup.values()),
           "errores": [], "permitidos": [], "sin_clasificar": []}
    if origenes is None:
        out["sin_clasificar"] = [list(k) for k in dup]
        return out
    for k, c in dup.items():
        origs = origenes.get(k, [])
        placebo = [o for o in origs if o == "placebo"]
        dets = [o for o in origs if o != "placebo"]
        if placebo and dets:
            out["errores"].append({"clave": list(k), "filas": c,
                                   "origenes": [str(o) for o in origs],
                                   "motivo": "mezcla placebo/deteccion (familias incompatibles)"})
        elif placebo:
            out["permitidos"].append({"clave": list(k), "filas": c,
                                      "origenes": ["placebo"],
                                      "nota": "colision interna placebo (identidad sintetica)"})
        else:
            if c > len(dets) or len(set(dets)) < c:
                out["errores"].append({"clave": list(k), "filas": c,
                                       "origenes": [str(o) for o in origs],
                                       "motivo": "misma deteccion admitida 2 veces"})
            else:
                out["permitidos"].append({"clave": list(k), "filas": c,
                                          "origenes": sorted(str(o) for o in origs)})
    return out


H2_SRC_DEFS = {"FAILED_HIGH_CANDIDATE", "FAILED_LOW_CANDIDATE"}
CONFIRM_WINDOW = 3  # igual que build_census_eval_inputs.py


def _confirm_h2_recon(bars: list, formation: int, ref_price: float,
                      trailing: float, want_short: bool):
    """Reconstrucción determinista de CONFIRM-H2-{SHORT,LONG}-v1 sobre
    barras cerradas mismas-grid (idéntica a build_census_eval_inputs)."""
    fwd = sorted((b for b in bars if b["open_time_ms"] > formation),
                 key=lambda b: b["open_time_ms"])
    for k in range(1, CONFIRM_WINDOW + 1):
        if len(fwd) < k:
            return None, "h2-no-confirmation"
        bar = fwd[k - 1]
        if want_short:
            if bar["close"] > trailing:
                return None, "h2-reclaim"
            if bar["close"] <= ref_price:
                return bar, None
        else:
            if bar["close"] < trailing:
                return None, "h2-reclaim"
            if bar["close"] >= ref_price:
                return bar, None
    return None, "h2-no-confirmation"


def origenes_de_evento(eventos: list, detecciones: list,
                       bars_by: dict | None = None) -> dict:
    """Reconstruye origenes por clave semántica de evento desde las
    detecciones. H1/H3: vínculo formation_time == event_time_ms.
    H2: reconstrucción determinista de la barra de confirmación con las
    barras disponibles (bars_by: (sym, res) -> lista de barras).
    Placebo se marca con identidad propia 'placebo'."""
    out = defaultdict(list)
    for d in detecciones:
        if d.get("formation_gap") or d.get("entry_time_same_grid") is None:
            continue
        fam_def = d.get("definition_name")
        if fam_def in H1_SRC_DEFS or fam_def in H3_SRC_DEFS:
            ivo = "LONG" if fam_def in H1_SRC_DEFS else "SHORT"
            fam = "H1" if ivo == "LONG" else "H3"
            grp = "continuation" if ivo == "LONG" else "bearish-continuation"
            clave = (d["symbol"], d["formation_time"], ivo, fam,
                     ("%s-v1" % fam), grp)
            out[clave].append(d.get("original_event_id")
                              or d.get("census_id"))
        elif fam_def in H2_SRC_DEFS and bars_by:
            key = (d["symbol"], d.get("source_interval"))
            bars = bars_by.get(key)
            if not bars:
                continue
            f_ = d["formation_time"]
            window = [b for b in bars if b["open_time_ms"] <= f_][-96:]
            if not window:
                continue
            want_short = fam_def == "FAILED_HIGH_CANDIDATE"
            trailing = (max(b["high"] for b in window) if want_short
                        else min(b["low"] for b in window))
            bar, motive = _confirm_h2_recon(bars, f_, d["reference_price"],
                                           trailing, want_short)
            if bar is None:
                continue  # excluida h2-no-confirmation / h2-reclaim
            ivo = "SHORT" if want_short else "LONG"
            grp = "correction-exhaustion" if want_short else "correction-reversal"
            clave = (d["symbol"], bar["open_time_ms"], ivo, "H2",
                     "H2-v1", grp)
            out[clave].append(d.get("original_event_id")
                              or d.get("census_id"))
    for e in eventos:
        if e.get("group") == "baseline":
            out[clave_semantica_evento(e)].append("placebo")
    return out


def vincular_eventos_h1h3(eventos: list, detecciones: list) -> dict:
    """Vínculo detección→evento para H1/H3: cada evento debe tener >=1
    detección respaldo y no superar su número (el builder no inventa).
    H2 queda fuera: su event_time_ms es la barra de confirmación."""
    dets = Counter()
    for d in detecciones:
        if d.get("definition_name") not in H1_SRC_DEFS | H3_SRC_DEFS:
            continue
        if d.get("formation_gap") or d.get("entry_time_same_grid") is None:
            continue
        ivo = "LONG" if d["definition_name"] in H1_SRC_DEFS else "SHORT"
        fam = "H1" if ivo == "LONG" else "H3"
        dets[(d["symbol"], d["formation_time"], ivo, fam)] += 1
    evs = Counter()
    for e in eventos:
        if e.get("family") in ("H1", "H3") and e.get("group") in (
                "continuation", "bearish-continuation"):
            evs[(e["symbol"], e["event_time_ms"], e["direction"],
                 e["family"])] += 1
    sin_respaldo, excedentes = [], []
    for k, c in sorted(evs.items()):
        nd = dets.get(k, 0)
        if nd == 0:
            sin_respaldo.append({"clave": list(k), "eventos": c})
        elif c > nd:
            excedentes.append({"clave": list(k), "eventos": c,
                               "detecciones": nd})
    return {"eventos_h1h3": sum(evs.values()),
            "detecciones_respaldo": sum(dets.values()),
            "n_sin_respaldo": len(sin_respaldo),
            "n_excedentes": len(excedentes),
            "sin_respaldo": sin_respaldo[:50],
            "excedentes": excedentes[:50]}


def clasificar_descartes(detecciones: list, bars_by: dict | None = None) -> dict:
    """Clasifica cada detección según MAP-CANDIDATE-v2 en la categoría
    que el builder le asignaría: h1/h3/h2ex/h2rev admitidas o excluded
    con motivo. Se compara contra build_report.counts; discrepancia =
    motivo de descarte ausente o alterado."""
    total = {"h1": 0, "h3": 0, "h2ex": 0, "h2rev": 0, "placebo": 0,
             "excluded_gap": 0, "excluded_no_entry": 0,
             "excluded_h2_no_confirmation": 0, "excluded_h2_reclaim": 0,
             "excluded_other_symbol": 0}
    for d in detecciones:
        fam_def = d.get("definition_name")
        if d.get("formation_gap"):
            total["excluded_gap"] += 1
            continue
        if d.get("entry_time_same_grid") is None:
            total["excluded_no_entry"] += 1
            continue
        if fam_def in H1_SRC_DEFS:
            total["h1"] += 1
        elif fam_def in H3_SRC_DEFS:
            total["h3"] += 1
        elif fam_def in H2_SRC_DEFS and bars_by:
            key = (d["symbol"], d.get("source_interval"))
            bars = bars_by.get(key)
            if not bars:
                total["excluded_h2_no_confirmation"] += 1
                continue
            f_ = d["formation_time"]
            window = [b for b in bars if b["open_time_ms"] <= f_][-96:]
            if not window:
                total["excluded_h2_no_confirmation"] += 1
                continue
            want_short = fam_def == "FAILED_HIGH_CANDIDATE"
            trailing = (max(b["high"] for b in window) if want_short
                        else min(b["low"] for b in window))
            bar, motive = _confirm_h2_recon(bars, f_, d["reference_price"],
                                           trailing, want_short)
            if motive == "h2-no-confirmation":
                total["excluded_h2_no_confirmation"] += 1
            elif motive == "h2-reclaim":
                total["excluded_h2_reclaim"] += 1
            elif want_short:
                total["h2ex"] += 1
            else:
                total["h2rev"] += 1
        elif fam_def in H2_SRC_DEFS:
            total["excluded_h2_no_confirmation"] += 1
        else:
            total["excluded_other_symbol"] += 1
    return total


def verificar_motivos_descarte(counts_reporte: dict,
                               detecciones: list,
                               bars_by: dict | None = None) -> dict:
    """Compara los counts del build_report con la clasificación
    determinista de las detecciones. INCOMPLETE si faltan campos de
    motivo; discrepancia si no cuadra."""
    errores = []
    esperado = clasificar_descartes(detecciones, bars_by)
    for campo in ("h1", "h3", "h2ex", "h2rev", "placebo",
                  "excluded_gap", "excluded_no_entry",
                  "excluded_h2_no_confirmation", "excluded_h2_reclaim"):
        if campo not in (counts_reporte or {}):
            errores.append("campo ausente en build_report: %s" % campo)
    n_direccionales = esperado["h1"] + esperado["h3"] + esperado["h2ex"] \
        + esperado["h2rev"]
    if "placebo" in (counts_reporte or {}) \
            and counts_reporte["placebo"] != n_direccionales:
        errores.append("placebo=%d != direccionales=%d"
                       % (counts_reporte["placebo"], n_direccionales))
    for campo in ("h1", "h3", "h2ex", "h2rev", "excluded_gap",
                  "excluded_no_entry", "excluded_h2_no_confirmation",
                  "excluded_h2_reclaim"):
        if campo in (counts_reporte or {}) \
                and counts_reporte[campo] != esperado[campo]:
            errores.append("%s: reporte=%d esperado=%d"
                           % (campo, counts_reporte[campo], esperado[campo]))
    return {"esperado": esperado, "reporte": counts_reporte,
            "errores": errores,
            "estado": "INCOMPLETE" if any("ausente" in e for e in errores)
            else ("COMPLETO" if not errores
                  else "COMPLETO_CON_DISCREPANCIAS")}


def verificar_funding_celda(seg: dict) -> dict:
    """funding_quality de una celda del manifiesto: ausente = INCOMPLETE
    (nunca cero por defecto); presente = OK con métricas. unknown_excluded
    y uncovered_ms son conceptos distintos."""
    fq = seg.get("funding_quality")
    if not fq or not isinstance(fq, dict):
        return {"estado": "INCOMPLETE",
                "motivo": "funding_quality ausente (nunca cero por defecto)"}
    for campo in ("settled_events", "unknown_excluded", "uncovered_ms"):
        if campo not in fq:
            return {"estado": "INCOMPLETE",
                    "motivo": "campo ausente en funding_quality: %s" % campo}
        if not finite_number(fq[campo]):
            return {"estado": "INCOMPLETE",
                    "motivo": "valor no finito en %s" % campo}
    return {"estado": "OK",
            "settled_events": fq["settled_events"],
            "unknown_excluded": fq["unknown_excluded"],
            "uncovered_ms": fq["uncovered_ms"]}


def rango_mfe_mae(celdas: list) -> dict:
    """Celdas: lista de dicts con mfe_mean, mae_mean, n_trades.
    Calcula rango global y rango direccionales con n>=30.
    Media por celda (excursión por posición), NO ganancia capturada.
    UNKNOWN si la lista está vacía."""
    if not celdas:
        return {"estado": "UNKNOWN", "motivo": "sin celdas con MFE/MAE"}
    mfes = [c["mfe_mean"] for c in celdas
            if finite_number(c.get("mfe_mean"))]
    mas = [c["mae_mean"] for c in celdas
           if finite_number(c.get("mae_mean"))]
    n30 = [c for c in celdas
           if finite_number(c.get("mfe_mean"))
           and finite_number(c.get("mae_mean"))
           and c.get("n_trades", 0) >= 30]
    mfes30 = [c["mfe_mean"] for c in n30]
    mas30 = [c["mae_mean"] for c in n30]
    if not mfes:
        return {"estado": "UNKNOWN", "motivo": "sin valores finitos"}
    return {"estado": "COMPLETO",
            "n_celdas": len(celdas), "n_celdas_n30": len(n30),
            "mfe_min": min(mfes), "mfe_max": max(mfes),
            "mae_min": min(mas), "mae_max": max(mas),
            "mfe_min_n30": min(mfes30) if mfes30 else None,
            "mfe_max_n30": max(mfes30) if mfes30 else None,
            "mae_min_n30": min(mas30) if mas30 else None,
            "mae_max_n30": max(mas30) if mas30 else None}


# Mapa de direcciones: detecciones usan up/down; eventos/trades LONG/SHORT
DIR_DET_TO_EVENTO = {"up": "LONG", "down": "SHORT"}


def familia_direccion_de_definicion(fam_def: str) -> tuple | None:
    """Devuelve (familia, direccion, grupo) implícitos en la definición de
    una detección, o None si no es una definición mapeable a evento.
    Usado para verificar que el respaldo de una operación tiene familia,
    dirección y grupo compatibles (sin cruzar resoluciones)."""
    if fam_def in H1_SRC_DEFS:
        return ("H1", "LONG", "continuation")
    if fam_def in H3_SRC_DEFS:
        return ("H3", "SHORT", "bearish-continuation")
    if fam_def in H2_SRC_DEFS:
        direccion = "SHORT" if fam_def == "FAILED_HIGH_CANDIDATE" else "LONG"
        grupo = "correction-exhaustion" if fam_def == "FAILED_HIGH_CANDIDATE" \
            else "correction-reversal"
        return ("H2", direccion, grupo)
    return None


def vincular_trades_eventos(trades: list, manifiestos: dict,
                            detecciones: list,
                            bars_by: dict | None = None) -> dict:
    """Trazabilidad operación ← candidato. Cada trade escala 1.0 debe:
    - tener event_id presente en los event_ids del manifiesto (respaldo);
    - tener entrada efectiva finita;
    - H1/H3: entry_ms >= available_at de su detección vinculada (misma
      resolución, familia y dirección);
    - H2: confirmación y cierre conocido de su vela (close_time_ms finito),
      entrada tras el cierre de la confirmación;
    - placebo: entry_ms coincide con una open_time de las velas;
    - estado realizada/abierta coherente con exit_executed.
    Campos temporales ausentes o no finitos → INCOMPLETE (nunca aceptación
    implícita). Entrada anterior a disponibilidad → FAIL.
    Devuelve veredicto con discrepancias (FAIL) e incompletos (INCOMPLETE),
    cada uno con sección, clave y motivo."""
    discrep = []
    incompletos = []
    ids_por_grupo = {}
    for (sym, res), man in manifiestos.items():
        for fam, g in man.get("groups", {}).items():
            ids = g.get("event_ids", [])
            if len(ids) != len(set(ids)):
                discrep.append({"seccion": "trazabilidad_operaciones",
                                "clave": "%s/%s/%s" % (sym, res, fam),
                                "motivo": "event_ids duplicados en manifiesto"})
            ids_por_grupo.setdefault((sym, res, fam), set(ids))
    # Respaldos indexados por CLAVE QUE INCLUYE RESOLUCIÓN para evitar cruzar
    # detecciones de resoluciones distintas que compartan símbolo y timestamp.
    dets_por_clave = {}
    for d in detecciones:
        ivo = DIR_DET_TO_EVENTO.get(d.get("direction", "").lower(),
                                    d.get("direction"))
        clave = (d.get("symbol"), d.get("formation_time"),
                 d.get("source_interval"), ivo)
        dets_por_clave.setdefault(clave, []).append(d)
    conf_h2 = {}
    if bars_by:
        for d in detecciones:
            if d.get("definition_name") not in H2_SRC_DEFS:
                continue
            key = (d.get("symbol"), d.get("source_interval"))
            bars = bars_by.get(key)
            if not bars:
                continue
            f_ = d["formation_time"]
            window = [b for b in bars if b["open_time_ms"] <= f_][-96:]
            if not window:
                continue
            want_short = d["definition_name"] == "FAILED_HIGH_CANDIDATE"
            trailing = (max(b["high"] for b in window) if want_short
                        else min(b["low"] for b in window))
            bar, motive = _confirm_h2_recon(bars, f_, d["reference_price"],
                                           trailing, want_short)
            if bar is None:
                continue
            ivo = "SHORT" if want_short else "LONG"
            conf_h2[(d.get("symbol"), bar["open_time_ms"],
                     d.get("source_interval"), ivo)] = bar
    opens_por = {}
    if bars_by:
        for key, bars in bars_by.items():
            opens_por[key] = set(b["open_time_ms"] for b in bars)
    n = 0
    for t in trades:
        if t.get("escala") != 1.0:
            continue
        n += 1
        eid = t.get("event_id", "")
        sym, res, grp = t.get("symbol"), t.get("res"), t.get("group")
        direccion = t.get("direction")
        # 1) event_id presente en manifiesto (identidad compatible)
        if eid not in ids_por_grupo.get((sym, res, grp), set()):
            discrep.append({"seccion": "trazabilidad_operaciones",
                            "clave": eid or t.get("symbol"),
                            "motivo": "operación sin candidato en manifiesto"})
            continue
        # 2) estado / exit_executed según contrato realizada o abierta
        if t.get("exit_executed") == bool(t.get("estado") == "abierta") \
                and t.get("estado") is not None:
            discrep.append({"seccion": "trazabilidad_operaciones",
                            "clave": eid,
                            "motivo": "estado incoherente con exit_executed"})
        if grp == "baseline":
            op = opens_por.get((sym, res))
            if op is not None and t.get("entry_ms") not in op:
                discrep.append({"seccion": "trazabilidad_operaciones",
                                "clave": eid,
                                "motivo": "placebo: entry_ms no es una "
                                          "apertura de vela conocida"})
            continue
        # 3) H2: confirmación y cierre conocido de su vela
        if grp in ("correction-exhaustion", "correction-reversal"):
            bar = conf_h2.get((sym, t.get("event_time_ms"), res, direccion))
            if bar is None:
                incompletos.append({"seccion": "trazabilidad_operaciones",
                                    "clave": eid,
                                    "motivo": "H2 sin confirmación "
                                              "reconstruible"})
            else:
                ct = bar.get("close_time_ms")
                ems = t.get("entry_ms")
                ct_ok = finite_number(ct)
                ems_ok = finite_number(ems)
                if not ct_ok:
                    incompletos.append({"seccion": "trazabilidad_operaciones",
                                        "clave": eid,
                                        "motivo": "H2 close_time_ms de la "
                                                  "vela de confirmación ausente "
                                                  "o no finito"})
                if not ems_ok:
                    incompletos.append({"seccion": "trazabilidad_operaciones",
                                        "clave": eid,
                                        "motivo": "H2 entry_ms ausente o no "
                                                  "finito"})
                elif ct_ok and ems < ct:
                    discrep.append({"seccion": "trazabilidad_operaciones",
                                    "clave": eid,
                                    "motivo": "H2 entrando antes de conocerse "
                                              "su confirmación "
                                              "(entry_ms=%s < close_time_ms=%s)"
                                              % (ems, ct)})
            continue
        # 4) H1/H3: respaldo con símbolo, resolución, familia, dirección e
        #    identidad compatibles.
        clave_ds = (sym, t.get("event_time_ms"), res, direccion)
        ds = dets_por_clave.get(clave_ds, [])
        if not ds:
            incompletos.append({"seccion": "trazabilidad_operaciones",
                                "clave": eid,
                                "motivo": "H1/H3 sin detección de respaldo "
                                          "compatible (símbolo/resolución/"
                                          "familia/dirección)"})
            continue
        fd = familia_direccion_de_definicion(
            ds[0].get("definition_name", ""))
        if fd is None or (fd[0], fd[1]) != (t.get("family"), direccion):
            incompletos.append({"seccion": "trazabilidad_operaciones",
                                "clave": eid,
                                "motivo": "respaldo sin familia/dirección "
                                          "compatibles con la operación"})
        # 5) disponibilidad efectiva de la detección/candidato (no se deriva
        #    igualándola a la entrada).
        avail_vals = [d.get("available_at") for d in ds]
        if not all(finite_number(v) for v in avail_vals):
            incompletos.append({"seccion": "trazabilidad_operaciones",
                                "clave": eid,
                                "motivo": "available_at (disponibilidad) "
                                          "ausente o no finito"})
        else:
            avail = max(avail_vals)
            ems = t.get("entry_ms")
            if not finite_number(ems):
                incompletos.append({"seccion": "trazabilidad_operaciones",
                                    "clave": eid,
                                    "motivo": "entry_ms ausente o no finito"})
            elif ems < avail:
                discrep.append({"seccion": "trazabilidad_operaciones",
                                "clave": eid,
                                "motivo": "entrada efectiva anterior a "
                                          "disponibilidad (entry_ms=%s < "
                                          "available_at=%s)"
                                          % (ems, avail)})
    estado = ("COMPLETO" if not discrep and not incompletos
              else ("COMPLETO_CON_DISCREPANCIAS" if discrep else "INCOMPLETE"))
    return {"n_trades_revisados": n, "discrepancias": discrep,
            "incompletos": incompletos, "estado": estado}


def verificar_multiplicidad_trades(trades: list, manifiesto: dict) -> list:
    """n trades escala 1.0 por (grupo, segmento) debe igualar n_trades del
    manifiesto (multiplicidad preservada: 3 escalas no se mezclan)."""
    discrep = []
    contador = {}
    for t in trades:
        if t.get("escala") != 1.0:
            continue
        k = (t.get("group"), t.get("segmento"))
        contador[k] = contador.get(k, 0) + 1
    for fam, segmentos in manifiesto.get("groups", {}).items():
        for seg, escalas in segmentos.items():
            if not isinstance(escalas, dict):
                continue
            ref = escalas.get("1.0", {}).get("n_trades")
            if ref is None:
                continue
            if contador.get((fam, seg), 0) != ref:
                discrep.append({"seccion": "trazabilidad_operaciones",
                                "clave": "%s/%s" % (fam, seg),
                                "motivo": "multiplicidad: %d trades != %d "
                                          "manifiesto"
                                          % (contador.get((fam, seg), 0),
                                             ref)})
    return discrep


def clasificar_tail_edge(detecciones: list, build_reports: dict) -> dict:
    """Los 6 tail-edge (entry_time_same_grid NULL, sin formation_gap) deben
    clasificarse como exclusiones ESPERADAS cuando pueda probarse: la suma
    del tail-edge de los símbolos que cubre cada build_report debe igualar
    su excluded_no_entry (el builder cuenta por corrida, que agrupa
    símbolos). Símbolos sin build_report propio: INCOMPLETE (no
    verificable), nunca FAIL ni UNKNOWN aceptable."""
    tail = [d for d in detecciones
            if d.get("entry_time_same_grid") is None
            and not d.get("formation_gap")]
    por_sym_res = Counter((d["symbol"], d["source_interval"]) for d in tail)
    cubiertos = set()
    clasificados = []
    discrepancias = []
    for dname, br in build_reports.items():
        syms = set(br.get("symbols", []))
        iv = br.get("interval")
        n_tail = sum(n for (s, r), n in por_sym_res.items()
                     if s in syms and r == iv)
        n_build = br.get("counts", {}).get("excluded_no_entry")
        cubiertos.update((s, iv) for s in syms)
        if n_build is None:
            discrepancias.append({"build_report": dname,
                                  "motivo": "sin excluded_no_entry "
                                            "en build_report"})
        elif n_build != n_tail:
            discrepancias.append({"build_report": dname,
                                  "motivo": "excluded_no_entry=%d != "
                                            "tail_edge=%d"
                                            % (n_build, n_tail)})
        else:
            clasificados.append({"build_report": dname,
                                 "n_tail_edge": n_tail,
                                 "excluded_no_entry": n_build})
    no_cubiertos = [{"symbol": s, "res": r, "n": n}
                    for (s, r), n in por_sym_res.items()
                    if (s, r) not in cubiertos]
    estado = "COMPLETO" if not discrepancias and not no_cubiertos \
        else ("COMPLETO_CON_DISCREPANCIAS" if discrepancias
              else "INCOMPLETE_NO_VERIFICABLE")
    return {"n_tail_edge": len(tail),
            "exclusiones_esperadas_verificadas": clasificados,
            "discrepancias": discrepancias,
            "no_cubiertos": no_cubiertos,
            "estado": estado}


def veredicto_global(secciones: dict) -> dict:
    """Veredicto coherente que integra TODAS las secciones.
    PASS: adquisición completa y 0 discrepancias.
    FAIL: discrepancia demostrada (coexiste con INCOMPLETE si procede).
    INCOMPLETE: falta evidencia obligatoria sin discrepancia.
    Cada error incluye sección, clave afectada y motivo."""
    discrepancias = []
    incompletitud = []

    def _add_discrep(sec, clave, motivo):
        discrepancias.append({"seccion": sec, "clave": str(clave),
                              "motivo": motivo})

    adq = secciones.get("adquisicion", {})
    if adq.get("incompleta"):
        incompletitud.append({"seccion": "adquisicion",
                              "motivo": adq.get("motivo", "inputs "
                                                 "incompletos")})

    c = secciones.get("causalidad", {})
    if c.get("estado") == "UNKNOWN":
        incompletitud.append({"seccion": "causalidad",
                              "motivo": c.get("motivo", "sin datos")})
    else:
        for v in c.get("detalle", []):
            _add_discrep("causalidad",
                         "%s/%s@%s" % (v.get("symbol"),
                                       v.get("interval"),
                                       v.get("formation_time")),
                         v.get("motivo", "violación causal"))

    r = secciones.get("referencias", {})
    if r and not r.get("consistente", False):
        for k in r.get("solo_artefacto_con_eventos", []):
            _add_discrep("referencias", k, "celda con eventos sin "
                         "manifiesto")
        for k in r.get("solo_manifiesto", []):
            _add_discrep("referencias", k, "celda en manifiesto sin "
                         "artefacto")
        for m in r.get("campos_incompatibles", []):
            _add_discrep("referencias", m, "campo compartido "
                         "incompatible")
        for m in r.get("escalas_inesperadas", []):
            _add_discrep("referencias", m, "escenario inesperado")

    ec = secciones.get("campos_economicos", {})
    if ec:
        for item in ec.get("discrepancias", []):
            _add_discrep(item.get("seccion", "campos_economicos"),
                         item.get("clave"), item.get("motivo"))

    for e in secciones.get("duplicados_events", []):
        for err in e.get("errores", []):
            _add_discrep("duplicados_events",
                         "%s/%s %s" % (e.get("symbol"), e.get("res"),
                                       err.get("clave")),
                         err.get("motivo", "duplicado indebido"))

    for v in secciones.get("vinculos_h1h3", []):
        for s in v.get("sin_respaldo", []):
            _add_discrep("vinculo_h1h3", s.get("clave"),
                         "evento sin detección de respaldo")
        for s in v.get("excedentes", []):
            _add_discrep("vinculo_h1h3", s.get("clave"),
                         "más eventos que detecciones respaldo")

    d = secciones.get("descartes", {})
    if d:
        if d.get("estado") == "INCOMPLETE":
            for e in d.get("errores", []):
                if "ausente" in e:
                    incompletitud.append({"seccion": "descartes",
                                          "motivo": e})
        elif d.get("estado") == "COMPLETO_CON_DISCREPANCIAS":
            for e in d.get("errores", []):
                _add_discrep("descartes", "build_report", e)

    f = secciones.get("funding", {})
    if f:
        for item in f.get("incompleto", []):
            incompletitud.append({"seccion": "funding", "motivo": item})

    t = secciones.get("trazabilidad_operaciones", {})
    if t.get("estado") == "UNKNOWN":
        incompletitud.append({"seccion": "trazabilidad_operaciones",
                              "motivo": t.get("motivo",
                                              "trades no proporcionados")})
    else:
        for item in t.get("discrepancias", []):
            _add_discrep(item.get("seccion", "trazabilidad_operaciones"),
                         item.get("clave"), item.get("motivo"))
        for item in t.get("incompletos", []):
            incompletitud.append({"seccion": "trazabilidad_operaciones",
                                  "motivo": item.get("motivo")})

    te = secciones.get("tail_edge", {})
    if te:
        for item in te.get("discrepancias", []):
            _add_discrep("tail_edge", item.get("build_report"),
                         item.get("motivo"))
        for item in te.get("no_cubiertos", []):
            incompletitud.append({
                "seccion": "tail_edge",
                "motivo": "%s/%s: tail-edge sin build_report verificable "
                          "(INCOMPLETE, no FAIL)"
                          % (item.get("symbol"), item.get("res"))})

    if discrepancias:
        estado = "FAIL+INCOMPLETE" if incompletitud else "FAIL"
    elif incompletitud:
        estado = "INCOMPLETE"
    else:
        estado = "PASS"
    return {"estado": estado,
            "discrepancias": discrepancias,
            "incompleto": incompletitud,
            "exitoso": estado == "PASS"}


def verificar_campos_economicos(artefacto: dict, manifiestos: dict,
                               rtol: float = 1e-9) -> dict:
    """Compara campos compartidos con correspondencias explícitas:
    E_net ↔ expectancy_net, placebo_E_net ↔ expectancy_net (baseline),
    exit_stop ↔ exit_reasons.stop. Tolerancia relativa 1e-9 (mismo
    float determinista). No acepta ausencias como coincidencias."""
    discrep = []
    n = 0
    for sym in artefacto["cells"]:
        for res in artefacto["cells"][sym]:
            man = manifiestos.get((sym, res))
            if not man:
                continue
            for fam in artefacto["cells"][sym][res]:
                for split in artefacto["cells"][sym][res][fam]:
                    if "1.0" not in artefacto["cells"][sym][res][fam][split]:
                        continue
                    c = artefacto["cells"][sym][res][fam][split]["1.0"]
                    seg = man["groups"].get(fam, {}).get(split, {}).get("1.0", {})
                    if not seg:
                        continue
                    n += 1
                    en = c.get("E_net")
                    mn = seg.get("expectancy_net")
                    if en is None or mn is None:
                        discrep.append({"seccion": "campos_economicos",
                                        "clave": "%s/%s/%s/%s E_net" % (sym, res, fam, split),
                                        "motivo": "campo ausente (artefacto=%s manifiesto=%s)" % (en, mn)})
                    elif abs(en - mn) > rtol * max(1.0, abs(en), abs(mn)):
                        discrep.append({"seccion": "campos_economicos",
                                        "clave": "%s/%s/%s/%s E_net" % (sym, res, fam, split),
                                        "motivo": "E_net=%s != expectancy_net=%s" % (en, mn)})
                    es = c.get("exit_stop")
                    ms = seg.get("exit_reasons", {}).get("stop")
                    if es is None or ms is None:
                        discrep.append({"seccion": "campos_economicos",
                                        "clave": "%s/%s/%s/%s exit_stop" % (sym, res, fam, split),
                                        "motivo": "campo ausente (artefacto=%s manifiesto=%s)" % (es, ms)})
                    elif es != ms:
                        discrep.append({"seccion": "campos_economicos",
                                        "clave": "%s/%s/%s/%s exit_stop" % (sym, res, fam, split),
                                        "motivo": "exit_stop=%s != exit_reasons.stop=%s" % (es, ms)})
                    if fam != "baseline":
                        pen = c.get("placebo_E_net")
                        bseg = man["groups"].get("baseline", {}).get(split, {}).get("1.0", {})
                        bn = bseg.get("expectancy_net")
                        if pen is None or bn is None:
                            discrep.append({"seccion": "campos_economicos",
                                            "clave": "%s/%s/%s/%s placebo_E_net" % (sym, res, fam, split),
                                            "motivo": "campo ausente (artefacto=%s manifiesto=%s)" % (pen, bn)})
                        elif abs(pen - bn) > rtol * max(1.0, abs(pen), abs(bn)):
                            discrep.append({"seccion": "campos_economicos",
                                            "clave": "%s/%s/%s/%s placebo_E_net" % (sym, res, fam, split),
                                            "motivo": "placebo_E_net=%s != baseline expectancy_net=%s" % (pen, bn)})
    return {"n_celdas": n, "discrepancias": discrep,
            "estado": "COMPLETO" if not discrep else "COMPLETO_CON_DISCREPANCIAS"}


def verificar_referencias(artefacto: dict, manifiestos: dict) -> dict:
    """Correspondencia exacta (symbol, resolución, familia, segmento)
    entre artefacto (celdas 1x) y manifiestos. Detecta filas ausentes,
    extra, duplicadas o incompatibles; compara campos compartidos."""
    a_keys = set()
    for sym in artefacto["cells"]:
        for res in artefacto["cells"][sym]:
            for fam in artefacto["cells"][sym][res]:
                for split in artefacto["cells"][sym][res][fam]:
                    if "1.0" in artefacto["cells"][sym][res][fam][split]:
                        a_keys.add((sym, res, fam, split))
    m_keys = set()
    escalas_inesperadas = []
    for (sym, res), man in manifiestos.items():
        for fam in man.get("groups", {}):
            if not man["groups"][fam].get("event_ids"):
                continue
            for split in ("dev", "oos"):
                for escala in man["groups"][fam].get(split, {}):
                    if escala not in ALLOWED_SCALES:
                        escalas_inesperadas.append(
                            "%s/%s/%s/%s escala %s" % (sym, res, fam, split,
                                                       escala))
                if "1.0" in man["groups"][fam].get(split, {}):
                    m_keys.add((sym, res, fam, split))
    solo_art = a_keys - m_keys
    solo_man = m_keys - a_keys
    solo_art_reales = set()
    for (sym, res, fam, split) in solo_art:
        c = artefacto["cells"][sym][res][fam][split]["1.0"]
        if c.get("n_events", 0) > 0:
            solo_art_reales.add((sym, res, fam, split))
    incompat = []
    for sym in artefacto["cells"]:
        for res in artefacto["cells"][sym]:
            man = manifiestos.get((sym, res))
            if not man:
                continue
            for fam in artefacto["cells"][sym][res]:
                for split in artefacto["cells"][sym][res][fam]:
                    if "1.0" not in artefacto["cells"][sym][res][fam][split]:
                        continue
                    seg = man["groups"].get(fam, {}).get(split, {}).get("1.0", {})
                    if not seg:
                        continue
                    c = artefacto["cells"][sym][res][fam][split]["1.0"]
                    for campo in ("n_events", "n_trades", "n_open",
                                  "skipped_overlap"):
                        av, mv = c.get(campo), seg.get(campo)
                        if av is not None and mv is not None and av != mv:
                            incompat.append(
                                "%s/%s/%s/%s %s: artefacto=%s manifiesto=%s"
                                % (sym, res, fam, split, campo, av, mv))
                        elif (av is None) != (mv is None):
                            incompat.append(
                                "%s/%s/%s/%s %s: campo presente solo en un "
                                "lado (artefacto=%s manifiesto=%s)"
                                % (sym, res, fam, split, campo, av, mv))
    return {"n_celdas_artefacto": len(a_keys),
            "n_celdas_manifiesto": len(m_keys),
            "solo_artefacto_con_eventos": sorted(solo_art_reales)[:50],
            "solo_manifiesto": sorted(solo_man)[:50],
            "campos_incompatibles": incompat[:50],
            "escalas_inesperadas": escalas_inesperadas[:50],
            "consistente": (not solo_art_reales) and (not solo_man)
            and (not incompat) and (not escalas_inesperadas)}


def validate_artifact(art: Path) -> tuple[dict, str, list[str]]:
    """Valida el artefacto: esquema, familias, campos requeridos, finitos.
    Devuelve (datos, sha256, errores)."""
    errores = []
    with open(art, encoding="utf-8") as f:
        data = json.load(f)
    sha = sha256_file(art)

    # Campos de nivel superior
    for campo in ("schema_version", "artifact_version", "cells"):
        if campo not in data:
            errores.append("campo ausente en artefacto: %s" % campo)

    cells = data.get("cells", {})
    for sym in cells:
        if sym not in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            errores.append("símbolo inesperado en artefacto: %s" % sym)
        for res in cells[sym]:
            if res not in ("15m", "1h"):
                errores.append("resolución inesperada: %s/%s" % (sym, res))
            for fam in cells[sym][res]:
                if fam not in ALLOWED_FAMILIES:
                    errores.append("familia inesperada: %s/%s/%s"
                                   % (sym, res, fam))
                for split in cells[sym][res][fam]:
                    if split not in ("dev", "oos"):
                        errores.append("segmento inesperado: %s/%s/%s/%s"
                                       % (sym, res, fam, split))
                    cell = cells[sym][res][fam][split]
                    for escala, c in cell.items():
                        if escala not in ALLOWED_SCALES:
                            errores.append("escenario inesperado: %s/%s/%s/%s/%s"
                                            % (sym, res, fam, split, escala))
                        for campo in REQUIRED_ARTIFACT_FIELDS:
                            if campo not in c:
                                errores.append("campo ausente %s/%s/%s/%s/%s/%s"
                                               % (sym, res, fam, split, escala, campo))
                            elif not finite_number(c[campo]) and campo != "verdict":
                                errores.append("valor no finito %s/%s/%s/%s/%s/%s.%s = %s"
                                               % (sym, res, fam, split, escala, campo, c[campo]))
    return data, sha, errores


COMBOS = [
    ("eval15_btc", "BTCUSDT", "15m"),
    ("eval15_ethsol", "ETHUSDT", "15m"),
    ("eval15_ethsol", "SOLUSDT", "15m"),
    ("eval1h_trio", "BTCUSDT", "1h"),
    ("eval1h_trio", "ETHUSDT", "1h"),
    ("eval1h_trio", "SOLUSDT", "1h"),
]


class Ledger:
    def __init__(self, artifact_path: Path, temp_dir: Path | None,
                 out_path: Path):
        self.artifact_path = artifact_path
        self.temp_dir = temp_dir
        self.out_path = out_path
        self.data = None
        self.artifact_sha256 = None
        self.validation_errors = []
        self.inputs = {}  # descripcion -> {"path":..., "sha256":..., "exists":bool}
        self.incomplete = False
        self.incomplete_reasons = []
        self.manif_traces = None  # reconstruction_manifest.json validado

    def _register_input(self, desc: str, path: Path | None):
        if path is None:
            self.inputs[desc] = {"path": None, "sha256": None, "exists": False}
            return
        p = Path(path)
        try:
            base = self.package if self.package else self.temp_dir
            ruta = str(p.relative_to(base)) if base else str(p)
        except ValueError:
            ruta = str(p)
        if p.exists():
            self.inputs[desc] = {"path": ruta, "sha256": sha256_file(p),
                                 "exists": True}
        else:
            self.inputs[desc] = {"path": ruta, "sha256": None,
                                 "exists": False}
            self.incomplete = True
            self.incomplete_reasons.append("input externo ausente: %s" % p)

    def load(self, package: Path | None = None,
             trades_dir: Path | None = None):
        self.package = package
        self.trades_dir = trades_dir
        self.data, self.artifact_sha256, self.validation_errors = \
            validate_artifact(self.artifact_path)
        if self.validation_errors:
            self.incomplete = True
            self.incomplete_reasons.extend(self.validation_errors)

        # Registra inputs externos (manifiestos, selection, build_report,
        # funding) — pueden no existir (fuera de Git).
        combos = COMBOS
        for d, sym, res in combos:
            if self.base_dir is None:
                continue
            base = self.base_dir / d
            self._register_input("manifest %s_%s" % (sym, res),
                                 base / ("manifest_%s_%s.json" % (sym, res)))
            self._register_input("events %s_%s" % (sym, res),
                                 base / ("events_%s_%s.json" % (sym, res)))
            self._register_input("selection %s_%s" % (sym, res),
                                 base / ("selection_%s_%s.json" % (sym, res)))
        seen_dirs = set()
        for d, _, _ in combos:
            if d in seen_dirs:
                continue
            seen_dirs.add(d)
            if self.base_dir is not None:
                self._register_input("build_report %s" % d,
                                     self.base_dir / d / "build_report.json")
        fund_dir = self.package / "funding" if self.package else self.temp_dir
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            if fund_dir is not None:
                self._register_input("funding %s" % sym,
                                     fund_dir / ("funding_%s.json" % sym))
        if fund_dir is not None and (fund_dir / "funding_raw.json").exists():
            self._register_input("funding_raw",
                                 fund_dir / "funding_raw.json")
        if self.temp_dir is None and package is None:
            self.incomplete = True
            self.incomplete_reasons.append(
                "temp_dir/package no especificado: manifiestos, funding y "
                "detecciones no cargados (secciones de evidencia vacias)")
        # Detecciones del reconstruct (censo causal con tiempos reales)
        self.detecciones = []
        self.census_files = []
        if package is not None:
            for dname, symbols, res in CENSUS_DIRS:
                cp = package / "detections" / ("%s_detections.jsonl" % dname)
                self._register_input("detecciones %s" % dname, cp)
                if cp.exists():
                    for line in cp.read_text(encoding="utf-8").splitlines():
                        if line.strip():
                            self.detecciones.append(json.loads(line))
                    self.census_files.append(str(cp))
        elif self.temp_dir is not None:
            for dname, symbols, res in CENSUS_DIRS:
                cp = self.temp_dir / ("%s/%s" % (dname, CENSUS_DETECTIONS_NAME))
                self._register_input("detecciones %s" % dname, cp)
                if cp.exists():
                    for line in cp.read_text(encoding="utf-8").splitlines():
                        if line.strip():
                            self.detecciones.append(json.loads(line))
                    self.census_files.append(str(cp))
        # Trazas reconstruidas (trades_*.json) si se proporcionan
        self.trades = {}
        if trades_dir is not None:
            for d, sym, res in COMBOS:
                tp = trades_dir / ("trades_%s_%s.json" % (sym, res))
                if tp.exists():
                    self.trades[(sym, res)] = json.loads(
                        tp.read_text(encoding="utf-8"))
                    self._register_input("trazas %s_%s" % (sym, res), tp)
                else:
                    self.incomplete = True
                    self.incomplete_reasons.append(
                        "trazas ausentes: %s" % tp)
            # Registra el manifiesto de trazas para validación antes del uso.
            mp = trades_dir / "reconstruction_manifest.json"
            self._register_input("reconstruction_manifest", mp)
            if mp.exists():
                try:
                    self.manif_traces = json.loads(
                        mp.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    self.manif_traces = None
                    self.incomplete = True
                    self.incomplete_reasons.append(
                        "reconstruction_manifest.json ilegible: %s" % mp)

    @property
    def base_dir(self) -> Path | None:
        if self.package is not None:
            return self.package / "combos"
        return self.temp_dir

    def _manifiestos(self) -> dict:
        """Carga todos los manifiestos disponibles como (sym, res) -> dict."""
        out = {}
        for d, s, r in [
            ("eval15_btc", "BTCUSDT", "15m"),
            ("eval15_ethsol", "ETHUSDT", "15m"),
            ("eval15_ethsol", "SOLUSDT", "15m"),
            ("eval1h_trio", "BTCUSDT", "1h"),
            ("eval1h_trio", "ETHUSDT", "1h"),
            ("eval1h_trio", "SOLUSDT", "1h"),
        ]:
            if (s, r) in out:
                continue
            m = self._load_manifest(s, r)
            if m is not None:
                out[(s, r)] = m
        return out

    def _build_reports(self) -> dict:
        """Carga los build_report disponibles como dir -> dict."""
        out = {}
        if self.base_dir is None:
            return out
        for d, _, _ in COMBOS:
            if d in out:
                continue
            bp = self.base_dir / d / "build_report.json"
            if bp.exists():
                out[d] = json.loads(bp.read_text(encoding="utf-8"))
        return out

    def _descartes_global(self) -> dict:
        """Verifica motivos de descarte del builder contra la clasificación
        determinista de las detecciones (agregado por build_report)."""
        brs = self._build_reports()
        if not brs:
            return {"estado": "UNKNOWN",
                    "motivo": "build_reports no disponibles",
                    "errores": []}
        errores = []
        estado = "COMPLETO"
        bars_by = {}
        for d, sym, res in COMBOS:
            if self.base_dir is None:
                continue
            cp = self.base_dir / d / ("candles_%s_%s.json" % (sym, res))
            if cp.exists():
                bars_by[(sym, res)] = json.loads(cp.read_text(encoding="utf-8"))
        for dname, br in brs.items():
            syms = br.get("symbols", [])
            iv = br.get("interval")
            dets = [x for x in self.detecciones
                    if x.get("symbol") in syms
                    and x.get("source_interval") == iv]
            bb = {}
            for s in syms:
                if (s, iv) in bars_by:
                    bb[(s, iv)] = bars_by[(s, iv)]
            r = verificar_motivos_descarte(br.get("counts", {}), dets,
                                           bb or None)
            for e in r["errores"]:
                errores.append("%s: %s" % (dname, e))
            if r["estado"] == "INCOMPLETE":
                estado = "INCOMPLETE"
            elif r["estado"] == "COMPLETO_CON_DISCREPANCIAS" \
                    and estado != "INCOMPLETE":
                estado = "COMPLETO_CON_DISCREPANCIAS"
        return {"estado": estado, "errores": errores}

    def _funding_incompleto(self) -> list:
        """Celdas sin funding_quality (INCOMPLETE, nunca cero)."""
        out = []
        mans = self._manifiestos()
        for sym in self.data["cells"]:
            for res in self.data["cells"][sym]:
                man = mans.get((sym, res))
                if not man:
                    continue
                for fam in self.data["cells"][sym][res]:
                    for split in self.data["cells"][sym][res][fam]:
                        if "1.0" not in self.data["cells"][sym][res][fam][split]:
                            continue
                        seg = man["groups"].get(fam, {}).get(split, {}).get(
                            "1.0", {})
                        if not seg.get("funding_quality"):
                            out.append("%s/%s/%s/%s" % (sym, res, fam, split))
        return out

    def _load_manifest(self, sym: str, res: str):
        if self.base_dir is None:
            return None
        for d, s, r in [
            ("eval15_btc", "BTCUSDT", "15m"),
            ("eval15_ethsol", "ETHUSDT", "15m"),
            ("eval15_ethsol", "SOLUSDT", "15m"),
            ("eval1h_trio", "BTCUSDT", "1h"),
            ("eval1h_trio", "ETHUSDT", "1h"),
            ("eval1h_trio", "SOLUSDT", "1h"),
        ]:
            if s == sym and r == res:
                p = self.base_dir / d / ("manifest_%s_%s.json" % (sym, res))
                if p.exists():
                    return json.loads(p.read_text(encoding="utf-8"))
        return None

    def _load_selection(self, sym: str, res: str):
        if self.temp_dir is None:
            return None
        for d, s, r in [
            ("eval15_btc", "BTCUSDT", "15m"),
            ("eval15_ethsol", "ETHUSDT", "15m"),
            ("eval15_ethsol", "SOLUSDT", "15m"),
            ("eval1h_trio", "BTCUSDT", "1h"),
            ("eval1h_trio", "ETHUSDT", "1h"),
            ("eval1h_trio", "SOLUSDT", "1h"),
        ]:
            if s == sym and r == res:
                p = self.base_dir / d / ("selection_%s_%s.json" % (sym, res))
                if p.exists():
                    return json.loads(p.read_text(encoding="utf-8"))
        return None

    def _validar_manifest_traces(self, trades_dir: Path) -> dict:
        """Valida reconstruction_manifest.json ANTES de consumir las trazas:
        - veredicto == COMPLETO (FAIL → trazas no consumibles).
        - cobertura: los 6 combos esperados presentes y consumibles.
        - hashes de cada trades_*.json coinciden con el manifiesto.
        - no faltan trades esperados ni sobran archivos extra/obsoletos
          de una ejecución previa.
        - cada trades_*.json tiene equivalencia == "verificada" y consumible.
        Devuelve {"valido": bool, "motivo": str, "discrepancias": [...],
        "incompletos": [...]}."""
        discrepancias = []
        incompletos = []
        mp = trades_dir / "reconstruction_manifest.json"
        if not mp.exists():
            incompletos.append({"seccion": "trazabilidad_operaciones",
                                "motivo": "reconstruction_manifest.json "
                                          "ausente (trazas no validadas)"})
            return {"valido": False, "motivo": "manifiesto de trazas ausente",
                    "discrepancias": discrepancias, "incompletos": incompletos}
        try:
            man = json.loads(mp.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            incompletos.append({"seccion": "trazabilidad_operaciones",
                                "motivo": "reconstruction_manifest.json "
                                          "ilegible: %s" % exc})
            return {"valido": False, "motivo": "manifiesto de trazas ilegible",
                    "discrepancias": discrepancias, "incompletos": incompletos}
        if man.get("veredicto") != "COMPLETO":
            discrepancias.append({"seccion": "trazabilidad_operaciones",
                                  "clave": "reconstruction_manifest",
                                  "motivo": "veredicto de trazas = %s (se "
                                            "requiere COMPLETO; FAIL = trazas "
                                            "no consumibles)"
                                  % man.get("veredicto")})
            return {"valido": False,
                    "motivo": "reconstruction_manifest veredicto %s: trazas "
                              "no consumibles" % man.get("veredicto"),
                    "discrepancias": discrepancias, "incompletos": incompletos}
        cov = man.get("cobertura", {})
        if cov.get("celdas_fail", 0) != 0:
            discrepancias.append({"seccion": "trazabilidad_operaciones",
                                  "clave": "reconstruction_manifest",
                                  "motivo": "%d celdas sin equivalencia "
                                            "demostrada" % cov.get("celdas_fail")})
            return {"valido": False,
                    "motivo": "celdas falladas sin equivalencia",
                    "discrepancias": discrepancias, "incompletos": incompletos}
        trades_sha = man.get("trades_sha256", {}) or {}
        expected = ["trades_%s_%s.json" % (s, r) for (_, s, r) in COMBOS]
        seen = set()
        for fname in expected:
            tp = trades_dir / fname
            if not tp.exists():
                incompletos.append({"seccion": "trazabilidad_operaciones",
                                    "motivo": "traza esperada ausente: %s" % fname})
                return {"valido": False,
                        "motivo": "traza esperada ausente: %s" % fname,
                        "discrepancias": discrepancias, "incompletos": incompletos}
            h = sha256_file(tp)
            if trades_sha.get(fname) != h:
                discrepancias.append({"seccion": "trazabilidad_operaciones",
                                      "clave": fname,
                                      "motivo": "hash de traza no coincide "
                                                "con reconstruction_manifest "
                                                "(traza alterada después de "
                                                "reconstruir)"})
                return {"valido": False,
                        "motivo": "traza alterada (hash mismatch): %s" % fname,
                        "discrepancias": discrepancias, "incompletos": incompletos}
            try:
                tdata = json.loads(tp.read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                incompletos.append({"seccion": "trazabilidad_operaciones",
                                    "motivo": "traza ilegible: %s (%s)"
                                              % (fname, exc)})
                return {"valido": False,
                        "motivo": "traza ilegible: %s" % fname,
                        "discrepancias": discrepancias, "incompletos": incompletos}
            if tdata.get("equivalencia") != "verificada" \
                    or not tdata.get("consumible"):
                discrepancias.append({"seccion": "trazabilidad_operaciones",
                                      "clave": fname,
                                      "motivo": "traza no consumible "
                                                "(equivalencia != verificada)"})
                return {"valido": False,
                        "motivo": "traza no consumible: %s" % fname,
                        "discrepancias": discrepancias, "incompletos": incompletos}
            seen.add(fname)
        for p in trades_dir.glob("trades_*.json"):
            if p.name not in seen:
                discrepancias.append({"seccion": "trazabilidad_operaciones",
                                      "clave": p.name,
                                      "motivo": "traza extra/obsoleta de una "
                                                "ejecución previa que no "
                                                "pertenece a la reconstrucción "
                                                "actual"})
                return {"valido": False,
                        "motivo": "traza obsoleta/extra: %s" % p.name,
                        "discrepancias": discrepancias, "incompletos": incompletos}
        return {"valido": True, "motivo": "trazas validadas contra "
                                          "reconstruction_manifest",
                "discrepancias": discrepancias, "incompletos": incompletos}

    def build(self):
        cells = self.data["cells"]
        filas = []
        summary = {
            "builder": {"h1": 0, "h3": 0, "h2ex": 0, "h2rev": 0,
                        "placebo": 0, "excl_gap": 0, "excl_no_entry": 0,
                        "excl_h2_nc": 0, "excl_h2_rec": 0},
            "selection": {"n_in": 0, "n_dev": 0, "n_oos": 0,
                          "n_purged": 0},
            "artefacto": {"eventos": 0, "trades": 0, "open": 0,
                          "skipped": 0},
            "hipotesis": {"eventos": 0, "trades": 0, "open": 0,
                          "skipped": 0, "realizadas": 0},
            "placebo": {"eventos": 0, "trades": 0, "open": 0,
                        "skipped": 0, "realizadas": 0},
            "total": {"eventos": 0, "trades": 0, "open": 0,
                      "skipped": 0, "realizadas": 0},
            "h15_direccional": {"celdas": 0, "negativas": 0,
                                "eventos": 0, "trades": 0, "open": 0,
                                "skipped": 0},
            "funding": {"settled": 0, "unknown_excluded": 0,
                        "uncovered_ms": 0, "gap_ms": 0,
                        "celdas_uncovered": 0, "celdas_totales": 0},
            "mfe_mae": {"mfe_min": None, "mfe_max": None,
                        "mae_min": None, "mae_max": None,
                        "mfe_min_n30": None, "mfe_max_n30": None,
                        "mae_min_n30": None, "mae_max_n30": None},
        }

        builder_seen = set()
        for d, sym, res in COMBOS:
            if d in builder_seen:
                continue
            builder_seen.add(d)
            if self.temp_dir is None:
                continue
            bp = self.base_dir / d / "build_report.json"
            if bp.exists():
                br = json.loads(bp.read_text(encoding="utf-8"))
                ct = br.get("counts", {})
                summary["builder"]["h1"] += ct.get("h1", 0)
                summary["builder"]["h3"] += ct.get("h3", 0)
                summary["builder"]["h2ex"] += ct.get("h2ex", 0)
                summary["builder"]["h2rev"] += ct.get("h2rev", 0)
                summary["builder"]["placebo"] += ct.get("placebo", 0)
                summary["builder"]["excl_gap"] += ct.get("excluded_gap", 0)
                summary["builder"]["excl_no_entry"] += ct.get("excluded_no_entry", 0)
                summary["builder"]["excl_h2_nc"] += ct.get("excluded_h2_no_confirmation", 0)
                summary["builder"]["excl_h2_rec"] += ct.get("excluded_h2_reclaim", 0)

        for d, sym, res in COMBOS:
            if self.temp_dir is None:
                continue
            sp = self.base_dir / d / ("selection_%s_%s.json" % (sym, res))
            if sp.exists():
                s = json.loads(sp.read_text(encoding="utf-8"))
                summary["selection"]["n_in"] += s.get("n_in", 0)
                summary["selection"]["n_dev"] += s.get("n_dev", 0)
                summary["selection"]["n_oos"] += s.get("n_oos", 0)
                summary["selection"]["n_purged"] += s.get("n_purged_dev_crossing", 0)

        for sym in cells:
            for res in cells[sym]:
                man = self._load_manifest(sym, res)
                sel = self._load_selection(sym, res)
                for fam in cells[sym][res]:
                    for split in cells[sym][res][fam]:
                        if "1.0" not in cells[sym][res][fam][split]:
                            continue
                        c = cells[sym][res][fam][split]["1.0"]
                        fk = family_kind(fam)
                        mseg = None
                        if man:
                            mseg = man["groups"].get(fam, {}).get(split, {}).get("1.0", {})
                        filas.append({
                            "symbol": sym, "res": res, "familia": fam,
                            "familia_tipo": fk, "segmento": split,
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
                            "selection": sel or {},
                        })

                        # Acumuladores artefacto
                        summary["artefacto"]["eventos"] += c["n_events"]
                        summary["artefacto"]["trades"] += c["n_trades"]
                        summary["artefacto"]["open"] += c["n_open"]
                        summary["artefacto"]["skipped"] += c["skipped_overlap"]
                        summary["total"]["eventos"] += c["n_events"]
                        summary["total"]["trades"] += c["n_trades"]
                        summary["total"]["open"] += c["n_open"]
                        summary["total"]["skipped"] += c["skipped_overlap"]

                        if fk == "baseline/placebo":
                            summary["placebo"]["eventos"] += c["n_events"]
                            summary["placebo"]["trades"] += c["n_trades"]
                            summary["placebo"]["open"] += c["n_open"]
                            summary["placebo"]["skipped"] += c["skipped_overlap"]
                        else:
                            summary["hipotesis"]["eventos"] += c["n_events"]
                            summary["hipotesis"]["trades"] += c["n_trades"]
                            summary["hipotesis"]["open"] += c["n_open"]
                            summary["hipotesis"]["skipped"] += c["skipped_overlap"]

                        if fk == "H1/H3 direccional" and res == "15m":
                            summary["h15_direccional"]["celdas"] += 1
                            summary["h15_direccional"]["eventos"] += c["n_events"]
                            summary["h15_direccional"]["trades"] += c["n_trades"]
                            summary["h15_direccional"]["open"] += c["n_open"]
                            summary["h15_direccional"]["skipped"] += c["skipped_overlap"]
                            if c["E_net"] < 0:
                                summary["h15_direccional"]["negativas"] += 1

                        # Funding por celda
                        if mseg:
                            fq = mseg.get("funding_quality", {})
                            if fq:
                                summary["funding"]["settled"] += fq.get("settled_events", 0)
                                summary["funding"]["unknown_excluded"] += fq.get("unknown_excluded", 0)
                                summary["funding"]["uncovered_ms"] += fq.get("uncovered_ms", 0)
                                summary["funding"]["gap_ms"] += fq.get("gap_ms", 0)
                                summary["funding"]["celdas_totales"] += 1
                                if fq.get("uncovered_ms", 0) > 0:
                                    summary["funding"]["celdas_uncovered"] += 1
                            else:
                                self.incomplete = True
                                self.incomplete_reasons.append(
                                    "funding_quality ausente en %s/%s/%s/%s"
                                    % (sym, res, fam, split))

                        # MFE/MAE
                        if mseg:
                            m = mseg.get("mfe_mean"); a = mseg.get("mae_mean")
                            n = mseg.get("n_trades", 0)
                            if m is not None and a is not None:
                                # global
                                mn = summary["mfe_mae"]["mfe_min"]
                                mx = summary["mfe_mae"]["mfe_max"]
                                summary["mfe_mae"]["mfe_min"] = m if mn is None else min(mn, m)
                                summary["mfe_mae"]["mfe_max"] = m if mx is None else max(mx, m)
                                mn = summary["mfe_mae"]["mae_min"]
                                mx = summary["mfe_mae"]["mae_max"]
                                summary["mfe_mae"]["mae_min"] = a if mn is None else min(mn, a)
                                summary["mfe_mae"]["mae_max"] = a if mx is None else max(mx, a)
                                # n>=30 direccional
                                if fam in H_DIRECCIONAL or fam in H2_FADE:
                                    if n >= 30:
                                        mn = summary["mfe_mae"]["mfe_min_n30"]
                                        mx = summary["mfe_mae"]["mfe_max_n30"]
                                        summary["mfe_mae"]["mfe_min_n30"] = m if mn is None else min(mn, m)
                                        summary["mfe_mae"]["mfe_max_n30"] = m if mx is None else max(mx, m)
                                        mn = summary["mfe_mae"]["mae_min_n30"]
                                        mx = summary["mfe_mae"]["mae_max_n30"]
                                        summary["mfe_mae"]["mae_min_n30"] = a if mn is None else min(mn, a)
                                        summary["mfe_mae"]["mae_max_n30"] = a if mx is None else max(mx, a)

        # Realizadas = trades - abiertas
        for clave in ("hipotesis", "placebo", "total"):
            s = summary[clave]
            s["realizadas"] = s["trades"] - s["open"]

        # --- Verificaciones sobre datos reales (funciones puras) ---
        causalidad = verificar_causalidad_poblacion(self.detecciones)
        causalidad["vinculos_h1h3"] = []
        duplicados_events = []
        for d, sym, res in COMBOS:
            if self.temp_dir is None:
                continue
            ep = self.base_dir / d / ("events_%s_%s.json" % (sym, res))
            if not ep.exists():
                continue
            evs = json.loads(ep.read_text(encoding="utf-8"))
            cp = self.base_dir / d / ("candles_%s_%s.json" % (sym, res))
            bars = None
            if cp.exists():
                bars = json.loads(cp.read_text(encoding="utf-8"))
                self._register_input("candles %s_%s" % (sym, res), cp)
            dets = [x for x in self.detecciones
                    if x.get("symbol") == sym
                    and x.get("source_interval") == res]
            orig = origenes_de_evento(evs, dets,
                                      {(sym, res): bars} if bars else None)
            dup = clasificar_duplicados_semanticos(evs, orig)
            vin = vincular_eventos_h1h3(evs, dets)
            duplicados_events.append({
                "symbol": sym, "res": res,
                "claves_unicas": dup["claves_unicas"],
                "claves_duplicadas": dup["claves_duplicadas"],
                "filas_extra": dup["filas_extra"],
                "errores": dup["errores"],
                "permitidos": dup["permitidos"],
                "n_origenes_placebo": sum(
                    1 for v in orig.values() if "placebo" in v),
            })
            causalidad["vinculos_h1h3"].append({
                "symbol": sym, "res": res, **vin})
        # Vínculo global H1/H3 (agregado)
        todos_evs = []
        for d, sym, res in COMBOS:
            if self.temp_dir is None:
                continue
            ep = self.base_dir / d / ("events_%s_%s.json" % (sym, res))
            if ep.exists():
                todos_evs.extend(json.loads(ep.read_text(encoding="utf-8")))
        vinculo_global = vincular_eventos_h1h3(todos_evs, self.detecciones)
        filas_censo = [{"symbol": x.get("symbol"),
                        "interval": x.get("source_interval"),
                        "formation_time": x.get("formation_time"),
                        "definition_name": x.get("definition_name")}
                       for x in self.detecciones]
        censo_dup = verificar_censo_duplicados(filas_censo)
        referencias = verificar_referencias(self.data, self._manifiestos())
        economicos = verificar_campos_economicos(self.data, self._manifiestos())

        # --- Trazabilidad hasta la operación (trades reconstruidos) ---
        # El ledger valida reconstruction_manifest.json (veredicto,
        # cobertura y hashes de las trazas) ANTES de consumir las trazas.
        # Un manifiesto con veredicto FAIL, hashes que no coinciden,
        # trazas faltantes/extra/obsoletas o archivos no consumibles
        # hace que el ledger rechace las trazas (RECHAZADA → INCOMPLETE).
        mans = self._manifiestos()
        trazabilidad = {"estado": "UNKNOWN",
                        "motivo": "trades no proporcionados "
                                  "(--trades-dir o reconstruir con "
                                  "reconstruct_replay_traces.py)",
                        "discrepancias": [], "incompletos": []}
        if self.trades_dir is not None:
            vt = self._validar_manifest_traces(self.trades_dir)
            if not vt["valido"]:
                trazabilidad = {
                    "estado": ("COMPLETO_CON_DISCREPANCIAS"
                               if vt["discrepancias"] else "INCOMPLETE"),
                    "motivo": vt["motivo"],
                    "discrepancias": vt.get("discrepancias", []),
                    "incompletos": vt.get("incompletos", []),
                    "n_trades_revisados": 0}
            elif self.trades:
                discrep_op = []
                incompletos_op = []
                n_rev = 0
                for (sym, res), tdata in self.trades.items():
                    trades = tdata.get("trades", [])
                    man = mans.get((sym, res), {})
                    dets = [x for x in self.detecciones
                            if x.get("symbol") == sym
                            and x.get("source_interval") == res]
                    bars = None
                    for d, s, r in COMBOS:
                        if s == sym and r == res and self.base_dir is not None:
                            cp = self.base_dir / d / ("candles_%s_%s.json" % (sym, res))
                            if cp.exists():
                                bars = json.loads(cp.read_text(encoding="utf-8"))
                    v = vincular_trades_eventos(trades, mans, dets,
                                                {(sym, res): bars}
                                                if bars else None)
                    n_rev += v["n_trades_revisados"]
                    discrep_op.extend(v["discrepancias"])
                    incompletos_op.extend(v.get("incompletos", []))
                    discrep_op.extend(verificar_multiplicidad_trades(trades, man))
                trazabilidad = {
                    "estado": ("COMPLETO" if not discrep_op and not incompletos_op
                               else ("COMPLETO_CON_DISCREPANCIAS"
                                     if discrep_op else "INCOMPLETE")),
                    "n_trades_revisados": n_rev,
                    "discrepancias": discrep_op,
                    "incompletos": incompletos_op}

        # --- Tail-edge: exclusiones esperadas verificables ---
        tail_edge = clasificar_tail_edge(self.detecciones,
                                         self._build_reports())

        # --- Veredicto global (integra todas las secciones) ---
        secciones = {
            "adquisicion": {
                "incompleta": self.incomplete,
                "motivo": "; ".join(self.incomplete_reasons)},
            "causalidad": causalidad,
            "referencias": referencias,
            "campos_economicos": economicos,
            "duplicados_events": duplicados_events,
            "vinculos_h1h3": [v for v in causalidad.get("vinculos_h1h3", [])],
            "descartes": self._descartes_global(),
            "funding": {"incompleto": self._funding_incompleto()},
            "trazabilidad_operaciones": trazabilidad,
            "tail_edge": tail_edge,
        }
        veredicto = veredicto_global(secciones)

        reporte = {
            "estatus": veredicto["estado"],
            "veredicto": veredicto,
            "incomplete_reasons": self.incomplete_reasons,
            "trazabilidad_operaciones": trazabilidad,
            "tail_edge": tail_edge,
            "descartes_global": self._descartes_global(),
            "procedencia": {
                "artefacto": _ruta_repo(self.artifact_path),
                "artefacto_sha256": self.artifact_sha256,
                "inputs_externos": self.inputs,
                "temp_limitacion": ("Manifiestos, funding y detecciones en "
                                     "temp/opencode (fuera de Git). Si faltan, "
                                     "el estatus es INCOMPLETE."),
            },
            "validacion_artefacto": {
                "errores": self.validation_errors,
                "valido": len(self.validation_errors) == 0,
            },
            "causalidad": causalidad,
            "vinculo_h1h3_global": {k: v for k, v in vinculo_global.items()
                                    if not isinstance(v, list)},
            "campos_economicos": economicos,
            "duplicados_censo": censo_dup,
            "duplicados_events": duplicados_events,
            "referencias": {k: v for k, v in referencias.items()
                            if not isinstance(v, list)},
            "referencias_detalle": {
                "solo_artefacto_con_eventos":
                    referencias["solo_artefacto_con_eventos"],
                "solo_manifiesto": referencias["solo_manifiesto"],
                "campos_incompatibles": referencias["campos_incompatibles"],
            },
            "builder": summary["builder"],
            "selection_purge": summary["selection"],
            "artefacto_final": summary["artefacto"],
            "conteos": {
                "hipotesis": summary["hipotesis"],
                "placebo": summary["placebo"],
                "total": summary["total"],
            },
            "h15_direccional": summary["h15_direccional"],
            "mfe_mae": {
                k: (round(v, 6) if isinstance(v, float) else v)
                for k, v in summary["mfe_mae"].items()
            },
            "funding": summary["funding"],
            "filas": filas,
        }
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self.out_path.write_text(json.dumps(reporte, indent=2,
                                            default=str), encoding="utf-8")
        return reporte


def main(argv=None):
    ap = ArgumentParser(description="Ledger de auditoría EVAL-CENSUS-V2.")
    ap.add_argument("--artifact", default=str(ARTIFACT_DEFAULT),
                    help="ruta al artefacto census-eval-v2.json")
    ap.add_argument("--temp-dir", default=None,
                    help="directorio temp con manifiestos (fuera de Git)")
    ap.add_argument("--package", default=None,
                    help="paquete de evidencia publicado (combos/<dir>/...)")
    ap.add_argument("--trades-dir", default=None,
                    help="directorio con trades_*.json reconstruidos")
    ap.add_argument("--out", default=str(OUT_DEFAULT),
                    help="ruta del informe JSON de salida")
    args = ap.parse_args(argv)

    artifact_path = Path(args.artifact)
    out_path = Path(args.out)
    temp_dir = Path(args.temp_dir) if args.temp_dir else None
    package = Path(args.package) if args.package else None
    trades_dir = Path(args.trades_dir) if args.trades_dir else None

    ledger = Ledger(artifact_path, temp_dir, out_path)
    ledger.load(package=package, trades_dir=trades_dir)
    reporte = ledger.build()

    print("veredicto global:", reporte["veredicto"]["estado"])
    print("discrepancias: %d" % len(reporte["veredicto"]["discrepancias"]))
    for d in reporte["veredicto"]["discrepancias"]:
        print("  - [%s] %s: %s" % (d["seccion"], d["clave"], d["motivo"]))
    print("incompleto: %d" % len(reporte["veredicto"]["incompleto"]))
    for d in reporte["veredicto"]["incompleto"]:
        print("  - [%s] %s" % (d["seccion"], d["motivo"]))
    print("artefacto sha256:", reporte["procedencia"]["artefacto_sha256"])
    print("hipotesis: eventos=%d trades=%d abiertas=%d skipped=%d realizadas=%d" % (
        reporte["conteos"]["hipotesis"]["eventos"],
        reporte["conteos"]["hipotesis"]["trades"],
        reporte["conteos"]["hipotesis"]["open"],
        reporte["conteos"]["hipotesis"]["skipped"],
        reporte["conteos"]["hipotesis"]["realizadas"]))
    print("placebo: eventos=%d trades=%d abiertas=%d skipped=%d realizadas=%d" % (
        reporte["conteos"]["placebo"]["eventos"],
        reporte["conteos"]["placebo"]["trades"],
        reporte["conteos"]["placebo"]["open"],
        reporte["conteos"]["placebo"]["skipped"],
        reporte["conteos"]["placebo"]["realizadas"]))
    print("total: eventos=%d trades=%d abiertas=%d skipped=%d realizadas=%d" % (
        reporte["conteos"]["total"]["eventos"],
        reporte["conteos"]["total"]["trades"],
        reporte["conteos"]["total"]["open"],
        reporte["conteos"]["total"]["skipped"],
        reporte["conteos"]["total"]["realizadas"]))
    print("h15 direccional: celdas=%d negativas=%d" % (
        reporte["h15_direccional"]["celdas"],
        reporte["h15_direccional"]["negativas"]))
    print("funding: settled=%d unknown=%d uncovered_ms=%d celdas_uncovered=%d/%d" % (
        reporte["funding"]["settled"],
        reporte["funding"]["unknown_excluded"],
        reporte["funding"]["uncovered_ms"],
        reporte["funding"]["celdas_uncovered"],
        reporte["funding"]["celdas_totales"]))
    print("trazabilidad operaciones: %s" % reporte["trazabilidad_operaciones"]["estado"])
    print("tail-edge: %s" % reporte["tail_edge"]["estado"])
    print("informe escrito en", out_path)
    return 0 if reporte["veredicto"]["exitoso"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
