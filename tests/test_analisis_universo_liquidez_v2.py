"""Pruebas portables del analizador universo-liquidez-v1 v2.

Usan JSONL temporales construidos a mano (no dependen del dataset externo) e
invocan el CLI real al menos una vez, comprobando los archivos generados.

Casos cubiertos:
- campos ausentes / no finitos en flujo y libro;
- denominador de profundidad cero o invalido (produce ratio None, nunca cero);
- observation_id duplicados;
- resultados faltantes (horizonte sin par);
- selecciones sin observacion emitida (ciclos de ciclo con selected sin observacion);
- una entrada sin libro ni flujo produce cero parejas validas y nunca
  publica "168/168";
- ponderaciones con un ejemplo pequeno calculado a mano;
- distinguir comprobaciones portables de comprobaciones contra dataset externo.
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "analisis_universo_liquidez_v2.py"


def _escribir_jsonl(ruta: Path, objetos: list[dict]) -> None:
    with open(ruta, "w", encoding="utf-8") as fh:
        for o in objetos:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")


def _hacer_observacion(
    simbolo="SYM",
    role="candidate",
    estado="observada",
    lado="UP",
    decision_ms=1000,
    referencia_ms=900,
    buy=None,
    sell=None,
    bid=None,
    ask=None,
    ventana_completa=True,
    retorno_5m=0.01,
    retorno_15m=0.02,
    retorno_60m=0.03,
    motivo=None,
):
    obs = {
        "kind": "observacion",
        "symbol": simbolo,
        "role": role,
        "estado": estado,
        "decision_ms": decision_ms,
        "observation_id": "%s|%s" % (simbolo, decision_ms),
        "side": lado,
        "flujo": {},
        "libro": {},
        "cobertura": {"flujo_ventana_completa": ventana_completa},
        "motivos": [motivo] if motivo else [],
    }
    if buy is not None or sell is not None:
        obs["flujo"] = {
            "buy_notional": buy,
            "sell_notional": sell,
            "window_ms": 60000,
            "ventana_completa": ventana_completa,
        }
    if bid is not None or ask is not None:
        obs["libro"] = {
            "bid_notional_top20": bid,
            "ask_notional_top20": ask,
        }
    return obs


def _hacer_resultado(observation_id, horizon, retorno, estado="resuelto"):
    return {
        "kind": "resultado",
        "observation_id": observation_id,
        "horizon": horizon,
        "retorno": retorno,
        "estado": estado,
        "neto": None,
        "neto_estado": "UNKNOWN",
        "precio_base": 100.0,
        "precio_base_fuente": "libro_mid",
        "precio_posterior": 100.0 * (1 + retorno) if retorno is not None else None,
        "precio_posterior_fuente": "klines_apertura_1m",
    }


def _hacer_ciclo(reference_ms, decision_ms, simbolos_cand, simbolos_comp):
    return {
        "kind": "ciclo",
        "cycle_id": "c-%s" % reference_ms,
        "reference_ms": reference_ms,
        "reference_iso": "2026-01-01T00:00:00Z",
        "selected": [
            {"symbol": s, "side": "UP" if i % 2 == 0 else "DOWN"}
            for i, s in enumerate(simbolos_cand)
        ],
        "comparator": [
            {"symbol": s, "side": None} for s in simbolos_comp
        ],
        "decision_ms": decision_ms,
    }


@pytest.fixture
def tmp_run(tmp_path):
    """Crea un JSONL temporal, ejecuta el CLI real y devuelve rutas y tablas."""
    jsonl = tmp_path / "obs.jsonl"
    out_derivados = tmp_path / "derivados"
    out_tablas = tmp_path / "tablas"
    return {
        "jsonl": jsonl,
        "out_derivados": out_derivados,
        "out_tablas": out_tablas,
        "tablas_json": out_tablas / "resumen_analisis_universo_liquidez_v2.json",
        "derivado_json": out_derivados / "analisis_completo_v2.json",
    }


def _ejecutar_cli(tmp_run):
    cmd = [
        sys.executable, str(SCRIPT),
        "--jsonl", str(tmp_run["jsonl"]),
        "--out-derivados", str(tmp_run["out_derivados"]),
        "--out-tablas", str(tmp_run["out_tablas"]),
        "--run_id", "test-run-temporal",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, "CLI fallo: %s" % res.stderr
    assert tmp_run["tablas_json"].exists(), "tabla no generada"
    assert tmp_run["derivado_json"].exists(), "derivado no generado"
    return json.loads(tmp_run["tablas_json"].read_text(encoding="utf-8"))


# -------------------- CLI real: happy path --------------------

def test_cli_real_genera_archivos(tmp_run):
    objetos = []
    ciclos = [
        _hacer_ciclo(900, 1000, ["AAA", "BBB"], ["CCC", "DDD"]),
        _hacer_ciclo(2000, 2100, ["EEE"], ["FFF"]),
    ]
    observaciones = [
        _hacer_observacion("AAA", "candidate", "observada", "UP", 1000, 900, 100, 50, 1000, 500, True, 0.01, 0.02, 0.03),
        _hacer_observacion("BBB", "candidate", "observada", "DOWN", 1000, 900, 200, 100, 800, 400, True, -0.005, -0.01, -0.02),
        _hacer_observacion("CCC", "comparator", "observada", None, 1000, 900, 150, 75, 900, 450, True, 0.001, 0.002, 0.003),
        _hacer_observacion("DDD", "comparator", "observada", None, 1000, 900, 300, 50, 600, 300, True, -0.002, -0.004, -0.006),
        _hacer_observacion("EEE", "candidate", "observada", "UP", 2100, 2000, 500, 250, 400, 200, True, 0.02, 0.04, 0.06),
        _hacer_observacion("FFF", "comparator", "observada", None, 2100, 2000, 100, 60, 300, 150, True, 0.005, 0.01, 0.015),
    ]
    resultados = []
    for o in observaciones:
        oid = o["observation_id"]
        for h, ret in (("5m", 0.01), ("15m", 0.02), ("60m", 0.03)):
            pass
    # resultados específicos por observacion
    resultado_por_obs = {
        "AAA|1000": {"5m": 0.01, "15m": 0.02, "60m": 0.03},
        "BBB|1000": {"5m": -0.005, "15m": -0.01, "60m": -0.02},
        "CCC|1000": {"5m": 0.001, "15m": 0.002, "60m": 0.003},
        "DDD|1000": {"5m": -0.002, "15m": -0.004, "60m": -0.006},
        "EEE|2100": {"5m": 0.02, "15m": 0.04, "60m": 0.06},
        "FFF|2100": {"5m": 0.005, "15m": 0.01, "60m": 0.015},
    }
    for oid, por_h in resultado_por_obs.items():
        simbolo = oid.split("|")[0]
        decision = oid.split("|")[1]
        for h, ret in por_h.items():
            resultados.append(_hacer_resultado(oid, h, ret))
    objetos = ciclos + observaciones + resultados
    _escribir_jsonl(tmp_run["jsonl"], objetos)

    tablas = _ejecutar_cli(tmp_run)
    rg = tablas["resumen_global"]
    assert rg["seleccionados_total"] == 6  # 3 cand + 2 comp + 1 cand
    assert rg["seleccionados_por_rol"] == {"candidate": 3, "comparator": 3}
    assert rg["observaciones_total"] == 6
    assert rg["observaciones_aptas"] == 6
    assert rg["observaciones_descartadas"] == 0
    assert rg["total_sin_observacion"] == 0
    assert rg["resultados_total"] == 18
    assert rg["resultados_por_horizonte"] == {"5m": 6, "15m": 6, "60m": 6}

    # nunca publica "168/168" (ese texto es del dataset externo, no del temporal)
    derivado = json.loads(tmp_run["derivado_json"].read_text(encoding="utf-8"))
    asoc = derivado["asociaciones"]
    assert asoc["n_filas_totales"] == 18
    assert asoc["parejas_validas_por_horizonte"] == {"5m": 6, "15m": 6, "60m": 6}
    assert asoc["n_campos_ausentes_o_no_finitos"] == 0
    assert asoc["n_profundidad_cero_o_invalida"] == 0


# -------------------- campos ausentes / denominador cero --------------------

def test_campos_ausentes_no_publican_disponibilidad_completa(tmp_run):
    objetos = [
        _hacer_ciclo(900, 1000, ["AAA"], ["CCC"]),
        # AAA: sin flujo ni libro -> cero parejas validas
        _hacer_observacion("AAA", "candidate", "observada", "UP", 1000, 900, None, None, None, None, True, 0.01, 0.02, 0.03),
        # CCC: libro con profundidad cero -> denominador cero, ratio None
        _hacer_observacion("CCC", "comparator", "observada", None, 1000, 900, 100, 50, 0, 0, True, 0.001, 0.002, 0.003),
    ]
    resultados = []
    for oid, por_h in {"AAA|1000": {"5m": 0.01, "15m": 0.02, "60m": 0.03},
                       "CCC|1000": {"5m": 0.001, "15m": 0.002, "60m": 0.003}}.items():
        for h, ret in por_h.items():
            resultados.append(_hacer_resultado(oid, h, ret))
    _escribir_jsonl(tmp_run["jsonl"], objetos + resultados)

    tablas = _ejecutar_cli(tmp_run)
    asoc = tablas["asociaciones_flujo_profundidad"]
    assert asoc["n_filas_totales"] == 6
    assert asoc["n_campos_ausentes_o_no_finitos"] == 3  # AAA 3 horizontes
    assert asoc["n_profundidad_cero_o_invalida"] == 3   # CCC 3 horizontes
    # AAA: flujo ausente -> ratio None. CCC: profundidad cero -> ratio None.
    # Ninguna produce parejas validas (requieren ratio y retorno no None).
    assert asoc["parejas_validas_por_horizonte"] == {"5m": 0, "15m": 0, "60m": 0}
    derivado = json.loads(tmp_run["derivado_json"].read_text(encoding="utf-8"))
    assert derivado["asociaciones"]["parejas_validas_por_horizonte"] == {"5m": 0, "15m": 0, "60m": 0}
    # nunca hay "168/168"
    texto = json.dumps(tablas, ensure_ascii=False)
    assert "168/168" not in texto


# -------------------- duplicados y resultados faltantes --------------------

def test_duplicados_y_faltantes(tmp_run):
    objetos = [
        _hacer_ciclo(900, 1000, ["AAA"], ["CCC"]),
        _hacer_observacion("AAA", "candidate", "observada", "UP", 1000, 900, 100, 50, 1000, 500, True, 0.01, 0.02, 0.03),
        _hacer_observacion("CCC", "comparator", "observada", None, 1000, 900, 150, 75, 900, 450, True, 0.001, 0.002, 0.003),
        # observacion duplicada (mismo observation_id) -> debe contarse una vez como seleccionada/emitida
        _hacer_observacion("AAA", "candidate", "observada", "UP", 1000, 900, 100, 50, 1000, 500, True, 0.01, 0.02, 0.03),
    ]
    resultados = [
        _hacer_resultado("AAA|1000", "5m", 0.01),
        _hacer_resultado("AAA|1000", "15m", 0.02),
        # 60m falta para AAA
        _hacer_resultado("CCC|1000", "5m", 0.001),
        _hacer_resultado("CCC|1000", "15m", 0.002),
        _hacer_resultado("CCC|1000", "60m", 0.003),
    ]
    _escribir_jsonl(tmp_run["jsonl"], objetos + resultados)

    tablas = _ejecutar_cli(tmp_run)
    rg = tablas["resumen_global"]
    assert rg["observaciones_total"] == 3  # se leen 3 filas de observacion
    # resultados totales: 5 (uno falta)
    assert rg["resultados_total"] == 5
    assert rg["resultados_por_horizonte"] == {"5m": 2, "15m": 2, "60m": 1}

    # cobertura por fila: AAA 60m faltante
    filas = { (f["decision_ms"], f["rol"]): f for f in tablas["embudo_desde_ciclos"]["filas_por_ciclo_rol"] }
    aaa = filas[(1000, "candidate")]
    assert aaa["seleccionados"] == 1
    assert aaa["observaciones_emitidas"] == 2  # dos filas con mismo id
    # cada fila duplicada genera su propio faltante en 60m
    assert aaa["cobertura_por_horizonte"]["60m"]["resultado_faltante"] == 2
    ccc = filas[(1000, "comparator")]
    assert ccc["cobertura_por_horizonte"]["60m"]["resultado_registrado"] == 1


# -------------------- seleccion sin observacion emitida --------------------

def test_seleccion_sin_observacion(tmp_run):
    # ciclo selecciona 2 candidatos pero solo se emite una observacion
    objetos = [
        _hacer_ciclo(900, 1000, ["AAA", "BBB"], ["CCC"]),
        _hacer_observacion("AAA", "candidate", "observada", "UP", 1000, 900, 100, 50, 1000, 500, True, 0.01, 0.02, 0.03),
        _hacer_observacion("CCC", "comparator", "observada", None, 1000, 900, 150, 75, 900, 450, True, 0.001, 0.002, 0.003),
        # BBB no tiene observacion emitida
    ]
    resultados = [
        _hacer_resultado("AAA|1000", "5m", 0.01),
        _hacer_resultado("CCC|1000", "5m", 0.001),
    ]
    _escribir_jsonl(tmp_run["jsonl"], objetos + resultados)

    tablas = _ejecutar_cli(tmp_run)
    rg = tablas["resumen_global"]
    assert rg["seleccionados_total"] == 3  # 2 cand + 1 comp
    assert rg["total_sin_observacion"] == 1  # BBB no emitido
    filas = { (f["decision_ms"], f["rol"]): f for f in tablas["embudo_desde_ciclos"]["filas_por_ciclo_rol"] }
    cand = filas[(1000, "candidate")]
    assert cand["seleccionados"] == 2
    assert cand["observaciones_emitidas"] == 1
    assert cand["seleccion_sin_observacion"] == 1


# -------------------- ponderaciones con ejemplo a mano --------------------

def test_ponderaciones_ejemplo_mano(tmp_run):
    """Ejemplo pequeno calculado a mano para validar ponderaciones.

    Cyclo 0: candidate A (5m=0.10), candidate B (5m=0.20); comparator C (5m=0.00).
    Cyclo 1: candidate D (5m=0.30); comparator E (5m=0.05), comparator F (5m=0.15).
    """
    objetos = [
        _hacer_ciclo(900, 1000, ["A", "B"], ["C"]),
        _hacer_ciclo(2000, 2100, ["D"], ["E", "F"]),
    ]
    observaciones = [
        _hacer_observacion("A", "candidate", "observada", "UP", 1000, 900, 100, 0, 1000, 500, True, 0.10, 0.0, 0.0),
        _hacer_observacion("B", "candidate", "observada", "UP", 1000, 900, 200, 0, 1000, 500, True, 0.20, 0.0, 0.0),
        _hacer_observacion("C", "comparator", "observada", None, 1000, 900, 0, 0, 1000, 500, True, 0.00, 0.0, 0.0),
        _hacer_observacion("D", "candidate", "observada", "UP", 2100, 2000, 300, 0, 1000, 500, True, 0.30, 0.0, 0.0),
        _hacer_observacion("E", "comparator", "observada", None, 2100, 2000, 0, 0, 1000, 500, True, 0.05, 0.0, 0.0),
        _hacer_observacion("F", "comparator", "observada", None, 2100, 2000, 0, 0, 1000, 500, True, 0.15, 0.0, 0.0),
    ]
    resultados = []
    datos = {"A|1000": {"5m": 0.10}, "B|1000": {"5m": 0.20}, "C|1000": {"5m": 0.00},
             "D|2100": {"5m": 0.30}, "E|2100": {"5m": 0.05}, "F|2100": {"5m": 0.15}}
    for oid, por_h in datos.items():
        for h, ret in por_h.items():
            resultados.append(_hacer_resultado(oid, h, ret))
    _escribir_jsonl(tmp_run["jsonl"], objetos + observaciones + resultados)

    tablas = _ejecutar_cli(tmp_run)
    comp = tablas["comparacion_candidatos_comparadores"]["5m"]
    # Medias agrupadas: cand = (0.10+0.20+0.30)/3 = 0.20; comp = (0.00+0.05+0.15)/3 = 0.0666...
    assert abs(comp["candidatos"]["media"] - 0.20) < 1e-12
    assert abs(comp["comparadores"]["media"] - (0.20 / 3)) < 1e-12
    assert abs(comp["diferencia_medias_agrupada"] - (0.20 - 0.20 / 3)) < 1e-12
    # Media de diferencias por ciclo:
    # ciclo 0: cand 0.15, comp 0.00 -> diff 0.15
    # ciclo 1: cand 0.30, comp 0.10 -> diff 0.20
    # media = (0.15 + 0.20) / 2 = 0.175
    assert abs(comp["media_de_diferencias_por_ciclo"] - 0.175) < 1e-12
    # Media por simbolo (igual peso): cand = (0.10+0.20+0.30)/3 = 0.20; comp = (0.00+0.05+0.15)/3 = 0.0666...
    assert abs(comp["diferencia_medias_agrupada_por_simbolo"] - (0.20 - 0.20 / 3)) < 1e-12
    # Las tres ponderaciones no son obligatoriamente iguales; aqui coinciden por construccion.
    # No se exige que sean diferentes (requisito del enunciado).


# -------------------- distinguir dataset externo vs portables --------------------

def test_no_asume_168_168_desde_derivados_propios(tmp_run):
    """El analizador no debe publicar "168/168" ni disponibilidad completa
    solo porque existan resultados forward. Usa datos del temporal."""
    objetos = [
        _hacer_ciclo(900, 1000, ["AAA"], ["CCC"]),
        _hacer_observacion("AAA", "candidate", "observada", "UP", 1000, 900, 100, 50, 1000, 500, True, 0.01, 0.02, 0.03),
        _hacer_observacion("CCC", "comparator", "observada", None, 1000, 900, 150, 75, 900, 450, True, 0.001, 0.002, 0.003),
    ]
    resultados = []
    for oid in ("AAA|1000", "CCC|1000"):
        for h in ("5m", "15m", "60m"):
            resultados.append(_hacer_resultado(oid, h, 0.01))
    _escribir_jsonl(tmp_run["jsonl"], objetos + resultados)

    tablas = _ejecutar_cli(tmp_run)
    asoc = tablas["asociaciones_flujo_profundidad"]
    assert asoc["n_filas_totales"] == 6
    assert asoc["parejas_validas_por_horizonte"] == {"5m": 2, "15m": 2, "60m": 2}
    texto = json.dumps(tablas, ensure_ascii=False)
    assert "168/168" not in texto
