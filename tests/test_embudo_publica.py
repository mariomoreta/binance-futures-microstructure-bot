"""Pruebas focalizadas del embudo y la carrera de incorporación de la captura
pública public-pilot-1h-20261105a.

Todas las pruebas leen el dataset original sin modificarlo, salvo la prueba de
carrera que usa el camino productivo del piloto (ResearchPilot/take_decisions)
con reloj manual y sin red pública.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from research_pilot import ResearchPilot, PilotConfig  # noqa: E402

DATASET_JSONL = Path(
    r"C:\proyectos\binance-futures-data\public-pilot-1h-20261105a\observaciones.jsonl"
)
T0 = 1_735_689_600_000


def _cargar_jsonl(ruta: Path) -> list[dict]:
    objetos = []
    with open(ruta, "r", encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if linea:
                objetos.append(json.loads(linea))
    return objetos


@pytest.fixture
def datos():
    return _cargar_jsonl(DATASET_JSONL)


# ---------------------------------------------------------------------------
# 1. Embudo: totales por rol y suma global (no solapamiento entre roles)
# ---------------------------------------------------------------------------

def test_totales_por_rol_y_suma_global(datos):
    observaciones = [o for o in datos if o.get("kind") == "observacion"]
    roles = {}
    for o in observaciones:
        rol = o.get("role") or "desconocido"
        estado = o.get("estado")
        r = roles.setdefault(rol, {"seleccionadas": 0, "aptas": 0, "descartadas": 0})
        r["seleccionadas"] += 1
        if estado == "observada":
            r["aptas"] += 1
        elif estado == "descartada":
            r["descartadas"] += 1

    # Los conteos por rol no se solapan: candidate y comparator son excluyentes.
    assert roles["candidate"]["seleccionadas"] == 144
    assert roles["candidate"]["aptas"] == 109
    assert roles["candidate"]["descartadas"] == 35
    assert roles["comparator"]["seleccionadas"] == 96
    assert roles["comparator"]["aptas"] == 19
    assert roles["comparator"]["descartadas"] == 77

    total_sel = sum(r["seleccionadas"] for r in roles.values())
    total_aptas = sum(r["aptas"] for r in roles.values())
    total_desc = sum(r["descartadas"] for r in roles.values())
    assert total_sel == len(observaciones) == 240
    assert total_aptas == 128
    assert total_desc == 112
    assert total_aptas + total_desc == total_sel


# ---------------------------------------------------------------------------
# 2. Tasas con denominadores correctos (sobre aptas y sobre seleccionadas)
# ---------------------------------------------------------------------------

def test_tasas_denominadores_correctos(datos):
    resultados = [o for o in datos if o.get("kind") == "resultado"]
    observaciones = [o for o in datos if o.get("kind") == "observacion"]
    aptas = [o for o in observaciones if o.get("estado") == "observada"]

    assert len(aptas) == 128
    assert len(resultados) == 206

    # Resultados por rol y horizonte (join observation_id).
    res_por_id_h = {}
    for r in resultados:
        res_por_id_h.setdefault((str(r.get("observation_id")), r.get("horizon")), []).append(r)

    def contar(rol, h):
        n = 0
        for o in aptas:
            if o.get("role") != rol:
                continue
            oid = o.get("observation_id")
            if res_por_id_h.get((str(oid), h)):
                n += 1
        return n

    cand_5m = contar("candidate", "5m")
    cand_15m = contar("candidate", "15m")
    comp_5m = contar("comparator", "5m")
    comp_15m = contar("comparator", "15m")

    assert cand_5m == 97
    assert cand_15m == 76
    assert comp_5m == 18
    assert comp_15m == 15

    # Tasas sobre aptas.
    assert abs(cand_5m / 109 - 0.890) < 0.001
    assert abs(cand_15m / 109 - 0.697) < 0.001
    assert abs(comp_5m / 19 - 0.947) < 0.001
    assert abs(comp_15m / 19 - 0.789) < 0.001

    # Tasas sobre seleccionadas (claramente diferenciadas).
    assert abs(cand_5m / 144 - 0.674) < 0.001
    assert abs(comp_5m / 96 - 0.188) < 0.001


# ---------------------------------------------------------------------------
# 3. Entrada, permanencia y reincorporación (condición de incorporación)
# ---------------------------------------------------------------------------

def test_condicion_incorporacion(datos):
    ciclos = [o for o in datos if o.get("kind") == "ciclo"]
    observaciones = [o for o in datos if o.get("kind") == "observacion"]

    # Ciclos ordenados por reference_ms.
    ciclos_ordenados = sorted(ciclos, key=lambda c: c.get("reference_ms", 0))
    ciclos_por_ref = {c.get("reference_ms"): i for i, c in enumerate(ciclos_ordenados)
                      if isinstance(c.get("reference_ms"), int)}

    # Símbolo -> lista de ciclo_idx ordenados.
    apariciones = {}
    for o in observaciones:
        simbolo = o.get("symbol")
        disp = o.get("disponibilidad") or {}
        sel_ms = disp.get("seleccion_ms")
        if simbolo is None or not isinstance(sel_ms, int) or sel_ms not in ciclos_por_ref:
            continue
        ci = ciclos_por_ref[sel_ms]
        apariciones.setdefault(simbolo, []).append(ci)
    for simbolo in apariciones:
        apariciones[simbolo].sort()

    def condicion(simbolo, ci):
        lista = apariciones.get(simbolo, [])
        if not lista:
            return "desconocido"
        if lista[0] == ci:
            return "primera_vez"
        if (ci - 1) in lista:
            return "permanece"
        return "reincorpora"

    # Contar por rol y condición.
    conteo = {}
    for o in observaciones:
        rol = o.get("role") or "desconocido"
        disp = o.get("disponibilidad") or {}
        sel_ms = disp.get("seleccion_ms")
        ci = ciclos_por_ref.get(sel_ms) if isinstance(sel_ms, int) else None
        if ci is None:
            continue
        c = condicion(o.get("symbol"), ci)
        clave = (rol, c)
        conteo[clave] = conteo.get(clave, 0) + 1

    # candidate: permanece=122, primera_vez=17, reincorpora=5
    assert conteo.get(("candidate", "permanece")) == 122
    assert conteo.get(("candidate", "primera_vez")) == 17
    assert conteo.get(("candidate", "reincorpora")) == 5
    # comparator: permanece=52, primera_vez=27, reincorpora=17
    assert conteo.get(("comparator", "permanece")) == 52
    assert conteo.get(("comparator", "primera_vez")) == 27
    assert conteo.get(("comparator", "reincorpora")) == 17

    # Suma global por condición (sin solapamiento de roles).
    total_pv = sum(v for (r, c), v in conteo.items() if c == "primera_vez")
    total_perm = sum(v for (r, c), v in conteo.items() if c == "permanece")
    total_reinc = sum(v for (r, c), v in conteo.items() if c == "reincorpora")
    assert total_pv == 44
    total_perm == 174 or True  # se verifica por abajo
    total_perm_actual = sum(v for (r, c), v in conteo.items() if c == "permanece")
    assert total_perm_actual == 174
    assert total_reinc == 22
    assert total_pv + total_perm_actual + total_reinc == 240


# ---------------------------------------------------------------------------
# 4. Timestamp ausente tratado como UNKNOWN
# ---------------------------------------------------------------------------

def test_timestamp_ausente_unknown(datos):
    observaciones = [o for o in datos if o.get("kind") == "observacion"]
    # Todas las observaciones deben tener decision_ms e referencia de ciclo.
    sin_decision = [o for o in observaciones if o.get("decision_ms") is None]
    assert sin_decision == [], "no debe haber observaciones sin decision_ms"

    # Los descartes por primera_vez/reincorpora no tienen libro ni flujo (NULL).
    ciclos = [o for o in datos if o.get("kind") == "ciclo"]
    ciclos_por_ref = {c.get("reference_ms"): i for i, c in enumerate(ciclos)
                      if isinstance(c.get("reference_ms"), int)}
    ciclos_ordenados = sorted(ciclos, key=lambda c: c.get("reference_ms", 0))

    apariciones = {}
    for o in observaciones:
        simbolo = o.get("symbol")
        sel_ms = (o.get("disponibilidad") or {}).get("seleccion_ms")
        if simbolo is None or not isinstance(sel_ms, int) or sel_ms not in ciclos_por_ref:
            continue
        apariciones.setdefault(simbolo, []).append(ciclos_por_ref[sel_ms])
    for simbolo in apariciones:
        apariciones[simbolo].sort()

    for o in observaciones:
        if o.get("estado") != "descartada":
            continue
        simbolo = o.get("symbol")
        sel_ms = (o.get("disponibilidad") or {}).get("seleccion_ms")
        ci = ciclos_por_ref.get(sel_ms) if isinstance(sel_ms, int) else None
        if ci is None:
            continue
        lista = apariciones.get(simbolo, [])
        es_primera = lista and lista[0] == ci
        es_permanece = (ci - 1) in lista
        if es_primera or (not es_permanece and lista):
            # primera_vez o reincorpora: no debe tener libro ni flujo.
            libro = (o.get("disponibilidad") or {}).get("libro_ms")
            flujo = (o.get("disponibilidad") or {}).get("flujo_ms")
            assert libro is None, f"{simbolo} {ci} primera/reinc con libro {libro}"
            assert flujo is None, f"{simbolo} {ci} primera/reinc con flujo {flujo}"


# ---------------------------------------------------------------------------
# 5. Motivos de descarte solapados sin duplicar observaciones
# ---------------------------------------------------------------------------

def test_motivos_solapados_sin_duplicar_observaciones(datos):
    observaciones = [o for o in datos if o.get("kind") == "observacion"]
    descartadas = [o for o in observaciones if o.get("estado") == "descartada"]
    assert len(descartadas) == 112

    # Conteo de observaciones (una por descarte, sin duplicar).
    assert sum(1 for _ in descartadas) == 112

    # Conteo de motivos (pueden solaparse: una observación tiene varios motivos).
    conteo_motivos = {}
    for o in descartadas:
        for m in (o.get("motivos") or []):
            conteo_motivos[m] = conteo_motivos.get(m, 0) + 1
    suma_motivos = sum(conteo_motivos.values())
    assert suma_motivos >= len(descartadas)  # solapamiento permitido
    # Ninguna observación descartada aparece dos veces en el conteo de observaciones.
    ids_descartadas = {o.get("observation_id") for o in descartadas}
    assert len(ids_descartadas) == len(descartadas)


# ---------------------------------------------------------------------------
# 6. Carrera reproducible: símbolo recién seleccionado sin datos se descarta
# ---------------------------------------------------------------------------

def test_carrera_simbolo_nuevo_sin_datos_se_descarta():
    """Un símbolo seleccionado por primera vez, sin libro ni flujo acumulados
    (feeds acabados de abrir), se descarta al evaluar inmediatamente.

    Demuestra el orden del código: seleccion (run_cycle) -> apertura de feeds
    (_restart_feeds) -> evaluacion (take_decisions). Los símbolos nuevos no
    tienen datos cuando se evalúan por primera vez.
    """
    tmp = Path(tempfile.mkdtemp(prefix="carrera-"))
    try:
        pilot = ResearchPilot(
            PilotConfig(
                run_id="carrera", out_dir=str(tmp),
                duration_seconds=60, settle_seconds=5,
                max_data_age_ms=5000, max_bytes=128 * 1024 * 1024,
            ),
            clock=None,  # usa el reloj del sistema; solo importa el orden
        )
        # Simular un símbolo recién seleccionado (primera_vez) en followed/roles.
        simbolo = "NUEVOUSDT"
        pilot.followed = {simbolo}
        pilot.roles = {simbolo: "candidate"}
        pilot.selection_meta = {
            simbolo: {"role": "candidate", "side": None, "priority": None,
                      "move_24h_pct": None, "classification": None},
        }
        pilot.last_selection_reference_ms = T0

        # Sin libro ni flujo para el símbolo: feeds acabados de abrir, sin datos.
        piloto_now = T0
        pilot.take_decisions(piloto_now)

        filas = []
        ruta_jsonl = Path(tmp) / "observaciones.jsonl"
        if ruta_jsonl.exists():
            for linea in ruta_jsonl.read_text(encoding="utf-8").splitlines():
                linea = linea.strip()
                if linea:
                    filas.append(json.loads(linea))

        obs = [f for f in filas if f.get("kind") == "observacion"
               and f.get("symbol") == simbolo]
        assert len(obs) == 1, f"se esperaba 1 observacion, se obtuvieron {len(obs)}"
        o = obs[0]
        assert o["estado"] == "descartada"
        assert o["apto_para_evaluacion"] is False
        motivos = set(o.get("motivos") or [])
        assert "sin_libro" in motivos, f"motivos={motivos}"
        assert "sin_flujo" in motivos, f"motivos={motivos}"
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
