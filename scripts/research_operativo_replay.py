#!/usr/bin/env python
"""Reconstruccion OFFLINE de los resultados operativos de una corrida.

Reutiliza el adaptador y los motores existentes (``paper_lab_engine`` y
``backtest_offline``) sobre los archivos YA persistidos por el piloto:

- ``manifiesto.json``: configuracion operativa congelada y hashes de los
  ficheros necesarios. La configuracion es OBLIGATORIA: si falta, esta
  incompleta o es invalida NO se reconstruye nada (nunca valores por
  defecto silenciosos).
- ``observaciones.jsonl``: observaciones con su informacion disponible al
  decidir (seleccion, libro, flujo, decision_ms).
- ``consultas_klines.jsonl``: cuerpo REAL recibido en cada consulta de
  trayectoria, con parametros exactos, instantes, estado HTTP y hash. Cada
  consulta se acredita ANTES de usarse: identidad de corrida, observacion
  correspondiente, simbolo, intervalo, decision_ms, parametros exactos de
  la peticion y respuesta del ledger HTTP (el hash del cuerpo por si solo
  NO prueba que peticion lo produjo).
- ``funding_adquisicion.jsonl`` y ``funding/*.json``: liquidaciones de
  funding realmente observadas (metodo A) o calendario con cobertura (B).
- ``resultado_operativo.jsonl``: resultado de la ejecucion. Se COMPARA; no
  se usa como entrada de decision.

No abre red, no consulta a la venue, no crea cliente, motor, servicio ni base
de datos: solo lee lo persistido y reconstruye. Un fichero ausente, corrupto
o contradictorio produce una LIMITACION explicita: nunca un resultado
inventado y nunca un funding desconocido convertido en cero.

Comparacion por TIPO de campo: los timestamps en milisegundos, los
identificadores, las decisiones, los estados y los booleanos se comparan con
igualdad EXACTA (True nunca es 1, un desplazamiento de 1 ms ya es una
diferencia). La UNICA tolerancia es ABSOLUTA (1e-9 USDT) y se aplica
exclusivamente a los valores economicos decimales, para ruido de
representacion.

Veredictos (regla estricta, v2; ya no existe EQUIVALENTE_CON_LIMITACIONES):
- EQUIVALENTE (codigo 0): evidencia integra (hashes del manifiesto),
  procedencia de todas las consultas acreditada, configuracion operativa
  verificada, denominador completo y resultados identicos.
- LIMITACION (codigo 3): falta evidencia indispensable, esta corrupta o es
  contradictoria, hay consultas sin vinculo valido u observaciones sin
  correspondencia. Se publica QUE pudo reconstruirse y QUE no.
- DIFERENCIAS (codigo 4): evidencia valida y acreditada, pero los
  resultados difieren.

Uso:
    python scripts/research_operativo_replay.py --run-dir <dir> [--out <json>]
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

REPLAY_VERSION = "research-operativo-replay/v2"

# --- Comparacion por tipo de campo -----------------------------------------

# Timestamps en milisegundos: igualdad EXACTA de enteros.
CAMPOS_TIMESTAMP_MS = ("decision_ms", "entry_ms", "exit_ms")

# Identificadores, direcciones, decisiones y estados: igualdad EXACTA.
CAMPOS_EXACTOS = (
    "observation_id", "symbol", "role", "direction", "decision",
    "exit_reason", "funding_estado", "neto_estado", "neto_motivo",
    "contabilidad_funding_estado", "config_hash", "engine_version",
)

# Booleanos: igualdad exacta Y de tipo (True nunca equivale a 1).
CAMPOS_BOOLEANOS = ("exit_executed", "open_at_end")

# Valores economicos decimales: UNICA tolerancia, absoluta y justificada
# (1e-9 USDT ≈ ruido de representacion; muy por debajo de cualquier
# umbral economico). Nunca se aplica a los campos anteriores.
TOLERANCIA_ECONOMICA_ABS = 1e-9
CAMPOS_ECONOMICOS = (
    "entry_px", "stop_px", "exit_px", "qty", "gross_pnl", "fees",
    "spread_slip", "funding", "net_pnl",
)

CAMPOS_COMPARADOS = (CAMPOS_TIMESTAMP_MS + CAMPOS_EXACTOS
                     + CAMPOS_BOOLEANOS + CAMPOS_ECONOMICOS)

# --- Configuracion operativa: campos exigidos -------------------------------

CAMPOS_CONFIG_REQUERIDOS = (
    "version", "rule_version", "stop_distance_pct", "notional_usdt",
    "horizon_ms", "fee_bps", "spread_bps", "slippage_bps", "max_concurrent",
    "max_symbols", "max_candidates", "max_comparators",
    "funding_estimated_bps",
)
CAMPOS_CONFIG_ENTEROS = ("horizon_ms", "max_concurrent", "max_symbols",
                         "max_candidates", "max_comparators")
CAMPOS_CONFIG_DECIMALES = ("stop_distance_pct", "notional_usdt", "fee_bps",
                           "spread_bps", "slippage_bps")
CAMPOS_CONFIG_POSITIVOS = ("stop_distance_pct", "notional_usdt", "horizon_ms",
                           "max_concurrent")

# Ficheros cuya integridad comprueba el replay contra el manifiesto (los que
# consume; el resto de ficheros listados en el manifiesto no son necesarios).
FICHEROS_NECESARIOS = (
    "observaciones.jsonl", "resultado_operativo.jsonl",
    "http_requests.jsonl", "consultas_klines.jsonl",
    "funding_adquisicion.jsonl", "resumen.json",
)

# Limitaciones que IMPIDEN reconstruir o acreditar la fuente (reporte). Con
# la regla estricta CUALQUIER limitacion impide el codigo 0; esta
# clasificacion solo distingue, en el informe, lo reconstructivo de lo
# verificativo.
MOTIVOS_RECONSTRUCTIVOS = frozenset({
    "manifiesto_ausente",
    "manifiesto_corrupto",
    "config_operativa_ausente",
    "config_operativa_incompleta",
    "config_operativa_invalida",
    "config_hash_no_coincide",
    "integridad_fichero_rota",
    "integridad_no_publicada",
    "observaciones_ausentes",
    "observaciones_corruptas",
    "consultas_klines_ausentes",
    "consultas_klines_corruptas",
    "consulta_corrupta_hash",
    "consulta_cuerpo_ilegible",
    "consulta_sin_cuerpo",
    "consulta_run_id_distinto",
    "consulta_observacion_inexistente",
    "consulta_observacion_no_apta",
    "consulta_simbolo_distinto",
    "consulta_intervalo_distinto",
    "consulta_decision_ms_distinto",
    "consulta_parametros_distintos",
    "consulta_sin_vinculo_ledger",
    "consulta_discrepancia_ledger",
    "ledger_ausente",
    "ledger_corrupto",
    "funding_log_ausente",
    "funding_log_corrupto",
    "resumen_ausente_para_cierre",
    "resultados_ausentes",
    "resultados_corruptos",
    "resultado_sin_observacion_apta",
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


def _sha256_archivo(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Comparacion por tipo
# ---------------------------------------------------------------------------

def _igual_exacto(a: Any, b: Any) -> bool:
    """Igualdad exacta, sin confundir tipos (True nunca es 1)."""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    return a == b


def _iguales_por_tipo(campo: str, a: Any, b: Any) -> bool:
    """Compara un campo economico segun su tipo declarado.

    - Timestamps en ms: igualdad EXACTA de enteros (1 ms de diferencia ya
      es una diferencia; la tolerancia relativa de la v1 escondia
      desplazamientos de segundos).
    - Identificadores, decisiones y estados: igualdad EXACTA.
    - Booleanos: igualdad exacta y de tipo.
    - Valores economicos decimales: tolerancia absoluta 1e-9.
    """
    if a is None or b is None:
        return a is None and b is None
    if campo in CAMPOS_TIMESTAMP_MS:
        if isinstance(a, bool) or isinstance(b, bool):
            return False
        if not isinstance(a, int) or not isinstance(b, int):
            return False
        return a == b
    if campo in CAMPOS_BOOLEANOS:
        if not isinstance(a, bool) or not isinstance(b, bool):
            return False
        return a is b
    if campo in CAMPOS_ECONOMICOS:
        if isinstance(a, bool) or isinstance(b, bool):
            return False
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            return False
        return abs(float(a) - float(b)) <= TOLERANCIA_ECONOMICA_ABS
    return _igual_exacto(a, b)


def _params_iguales(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Igualdad EXACTA de los parametros de la peticion.

    Las claves deben coincidir en conjunto y los valores en valor (los
    numeros se comparan por valor para no distinguir 1 de 1.0 en JSON; un
    desplazamiento de startTime en 1 ms SI es distinto).
    """
    if set(a) != set(b):
        return False
    for k in a:
        va, vb = a[k], b[k]
        if isinstance(va, bool) or isinstance(vb, bool):
            if not _igual_exacto(va, vb):
                return False
            continue
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            if float(va) != float(vb):
                return False
            continue
        if not _igual_exacto(va, vb):
            return False
    return True


