"""Funding coverage v1: credited absence only with explicit, valid evidence.

Covers the local A-F acceptance for the bounded funding-coverage contract:
known zero, known payment, partial coverage, invalid/truncated evidence,
legacy conservatism, exposure boundaries, and hash/config commitment.
Synthetic fixtures only; no network or market acquisition.
Run: python run_tests.py
"""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from scripts.research_operativo_adapter import (
    OperativoAdapter,
    OperativoConfig,
    OperativoTradeResult,
)
from microstructure_probe.paper_lab_engine import PaperCandle
from microstructure_probe.backtest_offline import (
    BacktestConfig,
    Candle,
    FundingCalendar,
    FundingCoverage,
    FundingSettlement,
    StudyEvent,
    funding_settlements_sha256,
    run_backtest,
)

H = 3_600_000
SYMBOL = "BTCUSDT"


def _cfg(**kwargs):
    base = dict(
        fee_bps=0.0,
        funding_8h_bps=0.0,
        spread_bps=0.0,
        slippage_bps=0.0,
        notional_usdt=1000.0,
        stop_distance_pct=50.0,
        exit_horizon_ms=5 * H,
    )
    base.update(kwargs)
    return BacktestConfig(**base)


def _hourly(count=12):
    return [
        Candle(SYMBOL, index * H, 100.0, 100.1, 99.9, 100.0)
        for index in range(count)
    ]


def _coverage(
    start_ms,
    end_ms,
    settlements=(),
    *,
    symbol=SYMBOL,
    status="complete",
    method="synthetic-fixture",
    evidence_kind="synthetic-fixture",
    request_symbol=None,
    pagination=None,
    response_digest=None,
):
    ordered = tuple(sorted(settlements, key=lambda item: item.settlement_ms))
    digest = response_digest or funding_settlements_sha256(ordered)
    page = {
        "pages": 1,
        "complete": True,
        "truncated": False,
    }
    if pagination is not None:
        page.update(pagination)
    evidence = {
        "kind": evidence_kind,
        "reference": "synthetic-fixture://funding-coverage/v1",
        "statement": "synthetic complete coverage for local mechanics",
        "sha256": "a" * 64,
        "artifact_uri": "synthetic-fixture://funding-coverage/v1",
        "artifact_sha256": "a" * 64,
        "symbol": symbol,
        "venue": "synthetic",
        "interval_start_ms": start_ms,
        "interval_end_ms": end_ms,
        "valid_from_ms": start_ms,
        "valid_until_ms": end_ms,
    }
    publication = {
        "kind": "synthetic-fixture",
        "reference": "synthetic-fixture://publication-delay/v1",
        "statement": "synthetic rows are available at acquisition time",
        "sha256": "b" * 64,
        "artifact_uri": "synthetic-fixture://publication-delay/v1",
        "artifact_sha256": "b" * 64,
        "symbol": symbol,
        "venue": "synthetic",
        "interval_start_ms": start_ms,
        "interval_end_ms": end_ms,
        "available_at_ms": end_ms,
    }
    return FundingCoverage(
        version="funding-coverage/v1",
        status=status,
        symbol=symbol,
        venue="synthetic",
        source="synthetic-fixture",
        interval_start_ms=start_ms,
        interval_end_ms=end_ms,
        acquired_at_ms=end_ms,
        available_at_ms=end_ms,
        method=method,
        evidence=evidence,
        request={
            "endpoint": "synthetic://funding-history",
            "params": {
                "symbol": request_symbol or symbol,
                "startTime": start_ms,
                "endTime": end_ms - 1,
                "limit": 1000,
            },
            "http_status": 200,
            "sent_at_ms": end_ms,
            "completed_at_ms": end_ms,
        },
        response={
            "sha256": "c" * 64,
            "row_count": len(ordered),
            "symbols": [symbol] if ordered else [],
            "pagination": page,
            "settlement_sha256": digest,
            "first_settlement_ms": (
                ordered[0].settlement_ms if ordered else None),
            "last_settlement_ms": (
                ordered[-1].settlement_ms if ordered else None),
        },
        publication_delay_ms=0,
        publication_delay_evidence=publication,
        reason=("UNKNOWN synthetic evidence" if status != "complete" else ""),
    )


