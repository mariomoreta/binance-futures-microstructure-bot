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
