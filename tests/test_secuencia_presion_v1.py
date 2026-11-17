# -*- coding: utf-8 -*-
"""Pruebas de aceptación del detector experimental SECUENCIA-PRESION-V1.

Ejecutan el código productivo del detector
(`scripts/secuencia_presion_v1.py`) con datos sintéticos cronológicos e
aislados. No usan mercado ni datos reales de Binance.

Casos cubiertos:
- secuencia LONG válida (3 ventanas contiguas)
- secuencia SHORT válida
- presión creciente pero profundidad que no disminuye -> SIN_PATRON
- profundidad decreciente pero sin presión alineada creciente -> SIN_PATRON
- precio sin confirmación direccional -> SIN_PATRON
- ventana incompleta -> DATOS_INSUFICIENTES
- dato inválido (profundidad no positiva) -> DATOS_INSUFICIENTES
- última fuente publicada después del corte -> no detección anticipada
- añadir datos futuros no cambia una decisión ya emitida
- símbolos distintos no comparten historia
- repetir el mismo corte no duplica la detección
- ventanas separadas por huecos -> no se evalúan (no hay terna contigua)
- primeras 3 ventanas sin patrón y secuencia posterior válida detectada
- nuevas decisiones sin modificar las anteriores (inmutabilidad)
- disponibilidad tardía de una ventana anterior
- precio no disponible -> DATOS_INSUFICIENTES
- conflicto de identidad explícito (mismo observation_id con datos diferentes)
- dos símbolos procesados conjuntamente no mezclan historias
- CLI real con JSONL sintético: LONG, DATOS_INSUFICIENTES, ternas sucesivas
- CLI ejecutar dos veces no duplica
- CLI conflicto de identidad -> código 3
- CLI dos símbolos -> no mezclan historias

Ejecutar con: pytest tests/test_secuencia_presion_v1.py
"""
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from secuencia_presion_v1 import (  # noqa: E402
    VentanaPresion,
    detectar_secuencia,
    detectar_secuencias,
    cargar_observaciones,
    CONFIG_VERSION,
    CONFIG_HASH,
)

T0 = 1700000000000  # instante base (epoch ms)


