"""Regresiones del VEREDICTO del arn�s de ventana de ingeniería.

Defecto comprobado en ``eng-run-public-20261102c``: el arnés declaró PASS
interno con sesión creada y revisiones presentes, aunque la sesión no procesó
ningún evento y no ejecutó ninguna evaluación (decisión ``null``, contador
congelado por el defecto de ``events_processed`` del transporte
``market_stream``). Criterio de aceptación fijo:

  * sesión creada o revisiones presentes NO bastan;
  * cero cierres nuevos admitidos o cero evaluaciones ejecutadas impiden PASS;
  * la evaluación exigida debe estar vinculada a evento disparador, T,
    config_hash, decisión y motivo;
  * SIN_ENTRADA explícito con motivo sigue siendo válida (PASS).

Sin Binance, sin ventana pública, sin red: se invoca ``_verdict`` del arnés
real con evidencia preparada en memoria (sin cálculo de ledger: run_id
None). """
from __future__ import annotations

import argparse
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
_SCRIPTS_DIR = ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import engineering_live_window as elw  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _orchestrator(tmp: Path) -> Any:
    a = argparse.Namespace()
    a.transport = "local"
    a.execute = False
    a.service_port = _free_port()
    a.engineering_port = _free_port()
    a.provider_port = 0
    a.ws_port = _free_port()
    a.dashboard = "http://127.0.0.1:3020"
    a.build_id = "verdict-test-build"
    a.symbols = "MINAUSDT,BTCUSDT"
    a.interval = "1m"
    a.bars = 300
    a.duration = 60.0
    a.deadline = 60.0
    a.sessions_dir = str(tmp / "sessions")
    a.clock_source = None
    a.clock_readiness_timeout_s = None
    a.run_id = None  # sin presupuesto/ledger en este test
    a.rest_base_url = None
    return elw.WindowOrchestrator(a)


def _revision(n: int, decision: Optional[str] = None,
              reason: Optional[str] = None,
              clock_ms: int = 1793669219999,
              eventos: int = 0) -> Dict[str, Any]:
    return {"revision": n, "at_ms": 1793669229184, "estado": "sin_iniciar",
            "decision": decision, "decision_reason": reason,
            "clock_ms": clock_ms, "eventos_procesados": eventos}


def _eval(num: int, *, decision: str = "SIN_ENTRADA",
          reason: str = "sin cruz de umbral con datos cerrados",
          config_hash: str = "4a339c046cc3ad63",
          evento: Optional[Dict[str, Any]] = None,
          t_ms: Optional[int] = 1793669280000,
          rule_version: str = "RULE-CAUSAL-V1") -> Dict[str, Any]:
    return {
        "evaluacion_num": num,
        "config_hash": config_hash,
        "evento_disparador": evento if evento is not None else {
            "frame": "closed", "open_time_ms": 1793669280000,
            "close_time_ms": 1793669339999, "received_at_ms": 1793669342018},
        "T": t_ms,
        "config": {"rule_version": rule_version,
                   "hypothesis_id": "H", "hypothesis_version": "v1",
                   "symbol": "MINAUSDT", "interval": "1m",
                   "notional_usdt": 1000.0},
        "resultado": {"decision": decision, "decision_reason": reason,
                      "abstencion_sin_entrada": decision == "SIN_ENTRADA"}
    }


class _Base:
    @staticmethod
    def _with_evidence(tmp: Path, evidence: Dict[str, Any],
                       **attr: Any) -> Any:
        orch = _orchestrator(tmp)
        # El veredicto computa duración si no hay evidencia de adquisición.
        evidence.setdefault("duracion_adquisicion_s", 42.5)
        orch.evidence = evidence
        for k, v in attr.items():
            setattr(orch, k, v)
        if "config_hash" not in attr:
            orch.config_hash = (evidence.get("create") or {}).get(
                "config_hash")
        return orch

    @staticmethod
    def _crea() -> Dict[str, Any]:
        return {"session_id": "PL-MINAUSDT-LONG-1793669229096-9d935300",
                "config_hash": "4a339c046cc3ad63"}


def test_forma_observada_20261102c_es_fail():
    """La forma EXACTA observada (sesión creada, revisiones presentes,
    decisión null, contador cero, sin evidencia de cierres ni
    evaluaciones) es NO PASS (FAIL), no PASS."""
    with tempfile.TemporaryDirectory() as raw:
        evidence = {
            "create": _Base._crea(),
            "revisiones": [_revision(0), _revision(2)],
            "revision_final": 2,
            "eventos_procesados_final": 0,
            "cierres_admitidos_final": 0,
            "evaluaciones_final": [],
            "evaluacion_contador_final": 0,
        }
        orch = _Base._with_evidence(Path(raw), evidence)
        orch._verdict()
        assert orch.verdict == "FAIL", orch.verdict
        fail = orch.evidence["verdict_reasons"]["fail"]
        assert "sin_cierre_nuevo_admitido" in fail, fail
        assert "sin_evaluacion_ejecutada" in fail, fail


