from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LiquidationConfig:
    window_seconds: int
    individual_notional_usdt: dict[str, float]
    window_notional_usdt: dict[str, float]


@dataclass(frozen=True)
class FundingConfig:
    history_size: int
    minimum_samples: int
    lower_percentile: float
    upper_percentile: float


@dataclass(frozen=True)
class VolumeConfig:
    bucket_seconds: int
    history_buckets: int
    minimum_buckets: int
    z_score_threshold: float


@dataclass(frozen=True)
class DiscoveryConfig:
    enabled: bool
    interval_seconds: int
    hot_dynamic_slots: int
    min_quote_volume_usdt: float
    top_n: int
    min_votes: int


@dataclass(frozen=True)
class UniverseConfig:
    """Dynamic HOT-universe budgets (P1-12B). All values operator-tunable.

    Stream/connection caps are CONSERVATIVE local policy, not Binance
    guarantees: the official USD-M websocket docs were not fetchable from
    this environment, so every transport assumption below is UNVERIFIED and
    the manager fails closed (no promotion) when a budget would break.
    """
    enabled: bool
    max_hot_slots: int
    max_total_streams: int
    max_streams_per_connection: int
    max_connections: int
    promotion_interval_seconds: int
    min_dwell_seconds: int
    demotion_cooldown_seconds: int
    max_discovery_age_seconds: int
    demote_after_missed_scans: int
    max_hot_reconnects_per_hour: int
    clock_skew_tolerance_ms: int


@dataclass(frozen=True)
class OpenInterestConfig:
    enabled: bool
    interval_seconds: int
    request_timeout_seconds: float
    stale_after_seconds: int


@dataclass(frozen=True)
class ClockSyncConfig:
    interval_seconds: int
    samples: int
    request_timeout_seconds: float


@dataclass(frozen=True)
class ProbeConfig:
    symbols: tuple[str, ...]
    summary_interval_seconds: int
    stale_after_seconds: int
    max_event_clock_skew_ms: int
    telemetry_max_samples: int
    clock_sync: ClockSyncConfig
    liquidation: LiquidationConfig
    funding: FundingConfig
    volume: VolumeConfig
    observation_sample_ms: dict = field(default_factory=dict)
    discovery: DiscoveryConfig = field(default_factory=lambda: DiscoveryConfig(
        enabled=True, interval_seconds=600, hot_dynamic_slots=6,
        min_quote_volume_usdt=1_000_000.0, top_n=10, min_votes=2))
    open_interest: OpenInterestConfig = field(
        default_factory=lambda: OpenInterestConfig(
            enabled=True, interval_seconds=60,
            request_timeout_seconds=15.0, stale_after_seconds=180))
    universe: UniverseConfig = field(
        default_factory=lambda: UniverseConfig(
            enabled=True, max_hot_slots=3, max_total_streams=60,
            max_streams_per_connection=50, max_connections=6,
            promotion_interval_seconds=600, min_dwell_seconds=1800,
            demotion_cooldown_seconds=3600, max_discovery_age_seconds=1800,
            demote_after_missed_scans=2, max_hot_reconnects_per_hour=10,
            clock_skew_tolerance_ms=60_000))


def _positive(name: str, value: Any) -> float:
    number = float(value)
    if number <= 0:
        raise ValueError(f"{name} debe ser mayor que cero")
    return number


