"""Recuperacion parcial tras interrupcion (CLI real + loopback + reloj manual).

Leccion del incidente de la ventana exp-v2-ventana-3-20261115a (reinicio del
anfitrion durante el settle): sin cierre normal no hay manifiesto y sin
configuracion acreditada no hay reconstruccion. Esta suite demuestra, sin
mercado y con almacenamiento temporal, que:

1. La configuracion efectiva queda persistida de forma ATOMICA (temp +
   replace) ANTES de la primera adquisicion, con hashes internos y el mismo
   ``config_hash`` que publican las filas operativas.
2. El piloto publica checkpoints parciales en puntos existentes del
   recorrido (transicion de fase y lote operativo ya persistido), cada uno
   con estado INICIADA/PARCIAL, alcance acreditado POR PREFIJO (bytes +
   hash de esos bytes) y trabajo pendiente; un checkpoint NO es un cierre
   normal (no inventa exit code, no certifica recursos, no declara
   terminada la corrida).
3. Una interrupcion ABRUPTA (kill del proceso, como el incidente real) deja
   el dataset sin manifiesto ni resumen, pero con la configuracion inicial
   y los checkpoints disponibles.
4. El replay offline reconstruye SOLO el alcance acreditado por el ultimo
   checkpoint; lo escrito despues se cuenta (contable) y se limita
   explicitamente; el veredicto global sigue siendo LIMITACION y el
   denominador completo (acreditado + posterior + pendiente) se publica.
5. Un registro corrupto DENTRO del prefijo acreditado rompe la acreditacion
   de ese fichero; uno corrupto FUERA del corte solo se cuenta; y sin
   config_inicial ni checkpoints NO se reconstruye nada (nunca defaults).
"""

from __future__ import annotations

import atexit
import hashlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts"),
           str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import tests.test_research_pilot as tr  # noqa: E402
import tests.test_operativo_replay_offline as tro  # noqa: E402

_TMP: List[Path] = []


def _limpiar() -> None:
    for path in _TMP:
        shutil.rmtree(path, ignore_errors=True)


atexit.register(_limpiar)

HORIZONS_CORTOS: Tuple[Tuple[str, int], ...] = (("5m", 300_000),)


def _leer_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _ultimo_checkpoint(out_dir: Path) -> Optional[Dict[str, Any]]:
    path = out_dir / "checkpoints.jsonl"
    if not path.exists():
        return None
    entradas = [e for e in _leer_jsonl(path) if e.get("kind") == "checkpoint"]
    return entradas[-1] if entradas else None


def _validar_alcance_checkpoint(out_dir: Path, checkpoint: Dict[str, Any],
                               ) -> None:
    """Cada fichero del alcance esta acreditado por prefijo verificado."""
    assert checkpoint.get("estado") in ("INICIADA", "PARCIAL"), checkpoint
    assert checkpoint.get("fase") != "fin", checkpoint
    assert "exit_code" not in checkpoint, checkpoint
    assert "cierre normal" in str(checkpoint.get("nota")), checkpoint
    alcance = checkpoint.get("alcance") or []
    assert alcance, checkpoint
    for entrada in alcance:
        fichero = out_dir / str(entrada["fichero"])
        assert fichero.exists(), entrada
        bytes_n = int(entrada["bytes_cubiertos"])
        assert fichero.stat().st_size >= bytes_n, entrada
        sha = hashlib.sha256(fichero.read_bytes()[:bytes_n]).hexdigest()
        assert sha == entrada["sha256_prefijo"], entrada
        assert entrada["completa"] is False, entrada


