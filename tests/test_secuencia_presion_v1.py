# -*- coding: utf-8 -*-
"""Pruebas de aceptación del detector experimental SECUENCIA-PRESION-V1.

Ejecutan el código productivo del detector
(`scripts/secuencia_presion_v1.py`) con datos sintéticos cronológicos e
aislados. No usan mercado ni datos reales de Binance.

Casos indispensables:
- secuencia LONG válida;
- secuencia SHORT válida;
- presión creciente pero profundidad que no disminuye → SIN_PATRON;
- profundidad decreciente pero sin presión alineada creciente → SIN_PATRON;
- precio sin confirmación direccional → SIN_PATRON;
- ventana incompleta, hueco o dato inválido → DATOS_INSUFICIENTES;
- última fuente publicada después del corte → no detección anticipada;
- añadir datos futuros no cambia una decisión ya emitida;
- símbolos distintos no comparten historia;
- repetir el mismo corte no duplica la detección.
"""
import io
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from secuencia_presion_v1 import (  # noqa: E402
    VentanaPresion,
    detectar_secuencia,
    detectar_en_observaciones,
    cargar_observaciones,
    CONFIG_VERSION,
    CONFIG_HASH,
)

T0 = 1700000000000  # instante base (epoch ms)


def _utc(ms: int) -> str:
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
    evento_ms: Optional[int] = None,
) -> VentanaPresion:
    """Construye una VentanaPresion sintética."""
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
        disponibilidad_iso=_utc(disponible_ms) if disponible_ms is not None else None,
        ventana_completa=ventana_completa,
        ventana_ms=60_000,
        buy_notional=compra if compra >= 0 else 0.0,
        sell_notional=venta if venta >= 0 else 0.0,
        bid_notional_top20=profundidad_contraria
        if direccion == "SHORT"
        else profundidad_contraria + 100.0,
        ask_notional_top20=profundidad_contraria
        if direccion == "LONG"
        else profundidad_contraria + 100.0,
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


def _secuencia_long_valida() -> list[VentanaPresion]:
    """3 ventanas: flujo comprador creciente, profundidad de venta
    decreciente, precio al alza → LONG_EXPERIMENTAL."""
    return [
        _ventana("w1", "SYM", T0 + 0, "LONG", 100.0, 20.0, 1000.0, 100.00, T0 + 1000),
        _ventana("w2", "SYM", T0 + 60_000, "LONG", 150.0, 20.0, 900.0, 100.50, T0 + 61_000),
        _ventana("w3", "SYM", T0 + 120_000, "LONG", 200.0, 20.0, 800.0, 101.00, T0 + 121_000),
    ]


def _secuencia_short_valida() -> list[VentanaPresion]:
    """3 ventanas: flujo vendedor creciente (F negativo), profundidad de
    compra decreciente, precio al baja → SHORT_EXPERIMENTAL."""
    return [
        _ventana("w1", "SYM", T0 + 0, "SHORT", 20.0, 100.0, 1000.0, 100.00, T0 + 1000),
        _ventana("w2", "SYM", T0 + 60_000, "SHORT", 20.0, 150.0, 900.0, 99.50, T0 + 61_000),
        _ventana("w3", "SYM", T0 + 120_000, "SHORT", 20.0, 200.0, 800.0, 99.00, T0 + 121_000),
    ]


def _result(r):
    return {
        "symbol": r.symbol,
        "observation_id": r.observation_id,
        "decision": r.decision,
        "direccion_candidata": r.direccion_candidata,
        "motivo": r.motivo,
        "condiciones_cumplidas": r.condiciones_cumplidas,
        "condiciones_faltantes": r.condiciones_faltantes,
        "config_version": r.config_version,
        "config_hash": r.config_hash,
    }


# ---------------------------------------------------------------------------
# Casos indispensables
# ---------------------------------------------------------------------------


def test_secuencia_long_valida():
    ventanas = _secuencia_long_valida()
    r = detectar_secuencia(ventanas, "SYM")
    d = _result(r)
    assert r.decision == "LONG_EXPERIMENTAL", r.motivo
    assert r.direccion_candidata == "LONG"
    assert r.config_version == CONFIG_VERSION
    assert r.config_hash == CONFIG_HASH
    # Q: 0.1 < 0.166... < 0.25 ; D: 1000 > 900 > 800 ; precio: 100 < 100.5 < 101
    assert r.condiciones_cumplidas == [
        "profundidad_contraria_decreciente",
        "q_positivo_creciente",
        "precio_avanza_en_direccion",
    ]


def test_secuencia_short_valida():
    ventanas = _secuencia_short_valida()
    r = detectar_secuencia(ventanas, "SYM")
    d = _result(r)
    assert r.decision == "SHORT_EXPERIMENTAL", r.motivo
    assert r.direccion_candidata == "SHORT"
    assert r.config_version == CONFIG_VERSION
    assert r.config_hash == CONFIG_HASH