def _observation_sample_ms(raw: Any) -> dict:
    """Optional per-kind observation sampling intervals (ms).

    Absent section means "no operator override": the persistence code
    defaults apply. Present values must be positive integers; 0 or
    negative is rejected here (disable per kind via configure_sampling).
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("observation_sample_ms debe ser un objeto kind->ms")
    out = {}
    for kind, value in raw.items():
        out[str(kind)] = int(_positive(f"observation_sample_ms.{kind}", value))
    return out


def _discovery_config(raw: Any) -> DiscoveryConfig:
    """Optional discovery section; absent means code defaults (enabled)."""
    raw = raw if isinstance(raw, dict) else {}
    enabled = raw.get("enabled", True)
    hot_slots = int(raw.get("hot_dynamic_slots", 6))
    top_n = int(raw.get("top_n", 10))
    min_votes = int(raw.get("min_votes", 2))
    if hot_slots < 0 or top_n < 1 or min_votes < 1:
        raise ValueError(
            "discovery requires hot_dynamic_slots >= 0, top_n >= 1, min_votes >= 1")
    floor = raw.get("min_quote_volume_usdt", 1_000_000.0)
    if float(floor) < 0:
        raise ValueError("discovery.min_quote_volume_usdt must be >= 0")
    return DiscoveryConfig(
        enabled=bool(enabled),
        interval_seconds=int(_positive(
            "discovery.interval_seconds", raw.get("interval_seconds", 600))),
        hot_dynamic_slots=hot_slots,
        min_quote_volume_usdt=float(floor),
        top_n=top_n,
        min_votes=min_votes,
    )


def load_config(path: str | Path) -> ProbeConfig:
    bot_mode = os.environ.get("BOT_MODE", "observe").strip().lower()
    if bot_mode != "observe":
        raise RuntimeError(
            f"BOT_MODE={bot_mode!r} no esta permitido en Fase 1; use BOT_MODE=observe"
        )

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    symbols = tuple(dict.fromkeys(str(item).strip().upper() for item in raw["symbols"]))
    if not symbols or any(not symbol.endswith("USDT") for symbol in symbols):
        raise ValueError("symbols debe contener al menos un contrato USD-M terminado en USDT")

    liquidation_raw = raw["liquidation"]
    individual = {
        str(key).upper(): _positive(f"individual_notional_usdt.{key}", value)
        for key, value in liquidation_raw["individual_notional_usdt"].items()
    }
    window = {
        str(key).upper(): _positive(f"window_notional_usdt.{key}", value)
        for key, value in liquidation_raw["window_notional_usdt"].items()
    }
    missing = set(symbols) - (individual.keys() & window.keys())
    if missing:
        raise ValueError(f"Faltan umbrales de liquidacion para: {sorted(missing)}")

    funding_raw = raw["funding"]
    lower = float(funding_raw["lower_percentile"])
    upper = float(funding_raw["upper_percentile"])
    if not 0 < lower < upper < 1:
        raise ValueError("Los percentiles de funding deben cumplir 0 < lower < upper < 1")

def _universe_config(raw: Any) -> UniverseConfig:
    """Optional dynamic-universe section; absent means code defaults."""
    raw = raw if isinstance(raw, dict) else {}
    def _int(name: str, default: int, lo: int) -> int:
        value = int(raw.get(name, default))
        if value < lo:
            raise ValueError(f"universe.{name} must be >= {lo}")
        return value
    return UniverseConfig(
        enabled=bool(raw.get("enabled", True)),
        max_hot_slots=_int("max_hot_slots", 3, 0),
        max_total_streams=_int("max_total_streams", 60, 1),
        max_streams_per_connection=_int("max_streams_per_connection", 50, 1),
        max_connections=_int("max_connections", 6, 1),
        promotion_interval_seconds=int(_positive(
            "universe.promotion_interval_seconds",
            raw.get("promotion_interval_seconds", 600))),
        min_dwell_seconds=_int("min_dwell_seconds", 1800, 0),
        demotion_cooldown_seconds=_int("demotion_cooldown_seconds", 3600, 0),
        max_discovery_age_seconds=_int("max_discovery_age_seconds", 1800, 60),
        demote_after_missed_scans=_int("demote_after_missed_scans", 2, 1),
        max_hot_reconnects_per_hour=_int(
            "max_hot_reconnects_per_hour", 10, 1),
        clock_skew_tolerance_ms=_int(
            "clock_skew_tolerance_ms", 60_000, 0),
    )


def _open_interest_config(raw: Any) -> OpenInterestConfig:
    """Optional OI section; absent means code defaults (enabled, 60s)."""
    raw = raw if isinstance(raw, dict) else {}
    return OpenInterestConfig(
        enabled=bool(raw.get("enabled", True)),
        interval_seconds=int(_positive(
            "open_interest.interval_seconds",
            raw.get("interval_seconds", 60))),
        request_timeout_seconds=_positive(
            "open_interest.request_timeout_seconds",
            raw.get("request_timeout_seconds", 15.0)),
        stale_after_seconds=int(_positive(
            "open_interest.stale_after_seconds",
            raw.get("stale_after_seconds", 180))),
    )


def load_config(path: str | Path) -> ProbeConfig:
    bot_mode = os.environ.get("BOT_MODE", "observe").strip().lower()
    if bot_mode != "observe":
        raise RuntimeError(
            f"BOT_MODE={bot_mode!r} no esta permitido en Fase 1; use BOT_MODE=observe"
        )

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    symbols = tuple(dict.fromkeys(str(item).strip().upper() for item in raw["symbols"]))
    if not symbols or any(not symbol.endswith("USDT") for symbol in symbols):
        raise ValueError("symbols debe contener al menos un contrato USD-M terminado en USDT")

    liquidation_raw = raw["liquidation"]
    individual = {
        str(key).upper(): _positive(f"individual_notional_usdt.{key}", value)
        for key, value in liquidation_raw["individual_notional_usdt"].items()
    }
    window = {
        str(key).upper(): _positive(f"window_notional_usdt.{key}", value)
        for key, value in liquidation_raw["window_notional_usdt"].items()
    }
    missing = set(symbols) - (individual.keys() & window.keys())
    if missing:
        raise ValueError(f"Faltan umbrales de liquidacion para: {sorted(missing)}")

    funding_raw = raw["funding"]
    lower = float(funding_raw["lower_percentile"])
    upper = float(funding_raw["upper_percentile"])
    if not 0 < lower < upper < 1:
        raise ValueError("Los percentiles de funding deben cumplir 0 < lower < upper < 1")

    return ProbeConfig(
        symbols=symbols,
        discovery=_discovery_config(raw.get("discovery", {})),
        open_interest=_open_interest_config(raw.get("open_interest", {})),
        universe=_universe_config(raw.get("universe", {})),
        observation_sample_ms=_observation_sample_ms(
            raw.get("observation_sample_ms", {})
        ),
        summary_interval_seconds=int(
            _positive("summary_interval_seconds", raw["summary_interval_seconds"])
        ),
        stale_after_seconds=int(_positive("stale_after_seconds", raw["stale_after_seconds"])),
        max_event_clock_skew_ms=int(
            _positive("max_event_clock_skew_ms", raw["max_event_clock_skew_ms"])
        ),
        telemetry_max_samples=int(
            _positive("telemetry_max_samples", raw.get("telemetry_max_samples", 20_000))
        ),
        clock_sync=ClockSyncConfig(
            interval_seconds=int(
                _positive(
                    "clock_sync.interval_seconds",
                    raw.get("clock_sync", {}).get("interval_seconds", 600),
                )
            ),
            samples=int(
                _positive("clock_sync.samples", raw.get("clock_sync", {}).get("samples", 5))
            ),
            request_timeout_seconds=_positive(
                "clock_sync.request_timeout_seconds",
                raw.get("clock_sync", {}).get("request_timeout_seconds", 5),
            ),
        ),
        liquidation=LiquidationConfig(
            window_seconds=int(
                _positive("liquidation.window_seconds", liquidation_raw["window_seconds"])
            ),
            individual_notional_usdt=individual,
            window_notional_usdt=window,
        ),
        funding=FundingConfig(
            history_size=int(_positive("funding.history_size", funding_raw["history_size"])),
            minimum_samples=int(
                _positive("funding.minimum_samples", funding_raw["minimum_samples"])
            ),
            lower_percentile=lower,
            upper_percentile=upper,
        ),
        volume=VolumeConfig(
            bucket_seconds=int(
                _positive("volume.bucket_seconds", raw["volume"]["bucket_seconds"])
            ),
            history_buckets=int(
                _positive("volume.history_buckets", raw["volume"]["history_buckets"])
            ),
            minimum_buckets=int(
                _positive("volume.minimum_buckets", raw["volume"]["minimum_buckets"])
            ),
            z_score_threshold=_positive(
                "volume.z_score_threshold", raw["volume"]["z_score_threshold"]
            ),
        ),
    )