def test_revisiones_solo_no_bastan_incluso_con_cierre():
    """Sesión creada + revisiones + UN cierre admitido pero cero
    evaluaciones = FAIL (la ventana 20261102c con el contador corregido
    habría revelado esto)."""
    with tempfile.TemporaryDirectory() as raw:
        evidence = {
            "create": _Base._crea(),
            "revisiones": [_revision(0), _revision(
                2, clock_ms=1793669280000, eventos=3)],
            "revision_final": 2,
            "eventos_procesados_final": 3,
            "cierres_admitidos_final": 1,
            "evaluaciones_final": [],
            "evaluacion_contador_final": 0,
        }
        orch = _Base._with_evidence(Path(raw), evidence)
        orch._verdict()
        assert orch.verdict == "FAIL", orch.verdict
        fail = orch.evidence["verdict_reasons"]["fail"]
        assert "sin_evaluacion_ejecutada" in fail, fail
        assert "sin_cierre_nuevo_admitido" not in fail, fail


def test_sin_entrada_explicita_con_motivo_es_valida():
    """Cierre nuevo admitido + evaluación SIN_ENTRADA con motivo vinculada
    a evento/T/config_hash = PASS (SIN_ENTRADA sigue acreditando)."""
    with tempfile.TemporaryDirectory() as raw:
        evidence = {
            "create": _Base._crea(),
            "revisiones": [_revision(0), _revision(
                2, decision="SIN_ENTRADA",
                reason="sin cruce de umbral con datos cerrados",
                clock_ms=1793669280000, eventos=3)],
            "revision_final": 2,
            "eventos_procesados_final": 3,
            "cierres_admitidos_final": 1,
            "evaluaciones_final": [_eval(1)],
            "evaluacion_contador_final": 1,
        }
        orch = _Base._with_evidence(Path(raw), evidence)
        orch._verdict()
        assert orch.verdict == "PASS", orch.evidence["verdict_reasons"]
        vinc = orch.evidence["evaluacion_vinculada"]
        assert vinc["abstencion_sin_entrada_valida"] is True
        assert vinc["decision"] == "SIN_ENTRADA"
        assert vinc["motivo"]


def test_evaluacion_sin_vinculo_es_fail():
    """Evaluación sin evento/T/motivo (contador > 0 pero entrada sin
    vínculo completo) = FAIL."""
    with tempfile.TemporaryDirectory() as raw:
        evidence = {
            "create": _Base._crea(),
            "revisiones": [_revision(0), _revision(1, eventos=1)],
            "revision_final": 1,
            "eventos_procesados_final": 1,
            "cierres_admitidos_final": 1,
            "evaluaciones_final": [_eval(1, decision="SIN_ENTRADA",
                                         reason=None)],
            "evaluacion_contador_final": 1,
        }
        orch = _Base._with_evidence(Path(raw), evidence)
        orch._verdict()
        assert orch.verdict == "FAIL", orch.verdict
        fail = orch.evidence["verdict_reasons"]["fail"]
        assert "evaluacion_sin_vinculo_completo" in fail, fail


def test_evaluacion_config_hash_distinta_es_fail():
    """Evaluación cuyo config_hash no coincide con la sesión creada =
    FAIL (sin vínculo de identidad)."""
    with tempfile.TemporaryDirectory() as raw:
        evidence = {
            "create": _Base._crea(),
            "revisiones": [_revision(0), _revision(1, eventos=1)],
            "revision_final": 1,
            "eventos_procesados_final": 1,
            "cierres_admitidos_final": 1,
            "evaluaciones_final": [_eval(1, config_hash="otro-hash")],
            "evaluacion_contador_final": 1,
        }
        orch = _Base._with_evidence(Path(raw), evidence)
        orch._verdict()
        assert orch.verdict == "FAIL", orch.verdict
        fail = orch.evidence["verdict_reasons"]["fail"]
        assert "evaluacion_config_hash_distinta" in fail, fail


def test_sin_revisiones_sigue_siendo_unknown():
    """Sin revisiones ni evaluaciones (sesión no arrancada): UNKNOWN,
    no PASS (el arnés no debe disfrazar silencio de éxito)."""
    with tempfile.TemporaryDirectory() as raw:
        evidence = {
            "create": _Base._crea(),
            "revisiones": [],
            "revision_final": None,
            "eventos_procesados_final": 0,
            "cierres_admitidos_final": 0,
            "evaluaciones_final": [],
            "evaluacion_contador_final": 0,
        }
        orch = _Base._with_evidence(Path(raw), evidence)
        orch._verdict()
        assert orch.verdict == "UNKNOWN", orch.verdict
        missing = orch.evidence["verdict_reasons"]["missing"]
        assert "sin_evaluaciones_registradas" in missing, missing


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"--- {name}")
            try:
                fn()
                print("OK")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                import traceback
                traceback.print_exc()
                print(f"FALLO: {exc}")
    print("RESUMEN:", "TODO OK" if failures == 0 else f"{failures} fallos")
    raise SystemExit(1 if failures else 0)