def _ejecutar_parcial() -> Dict[str, Any]:
    """Corrida real con trabajo ya persistido, interrumpida ABRUPTAMENTE.

    Sin cierre normal: kill del proceso, como en el incidente real. Quedan
    config_inicial.json y checkpoints.jsonl; no hay manifiesto ni resumen.
    """
    tmp = Path(tempfile.mkdtemp(prefix="recuperacion-parcial-"))
    _TMP.append(tmp)
    run = tr.PilotRun(
        tmp, universe=tr.UNIVERSE, duration_s=120, settle_s=3900,
        selection_s=120, max_symbols=5, cycle_s=120, horizons=HORIZONS_CORTOS,
        max_http_attempts=2000, moves=tro.MOVES_LONG)
    e0 = tr.T0 + tr.MINUTE
    seed = list(range(e0 - 62_000, e0 + 1, 1_000))
    try:
        run.wait_ready(expected_followed=5)
        # 1) La configuracion efectiva ya esta persistida ANTES de que el
        #    piloto adquiera nada: sin observaciones todavia.
        config_inicial = json.loads(
            (run.out_dir / "config_inicial.json").read_text(
                encoding="utf-8"))
        assert config_inicial["kind"] == "config_inicial", config_inicial
        assert config_inicial["run_id"] == "pilot-sync", config_inicial
        sha_config = hashlib.sha256(json.dumps(
            config_inicial["config"], sort_keys=True,
            default=str).encode("utf-8")).hexdigest()
        assert sha_config == config_inicial["config_sha256"], config_inicial
        sha_op = hashlib.sha256(json.dumps(
            config_inicial["operativo_config"], sort_keys=True,
            default=str).encode("utf-8")).hexdigest()
        assert sha_op == config_inicial["operativo_config_sha256"], config
        assert run.out_dir / "observaciones.jsonl" is not None
        observaciones_previas = [
            r for r in _leer_jsonl(run.out_dir / "observaciones.jsonl")
            if r.get("kind") == "observacion"] \
            if (run.out_dir / "observaciones.jsonl").exists() else []
        assert not observaciones_previas, observaciones_previas

        # 2) Captura: una decision por simbolo; settle con trayectoria.
        run.step(e0, depth_symbols=tr.UNIVERSE,
                 trade_events={s: seed for s in tr.UNIVERSE},
                 evaluate=True, expected_obs=5)
        capture_end = run.status()["capture_end_ms"]
        run.advance(capture_end)
        assert run.status()["phase"] == "settle", run.status()
        # 3) Trayectoria del horizonte operativo (60 min por defecto del
        #    adaptador) disponible: el lote se resuelve y se persiste; el
        #    checkpoint del lote queda publicado.
        run.advance(e0 + 3_600_000 + tr.MINUTE * 2)
        ops_path = run.out_dir / "resultado_operativo.jsonl"
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            filas = [r for r in _leer_jsonl(ops_path)
                     if r.get("kind") == "resultado_operativo"] \
                if ops_path.exists() else []
            checkpoint = _ultimo_checkpoint(run.out_dir)
            if (len(filas) >= 5 and checkpoint
                    and checkpoint.get("punto") == "lote_operativo_persistido"):
                break
            if run.proc.poll() is not None:
                raise AssertionError(
                    f"el piloto termino antes de persistir el lote: "
                    f"rc={run.proc.poll()} stderr={run.stderr!r}")
            time.sleep(0.02)
        else:
            raise AssertionError("el lote operativo no se persistio a tiempo")
        # Checkpoint coherente: alcance por prefijo verificado.
        _validar_alcance_checkpoint(run.out_dir, checkpoint)

        # 4) Interrupcion ABRUPTA: sin cierre normal, sin manifiesto.
        run.proc.kill()
        run.proc.communicate(timeout=10)
        assert run.proc.returncode != 0, run.proc.returncode
        assert not (run.out_dir / "manifiesto.json").exists()
        assert not (run.out_dir / "resumen.json").exists()
        assert (run.out_dir / "config_inicial.json").exists()
        assert (run.out_dir / "checkpoints.jsonl").exists()
        return {"run": run, "out_dir": run.out_dir,
                "e0": e0, "checkpoint": checkpoint}
    except BaseException:
        run.shutdown()
        raise


def _replay(run_dir: Path, report_path: Path):
    """CLI real del replay offline con informe publicado."""
    return tro._replay(run_dir, report_path)


# ---------------------------------------------------------------------------
# 1) Configuracion inicial y checkpoints: persistencia antes de adquirir
# ---------------------------------------------------------------------------