def _calendar_with_settlements(settlements, coverage, *, interval_ms=None):
    return FundingCalendar(
        version="synthetic/v1",
        source="synthetic-fixture",
        interval_ms=interval_ms,
        settlements=tuple(settlements),
        symbol=SYMBOL,
        coverage=coverage,
    )


def _run(calendar):
    result = run_backtest(
        [StudyEvent(SYMBOL, 0, "LONG", 100.0)],
        _hourly(),
        _cfg(funding_calendar=calendar),
    )
    return result, result["trades"][0]


class KnownZeroTest(unittest.TestCase):
    def test_complete_explicit_coverage_credits_zero_without_cadence(self):
        coverage = _coverage(H, 5 * H)
        calendar = _calendar_with_settlements((), coverage)
        result, trade = _run(calendar)
        self.assertEqual(trade["funding"], 0.0)
        self.assertTrue(trade["funding_accounting_complete"])
        self.assertEqual(trade["funding_uncovered_ms"], 0)
        self.assertEqual(trade["funding_coverage_status"], "complete")
        self.assertEqual(result["funding_calendar"]["coverage_status"],
                         "complete")
        self.assertTrue(result["funding_calendar"]["complete"])


class KnownPaymentTest(unittest.TestCase):
    def test_payment_in_complete_coverage_keeps_existing_amount_formula(self):
        settlement = FundingSettlement(2 * H, 10.0)
        coverage = _coverage(H, 5 * H, (settlement,))
        calendar = _calendar_with_settlements((settlement,), coverage)
        _, trade = _run(calendar)
        self.assertAlmostEqual(trade["funding"], 1.0)
        self.assertTrue(trade["funding_accounting_complete"])
        self.assertEqual(len(trade["funding_events"]), 1)
        self.assertEqual(trade["funding_events"][0]["held_qty"], 10.0)
        self.assertEqual(trade["funding_events"][0]["settlement_mark_px"],
                         100.0)


class PartialCoverageTest(unittest.TestCase):
    def test_partial_interval_keeps_observed_amount_but_total_unknown(self):
        settlement = FundingSettlement(2 * H, 10.0)
        coverage = _coverage(H, 3 * H, (settlement,))
        calendar = _calendar_with_settlements((settlement,), coverage)
        _, trade = _run(calendar)
        self.assertAlmostEqual(trade["funding"], 1.0)
        self.assertFalse(trade["funding_accounting_complete"])
        self.assertEqual(trade["funding_uncovered_ms"], 2 * H)
        self.assertIn("coverage missing", trade["funding_accounting_basis"])


