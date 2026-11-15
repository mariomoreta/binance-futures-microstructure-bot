#!/usr/bin/env python
"""Reconstruccion OFFLINE de los resultados operativos de una corrida.

Reutiliza el adaptador y los motores existentes (``paper_lab_engine`` y
``backtest_offline``) sobre los archivos YA persistidos por el piloto:

- ``observaciones.jsonl``: observaciones con su informacion disponible al
  decidir (seleccion, libro, flujo, decision_ms).
- ``consultas_klines.jsonl``: cuerpo REAL recibido en cada consulta de
  trayectoria, con parametros exactos, instantes, estado HTTP y hash.
- ``funding_adquisicion.jsonl`` y ``funding/*.json``: liquidaciones de
  funding realmente observadas (metodo A) o calendario con cobertura (B).
- ``resultado_operativo.jsonl``: resultado de la ejecucion. Se COMPARA; no
  se usa como entrada de decision.

No abre red, no consulta a la venue, no crea cliente, motor, servicio ni base
de datos: solo lee lo persistido y reconstruye. Un fichero ausente o
corrupto produce una LIMITACION explicita: nunca un resultado inventado y
nunca un funding desconocido convertido en cero.

Uso:
    python scripts/research_operativo_replay.py --run-dir <dir> [--out <json>]

Codigos de salida:
    0  EQUIVALENTE (o EQUIVALENTE_CON_LIMITACIONES: solo limites de cruce)
    3  LIMITACION   (faltan o estan corruptos ficheros: no se inventa)
    4  DIFERENCIAS  (el replay corre y no coincide con la ejecucion)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from microstructure_probe.backtest_offline import FundingCalendar  # noqa: E402
from microstructure_probe.paper_lab_engine import PaperCandle  # noqa: E402
from research_operativo_adapter import (  # noqa: E402
    OperativoAdapter, OperativoConfig,
)

REPLAY_VERSION = "research-operativo-replay/v1"

# Campos comparados entre ejecucion y replay. Los timestamps de publicacion
# pueden diferir: no se comparan.
CAMPOS_COMPARADOS = (
    "observation_id",
    "symbol",
    "role",
    "direction",
    "decision",
    "decision_ms",
    "entry_px",
    "entry_ms",
    "stop_px",
    "exit_px",
    "exit_ms",
    "exit_reason",
    "exit_executed",
    "open_at_end",
    "qty",
    "gross_pnl",
    "fees",
    "spread_slip",
    "funding",
    "net_pnl",
    "funding_estado",
    "neto_estado",
    "neto_motivo",
    "contabilidad_funding_estado",
    "config_hash",
    "engine_version",
)

# Limitaciones que IMPIDEN reconstruir (no son un simple cruce de verificacion).
MOTIVOS_RECONSTRUCTIVOS = frozenset({
    "manifiesto_ausente",
    "manifiesto_corrupto",
    "observaciones_ausentes",
    "observaciones_corruptas",
    "consultas_klines_ausentes",
    "consultas_klines_corruptas",
    "consulta_corrupta_hash",
    "consulta_cuerpo_ilegible",
    "consulta_sin_cuerpo",
    "resultados_ausentes",
    "resultados_corruptos",
})


class ArchivoCorrupto(Exception):
    """El fichero existe pero no se puede interpretar."""


# ---------------------------------------------------------------------------
# Lectura (solo lectura) de lo persistido
# ---------------------------------------------------------------------------

def leer_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                fila = json.loads(line)
            except ValueError as exc:
                raise ArchivoCorrupto(f"{path.name}:{n}: {exc}") from exc
            if isinstance(fila, dict):
                rows.append(fila)
    return rows


def leer_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ArchivoCorrupto(f"{path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise ArchivoCorrupto(f"{path.name}: no es un objeto JSON")
    return data


def _config_operativa(data: Optional[Dict[str, Any]]) -> OperativoConfig:
    """Reconstruye la configuracion operativa congelada desde el manifiesto."""
    conocidos = {f.name for f in fields(OperativoConfig)}
    kwargs = {k: v for k, v in (data or {}).items() if k in conocidos}
    kwargs.pop("funding_calendar", None)
    return OperativoConfig(**kwargs)


def _velas_desde_filas(
    filas: List[Any], reloj_ms: int,
) -> List[PaperCandle]:
    """Convierte el cuerpo de klines en velas causales (mismo corte que el piloto).

    Se descartan las velas cuya apertura es posterior al reloj de la consulta:
    no eran conocidas en ese instante. No se rellenan huecos ni se convierten
    ausencias en cero.
    """
    out: List[PaperCandle] = []
    for r in filas:
        try:
            open_ms = int(r[0])
            close_ms = int(r[6]) if r[6] is not None else None
        except (TypeError, ValueError, IndexError):
            continue
        if open_ms > int(reloj_ms):
            continue
        out.append(PaperCandle(
            open_time_ms=open_ms, open=float(r[1]), high=float(r[2]),
            low=float(r[3]), close=float(r[4]) if r[4] is not None else None,
            close_time_ms=close_ms,
        ))
    return out


def _iguales(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        escala = max(1.0, abs(float(a)), abs(float(b)))
        return abs(float(a) - float(b)) <= 1e-9 * escala
    return a == b


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------

def _cargar_consultas(
    path: Path, ledger: List[Dict[str, Any]],
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    """Lee los cuerpos persistidos y comprueba su hash y su vinculo con el ledger.

    Devuelve (consultas por observation_id, limitaciones). Una fila con hash
    incoherente o cuerpo ilegible se descarta: no se usa para reconstruir.
    """
    limitaciones: List[Dict[str, Any]] = []
    por_oid: Dict[str, List[Dict[str, Any]]] = {}
    if not path.exists():
        limitaciones.append({
            "motivo": "consultas_klines_ausentes",
            "detalle": "no existe el fichero de cuerpos de las consultas "
                       "klines: no hay trayectoria reconstructible",
        })
        return por_oid, limitaciones
    try:
        filas = leer_jsonl(path)
    except ArchivoCorrupto as exc:
        limitaciones.append({"motivo": "consultas_klines_corruptas",
                             "detalle": str(exc)})
        return por_oid, limitaciones
    # Vinculo con el ledger HTTP: hash y parametros de la misma peticion.
    ledger_por_sha: Dict[str, List[Dict[str, Any]]] = {}
    for row in ledger:
        sha = row.get("response_sha256")
        if sha:
            ledger_por_sha.setdefault(str(sha), []).append(row)
    for row in filas:
        if row.get("kind") != "consulta_klines_trayectoria":
            continue
        oid = str(row.get("observation_id"))
        cuerpo = row.get("cuerpo")
        sha = row.get("cuerpo_sha256")
        if not isinstance(cuerpo, str) or not sha:
            limitaciones.append({
                "motivo": "consulta_sin_cuerpo",
                "detalle": "consulta sin cuerpo o sin hash",
                "observation_id": oid,
            })
            continue
        real = hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()
        if real != str(sha):
            limitaciones.append({
                "motivo": "consulta_corrupta_hash",
                "detalle": "el hash del cuerpo persistido no coincide",
                "observation_id": oid,
                "cuerpo_sha256_declarado": sha,
                "cuerpo_sha256_calculado": real,
            })
            continue
        try:
            payload = json.loads(cuerpo)
        except ValueError as exc:
            limitaciones.append({
                "motivo": "consulta_cuerpo_ilegible",
                "detalle": str(exc),
                "observation_id": oid,
            })
            continue
        if not isinstance(payload, list):
            limitaciones.append({
                "motivo": "consulta_cuerpo_ilegible",
                "detalle": "el cuerpo no es una lista de velas",
                "observation_id": oid,
            })
            continue
        entradas = ledger_por_sha.get(str(sha), [])
        if not entradas:
            limitaciones.append({
                "motivo": "consulta_sin_vinculo_ledger",
                "detalle": "no hay fila del ledger HTTP con ese hash",
                "observation_id": oid,
            })
        fila = dict(row)
        fila["_filas"] = payload
        por_oid.setdefault(oid, []).append(fila)
    for oid in por_oid:
        por_oid[oid].sort(key=lambda r: int(r.get("consulta_numero") or 0))
    return por_oid, limitaciones


def _replay(
    run_dir: Path, out_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Reconstruye la corrida desde lo persistido y compara con la ejecucion."""
    limitaciones: List[Dict[str, Any]] = []
    fuentes: Dict[str, Any] = {}

    # -- manifiesto (configuracion congelada) --------------------------------
    manifest_path = run_dir / "manifiesto.json"
    manifest: Dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = leer_json(manifest_path)
        except ArchivoCorrupto as exc:
            limitaciones.append({"motivo": "manifiesto_corrupto",
                                 "detalle": str(exc)})
    else:
        limitaciones.append({
            "motivo": "manifiesto_ausente",
            "detalle": "sin manifiesto no se puede reconstruir la "
                       "configuracion operativa congelada",
        })
    config_piloto = manifest.get("config") or {}
    operativo_cfg = _config_operativa(manifest.get("operativo_config"))
    funding_source = str(config_piloto.get("funding_source") or "none")
    funding_method = str(config_piloto.get("funding_method") or "")
    metodo_observado = (funding_source == "exchange"
                        and funding_method == "observed-settlements")

    # -- ledger HTTP (vinculo y hash) ---------------------------------------
    ledger: List[Dict[str, Any]] = []
    ledger_path = run_dir / "http_requests.jsonl"
    if ledger_path.exists():
        try:
            ledger = leer_jsonl(ledger_path)
        except ArchivoCorrupto as exc:
            limitaciones.append({"motivo": "ledger_corrupto",
                                 "detalle": str(exc)})
    else:
        limitaciones.append({
            "motivo": "ledger_ausente",
            "detalle": "sin ledger HTTP no se puede cruzar el hash de los "
                       "cuerpos con la peticion que los produjo",
        })
    fuentes["http_requests"] = len(ledger)

    # -- observaciones --------------------------------------------------------
    obs_path = run_dir / "observaciones.jsonl"
    observaciones: List[Dict[str, Any]] = []
    if obs_path.exists():
        try:
            filas = leer_jsonl(obs_path)
        except ArchivoCorrupto as exc:
            limitaciones.append({"motivo": "observaciones_corruptas",
                                 "detalle": str(exc)})
            filas = []
        observaciones = [r for r in filas
                         if r.get("kind") == "observacion"
                         and r.get("apto_para_evaluacion")]
    else:
        limitaciones.append({"motivo": "observaciones_ausentes",
                             "detalle": "no existe observaciones.jsonl"})
    fuentes["observaciones_aptas"] = len(observaciones)

    # -- consultas klines (cuerpos) ------------------------------------------
    consultas, lim_consultas = _cargar_consultas(
        run_dir / "consultas_klines.jsonl", ledger)
    limitaciones.extend(lim_consultas)
    fuentes["consultas_klines"] = sum(len(v) for v in consultas.values())
    fuentes["observaciones_con_consulta"] = len(consultas)

    # -- funding --------------------------------------------------------------
    funding_log: List[Dict[str, Any]] = []
    funding_path = run_dir / "funding_adquisicion.jsonl"
    if funding_path.exists():
        try:
            funding_log = leer_jsonl(funding_path)
        except ArchivoCorrupto as exc:
            limitaciones.append({"motivo": "funding_log_corrupto",
                                 "detalle": str(exc)})
    fuentes["funding_adquisiciones"] = len(
        [r for r in funding_log if r.get("kind") == "funding_adquisicion"])

    # -- ejecucion (se COMPARA, no se usa como entrada) ------------------------
    ejecucion: Dict[str, Dict[str, Any]] = {}
    ejec_rows = 0
    op_path = run_dir / "resultado_operativo.jsonl"
    if op_path.exists():
        try:
            filas_op = leer_jsonl(op_path)
        except ArchivoCorrupto as exc:
            limitaciones.append({"motivo": "resultados_corruptos",
                                 "detalle": str(exc)})
            filas_op = []
        for row in filas_op:
            if row.get("kind") != "resultado_operativo":
                continue
            ejec_rows += 1
            oid = str(row.get("observation_id"))
            # El estado final por observacion es la ULTIMA fila persistida.
            ejecucion[oid] = row
    else:
        limitaciones.append({"motivo": "resultados_ausentes",
                             "detalle": "no existe resultado_operativo.jsonl"})
    fuentes["resultados_ejecucion"] = ejec_rows

    # -- replay ---------------------------------------------------------------
    tmp_dir = Path(tempfile.mkdtemp(prefix="replay-operativo-"))
    adapter = OperativoAdapter(
        store_path=tmp_dir / "replay_resultado_operativo.jsonl",
        cfg=operativo_cfg,
    )
    resultados: Dict[str, Any] = {}
    velas_por_oid: Dict[str, List[PaperCandle]] = {}
    motivo_sin_trayectoria: Dict[str, str] = {}
    # Calendarios por observacion (metodo B): el log de adquisicion lleva el
    # calendario que se aplico a cada observacion.
    cal_por_oid: Dict[str, FundingCalendar] = {}
    for row in funding_log:
        if row.get("kind") != "funding_adquisicion":
            continue
        if row.get("estado") != "OK" or not isinstance(row.get("calendar"), dict):
            continue
        try:
            cal = FundingCalendar.from_dict(row["calendar"])
        except Exception:
            continue
        if row.get("scope") == "observacion" and row.get("observation_id"):
            cal_por_oid[str(row["observation_id"])] = cal

    orden = sorted(
        observaciones,
        key=lambda o: (int(o["decision_ms"]), str(o["symbol"]).upper(),
                       str(o["observation_id"])))
    for obs in orden:
        oid = str(obs["observation_id"])
        consultas_oid = consultas.get(oid) or []
        if not consultas_oid:
            motivo_sin_trayectoria[oid] = "sin_trayectoria_persistida"
            continue
        cal = cal_por_oid.get(oid) if not metodo_observado else None
        tr = None
        velas: List[PaperCandle] = []
        for consulta in consultas_oid:
            filas = consulta.get("_filas") or []
            if not filas:
                motivo_sin_trayectoria[oid] = "sin_trayectoria_en_la_consulta"
                continue
            velas = _velas_desde_filas(filas, int(consulta.get("reloj_ms") or 0))
            tr = adapter.procesar_observacion(obs, velas, funding_calendar=cal)
        if tr is None:
            continue
        velas_por_oid[oid] = velas
        resultados[oid] = tr
        contabilidad = None
        if (metodo_observado and tr.decision == "ENTRADA_EJECUTADA"
                and tr.exit_executed and tr.exit_ms is not None
                and tr.entry_ms is not None):
            contabilidad = {
                "estado": "PENDIENTE",
                "motivo": "espera_contable: liquidacion posterior a la "
                          "salida todavia no observada",
            }
        adapter.persistir(tr, contabilidad=contabilidad)

    # -- contabilidad diferida de funding (metodo A) --------------------------
    if metodo_observado:
        pendientes: Dict[str, List[str]] = {}
        for oid, tr in resultados.items():
            if (tr.decision == "ENTRADA_EJECUTADA" and tr.exit_executed
                    and tr.exit_ms is not None and tr.entry_ms is not None):
                pendientes.setdefault(str(tr.symbol).upper(), []).append(oid)
        for row in funding_log:
            if row.get("kind") != "funding_adquisicion":
                continue
            if row.get("estado") != "OK" or not isinstance(row.get("calendar"), dict):
                continue
            if row.get("scope") != "simbolo":
                continue
            symbol = str(row.get("symbol") or "").upper()
            try:
                cal = FundingCalendar.from_dict(row["calendar"])
            except Exception:
                continue
            for oid in list(pendientes.get(symbol) or []):
                tr = resultados.get(oid)
                velas = velas_por_oid.get(oid) or []
                if tr is None or not velas:
                    continue
                veredicto = adapter.reevaluar_funding(tr, velas, cal)
                if veredicto["creditable"]:
                    estado = "ACREDITADA"
                    motivo = "liquidaciones observadas; cobertura completa"
                elif veredicto["puede_mejorar"]:
                    estado = "PENDIENTE"
                    motivo = "espera_contable: %s" % veredicto["motivo"]
                else:
                    estado = "UNKNOWN"
                    motivo = str(veredicto["motivo"])
                adapter.persistir(
                    veredicto["resultado"],
                    contabilidad={"estado": estado, "motivo": motivo})
                if estado != "PENDIENTE":
                    pendientes[symbol].remove(oid)
        # Cierre de la espera contable (como en el piloto).
        if any(pendientes.values()):
            resumen = {}
            resumen_path = run_dir / "resumen.json"
            if resumen_path.exists():
                try:
                    resumen = leer_json(resumen_path)
                except ArchivoCorrupto:
                    resumen = {}
            stop_reason = str(resumen.get("stop_reason") or "")
            cierre = str((resumen.get("espera_contable") or {}).get("cierre") or "")
            parada = bool(stop_reason) and stop_reason != "duracion"
            estado = "PENDIENTE" if parada else "UNKNOWN"
            motivo = (stop_reason if parada else
                      (cierre or "vencimiento_de_la_espera_contable"))
            for symbol, oids in pendientes.items():
                for oid in list(oids):
                    tr = resultados.get(oid)
                    if tr is None:
                        continue
                    adapter.persistir(
                        tr, contabilidad={"estado": estado, "motivo": motivo})
                    oids.remove(oid)

    # -- comparacion ----------------------------------------------------------
    filas_replay = leer_jsonl(adapter.store_path)
    replay: Dict[str, Dict[str, Any]] = {}
    for row in filas_replay:
        if row.get("kind") != "resultado_operativo":
            continue
        replay[str(row.get("observation_id"))] = row
    adapter.close()

    comparacion: List[Dict[str, Any]] = []
    for oid in sorted(set(ejecucion) | set(replay)):
        fila_ej = ejecucion.get(oid)
        fila_rp = replay.get(oid)
        if fila_ej is None:
            comparacion.append({
                "observation_id": oid, "estado": "limitada",
                "motivo": "sin_resultado_en_la_ejecucion",
            })
            continue
        if fila_rp is None:
            comparacion.append({
                "observation_id": oid, "estado": "limitada",
                "motivo": "sin_resultado_en_el_replay",
            })
            continue
        diferencias = []
        for campo in CAMPOS_COMPARADOS:
            a = fila_ej.get(campo)
            b = fila_rp.get(campo)
            if not _iguales(a, b):
                diferencias.append({"campo": campo, "ejecucion": a,
                                    "replay": b})
        comparacion.append({
            "observation_id": oid,
            "estado": "coincidente" if not diferencias else "diferente",
            "diferencias": diferencias,
        })

    # Observaciones sin resultado en ninguna de las dos partes.
    for oid, motivo in sorted(motivo_sin_trayectoria.items()):
        if oid in ejecucion or oid in replay:
            continue
        comparacion.append({
            "observation_id": oid, "estado": "limitada",
            "motivo": motivo,
        })

    n_coinc = sum(1 for c in comparacion if c["estado"] == "coincidente")
    n_dif = sum(1 for c in comparacion if c["estado"] == "diferente")
    n_lim = sum(1 for c in comparacion if c["estado"] == "limitada")

    economia = {
        "operaciones_ejecucion": sum(
            1 for r in ejecucion.values()
            if r.get("decision") == "ENTRADA_EJECUTADA"),
        "operaciones_replay": sum(
            1 for r in replay.values()
            if r.get("decision") == "ENTRADA_EJECUTADA"),
        "neto_completo_ejecucion": sum(
            1 for r in ejecucion.values() if r.get("neto_estado") == "COMPLETO"),
        "neto_completo_replay": sum(
            1 for r in replay.values() if r.get("neto_estado") == "COMPLETO"),
        "neto_conditionado_ejecucion": sum(
            1 for r in ejecucion.values()
            if r.get("neto_estado") == "CONDICIONADO_SIN_FUNDING_COMPLETO"),
        "neto_conditionado_replay": sum(
            1 for r in replay.values()
            if r.get("neto_estado") == "CONDICIONADO_SIN_FUNDING_COMPLETO"),
        "neto_unknown_ejecucion": sum(
            1 for r in ejecucion.values() if r.get("neto_estado") == "UNKNOWN"),
        "neto_unknown_replay": sum(
            1 for r in replay.values() if r.get("neto_estado") == "UNKNOWN"),
    }

    reconstructivas = [l for l in limitaciones
                       if l.get("motivo") in MOTIVOS_RECONSTRUCTIVOS]
    if reconstructivas or n_lim:
        # Faltan o estan corruptos datos: se declara la limitacion y NO se
        # inventa ningun resultado (las diferencias que se observen pueden
        # ser consecuencia de la propia limitacion).
        estado = "LIMITACION"
    elif n_dif:
        estado = "DIFERENCIAS"
    elif limitaciones:
        # Solo hay limites de verificacion (p. ej. sin ledger): la
        # reconstruccion coincide y la limitacion queda publicada.
        estado = "EQUIVALENTE_CON_LIMITACIONES"
    else:
        estado = "EQUIVALENTE"

    return {
        "version": REPLAY_VERSION,
        "run_id": manifest.get("run_id") or config_piloto.get("run_id"),
        "run_dir": str(run_dir),
        "metodo_funding": funding_method,
        "fuente_funding": funding_source,
        "veredicto": {
            "estado": estado,
            "observaciones_comparadas": len(comparacion),
            "coincidentes": n_coinc,
            "diferentes": n_dif,
            "limitadas": n_lim,
            "limitaciones": len(limitaciones),
            "limitaciones_reconstructivas": len(reconstructivas),
            "sin_red": True,
            "reutiliza_adaptador_y_motores_existentes": True,
        },
        "fuentes": fuentes,
        "limitaciones": limitaciones,
        "economia": economia,
        "observaciones": comparacion,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Reconstruccion offline de los resultados operativos.")
    p.add_argument("--run-dir", required=True,
                   help="directorio de la corrida (persistido por el piloto)")
    p.add_argument("--out", default=None,
                   help="fichero JSON donde escribir el informe")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        print(json.dumps({
            "error": f"no existe el directorio de corrida: {run_dir}",
            "limitacion": "sin datos persistidos no hay resultado: nunca se "
                          "inventa",
        }, ensure_ascii=False), file=sys.stderr)
        return 3
    informe = _replay(run_dir)
    texto = json.dumps(informe, ensure_ascii=False, indent=2,
                       sort_keys=True) + "\n"
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(texto, encoding="utf-8", newline="\n")
    print(json.dumps(informe["veredicto"], ensure_ascii=False, sort_keys=True))
    estado = informe["veredicto"]["estado"]
    if estado in ("EQUIVALENTE", "EQUIVALENTE_CON_LIMITACIONES"):
        return 0
    if estado == "LIMITACION":
        return 3
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