def test_presion_creciente_profundidad_no_disminuye():
    """F creciente pero D constante → SIN_PATRON."""
    ventanas = [
        _ventana("w1", "SYM", T0 + 0, "LONG", 100.0, 20.0, 1000.0, 100.00, T0 + 1000),
        _ventana("w2", "SYM", T0 + 60_000, "LONG", 150.0, 20.0, 1000.0, 100.50, T0 + 61_000),
        _ventana("w3", "SYM", T0 + 120_000, "LONG", 200.0, 20.0, 1000.0, 101.00, T0 + 121_000),
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


def test_precio_sin_confirmacion_direccional():
    """Q cumple pero el precio no avanza en dirección LONG → SIN_PATRON."""
    ventanas = [
        _ventana("w1", "SYM", T0 + 0, "LONG", 100.0, 20.0, 1000.0, 100.00, T0 + 1000),
        _ventana("w2", "SYM", T0 + 60_000, "LONG", 150.0, 20.0, 900.0, 99.50, T0 + 61_000),
        _ventana("w3", "SYM", T0 + 120_000, "LONG", 200.0, 20.0, 800.0, 99.00, T0 + 121_000),
    ]
    r = detectar_secuencia(ventanas, "SYM")
    assert r.decision == "SIN_PATRON", r.motivo
    assert "precio_avanza_en_direccion_long" in r.condiciones_faltantes


def test_ventana_incompleta():
    """Una ventana con ventana_completa=False → DATOS_INSUFICIENTES."""
    ventanas = [
        _ventana("w1", "SYM", T0 + 0, "LONG", 100.0, 20.0, 1000.0, 100.00, T0 + 1000),
        _ventana("w2", "SYM", T0 + 60_000, "LONG", 150.0, 20.0, 900.0, 100.50, T0 + 61_000,
                 ventana_completa=False),
        _ventana("w3", "SYM", T0 + 120_000, "LONG", 200.0, 20.0, 800.0, 101.00, T0 + 121_000),
    ]
    r = detectar_secuencia(ventanas, "SYM")
    assert r.decision == "DATOS_INSUFICIENTES", r.motivo


def test_dato_invalido_profundidad_no_positiva():
    """D <= 0 → ventana no válida → DATOS_INSUFICIENTES."""
    ventanas = [
        _ventana("w1", "SYM", T0 + 0, "LONG", 100.0, 20.0, 1000.0, 100.00, T0 + 1000),
        _ventana("w2", "SYM", T0 + 60_000, "LONG", 150.0, 20.0, 0.0, 100.50, T0 + 61_000),
        _ventana("w3", "SYM", T0 + 120_000, "LONG", 200.0, 20.0, 800.0, 101.00, T0 + 121_000),
    ]
    r = detectar_secuencia(ventanas, "SYM")
    assert r.decision == "DATOS_INSUFICIENTES", r.motivo


def test_ultima_fuente_despues_del_corte_no_detecion_anticipada():
    """Solo 2 ventanas válidas (la 3ra tiene disponibilidad futura/None) →
    DATOS_INSUFICIENTES, no se emite detección anticipada."""
    ventanas = [
        _ventana("w1", "SYM", T0 + 0, "LONG", 100.0, 20.0, 1000.0, 100.00, T0 + 1000),
        _ventana("w2", "SYM", T0 + 60_000, "LONG", 150.0, 20.0, 900.0, 100.50, T0 + 61_000),
        _ventana("w3", "SYM", T0 + 120_000, "LONG", 200.0, 20.0, 800.0, 101.00,
                 disponible_ms=None),  # no disponible aún
    ]
    r = detectar_secuencia(ventanas, "SYM")
    assert r.decision == "DATOS_INSUFICIENTES", r.motivo


def test_anadir_datos_futuros_no_cambia_decision():
    """3 ventanas que dan LONG; añadir una 4ta con datos futuros no cambia
    la decisión (se mantiene basada en las primeras 3)."""
    base = _secuencia_long_valida()
    ventana4 = _ventana("w4", "SYM", T0 + 180_000, "LONG", 10.0, 20.0, 500.0, 102.00,
                        T0 + 181_000)
    ventanas = base + [ventana4]
    r = detectar_secuencia(ventanas, "SYM")
    assert r.decision == "LONG_EXPERIMENTAL", r.motivo
    assert r.observation_id == "w3"  # basada en la 3ra ventana, no en la 4ta


def test_simbolos_distintos_no_comparten_historia():
    """Dos símbolos con sus propias 3 ventanas; cada uno evalúa de forma
    independiente."""
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


# ---------------------------------------------------------------------------
# Ejecución real del CLI con archivo JSONL sintético
# ---------------------------------------------------------------------------


def _escribir_jsonl(ruta: Path, observaciones: list[dict]) -> None:
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