def test_config_inicial_antes_de_adquirir_y_checkpoint_coherente() -> None:
    """La configuracion se persiste antes de adquirir; el checkpoint del
    lote acredita por prefijo y declara trabajo pendiente."""
    datos = _ejecutar_parcial()
    run = datos["run"]
    out_dir = run.out_dir
    try:
        config_inicial = json.loads(
            (out_dir / "config_inicial.json").read_text(encoding="utf-8"))
        # El config_hash de las filas operativas es el publicado en la
        # configuracion inicial (mismo contrato que el manifiesto).
        filas = [r for r in _leer_jsonl(out_dir / "resultado_operativo.jsonl")
                 if r.get("kind") == "resultado_operativo"]
        assert filas, filas
        hashes_fila = {r["config_hash"] for r in filas}
        assert hashes_fila == {config_inicial["operativo_config_hash"]}, \
            (hashes_fila, config_inicial["operativo_config_hash"])
        # Checkpoints: transicion de fase y lote persistido, en orden.
        entradas = [e for e in _leer_jsonl(out_dir / "checkpoints.jsonl")
                    if e.get("kind") == "checkpoint"]
        puntos = [e.get("punto") for e in entradas]
        assert puntos[0] == "transicion_captura_settle", puntos
        assert "lote_operativo_persistido" in puntos, puntos
        # El estado declarado es PARCIAL (fase settle): nada declara fin.
        for entrada in entradas:
            _validar_alcance_checkpoint(out_dir, entrada)
        ultimo = entradas[-1]
        pendientes = ultimo["trabajo_pendiente"]
        assert set(pendientes) == {"observaciones", "operativos",
                                   "contabilidad"}, pendientes
    finally:
        run.shutdown()


# ---------------------------------------------------------------------------
# 2) Recuperacion: reconstruccion limitada al alcance acreditado
# ---------------------------------------------------------------------------

def test_recuperacion_limitada_al_alcance_acreditado() -> None:
    """El replay reconstruye SOLO lo acreditado por el ultimo checkpoint;
    el veredicto global sigue siendo LIMITACION y el denominador completo
    (acreditado + posterior + pendiente) se publica sin reducirse."""
    datos = _ejecutar_parcial()
    run = datos["run"]
    out_dir = run.out_dir
    tmp = out_dir.parent
    try:
        run.shutdown()
        proc, informe = _replay(out_dir, tmp / "replay_parcial.json")
        assert proc.returncode == 3, (proc.stdout, proc.stderr)
        assert informe["veredicto"]["estado"] == "LIMITACION", informe
        motivos = {l["motivo"] for l in informe["limitaciones"]}
        assert "manifiesto_ausente" in motivos, informe
        assert "corrida_parcial_sin_cierre_normal" in motivos, informe
        # Configuracion acreditada desde config_inicial (sin defaults).
        assert informe["veredicto"]["config_operativa_acreditada"] is True, \
            informe
        recuperacion = informe.get("recuperacion") or {}
        assert recuperacion.get("activa") is True, informe
        assert recuperacion.get("modo") == "parcial_offline", informe
        assert recuperacion["ultimo_checkpoint"]["punto"] == \
            "lote_operativo_persistido", recuperacion
        # Denominador completo: acreditado + posterior + pendiente.
        den = recuperacion["denominador"]
        assert den["observaciones_acreditadas_por_checkpoint"] == 5, den
        # Sin observaciones aptas posteriores: lo posterior al checkpoint son
        # los resultados forward (kind=resultado), contados aparte.
        assert den["observaciones_posteriores_no_acreditadas"] == 0, den
        assert den["resultados_forward_posteriores_no_acreditados"] == 5, den
        assert den["lineas_posteriores_por_fichero"][
            "observaciones.jsonl"] == 5, den
        pend = den["pendientes_declarados_por_el_checkpoint"]
        assert set(pend) == {"observaciones", "operativos",
                             "contabilidad"}, pend
        # Alcance validado: prefijos verificados por el replay.
        alcance = recuperacion["alcance_validado"]
        nombres = {a["fichero"] for a in alcance}
        assert {"observaciones.jsonl", "resultado_operativo.jsonl",
                "consultas_klines.jsonl", "http_requests.jsonl"} <= nombres, \
            alcance
        # Lo acreditado se reconstruye identico: 5 coincidentes.
        v = informe["veredicto"]
        assert v["coincidentes"] == 5, informe
        assert v["limitadas"] == 0, informe
        assert informe["denominador"]["observaciones_reconstruidas"] == 5, \
            informe
        assert informe["run_id"] == "pilot-sync", informe
    finally:
        run.shutdown()


