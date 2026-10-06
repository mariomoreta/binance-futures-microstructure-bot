from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class DetectedEvent:
    timestamp_ms: int
    symbol: str
    event_type: str
    magnitude: float
    price_snapshot: float
    details: dict[str, Any]

    def as_log_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["timestamp"] = datetime.fromtimestamp(
            self.timestamp_ms / 1000, tz=timezone.utc
        ).isoformat()
        return record