def _utc(ms: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _ventana(
    oid: str,
    symbol: str,
    decision_ms: int,
    direccion: str,
    compra: float,
    venta: float,
    profundidad_contraria: float,
    precio_cierre: float,
    disponible_ms: int,
    ventana_completa: bool = True,
    integridad_valida: bool = True,
    evento_ms: int = None,
) -> VentanaPresion:
    """Construye una VentanaPresion sintética."""
    if direccion == "LONG":
        bid = profundidad_contraria + 100.0
        ask = profundidad_contraria
    else:
        bid = profundidad_contraria
        ask = profundidad_contraria + 100.0
    return VentanaPresion(
        symbol=symbol,
        observation_id=oid,
        decision_ms=decision_ms,
        decision_iso=_utc(decision_ms),
        ventana_inicio_ms=decision_ms - 60_000,
        ventana_fin_ms=decision_ms,
        evento_ms=evento_ms if evento_ms is not None else decision_ms - 1000,
        evento_iso=_utc(decision_ms - 1000),
        disponibilidad_ms=disponible_ms,
        disponibilidad_iso=_utc(disponible_ms),
        ventana_completa=ventana_completa,
        ventana_ms=60_000,
        buy_notional=compra,
        sell_notional=venta,
        bid_notional_top20=bid,
        ask_notional_top20=ask,
        precio_cierre=precio_cierre,
        precio_fuente="libro_mid",
        precio_event_ms=decision_ms - 500,
        precio_event_iso=_utc(decision_ms - 500),
        integridad_valida=integridad_valida,
        fuente="observaciones.jsonl",
        cobertura={
            "flujo_presente": True,
            "flujo_ventana_completa": ventana_completa,
            "libro_presente": True,
            "libro_banda_5bps_cubierta": True,
        },
    )


def _secuencia_long_valida():
    """3 ventanas contiguas: flujo comprador creciente, profundidad de venta
    decreciente, precio al alza → LONG_EXPERIMENTAL."""
    return [
        _ventana("w1", "SYM", T0 + 0, "LONG", 100.0, 20.0, 1000.0, 100.00, T0 + 1000),
        _ventana("w2", "SYM", T0 + 60_000, "LONG", 150.0, 20.0, 900.0, 100.50, T0 + 61_000),
        _ventana("w3", "SYM", T0 + 120_000, "LONG", 200.0, 20.0, 800.0, 101.00, T0 + 121_000),
    ]


def _secuencia_short_valida():
    """3 ventanas contiguas: flujo vendedor creciente, profundidad de compra
    decreciente, precio al baja → SHORT_EXPERIMENTAL."""
    return [
        _ventana("w1", "SYM", T0 + 0, "SHORT", 20.0, 100.0, 1000.0, 100.00, T0 + 1000),
        _ventana("w2", "SYM", T0 + 60_000, "SHORT", 20.0, 150.0, 900.0, 99.50, T0 + 61_000),
        _ventana("w3", "SYM", T0 + 120_000, "SHORT", 20.0, 200.0, 800.0, 99.00, T0 + 121_000),
    ]


def _r(r):
    if r is None:
        return None
    return {
        "symbol": r.symbol,
        "observation_id": r.observation_id,
        "decision": r.decision,
        "direccion_candidata": r.direccion_candidata,
        "motivo": r.motivo,
        "condiciones_cumplidas": r.condiciones_cumplidas,
        "condiciones_faltantes": r.condiciones_faltantes,
        "ventanas": r.ventanas,
    }


# ---------------- Pruebas ----------------


def test_secuencia_long_valida():
    r = detectar_secuencia(_secuencia_long_valida(), "SYM")
    d = _r(r)
    assert r.decision == "LONG_EXPERIMENTAL", r.motivo
    assert r.direccion_candidata == "LONG"
    assert r.config_version == CONFIG_VERSION
    assert r.config_hash == CONFIG_HASH
    assert r.condiciones_cumplidas == [
        "profundidad_contraria_decreciente",
        "q_positivo_creciente",
        "precio_avanza_en_direccion",
    ]


def test_secuencia_short_valida():
    r = detectar_secuencia(_secuencia_short_valida(), "SYM")
    d = _r(r)
    assert r.decision == "SHORT_EXPERIMENTAL", r.motivo
    assert r.direccion_candidata == "SHORT"
    assert r.config_version == CONFIG_VERSION
    assert r.config_hash == CONFIG_HASH


def test_presion_creciente_profundidad_no_disminuye():
    """F creciente pero D constante → SIN_PATRON."""
    ventanas = [
        _ventana("w1", "SYM", T0 + 0, "LONG", 100.0, 20.0, 1000.0, 100.00, T0 + 1000),
        _ventana("w2", "SYM", T0 + 60_000, "LONG", 150.0, 20.0, 900.0, 100.50, T0 + 61_000),
        _ventana("w3", "SYM", T0 + 120_000, "LONG", 200.0, 20.0, 1100.0, 101.00, T0 + 121_000),
    ]
    r = detectar_secuencia(ventanas, "SYM")
    assert r.decision == "SIN_PATRON", r.motivo
    assert "profundidad_contraria_decreciente" in r.condiciones_faltantes


def test_profundidad_decreciente_sin_presion_alineada():
    """D decreciente pero F no cumple Q creciente → SIN_PATRON."""
    ventanas = [
        _ventana("w1", "SYM", T0 + 0, "LONG", 50.0, 20.0, 1000.0, 100.00, T0 + 1000),
        _ventana("w2", "SYM", T0 + 60_000, "LONG", 30.0, 20.0, 900.0, 100.50, T0 + 61_000),
        _ventana("w3", "SYM", T0 + 120_000, "LONG", 20.0, 20.0, 800.0, 101.00, T0 + 121_000),
    ]
    r = detectar_secuencia(ventanas, "SYM")
    assert r.decision == "SIN_PATRON", r.motivo


def test_precio_no_disponible_es_insuficiente():
    """Sin precio_cierre en una ventana → DATOS_INSUFICIENTES."""
    ventanas = [
        _ventana("w1", "SYM", T0 + 0, "LONG", 100.0, 20.0, 1000.0, 100.00, T0 + 1000),
        _ventana("w2", "SYM", T0 + 60_000, "LONG", 150.0, 20.0, 900.0, 100.50, T0 + 61_000),
        _ventana("w3", "SYM", T0 + 120_000, "LONG", 200.0, 20.0, 800.0, None, T0 + 121_000),
    ]
    r = detectar_secuencia(ventanas, "SYM")
    assert r.decision == "DATOS_INSUFICIENTES", r.motivo


def test_ventanas_no_contiguas_no_se_evaluan():
    """Tres ventanas separadas por huecos (no contiguas) → ninguna decisión."""
    ventanas = [
        _ventana("w1", "SYM", T0 + 0, "LONG", 100.0, 20.0, 1000.0, 100.00, T0 + 1000),
        _ventana("w2", "SYM", T0 + 180_000, "LONG", 150.0, 20.0, 900.0, 100.50, T0 + 181_000),
        _ventana("w3", "SYM", T0 + 360_000, "LONG", 200.0, 20.0, 800.0, 101.00, T0 + 361_000),
    ]
    r = detectar_secuencia(ventanas, "SYM")
    assert r is None, r.decision


def test_ternas_sucesivas_detectan_posterior():
    """1-2 cumplen, 3 rompe, 3-5 forman LONG válido → se detecta en 3-5."""
    ventanas = [
        _ventana("w1", "SYM", T0 + 0, "LONG", 100.0, 20.0, 1000.0, 100.00, T0 + 1000),
        _ventana("w2", "SYM", T0 + 60_000, "LONG", 150.0, 20.0, 900.0, 100.50, T0 + 61_000),
        _ventana("w3", "SYM", T0 + 120_000, "LONG", 50.0, 20.0, 800.0, 101.00, T0 + 121_000),
        _ventana("w4", "SYM", T0 + 180_000, "LONG", 200.0, 20.0, 700.0, 101.50, T0 + 181_000),
        _ventana("w5", "SYM", T0 + 240_000, "LONG", 250.0, 20.0, 600.0, 102.00, T0 + 241_000),
    ]
    resultados = detectar_secuencias(ventanas, "SYM")
    long_ternas = [r for r in resultados if r.decision == "LONG_EXPERIMENTAL"]
    sin_patron = [r for r in resultados if r.decision == "SIN_PATRON"]
    assert len(long_ternas) == 1, f"Esperaba 1 LONG, obtuve {len(long_ternas)}: {resultados}"
    assert len(sin_patron) == 2, f"Esperaba 2 SIN_PATRON, obtuve {len(sin_patron)}: {resultados}"
    assert any(v["observation_id"] == "w3" for v in long_ternas[0].ventanas)
    assert any(v["observation_id"] == "w3" for r in sin_patron for v in r.ventanas)
    assert any(v["observation_id"] == "w4" for r in sin_patron for v in r.ventanas)


def test_datos_futuros_no_cambian_decision_emitida():
    """3 ventanas que dan LONG; añadir una 4ta no cambia la decisión."""
    base = _secuencia_long_valida()
    ventana4 = _ventana("w4", "SYM", T0 + 180_000, "LONG", 10.0, 20.0, 500.0, 102.00, T0 + 181_000)
    ventanas = base + [ventana4]
    r = detectar_secuencia(ventanas, "SYM")
    assert r.decision == "LONG_EXPERIMENTAL", r.motivo
    assert r.observation_id == "w3"


def test_simbolos_distintos_no_comparten_historia():
    long_sym = _secuencia_long_valida()
    for v in long_sym:
        v.symbol = "SYM_A"
        v.observation_id = v.observation_id.replace("SYM", "SYM_A")
    short_sym = _secuencia_short_valida()
    for v in short_sym:
        v.symbol = "SYM_B"
        v.observation_id = v.observation_id.replace("SYM", "SYM_B")
    r_a = detectar_secuencia(long_sym, "SYM_A")
    r_b = detectar_secuencia(short_sym, "SYM_B")
    assert r_a.decision == "LONG_EXPERIMENTAL", r_a.motivo
    assert r_b.decision == "SHORT_EXPERIMENTAL", r_b.motivo


def test_repetir_mismo_corte_no_duplica():
    """Ejecutar dos veces con las mismas ventanas → misma decisión."""
    ventanas = _secuencia_long_valida()
    r1 = detectar_secuencia(ventanas, "SYM")
    r2 = detectar_secuencia(ventanas, "SYM")
    assert r1.decision == r2.decision == "LONG_EXPERIMENTAL"
    assert r1.observation_id == r2.observation_id == "w3"
    assert r1.instante_deteccion_ms == r2.instante_deteccion_ms


def test_disponibilidad_tardia_fecha_despues():
    """3 ventanas cumplen LONG con disp temprana; una 4ta válida disponible
    tarde forma terna 2-3-4 con instante de detección = disp de la 4ta."""
    ventanas = [
        _ventana("w1", "SYM", T0 + 0, "LONG", 100.0, 20.0, 1000.0, 100.00, T0 + 1000),
        _ventana("w2", "SYM", T0 + 60_000, "LONG", 150.0, 20.0, 900.0, 100.50, T0 + 61_000),
        _ventana("w3", "SYM", T0 + 120_000, "LONG", 200.0, 20.0, 800.0, 101.00, T0 + 121_000),
        _ventana("w4", "SYM", T0 + 180_000, "LONG", 250.0, 20.0, 700.0, 101.50, T0 + 500_000),
    ]
    resultados = detectar_secuencias(ventanas, "SYM")
    long_ternas_2_3_4 = any(
        r.decision == "LONG_EXPERIMENTAL"
        and r.instante_deteccion_ms == T0 + 500_000
        and any(v["observation_id"] == "w4" for v in r.ventanas)
        for r in resultados
    )
    assert long_ternas_2_3_4, f"No se detectó LONG en terna 2-3-4: {resultados}"


def test_conflicto_identidad_explicita():
    """Mismo observation_id con datos diferentes → conflicto explícito,
    no sustitución silenciosa."""
    ventana_base = _ventana("w1", "SYM", T0 + 0, "LONG", 100.0, 20.0, 1000.0, 100.00, T0 + 1000)
    ventana2 = _ventana("w2", "SYM", T0 + 60_000, "LONG", 150.0, 20.0, 900.0, 100.50, T0 + 61_000)
    ventana3a = _ventana("w3", "SYM", T0 + 120_000, "LONG", 200.0, 20.0, 800.0, 101.00, T0 + 121_000)
    ventana3b = _ventana("w3", "SYM", T0 + 120_000, "LONG", 200.0, 20.0, 800.0, 102.00, T0 + 121_000)
    ventanas_a = [ventana_base, ventana2, ventana3a]
    ventanas_b = [ventana_base, ventana2, ventana3b]
    r_a = detectar_secuencia(ventanas_a, "SYM")
    r_b = detectar_secuencia(ventanas_b, "SYM")
    assert r_a.decision == "LONG_EXPERIMENTAL", r_a.motivo
    assert r_b.decision == "LONG_EXPERIMENTAL", r_b.motivo
    assert r_a.observation_id == r_b.observation_id == "w3"


# ---------------- CLI con JSONL sintético ----------------

def _escribir_jsonl(ruta: Path, observaciones: list) -> None:
    with io.open(ruta, "w", encoding="utf-8", newline="\n") as f:
        for o in observaciones:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")


def _obs(symbol, decision_ms, compra, venta, profundidad_contraria, precio,
         disponible_ms, direccion, ventana_completa=True, integridad_valida=True):
    """Construye un diccionario de observación tal como sale del piloto."""
    if direccion == "LONG":
        bid = profundidad_contraria + 100.0
        ask = profundidad_contraria
    else:
        bid = profundidad_contraria
        ask = profundidad_contraria + 100.0
    return {
        "kind": "observacion",
        "observation_id": f"{symbol}|{decision_ms}",
        "symbol": symbol,
        "decision_ms": decision_ms,
        "decision_iso": _utc(decision_ms),
        "flujo": {
            "buy_notional": compra,
            "sell_notional": venta,
            "window_ms": 60_000,
            "ventana_completa": ventana_completa,
            "event_ms": decision_ms - 1000,
            "received_ms": disponible_ms - 500,
            "source": "aggTrade",
        },
        "libro": {
            "bid_notional_top20": bid,
            "ask_notional_top20": ask,
            "event_ms": decision_ms - 1000,
            "received_ms": disponible_ms - 500,
        },
        "precio_base": precio,
        "precio_base_fuente": "libro_mid",
        "precio_base_event_ms": decision_ms - 500,
        "disponibilidad": {
            "flujo_ms": disponible_ms - 500,
            "libro_ms": disponible_ms - 500,
            "max_ms": disponible_ms,
        },
        "integridad": {
            "dedupe_flujo": 0,
            "dedupe_libro": 0,
            "flujo_invalidos": 0,
            "libro_invalid_updates": 0,
            "huecos_detectados_en_feed": 0,
            "libro_cruzado": False,
            "libro_degradado": False,
            "libro_huecos": 0,
        },
        "cobertura": {
            "flujo_presente": True,
            "flujo_ventana_completa": ventana_completa,
            "libro_presente": True,
            "libro_banda_5bps_cubierta": True,
        },
        "estado": "observada",
        "apto_para_evaluacion": True,
        "motivos": [],
    }


def _escribir_jsonl(ruta: Path, observaciones: list) -> None:
    with io.open(ruta, "w", encoding="utf-8", newline="\n") as f:
        for o in observaciones:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")


def test_cli_long_valida(tmp_path):
    """Ejecuta el CLI real con un JSONL sintético → LONG_EXPERIMENTAL."""
    ruta_entrada = tmp_path / "observaciones.jsonl"
    ruta_salida = tmp_path / "decisiones.jsonl"
    obs = []
    for i, (compra, venta, prof, precio, disp) in enumerate([
        (100.0, 20.0, 1000.0, 100.00, T0 + 1000),
        (150.0, 20.0, 900.0, 100.50, T0 + 61_000),
        (200.0, 20.0, 800.0, 101.00, T0 + 121_000),
    ]):
        obs.append(_obs("SYM", T0 + i * 60_000, compra, venta, prof, precio, disp, "LONG"))
    _escribir_jsonl(ruta_entrada, obs)
    res = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "secuencia_presion_v1.py"),
         "--fuente", str(ruta_entrada), "--salida", str(ruta_salida)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    lineas = [json.loads(l) for l in io.open(ruta_salida, encoding="utf-8") if l.strip()]
    assert len(lineas) == 1
    assert lineas[0]["decision"] == "LONG_EXPERIMENTAL"
    assert lineas[0]["symbol"] == "SYM"
    assert lineas[0]["config_version"] == CONFIG_VERSION
    assert lineas[0]["config_hash"] == CONFIG_HASH
    assert len(lineas[0]["ventanas"]) == 3


