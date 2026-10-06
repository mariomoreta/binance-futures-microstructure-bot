from __future__ import annotations

import asyncio
import json
import logging
import statistics
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

LOGGER = logging.getLogger("microstructure_probe")
SERVER_TIME_URL = "https://fapi.binance.com/fapi/v1/time"


@dataclass(frozen=True)
class ClockSample:
    offset_ms: float
    rtt_ms: float


def calculate_clock_sample(
    local_before_ms: float, server_time_ms: float, local_after_ms: float
) -> ClockSample:
    if local_after_ms < local_before_ms:
        raise ValueError("local_after_ms no puede ser anterior a local_before_ms")
    midpoint_ms = (local_before_ms + local_after_ms) / 2.0
    return ClockSample(
        offset_ms=float(server_time_ms) - midpoint_ms,
        rtt_ms=local_after_ms - local_before_ms,
    )


def corrected_lag_ms(local_receive_ms: float, exchange_timestamp_ms: float, offset_ms: float) -> float:
    return (local_receive_ms + offset_ms) - exchange_timestamp_ms


class ClockSynchronizer:
    def __init__(
        self,
        *,
        sample_count: int = 5,
        interval_seconds: float = 600.0,
        request_timeout_seconds: float = 5.0,
        fetch_server_time: Callable[[], int] | None = None,
        wall_clock_ms: Callable[[], float] | None = None,
    ) -> None:
        self.sample_count = sample_count
        self.interval_seconds = interval_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self._fetch_server_time = fetch_server_time or self._http_server_time
        self._wall_clock_ms = wall_clock_ms or (lambda: time.time_ns() / 1_000_000)
        self.offset_ms: float | None = None
        self.rtt_ms: float | None = None
        self.last_sync_timestamp: str | None = None
        self.successful_syncs = 0
        self.failed_syncs = 0
        self.valid_samples = 0
        self.failed_samples = 0

    def _http_server_time(self) -> int:
        request = urllib.request.Request(SERVER_TIME_URL, method="GET")
        with urllib.request.urlopen(request, timeout=self.request_timeout_seconds) as response:
            payload = json.loads(response.read())
        return int(payload["serverTime"])

    def _sample_once(self) -> ClockSample:
        before = self._wall_clock_ms()
        server_time = self._fetch_server_time()
        after = self._wall_clock_ms()
        return calculate_clock_sample(before, server_time, after)

    def collect_samples(self) -> list[ClockSample]:
        samples: list[ClockSample] = []
        for _ in range(self.sample_count):
            try:
                samples.append(self._sample_once())
                self.valid_samples += 1
            except Exception as exc:
                self.failed_samples += 1
                LOGGER.warning(
                    json.dumps(
                        {
                            "kind": "clock_sync_sample_error",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                )
        return samples

    async def sync(self) -> bool:
        samples = await asyncio.to_thread(self.collect_samples)
        if not samples:
            self.failed_syncs += 1
            LOGGER.warning(json.dumps({"kind": "clock_sync_failed", **self.snapshot()}))
            return False
        self.offset_ms = statistics.median(sample.offset_ms for sample in samples)
        self.rtt_ms = statistics.median(sample.rtt_ms for sample in samples)
        self.last_sync_timestamp = datetime.now(timezone.utc).isoformat()
        self.successful_syncs += 1
        LOGGER.info(json.dumps({"kind": "clock_sync", **self.snapshot()}))
        return True

    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                await self.sync()

    def snapshot(self) -> dict[str, float | int | str | None]:
        return {
            "clockOffsetMs": None if self.offset_ms is None else round(self.offset_ms, 6),
            "serverTimeRttMs": None if self.rtt_ms is None else round(self.rtt_ms, 6),
            "lastClockSyncTimestamp": self.last_sync_timestamp,
            "clockSyncSuccessful": self.successful_syncs,
            "clockSyncFailed": self.failed_syncs,
            "clockSamplesValid": self.valid_samples,
            "clockSamplesFailed": self.failed_samples,
        }
