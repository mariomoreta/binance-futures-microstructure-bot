"""Aceptacion local del registro de cotizaciones con el piloto real.

Recorrido productivo con proveedores loopback, reloj controlado y
almacenamiento temporal. Sin Binance, capturas nuevas ni ordenes.
Criterios congelados en
``docs/evidence/cotizaciones-local-20261119/PREDECLARACION.md``.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import quote_tape as qt  # noqa: E402
import research_pilot as rp  # noqa: E402
import test_research_pilot as trp  # noqa: E402
from test_research_pilot import (  # noqa: E402
    MINUTE, T0, PilotRun, UNIVERSE, read_rows,
)

RUN_ID = "pilot-sync"


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="cotizaciones-local-"))
        self.runs = []

    def tearDown(self) -> None:
        for run in self.runs:
            run.shutdown()

    def _start(self, **kwargs) -> PilotRun:
        base = dict(universe=UNIVERSE, duration_s=900, settle_s=60,
                    selection_s=300, max_symbols=5)
        base.update(kwargs)
        run = PilotRun(self.tmp, **base)
        self.runs.append(run)
        return run

    def _finish(self, run: PilotRun):
        rc = run.stop()
        self.assertEqual(rc, 0, f"piloto fallo: {run.stderr}")
        return trp.read_rows(run.obs_path)

    def _filas(self, run: PilotRun):
        return qt.leer_tape(run.quote_path)

    @staticmethod
    def _publicar(run: PilotRun, instante: int, simbolos, specs=None):
        """Publica libro con el reloj ya en ``instante`` (evento = reloj)."""
        for simbolo, spec in (specs or {}).items():
            payload = dict(spec)
            payload.setdefault("event_ms", instante)
            run.ws.queue_depth(simbolo, payload)
        base = run.advance(instante)
        return run.publish_and_confirm(base, instante,
                                       depth_symbols=tuple(simbolos))

    @staticmethod
    def _precios_quitados(simbolo: str, entrada: int, salida: int, tape):
        me = trp.kline_price(simbolo, entrada)
        ms = trp.kline_price(simbolo, salida)
        return (me, ms)


class TestTrazas(Base):
    def test_long_y_short_recuperadas_de_lo_persistido(self):
        moves = {UNIVERSE[0]: 5.0, UNIVERSE[1]: -5.0,
                 UNIVERSE[2]: 0.1, UNIVERSE[3]: 0.1, UNIVERSE[4]: 0.1}
        run = self._start(quote_tape=True, moves=moves)
        run.wait_ready(expected_followed=5)

        decision = T0 + MINUTE
        obs = run.step(
            decision, depth_symbols=UNIVERSE,
            trade_events={s: trp._full_window(decision) for s in UNIVERSE},
            evaluate=True, expected_obs=5)
        self.assertEqual(len(obs), 5)
        ciclos = [r for r in trp.read_rows(run.obs_path)
                  if r.get("kind") == "ciclo"]
        seleccion = {x["symbol"]: x["side"] for x in ciclos[-1]["selected"]}
        long_sym = next(s for s in UNIVERSE if seleccion.get(s) == "UP")
        short_sym = next(s for s in UNIVERSE if seleccion.get(s) == "DOWN")

        entrada = decision + MINUTE
        salida = entrada + 5 * MINUTE
        pares = {}
        for simbolo in (long_sym, short_sym):
            me, ms = self._precios_quitados(simbolo, entrada, salida, None)
            for instante, mid in ((entrada, me), (salida, ms)):
                run.ws.queue_depth(simbolo, {
                    "event_ms": instante,
                    "bid": f"{mid - 0.1:.8f}", "ask": f"{mid + 0.1:.8f}",
                    "bid_qty": "10.0", "ask_qty": "10.0",
                })
            run.step(entrada, depth_symbols=(simbolo,), evaluate=False)
            run.step(salida, depth_symbols=(simbolo,), evaluate=False)
            pares[simbolo] = (me, ms)

        self._finish(run)
        filas = self._filas(run)
        self.assertGreaterEqual(len(filas), 4)

        trazas = {}
        for lado, simbolo in (("LONG", long_sym), ("SHORT", short_sym)):
            me, ms = pares[simbolo]
            evaluacion = qt.evaluar_episodio(
                simbolo, entrada, salida, lado, qt.TAMANO_SIMULADO,
                filas, run_id=RUN_ID,
                precio_ref_entrada=me, precio_ref_salida=ms)
            self.assertTrue(evaluacion["evaluable"], evaluacion)
            self.assertEqual(evaluacion["fila_entrada"]["event_ms"], entrada)
            self.assertEqual(evaluacion["fila_salida"]["event_ms"], salida)
            for campo in ("comision_bps", "slippage_adicional_bps",
                          "funding_bps", "retorno_neto_bps"):
                self.assertEqual(evaluacion[campo], "UNKNOWN")
            self.assertFalse(evaluacion["precios_son_fills"])
            trazas[lado] = evaluacion

        # Sentido de cruce: LONG compra al ask y vende al bid; SHORT al reves.
        self.assertEqual(trazas["LONG"]["precio_entrada"],
                         trazas["LONG"]["fila_entrada"]["best_ask"])
        self.assertEqual(trazas["LONG"]["precio_salida"],
                         trazas["LONG"]["fila_salida"]["best_bid"])
        self.assertEqual(trazas["SHORT"]["precio_entrada"],
                         trazas["SHORT"]["fila_entrada"]["best_bid"])
        self.assertEqual(trazas["SHORT"]["precio_salida"],
                         trazas["SHORT"]["fila_salida"]["best_ask"])

        # El informe legible queda dentro del directorio temporal de la prueba.
        destino = run.out_dir / "trazas.json"
        destino.write_text(json.dumps({
            "run_id": RUN_ID, "entrada_ms": entrada, "salida_ms": salida,
            "decision_ms": decision, "lados": {"long": long_sym,
                                               "short": short_sym},
            "precios_referencia": {k: list(v) for k, v in pares.items()},
            "filas_fuente": [f for f in filas
                             if f.get("symbol") in (long_sym, short_sym)],
            "evaluaciones": trazas,
        }, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        self.assertTrue(destino.exists())

    def test_exclusiones_con_filas_persistidas(self):
        run = self._start(quote_tape=True)
        run.wait_ready(expected_followed=5)
        sim_vieja, sim_posterior = UNIVERSE[1], UNIVERSE[0]
        sim_punta, sim_cruzada, sim_salto = UNIVERSE[2], UNIVERSE[3], UNIVERSE[4]
        base_t = T0 + 120_000
        salida = base_t + 5 * MINUTE

        # Vieja: recibida 20 s antes del instante, fuera de la ventana de 5 s.
        self._publicar(run, base_t - 20_000, (sim_vieja,))

        # Salto de secuencia: hace falta una primera lectura que encadene.
        self._publicar(run, base_t - 10_000, (sim_salto,))
        for simbolo, spec in (
            (sim_cruzada, {"event_ms": base_t, "bid": "2000.0",
                           "ask": "1999.0"}),
            (sim_salto, {"event_ms": base_t, "prev_id": 999}),
            (sim_punta, {"event_ms": base_t, "bid_qty": "0.5",
                         "ask_qty": "0.5"}),
        ):
            run.ws.queue_depth(simbolo, spec)
        run.step(base_t, depth_symbols=(sim_cruzada, sim_salto, sim_punta),
                 evaluate=False)

        # Posterior: recibida 2 s DESPUES del instante que se evalua.
        self._publicar(run, base_t + 2_000, (sim_posterior,))

        # Segundo extremo de la punta insuficiente.
        run.ws.queue_depth(sim_punta, {
            "event_ms": salida, "bid_qty": "0.5", "ask_qty": "0.5"})
        run.step(salida, depth_symbols=(sim_punta,), evaluate=False)

        self._finish(run)
        filas = self._filas(run)
        self.assertEqual(
            qt.seleccionar(sim_posterior, base_t, filas, run_id=RUN_ID)["motivo"],
            "COTIZACION_FUTURA")
        self.assertEqual(
            qt.seleccionar(sim_vieja, base_t, filas, run_id=RUN_ID)["motivo"],
            "COTIZACION_VIEJA")
        self.assertEqual(
            qt.seleccionar(sim_cruzada, base_t, filas, run_id=RUN_ID)["motivo"],
            "LIBRO_CRUZADO")
        self.assertEqual(
            qt.seleccionar(sim_salto, base_t, filas, run_id=RUN_ID)["motivo"],
            "SALTO_SECUENCIA")
        evaluacion = qt.evaluar_episodio(
            sim_punta, base_t, salida, "LONG", qt.TAMANO_SIMULADO,
            filas, run_id=RUN_ID)
        self.assertFalse(evaluacion["evaluable"])
        self.assertEqual(evaluacion["motivo"], "TAMANO_INSUFICIENTE")
        self.assertIsNone(evaluacion["retorno_cruce_bps"])

    def test_rotacion_deja_faltante_con_motivo(self):
        run = self._start(
            universe=trp.ROTATION_UNIVERSE, duration_s=600, settle_s=40,
            selection_s=120, max_symbols=4, rotation=True, quote_tape=True)
        run.wait_ready(expected_followed=4)
        first = set(run.status()["followed"])
        e0 = T0 + MINUTE
        run.step(e0, depth_symbols=sorted(first), evaluate=False)
        e1 = T0 + 2 * MINUTE
        run.advance(e1)
        state = run.wait_status(lambda st: st.get("cycles_run", 0) >= 2,
                                "rotacion aplicada")
        retirados = first - set(state["followed"])
        self.assertTrue(retirados)
        self._finish(run)
        filas = self._filas(run)
        for simbolo in retirados:
            self.assertTrue(any(f.get("kind") == "faltante"
                                and f.get("symbol") == simbolo
                                and f.get("motivo") == "simbolo_fuera_de_seguimiento"
                                for f in filas), simbolo)
            sel = qt.seleccionar(simbolo, e1, filas, run_id=RUN_ID)
            self.assertEqual(sel["motivo"], "SIMBOLO_FUERA_DE_SEGUIMIENTO")

    def test_tope_de_filas_no_detiene_el_piloto(self):
        run = self._start(quote_tape=True, quote_tape_max_rows=3)
        run.wait_ready(expected_followed=5)
        decision = T0 + MINUTE
        obs = run.step(
            decision, depth_symbols=UNIVERSE,
            trade_events={s: trp._full_window(decision) for s in UNIVERSE},
            evaluate=True, expected_obs=5)
        self.assertEqual(len(obs), 5)
        self._finish(run)
        filas = self._filas(run)
        self.assertEqual(sum(1 for f in filas if f.get("kind") == "cotizacion"), 3)
        self.assertEqual(sum(1 for f in filas if f.get("kind") == "limite"), 1)
        estado = run.summary()["cotizaciones_investigacion"]
        self.assertTrue(estado["cap_reached"])
        self.assertEqual(estado["cap_reason"], "limite_filas")

    def test_desactivado_no_escribe_archivo(self):
        run = self._start()
        run.wait_ready(expected_followed=5)
        run.step(T0 + MINUTE, depth_symbols=(UNIVERSE[0],), evaluate=False)
        self._finish(run)
        self.assertFalse(run.quote_path.exists())
        self.assertFalse(run.summary()["cotizaciones_investigacion"]["enabled"])

    def test_invalididad_rompe_cobertura_y_solo_valida_posterior_restaura(self):
        """Cotizacion valida en entrada, invalidez despues, libro recuperado
        en salida: evaluable solo desde la nueva cotizacion de salida."""
        simbolo = UNIVERSE[0]
        run = self._start(quote_tape=True)
        run.wait_ready(expected_followed=5)
        decision = T0 + MINUTE
        entrada = decision + MINUTE
        salida = entrada + 5 * MINUTE

        # Entrada: cotizacion valida.
        run.ws.queue_depth(simbolo, {
            "event_ms": entrada, "bid": "100.0", "ask": "100.2",
            "bid_qty": "10.0", "ask_qty": "10.0",
        })
        run.step(entrada, depth_symbols=(simbolo,), evaluate=False)

        # Invalidez (salto de secuencia) entre entrada y salida.
        run.ws.queue_depth(simbolo, {
            "event_ms": entrada + 10_000, "prev_id": 999,
        })
        run.step(entrada + 10_000, depth_symbols=(simbolo,), evaluate=False)

        # Salida: libro recuperado con cotizacion valida nueva.
        run.ws.queue_depth(simbolo, {
            "event_ms": salida, "bid": "100.4", "ask": "100.6",
            "bid_qty": "10.0", "ask_qty": "10.0",
        })
        run.step(salida, depth_symbols=(simbolo,), evaluate=False)

        self._finish(run)
        filas = self._filas(run)

        # Entrada es valida (cotizacion previa a la invalidez).
        sel_e = qt.seleccionar(simbolo, entrada, filas, run_id=RUN_ID)
        self.assertIsNone(sel_e["motivo"], sel_e)

        # Salida: cobertura restablecida solo por la cotizacion valida nueva.
        sel_s = qt.seleccionar(simbolo, salida, filas, run_id=RUN_ID)
        self.assertIsNone(sel_s["motivo"], sel_s)
        self.assertEqual(sel_s["cotizacion"]["event_ms"], salida)

        ev = qt.evaluar_episodio(
            simbolo, entrada, salida, "LONG", qt.TAMANO_SIMULADO,
            filas, run_id=RUN_ID)
        self.assertTrue(ev["evaluable"], ev)
        self.assertEqual(ev["fila_entrada"]["event_ms"], entrada)
        self.assertEqual(ev["fila_salida"]["event_ms"], salida)

    def test_invalidez_sin_recuperacion_no_es_evaluable(self):
        """Cotizacion valida en entrada, invalidez despues y sin recuperacion:
        la salida no es evaluable con motivo explicito."""
        simbolo = UNIVERSE[0]
        run = self._start(quote_tape=True)
        run.wait_ready(expected_followed=5)
        decision = T0 + MINUTE
        entrada = decision + MINUTE
        salida = entrada + 5 * MINUTE

        run.ws.queue_depth(simbolo, {
            "event_ms": entrada, "bid": "100.0", "ask": "100.2",
            "bid_qty": "10.0", "ask_qty": "10.0",
        })
        run.step(entrada, depth_symbols=(simbolo,), evaluate=False)

        # Salto de secuencia (prev_id encadenado incorrectamente) sin
        # recuperacion antes de la salida: el libro queda degradado.
        run.ws.queue_depth(simbolo, {
            "event_ms": entrada + 10_000, "prev_id": 999,
        })
        run.step(entrada + 10_000, depth_symbols=(simbolo,), evaluate=False)

        self._finish(run)
        filas = self._filas(run)

        sel_e = qt.seleccionar(simbolo, entrada, filas, run_id=RUN_ID)
        self.assertIsNone(sel_e["motivo"], sel_e)

        sel_s = qt.seleccionar(simbolo, salida, filas, run_id=RUN_ID)
        self.assertEqual(sel_s["motivo"], "SALTO_SECUENCIA")
        self.assertIsNone(sel_s["cotizacion"])

        ev = qt.evaluar_episodio(
            simbolo, entrada, salida, "LONG", qt.TAMANO_SIMULADO,
            filas, run_id=RUN_ID)
        self.assertFalse(ev["evaluable"])
        self.assertTrue(ev["motivo"].startswith("SIN_COTIZACION_SALIDA:"),
                        ev)

    def test_invalididad_despues_de_entrada_no_altera_entrada(self):
        """Una invalidez ocurrida DESPUES del instante de entrada no cambia
        la cotizacion valida en entrada (aunque falle la salida)."""
        simbolo = UNIVERSE[0]
        run = self._start(quote_tape=True)
        run.wait_ready(expected_followed=5)
        decision = T0 + MINUTE
        entrada = decision + MINUTE
        salida = entrada + 5 * MINUTE

        run.ws.queue_depth(simbolo, {
            "event_ms": entrada, "bid": "100.0", "ask": "100.2",
            "bid_qty": "10.0", "ask_qty": "10.0",
        })
        run.step(entrada, depth_symbols=(simbolo,), evaluate=False)

        # Invalidez despues de entrada, antes de salida.
        run.ws.queue_depth(simbolo, {
            "event_ms": entrada + 60_000, "prev_id": 999,
        })
        run.step(entrada + 60_000, depth_symbols=(simbolo,), evaluate=False)

        # Salida sin cotizacion valida (cobertura rota).
        run.step(salida, depth_symbols=(), evaluate=False)

        self._finish(run)
        filas = self._filas(run)

        # Entrada sigue usando la cotizacion valida de entrada (la invalidez
        # es posterior a T y no se usa).
        sel_e = qt.seleccionar(simbolo, entrada, filas, run_id=RUN_ID)
        self.assertIsNone(sel_e["motivo"], sel_e)
        self.assertEqual(sel_e["cotizacion"]["event_ms"], entrada)

        # Salida: cobertura rota por la invalidez posterior.
        sel_s = qt.seleccionar(simbolo, salida, filas, run_id=RUN_ID)
        self.assertEqual(sel_s["motivo"], "SALTO_SECUENCIA")
        self.assertIsNone(sel_s["cotizacion"])

    def test_cinta_agotada_antes_de_salida_no_es_evaluable(self):
        """Cinta agotada antes de la salida: no evaluable por LIMITE_ALCANZADO
        y el piloto sigue registrando observaciones normales."""
        simbolo = UNIVERSE[0]
        run = self._start(quote_tape=True, quote_tape_max_rows=2)
        run.wait_ready(expected_followed=5)
        decision = T0 + MINUTE
        entrada = decision + MINUTE
        salida = entrada + 5 * MINUTE

        # Tres intentos de escritura llenan la cinta (max_rows=2): el tercer
        # intento dispara la fila limite.
        run.ws.queue_depth(simbolo, {
            "event_ms": entrada, "bid": "100.0", "ask": "100.2",
            "bid_qty": "10.0", "ask_qty": "10.0",
        })
        run.step(entrada, depth_symbols=(simbolo,), evaluate=False)
        run.ws.queue_depth(simbolo, {
            "event_ms": entrada + 1_000, "bid": "100.1", "ask": "100.3",
            "bid_qty": "10.0", "ask_qty": "10.0",
        })
        run.step(entrada + 1_000, depth_symbols=(simbolo,), evaluate=False)
        run.ws.queue_depth(simbolo, {
            "event_ms": entrada + 2_000, "bid": "100.2", "ask": "100.4",
            "bid_qty": "10.0", "ask_qty": "10.0",
        })
        run.step(entrada + 2_000, depth_symbols=(simbolo,), evaluate=False)

        self._finish(run)
        filas = self._filas(run)

        # Cinta agotada: 2 cotizaciones + 1 fila limite.
        n_cot = sum(1 for f in filas if f.get("kind") == "cotizacion")
        n_lim = sum(1 for f in filas if f.get("kind") == "limite")
        self.assertEqual(n_cot, 2)
        self.assertEqual(n_lim, 1)

        # La entrada es evaluable (cotizacion valida antes del tope).
        sel_e = qt.seleccionar(simbolo, entrada, filas, run_id=RUN_ID)
        self.assertIsNone(sel_e["motivo"], sel_e)

        # La salida no: la cinta esta agotada (fila limite antes de salida).
        sel_s = qt.seleccionar(simbolo, salida, filas, run_id=RUN_ID)
        self.assertEqual(sel_s["motivo"], "LIMITE_ALCANZADO")
        self.assertIsNone(sel_s["cotizacion"])

        # El piloto siguio con su registro normal (observaciones escritas).
        obs = trp.read_rows(run.obs_path)
        self.assertGreaterEqual(len(obs), 1)


class TestPresupuesto(Base):
    def test_proyeccion_sin_red(self):
        cfg = rp.PilotConfig(run_id="budget", out_dir=self.tmp / "budget",
                             duration_seconds=14_400, max_symbols=20,
                             quote_tape_enabled=True)
        presupuesto = rp.compute_budget(cfg)
        cinta = presupuesto["cotizaciones_investigacion"]
        self.assertEqual(cinta["filas_proyectadas"], 20 * 14_400)
        self.assertEqual(cinta["bytes_proyectados"], 20 * 14_400 * 512)
        self.assertFalse(cinta["cobertura_captura_completa"])
        # Capacidad por el tope que se agote primero (filas o bytes).
        # La duracion se calcula MULTIPLICANDO por el intervalo entre filas
        # (no dividiendo): filas * cadencia_s / simbolos / 60.
        filas_max_por_bytes = rp.COTIZACIONES_LIMITE_BYTES // rp.COTIZACIONES_BYTES_FILA
        filas_marca = 1 + 20 * 2
        filas_efectivas = min(
            rp.COTIZACIONES_LIMITE_FILAS,
            (rp.COTIZACIONES_LIMITE_BYTES - filas_marca * rp.COTIZACIONES_BYTES_FILA)
            // rp.COTIZACIONES_BYTES_FILA,
        )
        cadencia_s = 1.0
        minutos_esperados = min(
            rp.COTIZACIONES_LIMITE_FILAS * cadencia_s / 20 / 60,
            filas_efectivas * cadencia_s / 20 / 60,
        )
        self.assertAlmostEqual(cinta["minutos_cubiertos_por_tope"],
                               minutos_esperados, places=4)
        self.assertEqual(cinta["filas_efectivas"], filas_efectivas)
        self.assertEqual(cinta["filas_marca_reservadas"], filas_marca)
        self.assertFalse(cinta["cubre_instantes_entrada_salida"])
        # El tope actual no cubre 4 h con 20 simbolos; ademas el presupuesto
        # base de esa configuracion ya era insuficiente antes de la cinta.
        self.assertFalse(presupuesto["gate"]["cabe_en_limites"])

        desactivado = rp.compute_budget(
            rp.PilotConfig(run_id="budget2", out_dir=self.tmp / "budget2",
                           duration_seconds=14_400, max_symbols=20))
        self.assertFalse(desactivado["cotizaciones_investigacion"]["enabled"])
        self.assertEqual(
            desactivado["cotizaciones_investigacion"]["filas_proyectadas"], 0)

    def test_cadencia_dos_segundos_cubre_el_doble(self):
        """A igualdad de filas y simbolos, una fila cada 2 s cubre el doble
        de tiempo que una cada 1 s (multiplicar por intervalo, no dividir)."""
        cfg_1s = rp.PilotConfig(run_id="b1", out_dir=self.tmp / "b1",
                                duration_seconds=3_600, max_symbols=20,
                                quote_tape_enabled=True,
                                quote_tape_cadencia_ms=1_000)
        cfg_2s = rp.PilotConfig(run_id="b2", out_dir=self.tmp / "b2",
                                duration_seconds=3_600, max_symbols=20,
                                quote_tape_enabled=True,
                                quote_tape_cadencia_ms=2_000)
        b1 = rp.compute_budget(cfg_1s)["cotizaciones_investigacion"]
        b2 = rp.compute_budget(cfg_2s)["cotizaciones_investigacion"]
        # Mismas filas proyectadas (duracion/1s vs duracion/2s da diferente nro
        # de filas porque el proyecto usa ceil(duration/cadencia_s)).
        # Pero minutos cubiertos por tope: 2s cubre el doble que 1s.
        self.assertAlmostEqual(
            b2["minutos_cubiertos_por_tope"],
            2 * b1["minutos_cubiertos_por_tope"], places=4)

    def test_cubre_hasta_ultima_salida_entrada_tarde(self):
        """Entrada tardia cuya salida queda despues del cierre real del feed:
        cubre_hasta_ultima_salida es False aunque el presupuesto general
        apruebe.

        Convencion: milisegundos desde el inicio programado de la captura.
        duration_seconds=600 -> feed cierra en 600_000 ms. Entrada en
        500_000 ms, salida en 800_000 ms (500_000 + 300_000). La salida cae
        despues del cierre del feed, por lo que no hay cobertura.
        """
        cfg = rp.PilotConfig(run_id="b3", out_dir=self.tmp / "b3",
                             duration_seconds=600, max_symbols=1,
                             quote_tape_enabled=True,
                             quote_tape_max_rows=100_000,
                             quote_tape_max_bytes=10 * 1024 * 1024,  # 10 MiB
                             quote_tape_ultima_entrada_ms_desde_inicio=500_000)
        presupuesto = rp.compute_budget(cfg)
        cinta = presupuesto["cotizaciones_investigacion"]
        self.assertFalse(cinta["cubre_hasta_ultima_salida"])
        # cubre_instantes_entrada_salida es sobre capacidad general de la
        # cinta vs horizonte, no sobre una entrada/salida específica.

    def test_cubre_hasta_ultima_salida_si_cubre(self):
        """Cinta cubre entrada + 5 min cuando hay suficientes filas/bytes
        y el feed esta abierto hasta la salida.

        Convencion: milisegundos desde el inicio. duration_seconds=600 ->
        feed cierra en 600_000 ms. Entrada en 100_000 ms, salida en
        400_000 ms (100_000 + 300_000). La salida esta antes del cierre
        del feed y dentro de la capacidad de la cinta.
        """
        cfg = rp.PilotConfig(run_id="b4", out_dir=self.tmp / "b4",
                             duration_seconds=600, max_symbols=20,
                             quote_tape_enabled=True,
                             quote_tape_max_rows=100_000,
                             quote_tape_max_bytes=10 * 1024 * 1024,  # 10 MiB
                             quote_tape_ultima_entrada_ms_desde_inicio=100_000)
        presupuesto = rp.compute_budget(cfg)
        cinta = presupuesto["cotizaciones_investigacion"]
        self.assertTrue(cinta["cubre_hasta_ultima_salida"])
        # Presupuesto general aprobado != cobertura de cinta.
        self.assertTrue(presupuesto["gate"]["cabe_en_limites"])

    def test_sin_ultima_entrada_no_declara_cobertura(self):
        """Sin ultima_entrada ni fin_feed no se declara cobertura de extremos."""
        cfg = rp.PilotConfig(run_id="b5", out_dir=self.tmp / "b5",
                             duration_seconds=600, max_symbols=1,
                             quote_tape_enabled=True,
                             quote_tape_max_rows=100_000,
                             quote_tape_max_bytes=10 * 1024 * 1024)
        presupuesto = rp.compute_budget(cfg)
        cinta = presupuesto["cotizaciones_investigacion"]
        self.assertFalse(cinta["cubre_hasta_ultima_salida"])

    def test_agotamiento_por_bytes_sin_marca_en_jsonl(self):
        """Agotamiento real por bytes sin fila limite en el JSONL: el piloto
        persiste el instante y motivo en resumen.json; el replay lee solo
        artefactos persistidos y devuelve LIMITE_ALCANZADO tras el corte."""
        simbolo = UNIVERSE[0]
        run = self._start(
            quote_tape=True, quote_tape_max_rows=10_000,
            quote_tape_max_bytes=450,  # cabe una fila (~300 B) pero no dos
        )
        run.wait_ready(expected_followed=5)
        decision = T0 + MINUTE
        entrada = decision + MINUTE

        # Primera cotizacion cabe; la segunda no (no hay espacio ni para
        # la fila ni para la marca limite).
        run.ws.queue_depth(simbolo, {
            "event_ms": entrada, "bid": "100.0", "ask": "100.2",
            "bid_qty": "10.0", "ask_qty": "10.0",
        })
        run.step(entrada, depth_symbols=(simbolo,), evaluate=False)
        # Segundo intento en segundo distinto: supera el tope de bytes.
        run.ws.queue_depth(simbolo, {
            "event_ms": entrada + 1_000, "bid": "100.1", "ask": "100.3",
            "bid_qty": "10.0", "ask_qty": "10.0",
        })
        run.step(entrada + 1_000, depth_symbols=(simbolo,), evaluate=False)

        self._finish(run)
        filas = self._filas(run)

        # El JSONL tiene una cotizacion pero NO fila limite (no cabio).
        n_cot = sum(1 for f in filas if f.get("kind") == "cotizacion")
        n_lim = sum(1 for f in filas if f.get("kind") == "limite")
        self.assertEqual(n_cot, 1)
        self.assertEqual(n_lim, 0)

        # resumen.json conserva el agotamiento (artefacto fuera del JSONL).
        resumen = json.loads(
            (run.out_dir / "resumen.json").read_text(encoding="utf-8"))
        cinta_estado = resumen["cotizaciones_investigacion"]
        self.assertTrue(cinta_estado["cap_reached"])
        self.assertIsNotNone(cinta_estado["cap_instante_ms"])
        self.assertIn(cinta_estado["cap_reason"], ("limite_bytes",))

        # Replay con agotamiento desde el artefacto persistido.
        agotamiento = {
            "instante_ms": cinta_estado["cap_instante_ms"],
            "motivo": cinta_estado["cap_reason"],
        }
        salida = entrada + 5 * MINUTE

        # Consulta EN el corte: LIMITE_ALCANZADO (aunque no hay fila
        # limite en el JSONL, el artefacto persistido lo acredita).
        sel_en_corte = qt.seleccionar(simbolo, entrada, filas, run_id=RUN_ID,
                                      agotamiento=agotamiento)
        self.assertEqual(sel_en_corte["motivo"], "LIMITE_ALCANZADO")
        self.assertIsNone(sel_en_corte["cotizacion"])

        # Consulta DESPUES del corte: LIMITE_ALCANZADO.
        sel_despues = qt.seleccionar(simbolo, salida, filas, run_id=RUN_ID,
                                     agotamiento=agotamiento)
        self.assertEqual(sel_despues["motivo"], "LIMITE_ALCANZADO")
        self.assertIsNone(sel_despues["cotizacion"])

        # Consulta para un simbolo sin datos ANTES del corte: SIN_COTIZACION
        # (el agotamiento global solo rige a partir de cap_instante_ms).
        sel_otro = qt.seleccionar("ZZZUSDT", entrada - 1000, filas,
                                  run_id=RUN_ID, agotamiento=agotamiento)
        self.assertEqual(sel_otro["motivo"], "SIN_COTIZACION")

        # El piloto siguio guardando observaciones normales tras el agotamiento.
        obs = trp.read_rows(run.obs_path)
        self.assertGreaterEqual(len(obs), 1)

    def test_replay_agotamiento_desde_resumen_json(self):
        """Recorrido completo desde artefactos persistidos (replay publico):
        el piloto agota la cinta por bytes sin escribir marca limite en el
        JSONL. ``replay_episodio_desde_corrida`` lee resumen.json y el JSONL,
        verifica mismo run_id, construye el agotamiento internamente y lo
        aplica a ambos extremos de evaluar_episodio."""
        simbolo = UNIVERSE[0]
        run = self._start(
            quote_tape=True, quote_tape_max_rows=10_000,
            quote_tape_max_bytes=450,  # cabe una fila pero no dos
        )
        run.wait_ready(expected_followed=5)
        decision = T0 + MINUTE
        entrada = decision + MINUTE
        salida = entrada + 5 * MINUTE

        # Primera cotizacion cabe (antes del agotamiento).
        run.ws.queue_depth(simbolo, {
            "event_ms": entrada - 2_000, "bid": "100.0", "ask": "100.2",
            "bid_qty": "10.0", "ask_qty": "10.0",
        })
        run.step(entrada - 2_000, depth_symbols=(simbolo,), evaluate=False)
        # Segundo intento dispara el agotamiento por bytes (cap_instante_ms =
        # entrada - 1000); no cabio la marca limite en el JSONL.
        run.ws.queue_depth(simbolo, {
            "event_ms": entrada, "bid": "100.1", "ask": "100.3",
            "bid_qty": "10.0", "ask_qty": "10.0",
        })
        run.step(entrada, depth_symbols=(simbolo,), evaluate=False)

        self._finish(run)
        filas = self._filas(run)

        # El JSONL tiene una cotizacion pero NO fila limite.
        n_cot = sum(1 for f in filas if f.get("kind") == "cotizacion")
        n_lim = sum(1 for f in filas if f.get("kind") == "limite")
        self.assertEqual(n_cot, 1)
        self.assertEqual(n_lim, 0)

        # Replay publico desde el directorio de la corrida: NO se construye
        # el argumento agotamiento a mano; replay_episodio_desde_corrida lo
        # lee de resumen.json.
        ev = qt.replay_episodio_desde_corrida(
            run.out_dir, simbolo, entrada - 2_000, salida, "LONG",
            qt.TAMANO_SIMULADO, run_id=RUN_ID)
        self.assertFalse(ev["evaluable"], ev)
        # La entrada esta antes del corte: se conserva como valida.
        self.assertIsNotNone(ev["fila_entrada"])
        self.assertEqual(ev["motivo_entrada"], None)
        self.assertEqual(ev["fila_entrada"]["event_ms"], entrada - 2_000)
        # La salida esta despues del corte: rechazada con LIMITE_ALCANZADO
        # aunque la ultima cita siga fresca.
        self.assertIsNone(ev["fila_salida"])
        self.assertEqual(ev["motivo_salida"], "LIMITE_ALCANZADO")
        self.assertTrue(ev["motivo"].startswith("SIN_COTIZACION_SALIDA:"),
                        ev)

        # El piloto siguio guardando observaciones normales tras el agotamiento.
        obs = trp.read_rows(run.obs_path)
        self.assertGreaterEqual(len(obs), 1)

    def test_replay_episodio_valido_sin_agotamiento(self):
        """Episodio valido sin agotamiento: replay publico es evaluable
        normalmente (regresion del comportamiento previo)."""
        simbolo = UNIVERSE[0]
        run = self._start(quote_tape=True, quote_tape_max_rows=10_000)
        run.wait_ready(expected_followed=5)
        decision = T0 + MINUTE
        entrada = decision + MINUTE
        salida = entrada + 5 * MINUTE

        run.ws.queue_depth(simbolo, {
            "event_ms": entrada, "bid": "100.0", "ask": "100.2",
            "bid_qty": "10.0", "ask_qty": "10.0",
        })
        run.step(entrada, depth_symbols=(simbolo,), evaluate=False)
        run.ws.queue_depth(simbolo, {
            "event_ms": salida, "bid": "100.4", "ask": "100.6",
            "bid_qty": "10.0", "ask_qty": "10.0",
        })
        run.step(salida, depth_symbols=(simbolo,), evaluate=False)

        self._finish(run)
        filas = self._filas(run)

        # No hubo agotamiento (cinta con espacio): agotamiento es None.
        resumen = json.loads(
            (run.out_dir / "resumen.json").read_text(encoding="utf-8"))
        self.assertFalse(resumen["cotizaciones_investigacion"]["cap_reached"])

        ev = qt.replay_episodio_desde_corrida(
            run.out_dir, simbolo, entrada, salida, "LONG",
            qt.TAMANO_SIMULADO, run_id=RUN_ID)
        self.assertTrue(ev["evaluable"], ev)
        self.assertEqual(ev["fila_entrada"]["event_ms"], entrada)
        self.assertEqual(ev["fila_salida"]["event_ms"], salida)
        self.assertIsNone(ev["motivo_entrada"])
        self.assertIsNone(ev["motivo_salida"])

    def test_replay_run_id_distinto_no_evaluable(self):
        """run_id distinto al de la corrida: resultado explicito y no
        evaluable, sin interpretar la ausencia como falta de agotamiento."""
        simbolo = UNIVERSE[0]
        run = self._start(
            quote_tape=True, quote_tape_max_rows=10_000,
            quote_tape_max_bytes=450,  # agota por bytes
        )
        run.wait_ready(expected_followed=5)
        decision = T0 + MINUTE
        entrada = decision + MINUTE
        salida = entrada + 5 * MINUTE

        run.ws.queue_depth(simbolo, {
            "event_ms": entrada, "bid": "100.0", "ask": "100.2",
            "bid_qty": "10.0", "ask_qty": "10.0",
        })
        run.step(entrada, depth_symbols=(simbolo,), evaluate=False)

        self._finish(run)

        # Solicitar un run_id que no coincide con el de la cinta/resumen.
        ev = qt.replay_episodio_desde_corrida(
            run.out_dir, simbolo, entrada, salida, "LONG",
            qt.TAMANO_SIMULADO, run_id="run-otro-distinto")
        self.assertFalse(ev["evaluable"])
        self.assertEqual(ev["motivo"], "RUN_ID_DISTINTO")

    def test_budget_only_cubre_hasta_ultima_salida_positivo(self):
        """--budget-only: plan que cubre hasta la ultima salida."""
        out = self.tmp / "presupuesto-pos"
        cmd = [sys.executable, str(ROOT / "scripts" / "research_pilot.py"),
               "--run-id", "budget-pos", "--out-dir", str(out),
               "--mode", "local", "--budget-only", "--quote-tape",
               "--duration-seconds", "600", "--max-symbols", "1",
               "--max-candidates", "1", "--max-comparators", "0",
               "--quote-tape-max-rows", "100000",
               "--quote-tape-max-bytes", str(10 * 1024 * 1024),
               "--quote-tape-ultima-entrada-ms-desde-inicio", "100000"]
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                              text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads((out / "presupuesto.json").read_text(encoding="utf-8"))
        cinta = data["cotizaciones_investigacion"]
        self.assertTrue(cinta["cubre_hasta_ultima_salida"])
        self.assertTrue(data["gate"]["cabe_en_limites"])

    def test_budget_only_cubre_hasta_ultima_salida_negativo_feed_cerrado(self):
        """--budget-only: capacidad de cinta suficiente pero salida despues
        del cierre real del feed. cubre_hasta_ultima_salida es False."""
        out = self.tmp / "presupuesto-neg"
        cmd = [sys.executable, str(ROOT / "scripts" / "research_pilot.py"),
               "--run-id", "budget-neg", "--out-dir", str(out),
               "--mode", "local", "--budget-only", "--quote-tape",
               "--duration-seconds", "600", "--max-symbols", "1",
               "--max-candidates", "1", "--max-comparators", "0",
               "--quote-tape-max-rows", "100000",
               "--quote-tape-max-bytes", str(10 * 1024 * 1024),
               "--quote-tape-ultima-entrada-ms-desde-inicio", "500000"]
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                              text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads((out / "presupuesto.json").read_text(encoding="utf-8"))
        cinta = data["cotizaciones_investigacion"]
        self.assertFalse(cinta["cubre_hasta_ultima_salida"])
        self.assertTrue(data["gate"]["cabe_en_limites"])

    def test_budget_only_unidades_incompatibles_sin_cobertura(self):
        """--budget-only: si se pasa una hora de epocita como si fuera ms
        desde el inicio, la salida queda muy mas alla del cierre del feed
        y nunca se aprueba cobertura."""
        out = self.tmp / "presupuesto-incomp"
        cmd = [sys.executable, str(ROOT / "scripts" / "research_pilot.py"),
               "--run-id", "budget-incomp", "--out-dir", str(out),
               "--mode", "local", "--budget-only", "--quote-tape",
               "--duration-seconds", "600", "--max-symbols", "1",
               "--max-candidates", "1", "--max-comparators", "0",
               "--quote-tape-max-rows", "100000",
               "--quote-tape-max-bytes", str(10 * 1024 * 1024),
               # Valor de epocita (~1.7 billones) interpretado como ms
               # desde el inicio: salida >> cierre del feed.
               "--quote-tape-ultima-entrada-ms-desde-inicio", "1735689720000"]
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                              text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads((out / "presupuesto.json").read_text(encoding="utf-8"))
        cinta = data["cotizaciones_investigacion"]
        self.assertFalse(cinta["cubre_hasta_ultima_salida"])

    def test_budget_only_quote_tape_sin_red(self):
        out = self.tmp / "presupuesto"
        cmd = [sys.executable, str(ROOT / "scripts" / "research_pilot.py"),
               "--run-id", "budget-cli", "--out-dir", str(out),
               "--mode", "local", "--budget-only", "--quote-tape",
               "--duration-seconds", "600", "--max-symbols", "20"]
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                              text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads((out / "presupuesto.json").read_text(encoding="utf-8"))
        self.assertTrue(data["cotizaciones_investigacion"]["enabled"])
        self.assertEqual(data["cotizaciones_investigacion"]["filas_proyectadas"],
                         20 * 600)


if __name__ == "__main__":
    unittest.main()