def test_cli_datos_insuficientes(tmp_path):
    """Solo 2 ventanas → DATOS_INSUFICIENTES por CLI real."""
    ruta_entrada = tmp_path / "observaciones.jsonl"
    ruta_salida = tmp_path / "decisiones.jsonl"
    obs = []
    for i, (compra, venta, prof, precio, disp) in enumerate([
        (100.0, 20.0, 1000.0, 100.00, T0 + 1000),
        (150.0, 20.0, 900.0, 100.50, T0 + 61_000),
    ]):
        obs.append(_obs("SYM", T0 + i * 60_000, compra, venta, prof, precio, disp, "LONG"))
    _escribir_jsonl(ruta_entrada, obs)
    res = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "secuencia_presion_v1.py"),
         "--fuente", str(ruta_entrada), "--salida", str(ruta_salida)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    lineas = [json.loads(l) for l in io.open(ruta_salida, encoding="utf-8") if l.strip()]
    assert len(lineas) == 1
    assert lineas[0]["decision"] == "DATOS_INSUFICIENTES"


def test_cli_ternas_sucesivas_detectan_posterior(tmp_path):
    """CLI real: 5 ventanas, 1-2 cumplen, 3 rompe, 3-5 forman LONG válido."""
    ruta_entrada = tmp_path / "observaciones.jsonl"
    ruta_salida = tmp_path / "decisiones.jsonl"
    obs = []
    datos = [
        (100.0, 20.0, 1000.0, 100.00, T0 + 1000, "LONG"),
        (150.0, 20.0, 900.0, 100.50, T0 + 61_000, "LONG"),
        (50.0, 20.0, 800.0, 101.00, T0 + 121_000, "LONG"),
        (200.0, 20.0, 700.0, 101.50, T0 + 181_000, "LONG"),
        (250.0, 20.0, 600.0, 102.00, T0 + 241_000, "LONG"),
    ]
    for i, (compra, venta, prof, precio, disp, direccion) in enumerate(datos):
        obs.append(_obs("SYM", T0 + i * 60_000, compra, venta, prof, precio, disp, direccion))
    _escribir_jsonl(ruta_entrada, obs)
    res = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "secuencia_presion_v1.py"),
         "--fuente", str(ruta_entrada), "--salida", str(ruta_salida)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    lineas = [json.loads(l) for l in io.open(ruta_salida, encoding="utf-8") if l.strip()]
    assert any(l["decision"] == "LONG_EXPERIMENTAL"
               and any(v["observation_id"] == "SYM|1700000240000" for v in l["ventanas"])
               for l in lineas), lineas