# ---------------------------------------------------------------------------
# Configuracion operativa OBLIGATORIA
# ---------------------------------------------------------------------------

def _config_operativa_validada(
    data: Optional[Dict[str, Any]],
) -> Tuple[Optional[OperativoConfig], Optional[str], List[Dict[str, Any]]]:
    """Valida la configuracion operativa persistida en el manifiesto.

    NUNCA sustituye un campo por su valor por defecto. Devuelve
    (config, hash_config, limitaciones); si hay limitaciones la
    configuracion NO se puede usar para reconstruir.
    """
    limitaciones: List[Dict[str, Any]] = []
    if data is None:
        return None, None, [{
            "motivo": "config_operativa_ausente",
            "detalle": ("el manifiesto no publica operativo_config: sin la "
                        "configuracion congelada no se puede reconstruir con "
                        "el mismo contrato y NO se usan valores por defecto"),
        }]
    if not isinstance(data, dict):
        return None, None, [{
            "motivo": "config_operativa_invalida",
            "detalle": "operativo_config no es un objeto JSON",
        }]
    faltan = [c for c in CAMPOS_CONFIG_REQUERIDOS if c not in data]
    if faltan:
        limitaciones.append({
            "motivo": "config_operativa_incompleta",
            "detalle": ("operativo_config no contiene campos necesarios: "
                        + ", ".join(sorted(faltan))),
            "campos_faltantes": sorted(faltan),
        })
    for campo in CAMPOS_CONFIG_ENTEROS:
        valor = data.get(campo)
        if isinstance(valor, bool) or not isinstance(valor, int):
            limitaciones.append({
                "motivo": "config_operativa_invalida",
                "detalle": f"{campo} no es un entero: {valor!r}",
            })
    for campo in CAMPOS_CONFIG_DECIMALES:
        valor = data.get(campo)
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            limitaciones.append({
                "motivo": "config_operativa_invalida",
                "detalle": f"{campo} no es numerico: {valor!r}",
            })
    for campo in CAMPOS_CONFIG_POSITIVOS:
        valor = data.get(campo)
        if (isinstance(valor, (int, float)) and not isinstance(valor, bool)
                and float(valor) <= 0):
            limitaciones.append({
                "motivo": "config_operativa_invalida",
                "detalle": f"{campo} debe ser positivo: {valor!r}",
            })
    for campo in ("version", "rule_version"):
        if not str(data.get(campo) or "").strip():
            limitaciones.append({
                "motivo": "config_operativa_invalida",
                "detalle": f"{campo} vacio o ausente",
            })
    valor_fe = data.get("funding_estimated_bps")
    if valor_fe is not None and (isinstance(valor_fe, bool)
                                 or not isinstance(valor_fe, (int, float))):
        limitaciones.append({
            "motivo": "config_operativa_invalida",
            "detalle": ("funding_estimated_bps debe ser numerico o null: "
                        f"{valor_fe!r}"),
        })
    if limitaciones:
        return None, None, limitaciones
    conocidos = {f.name for f in fields(OperativoConfig)}
    kwargs = {k: v for k, v in data.items() if k in conocidos}
    kwargs.pop("funding_calendar", None)
    try:
        cfg = OperativoConfig(**kwargs)
    except Exception as exc:  # configuracion no constructible
        return None, None, [{
            "motivo": "config_operativa_invalida",
            "detalle": f"no se puede construir la configuracion: {exc}",
        }]
    hash_cfg = hashlib.sha256(
        json.dumps(cfg.to_dict(), sort_keys=True, default=str)
        .encode("utf-8")).hexdigest()[:16]
    return cfg, hash_cfg, []