def test_registro_posterior_al_checkpoint_no_se_usa() -> None:
    """Lo escrito DESPUES del ultimo checkpoint existe pero NO esta
    acreditado: se cuenta, se limita explicitamente y no se reconstruye."""
    datos = _ejecutar_parcial()
    run = datos["run"]
    out_dir = run.out_dir
    tmp = out_dir.parent
    try:
        run.shutdown()
        destino = tmp / "posterior"
        shutil.copytree(out_dir, destino)
        # Simula trabajo persistido despues del ultimo checkpoint: una
        # observacion apta adicional (datos sinteticos de prueba).
        obs_path = destino / "observaciones.jsonl"
        filas_obs = _leer_jsonl(obs_path)
        base = next(r for r in filas_obs if r.get("kind") == "observacion"
                    and r.get("apto_para_evaluacion"))
        extra = dict(base)
        extra["observation_id"] = "FAKEPOST1"
        extra["decision_ms"] = int(base["decision_ms"]) + 60_000
        obs_path.write_text(
            obs_path.read_text(encoding="utf-8")
            + json.dumps(extra, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
        proc, informe = _replay(destino, tmp / "replay_posterior.json")
        assert proc.returncode == 3, (proc.stdout, proc.stderr)
        recuperacion = informe["recuperacion"]
        den = recuperacion["denominador"]
        assert den["observaciones_posteriores_no_acreditadas"] == 1, den
        # La observacion posterior aparece limitada con su motivo honesto y
        # NO entra en la reconstruccion.
        fila = next(c for c in informe["observaciones"]
                    if c["observation_id"] == "FAKEPOST1")
        assert fila["estado"] == "limitada", fila
        assert fila["motivo"] == "registro_posterior_al_ultimo_checkpoint", \
            fila
        # El resto del denominador no cambia: 5 acreditadas, 5 coincidentes.
        assert den["observaciones_acreditadas_por_checkpoint"] == 5, den
        assert informe["veredicto"]["coincidentes"] == 5, informe
        assert informe["veredicto"]["limitadas"] == 1, informe
        assert informe["denominador"]["observaciones_reconstruidas"] == 5, \
            informe
    finally:
        run.shutdown()


# ---------------------------------------------------------------------------
# 3) Corrupcion dentro y fuera del corte acreditado
# ---------------------------------------------------------------------------

def test_corrupcion_dentro_del_prefijo_rota_la_acreditacion() -> None:
    """Un byte corrupto DENTRO del prefijo acreditado rompe el hash del
    checkpoint: ese fichero pierde la acreditacion y NADA se reconstruye
    desde el."""
    datos = _ejecutar_parcial()
    run = datos["run"]
    out_dir = run.out_dir
    tmp = out_dir.parent
    try:
        run.shutdown()
        destino = tmp / "corrupto"
        shutil.copytree(out_dir, destino)
        obs_path = destino / "observaciones.jsonl"
        brutos = bytearray(obs_path.read_bytes())
        brutos[0] = ord("X") if brutos[0] != ord("X") else ord("Y")
        obs_path.write_bytes(bytes(brutos))
        proc, informe = _replay(destino, tmp / "replay_corrupto.json")
        assert proc.returncode == 3, (proc.stdout, proc.stderr)
        motivos = {l["motivo"] for l in informe["limitaciones"]}
        assert "integridad_checkpoint_rota" in motivos, informe
        assert informe["veredicto"]["config_operativa_acreditada"] is True, \
            informe
        # La observacion ya no puede acreditarse: nada coincidente.
        assert informe["veredicto"]["coincidentes"] == 0, informe
        assert informe["denominador"]["observaciones_reconstruidas"] == 0, \
            informe
    finally:
        run.shutdown()


def test_corrupcion_fuera_del_corte_solo_se_cuenta() -> None:
    """Una linea corrupta DESPUES del corte se cuenta (ilegible posterior)
    y no rompe la acreditacion del prefijo ni la reconstruccion del resto."""
    datos = _ejecutar_parcial()
    run = datos["run"]
    out_dir = run.out_dir
    tmp = out_dir.parent
    try:
        run.shutdown()
        destino = tmp / "corrupto_posterior"
        shutil.copytree(out_dir, destino)
        obs_path = destino / "observaciones.jsonl"
        obs_path.write_text(
            obs_path.read_text(encoding="utf-8") + '{"roto"\n',
            encoding="utf-8", newline="\n")
        proc, informe = _replay(destino, tmp / "replay_corrupto_post.json")
        assert proc.returncode == 3, (proc.stdout, proc.stderr)
        recuperacion = informe["recuperacion"]
        den = recuperacion["denominador"]
        assert den["lineas_ilegibles_posteriores"] >= 1, den
        # El prefijo acreditado sigue integro: 5 coincidentes.
        assert informe["veredicto"]["coincidentes"] == 5, informe
    finally:
        run.shutdown()


# ---------------------------------------------------------------------------
# 4) Sin config_inicial ni checkpoints: LIMITACION sin defaults
# ---------------------------------------------------------------------------

def test_sin_config_inicial_ni_checkpoints_no_hay_defaults() -> None:
    """Dataset interrumpido SIN las fuentes de acreditacion (el estado de
    la ventana 3): manifiesto_ausente + config_operativa_ausente, nada
    reconstruido, sin valores por defecto."""
    datos = _ejecutar_parcial()
    run = datos["run"]
    out_dir = run.out_dir
    tmp = out_dir.parent
    try:
        run.shutdown()
        destino = tmp / "sin_config"
        shutil.copytree(out_dir, destino)
        (destino / "config_inicial.json").unlink()
        (destino / "checkpoints.jsonl").unlink()
        proc, informe = _replay(destino, tmp / "replay_sin_config.json")
        assert proc.returncode == 3, (proc.stdout, proc.stderr)
        motivos = {l["motivo"] for l in informe["limitaciones"]}
        assert "manifiesto_ausente" in motivos, informe
        assert "config_operativa_ausente" in motivos, informe
        assert informe.get("recuperacion") is None, informe
        assert informe["veredicto"]["config_operativa_acreditada"] is False, \
            informe
        # Nada se reconstruye con defaults: ni una operacion.
        assert informe["economia"]["operaciones_replay"] == 0, informe
        aptas_limitadas = [c for c in informe["observaciones"]
                           if c["estado"] == "limitada"]
        assert len(aptas_limitadas) == 5, informe
    finally:
        run.shutdown()


def test_config_inicial_corrupta_no_se_acepta() -> None:
    """Si la configuracion persistida no integra (hash interno roto), la
    recuperacion no la usa: LIMITACION, sin defaults."""
    datos = _ejecutar_parcial()
    run = datos["run"]
    out_dir = run.out_dir
    tmp = out_dir.parent
    try:
        run.shutdown()
        destino = tmp / "config_rota"
        shutil.copytree(out_dir, destino)
        ci_path = destino / "config_inicial.json"
        ci = json.loads(ci_path.read_text(encoding="utf-8"))
        ci["config"]["stop_distance_pct"] = 0.9
        ci_path.write_text(
            json.dumps(ci, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n", encoding="utf-8", newline="\n")
        proc, informe = _replay(destino, tmp / "replay_config_rota.json")
        assert proc.returncode == 3, (proc.stdout, proc.stderr)
        motivos = {l["motivo"] for l in informe["limitaciones"]}
        assert "config_inicial_hash_roto" in motivos, informe
        assert informe.get("recuperacion") is None, informe
        assert informe["veredicto"]["config_operativa_acreditada"] is False, \
            informe
        assert informe["economia"]["operaciones_replay"] == 0, informe
    finally:
        run.shutdown()