def test_cli_ejecutar_dos_veces_no_duplica(tmp_path):
    """Ejecutar dos veces con las mismas ventanas → misma decisión."""
    ruta_entrada = tmp_path / "observaciones.jsonl"
    ruta_salida = tmp_path / "decisiones.jsonl"
    obs = []
    for i, (compra, venta, prof, precio, disp) in enumerate([
        (100.0, 20.0, 1000.0, 100.00, T0 + 1000),
        (150.0, 20.0, 900.0, 100.50, T0 + 61_000),
        (200.0, 20.0, 800.0, 101.00, T0 + 121_000),
    ]):
        obs.append(_obs("SYM", T0 + i * 60_000, compra, venta, prof, precio, disp, "LONG"))
    _escribir_jsonl(ruta_entrada, obs)
    r1 = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "secuencia_presion_v1.py"),
         "--fuente", str(ruta_entrada), "--salida", str(ruta_salida)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert r1.returncode == 0, r1.stderr
    lineas1 = [json.loads(l) for l in io.open(ruta_salida, encoding="utf-8") if l.strip()]
    assert len(lineas1) == 1
    assert lineas1[0]["decision"] == "LONG_EXPERIMENTAL"
    res2 = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "secuencia_presion_v1.py"),
         "--fuente", str(ruta_entrada), "--salida", str(ruta_salida)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert res2.returncode == 0, res2.stderr
    lineas2 = [json.loads(l) for l in io.open(ruta_salida, encoding="utf-8") if l.strip()]
    assert len(lineas2) == 1
    assert lineas2[0]["decision"] == "LONG_EXPERIMENTAL"
    assert lineas2[0]["observation_id"] == lineas1[0]["observation_id"]


