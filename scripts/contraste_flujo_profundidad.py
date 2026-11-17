# -*- coding: utf-8 -*-
"""Contraste principal exploratorio: flujo/profundidad vs continuacion/reversion.

Pregunta economica: ¿El flujo agresor frente a la profundidad, observado al
decidir, distingue continuación de reversión mejor que asumir continuación
por el signo del movimiento de 24 horas?

Este bloque es EXPLORATORIO. Los resultados de esta captura ya fueron
examinados: no se presenta como prueba independiente ni como protocolo
prerregistrado.

Definiciones (fijadas ANTES de generar agregados):
- ratio = (buy_notional - sell_notional) / (bid_notional_top20 + ask_notional_top20)
  con flujo de 60 segundos y profundidad top20 efectivamente registrada.
- ratio_alineado = signo(move_24h_pct) * ratio
  (buy - sell a favor del movimiento previo si > 0, contrario si < 0).
- Se exige: buy_notional y sell_notional validos, denominador finito y
  estrictamente positivo, move_24h_pct valido y distinto de cero.
- Cero o datos insuficientes: grupo separado, nunca convertido en cero.

Resultado posterior (horizonte principal 60 min, causal):
- precio_inicial = ref_close: close de la ultima vela 1m plenamente conocida
  en T (close_time_ms <= decision_ms).
- precio_final = close de la vela mas reciente con close_time_ms <= T + 60 min.
  Si no existe una vela valida (desfase < 60 000 ms respecto del objetivo),
  la observacion se conserva en el denominador como limitada, con motivo.
  NO se convierte su retorno en cero.
- retorno = (precio_final - precio_inicial) / precio_inicial
- retorno_alineado = signo(move_24h_pct) * retorno
- continuacion: retorno_alineado > 0
- reversión: retorno_alineado < 0
- neutral: retorno_alineado == 0 exactamente

Acreditacion del horizonte (correccion):
- Para cada objetivo (T y T + 60 min) se selecciona la ultima vela 1m
  plenamente cerrada conocida en/antes del objetivo.
- Exige desfase = objetivo - close_time_ms: no negativo y menor de 60 000 ms.
- Exige que la vela corresponda a la cuadrícula del minuto:
  open_time_ms multiplo de 60 000 y close_time_ms == open_time_ms + 59 999.
- No se usa una vela antigua como sustituto silencioso del precio al horizonte,
  ni cierres posteriores a cada objetivo.
- Se declara el horizonte efectivo (close_final - close_inicial) y cualquier
  discrepancia respecto de 60 min.

Usa TODAS las 161 observaciones aptas con datos suficientes, no solo las
124 operaciones contrafactuales admitidas.

Uso:
    python scripts/contraste_flujo_profundidad.py
        --run-dir <directorio fuente de la corrida>
        --out-dir  <directorio de derivados (se crea si no existe)>

Salida (derivado, fuera de Git):
  <out-dir>/contraste_flujo_profundidad.json
  <out-dir>/contraste_filas.jsonl (una fila por observacion apta evaluada)
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:\proyectos\binance-futures-microstructure-bot")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from microstructure_probe.paper_lab_engine import PaperCandle

HORIZON_MS = 60 * 60 * 1000  # 60 minutos
STEP_MS = 60 * 1000  # 1 minuto
MAX_DESFASE_MS = 60_000  # menor de un minuto respecto del objetivo
T0 = 1794857178038  # started_ms de config_inicial de la ventana 4


def utc_iso(ms):
    if ms is None:
        return None
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()


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


def signo(x):
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"n": 0, "media": None, "mediana": None, "min": None, "max": None}
    ordenados = sorted(vals)
    n = len(ordenados)
    mediana = (ordenados[n // 2] if n % 2 == 1
               else (ordenados[n // 2 - 1] + ordenados[n // 2]) / 2.0)
    return {
        "n": n,
        "media": round(sum(vals) / n, 8),
        "mediana": round(mediana, 8),
        "min": round(min(vals), 8),
        "max": round(max(vals), 8),
    }


def proporcionar(n, total):
    return round(n / total, 6) if total else None


def seleccionar_vela_cerrada(cuerpo_json, objetivo_ms):
    """
    Selecciona la ultima vela 1m plenamente cerrada conocida en/antes de
    objetivo_ms.

    Devuelve dict con:
      - open_time_ms, close_time_ms, precio_close: de la vela elegida (None si no hay valida)
      - desfase_ms: objetivo_ms - close_time_ms (None si no hay valida)
      - valido: bool
      - motivo: str si no valido, None si valida

    Reglas de validez:
      - close_time_ms <= objetivo_ms (no se usan cierres futuros).
      - 0 <= desfase_ms < MAX_DESFASE_MS (la vela cierra dentro del mismo
        minuto que el objetivo; nunca una vela antigua como sustituto silencioso).
      - Grid del minuto: open_time_ms multiplo de 60 000 y
        close_time_ms == open_time_ms + 59 999.
    """
    cuerpo = json.loads(cuerpo_json)
    mejor = None
    for r in cuerpo:
        ot = int(r[0])
        ct = int(r[6]) if r[6] is not None else None
        if ct is None or ct > objetivo_ms:
            continue
        # Grid del minuto: apertura alineada y cierre un minuto menos un ms.
        grid_ok = (ot % STEP_MS == 0) and (ct == ot + STEP_MS - 1)
        if not grid_ok:
            continue
        desfase = objetivo_ms - ct
        if desfase < 0 or desfase >= MAX_DESFASE_MS:
            continue
        if mejor is None or ct > mejor["close_time_ms"]:
            mejor = {
                "open_time_ms": ot,
                "close_time_ms": ct,
                "precio_close": float(r[4]),
                "desfase_ms": desfase,
                "valido": True,
                "motivo": None,
            }
    if mejor is None:
        return {
            "valido": False,
            "motivo": "sin_vela_cerrada_en_objetivo",
            "open_time_ms": None,
            "close_time_ms": None,
            "precio_close": None,
            "desfase_ms": None,
        }
    return mejor


def analizar(run_dir: Path, out_dir: Path) -> dict:
    """Ejecuta el contraste y escribe los derivados en out_dir."""
    if not run_dir.exists():
        raise ValueError(f"run-dir inexistente: {run_dir}")
    for nombre in ("observaciones.jsonl", "consultas_klines.jsonl",
                   "config_inicial.json", "resultado_operativo.jsonl"):
        if not (run_dir / nombre).exists():
            raise ValueError(f"fuente necesaria ausente o corrupta: {nombre}")

    out_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------
    # Cargar fuentes
    # -------------------------------------------------------------------
    observaciones = []
    for line in io.open(run_dir / "observaciones.jsonl", encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        if o.get("kind") == "observacion" and o.get("apto_para_evaluacion") is True:
            observaciones.append(o)

    klines = {}
    for line in io.open(run_dir / "consultas_klines.jsonl", encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        klines[o["observation_id"]] = o

    # -------------------------------------------------------------------
    # Contrastes fila a fila
    # -------------------------------------------------------------------
    filas = []
    grupos = {"flujo_a_favor": 0, "flujo_contrario": 0, "insuficiente": 0}
    retornos_cruzados = {
        ("flujo_a_favor", "continuacion"): [],
        ("flujo_a_favor", "reversion"): [],
        ("flujo_a_favor", "neutral"): [],
        ("flujo_contrario", "continuacion"): [],
        ("flujo_contrario", "reversion"): [],
        ("flujo_contrario", "neutral"): [],
        ("insuficiente", "continuacion"): [],
        ("insuficiente", "reversion"): [],
        ("insuficiente", "neutral"): [],
    }
    exclusiones = {"sin_klines": 0, "ratio_invalido": 0,
                   "horizonte_no_resoluble": 0, "move_24h_invalido": 0}

    for o in observaciones:
        oid = o["observation_id"]
        fila = {
            "observation_id": oid,
            "symbol": o["symbol"],
            "role": o.get("role"),
            "decision_ms": int(o["decision_ms"]),
            "decision_iso": o.get("decision_iso"),
            "ciclo": int((int(o["decision_ms"]) - T0) // 300000),
            "side_selector": o.get("side"),
            "move_24h_pct": (o.get("seleccion") or {}).get("move_24h_pct"),
            "flujo_window_ms": (o.get("flujo") or {}).get("window_ms"),
            "flujo_ventana_completa": (o.get("flujo") or {}).get("ventana_completa"),
            "libro_presente": (o.get("libro") or {}).get("event_ms") is not None,
            "disponibilidad": o.get("disponibilidad"),
            "cobertura": o.get("cobertura"),
            "reconstruido": False,
            "motivo_exclusion": None,
            # Trazabilidad del horizonte
            "objetivo_inicial_ms": int(o["decision_ms"]),
            "objetivo_final_ms": int(o["decision_ms"]) + HORIZON_MS,
            "inicial_open_ms": None, "inicial_close_ms": None,
            "inicial_desfase_ms": None, "inicial_valido": False,
            "final_open_ms": None, "final_close_ms": None,
            "final_desfase_ms": None, "final_valido": False,
            "horizonte_efectivo_ms": None, "horizonte_discrepante": False,
        }
        flujo = o.get("flujo") or {}
        libro = o.get("libro") or {}
        buy = flujo.get("buy_notional")
        sell = flujo.get("sell_notional")
        bid_top20 = libro.get("bid_notional_top20")
        ask_top20 = libro.get("ask_notional_top20")
        move = fila["move_24h_pct"]

        if oid not in klines:
            fila["motivo_exclusion"] = "sin_klines"
            exclusiones["sin_klines"] += 1
            filas.append(fila)
            grupos["insuficiente"] += 1
            continue
        if move is None or move == 0:
            fila["motivo_exclusion"] = "move_24h_invalido"
            exclusiones["move_24h_invalido"] += 1
            filas.append(fila)
            grupos["insuficiente"] += 1
            continue
        if buy is None or sell is None:
            fila["motivo_exclusion"] = "ratio_invalido"
            exclusiones["ratio_invalido"] += 1
            filas.append(fila)
            grupos["insuficiente"] += 1
            continue
        denominador = (float(bid_top20) if bid_top20 is not None else 0.0) + \
            (float(ask_top20) if ask_top20 is not None else 0.0)
        if denominador <= 0:
            fila["motivo_exclusion"] = "ratio_invalido"
            exclusiones["ratio_invalido"] += 1
            filas.append(fila)
            grupos["insuficiente"] += 1
            continue

        ratio = (float(buy) - float(sell)) / denominador
        ratio_alineado = signo(move) * ratio
        fila["buy_notional"] = float(buy)
        fila["sell_notional"] = float(sell)
        fila["bid_notional_top20"] = float(bid_top20) if bid_top20 is not None else None
        fila["ask_notional_top20"] = float(ask_top20) if ask_top20 is not None else None
        fila["ratio"] = ratio
        fila["ratio_alineado"] = ratio_alineado

        cuerpo = klines[oid]["cuerpo"]
        T = int(o["decision_ms"])

        inicial = seleccionar_vela_cerrada(cuerpo, T)
        final = seleccionar_vela_cerrada(cuerpo, T + HORIZON_MS)

        fila["inicial_open_ms"] = inicial["open_time_ms"]
        fila["inicial_close_ms"] = inicial["close_time_ms"]
        fila["inicial_desfase_ms"] = inicial["desfase_ms"]
        fila["inicial_valido"] = inicial["valido"]
        fila["final_open_ms"] = final["open_time_ms"]
        fila["final_close_ms"] = final["close_time_ms"]
        fila["final_desfase_ms"] = final["desfase_ms"]
        fila["final_valido"] = final["valido"]

        if not inicial["valido"]:
            fila["motivo_exclusion"] = "precio_inicial_no_valido"
            exclusiones["horizonte_no_resoluble"] += 1
            filas.append(fila)
            grupos["insuficiente"] += 1
            continue
        if not final["valido"]:
            fila["motivo_exclusion"] = "horizonte_no_resoluble"
            exclusiones["horizonte_no_resoluble"] += 1
            filas.append(fila)
            grupos["insuficiente"] += 1
            continue

        horizonte_efectivo = final["close_time_ms"] - inicial["close_time_ms"]
        fila["horizonte_efectivo_ms"] = horizonte_efectivo
        fila["horizonte_discrepante"] = abs(horizonte_efectivo - HORIZON_MS) >= STEP_MS
        if fila["horizonte_discrepante"]:
            fila["motivo_exclusion"] = "horizonte_efectivo_discrepante"
            exclusiones["horizonte_no_resoluble"] += 1
            filas.append(fila)
            grupos["insuficiente"] += 1
            continue

        precio_inicial = inicial["precio_close"]
        precio_final = final["precio_close"]
        fila["precio_inicial_ref_close"] = precio_inicial
        fila["precio_final_60m"] = precio_final

        retorno = (precio_final - precio_inicial) / precio_inicial
        retorno_alineado = signo(move) * retorno
        fila["retorno"] = retorno
        fila["retorno_alineado"] = retorno_alineado
        fila["reconstruido"] = True

        if ratio_alineado > 0:
            fila["grupo_ratio"] = "flujo_a_favor"
            grupos["flujo_a_favor"] += 1
        elif ratio_alineado < 0:
            fila["grupo_ratio"] = "flujo_contrario"
            grupos["flujo_contrario"] += 1
        else:
            fila["grupo_ratio"] = "insuficiente"
            grupos["insuficiente"] += 1

        if retorno_alineado > 0:
            fila["resultado"] = "continuacion"
        elif retorno_alineado < 0:
            fila["resultado"] = "reversion"
        else:
            fila["resultado"] = "neutral"
        retornos_cruzados[(fila["grupo_ratio"], fila["resultado"])].append(
            retorno_alineado)
        filas.append(fila)

    # Escritura filas fila a fila
    filas_jsonl = out_dir / "contraste_filas.jsonl"
    with io.open(filas_jsonl, "w", encoding="utf-8", newline="\n") as f:
        for fila in filas:
            f.write(json.dumps(fila, ensure_ascii=False, sort_keys=True) + "\n")

    # -------------------------------------------------------------------
    # Agregados
    # -------------------------------------------------------------------
    total_evaluadas = len(filas)

    regla_sencilla_aciertos = 0
    regla_sencilla_total = 0
    for f in filas:
        if not f["reconstruido"]:
            continue
        regla_sencilla_total += 1
        if f["retorno_alineado"] > 0:
            regla_sencilla_aciertos += 1

    def proporcionar_resultado(grupo_ratio, resultado_key):
        n = grupos[grupo_ratio]
        if n == 0:
            return {"n": 0, "proporcion_sobre_grupo": None,
                    "continuacion": 0, "reversion": 0, "neutral": 0,
                    "retorno_alineado": stats([])}
        vals = retornos_cruzados[(grupo_ratio, resultado_key)]
        return {
            "n": len(vals),
            "proporcion_sobre_grupo": round(len(vals) / n, 6),
            "continuacion": sum(1 for v in vals if v > 0),
            "reversion": sum(1 for v in vals if v < 0),
            "neutral": sum(1 for v in vals if v == 0),
            "retorno_alineado": stats(vals),
        }

    resumen = {
        "source_run_id": "exp-v2-ventana-4-20261116a",
        "origen": ("contraste exploratorio offline; no prueba independiente ni "
                   "protocolo prerregistrado"),
        "metodo": ("ratio=(buy_notional-sell_notional)/(bid_notional_top20+ask_notional_top20), "
                   "ratio_alienado=signo(move_24h_pct)*ratio; retorno a 60 min causal; "
                   "datos fuente sin modificar; horizonte acreditado por velas cerradas "
                   "con desfase < 60 000 ms respecto de cada objetivo"),
        "definiciones": {
            "ratio": "(buy_notional - sell_notional) / (bid_notional_top20 + ask_notional_top20)",
            "ratio_alineado": "signo(move_24h_pct) * ratio",
            "horizonte_ms": HORIZON_MS,
            "precio_inicial": "ref_close (close ultima vela 1m plenamente conocida en T)",
            "precio_final": "close vela mas reciente con close_time_ms <= T + 60 min",
            "retorno_alineado": "signo(move_24h_pct) * (precio_final - precio_inicial)/precio_inicial",
            "continuacion": "retorno_alineado > 0",
            "reversion": "retorno_alineado < 0",
            "neutral": "retorno_alineado == 0",
            "desfase_maximo_ms": MAX_DESFASE_MS,
        },
        "denominador": {
            "observaciones_aptas": len(observaciones),
            "filas_evaluadas": total_evaluadas,
            "grupo_flujo_a_favor": grupos["flujo_a_favor"],
            "grupo_flujo_contrario": grupos["flujo_contrario"],
            "grupo_datos_insuficientes": grupos["insuficiente"],
            "exclusiones": exclusiones,
        },
        "resultado_por_grupo_ratio": {
            "flujo_a_favor": {
                "n": grupos["flujo_a_favor"],
                "proporcion_sobre_evaluadas": proporcionar(
                    grupos["flujo_a_favor"], total_evaluadas),
                "continuacion": proporcionar_resultado("flujo_a_favor",
                                                       "continuacion"),
                "reversion": proporcionar_resultado("flujo_a_favor", "reversion"),
                "neutral": proporcionar_resultado("flujo_a_favor", "neutral"),
            },
            "flujo_contrario": {
                "n": grupos["flujo_contrario"],
                "proporcion_sobre_evaluadas": proporcionar(
                    grupos["flujo_contrario"], total_evaluadas),
                "continuacion": proporcionar_resultado("flujo_contrario",
                                                       "continuacion"),
                "reversion": proporcionar_resultado("flujo_contrario",
                                                    "reversion"),
                "neutral": proporcionar_resultado("flujo_contrario", "neutral"),
            },
            "datos_insuficientes": {
                "n": grupos["insuficiente"],
                "proporcion_sobre_evaluadas": proporcionar(
                    grupos["insuficiente"], total_evaluadas),
            },
        },
        "regla_sencilla_referencia": {
            "n": regla_sencilla_total,
            "aciertos_retorno_alineado_positivo": regla_sencilla_aciertos,
            "proporcion_aciertos": (round(regla_sencilla_aciertos /
                                        regla_sencilla_total, 6)
                                    if regla_sencilla_total else None),
            "nota": "direccion = signo(move_24h_pct), sin confirmacion de flujo",
        },
    }
    with io.open(out_dir / "contraste_flujo_profundidad.json", "w",
                 encoding="utf-8", newline="\n") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(json.dumps(resumen, ensure_ascii=False, indent=1)[:6000])
    print("\nEscrito:", filas_jsonl, out_dir / "contraste_flujo_profundidad.json")
    return resumen


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Contraste exploratorio flujo/profundidad vs continuacion/reversion (offline).")
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