class InvalidEvidenceTest(unittest.TestCase):
    def test_response_only_evidence_cannot_claim_complete(self):
        coverage = _coverage(
            H, 5 * H, evidence_kind="venue-response",
            method="venue-response")
        calendar = _calendar_with_settlements((), coverage)
        _, trade = _run(calendar)
        self.assertFalse(trade["funding_accounting_complete"])
        self.assertEqual(trade["funding_coverage_status"], "unknown")
        self.assertTrue(trade["funding_coverage_errors"])

    def test_truncated_pagination_cannot_claim_complete(self):
        coverage = _coverage(
            H, 5 * H,
            pagination={"complete": False, "truncated": True})
        calendar = _calendar_with_settlements((), coverage)
        _, trade = _run(calendar)
        self.assertFalse(trade["funding_accounting_complete"])
        self.assertEqual(trade["funding_coverage_status"], "unknown")

    def test_symbol_contradiction_cannot_claim_complete(self):
        coverage = _coverage(H, 5 * H, request_symbol="ETHUSDT")
        calendar = _calendar_with_settlements((), coverage)
        _, trade = _run(calendar)
        self.assertFalse(trade["funding_accounting_complete"])
        self.assertEqual(trade["funding_coverage_status"], "unknown")

    def test_settlement_digest_contradiction_cannot_claim_complete(self):
        coverage = _coverage(H, 5 * H, response_digest="d" * 64)
        calendar = _calendar_with_settlements((), coverage)
        _, trade = _run(calendar)
        self.assertFalse(trade["funding_accounting_complete"])
        self.assertEqual(trade["funding_coverage_status"], "unknown")

    def test_missing_publication_bound_cannot_claim_complete(self):
        coverage = replace(
            _coverage(H, 5 * H),
            publication_delay_ms=None,
            publication_delay_evidence={})
        calendar = _calendar_with_settlements((), coverage)
        _, trade = _run(calendar)
        self.assertFalse(trade["funding_accounting_complete"])
        self.assertEqual(trade["funding_coverage_status"], "unknown")

    def test_row_count_must_match_loaded_settlements(self):
        coverage = _coverage(H, 5 * H)
        response = dict(coverage.response)
        response["row_count"] = 1
        response["symbols"] = [SYMBOL]
        coverage = replace(coverage, response=response)
        calendar = _calendar_with_settlements((), coverage)
        _, trade = _run(calendar)
        self.assertFalse(trade["funding_accounting_complete"])
        self.assertEqual(trade["funding_coverage_status"], "unknown")

    def test_response_at_request_limit_cannot_claim_complete(self):
        coverage = _coverage(H, 5 * H)
        response = dict(coverage.response)
        response["row_count"] = 1000
        response["symbols"] = [SYMBOL]
        coverage = replace(coverage, response=response)
        calendar = _calendar_with_settlements((), coverage)
        _, trade = _run(calendar)
        self.assertFalse(trade["funding_accounting_complete"])
        self.assertEqual(trade["funding_coverage_status"], "unknown")

    def test_settlement_outside_requested_interval_cannot_claim_complete(self):
        settlement = FundingSettlement(H - 1, 10.0)
        coverage = _coverage(H, 5 * H, (settlement,))
        calendar = _calendar_with_settlements((settlement,), coverage)
        _, trade = _run(calendar)
        self.assertFalse(trade["funding_accounting_complete"])
        self.assertEqual(trade["funding_coverage_status"], "unknown")

    def test_synthetic_evidence_cannot_certify_binance_venue(self):
        coverage = replace(
            _coverage(H, 5 * H),
            venue="binance-usd-m")
        calendar = _calendar_with_settlements((), coverage)
        _, trade = _run(calendar)
        self.assertFalse(trade["funding_accounting_complete"])
        self.assertEqual(trade["funding_coverage_status"], "unknown")

    def test_venue_absence_proof_must_bind_symbol_and_interval(self):
        coverage = _coverage(H, 5 * H)
        evidence = dict(coverage.evidence)
        evidence.update({
            "kind": "venue-absence-proof",
            "artifact_uri": "sha256://" + "a" * 64,
        })
        publication = dict(coverage.publication_delay_evidence)
        publication.update({
            "kind": "venue-absence-proof",
            "artifact_uri": "sha256://" + "b" * 64,
        })
        coverage = replace(
            coverage,
            venue="fixture-venue",
            source="fixture-venue-history",
            evidence=evidence,
            publication_delay_evidence=publication)
        evidence.pop("symbol")
        invalid = replace(coverage, evidence=evidence)
        calendar = FundingCalendar(
            version="fixture/v1",
            source="fixture-venue-history",
            interval_ms=None,
            settlements=(),
            symbol=SYMBOL,
            coverage=invalid)
        _, trade = _run(calendar)
        self.assertFalse(trade["funding_accounting_complete"])
        self.assertEqual(trade["funding_coverage_status"], "unknown")

    def test_unknown_publication_evidence_cannot_certify_complete(self):
        coverage = _coverage(H, 5 * H)
        publication = dict(coverage.publication_delay_evidence)
        publication["kind"] = "UNKNOWN"
        coverage = replace(coverage, publication_delay_evidence=publication)
        calendar = _calendar_with_settlements((), coverage)
        _, trade = _run(calendar)
        self.assertFalse(trade["funding_accounting_complete"])
        self.assertEqual(trade["funding_coverage_status"], "unknown")

    def test_availability_must_include_publication_delay(self):
        coverage = replace(
            _coverage(H, 5 * H),
            publication_delay_ms=1000)
        calendar = _calendar_with_settlements((), coverage)
        _, trade = _run(calendar)
        self.assertFalse(trade["funding_accounting_complete"])
        self.assertEqual(trade["funding_coverage_status"], "unknown")

    def test_loader_downgrades_invalid_complete_claim_to_unknown(self):
        coverage = _coverage(H, 5 * H, request_symbol="ETHUSDT")
        loaded = FundingCoverage.from_dict(coverage.to_dict())
        self.assertEqual(loaded.status, "unknown")
        self.assertIn("invalid coverage evidence", loaded.reason)

    def test_missing_acquisition_instant_survives_the_round_trip(self):
        coverage = replace(
            _coverage(H, 5 * H, status="unknown"),
            acquired_at_ms=None,
            available_at_ms=None)
        loaded = FundingCoverage.from_dict(coverage.to_dict())
        self.assertIsNone(loaded.acquired_at_ms)
        self.assertIsNone(loaded.available_at_ms)
        self.assertEqual(loaded.effective_status(), "unknown")