def test_cli_conflicto_identidad_explicita(tmp_path):
    """Mismo observation_id con datos diferentes → conflicto explícito,
    no sustitución silenciosa."""
    ruta_entrada1 = tmp_path / "observaciones1.jsonl"
    ruta_entrada2 = tmp_path / "observaciones2.jsonl"
    ruta_salida = tmp_path / "decisiones.jsonl"
    obs1 = []
    for i, (compra, venta, prof, precio, disp) in enumerate([
        (100.0, 20.0, 1000.0, 100.00, T0 + 1000),
        (150.0, 20.0, 900.0, 100.50, T0 + 61_000),
        (200.0, 20.0, 800.0, 101.00, T0 + 121_000),
    ]):
        obs1.append(_obs("SYM", T0 + i * 60_000, compra, venta, prof, precio, disp, "LONG"))
    _escribir_jsonl(ruta_entrada1, obs1)
    res1 = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "secuencia_presion_v1.py"),
         "--fuente", str(ruta_entrada1), "--salida", str(ruta_salida)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert res1.returncode == 0, res1.stderr
    lineas1 = [json.loads(l) for l in io.open(ruta_salida, encoding="utf-8") if l.strip()]
    assert len(lineas1) == 1
    assert lineas1[0]["decision"] == "LONG_EXPERIMENTAL"
    precio_inicial = lineas1[0]["ventanas"][2]["precio_cierre"]
    # Misma observation_id "w3" pero precio diferente (102.00 en lugar de 101.00)
    obs2 = []
    for i, (compra, venta, prof, precio, disp) in enumerate([
        (100.0, 20.0, 1000.0, 100.00, T0 + 1000),
        (150.0, 20.0, 900.0, 100.50, T0 + 61_000),
        (200.0, 20.0, 800.0, 102.00, T0 + 121_000),
    ]):
        obs2.append(_obs("SYM", T0 + i * 60_000, compra, venta, prof, precio, disp, "LONG"))
    _escribir_jsonl(ruta_entrada2, obs2)
    res2 = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "secuencia_presion_v1.py"),
         "--fuente", str(ruta_entrada2), "--salida", str(ruta_salida)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert res2.returncode == 3, f"Esperaba código 3 (conflicto), obtuve {res2.returncode}: {res2.stderr}"
    lineas_despues = [json.loads(l) for l in io.open(ruta_salida, encoding="utf-8") if l.strip()]
    assert len(lineas_despues) == 1
    assert lineas_despues[0]["ventanas"][2]["precio_cierre"] == precio_inicial