# ---------------------------------------------------------------------------
# Integridad de los ficheros necesarios contra el manifiesto
# ---------------------------------------------------------------------------

def _verificar_integridad(
    run_dir: Path, manifest: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Comprueba el sha256 real de cada fichero necesario con el publicado.

    Un fichero presente en disco pero sin hash publicado, o con un hash
    distinto del publicado, rompe la integridad acreditada de la corrida.
    """
    limitaciones: List[Dict[str, Any]] = []
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        limitaciones.append({
            "motivo": "integridad_no_publicada",
            "detalle": ("el manifiesto no publica hashes de ficheros: la "
                        "integridad de la evidencia no puede acreditarse"),
        })
        return limitaciones
    for nombre in FICHEROS_NECESARIOS:
        path = run_dir / nombre
        if not path.exists():
            continue  # la ausencia se reporta al intentar usar el fichero
        entrada = files.get(nombre)
        if not isinstance(entrada, dict) or not entrada.get("sha256"):
            limitaciones.append({
                "motivo": "integridad_no_publicada",
                "fichero": nombre,
                "detalle": ("el fichero necesario existe pero el manifiesto "
                            "no publica su hash"),
            })
            continue
        real = _sha256_archivo(path)
        if real != str(entrada["sha256"]):
            limitaciones.append({
                "motivo": "integridad_fichero_rota",
                "fichero": nombre,
                "detalle": ("el sha256 real del fichero no coincide con el "
                            "publicado en el manifiesto"),
                "sha_publicado": str(entrada["sha256"]),
                "sha_real": real,
            })
    return limitaciones


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


# ---------------------------------------------------------------------------
# Procedencia de las consultas persistidas
# ---------------------------------------------------------------------------

def _discrepancias_ledger(
    fila: Dict[str, Any], entrada: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Diferencias entre la consulta persistida y su fila del ledger HTTP."""
    discrepancias: List[Dict[str, Any]] = []
    params_fila = fila.get("params") or {}
    params_ledger = entrada.get("params") or {}
    if not _params_iguales(params_fila, params_ledger):
        discrepancias.append({"campo": "params",
                              "consulta": params_fila,
                              "ledger": params_ledger})
    pares = (
        ("endpoint", "endpoint"), ("symbol", "symbol"),
        ("interval", "interval"), ("http_status", "http_status"),
        ("solicitado_ms", "sent_at_ms"), ("adquirido_ms", "completed_at_ms"),
        ("cuerpo_bytes", "response_bytes"), ("filas", "response_item_count"),
    )
    for campo_fila, campo_ledger in pares:
        if not _igual_exacto(fila.get(campo_fila), entrada.get(campo_ledger)):
            discrepancias.append({
                "campo": campo_fila,
                "consulta": fila.get(campo_fila),
                "ledger": entrada.get(campo_ledger)})
    resultado = entrada.get("result")
    if resultado not in (None, "ok"):
        discrepancias.append({"campo": "result", "consulta": "ok",
                              "ledger": resultado})
    return discrepancias


def _cargar_consultas(
    path: Path,
    ledger: List[Dict[str, Any]],
    obs_aptas: Dict[str, Dict[str, Any]],
    obs_todas: Dict[str, Dict[str, Any]],
    run_id_manifestado: Optional[str],
    price_interval: Optional[str],
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]],
           Dict[str, List[str]], int]:
    """Lee los cuerpos persistidos y ACREDITA su procedencia antes de usarlos.

    Para cada consulta comprueba: cuerpo y hash; identidad de corrida
    (run_id del manifiesto); observacion correspondiente (existente y apta);
    simbolo e intervalo; decision_ms; parametros exactos de la peticion y
    cruce completo con la respuesta del ledger HTTP. El hash del cuerpo por
    si solo NO prueba que peticion lo produjo.

    Devuelve (consultas por observation_id, limitaciones, motivos por oid,
    total de consultas persistidas). Una consulta rechazada NO se usa para
    reconstruir su observacion.
    """
    limitaciones: List[Dict[str, Any]] = []
    rechazos: Dict[str, List[str]] = {}
    por_oid: Dict[str, List[Dict[str, Any]]] = {}
    total_consultas = 0
    if not path.exists():
        limitaciones.append({
            "motivo": "consultas_klines_ausentes",
            "detalle": "no existe el fichero de cuerpos de las consultas "
                       "klines: no hay trayectoria reconstructible",
        })
        return por_oid, limitaciones, rechazos, 0
    try:
        filas = leer_jsonl(path)
    except ArchivoCorrupto as exc:
        limitaciones.append({"motivo": "consultas_klines_corruptas",
                             "detalle": str(exc)})
        return por_oid, limitaciones, rechazos, 0
    # Vinculo con el ledger HTTP: hash de la respuesta producida.
    ledger_por_sha: Dict[str, List[Dict[str, Any]]] = {}
    for row in ledger:
        sha = row.get("response_sha256")
        if sha:
            ledger_por_sha.setdefault(str(sha), []).append(row)

    def rechazar(oid: str, motivo: str, detalle: str, **extra: Any) -> None:
        limitaciones.append({"motivo": motivo, "detalle": detalle,
                             "observation_id": oid, **extra})
        rechazos.setdefault(oid, []).append(motivo)

    for row in filas:
        if row.get("kind") != "consulta_klines_trayectoria":
            continue
        total_consultas += 1
        oid = str(row.get("observation_id"))
        cuerpo = row.get("cuerpo")
        sha = row.get("cuerpo_sha256")
        payload: Optional[List[Any]] = None
        # 1) Cuerpo y hash.
        if not isinstance(cuerpo, str) or not sha:
            rechazar(oid, "consulta_sin_cuerpo",
                     "consulta sin cuerpo o sin hash")
        else:
            real = hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()
            if real != str(sha):
                rechazar(oid, "consulta_corrupta_hash",
                         "el hash del cuerpo persistido no coincide",
                         cuerpo_sha256_declarado=sha,
                         cuerpo_sha256_calculado=real)
            try:
                cargado = json.loads(cuerpo)
            except ValueError as exc:
                rechazar(oid, "consulta_cuerpo_ilegible", str(exc))
            else:
                if isinstance(cargado, list):
                    payload = cargado
                else:
                    rechazar(oid, "consulta_cuerpo_ilegible",
                             "el cuerpo no es una lista de velas")
        # 2) Identidad de la corrida.
        if run_id_manifestado and not _igual_exacto(
                row.get("run_id"), run_id_manifestado):
            rechazar(oid, "consulta_run_id_distinto",
                     "el run_id de la consulta no es el de la corrida del "
                     "manifiesto",
                     run_id_consulta=row.get("run_id"),
                     run_id_manifiesto=run_id_manifestado)
        # 3) Observacion correspondiente, simbolo y decision_ms.
        obs_apt = obs_aptas.get(oid)
        obs_toda = obs_todas.get(oid)
        if obs_toda is None:
            rechazar(oid, "consulta_observacion_inexistente",
                     "la consulta no corresponde a ninguna observacion "
                     "persistida")
        elif obs_apt is None:
            rechazar(oid, "consulta_observacion_no_apta",
                     "la consulta corresponde a una observacion que no es "
                     "apta para evaluacion")
        else:
            if str(row.get("symbol") or "").upper() != str(
                    obs_toda.get("symbol") or "").upper():
                rechazar(oid, "consulta_simbolo_distinto",
                         "el simbolo de la consulta no es el de su "
                         "observacion",
                         simbolo_consulta=row.get("symbol"),
                         simbolo_observacion=obs_toda.get("symbol"))
            if not _igual_exacto(row.get("decision_ms"),
                                 obs_toda.get("decision_ms")):
                rechazar(oid, "consulta_decision_ms_distinto",
                         "el decision_ms de la consulta no es el de su "
                         "observacion",
                         decision_ms_consulta=row.get("decision_ms"),
                         decision_ms_observacion=obs_toda.get("decision_ms"))
        # 4) Intervalo de la corrida.
        if price_interval and not _igual_exacto(row.get("interval"),
                                               price_interval):
            rechazar(oid, "consulta_intervalo_distinto",
                     "el intervalo de la consulta no es el configurado en la "
                     "corrida",
                     intervalo_consulta=row.get("interval"),
                     intervalo_corrida=price_interval)
        # 5) Vinculo con el ledger HTTP: la misma peticion y respuesta.
        entradas = ledger_por_sha.get(str(sha or ""), [])
        if not entradas:
            rechazar(oid, "consulta_sin_vinculo_ledger",
                     "no hay ninguna fila del ledger HTTP con el hash de "
                     "esta respuesta: no se puede acreditar que peticion la "
                     "produjo")
        else:
            mejor: Optional[Dict[str, Any]] = None
            disc_mejor: List[Dict[str, Any]] = []
            for entrada in entradas:
                disc = _discrepancias_ledger(row, entrada)
                if mejor is None or len(disc) < len(disc_mejor):
                    mejor, disc_mejor = entrada, disc
                if not disc:
                    break
            if disc_mejor:
                for d in disc_mejor:
                    motivo = ("consulta_parametros_distintos"
                              if d["campo"] == "params"
                              else "consulta_discrepancia_ledger")
                    rechazar(
                        oid, motivo,
                        "la consulta difiere de su fila del ledger HTTP "
                        "(campo %s)" % d["campo"],
                        campo_ledger=d["campo"],
                        valor_consulta=d["consulta"],
                        valor_ledger=d["ledger"])
        if rechazos.get(oid):
            continue
        fila = dict(row)
        fila["_filas"] = payload or []
        por_oid.setdefault(oid, []).append(fila)
    for oid in por_oid:
        por_oid[oid].sort(key=lambda r: int(r.get("consulta_numero") or 0))
    return por_oid, limitaciones, rechazos, total_consultas


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------

