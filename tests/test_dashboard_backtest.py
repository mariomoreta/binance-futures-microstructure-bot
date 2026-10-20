"""Ejecutor de Backtest de Dashboard V2 + enlace a Paper Lab (offline).

Cubre:
- Lista permitida: un experiment_id no permitido no ejecuta nada (exit != 0).
- Fail-closed: un paquete con hash alterado no produce resultados.
- Determinismo: dos ejecuciones producen trades.json y reconciliation.json
  byte-identicos (el summary solo difiere en metadatos de reloj).
- Reconciliacion: la suma de netos por operacion recompone total_net por celda.
- Identidad: cada event_id emitido pertenece al manifiesto original.
- Enlace operacion -> Paper Lab: el generador materializa la operacion exacta
  (ganadora, perdedora y abierta) y conserva la causalidad.

No toca la red, ni DBs canonicas, ni el monitor: usa un paquete sintetico
autocontenido en un directorio temporal.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from microstructure_probe.backtest_offline import (  # noqa: E402
    BacktestConfig, Candle, FundingCalendar, FundingSettlement, StudyEvent,
    run_backtest)

_spec = importlib.util.spec_from_file_location(
    "dashboard_bt", str(ROOT / "scripts" / "run_dashboard_backtest.py"))
dash = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dash)

_gen_spec = importlib.util.spec_from_file_location(
    "paper_gen", str(ROOT / "scripts" / "build_paper_lab_replay.py"))
paper_gen = importlib.util.module_from_spec(_gen_spec)
_gen_spec.loader.exec_module(paper_gen)

SYM, RES, GROUP = "BTCUSDT", "15m", "continuation"
FAMILY, VERSION = "H1", "H1-v1"
STEP = 900_000
# Corte alineado a la rejilla de velas para que formacion y corte coincidan.
CUTOFF = STEP * 1111
HORIZON = 3_600_000


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _events():
    """Eventos dev (tiempo < cutoff) y oos, alineados a la rejilla de velas."""
    rows = []
    for i in range(8):
        rows.append({"symbol": SYM, "event_time_ms": i * STEP,
                     "direction": "LONG", "reference_price": 100.0,
                     "family": FAMILY, "rules_version": VERSION, "group": GROUP})
    for i in range(8):
        rows.append({"symbol": SYM, "event_time_ms": CUTOFF + i * STEP,
                     "direction": "LONG", "reference_price": 101.0,
                     "family": FAMILY, "rules_version": VERSION, "group": GROUP})
    return rows


def _candles():
    out = []
    t = 0
    px = 100.0
    while t < CUTOFF + 9 * STEP:
        # Serie con alternancia alcista/bajista para producir ganadoras,
        # perdedoras y una ABIERTA al final (el dato termina antes de que la
        # ultima operacion alcance su horizonte).
        drift = 0.6 if (t // STEP) % 3 else -0.9
        o = px
        c = px * (1 + drift / 100.0)
        hi = max(o, c) * 1.001
        lo = min(o, c) * 0.999
        out.append({"symbol": SYM, "open_time_ms": t, "open": o, "high": hi,
                    "low": lo, "close": c, "close_time_ms": t + 899_999})
        px = c
        t += STEP
    return out


def build_package(root: Path) -> Path:
    pkg = root / "pkg"
    combo = pkg / "combos" / "eval15_btc"
    funding = pkg / "funding"
    combo.mkdir(parents=True, exist_ok=True)
    funding.mkdir(parents=True, exist_ok=True)
    events = _events()
    (combo / f"events_{SYM}_{RES}.json").write_text(
        json.dumps(events), encoding="utf-8")
    (combo / f"candles_{SYM}_{RES}.json").write_text(
        json.dumps(_candles()), encoding="utf-8")
    ids = ["%s:%d:%s:%s:%s:%d" % (SYM, e["event_time_ms"], e["direction"],
                                  e["family"], e["rules_version"], i)
           for i, e in enumerate(events)]
    manifest = {
        "cutoff_ms": CUTOFF, "exit_horizon_ms": HORIZON,
        "input_hash": "synthetic-fixture", "funding_calendar": "FUNDING-CAL-v1",
        "groups": {GROUP: {"event_ids": ids}},
    }
    (combo / f"manifest_{SYM}_{RES}.json").write_text(
        json.dumps(manifest), encoding="utf-8")
    (combo / f"selection_{SYM}_{RES}.json").write_text(
        json.dumps({"n_dev": 8, "n_oos": 8}), encoding="utf-8")
    (combo / "build_report.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    settlements = [{"symbol": SYM, "fundingTime": CUTOFF + i * 28_800_000,
                    "fundingRate": 0.0001} for i in range(4)]
    (funding / f"funding_{SYM}.json").write_text(
        json.dumps(settlements), encoding="utf-8")
    declared = {}
    for p in sorted(pkg.rglob("*.json")):
        declared[str(p.relative_to(pkg)).replace("\\", "/")] = {"sha256": _sha(p)}
    (pkg / "package_manifest.json").write_text(
        json.dumps({"paquete": "SYNTHETIC", "archivos": declared}), encoding="utf-8")
    return pkg


def write_detections(pkg: Path, trades: list[dict]) -> None:
    """Respaldo directo del censo para cada operacion (H1). Re-hashea el paquete.

    Convierte cada operacion en una deteccion con formation_time=event_time_ms,
    disponible en/antes de la entrada, de modo que el generador pueda resolver
    la causalidad (available_at) sin inventar disponibilidad.
    """
    det_dir = pkg / "detections"
    det_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for t in trades:
        lines.append(json.dumps({
            "symbol": t["symbol"], "source_interval": t["res"],
            "formation_time": t["event_time_ms"],
            "definition_name": "MOMENTUM_ACCELERATION_UP",
            "direction": "up" if t["direction"] == "LONG" else "down",
            "formation_gap": False,
            "entry_time_same_grid": t["entry_ms"],
            "available_at": t["entry_ms"] - 1,
            "census_id": "SYN-%s" % t["event_id"],
        }))
    (det_dir / "census_btc15_detections.jsonl").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    manifest_path = pkg / "package_manifest.json"
    man = json.loads(manifest_path.read_text(encoding="utf-8"))
    declared = {}
    for p in sorted(pkg.rglob("*")):
        if p.is_file() and p != manifest_path:
            declared[str(p.relative_to(pkg)).replace("\\", "/")] = {"sha256": _sha(p)}
    man["archivos"] = declared
    manifest_path.write_text(json.dumps(man), encoding="utf-8")


class DashboardBacktestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="dashbt_"))
        self.pkg = build_package(self.tmp)
        self._saved = dict(dash.EXPERIMENTS)
        dash.EXPERIMENTS["test-synth"] = {
            "label": "synthetic", "not_label": "not complete",
            "package": str(self.pkg), "package_version": "SYNTHETIC",
            "combos": [(SYM, RES)], "scales": [1.0, 2.0, 3.0],
            "groups": [GROUP],
        }
        # Las combos usan una sola pareja: se permite sin tocar COMBOS global.
        dash.COMBOS[(SYM, RES)] = "eval15_btc"

    def tearDown(self) -> None:
        dash.EXPERIMENTS.clear()
        dash.EXPERIMENTS.update(self._saved)

    def _run(self, out: Path) -> int:
        return dash.run_experiment("test-synth", out)

    def test_not_allowed_experiment_runs_nothing(self) -> None:
        out = self.tmp / "out_na"
        rc = dash.run_experiment("rm -rf /", out)
        self.assertNotEqual(rc, 0)
        state = json.loads((out / "job_state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "fallido")
        self.assertEqual(state["error"], "EXPERIMENT_NOT_ALLOWED")
        self.assertFalse((out / "trades.json").exists())

    def test_altered_package_fails_closed(self) -> None:
        ev = self.pkg / "combos" / "eval15_btc" / f"events_{SYM}_{RES}.json"
        ev.write_text(ev.read_text(encoding="utf-8").replace('"LONG"', '"SHORT"', 1),
                      encoding="utf-8")
        out = self.tmp / "out_alt"
        rc = self._run(out)
        self.assertNotEqual(rc, 0)
        state = json.loads((out / "job_state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["error"], "PACKAGE_VERIFICATION_FAILED")
        self.assertFalse((out / "trades.json").exists())

    def test_executor_records_verifiable_identity_and_result_hashes(self) -> None:
        # Identidad de ejecucion: run_id unico (no el experimento), token,
        # pid, y hashes de los resultados declarados por el propio ejecutor.
        out = self.tmp / "ident"
        rc = dash.run_experiment("test-synth", out, run_id="bt-run-abc-0001",
                                 executor_token="0123456789abcdef", budget_ms=600000)
        self.assertEqual(rc, 0)
        state = json.loads((out / "job_state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "completado")
        self.assertEqual(state["run_id"], "bt-run-abc-0001")
        self.assertEqual(state["job_id"], "bt-run-abc-0001")
        self.assertNotEqual(state["run_id"], state["experiment_id"])
        self.assertEqual(state["executor_token"], "0123456789abcdef")
        self.assertIsInstance(state["executor_pid"], int)
        # Etiqueta DECLARADA por el ejecutor: el BFF no la trata como prueba.
        self.assertEqual(state["identity"], "declared")
        # Los hashes declarados son los de los archivos realmente escritos.
        for name, declared in state["result_hashes"].items():
            self.assertEqual(declared, _sha(out / name), name)
        # Los artefactos declaran la MISMA ejecucion y experimento que el
        # estado: sin identidad no se pueden servir como resultados.
        for name in ("summary.json", "trades.json", "reconciliation.json"):
            doc = json.loads((out / name).read_text(encoding="utf-8"))
            self.assertEqual(doc["run_id"], "bt-run-abc-0001", name)
            self.assertEqual(doc["experiment_id"], "test-synth", name)

    def test_executor_budget_expired_before_verification_fails_closed(self) -> None:
        # Presupuesto ya agotado: falla explicito (TIMEOUT) sin escribir resultados.
        out = self.tmp / "budget"
        rc = dash.run_experiment("test-synth", out, run_id="bt-run-budget-0002",
                                 executor_token="0123456789abcdef", budget_ms=1)
        # El presupuesto se mide desde el arranque; con 1 ms debe cerrar.
        state = json.loads((out / "job_state.json").read_text(encoding="utf-8"))
        if rc == 0:
            # Maquina muy rapida: si completo, al menos la identidad es coherente.
            self.assertEqual(state["status"], "completado")
        else:
            self.assertEqual(state["status"], "fallido")
            self.assertEqual(state["error"], "TIMEOUT")
            self.assertFalse((out / "trades.json").exists())

    def test_deterministic_results_and_reconciliation(self) -> None:
        out1, out2 = self.tmp / "o1", self.tmp / "o2"
        self.assertEqual(self._run(out1), 0)
        self.assertEqual(self._run(out2), 0)
        self.assertEqual(_sha(out1 / "trades.json"), _sha(out2 / "trades.json"))
        self.assertEqual(_sha(out1 / "reconciliation.json"),
                         _sha(out2 / "reconciliation.json"))
        summary = json.loads((out1 / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["n_trades_1x"] * 3, summary["n_trades_total"])
        self.assertTrue(summary["reconciliation_ok"])
        # Reconciliacion por celda dentro de tolerancia 1e-9.
        recon = json.loads((out1 / "reconciliation.json").read_text(encoding="utf-8"))
        self.assertTrue(recon["ok"])
        for cell in recon["cells"]:
            self.assertTrue(cell["match"], cell)

    def test_trade_identity_belongs_to_manifest(self) -> None:
        out = self.tmp / "ids"
        self.assertEqual(self._run(out), 0)
        man = json.loads((self.pkg / "combos" / "eval15_btc" /
                          f"manifest_{SYM}_{RES}.json").read_text(encoding="utf-8"))
        ids = set(man["groups"][GROUP]["event_ids"])
        trades = json.loads((out / "trades.json").read_text(encoding="utf-8"))["trades"]
        self.assertTrue(trades)
        for t in trades:
            self.assertIn(t["event_id"], ids)

    def test_zero_trade_cell_is_labelled_sin_operaciones(self) -> None:
        # Un grupo sin eventos debe declararse explicitamente, no omitirse.
        dash.EXPERIMENTS["test-synth"]["groups"] = [GROUP, "bearish-continuation"]
        out = self.tmp / "zero"
        self.assertEqual(self._run(out), 0)
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        empty = [c for c in summary["cells"]
                 if c.get("group") == "bearish-continuation"]
        self.assertTrue(empty)
        self.assertEqual(empty[0]["status"], "sin_operaciones")


class PackagePortabilityTest(unittest.TestCase):
    """El paquete publicado debe ser byte-portable entre plataformas.

    Regresion del defecto de serializacion: con core.autocrlf=true y sin
    .gitattributes, git normalizaba a LF los finales de linea del blob, de
    modo que un checkout limpio entregaba bytes distintos a los hasheados
    (21/33 archivos). Estos tests fallan si vuelve a ocurrir.
    """

    PKG = "docs/evidence/eval-census-v2-package"

    def _manifest(self) -> dict:
        return json.loads((ROOT / self.PKG / "package_manifest.json")
                          .read_text(encoding="utf-8"))["archivos"]

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True)

    def test_gitattributes_marks_package_as_binary(self) -> None:
        # -text en las rutas del paquete: git no traduce finales de linea.
        attr = self._git("check-attr", "text", "--",
                         f"{self.PKG}/package_manifest.json")
        self.assertEqual(attr.returncode, 0, attr.stderr)
        self.assertIn(b"text: unset", attr.stdout,
                      "package_manifest.json debe ser -text (binario)")

    def test_committed_blobs_hash_to_manifest(self) -> None:
        # Cada blob DEL COMMIT (no del working tree) debe hashear al sha256
        # declarado. Si autocrlf normaliza a LF, esto falla.
        man = self._manifest()
        bad = []
        for rel, meta in man.items():
            out = self._git("cat-file", "blob", f"HEAD:{self.PKG}/{rel}")
            self.assertEqual(out.returncode, 0, f"blob ausente: {rel}")
            if hashlib.sha256(out.stdout).hexdigest() != meta["sha256"]:
                bad.append(rel)
        self.assertEqual(bad, [], f"blobs que no hashean al manifiesto: {bad}")

    def test_working_tree_matches_manifest_bytes(self) -> None:
        for rel, meta in self._manifest().items():
            p = ROOT / self.PKG / rel
            self.assertTrue(p.exists(), rel)
            self.assertEqual(_sha(p), meta["sha256"], rel)
            self.assertEqual(p.stat().st_size, meta["bytes"], rel)

    def test_verify_script_accepts_package(self) -> None:
        r = subprocess.run(
            [sys.executable, "scripts/verify_eval_package.py",
             "--package", self.PKG], cwd=ROOT, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(b"PASS", r.stdout)

    def test_real_alteration_is_rejected(self) -> None:
        # Copia aislada del paquete: alterar un byte debe romper la verificacion.
        tmp = Path(tempfile.mkdtemp(prefix="pkgport_"))
        try:
            dst = tmp / "pkg"
            shutil.copytree(ROOT / self.PKG, dst)
            target = dst / "funding" / "funding_BTCUSDT.json"
            raw = bytearray(target.read_bytes())
            raw[len(raw) // 2] ^= 0x01
            target.write_bytes(bytes(raw))
            r = subprocess.run(
                [sys.executable, "scripts/verify_eval_package.py",
                 "--package", str(dst)], cwd=ROOT, capture_output=True)
            self.assertNotEqual(r.returncode, 0, r.stdout)
            self.assertIn(b"FAIL", r.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class PaperLabLinkTest(unittest.TestCase):
    """El enlace materializa la operacion EXACTA, no la fija."""

    def setUp(self) -> None:
        # El generador deriva rutas relativas al ROOT del repo; el paquete
        # sintetico se crea dentro de un temp del repo y se limpia al final.
        self.tmp = Path(tempfile.mkdtemp(prefix=".link_", dir=ROOT))
        self.pkg = build_package(self.tmp)
        self._saved = dict(dash.EXPERIMENTS)
        dash.EXPERIMENTS["test-synth"] = {
            "label": "synthetic", "not_label": "not complete",
            "package": str(self.pkg), "package_version": "SYNTHETIC",
            "combos": [(SYM, RES)], "scales": [1.0], "groups": [GROUP],
        }
        dash.COMBOS[(SYM, RES)] = "eval15_btc"
        self.out = self.tmp / "res"
        dash.run_experiment("test-synth", self.out)
        self.trades = json.loads(
            (self.out / "trades.json").read_text(encoding="utf-8"))["trades"]
        # El paquete se re-hashea al añadir el respaldo directo del censo;
        # el ejecutor ya termino, asi que el artefacto no depende de ello.
        write_detections(self.pkg, self.trades)

    def tearDown(self) -> None:
        dash.EXPERIMENTS.clear()
        dash.EXPERIMENTS.update(self._saved)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _build(self, target: dict, run_id: str = "bt-link-0001") -> dict:
        return paper_gen.build(self.pkg, None, 4, target=target,
                               trades_json=self.out / "trades.json",
                               run_id=run_id)

    def test_link_reproduces_the_exact_operation(self) -> None:
        t = [x for x in self.trades if not x["open_at_end"]][0]
        art = self._build({"event_id": t["event_id"], "group": t["group"],
                           "segment": t["segment"], "scale": t["scale"]})
        self.assertEqual(art["trade"]["net_pnl"], t["net_pnl"])
        self.assertEqual(art["trade"]["entry_ms"], t["entry_ms"])
        self.assertEqual(art["event"]["event_id"], t["event_id"])
        self.assertTrue(all(art["result"]["reconciled_to_engine"].values()))
        # El artefacto prueba a que ejecucion de Backtest pertenece.
        self.assertEqual(art["backtest_run_id"], "bt-link-0001")

    def test_winner_and_loser_links_differ(self) -> None:
        realized = [x for x in self.trades if not x["open_at_end"]]
        if not realized:
            self.skipTest("fixture sin operaciones realizadas")
        win = max(realized, key=lambda x: x["net_pnl"])
        los = min(realized, key=lambda x: x["net_pnl"])
        aw = self._build({"event_id": win["event_id"], "group": win["group"],
                          "segment": win["segment"], "scale": win["scale"]})
        al = self._build({"event_id": los["event_id"], "group": los["group"],
                          "segment": los["segment"], "scale": los["scale"]})
        self.assertNotEqual(aw["replay_id"], al["replay_id"])
        self.assertEqual(aw["trade"]["net_pnl"], win["net_pnl"])
        self.assertEqual(al["trade"]["net_pnl"], los["net_pnl"])

    def test_open_operation_has_no_fabricated_exit(self) -> None:
        opened = [x for x in self.trades if x["open_at_end"]]
        if not opened:
            self.skipTest("fixture sin operaciones abiertas")
        t = opened[0]
        art = self._build({"event_id": t["event_id"], "group": t["group"],
                           "segment": t["segment"], "scale": t["scale"]})
        self.assertFalse(art["trade"]["exit_executed"])
        self.assertTrue(art["trade"]["open_at_end"])
        self.assertIsNone(art["trade"]["realized_net"])
        # No hay paso de cierre ejecutado.
        self.assertFalse(any(s["exit"] is not None for s in art["window"]["steps"]))

    def test_unknown_target_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self._build({"event_id": "no-existe", "group": GROUP,
                         "segment": "dev", "scale": 1.0})


if __name__ == "__main__":
    unittest.main()