class LegacyConservativeTest(unittest.TestCase):
    def test_legacy_calendar_without_coverage_stays_conservative(self):
        calendar = FundingCalendar(
            version="venue-4h/v1",
            source="synthetic-fixture",
            interval_ms=4 * H,
            settlements=(FundingSettlement(2 * H, 10.0),),
            symbol=SYMBOL)
        result, trade = _run(calendar)
        self.assertGreater(trade["funding_uncovered_ms"], 0)
        self.assertFalse(trade["funding_accounting_complete"])
        self.assertNotIn("funding_coverage_status", trade)
        self.assertNotIn("coverage", result["funding_calendar"])

    def test_published_legacy_config_hash_is_unchanged(self):
        calendar = FundingCalendar(
            version="FUNDING-CAL-v1",
            source="exchange-funding-history (Binance USD-M fundingRate)",
            interval_ms=28_800_000,
            settlements=(),
            symbol=SYMBOL)
        self.assertEqual(
            BacktestConfig(funding_calendar=calendar).config_hash(),
            "2e34e9d48595d5db")

    def test_loader_preserves_legacy_symbol_case(self):
        legacy = FundingCalendar(
            version="FUNDING-CAL-v1",
            source="exchange-funding-history",
            interval_ms=28_800_000,
            settlements=(),
            symbol="btcusdt")
        loaded = FundingCalendar.from_dict({
            "version": "FUNDING-CAL-v1",
            "source": "exchange-funding-history",
            "interval_ms": 28_800_000,
            "settlements": [],
            "symbol": "btcusdt",
        })
        self.assertEqual(loaded.symbol, "btcusdt")
        self.assertEqual(repr(loaded), repr(legacy))
        self.assertEqual(
            BacktestConfig(funding_calendar=loaded).config_hash(),
            BacktestConfig(funding_calendar=legacy).config_hash())


class BoundaryTest(unittest.TestCase):
    def test_entry_included_exit_excluded_with_explicit_coverage(self):
        settlements = (
            FundingSettlement(H, 10.0),
            FundingSettlement(5 * H, 10.0),
        )
        coverage = _coverage(H, 6 * H, settlements)
        calendar = _calendar_with_settlements(settlements, coverage)
        _, trade = _run(calendar)
        applied = [event["settlement_ms"]
                   for event in trade["funding_events"]
                   if event["basis"] == "settled"]
        self.assertEqual(applied, [H])
        self.assertAlmostEqual(trade["funding"], 1.0)