def _replay(run_dir: Path) -> Dict[str, Any]:
    """Reconstruye la corrida desde lo persistido y compara con la ejecucion."""
    limitaciones: List[Dict[str, Any]] = []
    fuentes: Dict[str, Any] = {}

    # -- manifiesto (configuracion congelada + hashes) ------------------------
    manifest: Dict[str, Any] = {}
    manifest_ok = False
    manifest_path = run_dir / "manifiesto.json"
    if manifest_path.exists():
        try:
            manifest = leer_json(manifest_path)
            manifest_ok = True
        except ArchivoCorrupto as exc:
            limitaciones.append({"motivo": "manifiesto_corrupto",
                                 "detalle": str(exc)})
    else:
        limitaciones.append({
            "motivo": "manifiesto_ausente",
            "detalle": "sin manifiesto no hay configuracion operativa "
                       "congelada ni hashes de integridad",
        })
    config_piloto = manifest.get("config") or {}
    run_id_manifestado = (manifest.get("run_id")
                          or config_piloto.get("run_id"))
    funding_source = str(config_piloto.get("funding_source") or "none")
    funding_method = str(config_piloto.get("funding_method") or "")
    metodo_observado = (funding_source == "exchange"
                        and funding_method == "observed-settlements")

    # -- integridad de los ficheros necesarios --------------------------------
    if manifest_ok:
        limitaciones.extend(_verificar_integridad(run_dir, manifest))

    # -- observaciones --------------------------------------------------------
    obs_path = run_dir / "observaciones.jsonl"
    observaciones_todas: Dict[str, Dict[str, Any]] = {}
    observaciones: List[Dict[str, Any]] = []
    if obs_path.exists():
        try:
            filas = leer_jsonl(obs_path)
        except ArchivoCorrupto as exc:
            limitaciones.append({"motivo": "observaciones_corruptas",
                                 "detalle": str(exc)})
            filas = []
        for r in filas:
            if r.get("kind") == "observacion":
                observaciones_todas[str(r.get("observation_id"))] = r
        observaciones = [r for r in observaciones_todas.values()
                         if r.get("apto_para_evaluacion")]
    else:
        limitaciones.append({"motivo": "observaciones_ausentes",
                             "detalle": "no existe observaciones.jsonl"})
    obs_aptas = {str(o["observation_id"]): o for o in observaciones}
    fuentes["observaciones_aptas"] = len(observaciones)

    # -- configuracion operativa (OBLIGATORIA) --------------------------------
    operativo_cfg, hash_cfg, lim_config = _config_operativa_validada(
        manifest.get("operativo_config"))
    limitaciones.extend(lim_config)
    config_acreditada = not lim_config
    if not config_acreditada:
        # Sin configuracion acreditada NO se reconstruye nada: ni valores por
        # defecto ni reconstrucciones parciales con otro contrato.
        comparacion = [
            {"observation_id": oid, "estado": "limitada",
             "motivo": lim_config[0]["motivo"] if lim_config else
                       "config_operativa_invalida"}
            for oid in sorted(obs_aptas)
        ]
        return _informe(
            run_dir=run_dir, manifest=manifest, config_piloto=config_piloto,
            funding_method=funding_method, funding_source=funding_source,
            estado="LIMITACION", comparacion=comparacion,
            limitaciones=limitaciones, fuentes=fuentes,
            ejecucion={}, replay={}, consultas_acreditadas=0,
            consultas_persistidas=0, config_acreditada=False,
            procedencia_acreditada=False,
            aptas=len(obs_aptas), reconstruidas=0)

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
            "detalle": "sin ledger HTTP no se puede acreditar que peticion "
                       "produjo cada cuerpo",
        })
    fuentes["http_requests"] = len(ledger)

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
    # Resultados de la ejecucion sin observacion apta que los respalde.
    for oid in sorted(set(ejecucion) - set(obs_aptas)):
        detalle = ("la observacion no existe"
                   if oid not in observaciones_todas else
                   "la observacion no es apta para evaluacion")
        limitaciones.append({
            "motivo": "resultado_sin_observacion_apta",
            "detalle": detalle,
            "observation_id": oid,
        })
    # Coherencia de la configuracion con el hash publicado en la ejecucion.
    hashes_ejecucion = {str(r.get("config_hash"))
                        for r in ejecucion.values() if r.get("config_hash")}
    if hash_cfg and hashes_ejecucion and hashes_ejecucion != {hash_cfg}:
        limitaciones.append({
            "motivo": "config_hash_no_coincide",
            "detalle": ("el hash de la configuracion reconstruida no "
                        "coincide con el publicado en los resultados de la "
                        "ejecucion"),
            "hash_reconstruido": hash_cfg,
            "hash_ejecucion": sorted(hashes_ejecucion),
        })

    # -- consultas klines (cuerpos, con procedencia acreditada) ---------------
    consultas, lim_consultas, rechazos, consultas_persistidas = \
        _cargar_consultas(
            run_dir / "consultas_klines.jsonl", ledger, obs_aptas,
            observaciones_todas, run_id_manifestado,
            config_piloto.get("price_interval"))
    limitaciones.extend(lim_consultas)
    consultas_acreditadas = sum(len(v) for v in consultas.values())
    fuentes["consultas_klines"] = consultas_acreditadas
    fuentes["consultas_rechazadas"] = consultas_persistidas \
        - consultas_acreditadas
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
    elif metodo_observado:
        limitaciones.append({
            "motivo": "funding_log_ausente",
            "detalle": ("el metodo de funding observado exige el registro de "
                        "adquisiciones: sin el, la contabilidad diferida no "
                        "puede reconstruirse"),
        })
    fuentes["funding_adquisiciones"] = len(
        [r for r in funding_log if r.get("kind") == "funding_adquisicion"])

    # -- replay ---------------------------------------------------------------
    tmp_dir = Path(tempfile.mkdtemp(prefix="replay-operativo-"))
    adapter = OperativoAdapter(
        store_path=tmp_dir / "replay_resultado_operativo.jsonl",
        cfg=operativo_cfg,
    )
    resultados: Dict[str, Any] = {}
    velas_por_oid: Dict[str, List[PaperCandle]] = {}
    limitados: Dict[str, str] = {}
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
        if rechazos.get(oid):
            # Sin procedencia acreditada no se usa la fuente: la observacion
            # queda limitada y NO se reconstruye (no hay resultado inventado).
            limitados[oid] = rechazos[oid][0]
            continue
        consultas_oid = consultas.get(oid) or []
        if not consultas_oid:
            limitados[oid] = "sin_trayectoria_persistida"
            continue
        cal = cal_por_oid.get(oid) if not metodo_observado else None
        tr = None
        velas: List[PaperCandle] = []
        for consulta in consultas_oid:
            filas = consulta.get("_filas") or []
            if not filas:
                limitados[oid] = "sin_trayectoria_en_la_consulta"
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
            resumen: Dict[str, Any] = {}
            resumen_path = run_dir / "resumen.json"
            if resumen_path.exists():
                try:
                    resumen = leer_json(resumen_path)
                except ArchivoCorrupto as exc:
                    limitaciones.append({
                        "motivo": "resumen_ausente_para_cierre",
                        "detalle": ("resumen.json corrupto: el cierre de la "
                                    "espera contable no puede leerse "
                                    "(%s)" % exc),
                    })
            else:
                limitaciones.append({
                    "motivo": "resumen_ausente_para_cierre",
                    "detalle": ("resumen.json ausente: el cierre de la "
                                "espera contable no puede leerse"),
                })
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
    for oid in sorted(set(ejecucion) | set(replay) | set(obs_aptas)):
        if oid in limitados:
            comparacion.append({
                "observation_id": oid, "estado": "limitada",
                "motivo": limitados[oid], "motivos": rechazos.get(oid),
            })
            continue
        if oid not in obs_aptas:
            comparacion.append({
                "observation_id": oid, "estado": "limitada",
                "motivo": "resultado_sin_observacion_apta",
            })
            continue
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
            if not _iguales_por_tipo(campo, a, b):
                diferencias.append({"campo": campo, "ejecucion": a,
                                    "replay": b})
        comparacion.append({
            "observation_id": oid,
            "estado": "coincidente" if not diferencias else "diferente",
            "diferencias": diferencias,
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

    if limitaciones or n_lim:
        # Evidencia indispensable ausente, corrupta o contradictoria, o
        # observaciones sin procedencia acreditada: NO se declara
        # equivalencia. El informe publica que pudo reconstruirse y que no;
        # las diferencias observadas pueden ser consecuencia de la limitacion.
        estado = "LIMITACION"
    elif n_dif:
        estado = "DIFERENCIAS"
    else:
        estado = "EQUIVALENTE"

    return _informe(
        run_dir=run_dir, manifest=manifest, config_piloto=config_piloto,
        funding_method=funding_method, funding_source=funding_source,
        estado=estado, comparacion=comparacion, limitaciones=limitaciones,
        fuentes=fuentes, ejecucion=ejecucion, replay=replay,
        consultas_acreditadas=consultas_acreditadas,
        consultas_persistidas=consultas_persistidas,
        config_acreditada=config_acreditada,
        procedencia_acreditada=(not lim_consultas and bool(ledger)),
        aptas=len(obs_aptas), reconstruidas=len(replay))


def _informe(
    *,
    run_dir: Path,
    manifest: Dict[str, Any],
    config_piloto: Dict[str, Any],
    funding_method: str,
    funding_source: str,
    estado: str,
    comparacion: List[Dict[str, Any]],
    limitaciones: List[Dict[str, Any]],
    fuentes: Dict[str, Any],
    ejecucion: Dict[str, Dict[str, Any]],
    replay: Dict[str, Dict[str, Any]],
    consultas_acreditadas: int,
    consultas_persistidas: int,
    config_acreditada: bool,
    procedencia_acreditada: bool,
    aptas: int,
    reconstruidas: int,
) -> Dict[str, Any]:
    """Estructura del informe (unico formato de salida)."""
    n_coinc = sum(1 for c in comparacion if c["estado"] == "coincidente")
    n_dif = sum(1 for c in comparacion if c["estado"] == "diferente")
    n_lim = sum(1 for c in comparacion if c["estado"] == "limitada")
    reconstructivas = [l for l in limitaciones
                       if l.get("motivo") in MOTIVOS_RECONSTRUCTIVOS]
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
            "config_operativa_acreditada": bool(config_acreditada),
            "procedencia_acreditada": bool(procedencia_acreditada),
            "sin_red": True,
            "reutiliza_adaptador_y_motores_existentes": True,
        },
        "denominador": {
            "observaciones_aptas": aptas,
            "observaciones_reconstruidas": reconstruidas,
            "observaciones_limitadas": n_lim,
            "observaciones_comparadas": len(comparacion),
            "consultas_persistidas": consultas_persistidas,
            "consultas_acreditadas": consultas_acreditadas,
            "consultas_rechazadas": max(
                0, consultas_persistidas - consultas_acreditadas),
            "nota": ("el denominador NUNCA se reduce en silencio: toda "
                     "observacion apta aparece como coincidente, diferente "
                     "o limitada"),
        },
        "fuentes": fuentes,
        "limitaciones": limitaciones,
        "economia": {
            "operaciones_ejecucion": sum(
                1 for r in ejecucion.values()
                if r.get("decision") == "ENTRADA_EJECUTADA"),
            "operaciones_replay": sum(
                1 for r in replay.values()
                if r.get("decision") == "ENTRADA_EJECUTADA"),
            "neto_completo_ejecucion": sum(
                1 for r in ejecucion.values()
                if r.get("neto_estado") == "COMPLETO"),
            "neto_completo_replay": sum(
                1 for r in replay.values()
                if r.get("neto_estado") == "COMPLETO"),
            "neto_conditionado_ejecucion": sum(
                1 for r in ejecucion.values()
                if r.get("neto_estado")
                == "CONDICIONADO_SIN_FUNDING_COMPLETO"),
            "neto_conditionado_replay": sum(
                1 for r in replay.values()
                if r.get("neto_estado")
                == "CONDICIONADO_SIN_FUNDING_COMPLETO"),
            "neto_unknown_ejecucion": sum(
                1 for r in ejecucion.values()
                if r.get("neto_estado") == "UNKNOWN"),
            "neto_unknown_replay": sum(
                1 for r in replay.values()
                if r.get("neto_estado") == "UNKNOWN"),
        },
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
    if estado == "EQUIVALENTE":
        return 0
    if estado == "LIMITACION":
        return 3
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