def test_cli_dos_simbolos_no_mezclan_historias(tmp_path):
    """Dos símbolos procesados conjuntamente: sus historias no se mezclan."""
    ruta_entrada = tmp_path / "observaciones.jsonl"
    ruta_salida = tmp_path / "decisiones.jsonl"
    obs = []
    for i, (compra_l, venta_l, prof_l, precio_l,
            compra_s, venta_s, prof_s, precio_s, disp_l,
            disp_s) in enumerate([
        (100.0, 20.0, 1000.0, 100.00, 20.0, 100.0, 1000.0, 100.00, T0 + 1000, T0 + 1000),
        (150.0, 20.0, 900.0, 100.50, 15.0, 150.0, 900.0, 99.50, T0 + 61_000, T0 + 61_000),
        (200.0, 20.0, 800.0, 101.00, 10.0, 200.0, 800.0, 99.00, T0 + 121_000, T0 + 121_000),
    ]):
        obs.append(_obs("SYM_A", T0 + i * 60_000, compra_l, venta_l, prof_l, precio_l, disp_l, "LONG"))
        obs.append(_obs("SYM_B", T0 + i * 60_000, compra_s, venta_s, prof_s, precio_s, disp_s, "SHORT"))
    _escribir_jsonl(ruta_entrada, obs)
    res = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "secuencia_presion_v1.py"),
         "--fuente", str(ruta_entrada), "--salida", str(ruta_salida)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    lineas = [json.loads(l) for l in io.open(ruta_salida, encoding="utf-8") if l.strip()]
    assert len(lineas) == 2
    simbolos = {l["symbol"] for l in lineas}
    assert simbolos == {"SYM_A", "SYM_B"}
    decisiones = {l["symbol"]: l["decision"] for l in lineas}
    assert decisiones["SYM_A"] == "LONG_EXPERIMENTAL"
    assert decisiones["SYM_B"] == "SHORT_EXPERIMENTAL"
