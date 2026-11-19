"""Genera la evidencia compacta del registro local de cotizaciones.

Ejecuta los mismos recorridos del piloto real con proveedores loopback, reloj
controlado y almacenamiento temporal que las pruebas de aceptacion. Sin red, sin
Binance y sin capturas nuevas. La salida es determinista (reloj y precios
controlados) y se publica en docs/evidence/cotizaciones-local-20261119/.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts"),
           str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import quote_tape as qt  # noqa: E402
import research_pilot as rp  # noqa: E402
import test_research_pilot as trp  # noqa: E402
from test_research_pilot import MINUTE, T0, UNIVERSE, PilotRun  # noqa: E402

RUN_ID = "pilot-sync"
SALIDA = ROOT / "docs" / "evidence" / "cotizaciones-local-20261119" / "C-evidencia.json"
BASE = "e5ba321313a05ffd63b38de107592b965d95e665"
PREDECLARACION = "43e1238ef19b2dfcd8f41f5e7bb7e12d42ca70c0"


class Recorridos:
    def __init__(self) -> None:
        self.raiz = Path(tempfile.mkdtemp(prefix="cotizaciones-evidencia-"))
        self.runs = []

    def iniciar(self, nombre: str, **kwargs) -> PilotRun:
        base = dict(universe=UNIVERSE, duration_s=900, settle_s=60,
                    selection_s=300, max_symbols=5)
        base.update(kwargs)
        destino = self.raiz / nombre
        destino.mkdir(parents=True, exist_ok=True)
        run = PilotRun(destino, **base)
        self.runs.append(run)
        return run

    @staticmethod
    def publicar(run: PilotRun, instante: int, simbolos, specs=None):
        for simbolo, spec in (specs or {}).items():
            payload = dict(spec)
            payload.setdefault("event_ms", instante)
            run.ws.queue_depth(simbolo, payload)
        estado = run.advance(instante)
        return run.publish_and_confirm(estado, instante,
                                       depth_symbols=tuple(simbolos))

    @staticmethod
    def cerrar(run: PilotRun):
        rc = run.stop()
        if rc != 0:
            raise RuntimeError(f"piloto termino con {rc}: {run.stderr}")
        return qt.leer_tape(run.quote_path)

    def shutdown(self):
        for run in self.runs:
            run.shutdown()


def filas_ordenadas(filas):
    return sorted(filas, key=lambda f: (str(f.get("symbol")),
                                        int(f.get("event_ms") or 0),
                                        int(f.get("seq") or 0)))


def trazas(rec: Recorridos):
    moves = {UNIVERSE[0]: 5.0, UNIVERSE[1]: -5.0,
             UNIVERSE[2]: 0.1, UNIVERSE[3]: 0.1, UNIVERSE[4]: 0.1}
    run = rec.iniciar("trazas", quote_tape=True, moves=moves)
    run.wait_ready(expected_followed=5)
    decision = T0 + MINUTE
    run.step(decision, depth_symbols=UNIVERSE,
             trade_events={s: trp._full_window(decision) for s in UNIVERSE},
             evaluate=True, expected_obs=5)
    ciclos = [r for r in trp.read_rows(run.obs_path)
              if r.get("kind") == "ciclo"]
    lados = {x["symbol"]: x["side"] for x in ciclos[-1]["selected"]}
    simbolos = {
        "LONG": next(s for s in UNIVERSE if lados.get(s) == "UP"),
        "SHORT": next(s for s in UNIVERSE if lados.get(s) == "DOWN"),
    }
    entrada = decision + MINUTE
    salida = entrada + 5 * MINUTE
    referencias = {}
    for simbolo in set(simbolos.values()):
        me = trp.kline_price(simbolo, entrada)
        ms = trp.kline_price(simbolo, salida)
        referencias[simbolo] = {"entrada": me, "salida": ms}
        for instante, mid in ((entrada, me), (salida, ms)):
            run.ws.queue_depth(simbolo, {
                "event_ms": instante,
                "bid": f"{mid - 0.1:.8f}", "ask": f"{mid + 0.1:.8f}",
                "bid_qty": "10.0", "ask_qty": "10.0"})
        run.step(entrada, depth_symbols=(simbolo,), evaluate=False)
        run.step(salida, depth_symbols=(simbolo,), evaluate=False)
    filas = rec.cerrar(run)
    bytes_archivo = run.quote_path.stat().st_size
    out = {}
    for lado, simbolo in simbolos.items():
        ref = referencias[simbolo]
        evaluacion = qt.evaluar_episodio(
            simbolo, entrada, salida, lado, qt.TAMANO_SIMULADO, filas,
            run_id=RUN_ID, precio_ref_entrada=ref["entrada"],
            precio_ref_salida=ref["salida"])
        fuente = [f for f in filas if f.get("symbol") == simbolo
                  and f.get("event_ms") in (entrada, salida)]
        out[lado] = {
            "symbol": simbolo, "decision_ms": decision,
            "entrada_ms": entrada, "salida_ms": salida,
            "precios_referencia": ref,
            "filas_fuente": filas_ordenadas(fuente),
            "evaluacion": evaluacion,
        }
    return out, bytes_archivo, len(filas)


def exclusiones(rec: Recorridos):
    run = rec.iniciar("exclusiones", quote_tape=True)
    run.wait_ready(expected_followed=5)
    vieja, posterior = UNIVERSE[1], UNIVERSE[0]
    punta, cruzada, salto = UNIVERSE[2], UNIVERSE[3], UNIVERSE[4]
    t = T0 + 120_000
    salida = t + 5 * MINUTE

    rec.publicar(run, t - 20_000, (vieja,))
    rec.publicar(run, t - 10_000, (salto,))
    for simbolo, spec in (
        (cruzada, {"event_ms": t, "bid": "2000.0", "ask": "1999.0"}),
        (salto, {"event_ms": t, "prev_id": 999}),
        (punta, {"event_ms": t, "bid_qty": "0.5", "ask_qty": "0.5"}),
    ):
        run.ws.queue_depth(simbolo, spec)
    run.step(t, depth_symbols=(cruzada, salto, punta), evaluate=False)
    rec.publicar(run, t + 2_000, (posterior,))
    run.ws.queue_depth(punta, {"event_ms": salida,
                               "bid_qty": "0.5", "ask_qty": "0.5"})
    run.step(salida, depth_symbols=(punta,), evaluate=False)
    filas = rec.cerrar(run)

    salidas = []
    for nombre, simbolo in (("cotizacion_posterior", posterior),
                            ("cotizacion_vieja", vieja),
                            ("libro_cruzado", cruzada),
                            ("salto_de_secuencia", salto)):
        sel = qt.seleccionar(simbolo, t, filas, run_id=RUN_ID)
        salidas.append({
            "caso": nombre, "symbol": simbolo, "instante_ms": t,
            "codigo_observado": sel["motivo"],
            "filas_fuente": filas_ordenadas(
                [f for f in filas if f.get("symbol") == simbolo]),
        })
    ev = qt.evaluar_episodio(punta, t, salida, "LONG", qt.TAMANO_SIMULADO,
                             filas, run_id=RUN_ID)
    salidas.append({
        "caso": "punta_insuficiente", "symbol": punta,
        "instante_ms": t,
        "codigo_observado": ev["motivo"],
        "size": ev["size"],
        "retorno_cruce_bps": ev["retorno_cruce_bps"],
        "filas_fuente": filas_ordenadas(
            [f for f in filas if f.get("symbol") == punta]),
    })
    return salidas


def rotacion(rec: Recorridos):
    run = rec.iniciar("rotacion", universe=trp.ROTATION_UNIVERSE,
                      duration_s=600, settle_s=40, selection_s=120,
                      max_symbols=4, rotation=True, quote_tape=True)
    run.wait_ready(expected_followed=4)
    primero = set(run.status()["followed"])
    run.step(T0 + MINUTE, depth_symbols=sorted(primero), evaluate=False)
    instante = T0 + 2 * MINUTE
    run.advance(instante)
    estado = run.wait_status(lambda st: st.get("cycles_run", 0) >= 2,
                             "rotacion aplicada")
    filas = rec.cerrar(run)
    retirados = sorted(primero - set(estado["followed"]))
    return {
        "instante_ms": instante,
        "retirados": retirados,
        "filas_faltante": filas_ordenadas(
            [f for f in filas if f.get("kind") == "faltante"]),
        "motivos": {s: qt.seleccionar(s, instante, filas,
                                      run_id=RUN_ID)["motivo"]
                    for s in retirados},
    }


def limite(rec: Recorridos):
    run = rec.iniciar("limite", quote_tape=True, quote_tape_max_rows=3)
    run.wait_ready(expected_followed=5)
    decision = T0 + MINUTE
    obs = run.step(decision, depth_symbols=UNIVERSE,
                   trade_events={s: trp._full_window(decision)
                                 for s in UNIVERSE},
                   evaluate=True, expected_obs=5)
    filas = rec.cerrar(run)
    estado = run.summary()["cotizaciones_investigacion"]
    return {
        "max_rows": estado["max_rows"],
        "observaciones_escritas": len(obs),
        "cotizaciones": sum(1 for f in filas
                            if f.get("kind") == "cotizacion"),
        "limite": [f for f in filas if f.get("kind") == "limite"],
        "estado": estado,
        "piloto_continuo": len(obs) == 5 and estado["cap_reached"],
    }


def presupuesto():
    def cfg(duracion, activo):
        return rp.PilotConfig(run_id="budget", out_dir=ROOT / "data",
                              duration_seconds=duracion, max_symbols=20,
                              quote_tape_enabled=activo)

    completo = rp.compute_budget(cfg(14_400, True))
    base = rp.compute_budget(cfg(14_400, False))
    corto = rp.compute_budget(cfg(600, True))
    return {
        "supuestos": {
            "simbolos_simultaneos": 20,
            "cadencia_ms": qt.CADENCIA_MS,
            "bytes_por_fila_estimados": qt.BYTES_POR_FILA_ESTIMADOS,
            "max_rows": qt.LIMITE_FILAS,
            "max_bytes": qt.LIMITE_BYTES,
        },
        "captura_4h_con_cinta": completo["cotizaciones_investigacion"],
        "captura_4h_sin_cinta": {
            "gate_cabe_en_limites": base["gate"]["cabe_en_limites"],
            "almacenamiento_previsto_bytes":
                base["gate"]["almacenamiento_previsto_bytes"],
        },
        "captura_10m_con_cinta": corto["cotizaciones_investigacion"],
        "captura_10m_gate_cabe_en_limites": corto["gate"]["cabe_en_limites"],
    }


def main() -> int:
    rec = Recorridos()
    try:
        tr, bytes_traza, filas_traza = trazas(rec)
        exc = exclusiones(rec)
        rot = rotacion(rec)
        lim = limite(rec)
    finally:
        rec.shutdown()

    presup = presupuesto()
    bytes_fila = bytes_traza / filas_traza if filas_traza else None
    payload = {
        "version": qt.VERSION,
        "base": BASE,
        "predeclaracion_commit": PREDECLARACION,
        "predeclaracion": "docs/evidence/cotizaciones-local-20261119/PREDECLARACION.md",
        "criterios": {
            "max_edad_ms": qt.MAX_EDAD_MS,
            "cadencia_ms": qt.CADENCIA_MS,
            "size": qt.TAMANO_SIMULADO,
            "max_rows": qt.LIMITE_FILAS,
            "max_bytes": qt.LIMITE_BYTES,
            "seleccion": "ultima fila valida con received_ms<=instante, "
                         "event_ms<=instante y edad<=5000 ms; desempate por "
                         "received_ms, event_ms y seq",
        },
        "esquema": {
            "cotizacion": ["kind", "version", "run_id", "symbol", "event_ms",
                           "received_ms", "seq", "best_bid", "best_ask",
                           "bid_qty", "ask_qty", "bid_levels", "ask_levels",
                           "mid", "spread_bps", "degraded", "gap", "crossed",
                           "valida", "motivos_invalidez", "cadencia_ms"],
            "faltante": ["kind", "version", "run_id", "symbol", "event_ms",
                         "received_ms", "seq", "motivo", "detalle",
                         "cadencia_ms"],
            "limite": ["kind", "version", "run_id", "seq", "motivo",
                       "filas_escritas", "bytes_escritos"],
            "lectura": "quote_tape.leer_tape -> seleccionar -> evaluar_episodio",
        },
        "recorrido": {
            "aceptado_localmente": all(
                v["evaluacion"]["evaluable"] for v in tr.values())
                and lim["piloto_continuo"],
            "proveedores": "loopback", "reloj": "manual",
            "almacenamiento": "temporal", "binance": False,
            "capturas_nuevas": False,
        },
        "trazas": tr,
        "exclusiones": exc,
        "rotacion": rot,
        "limite": lim,
        "presupuesto": presup,
        "bytes_medidos": {
            "archivo_trazas_bytes": bytes_traza,
            "filas_trazas": filas_traza,
            "bytes_por_fila_medidos": bytes_fila,
            "nota": "medido sobre las filas de los dos episodios con sus "
                    "fuentes; proyeccion usa 512 B por fila",
        },
        "no_acreditado": [
            "cobertura en captura publica",
            "fills reales: los precios son cotizados",
            "comision, slippage adicional y funding",
            "rentabilidad o neto completo",
        ],
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                 sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"salida": str(SALIDA),
                      "aceptado_localmente":
                          payload["recorrido"]["aceptado_localmente"],
                      "bytes": SALIDA.stat().st_size},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
