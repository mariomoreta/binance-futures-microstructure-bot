"""Aceptacion local de la via A: espera contable con liquidaciones observadas.

Ejecuta ``scripts/research_pilot.py`` como subproceso real (CLI, no
adaptador externo) con proveedores HTTP/WS loopback, reloj controlado y
almacenamiento temporal aislado. El modo publico no se abre: el proveedor es
loopback y la venue simulada publica cada liquidacion SOLO cuando ya ha
ocurrido, de modo que una liquidacion futura no puede inventarse.

Demuestra:
A. La captura termina y los feeds se cierran.
B. Una operacion sale segun su regla aunque su funding siga pendiente.
C. La liquidacion posterior todavia no disponible no se inventa.
D. Al aparecer evidencia suficiente, el mismo recorrido completa la contabilidad.
E. Un pago posterior a la salida no se cobra a la posicion.
F. Cobertura insuficiente o vencimiento de espera -> UNKNOWN con motivo.
G. Parada del operador -> conservacion de pendientes y limpieza.
H. Proveedor, gate y planificacion presupuestaria son coherentes.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

import tests.test_research_pilot as tr  # noqa: E402
import research_pilot as rp  # noqa: E402
from tests.test_research_pilot import base_price, kline_price  # noqa: E402

CADENCIA_MS = 8 * 3_600_000
# Configuracion congelada de la primera ventana (EXPERIMENTO_OPERATIVO_V2).
CAPTURA_S = 3_600
SETTLE_S = 4_200
ESPERA_S = 32_400
MAX_CONSULTAS_ESPERA = 3


def _venue(anchor_ms: int, *, published: bool = True):
    """Venue simulada: liquidaciones cada 8 h, publicadas al ocurrir.

    ``published=False`` simula una venue que no publica (la liquidacion
    posterior a la salida no llega nunca dentro del plazo).
    """
    def _rows(symbol: str, start: int, end: int, now: Any) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for k in range(-20, 21):
            instante = anchor_ms + k * CADENCIA_MS
            if instante < start or instante > end:
                continue
            if published and now is not None and instante > now:
                continue
            rows.append({
                "symbol": symbol,
                "fundingTime": instante,
                "fundingRate": "0.0001",
                "markPrice": str(base_price(symbol)),
                "rateType": "Regular",
            })
        return rows
    return _rows


def _leer_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _ops(path: Path) -> List[Dict[str, Any]]:
    return [r for r in _leer_jsonl(path)
            if r.get("kind") == "resultado_operativo"]


def _esperar(predicado, que: str, timeout: float = 60.0):
    deadline = time.monotonic() + timeout
    ultimo = None
    while time.monotonic() < deadline:
        ultimo = predicado()
        if ultimo:
            return ultimo
        time.sleep(0.02)
    raise AssertionError(f"timeout {timeout}s esperando {que}; ultimo={ultimo!r}")


def _preparar_corte(run: tr.PilotRun, universo, e0: int) -> None:
    """Publica el corte de decision y deja una observacion apta."""
    run.wait_ready(expected_followed=len(universo))
    seed = list(range(e0 - 62_000, e0 + 1, 1_000))
    run.step(
        e0,
        depth_symbols=universo,
        trade_events={s: seed for s in universo},
        evaluate=True,
        expected_obs=len(universo),
    )


def _pilot(tmp: Path, universo, *, funding_rows_fn, espera_s: int = ESPERA_S,
           max_consultas: int = MAX_CONSULTAS_ESPERA):
    return tr.PilotRun(
        tmp,
        universe=universo,
        duration_s=CAPTURA_S,
        settle_s=SETTLE_S,
        selection_s=300,
        max_symbols=len(universo),
        cycle_s=300,
        horizons=tr.HORIZONS,
        max_http_attempts=2000,
        funding_source="exchange",
        funding_method="observed-settlements",
        funding_wait_seconds=espera_s,
        funding_wait_max_queries=max_consultas,
        funding_rows_fn=funding_rows_fn,
    )


def test_espera_contable_completa_la_contabilidad_con_liquidaciones_observadas():
    """A-H: la salida se decide antes que el funding; la contabilidad A-H."""
    tmp = Path(tempfile.mkdtemp(prefix="cli-espera-contable-"))
    ok = False
    universo = [tr.UNIVERSE[0]]
    e0 = tr.T0 + tr.MINUTE
    # Ancla de la cadencia: una liquidacion DENTRO de la exposicion y la
    # siguiente DESPUES de la salida (esa segunda es la que aporta cobertura
    # y NO puede cobrarse a la posicion).
    ancla = e0 + 1_800_000
    liquidacion_en_exposicion = ancla
    liquidacion_tras_salida = ancla + CADENCIA_MS
    entrada_prevista = e0 + tr.MINUTE
    salida_prevista = entrada_prevista + 3_600_000
    assert entrada_prevista < liquidacion_en_exposicion < salida_prevista
    assert liquidacion_tras_salida > salida_prevista

    run = _pilot(tmp, universo, funding_rows_fn=_venue(ancla))
    op_path = run.out_dir / "resultado_operativo.jsonl"
    try:
        _preparar_corte(run, universo, e0)

        # --- A: la captura termina y los feeds se cierran -----------------
        capture_end = run.status()["capture_end_ms"]
        run.advance(capture_end)
        estado = run.status()
        assert estado["phase"] == "settle", estado
        assert all(not f.get("connected_now")
                   for f in (estado.get("feeds") or {}).values()), estado

        # --- B: la operacion sale por su regla con el funding pendiente ---
        instante_salida = salida_prevista + tr.MINUTE * 2
        run.advance(instante_salida)
        primera = _esperar(
            lambda: next((r for r in _ops(op_path)
                          if r.get("contabilidad_funding_estado") == "PENDIENTE"),
                         None),
            "fila operativa con contabilidad de funding pendiente")
        assert primera["decision"] == "ENTRADA_EJECUTADA", primera
        assert primera["exit_executed"] is True, primera
        assert primera["exit_reason"] == "horizon", primera
        assert primera["exit_ms"] == salida_prevista, primera
        assert primera["entry_ms"] == entrada_prevista, primera
        # El funding sigue pendiente: no se inventa ninguna liquidacion.
        assert primera["funding"] is None, primera
        assert primera["neto_estado"] == "CONDICIONADO_SIN_FUNDING_COMPLETO", primera

        # --- C: la liquidacion posterior todavia no esta publicada --------
        # La espera contable arranca al cerrar el settle. La venue solo
        # publica lo ya ocurrido: en la primera consulta la liquidacion
        # posterior a la salida todavia no existe.
        settle_end = run.status()["settle_end_ms"]
        run.advance(settle_end)
        _esperar(lambda: run.http.funding_calls >= 1,
                 "primera consulta de funding diferida")
        assert run.http.funding_calls >= 1, run.http.funding_calls
        diagnostico = _esperar(
            lambda: next((r for r in _ops(op_path)
                          if r.get("funding_sin_cubrir_ms") is not None
                          and r.get("funding_sin_cubrir_ms", 0) > 0), None),
            "diagnostico de cola sin cubrir")
        assert diagnostico["funding"] is None, diagnostico
        assert diagnostico["contabilidad_funding_estado"] == "PENDIENTE", diagnostico
        assert diagnostico["funding_sin_cubrir_ms"] > 0, diagnostico

        # --- D: al aparecer la evidencia, el mismo recorrido completa ------
        # La consulta se programa con la cadencia OBSERVADA (8 h) mas el
        # margen de publicacion: no se sondea en cada tick.
        instante_consulta = liquidacion_tras_salida + 1_800_000
        run.advance(instante_consulta)
        final = _esperar(
            lambda: next((r for r in _ops(op_path)
                          if r.get("contabilidad_funding_estado") == "ACREDITADA"),
                         None),
            "contabilidad de funding acreditada")
        assert final["funding"] is not None, final
        assert final["neto_estado"] == "COMPLETO", final
        assert final.get("funding_cuenta_completa") is True, final
        assert final.get("funding_sin_cubrir_ms") == 0, final
        assert final.get("funding_huecos_ms") == 0, final

        # --- E: el pago posterior a la salida NO se cobra ------------------
        # Solo se contabiliza la liquidacion dentro de [entry_ms, exit_ms).
        marca = kline_price(final["symbol"], liquidacion_en_exposicion)
        esperado = float(final["qty"]) * marca * 1.0 / 10_000.0
        assert abs(float(final["funding"]) - esperado) < 1e-9, (
            final["funding"], esperado)
        eventos = final.get("funding_liquidaciones") or []
        assert eventos, final
        liquidaciones_cobradas = [
            e for e in eventos if e.get("basis") == "settled"]
        assert len(liquidaciones_cobradas) == 1, eventos
        assert liquidaciones_cobradas[0]["settlement_ms"] == (
            liquidacion_en_exposicion), eventos
        assert all(e.get("settlement_ms", 0) < final["exit_ms"]
                   for e in liquidaciones_cobradas), eventos
        # La liquidacion posterior a la salida aparece en el calendario
        # observado (aporta cobertura) pero no se cobra a la posicion.
        calendario = json.loads(
            (run.out_dir / "funding" /
             f"{universo[0].upper()}--espera-contable.json").read_text(
                 encoding="utf-8"))
        instantes = {s["settlement_ms"]
                     for s in calendario["settlements"]}
        assert liquidacion_tras_salida in instantes, instantes
        assert liquidacion_tras_salida not in {
            e.get("settlement_ms") for e in eventos}, eventos

        # --- H: proveedor, gate y planificacion presupuestaria ------------
        log_funding = _leer_jsonl(run.out_dir / "funding_adquisicion.jsonl")
        assert log_funding, "sin registro de adquisicion de funding"
        for row in log_funding:
            assert row.get("scope") == "simbolo", row
            assert row.get("funding_metodo") == "observed-settlements", row
            assert row.get("estado") == "OK", row
            assert row.get("calendar_file"), row
            assert row.get("calendar", {}).get("provenance", {}).get(
                "response_sha256"), row

        rc = run.wait_exit()
        assert rc == 0, (rc, run.stdout, run.stderr)
        # El ledger HTTP se reconstruye al cierre: las consultas diferidas
        # quedan con sus parametros, su estado y su hash de respuesta.
        ledger = _leer_jsonl(run.out_dir / "http_requests.jsonl")
        consultas_funding = [
            r for r in ledger if "/fapi/v1/fundingRate" in (r.get("endpoint") or "")]
        assert len(consultas_funding) >= 2, consultas_funding
        for row in consultas_funding:
            assert row.get("result") == "ok", row
            assert row.get("http_status") == 200, row
            assert row.get("response_sha256"), row
            params = row.get("params") or {}
            assert params.get("symbol") == universo[0].upper(), row
            assert isinstance(params.get("startTime"), int), row
            assert isinstance(params.get("endTime"), int), row
        # La consulta se difiere: no se sondea en cada tick.
        assert len(consultas_funding) <= MAX_CONSULTAS_ESPERA, consultas_funding
        resumen = json.loads((run.out_dir / "resumen.json").read_text(
            encoding="utf-8"))
        espera = resumen["espera_contable"]
        assert espera["metodo"] == "observed-settlements", espera
        assert espera["cierre"] == "trabajo_resuelto", espera
        assert espera["posiciones_acreditadas"] >= 1, espera
        assert espera["posiciones_unknown"] == 0, espera
        assert espera["pendientes_finales"] == 0, espera
        assert espera["consultas_totales"] >= 2, espera
        assert resumen["presupuesto_http"]["blocked"] is False, resumen
        # Una sola corrida: un solo run_id y un solo presupuesto acumulado.
        assert resumen["run_id"] == "pilot-sync", resumen
        assert resumen["presupuesto_plan"]["funding"]["metodo"] == (
            "observed-settlements"), resumen
        print(f"  [espera contable] consultas={espera['consultas_totales']} "
              f"creditadas={espera['posiciones_acreditadas']} "
              f"unknown={espera['posiciones_unknown']} "
              f"funding={final['funding']}")
        ok = True
    finally:
        run.shutdown()
        if ok:
            shutil.rmtree(tmp, ignore_errors=True)


def _esperar_espera_iniciada(run: tr.PilotRun) -> Dict[str, Any]:
    """Espera a que la fase de espera contable este activa."""
    return _esperar(
        lambda: (lambda s: s if s.get("espera_contable_inicio_ms") else None)(
            run.status() or {}),
        "inicio de la espera contable")


def test_vencimiento_de_la_espera_deja_funding_unknown_con_motivo():
    """F: si la liquidacion no llega, el plazo vence y el funding queda UNKNOWN."""
    tmp = Path(tempfile.mkdtemp(prefix="cli-espera-vencimiento-"))
    ok = False
    universo = [tr.UNIVERSE[0]]
    e0 = tr.T0 + tr.MINUTE
    ancla = e0 + 1_800_000
    run = _pilot(tmp, universo, funding_rows_fn=_venue(ancla),
                 espera_s=1_800, max_consultas=2)
    op_path = run.out_dir / "resultado_operativo.jsonl"
    try:
        _preparar_corte(run, universo, e0)
        capture_end = run.status()["capture_end_ms"]
        run.advance(capture_end)
        run.advance(e0 + 3_600_000 + tr.MINUTE * 3)
        _esperar(lambda: next((r for r in _ops(op_path)
                               if r.get("contabilidad_funding_estado")
                               == "PENDIENTE"), None),
                 "fila operativa pendiente")
        # El plazo de espera vence: no hay prorroga.
        settle_end = run.status()["settle_end_ms"]
        run.advance(settle_end)
        estado = _esperar_espera_iniciada(run)
        fin_espera = int(estado["espera_contable_fin_ms"])
        run.advance(fin_espera + 1_000)
        cerrada = _esperar(
            lambda: next((r for r in _ops(op_path)
                          if r.get("contabilidad_funding_estado") == "UNKNOWN"),
                         None),
            "cierre por vencimiento de la espera")
        assert cerrada["funding"] is None, cerrada
        assert cerrada["neto_estado"] == "CONDICIONADO_SIN_FUNDING_COMPLETO", cerrada
        assert "plazo" in (cerrada.get("contabilidad_funding_motivo") or ""), cerrada
        rc = run.wait_exit()
        assert rc == 0, (rc, run.stdout, run.stderr)
        resumen = json.loads((run.out_dir / "resumen.json").read_text(
            encoding="utf-8"))
        espera = resumen["espera_contable"]
        assert espera["cierre"] == "plazo_maximo_de_espera_agotado", espera
        assert espera["posiciones_unknown"] >= 1, espera
        assert espera["pendientes_finales"] == 0, espera
        # La cobertura insuficiente se publica con su diagnostico canonico.
        assert cerrada.get("funding_cuenta_completa") is False, cerrada
        ok = True
    finally:
        run.shutdown()
        if ok:
            shutil.rmtree(tmp, ignore_errors=True)


def _cfg_publica_ventana_1(*extra: str):
    args = [
        "--mode", "local",
        "--duration-seconds", str(CAPTURA_S),
        "--settle-seconds", str(SETTLE_S),
        "--cycle-seconds", "300",
        "--selection-seconds", "300",
        "--max-symbols", "20",
        "--max-candidates", "12",
        "--max-comparators", "8",
        "--funding-source", "exchange",
        "--funding-method", "observed-settlements",
        "--funding-wait-seconds", str(ESPERA_S),
    ]
    args.extend(extra)
    return rp.config_from_args(rp.build_parser().parse_args(args))


def test_la_via_a_falla_cerrada_sin_espera_o_sin_fuente_real():
    """La eleccion de metodo es explicita: sin espera o sin fuente no hay via A."""
    with pytest.raises(ValueError) as ctx:
        rp.config_from_args(rp.build_parser().parse_args([
            "--mode", "local", "--funding-source", "exchange",
            "--funding-method", "observed-settlements"]))
    assert "funding-wait-seconds" in str(ctx.value), ctx.value

    with pytest.raises(ValueError) as ctx:
        rp.config_from_args(rp.build_parser().parse_args([
            "--mode", "local", "--funding-method", "observed-settlements",
            "--funding-wait-seconds", str(ESPERA_S)]))
    assert "funding-source exchange" in str(ctx.value), ctx.value

    # El plazo y las consultas no se pueden ampliar sobre el protocolo.
    with pytest.raises(ValueError) as ctx:
        _cfg_publica_ventana_1("--funding-wait-seconds",
                               str(rp.FUNDING_ESPERA_MAX_SEGUNDOS + 1))
    assert "plazo maximo" in str(ctx.value), ctx.value

    with pytest.raises(ValueError) as ctx:
        _cfg_publica_ventana_1("--funding-wait-max-queries",
                               str(rp.MAX_CONSULTAS_FUNDING_ESPERA_POR_SIMBOLO + 1))
    assert "tope del protocolo" in str(ctx.value), ctx.value


def test_presupuesto_de_la_via_a_cierra_dentro_de_los_techos():
    """H: la planificacion presupuestaria de la via A cabe en los topes."""
    cfg = _cfg_publica_ventana_1()
    plan = rp.compute_budget(cfg)
    funding = plan["funding"]
    assert funding["metodo"] == "observed-settlements", funding
    # Una consulta diferida por simbolo con posicion abierta, mas las
    # repetidas reservadas (3 consultas por simbolo como maximo).
    assert funding["consultas_base_ventana"] == 20, funding
    assert funding["consultas_repetidas_reserva"] == 40, funding
    assert funding["intentos_totales_reservados"] == 110, funding
    assert funding["espera_contable_max_s"] == ESPERA_S, funding
    assert funding["maximo_concentrado_5m_planificado"] <= \
        rp.FUNDING_RATE_SHARED_LIMIT_5M, funding
    supuestos = plan["supuestos"]
    assert supuestos["duracion_captura_s"] == CAPTURA_S, supuestos
    assert supuestos["periodo_settle_s"] == SETTLE_S, supuestos
    assert supuestos["espera_contable_max_s"] == ESPERA_S, supuestos
    assert supuestos["duracion_maxima_total_s"] == (
        CAPTURA_S + SETTLE_S + ESPERA_S), supuestos
    rest = plan["rest"]
    assert rest["intentos_base_mas_reservas"] <= rp.PROTOCOL_MAX_HTTP_ATTEMPTS, rest
    assert rest["peso_base_mas_reservas_max"] <= rp.PROTOCOL_MAX_HTTP_WEIGHT, rest
    assert plan["almacenamiento"]["total_bytes_previstos"] <= \
        rp.PROTOCOL_MAX_STORAGE_BYTES, plan["almacenamiento"]


def test_parada_del_operador_conserva_el_pendiente_y_limpia():
    """G: una parada explicita conserva el pendiente con su causa real."""
    tmp = Path(tempfile.mkdtemp(prefix="cli-espera-parada-"))
    ok = False
    universo = [tr.UNIVERSE[0]]
    e0 = tr.T0 + tr.MINUTE
    ancla = e0 + 1_800_000
    run = _pilot(tmp, universo, funding_rows_fn=_venue(ancla))
    op_path = run.out_dir / "resultado_operativo.jsonl"
    try:
        _preparar_corte(run, universo, e0)
        capture_end = run.status()["capture_end_ms"]
        run.advance(capture_end)
        run.advance(e0 + 3_600_000 + tr.MINUTE * 3)
        _esperar(lambda: next((r for r in _ops(op_path)
                               if r.get("contabilidad_funding_estado")
                               == "PENDIENTE"), None),
                 "fila operativa pendiente")
        # Parada del operador durante la espera contable.
        settle_end = run.status()["settle_end_ms"]
        run.advance(settle_end)
        _esperar_espera_iniciada(run)
        run.stop_path.write_text("parada\n", encoding="utf-8")
        rc = run.wait_exit()
        assert rc == 0, (rc, run.stdout, run.stderr)
        pendientes = [r for r in _ops(op_path)
                      if r.get("contabilidad_funding_estado") == "PENDIENTE"]
        assert pendientes, _ops(op_path)
        ultima = pendientes[-1]
        assert "parada_operador" in (
            ultima.get("contabilidad_funding_motivo") or ""), ultima
        assert ultima["funding"] is None, ultima
        # Limpieza: el cierre auditable se escribe desde lo persistido.
        resumen = json.loads((run.out_dir / "resumen.json").read_text(
            encoding="utf-8"))
        assert resumen["stop_reason"] == "parada_operador", resumen
        assert resumen["espera_contable"]["cierre"] == "parada_operador", resumen
        assert (run.out_dir / "manifiesto.json").exists()
        assert (run.out_dir / "http_requests.jsonl").exists()
        ok = True
    finally:
        run.shutdown()
        if ok:
            shutil.rmtree(tmp, ignore_errors=True)
