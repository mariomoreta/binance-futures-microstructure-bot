"""Observabilidad del monitor del piloto: exposicion de estado ya existente.

El monitor del dashboard (frontend/src/lib/pilot-monitor.ts) lee artefactos
que el piloto ya escribe. Este archivo fija el contrato de esa exposicion:

1. El snapshot atomico (``--status-file``) publica identidad de corrida, fase,
   contadores autoritativos de presupuesto y almacenamiento y plazos maximos.
   Es EXPOSICION: no reserva, no consume, no decide.
2. La fila operativa persistida publica el stop de la regla congelada, que
   ya existia en el motor; no se recalcula ni se altera ninguna decision.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import research_pilot as rp  # noqa: E402
from scripts.research_operativo_adapter import (  # noqa: E402
    OperativoAdapter,
    OperativoConfig,
)
from microstructure_probe.paper_lab_engine import PaperCandle  # noqa: E402


def _leer_jsonl(path: Path):
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def test_snapshot_publica_identidad_presupuesto_y_plazos() -> None:
    """El snapshot atomico expone el estado existente (sin consumir nada)."""
    tmp = Path(tempfile.mkdtemp(prefix="monitor-estado-"))
    cfg = rp.PilotConfig(
        run_id="pilot-monitor-estado",
        out_dir=tmp,
        mode="local",
        status_file=str(tmp / "estado.json"),
        duration_seconds=3600.0,
        settle_seconds=4200.0,
        funding_wait_seconds=32400.0,
        max_http_attempts=2000,
        max_http_retries=50,
        max_http_weight=5000,
        max_bytes=128 * 1024 * 1024,
    )
    pilot = rp.ResearchPilot(cfg)
    try:
        # Contadores ya existentes en la puerta de presupuesto: el snapshot
        # los publica, no los modifica.
        pilot.budget.attempts = 7
        pilot.budget.retries = 2
        pilot.budget.weight = 120
        pilot._write_status()
        estado = json.loads((tmp / "estado.json").read_text(encoding="utf-8"))
    finally:
        pilot.store.close()
        pilot.operativo.close()

    assert estado["run_id"] == "pilot-monitor-estado"
    assert estado["mode"] == "local"
    assert estado["phase"] == "captura"
    assert estado["presupuesto"]["attempts"] == 7
    assert estado["presupuesto"]["retries"] == 2
    assert estado["presupuesto"]["weight"] == 120
    assert estado["presupuesto"]["max_attempts"] == 2000
    assert estado["presupuesto"]["max_retries"] == 50
    assert estado["presupuesto"]["max_weight"] == 5000
    assert estado["almacenamiento"]["max_bytes"] == 128 * 1024 * 1024
    assert estado["duracion_maxima_total_ms"] == (3600 + 4200 + 32400) * 1000
    assert estado["espera_contable_plazo_max_ms"] == 32400 * 1000
    # La exposicion no consume presupuesto ni altera la puerta.
    assert pilot.budget.attempts == 7
    assert pilot.budget.max_attempts == 2000


def test_fila_operativa_publica_el_stop_de_la_regla_congelada() -> None:
    """El stop persistido es el de la regla (0,5 %): exposicion, no calculo."""
    tmp = Path(tempfile.mkdtemp(prefix="monitor-stop-"))
    velas = [
        PaperCandle(0, 100.0, 101.0, 99.0, 100.0, 59_999),
        PaperCandle(60_000, 101.6, 103.0, 101.55, 102.0, 119_000),
        PaperCandle(120_000, 102.0, 103.0, 101.0, 102.5, 179_000),
        PaperCandle(180_000, 102.0, 103.0, 101.0, 102.5, 239_000),
    ]
    obs = {
        "observation_id": "MON|119000", "symbol": "MONUSDT",
        "role": "candidate", "decision_ms": 119_000,
        "seleccion": {"move_24h_pct": +2.4}, "side": "UP",
    }
    store = tmp / "resultado_operativo.jsonl"
    adapter = OperativoAdapter(store_path=store, cfg=OperativoConfig())
    try:
        trade = adapter.procesar_observacion(obs, velas)
        adapter.persistir(trade)
    finally:
        adapter.close()

    row = _leer_jsonl(store)[-1]
    assert trade.stop_px is not None
    assert row["stop_px"] == trade.stop_px
    # El stop sigue la regla congelada: 0,5 % por debajo del precio de senal.
    assert abs(row["stop_px"] - 102.0 * (1.0 - 0.005)) < 1e-9
    assert abs(row["entry_px"] - 102.0) < 1e-9
    assert row["decision"] == "ENTRADA_EJECUTADA"