class EquivalenceTest(unittest.TestCase):
    def test_explicit_and_legacy_methods_match_known_payment(self):
        settlements = (
            FundingSettlement(H, 10.0),
            FundingSettlement(5 * H, 10.0),
        )
        coverage = _coverage(H, 6 * H, settlements)
        explicit = _calendar_with_settlements(settlements, coverage)
        legacy = FundingCalendar(
            version="venue-4h/v1",
            source="synthetic-fixture",
            interval_ms=4 * H,
            settlements=settlements,
            symbol=SYMBOL)
        _, explicit_trade = _run(explicit)
        _, legacy_trade = _run(legacy)
        self.assertAlmostEqual(explicit_trade["funding"],
                               legacy_trade["funding"])
        self.assertTrue(explicit_trade["funding_accounting_complete"])
        self.assertTrue(legacy_trade["funding_accounting_complete"])


class HashCommitmentTest(unittest.TestCase):
    def test_coverage_and_configuration_are_committed_by_hashes(self):
        first = _calendar_with_settlements((), _coverage(H, 5 * H))
        second = _calendar_with_settlements((), _coverage(H, 6 * H))
        self.assertNotEqual(first.calendar_hash(), second.calendar_hash())
        self.assertNotEqual(
            BacktestConfig(funding_calendar=first).config_hash(),
            BacktestConfig(funding_calendar=second).config_hash())


class LoaderCoverageTest(unittest.TestCase):
    def test_offline_loaders_preserve_explicit_coverage(self):
        from scripts.run_family_evaluation import _load_calendar as load_family
        from scripts.reconstruct_replay_traces import _load_calendar as load_replay
        from scripts.run_dashboard_backtest import _load_calendar as load_dashboard

        settlement = FundingSettlement(2 * H, 10.0)
        coverage = _coverage(H, 5 * H, (settlement,))
        payload = {
            "version": "synthetic/v1",
            "source": "synthetic-fixture",
            "interval_ms": None,
            "symbol": SYMBOL,
            "settlements": [{
                "settlement_ms": settlement.settlement_ms,
                "rate_bps": settlement.rate_bps,
            }],
            "coverage": coverage.to_dict(),
        }
        path = self.tmp_path("calendar.json", payload)
        loaded = (
            load_family(path),
            load_replay(path, SYMBOL),
            load_dashboard(path),
        )
        for calendar in loaded:
            self.assertIsNotNone(calendar.coverage)
            self.assertEqual(calendar.coverage.status, "complete")
            self.assertEqual(calendar.coverage.interval_start_ms, H)
            self.assertEqual(calendar.coverage.interval_end_ms, 5 * H)

    @staticmethod
    def tmp_path(name, payload):
        directory = Path(tempfile.mkdtemp(prefix="funding-coverage-loader-"))
        path = directory / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path


class AdapterCoverageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="funding-coverage-adapter-"))
        self.candles = [
            PaperCandle(0, 100.0, 101.0, 99.0, 100.0, 59_999),
            PaperCandle(60_000, 101.6, 103.0, 101.55, 102.0, 119_000),
            PaperCandle(120_000, 102.0, 103.0, 101.0, 102.5, 179_000),
            PaperCandle(180_000, 102.0, 103.0, 101.0, 102.5, 239_000),
        ]
        self.observation = {
            "observation_id": "COVERAGE|119000",
            "symbol": "FUNDUSDT",
            "role": "candidate",
            "decision_ms": 119_000,
            "seleccion": {"move_24h_pct": 2.4},
            "side": "UP",
        }

    def _process(self, name, calendar):
        adapter = OperativoAdapter(
            store_path=self.tmp / (name + ".jsonl"),
            cfg=OperativoConfig(),
            funding_calendars={"FUNDUSDT": calendar},
        )
        trade = adapter.procesar_observacion(self.observation, self.candles)
        adapter.persistir(trade)
        adapter.close()
        return trade, json.loads(
            (self.tmp / (name + ".jsonl")).read_text(encoding="utf-8").splitlines()[-1])

    def test_complete_coverage_persists_known_zero_and_complete_net(self):
        coverage = _coverage(
            120_000, 180_000, symbol="FUNDUSDT")
        calendar = FundingCalendar(
            version="synthetic/v1",
            source="synthetic-fixture",
            interval_ms=None,
            settlements=(),
            symbol="FUNDUSDT",
            coverage=coverage,
        )
        trade, row = self._process("complete", calendar)
        self.assertEqual(trade.funding, 0.0)
        self.assertTrue(row["funding_cuenta_completa"])
        self.assertEqual(row["funding_cobertura_estado"], "complete")
        self.assertEqual(row["funding_cobertura_inicio_ms"], 120_000)
        self.assertEqual(row["funding_cobertura_fin_ms"], 180_000)
        self.assertEqual(row["neto_estado"], "COMPLETO")

    def test_partial_coverage_does_not_credit_observed_amount(self):
        settlement = FundingSettlement(120_000, 1.0)
        coverage = _coverage(
            120_000, 150_000, (settlement,), symbol="FUNDUSDT")
        calendar = FundingCalendar(
            version="synthetic/v1",
            source="synthetic-fixture",
            interval_ms=None,
            settlements=(settlement,),
            symbol="FUNDUSDT",
            coverage=coverage,
        )
        trade, row = self._process("partial", calendar)
        self.assertIsNone(trade.funding)
        self.assertFalse(row["funding_cuenta_completa"])
        self.assertEqual(row["funding_sin_cubrir_ms"], 30_000)
        self.assertEqual(row["neto_estado"],
                         "CONDICIONADO_SIN_FUNDING_COMPLETO")

    def test_invalid_coverage_is_persisted_as_unknown(self):
        coverage = _coverage(
            120_000, 180_000, symbol="FUNDUSDT",
            request_symbol="ETHUSDT")
        calendar = FundingCalendar(
            version="synthetic/v1",
            source="synthetic-fixture",
            interval_ms=None,
            settlements=(),
            symbol="FUNDUSDT",
            coverage=coverage,
        )
        trade, row = self._process("invalid", calendar)
        self.assertIsNone(trade.funding)
        self.assertEqual(row["funding_cobertura_estado"], "unknown")
        self.assertEqual(row["funding_cobertura"]["status"], "unknown")
        self.assertTrue(row["funding_cobertura_errores"])
        self.assertEqual(row["neto_estado"],
                         "CONDICIONADO_SIN_FUNDING_COMPLETO")

    def test_open_position_is_not_persisted_as_complete_net(self):
        adapter = OperativoAdapter(
            store_path=self.tmp / "open.jsonl",
            cfg=OperativoConfig(),
        )
        observation_id = "OPEN|119000"
        adapter._funding_cuenta[observation_id] = {
            "funding_cuenta_completa": True,
        }
        trade = OperativoTradeResult(
            observation_id=observation_id,
            symbol="FUNDUSDT",
            role="candidate",
            direction="LONG",
            decision="ENTRADA_EJECUTADA",
            decision_ms=119_000,
            entry_px=100.0,
            entry_ms=120_000,
            stop_px=99.5,
            exit_px=101.0,
            exit_ms=None,
            exit_reason="open_at_end",
            exit_executed=False,
            open_at_end=True,
            qty=10.0,
            gross_pnl=10.0,
            fees=0.0,
            spread_slip=0.0,
            funding=0.0,
            net_pnl=10.0,
            funding_estado="settlement-calendar",
            config_hash="test",
            engine_version="test",
        )
        adapter.persistir(trade)
        adapter.close()
        row = json.loads(
            (self.tmp / "open.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(row["neto_estado"], "UNKNOWN")
        self.assertIsNone(row["net_pnl"])
        self.assertEqual(row["net_pnl_marca"], 10.0)


if __name__ == "__main__":
    unittest.main()
